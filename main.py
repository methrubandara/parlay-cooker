import os, time
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------- CONFIG ----------
THEODDS_KEY = os.getenv("THEODDS_API_KEY")  # set this in your host's env
SPORT = "americanfootball_nfl"
REGIONS = "us"  # us | us2 | eu
ODDS_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_BOOKS = ["draftkings", "fanduel"]
DEFAULT_MARKETS = (
    "player_pass_tds,"
    "player_pass_yards,"
    "player_receptions,"
    "player_receiving_yards,"
    "player_rushing_yards,"
    "player_anytime_td"
)

# ---------- MODELS ----------
class Projection(BaseModel):
    mean: float
    stdev: Optional[float] = None
    dist: Optional[str] = None  # "normal" | "poisson" | "binomial"

class Prop(BaseModel):
    player: str
    team: Optional[str] = None
    opponent: Optional[str] = None
    game: Optional[str] = None          # e.g., "BUF@NYJ"
    market: str                         # e.g., "player_pass_tds"
    line: float
    is_alt: bool
    odds: int                           # American odds
    book: str
    projection: Optional[Projection] = None
    context: Optional[Dict[str, Any]] = None

class Correlation(BaseModel):
    a: str
    b: str
    rho: float

class Slate(BaseModel):
    slate_date: str
    props: List[Prop]
    correlations: List[Correlation]
    timestamp: str
    provider: str
    books_used: List[str]

app = FastAPI(title="ParlayCooker Odds Service", version="1.0")

# ---------- HELPERS ----------
def parse_csv(csv: Optional[str], default_list: List[str]) -> List[str]:
    if not csv:
        return default_list
    return [x.strip() for x in csv.split(",") if x.strip()]

def normalize_event_name(event: dict) -> str:
    home, away = event.get("home_team", ""), event.get("away_team", "")
    return f"{away}@{home}" if away and home else event.get("id", "unknown_game")

def to_american(price_decimal: float) -> int:
    return int(round((price_decimal - 1) * 100)) if price_decimal >= 2 else int(round(-100 / (price_decimal - 1)))

async def fetch_market(client: httpx.AsyncClient, market: str, books_list: List[str]) -> list:
    if not THEODDS_KEY:
        raise HTTPException(500, "Missing THEODDS_API_KEY environment variable.")
    params = {
        "apiKey": THEODDS_KEY,
        "regions": REGIONS,
        "markets": market,
        "oddsFormat": "american",
        "bookmakers": ",".join(books_list),
    }
    url = f"{ODDS_BASE}/sports/{SPORT}/odds"
    r = await client.get(url, params=params, timeout=30)
    if r.status_code != 200:
        # Bubble up provider errors (quota, plan limitations, etc.)
        raise HTTPException(status_code=r.status_code, detail=f"TheOddsAPI error: {r.text}")
    return r.json()

def extract_props_from_event(event: dict, market: str, books_list: List[str]) -> List[Prop]:
    out: List[Prop] = []
    game = normalize_event_name(event)
    for bm in event.get("bookmakers", []):
        book_key = bm.get("key", "")
        if book_key not in books_list:
            continue
        for mk in bm.get("markets", []):
            if mk.get("key") != market:
                continue
            for o in mk.get("outcomes", []):
                player = o.get("description") or o.get("name") or "Unknown Player"

                # price (american preferred; fallback to decimal)
                american = None
                price = o.get("price")
                if isinstance(price, dict) and "american" in price:
                    american = int(price["american"])
                elif isinstance(price, dict) and "decimal" in price:
                    american = to_american(float(price["decimal"]))
                elif isinstance(price, (int, float)):
                    american = int(price)
                else:
                    continue  # skip if no price

                # line
                line = float(o.get("point") or o.get("total") or 0.0)

                out.append(Prop(
                    player=player,
                    market=market,
                    line=line,
                    is_alt=False,      # mark alt ladders yourself if your provider exposes them distinctly
                    odds=american,
                    book=book_key,
                    game=game
                ))
    return out

# ---------- ROUTES ----------
@app.get("/health")
def health():
    return {"ok": True, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "provider": "TheOddsAPI"}

@app.get("/nfl/props", response_model=Slate)
async def get_props(
    date: str = Query(..., description="YYYY-MM-DD (label only; odds are current)"),
    books: Optional[str] = Query(None, description="Comma-separated book keys, e.g., draftkings,fanduel"),
    markets: Optional[str] = Query(None, description="Comma-separated markets; default covers common player props"),
):
    books_list = parse_csv(books, DEFAULT_BOOKS)
    markets_list = parse_csv(markets, DEFAULT_MARKETS.split(","))

    props: List[Prop] = []
    async with httpx.AsyncClient() as client:
        for mkt in markets_list:
            data = await fetch_market(client, mkt, books_list)
            for event in data:
                props.extend(extract_props_from_event(event, mkt, books_list))

    # simple correlation priors (your GPT can refine)
    correlations = [
        Correlation(a="qb_pass_yards_over", b="wr_rec_yards_over", rho=0.55),
        Correlation(a="rb_rush_yards_over", b="own_qb_pass_yards_over", rho=-0.25),
    ]

    return Slate(
        slate_date=date,
        props=props,
        correlations=correlations,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        provider="TheOddsAPI",
        books_used=books_list,
    )
