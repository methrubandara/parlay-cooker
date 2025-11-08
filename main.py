from fastapi import FastAPI, HTTPException, Query
import os, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

SGO_API_KEY = os.getenv("SGO_API_KEY")
BASE_URL = os.getenv("SGO_BASE_URL", "https://api.sportsgameodds.com").rstrip("/")

def sgo_headers():
    if not SGO_API_KEY:
        raise HTTPException(500, "Missing SGO_API_KEY")
    return {"x-api-key": SGO_API_KEY}

@app.get("/health")
def health():
    return {"ok": True, "provider": "SportsGameOdds", "time": datetime.utcnow().isoformat()}

# --- 1) RAW: show SGO events payload exactly as returned ---
@app.get("/sgo/events/raw")
def sgo_events_raw(date: str | None = Query(None),
league: str = "NFL",          # <- default ID
bookmakers: str = "draftkings,fanduel"):
    """
    Pure proxy to SGO 'events' endpoint. Adjust path/params if your docs differ.
    """
    url_candidates = [
        f"{BASE_URL}/v2/events",
        f"{BASE_URL}/v1/events",
        f"{BASE_URL}/events",
    ]
    params = {
        "leagueID": league,             # <- key change
        "bookmakers": bookmakers,
        "oddsAvailable": "true",
        "includeOdds": "true",
        "includeAltLines": "true",
    }
    if date:
        params["date"] = date

    headers = sgo_headers()
    errors = []
    for url in url_candidates:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        if r.status_code == 200:
            return r.json()
        errors.append({"url": url, "status": r.status_code, "body": r.text[:300]})

    raise HTTPException(502, detail={"message": "SGO events endpoint not found",
                                     "attempts": errors})

# --- 2) NORMALIZED: extract player props from events ---
def is_player_prop_market(mkey: str) -> bool:
    if not mkey:
        return False
    m = mkey.lower()
    # catch common keys; expand when you see real keys in /sgo/events/raw
    return (
        "player" in m or
        m in {
            "player_pass_tds","player_passing_tds",
            "player_passing_yards","player_pass_yards",
            "player_receptions","player_rec",
            "player_receiving_yards","player_rec_yards",
            "player_rushing_yards","player_rush_yards",
            "player_rush_attempts","player_attempts",
            "player_anytime_td","player_anytime_touchdown"
        }
    )

def norm_american(price) -> int | None:
    # tries dict formats {american: "-115", decimal: 1.87} or plain str/int
    if price is None:
        return None
    if isinstance(price, dict):
        if "american" in price:
            try:
                return int(str(price["american"]))
            except Exception:
                return None
        if "decimal" in price:
            dec = float(price["decimal"])
            # approx convert to american
            return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))
    try:
        return int(str(price))
    except Exception:
        return None

@app.get("/nfl/props")
raw = sgo_events_raw(date=date, league=league, bookmakers=books)
# and change the default to ID-style too:
def nfl_props(date: str | None = Query(None),
              books: str = Query("draftkings,fanduel"),
              league: str = Query("NFL")):   # <- default ID

    # 2) normalize event list
    events = []
    if isinstance(raw, list):
        events = raw
    elif isinstance(raw, dict):
        # common wrappers: data / results / events
        events = raw.get("data") or raw.get("results") or raw.get("events") or []
        if not isinstance(events, list):
            events = []

    books_list = [b.strip() for b in books.split(",") if b.strip()]
    props_out = []

    # 3) walk: event -> bookmakers -> markets -> outcomes
    for ev in events:
        game_id = ev.get("id") or ev.get("eventId") or ev.get("uid") or ""
        home = ev.get("home_team") or ev.get("homeTeam") or ""
        away = ev.get("away_team") or ev.get("awayTeam") or ""
        game_label = f"{away}@{home}" if home or away else str(game_id)

        for bm in ev.get("bookmakers", []) or ev.get("books", []) or []:
            book_key = bm.get("key") or bm.get("bookmaker") or bm.get("name") or ""
            if book_key and book_key not in books_list:
                continue

            markets = bm.get("markets") or bm.get("odds") or []
            for mk in markets:
                mkey = mk.get("key") or mk.get("market") or mk.get("name") or ""
                if not is_player_prop_market(mkey):
                    continue

                for o in mk.get("outcomes", []) or mk.get("selections", []) or []:
                    player = (
                        o.get("description") or o.get("name") or
                        o.get("participant") or o.get("player") or "Unknown Player"
                    )
                    line = o.get("point") or o.get("total") or o.get("line") or o.get("handicap")
                    try:
                        line = float(line) if line is not None else None
                    except Exception:
                        line = None
                    american = norm_american(o.get("price") or o.get("odds"))

                    # direction (Over/Under) if provided
                    direction = (o.get("side") or o.get("label") or o.get("type") or "").title()
                    if direction not in ("Over", "Under"):
                        # many APIs encode O/U in outcome name, keep raw
                        direction = None

                    if american is None:
                        continue

                    props_out.append({
                        "player": player,
                        "market": mkey,
                        "line": line,
                        "direction": direction,
                        "odds": american,
                        "book": book_key,
                        "game": game_label
                    })

    return {
        "slate_date": date,
        "provider": "SGO",
        "books_used": books_list,
        "count": len(props_out),
        "props": props_out[:200],  # cap for readability
        "timestamp": datetime.utcnow().isoformat()
    }