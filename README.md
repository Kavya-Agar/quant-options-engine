# Quant Options Engine

A from-scratch quantitative options pricing engine built in Python, implementing the core models used in derivatives trading. Built as a learning project to deeply understand options theory — every formula is derived and explained, not just called from a library.

## What's Implemented

| Phase | Topic | Status |
|-------|-------|--------|
| 1 | Black-Scholes pricer + all five Greeks | ✅ |
| 2 | Monte Carlo GBM simulator + antithetic variance reduction | ✅ |
| 3 | Market data (yfinance) + Implied Volatility solver (Brent's method) | ✅ |
| 4 | FastAPI REST backend | ✅ |
| 5 | React dashboard (Greeks heatmap, IV surface, mispricing chart) | ✅ |

## Project Structure

```
quant-options-engine/
├── pricing/                   # Core pricing library
│   ├── black_scholes.py       # Closed-form BS price + Greeks (Phase 1)
│   ├── monte_carlo.py         # GBM simulation pricer (Phase 2)
│   ├── market_data.py         # Spot price, risk-free rate, options chain (Phase 3)
│   └── iv_solver.py           # Implied volatility solver — Brent's method (Phase 3)
├── api/                       # FastAPI backend (Phase 4)
│   ├── main.py                # App entry point + CORS
│   └── routes/
│       ├── price.py           # POST /api/price · GET /api/compute
│       └── chain.py           # GET /api/chain · GET /api/expiries
├── dashboard/                 # React frontend (Phase 5)
│   ├── src/
│   │   ├── App.jsx            # Tab layout
│   │   ├── bs.js              # Client-side BS for real-time sliders
│   │   ├── api.js             # Fetch wrappers
│   │   └── components/
│   │       ├── GreeksPanel.jsx    # Interactive Greeks sliders
│   │       ├── ChainView.jsx      # Live chain table + controls
│   │       └── MispricingChart.jsx # Recharts scatter plot
│   └── vite.config.js         # Dev server proxies /api → FastAPI
└── tests/                     # Test suite
    ├── test_black_scholes.py  # BS tests with reference values + identities
    ├── test_monte_carlo.py    # MC convergence + variance reduction tests
    └── test_iv_solver.py      # IV round-trip tests + edge cases
```

## Quickstart

**Install everything**

```bash
make install   # pip install -r requirements.txt && cd dashboard && npm install
```

**Run backend + frontend together**

```bash
make dev   # starts FastAPI on :8000 and Vite on :5173 concurrently
```

Or run each separately:

```bash
make api        # uvicorn api.main:app --reload --port 8000
make dashboard  # cd dashboard && npm run dev
```

- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:5173

**Tests**

```bash
pytest tests/ -v
```

**Demo scripts**

```bash
python -m pricing.black_scholes   # BS reference output
python -m pricing.monte_carlo     # MC convergence table
```

## Phase 1 — Black-Scholes

The closed-form BS model prices European calls and puts and computes all five Greeks analytically.

```python
from pricing import bs_price, greeks

# Price a call option
price = bs_price(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
# → 10.4506

# Get all Greeks at once
g = greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
# → {"price": 10.45, "delta": 0.637, "gamma": 0.019, "vega": 37.52, ...}
```

**Parameters:**
- `S` — spot price
- `K` — strike price
- `T` — time to expiry in years (e.g. 90 days → `T = 90/365`)
- `r` — risk-free rate, continuously compounded
- `sigma` — annualised volatility

**The Greeks:**

| Greek | Measures | Formula |
|-------|----------|---------|
| Delta | Price sensitivity to spot | `N(d1)` for calls |
| Gamma | Delta sensitivity to spot | `N'(d1) / (S·σ·√T)` |
| Vega  | Price sensitivity to vol  | `S·N'(d1)·√T` |
| Theta | Daily time decay          | See formula in code |
| Rho   | Rate sensitivity (per 1%) | `K·T·e^(-rT)·N(d2) / 100` |

## Phase 2 — Monte Carlo

The Monte Carlo pricer simulates thousands of GBM stock price paths and estimates the option value as the average discounted payoff.

```python
from pricing import mc_price, mc_convergence

# Price with 50,000 simulations
result = mc_price(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                  option_type="call", n_sims=50_000, seed=42)
# → {"price": 10.43, "std_error": 0.021, "conf_low": 10.39, "conf_high": 10.47}

# Track convergence to the BS analytical price
rows = mc_convergence(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
```

**Key concepts implemented:**
- **GBM terminal price**: `S_T = S · exp((r - ½σ²)T + σ√T · Z)`, `Z ~ N(0,1)`
- **Antithetic variates**: pairs each draw `Z` with `−Z` to halve variance at no cost
- **95% confidence interval**: quantifies the uncertainty of each MC estimate
- **Convergence tracking**: error shrinks at rate `O(1/√n)` — doubling precision costs 4× the compute

**Why MC when BS is exact?**
BS only works for European options under strict assumptions. Monte Carlo handles any payoff (Asian, barrier, etc.) and can incorporate stochastic volatility, jumps, and dividends — it's the industry tool for exotic derivatives.

## Phase 3 — Market Data + Implied Volatility

Phase 3 connects the pricing engine to real market data and adds an implied volatility solver.

**Market data** (`pricing/market_data.py`):

```python
from pricing.market_data import get_risk_free_rate, get_spot_price, get_options_chain, expiry_to_years

# 3-month T-bill rate from FRED (no API key required)
r = get_risk_free_rate()   # e.g. 0.0525

# Current spot price via yfinance
S = get_spot_price("SPY")  # e.g. 542.30

# Full options chain — defaults to nearest expiry
calls, puts, expiries, expiry = get_options_chain("SPY")
T = expiry_to_years(expiry)  # e.g. 0.038 (14 days)
```

**IV solver** (`pricing/iv_solver.py`):

```python
from pricing.iv_solver import implied_vol, full_chain_with_iv

# Solve for IV of a single contract using Brent's method
iv = implied_vol(market_price=5.40, S=542, K=545, T=0.038, r=0.0525, option_type="call")
# → 0.187  (18.7% annualised vol)

# Enrich an entire chain with IV — uses bid-ask midpoint, falls back to lastPrice
calls_with_iv, puts_with_iv = full_chain_with_iv(calls, puts, S=S, T=T, r=r)
# Both DataFrames now have an 'iv' column alongside yfinance's own estimate
```

`implied_vol` returns `None` (not an exception) when no valid solution exists — expired options, prices at or below intrinsic value, or contracts too far outside any realistic vol range.

## Phase 4 — FastAPI Backend

Four REST endpoints served by FastAPI with auto-generated OpenAPI docs.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/price` | POST | Live spot + risk-free rate fetch → BS price + all Greeks |
| `/api/compute` | GET | Raw BS computation from query params — no market data |
| `/api/chain` | GET | Full options chain with IV and mispricing |
| `/api/expiries` | GET | Available expiry dates for a ticker |

```bash
# Start the server
uvicorn api.main:app --reload --port 8000

# Interactive docs
open http://localhost:8000/docs
```

```bash
# Theoretical price + Greeks for a live ticker
curl -X POST http://localhost:8000/api/price \
  -H "Content-Type: application/json" \
  -d '{"ticker": "SPY", "strike": 545, "expiry": "2025-09-19", "option_type": "call"}'

# Raw computation (no market data fetch, instant)
curl "http://localhost:8000/api/compute?S=100&K=100&T=1.0&r=0.05&sigma=0.20&option_type=call"

# Full chain with IV
curl "http://localhost:8000/api/chain?ticker=SPY"
```

If `sigma` is omitted from `/api/price`, 30-day annualised historical volatility is computed from yfinance closes.

## Phase 5 — React Dashboard

A dark terminal-aesthetic React dashboard (Vite + Recharts) with two views:

**Greeks Explorer** — real-time sliders for S, K, T, r, σ and option type. All six Greeks update instantly client-side (no network call) using a JS implementation of the BS formula.

- Price, Delta, Gamma, Vega, Theta, Rho displayed as cards
- Breakeven, intrinsic value, and time value annotations
- ITM/ATM/OTM moneyness indicator

**Live Chain** — fetches a real options chain from the API and displays:

- Scatter plot: market price vs BS price per contract (calls green, puts red). The diagonal is fair value; points above it are BS-overpriced.
- Table: strike, type, market price, BS price, mispricing, IV, bid/ask, volume, OI
- Filter by calls / puts / all
- Stats bar: spot, T, risk-free rate, contract counts, average IV

```bash
cd dashboard
npm install
npm run dev   # → http://localhost:5173
```

## Running Tests

```bash
pytest tests/ -v
```

The Black-Scholes tests verify exact reference values and mathematical identities (put-call parity, delta relationship). The Monte Carlo tests verify convergence and statistical properties rather than exact values, since MC is a randomised algorithm.

## Key Concepts (Interview Reference)

**What do d1 and d2 represent?**
`N(d2)` is the risk-neutral probability of expiring in-the-money. `N(d1)` is the call Delta — the number of shares needed to replicate the option.

**Why does Monte Carlo converge to Black-Scholes for European options?**
Both price the same expected payoff under the risk-neutral measure. BS computes the expectation analytically; MC estimates it by averaging simulated outcomes. By the law of large numbers they must agree.

**What is implied volatility?**
The market-observed option price contains an implicit forward-looking volatility estimate. IV is the σ that makes `BS(σ) = market price`. It's the market's best guess of future realized vol.

**Why Brent's method for IV?**
Brent's method combines bisection (guaranteed convergence) with secant/quadratic interpolation (fast convergence). Pure bisection is slow; Newton's method can diverge near Vega ≈ 0. Brent's method is robust and fast.

**What is the volatility smile/skew?**
If BS were perfectly correct, IV would be constant across strikes. In practice, lower strikes have higher IV (skew) because investors buy downside protection. This reveals BS's assumptions are violated in real markets.

## Phase 6 — MCP Server + AI Strategy Planner

Building on the quantitative engine, this phase adds a conversational AI layer:

### MCP Server

An [Model Context Protocol](https://modelcontextprotocol.io/) server exposes the pricing functions as Claude tools:

- **`get_greeks`** — Black-Scholes Greeks for a single option
- **`get_implied_vol`** — Solve for IV from market price
- **`get_chain_snapshot`** — Full options chain (cached 10 min to avoid yfinance rate limits)
- **`price_strategy`** — Sum Greeks/P&L across multi-leg positions
- **`validate_trade`** — Check strategy against risk constraints (max loss, min DTE, OI, no naked shorts)

**Start the MCP server:**

```bash
python api/mcp_server.py
```

Then connect it to Claude Desktop for live testing.

### Strategy Planner Agent

Claude Opus orchestrates the tools to convert natural language goals into concrete multi-leg strategies:

**Supported strategies:**
- Covered Call: Long stock + short call (income)
- Protective Put: Long stock + long put (downside hedge)
- Vertical Spread: Buy/sell call or put spreads (defined risk)

**Example:**

```python
from agents import run_planner_agent

goal = "Hedge my 100 shares of SPY against a 10% drop"
result = run_planner_agent(goal)

# Returns:
# {
#   "proposals": [
#     {
#       "strategy_name": "Protective Put",
#       "legs": [...],
#       "net_cost": 285.00,
#       "max_loss": 1285.00,
#       "net_greeks": {...},
#       "rationale": "..."
#     }
#   ]
# }
```

**How it works:**

1. Claude parses your goal (e.g., hedge, income, reduce cost)
2. Calls `get_chain_snapshot("SPY")` to see available strikes
3. Proposes 1–3 strategies with specific strikes and expiries
4. Calls `price_strategy()` to compute real Greeks (no hallucination)
5. Returns ranked proposals with full P&L and risk breakdown

**Key safeguards:**
- All Greeks come from actual tool calls (verified against BS formula)
- Only liquid strikes (OI > 100)
- No naked shorts
- All strikes exist in the live chain

### Verifier + Eval Harness

A deterministic verifier validates proposals against hard constraints:

- Max loss: $5,000 USD
- Min days to expiration: 7 days
- No naked short legs
- Min open interest: 100 contracts

An eval harness runs the planner + verifier on 15 hand-written test scenarios and measures:

- **Pass rate:** % of proposals that pass all criteria
- **Verifier catch rate:** % of proposals with violations caught and rejected

**Run evaluation:**

```bash
python agents/eval_harness.py
```

Outputs: `agents/eval_results.json` with per-scenario results and summary metrics.

**Why this matters for interviews:**

This is how you demonstrate defensible AI: not just a fancy demo, but measurable validation. "The verifier caught and revised 2 out of 15 test-case proposals that violated my max-loss constraint" is a real, specific claim you can defend.

### Project Structure (with AI components)

```
quant-options-engine/
├── pricing/
│   ├── black_scholes.py
│   ├── monte_carlo.py
│   ├── market_data.py
│   ├── iv_solver.py
│   └── models.py              # Pydantic models for proposals (NEW)
├── api/
│   ├── main.py
│   ├── mcp_server.py          # MCP server with 5 tools (NEW)
│   └── routes/
│       ├── price.py
│       └── chain.py
├── agents/                    # AI agents (NEW)
│   ├── __init__.py
│   ├── planner.py             # Claude-powered strategy planner
│   ├── verifier.py            # Deterministic risk checker
│   ├── eval_harness.py        # Evaluation runner
│   └── test_scenarios.json    # 15 test cases
├── dashboard/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── bs.js
│   │   ├── api.js
│   │   └── components/
│   │       ├── GreeksPanel.jsx
│   │       ├── ChainView.jsx
│   │       └── MispricingChart.jsx
│   └── vite.config.js
└── tests/
    ├── test_black_scholes.py
    ├── test_monte_carlo.py
    └── test_iv_solver.py
```
