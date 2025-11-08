# 🏈 ParlayCooker – NFL Player Prop Analytics & EV Optimizer

**ParlayCooker** is an intelligent NFL player prop betting assistant that constructs high–expected-value (EV) 3–4 leg parlays using live DraftKings data and probabilistic modeling.  
It automates prop selection, calculates true probabilities, adjusts for correlation, and maximizes EV while maintaining a realistic hit rate threshold.

---

## 🚀 Features

- **Live Data Integration**
  - Pulls real-time player props, odds, and markets directly from the ParlayCooker API.
  - Supports:
    - Passing Yards / TDs  
    - Receiving Yards / Receptions  
    - Rushing Yards  
    - Anytime TDs

- **EV-Based Optimization**
  - Calculates true probabilities from player projections.
  - Compares against market-implied odds to find positive-EV legs.

- **Correlation-Aware Parlay Modeling**
  - QB ↔ WR correlation: +0.4–0.7  
  - RB ↔ own QB correlation: −0.2 to −0.4  
  - Cross-game correlation ≈ 0  

- **Flexible Parlay Building**
  - 3–4 leg parlays only (no spreads or totals).  
  - Alt lines supported when payout improves without dropping EV.  
  - Rejects legs worse than −180 unless EV > 0.

- **Responsible Gaming Logic**
  - Enforces risk caps and safe play reminders.

---

## 🧮 Methodology

| Step | Process | Formula / Model |
|------|----------|----------------|
| 1 | Fetch props and odds | `listNflEvents`, `getNflProps` |
| 2 | Estimate true probabilities | From player projections + variance |
| 3 | Compute market-implied probs | (100 / (O + 100)) or (O / (O + 100)) |
| 4 | Calculate edge | Edge = p_true − p_imp |
| 5 | Combine legs | Correlation-adjusted Gaussian approximation |
| 6 | Evaluate EV | EV = (p_joint × payout) − (1 − p_joint) × 100 |

---

## 💡 Example Output

```
Baker Mayfield – Over 1.5 Passing TDs (+120)
Mike Evans – Over 68.5 Receiving Yards (−110)
Rhamondre Stevenson – Over 55.5 Rushing Yards (−115)
Total Odds: +550
EV per $100: +$18
Joint Hit Probability: 0.20
Correlation Risk: Low
```

🧾 **Bet responsibly; never wager more than you can afford to lose.**

---

## 🧰 Tech Stack

- **Model:** GPT-5 (customized assistant)
- **API:** [ParlayCooker OnRender API](https://parlay-cooker.onrender.com)
- **Markets:**  
  `player_pass_tds`, `player_pass_yds`, `player_receptions`, `player_reception_yds`, `player_rush_yds`, `player_anytime_td`
- **Language:** Python
- **Math Tools:** NumPy, Pandas, Normal & Poisson approximations
- **Modes:**
  - **Quick Mode:** Concise, high-speed parlay generation
  - **Ticket-Only Mode:** Outputs bet slip summary only

---

## 🧪 Example Workflow

### 1️⃣ List NFL Games
```python
listNflEvents(date="2025-11-08")
```

### 2️⃣ Fetch Player Props
```python
getNflProps(
  event_id="39e7c1f6e36d5bc4d2613ebf7bb83c10",
  bookmakers="draftkings",
  markets="player_pass_tds,player_rush_yds,player_reception_yds"
)
```

### 3️⃣ Generate an Optimized Parlay
```
Quick Mode: build a 3-leg parlay from the Patriots @ Buccaneers game
```

---

## ⚙️ Defaults & Constraints

| Setting | Default | Description |
|----------|----------|-------------|
| Legs | 3–4 | No more than 4 legs |
| Min per-leg edge | ≥ 3% | p_true − p_imp |
| Max juice | −180 | Unless EV > 0 |
| Min joint hit rate | 0.18 (3-leg) / 0.12 (4-leg) | Ensures realistic hit probability |
| Weather adjustments | Wind > 15 mph lowers pass EV | |
| Injury rule | Exclude “Out”, fade “Q” | |

---

## ⚙️ Installation (for developers)

```bash
git clone https://github.com/yourusername/parlaycooker.git
cd parlaycooker
# optional: create a virtual environment
pip install -r requirements.txt
```

Then integrate with your OpenAI + ParlayCooker API keys.

---

## 📄 License

**MIT License © 2025 ParlayCooker Project**

Use responsibly. This project is for **informational and entertainment purposes only** — not financial advice.

---

### 🙏 Acknowledgements

Special thanks to the OpenAI GPT-5 model and the ParlayCooker API team for powering real-time NFL prop data and analysis.

---

> 🧾 *Bet responsibly; never wager more than you can afford to lose.*
