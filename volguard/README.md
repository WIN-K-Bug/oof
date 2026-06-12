# VolGuard — NIFTY Options Signal System

A real-time NIFTY 50 options trading signal system powered by a 18-gate
Directional Conviction Engine (DCE). Connects live to Angel One SmartAPI,
evaluates market conditions every second, and surfaces high-confidence
trade signals with entry price, stop-loss, and target.

---

## Architecture

```
Angel One SmartAPI
      │
      ├── REST (auth + instrument download)
      └── WebSocket (live tick stream)
            │
            ▼
    MarketStateManager (thread-safe buffer)
            │
            ▼
    17-Stage DCE (evaluates every 1s)
            │
            ▼
    Signal Engine (strike selection + risk levels)
            │
            ▼
    FastAPI Server (port 8000)
            │
            ▼
    React Dashboard (port 3000)
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Angel One trading account with SmartAPI access
- TOTP authenticator app (for 2FA secret)

---

## Setup

### 1. Clone the repository

```bash
git clone https://gitlab.com/kevin10275108-group/wink-project.git
cd wink-project/volguard
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your Angel One credentials:

```env
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id_here
ANGEL_PASSWORD=your_password_here
ANGEL_TOTP_SECRET=your_totp_secret_here
DAILY_LOSS_LIMIT=5000
SIGNAL_COOLDOWN_MINUTES=15
MIN_CONFIDENCE_SCORE=75
```

To get your `ANGEL_TOTP_SECRET`:
1. Log into Angel One web portal
2. Go to Profile → Security → Enable TOTP
3. Copy the secret key shown during QR setup

### 3. Run health check

```bash
cd backend
python healthcheck.py
```

All checks must pass before starting the system.

### 4. Start the system

**Windows:**
```bat
start.bat
```

**Mac/Linux:**
```bash
chmod +x start.sh && ./start.sh
```

**Manual:**
```bash
# Terminal 1
cd backend && python main.py

# Terminal 2
cd frontend && npm start
```

### 5. Open the dashboard

```
http://localhost:3000
```

API documentation available at `http://localhost:8000/docs`

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | System health check |
| `/api/dashboard` | GET | Full dashboard data |
| `/api/gates` | GET | All 18 DCE gate results |
| `/api/signal` | GET | Latest trade signal |
| `/api/signals/history` | GET | Recent signal history |
| `/api/status` | GET | System status + metrics |
| `/api/volguard/toggle` | POST | Toggle VolGuard block |
| `/api/signals/{id}/outcome` | POST | Update signal outcome |

---

## DCE Gates Reference

| Gate | Name | Threshold |
|---|---|---|
| 0 | Daily Loss Limit | P&L > -₹5000 |
| 1 | Market Hours | 09:20–15:00 IST |
| 2 | Tick Health | Last tick < 10s ago |
| 3 | Spot Price Valid | ₹15,000–₹35,000 |
| 4 | VWAP Calculated | VWAP > 0 |
| 5 | Spot vs VWAP | Deviation ≤ 2% |
| 6 | Signal Cooldown | 15 min between signals |
| 7 | VolGuard Status | Not manually blocked |
| 8 | Min Tick Count | ≥ 100 ticks received |
| 9 | Options Data | ≥ 10 live contracts |
| 10 | Price Momentum | ≥ 0.1% from VWAP |
| 11 | Gamma Squeeze Score | GSS ≥ 0.60 |
| 12 | Vanna Trigger | \|Vanna\| ≥ 5000 |
| 13 | IV Rank Skew | \|IV Skew\| > 3.0 |
| 14 | Spread Quality | ≥ 60% liquid contracts |
| 15 | Volume | Total volume ≥ 10,000 |
| 16 | OI Concentration | ≥ 30% OI near ATM |
| 17 | Directional Alignment | 2/3 indicators agree |

Signals only fire when confidence score ≥ 75% (≥ 14/18 gates passing).

---

## Signal Output Format

```json
{
  "signal": "BUY_CE",
  "symbol": "NIFTY27JUN24CE23550",
  "strike_price": 23550,
  "expiry": "27JUN2024",
  "entry_price": 85.50,
  "stop_loss": 55.57,
  "target": 141.07,
  "risk_reward": 1.86,
  "confidence_score": 83,
  "gates_passed": 15
}
```

---

## Backtesting

```bash
cd backend
python backtest.py data/sample_ticks.csv 30
```

Provide your own historical tick CSV with columns:
`timestamp, token, symbol, ltp, oi, volume, iv, bid, ask`

Results saved to `backend/db/backtest_results.json`

---

## Risk Disclaimer

This system is a **decision-support tool**, not an auto-executor.
All signals require manual review before placing trades.
Options trading involves significant risk of loss.
Past signal performance does not guarantee future results.
Never risk more than you can afford to lose.

---

## Project Structure

```
volguard/
├── backend/
│   ├── data/
│   │   ├── instrument_mapper.py   # Contract token filter
│   │   └── websocket_handler.py   # Live tick ingestion
│   ├── db/
│   │   └── volguard.db            # SQLite signal log
│   ├── logs/
│   ├── backtest.py                # Historical replay engine
│   ├── healthcheck.py             # Pre-launch validation
│   └── main.py                    # FastAPI server + DCE
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Dashboard.tsx
│       │   ├── GateStatus.tsx
│       │   ├── SignalCard.tsx
│       │   ├── FactorBreakdown.tsx
│       │   └── SignalHistory.tsx
│       └── types/
│           └── index.ts
├── .env.example
├── Dockerfile
├── requirements.txt
├── start.bat
└── start.sh
```
