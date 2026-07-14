# Quant Options Engine — Beginner's Guide

A plain-English walkthrough of what this project does and how to use it.

---

## What is this?

A tool that prices stock options using the **Black-Scholes model** and shows you the "Greeks" — numbers that tell you how sensitive an option's price is to market changes. It pulls live data from Yahoo Finance and has a React dashboard you can interact with in your browser.

On top of that math engine there's an **AI strategy planner**: type a plain-English goal like "hedge my 100 shares against a 10% drop" and Claude proposes concrete options strategies, using the pricing engine's own functions (exposed as tools) to compute every number instead of guessing.

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
│   ├── market_data.py     # yfinance + FRED rate fetcher
│   └── models.py          # Data shapes for strategy proposals (used by the AI planner)
├── api/                # FastAPI backend (REST endpoints)
│   ├── main.py
│   ├── mcp_server.py    # Exposes the pricing functions as tools Claude can call
│   └── routes/
│       ├── price.py    # /api/price, /api/compute
│       ├── chain.py    # /api/chain, /api/expiries
│       └── planner.py  # /api/plan — natural language goal → strategy proposals
├── agents/              # The AI planner
│   ├── planner.py       # Claude figures out which strategy to propose
│   ├── verifier.py      # Plain Python double-checks the proposal is actually safe
│   ├── eval_harness.py  # Runs 15 test scenarios and scores how well it worked
│   └── test_scenarios.json
├── dashboard/          # React frontend
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── GreeksPanel.jsx   # Tab 1: slider explorer
│           ├── ChainView.jsx     # Tab 2: live options chain
│           └── PlannerForm.jsx   # Tab 3: type a goal, get a strategy
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

# 4. Only needed for the AI Strategy Planner (Tab 3) — everything else works without this
export ANTHROPIC_API_KEY=sk-ant-...
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

### Tab 3 — Strategy Planner

Type a goal in plain English — "hedge my 100 shares of SPY against a 10% drop," "generate income from my SPY holding," "reduce my cost basis" — and click **Generate Strategies**. Requires `ANTHROPIC_API_KEY` to be set (see Setup above); the other two tabs don't need it.

Each proposal that comes back shows:
- **Strategy name and rationale** — plain-English explanation of the trade
- **Net cost, max gain, max loss** — max gain shows "Unbounded" when the strategy has no cap (e.g. a protective put, since you still own the stock)
- **Net Greeks** — delta/gamma/vega/theta/rho for the whole position, not just one leg
- **Legs table** — exactly what to buy/sell: side, type, strike, expiry
- **A ✓ Verified / ⚠ Needs Review badge** — a separate, non-AI check confirms the proposal actually respects the risk rules below; if it doesn't, the specific violations are listed

Only three strategies are supported by design: **Covered Call** (own the stock, sell a call against it for income), **Protective Put** (own the stock, buy a put as insurance), and **Vertical Spread** (buy one option and sell another at a different strike to lower cost).

---

## How the AI planner works (high level)

The planner doesn't guess numbers — it calls the same pricing functions this project already has, just wrapped so Claude can invoke them as tools:

1. **`api/mcp_server.py`** exposes `get_greeks`, `get_chain_snapshot`, `price_strategy`, `validate_trade`, and `get_implied_vol` as callable tools (using the [MCP](https://modelcontextprotocol.io/) standard).
2. **`agents/planner.py`** gives Claude your goal and those tools. Claude decides which of the 3 strategies fits, picks real strikes from the live chain, and calls `price_strategy` to get the actual net cost, max gain/loss, breakeven, and Greeks — it's instructed to copy those numbers through as-is rather than making its own estimate.
3. **`agents/verifier.py`** is *not* an AI — it's plain Python that checks the proposal against fixed rules (max loss under $5,000, at least 7 days to expiry, no uncovered short options, options liquid enough to actually trade). This is what earns the "Verified" badge.
4. **`agents/eval_harness.py`** runs the whole pipeline against 15 pre-written test scenarios and reports how often it got the right shape of strategy and passed verification — a repeatable way to check the AI is behaving, not just a one-off demo.

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

### `POST /api/plan`
Natural language goal → strategy proposals. Requires `ANTHROPIC_API_KEY` to be set.

```json
{ "goal": "Hedge my 100 shares of SPY against a 10% drop" }
```
Returns 1–3 proposals, each with legs, net cost, max gain/loss, breakeven, net Greeks, a plain-English rationale, and a `verified` flag (plus any `violations` if the deterministic checker found a problem).

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
