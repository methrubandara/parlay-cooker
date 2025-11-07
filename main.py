from fastapi import FastAPI
import requests
import os
from datetime import datetime

app = FastAPI()

SGO_API_KEY = os.getenv("SGO_API_KEY")
BASE_URL = os.getenv("SGO_BASE_URL", "https://api.sportsgameodds.com").rstrip("/")

@app.get("/health")
def health():
    return {"ok": True, "provider": "SportsGameOdds", "time": datetime.utcnow().isoformat()}

def sgo_headers():
    if not SGO_API_KEY:
        raise RuntimeError("Missing SGO_API_KEY")
    # SGO uses x-api-key, not Authorization
    return {"x-api-key": SGO_API_KEY}

@app.get("/nfl/props")
def get_props(date: str | None = None, books: str = "draftkings,fanduel"):
    """
    Fetch NFL player props from SGO.
    NOTE: Endpoint/params may vary by SGO plan/version. Adjust the path/params to match their docs.
    """
    try:
        headers = sgo_headers()
        # Try a common player-props endpoint; change if your docs specify another path
        endpoint = f"{BASE_URL}/v2/odds/player-props"

        # Typical params – update names per SGO docs if needed (league vs sport, bookmakers vs books, etc.)
        params = {
            "league": "nfl",                     # or 'sport': 'nfl'
            "bookmakers": books,                 # some docs use 'bookmakers'
            "includeAltLines": "true",           # if your plan supports it
        }
        if date:
            params["date"] = date                # only if the API supports a date filter

        resp = requests.get(endpoint, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            return {"error": f"SGO API error: {resp.status_code}", "detail": resp.text}

        data = resp.json()
        # Show a small sample to confirm shape
        if isinstance(data, list):
            sample = data[:3]
            count = len(data)
        elif isinstance(data, dict):
            # some APIs wrap results, try common keys
            items = data.get("data") or data.get("results") or data.get("events") or []
            sample = items[:3] if isinstance(items, list) else [items]
            count = len(items) if isinstance(items, list) else (1 if items else 0)
        else:
            sample, count = [data], 1

        return {"count": count, "sample": sample}
    except Exception as e:
        return {"error": str(e)}
