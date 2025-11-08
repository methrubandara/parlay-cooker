from fastapi import FastAPI, HTTPException
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env (local dev)
load_dotenv()

app = FastAPI()

# Read the API key from Render env or .env
SGO_API_KEY = os.getenv("SGO_API_KEY")
BASE_URL = "https://api.sportsgameodds.com"

@app.get("/health")
def health():
    """Simple health check."""
    return {
        "ok": True,
        "provider": "SportsGameOdds",
        "time": datetime.utcnow().isoformat()
    }


# Helper: add API key header
def sgo_headers():
    if not SGO_API_KEY:
        raise HTTPException(500, "Missing SGO_API_KEY")
    # SportsGameOdds uses x-api-key for auth
    return {"x-api-key": SGO_API_KEY}


# Common SGO endpoints that could serve player props
CANDIDATE_PATHS = [
    "/v2/odds/player-props",
    "/v2/player-props",
    "/v2/odds",
    "/v1/odds/player-props",
    "/v1/player-props",
    "/v1/odds",
    "/odds/player-props",
    "/odds",
]


def build_param_variants(date, books):
    """Generate parameter variants across known naming conventions."""
    base_variants = [
        {"league": "nfl", "bookmakers": books, "includeAltLines": "true"},
        {"sport": "nfl",  "bookmakers": books, "includeAltLines": "true"},
        {"league": "nfl", "books": books,      "includeAltLines": "true"},
        {"sport": "nfl",  "books": books,      "includeAltLines": "true"},
    ]
    for v in base_variants:
        if date:
            v["date"] = date
    # Some endpoints need explicit market field
    with_market = []
    for v in base_variants:
        vv = v.copy()
        vv["market"] = "player_props"
        with_market.append(vv)
    return base_variants + with_market


@app.get("/nfl/props")
def get_props(date: str | None = None, books: str = "draftkings,fanduel"):
    """
    Attempt multiple SGO API paths and parameter variants to find player prop odds.
    Returns first working combination and small sample of data.
    """
    headers = sgo_headers()
    errors = []

    for path in CANDIDATE_PATHS:
        url = f"{BASE_URL.rstrip('/')}{path}"
        for params in build_param_variants(date, books):
            try:
                r = requests.get(url, headers=headers, params=params, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "ok": True,
                        "used_url": url,
                        "used_params": params,
                        "count_hint": (
                            len(data)
                            if isinstance(data, list)
                            else len(data.get("data", []))
                            if isinstance(data, dict)
                            else 0
                        ),
                        "sample": (
                            data[:2]
                            if isinstance(data, list)
                            else data.get("data", data)
                        ),
                    }
                else:
                    errors.append({
                        "url": url,
                        "params": params,
                        "status": r.status_code,
                        "body": r.text[:200]
                    })
            except Exception as e:
                errors.append({"url": url, "params": params, "error": str(e)})

    raise HTTPException(status_code=502, detail={
        "message": "Could not locate the correct SGO endpoint for player props.",
        "hint": "Check SGO API docs for the correct path/param names.",
        "attempts": errors[:8]
    })
