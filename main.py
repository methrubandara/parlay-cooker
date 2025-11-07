from fastapi import FastAPI
import requests
import os
from datetime import datetime

app = FastAPI()

SGO_API_KEY = os.getenv("SGO_API_KEY")
BASE_URL = "https://api.sportsgameodds.com"

@app.get("/health")
def health():
    return {"ok": True, "provider": "SportsGameOdds", "time": datetime.utcnow().isoformat()}

@app.get("/nfl/props")
def get_props(date: str = None, books: str = "draftkings,fanduel"):
    """Fetch NFL player props from SGO."""
    if not SGO_API_KEY:
        return {"error": "Missing SGO_API_KEY in environment."}

    try:
        endpoint = f"{BASE_URL}/odds?sport=nfl&market=player_props"
        params = {"books": books, "date": date}
        headers = {"Authorization": f"Bearer {SGO_API_KEY}"}
        resp = requests.get(endpoint, headers=headers, params=params)

        if resp.status_code != 200:
            return {"error": f"SGO API error: {resp.status_code}", "detail": resp.text}

        data = resp.json()
        # Simplify output for now
        return {"count": len(data), "sample": data[:3]}  # just return 3 examples for test
    except Exception as e:
        return {"error": str(e)}
