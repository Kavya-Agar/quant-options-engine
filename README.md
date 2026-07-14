# Quant Options Engine

A from-scratch quantitative options pricing engine built in Python, implementing the core models used in derivatives trading. Built as a learning project to deeply understand options theory — every formula is derived and explained, not just called from a library.

It has two layers: a quantitative core (Black-Scholes, Monte Carlo, implied volatility, all against live market data) and an AI layer on top (an MCP server, a Claude-powered strategy planner, and a deterministic verifier + eval harness) that turns the pricing engine into something you can ask for a strategy in plain English and get back a proposal with real, tool-computed Greeks and P&L.

## What's Implemented

| Phase | Topic | Status |
|-------|-------|--------|
| 1 | Black-Scholes pricer + all five Greeks | ✅ |
| 2 | Monte Carlo GBM simulator + antithetic variance reduction | ✅ |
| 3 | Market data (yfinance) + Implied Volatility solver (Brent's method) | ✅ |
| 4 | FastAPI REST backend | ✅ |
| 5 | React dashboard (Greeks heatmap, IV surface, mispricing chart) | ✅ |
| 6 | MCP server + Claude strategy planner + deterministic verifier/eval harness | ✅ |

## Project Structure

```
quant-options-engine/
├── pricing/                   # Core pricing library
│   ├── black_scholes.py       # Closed-form BS price + Greeks (Phase 1)
│   ├── monte_carlo.py         # GBM simulation pricer (Phase 2)
│   ├── market_data.py         # Spot price, risk-free rate, options chain (Phase 3)
│   ├── iv_solver.py           # Implied volatility solver — Brent's method (Phase 3)
│   └── models.py              # Pydantic schemas: Leg, StrategyProposal, RiskConstraints (Phase 6)
├── api/                       # FastAPI backend (Phase 4)
│   ├── main.py                # App entry point + CORS
│   ├── mcp_server.py          # MCP server: 5 tools + exact payoff-at-expiry analysis (Phase 6)
│   └── routes/
│       ├── price.py           # POST /api/price · GET /api/compute
│       ├── chain.py           # GET /api/chain · GET /api/expiries
│       └── planner.py         # POST /api/plan — natural language → strategy proposals (Phase 6)
├── agents/                    # AI strategy planner (Phase 6)
│   ├── planner.py             # Claude tool-use loop → strategy proposals
│   ├── verifier.py            # Deterministic (non-LLM) risk-constraint checker
│   ├── eval_harness.py        # Runs planner+verifier over test_scenarios.json
│   └── test_scenarios.json    # 15 hand-written test scenarios
├── dashboard/                 # React frontend (Phase 5) + Strategy Planner tab (Phase 6)
│   ├── src/
│   │   ├── App.jsx            # Tab layout — Greeks Explorer, Live Chain, Strategy Planner
│   │   ├── bs.js               # Client-side BS for real-time sliders
│   │   ├── api.js              # Fetch wrappers
│   │   └── components/
│   │       ├── GreeksPanel.jsx      # Interactive Greeks sliders
│   │       ├── ChainView.jsx        # Live chain table + controls
│   │       ├── MispricingChart.jsx  # Recharts scatter plot
│   │       └── PlannerForm.jsx      # Strategy Planner tab (+ PlannerForm.css)
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

**AI planner (Phase 6) — needs one extra thing**

The MCP server, dashboard, and REST API all run with no additional setup. The strategy planner (`agents/planner.py`, the `/api/plan` endpoint, the "Strategy Planner" dashboard tab, and `agents/eval_harness.py`) calls the real Anthropic API, so it additionally needs:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Everything else — pricing, Greeks, chain data, the two original dashboard tabs — works without this key.

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

Building on the quantitative engine, this phase adds a conversational AI layer.

### MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server (`api/mcp_server.py`, built on the real `mcp.server.Server` + `stdio_server` API) exposes the pricing functions as Claude tools:

- **`get_greeks`** — Black-Scholes Greeks for a single option
- **`get_implied_vol`** — Solve for IV from market price
- **`get_chain_snapshot`** — Full options chain (cached 10 min per ticker+expiry, to avoid yfinance rate limits)
- **`price_strategy`** — Net cost and exact max gain/loss/breakeven for a multi-leg strategy, computed via piecewise-linear payoff-at-expiry analysis (not a heuristic), plus net Greeks. Handles stock legs directly (delta = 1/share) alongside option legs.
- **`validate_trade`** — Check a strategy against risk constraints (max loss, min DTE, min OI, no naked shorts)

**Start the MCP server:**

```bash
python api/mcp_server.py
```

It speaks MCP over stdio — connect it to Claude Desktop (or the MCP Inspector) for live testing.

### Strategy Planner Agent

Claude (`agents/planner.py`, using the raw Anthropic SDK's tool-use loop — no LangChain) orchestrates the MCP tools to convert natural language goals into concrete multi-leg strategies.

**Supported strategies:**
- Covered Call: Long stock + short call (income, capped upside)
- Protective Put: Long stock + long put (downside hedge, unbounded upside)
- Vertical Spread: Buy + sell same-type options at different strikes (defined risk both ways)

**Example:**

```python
from agents import run_planner_agent

goal = "Hedge my 100 shares of SPY against a 10% drop"
result = run_planner_agent(goal)

# Returns:
# {
#   "success": True,
#   "proposals": [
#     {
#       "strategy_name": "Protective Put",
#       "legs": [
#         {"side": "long", "strike": 500, "expiry": "2026-09-18", "option_type": "stock", "quantity": 100},
#         {"side": "long", "strike": 485, "expiry": "2026-09-18", "option_type": "put", "quantity": 1}
#       ],
#       "net_cost": 50285.00,   # includes the 100-share stock purchase, not just the put premium
#       "max_loss": 1785.00,
#       "max_gain": null,       # null = unbounded upside (the long stock leg has no cap)
#       "breakeven": [502.85],
#       "net_greeks": {"delta": 84.2, "gamma": 0.6, "vega": 45.1, "theta": -12.3, "rho": 30.5},
#       "rationale": "..."
#     }
#   ]
# }
```

Every numeric field (`net_cost`, `max_gain`, `max_loss`, `breakeven`, `net_greeks`) is copied verbatim from `price_strategy()`'s tool output — the planner's system prompt explicitly forbids it from computing or estimating these itself. `max_gain` is `null`/`None` whenever upside is genuinely unbounded (e.g. any strategy with a long stock leg and no capping short call) rather than a made-up number.

**How it works:**

1. Claude parses your goal (e.g., hedge, income, reduce cost)
2. Calls `get_chain_snapshot("SPY")` to see available strikes
3. Proposes 1–3 strategies with specific strikes and expiries
4. Calls `price_strategy()` and copies its numbers through as-is (no hallucination)
5. Returns ranked proposals with full P&L and risk breakdown

**Key safeguards:**
- All Greeks and P&L come from actual tool calls, never invented
- Only liquid strikes (OI > 100)
- No naked shorts (a short is "covered" if there's a same-expiry long option of the same type, or a long stock leg for a covered call)
- All strikes exist in the live chain

### REST API + Dashboard Tab

`POST /api/plan` (`api/routes/planner.py`) wraps the planner + verifier for the frontend:

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{"goal": "Generate income from my SPY holding"}'
```

The dashboard's third tab, **Strategy Planner** (`dashboard/src/components/PlannerForm.jsx`), is a form that posts to this endpoint and renders each proposal: rationale, net cost/max gain/max loss (showing "Unbounded" when `max_gain` is null), net Greeks, the leg table, and a ✓ Verified / ⚠ Needs Review badge with any constraint violations listed.

### Verifier + Eval Harness

A deterministic verifier (`agents/verifier.py` — plain Python, no LLM) validates proposals against hard constraints:

- Max loss: $5,000 USD
- Min days to expiration: 7 days
- No naked short legs
- Min open interest: 100 contracts

An eval harness (`agents/eval_harness.py`) runs the planner + verifier on 15 hand-written test scenarios (`agents/test_scenarios.json`) and measures:

- **Pass rate:** % of proposals that pass all scenario-specific criteria
- **Verifier catch rate:** % of proposals with violations caught and flagged

**Run evaluation:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python agents/eval_harness.py
```

Outputs: `agents/eval_results.json` with per-scenario results and summary metrics. This needs a live API key and market data, so the actual pass rate/catch rate are only known once you run it — treat any specific numbers elsewhere in the docs as illustrative targets, not a substitute for running it.

**Why this matters for interviews:**

This is how you demonstrate defensible AI: not just a fancy demo, but measurable validation. "The verifier caught and flagged N out of 15 test-case proposals that violated my max-loss constraint" is a real, specific claim you can defend — and reproduce by running the harness.

See [Project Structure](#project-structure) at the top for the full layout, including the Phase 6 files above.
