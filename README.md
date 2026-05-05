# Quant Options Engine

A from-scratch quantitative options pricing engine built in Python, implementing the core models used in derivatives trading. Built as a learning project to deeply understand options theory — every formula is derived and explained, not just called from a library.

## What's Implemented

| Phase | Topic | Status |
|-------|-------|--------|
| 1 | Black-Scholes pricer + all five Greeks | ✅ |
| 2 | Monte Carlo GBM simulator + antithetic variance reduction | ✅ |
| 3 | Market data (yfinance) + Implied Volatility solver (Brent's method) | 🔜 |
| 4 | FastAPI REST backend | 🔜 |
| 5 | React dashboard (Greeks heatmap, IV surface, mispricing chart) | 🔜 |

## Project Structure

```
Options-Pricing/
├── pricing/                   # Core pricing library
│   ├── black_scholes.py       # Closed-form BS price + Greeks (Phase 1)
│   └── monte_carlo.py         # GBM simulation pricer (Phase 2)
└── tests/                     # Test suite
    ├── test_black_scholes.py  # BS tests with reference values + identities
    └── test_monte_carlo.py    # MC convergence + variance reduction tests
```

## Quickstart

```bash
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# See Black-Scholes output
python -m pricing.black_scholes

# See Monte Carlo convergence demo
python -m pricing.monte_carlo
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
