from fastapi import FastAPI, HTTPException, Query
import os, time, requests
from datetime import datetime, timezone

app = FastAPI()

# -----------------------------
# Config
# -----------------------------
ODDS_API_KEY = os.getenv("ODDS_API_KEY")  # <-- set this on Render (or in .env locally)
BASE = "https://api.the-odds-api.com"
SPORT = "americanfootball_nfl"

# simple in-memory cache (per instance)
_cache = {
    "events": {"ts": 0.0, "data": []},  # list of events from /odds
    "props": {}                         # key: f"{event_id}|{books}|{markets}" -> {ts, data}
}
TTL_EVENTS = int(os.getenv("TTL_EVENTS", "60"))   # seconds
TTL_PROPS  = int(os.getenv("TTL_PROPS", "60"))    # seconds


# -----------------------------
# Helpers
# -----------------------------
def _get(path: str, params: dict) -> dict:
    """GET wrapper that adds apiKey and raises HTTPException on non-200."""
    if not ODDS_API_KEY:
        raise HTTPException(500, detail="Missing ODDS_API_KEY")
    r = requests.get(f"{BASE}{path}", params={"apiKey": ODDS_API_KEY, **params}, timeout=25)
    if r.status_code != 200:
        raise HTTPException(r.status_code, detail=r.text)
    return r.json()

def _now() -> float:
    return time.time()

def _normalize_props(event_json: dict, event_label: str) -> list[dict]:
    """Flatten bookmakers -> markets -> outcomes into a simple list."""
    out = []
    eid = event_json.get("id") or ""
    for bm in event_json.get("bookmakers", []) or []:
        if (bm.get("key") or "").lower() != "draftkings":
            continue
        for mk in bm.get("markets", []) or []:
            mkey = (mk.get("key") or "").lower()
            if not mkey.startswith("player_"):
                continue
            for o in mk.get("outcomes", []) or []:
                player = o.get("description") or o.get("name") or "Unknown Player"
                line = o.get("point") or o.get("line") or o.get("total")
                try:
                    line = float(line) if line is not None else None
                except Exception:
                    line = None
                direction = (o.get("name") or o.get("side") or "").title()
                if direction not in ("Over", "Under"):
                    direction = None
                price = o.get("price")
                try:
                    price = int(str(price))
                except Exception:
                    continue

                out.append({
                    "event_id": eid,
                    "game": event_label,
                    "book": "draftkings",
                    "market": mkey,
                    "player": player,
                    "line": line,
                    "direction": direction,
                    "odds": price,
                })
    return out


# -----------------------------
# Health
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True, "provider": "TheOddsAPI", "time": datetime.now(timezone.utc).isoformat()}

@app.head("/health")
def health_head():
    # lets UptimeRobot/Render health checks use HEAD
    return {}


# -----------------------------
# Events (IDs for current/next slate)
# -----------------------------
@app.get("/nfl/events")
def nfl_events(bookmakers: str = "draftkings", refresh: bool = False):
    """
    Returns upcoming/current NFL events (uses a cheap market to discover valid event IDs).
    Use these IDs to fetch per-event player props.
    """
    # serve cache unless refresh requested
    if not refresh and (_now() - _cache["events"]["ts"] < TTL_EVENTS) and _cache["events"]["data"]:
        data = _cache["events"]["data"]
    else:
        data = _get(f"/v4/sports/{SPORT}/odds", {
            "regions": "us",
            "bookmakers": bookmakers,
            "markets": "h2h",        # cheap market to list events
            "oddsFormat": "american"
        })
        _cache["events"] = {"ts": _now(), "data": data}

    events_min = []
    for ev in data:
        ev_id = ev.get("id")
        home = ev.get("home_team") or ""
        away = ev.get("away_team") or ""
        events_min.append({"id": ev_id, "matchup": f"{away} @ {home}"})
    return {"count": len(events_min), "events": events_min}


# -----------------------------
# Player props (DK-only, aggregated)
# -----------------------------
@app.get("/nfl/props")
def nfl_props_dk(
    markets: str = Query(
        "player_pass_tds,player_pass_yds,player_receptions,player_reception_yds,player_rush_yds,player_anytime_td"
    ),
    limit_events: int = Query(10, ge=1, le=32),
    refresh: bool = Query(False),
):
    """
    Aggregates DraftKings player props for the first N events.
    - markets: comma list of player_*** markets
    - limit_events: how many events to fetch
    - refresh: if true, bypasses caches (use sparingly)
    """
    # 1) get event list (cached)
    if not refresh and (_now() - _cache["events"]["ts"] < TTL_EVENTS) and _cache["events"]["data"]:
        events = _cache["events"]["data"][:limit_events]
    else:
        events = _get(f"/v4/sports/{SPORT}/odds", {
            "regions": "us",
            "bookmakers": "draftkings",
            "markets": "h2h",
            "oddsFormat": "american"
        })[:limit_events]
        _cache["events"] = {"ts": _now(), "data": events}

    # 2) for each event, fetch props (cached per event)
    all_props = []
    mks = ",".join([m.strip() for m in markets.split(",") if m.strip()])
    for ev in events:
        eid = ev.get("id")
        if not eid:
            continue
        key = f"{eid}|draftkings|{mks}"
        use_cache = (not refresh) and (key in _cache["props"]) and (_now() - _cache["props"][key]["ts"] < TTL_PROPS)

        if use_cache:
            ev_props = _cache["props"][key]["data"]
        else:
            ev_props = _get(f"/v4/sports/{SPORT}/events/{eid}/odds", {
                "regions": "us",
                "bookmakers": "draftkings",
                "markets": mks,
                "oddsFormat": "american"
            })
            _cache["props"][key] = {"ts": _now(), "data": ev_props}

        home = ev.get("home_team") or ""
        away = ev.get("away_team") or ""
        label = f"{away} @ {home}" if home and away else (ev.get("id") or "")
        all_props.extend(_normalize_props(ev_props, label))

    return {
        "provider": "TheOddsAPI",
        "book": "draftkings",
        "event_count": len(events),
        "markets_requested": mks.split(","),
        "count": len(all_props),
        "props": all_props[:500],  # cap for response size
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
