from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time

# --------- MODE: start with STUB=True; later set to False to go live ---------
STUB = False

class Projection(BaseModel):
    mean: float
    stdev: Optional[float] = None
    dist: Optional[str] = None

class Prop(BaseModel):
    player: str
    team: Optional[str] = None
    opponent: Optional[str] = None
    game: Optional[str] = None
    market: str
    line: float
    is_alt: bool
    odds: int
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

app = FastAPI(title="ParlayLab Odds Service", version="1.0")

@app.get("/health")
def health():
    return {"ok": True, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ")}

def stub_payload(date: str, books: List[str]) -> Slate:
    props = [
        Prop(player="Josh Allen", market="player_pass_tds", line=1.5, is_alt=False, odds=-135, book="draftkings",
             game="NYJ@BUF", projection=Projection(mean=2.05, stdev=0.95, dist="poisson")),
        Prop(player="Travis Kelce", market="player_receptions", line=6.5, is_alt=False, odds=-115, book="draftkings",
             game="KC@PIT", projection=Projection(mean=7.2, stdev=2.0, dist="normal")),
        Prop(player="Joe Mixon", market="player_rushing_yards", line=64.5, is_alt=False, odds=-110, book="draftkings",
             game="CIN@KC", projection=Projection(mean=72, stdev=22, dist="normal")),
    ]
    cors = [
        Correlation(a="qb_pass_yards_over", b="wr_rec_yards_over", rho=0.55),
        Correlation(a="rb_rush_yards_over", b="own_qb_pass_yards_over", rho=-0.25),
    ]
    return Slate(
        slate_date=date,
        props=props,
        correlations=cors,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        provider="stub",
        books_used=books
    )

# Minimal books parser
def parse_books(books_csv: str) -> List[str]:
    return [b.strip() for b in (books_csv or "draftkings,fanduel").split(",") if b.strip()]

@app.get("/nfl/props", response_model=Slate)
def get_props(date: str = Query(...), books: Optional[str] = None, markets: Optional[str] = None):
    books_list = parse_books(books or "draftkings,fanduel")
    if STUB:
        return stub_payload(date, books_list)
    # If STUB=False, we’ll route to the live odds function (added in Step 4)
    raise RuntimeError("Live mode not enabled yet. Set STUB=False and add live code per Step 4.")
