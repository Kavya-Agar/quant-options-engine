# Quant Options Engine — Beginner's Guide

A plain-English walkthrough of what this project does and how to use it.

---

## What is this?

A tool that prices stock options using the **Black-Scholes model** and shows you the "Greeks" — numbers that tell you how sensitive an option's price is to market changes. It pulls live data from Yahoo Finance and has a React dashboard you can interact with in your browser.

---

## Key concepts (no finance background required)

**Option** — a contract giving you the right (not obligation) to buy (`call`) or sell (`put`) a stock at a fixed price (`strike`) before a certain date (`expiry`).

**Black-Scholes** — a math formula from 1973 that estimates what an option *should* be worth, given: current stock price, strike, time left, interest rate, and volatility.

**Implied Volatility (IV)** — the market's *current expectation* of how much a stock will move. Black-Scholes can be run in reverse: given the market price, solve for what volatility the market is "implying."

**The Greeks** — how the option price changes when one input moves by a small amount:

| Greek | Answers |
|-------|---------|
| Delta | If stock moves $1, option moves how much? |
| Gamma | How fast is Delta itself changing? |
| Vega  | If volatility rises 1%, option changes how much? |
| Theta | How much value does the option lose per day? |
| Rho   | If interest rates rise 1%, option changes how much? |

---

## Project structure

```
quant-options-engine/
├── pricing/            # Pure math — no web, no API
│   ├── black_scholes.py   # BS formula + all 5 Greeks
│   ├── iv_solver.py       # Implied vol via Brent's method
│   ├── monte_carlo.py     # Monte Carlo path simulator
│   └── market_data.py     # yfinance + FRED rate fetcher
├── api/                # FastAPI backend (REST endpoints)
│   ├── main.py
│   └── routes/
│       ├── price.py    # /api/price, /api/compute
│       └── chain.py    # /api/chain, /api/expiries
├── dashboard/          # React frontend
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── GreeksPanel.jsx   # Tab 1: slider explorer
│           └── ChainView.jsx     # Tab 2: live options chain
└── tests/              # pytest unit tests
```

---

## Setup

**Requirements:** Python 3.10+, Node.js 18+

```bash
# 1. Clone and enter the project
cd quant-options-engine

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Mac/Linux
# .venv\Scripts\activate        # Windows

# 3. Install everything
make install
# (equivalent to: pip install -r requirements.txt && cd dashboard && npm install)
```

---

## Running the app

```bash
make dev
```

This starts both servers simultaneously:
- **API** → `http://localhost:8000`
- **Dashboard** → `http://localhost:5173`

Open `http://localhost:5173` in your browser.

---

## Using the dashboard

### Tab 1 — Greeks Explorer

Adjust sliders for spot price, strike, time to expiry, volatility, and interest rate. The Delta/Gamma/Vega/Theta/Rho values update instantly (no network call — pure math in the browser via `/api/compute`).

Good for answering questions like: *"What happens to my call's Delta as the stock approaches the strike?"*

### Tab 2 — Live Chain

Enter a real ticker (e.g. `SPY`, `AAPL`) and pick an expiry date. The table shows every contract in the chain with:
- **Market price** — what it's trading at right now
- **BS price** — what Black-Scholes says it should be worth
- **Mispricing** — the difference (positive = BS says it's overpriced vs. market)
- **IV** — the implied volatility solved for that contract

---

## API endpoints

The interactive docs live at `http://localhost:8000/docs` while the server is running.

### `POST /api/price`
Live price + Greeks for a real ticker.

```json
{
  "ticker": "SPY",
  "strike": 545.0,
  "expiry": "2025-09-19",
  "option_type": "call",
  "sigma": 0.18
}
```
Omit `sigma` to auto-compute 30-day historical volatility from yfinance.

### `GET /api/compute`
Instant Greeks from raw numbers — no market data fetched.

```
GET /api/compute?S=545&K=545&T=0.25&r=0.05&sigma=0.18&option_type=call
```

### `GET /api/expiries?ticker=SPY`
Returns the list of available expiry dates for a ticker.

### `GET /api/chain?ticker=SPY&expiry=2025-09-19`
Full options chain (calls + puts) with IV and BS mispricing per contract.

---

## Running the tests

```bash
pytest
```

Tests cover Black-Scholes pricing accuracy, Greeks values, IV solver convergence, and Monte Carlo convergence to BS prices.

---

## How the math works (high level)

1. `black_scholes.py` computes `d1` and `d2` — two intermediate numbers that capture how far in/out-of-the-money the option is, adjusted for time and vol. Greeks are then closed-form derivatives of the price formula.

2. `iv_solver.py` uses **Brent's method** (`scipy.optimize.brentq`) to invert Black-Scholes: given a market price, it finds the sigma that makes BS(sigma) = market price. Brent's method is preferred over Newton's method here because option prices can be flat near boundaries, making derivatives unreliable.

3. `market_data.py` fetches the live spot price and options chain from **yfinance**, and pulls the current 3-month T-bill rate from **FRED** as the risk-free rate (no API key needed).

4. `monte_carlo.py` simulates thousands of random stock price paths (geometric Brownian motion) and prices the option as the average discounted payoff. For European options, this converges to the Black-Scholes price — useful as a sanity check.
