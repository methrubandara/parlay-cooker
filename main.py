from fastapi import FastAPI, HTTPException, Query
import os, time, requests, itertools, json
from datetime import datetime, timezone
from typing import Dict, Any, List

app = FastAPI()

# -----------------------------
# Config
# -----------------------------
BASE = "https://api.the-odds-api.com"
SPORT = "americanfootball_nfl"

# Multiple keys (rotate)
_ODDS_KEYS = [
    os.getenv("ODDS_API_KEY_1"),
    os.getenv("ODDS_API_KEY_2"),
    os.getenv("ODDS_API_KEY_3"),
    os.getenv("ODDS_API_KEY"),  # optional legacy single-key fallback
]
ODDS_API_KEYS: List[str] = [k for k in _ODDS_KEYS if k]
if not ODDS_API_KEYS:
    # we still raise at call-time to surface a clear message
    ODDS_API_KEYS = []

_key_cycle = itertools.cycle(ODDS_API_KEYS) if ODDS_API_KEYS else None

TTL_EVENTS = int(os.getenv("TTL_EVENTS", "60"))   # seconds
TTL_PROPS  = int(os.getenv("TTL_PROPS", "60"))    # seconds

# simple in-memory cache (per instance)
_cache = {
    "events": {"ts": 0.0, "data": []},  # list of events from /odds
    "props": {}                         # key: f"{event_id}|{books}|{markets}" -> {ts, data}
}

# optional tiny disk snapshot so we can serve last-known-good when quota pops mid-day
DISK_CACHE_PATH = "/tmp/parlay_disk_cache.json"
_MAX_DISK_BYTES = 800_000  # keep it small to avoid issues

def _disk_cache_read() -> Dict[str, Any]:
    try:
        if not os.path.exists(DISK_CACHE_PATH):
            return {}
        with open(DISK_CACHE_PATH, "r") as f:
            return json.loads(f.read() or "{}")
    except Exception:
        return {}

def _disk_cache_write(blob: Dict[str, Any]) -> None:
    try:
        js = json.dumps(blob)
        # guard size
        if len(js) > _MAX_DISK_BYTES:
            return
        with open(DISK_CACHE_PATH, "w") as f:
            f.write(js)
    except Exception:
        pass

_disk_cache = _disk_cache_read()

# -----------------------------
# Helpers
# -----------------------------
def _now() -> float:
    return time.time()

def _rotate_key() -> str:
    if not _key_cycle:
        raise HTTPException(500, detail="No API keys configured. Add ODDS_API_KEY_1, ODDS_API_KEY_2, ...")
    return next(_key_cycle)

def _cache_get(mem_key: str):
    return _disk_cache.get(mem_key)

def _cache_set(mem_key: str, data: Any):
    _disk_cache[mem_key] = data
    _disk_cache_write(_disk_cache)

def _provider_get(path: str, params: dict, allow_rotation=True) -> dict:
    """
    GET with key rotation:
      - tries each key until one succeeds
      - if quota/usage error, rotates to next key
      - if all fail on quota, raises 429 with details
    """
    url = f"{BASE}{path}"
    last_error = None
    tried = 0
    total = max(1, len(ODDS_API_KEYS) or 1)

    while tried < total:
        api_key = _rotate_key()
        qp = {"apiKey": api_key, **params}
        try:
            r = requests.get(url, params=qp, timeout=25)
        except requests.RequestException as e:
            last_error = f"Request error: {e}"
            tried += 1
            continue

        if r.status_code == 200:
            return r.json()

        body = r.text[:2000]
        # The Odds API quota codes often return 402 or body mentions usage/credits
        if r.status_code in (402, 429) or "OUT_OF_USAGE_CREDITS" in body or "quota" in body.lower():
            last_error = f"Key exhausted or quota hit. status={r.status_code}, body={body[:220]}"
            tried += 1
            # rotate and try next key
            continue

        # Other provider errors (invalid market, event expired, etc.)
        raise HTTPException(r.status_code, detail={
            "provider_status": r.status_code,
            "provider_body": body,
            "url": url,
            "params": {k:v for k,v in qp.items() if k != "apiKey"}
        })

    # if we get here, all keys failed on quota
    raise HTTPException(429, detail={
        "message": "All provider keys exhausted (usage quota). Reduce markets, query one event at a time, or wait for reset.",
        "url": url,
        "params": {k:v for k,v in params.items() if k != "apiKey"}
    })

def _get(path: str, params: dict, cache_key: str | None = None, ttl: int | None = None) -> dict:
    """Provider GET with optional cache and disk snapshot fallback on quota."""
    # serve in-memory event cache separately (kept below)
    if cache_key and ttl:
        # try fresh-ish memory cache (your existing in-memory cache applies for events/props too)
        pass

    try:
        data = _provider_get(path, params)
        if cache_key:
            _cache_set(cache_key, {"ts": _now(), "data": data})
        return data
    except HTTPException as e:
        # If 429 (quota), try last-known-good disk snapshot
        if e.status_code == 429 and cache_key:
            snap = _cache_get(cache_key)
            if snap and isinstance(snap, dict) and "data" in snap:
                return snap["data"]
        raise

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
    # serve memory cache unless refresh is requested
    if (not refresh) and (_now() - _cache["events"]["ts"] < TTL_EVENTS) and _cache["events"]["data"]:
        data = _cache["events"]["data"]
    else:
        data = _get(
            f"/v4/sports/{SPORT}/odds",
            {
                "regions": "us",
                "bookmakers": bookmakers,
                "markets": "h2h",        # cheap market to list events
                "oddsFormat": "american"
            },
            cache_key="events",
            ttl=TTL_EVENTS,
        )
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
    limit_events: int = Query(8, ge=1, le=16),   # keep smaller to avoid quotas/timeouts
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
        events = _get(
            f"/v4/sports/{SPORT}/odds",
            {
                "regions": "us",
                "bookmakers": "draftkings",
                "markets": "h2h",
                "oddsFormat": "american"
            },
            cache_key="events",
            ttl=TTL_EVENTS,
        )[:limit_events]
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
            ev_props = _get(
                f"/v4/sports/{SPORT}/events/{eid}/odds",
                {
                    "regions": "us",
                    "bookmakers": "draftkings",
                    "markets": mks,
                    "oddsFormat": "american"
                },
                cache_key=key,
                ttl=TTL_PROPS,
            )
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
