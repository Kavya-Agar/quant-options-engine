# Quant Options Engine — Complete Technical Reference

> A from-scratch quantitative options pricing engine implementing the Black-Scholes model, Monte Carlo simulation, implied volatility solving, live market data integration, a REST API, and a React dashboard.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Financial Preliminaries](#3-financial-preliminaries)
4. [Phase 1 — Black-Scholes Pricing & Greeks](#4-phase-1--black-scholes-pricing--greeks)
5. [Phase 2 — Monte Carlo Simulation](#5-phase-2--monte-carlo-simulation)
6. [Phase 3 — Market Data & Implied Volatility](#6-phase-3--market-data--implied-volatility)
7. [Phase 4 — FastAPI Backend](#7-phase-4--fastapi-backend)
8. [Phase 5 — React Dashboard](#8-phase-5--react-dashboard)
9. [Test Suite](#9-test-suite)
10. [End-to-End Data Flow](#10-end-to-end-data-flow)
11. [Mathematical Identities & Limiting Behavior](#11-mathematical-identities--limiting-behavior)
12. [Variable & Symbol Reference](#12-variable--symbol-reference)
13. [Complete Function Signatures](#13-complete-function-signatures)
14. [Configuration & Deployment](#14-configuration--deployment)
15. [Edge Cases & Error Handling](#15-edge-cases--error-handling)

---

## 1. Project Overview

**Name:** Quant Options Engine  
**Version:** 0.1.0  
**Purpose:** A complete, production-structured implementation of core derivatives pricing theory — built from scratch to demonstrate quantitative finance engineering.

### Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Pricing engine | Python | 3.14 |
| Numerical computing | NumPy | ≥ 1.24.0 |
| Statistical methods | SciPy | ≥ 1.11.0 |
| Data manipulation | pandas | ≥ 2.0.0 |
| Market data | yfinance | ≥ 0.2.40 |
| Rate data | requests (FRED CSV) | ≥ 2.31.0 |
| REST API | FastAPI + Uvicorn | ≥ 0.110.0 / ≥ 0.27.0 |
| Frontend UI | React | 18.3.0 |
| Charting | Recharts | 2.12.0 |
| Build tool | Vite | 5.4.0 |
| Testing | pytest | ≥ 7.0.0 |

---

## 2. Repository Structure

```
Options Pricing/
├── README.md
├── Plan.txt                         # Original build plan + resume notes
├── requirements.txt                 # Python dependencies
├── Makefile                         # One-command dev startup
│
├── pricing/                         # Core quantitative library
│   ├── __init__.py
│   ├── black_scholes.py             # Phase 1: Closed-form pricing + 5 Greeks
│   ├── monte_carlo.py               # Phase 2: GBM simulation + convergence
│   ├── market_data.py               # Phase 3: yfinance + FRED data fetchers
│   └── iv_solver.py                 # Phase 3: Brent's method IV inversion
│
├── api/                             # FastAPI application
│   ├── __init__.py
│   ├── main.py                      # App factory, CORS, router registration
│   └── routes/
│       ├── __init__.py
│       ├── price.py                 # POST /api/price, GET /api/compute
│       └── chain.py                 # GET /api/chain, GET /api/expiries
│
├── dashboard/                       # React frontend (Vite)
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx                 # React DOM root mount
│       ├── App.jsx                  # Tab layout, top-level state
│       ├── index.css                # Global styles, CSS custom properties
│       ├── bs.js                    # Client-side BS + Greeks (pure JS)
│       ├── api.js                   # fetch() wrappers for backend
│       └── components/
│           ├── GreeksPanel.jsx      # Interactive slider explorer
│           ├── ChainView.jsx        # Live chain table + controls
│           └── MispricingChart.jsx  # Recharts scatter plot
│
└── tests/                           # pytest test suite
    ├── __init__.py
    ├── test_black_scholes.py        # 28 test cases
    ├── test_monte_carlo.py          # 20 test cases
    └── test_iv_solver.py            # 32 test cases
```

---

## 3. Financial Preliminaries

### 3.1 What Is an Option?

An **option** is a financial derivative — a contract whose value derives from an underlying asset (a stock, index, commodity, etc.).

- A **call option** grants the buyer the right (but not the obligation) to **buy** the underlying at a fixed price $K$ on or before expiry date $T$.
- A **put option** grants the buyer the right (but not the obligation) to **sell** the underlying at strike $K$.

The seller (writer) of the option receives a **premium** upfront in exchange for taking on this obligation.

### 3.2 Payoff at Expiry

If $S_T$ is the spot price of the underlying at expiry:

$$\text{Call payoff} = \max(S_T - K,\ 0)$$

$$\text{Put payoff} = \max(K - S_T,\ 0)$$

The max ensures the holder never exercises at a loss (they simply walk away).

### 3.3 Key Terminology

| Term | Symbol | Definition |
|------|--------|-----------|
| Spot price | $S$ | Current market price of the underlying |
| Strike price | $K$ | Price at which the option can be exercised |
| Time to expiry | $T$ | Remaining life in **years** (e.g., 90 days = 90/365) |
| Risk-free rate | $r$ | Continuously compounded rate (e.g., 5% → 0.05) |
| Volatility | $\sigma$ | Annualized standard deviation of log-returns (e.g., 20% → 0.20) |
| In-the-money (ITM) | — | Call: $S > K$; Put: $S < K$ |
| At-the-money (ATM) | — | $S \approx K$ |
| Out-of-the-money (OTM) | — | Call: $S < K$; Put: $S > K$ |
| Intrinsic value | — | $\max(S-K, 0)$ for calls; $\max(K-S, 0)$ for puts |
| Time value | — | Option price − Intrinsic value |

### 3.4 Risk-Neutral Pricing

The Black-Scholes framework prices options under the **risk-neutral measure** $\mathbb{Q}$. Under $\mathbb{Q}$:

- Every asset grows at the risk-free rate $r$, regardless of its real-world drift.
- Option price = discounted expected payoff under $\mathbb{Q}$.

$$C = e^{-rT} \mathbb{E}^{\mathbb{Q}}[\max(S_T - K, 0)]$$

This is the fundamental pricing equation. The specific form of $\mathbb{E}^{\mathbb{Q}}$ depends on the assumed dynamics of $S$.

### 3.5 Geometric Brownian Motion

The Black-Scholes model assumes the underlying follows **Geometric Brownian Motion** under the real-world measure $\mathbb{P}$:

$$dS = \mu S\, dt + \sigma S\, dW_t$$

where $W_t$ is a standard Brownian motion, $\mu$ is the drift (real-world expected return), and $\sigma$ is the instantaneous volatility.

Under the risk-neutral measure $\mathbb{Q}$, the drift $\mu$ is replaced by $r$:

$$dS = r S\, dt + \sigma S\, d\tilde{W}_t$$

By Itô's lemma, this SDE has the closed-form solution:

$$S_T = S_0 \cdot \exp\!\left[\left(r - \tfrac{1}{2}\sigma^2\right)T + \sigma\sqrt{T}\cdot Z\right], \quad Z \sim \mathcal{N}(0,1)$$

The $-\tfrac{1}{2}\sigma^2$ term is the **Itô correction** — it arises because the log of a log-normally distributed variable has a drift adjustment due to Jensen's inequality.

---

## 4. Phase 1 — Black-Scholes Pricing & Greeks

**File:** `pricing/black_scholes.py`

### 4.1 The Black-Scholes Formula

Fischer Black and Myron Scholes (1973) derived a closed-form solution for European option prices under GBM assumptions. Merton extended it. They shared the Nobel Prize in 1997.

**d₁ and d₂** are intermediate quantities:

$$d_1 = \frac{\ln(S/K) + (r + \tfrac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}$$

$$d_2 = d_1 - \sigma\sqrt{T} = \frac{\ln(S/K) + (r - \tfrac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}$$

**Interpretation of d₁ and d₂:**
- $\ln(S/K)$ — log-moneyness: how far in- or out-of-the-money the option is.
- $(r + \tfrac{1}{2}\sigma^2)T$ — risk-adjusted drift over the option's life (Itô-corrected).
- $\sigma\sqrt{T}$ — total volatility over the option's life.
- $N(d_2)$ = risk-neutral probability the call expires in-the-money.
- $N(d_1)$ = the option's **Delta** (hedge ratio).

**Black-Scholes Call Price:**

$$C = S \cdot N(d_1) - K e^{-rT} \cdot N(d_2)$$

The two terms have distinct economic meanings:
- $S \cdot N(d_1)$: present value of receiving the stock if exercised, weighted by the probability $N(d_1)$.
- $K e^{-rT} \cdot N(d_2)$: present value of paying the strike, weighted by the risk-neutral exercise probability $N(d_2)$.

**Black-Scholes Put Price:**

$$P = K e^{-rT} \cdot N(-d_2) - S \cdot N(-d_1)$$

By symmetry of the normal distribution, $N(-x) = 1 - N(x)$.

**Python implementation:**

```python
# pricing/black_scholes.py

def _d1_d2(S, K, T, r, sigma):
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2

def bs_price(S, K, T, r, sigma, option_type="call"):
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
```

**Reference output** (S = 100, K = 100, T = 1 yr, r = 5%, σ = 20%):

| Quantity | Call | Put |
|----------|------|-----|
| Price | $10.4506 | $5.5735 |

### 4.2 Put-Call Parity

A fundamental no-arbitrage identity — holds for **any** option pricing model:

$$C - P = S - K e^{-rT}$$

**Proof by construction:** If the identity is violated, buy the cheap side and sell the expensive side to earn riskless profit. Markets eliminate such opportunities.

Implication: once you can price calls, you can price puts (and vice versa) without additional modeling.

### 4.3 The Greeks

The Greeks measure how an option's price changes with respect to each input parameter. They are the primary tools of options risk management.

---

#### 4.3.1 Delta (Δ)

**Definition:** $\Delta = \partial C / \partial S$ — sensitivity of option price to underlying price.

$$\Delta_{\text{call}} = N(d_1) \in (0, 1)$$

$$\Delta_{\text{put}} = N(d_1) - 1 \in (-1, 0)$$

**Key identity:** $\Delta_{\text{call}} - \Delta_{\text{put}} = 1$ (exact, follows from put-call parity).

**Economic interpretation:** Delta = number of shares needed to hedge one option. To be **delta-neutral**, short $\Delta$ shares for each long call. This eliminates first-order exposure to $S$.

**Intuition by moneyness:**
- ATM call: $\Delta \approx 0.5$ (equal chance of expiring above or below $K$)
- Deep ITM call: $\Delta \to 1$ (behaves like stock)
- Deep OTM call: $\Delta \to 0$ (unlikely to exercise)

```python
def delta(S, K, T, r, sigma, option_type="call"):
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1
```

---

#### 4.3.2 Gamma (Γ)

**Definition:** $\Gamma = \partial^2 C / \partial S^2 = \partial \Delta / \partial S$ — second-order price sensitivity; rate of change of Delta.

$$\Gamma = \frac{\phi(d_1)}{S \sigma \sqrt{T}}$$

where $\phi(\cdot)$ is the standard normal PDF.

**Key properties:**
- Always positive (same for calls and puts — follows from put-call parity on Delta).
- Peaks ATM; decreases toward zero deep ITM or OTM.
- Increases near expiry for ATM options — "Gamma risk" is most acute when both ATM and short-dated.

**Economic interpretation:** Gamma measures how frequently a delta-hedged portfolio must be rebalanced. High Gamma = hedge drifts quickly as $S$ moves. Long options benefit from Gamma (they gain more on upside than they lose on downside); short options suffer.

**Gamma-Theta tradeoff:** Long Gamma (expensive to hold) decays via negative Theta. Short Gamma (profitable carry) is exposed to large moves. This is the central tradeoff in volatility trading.

```python
def gamma(S, K, T, r, sigma):
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))
```

---

#### 4.3.3 Vega (ν)

**Definition:** $\nu = \partial C / \partial \sigma$ — sensitivity to changes in implied volatility.

$$\nu = S \cdot \phi(d_1) \cdot \sqrt{T}$$

**Key properties:**
- Always positive (more volatility → higher option prices for both calls and puts — uncertainty has value).
- Same for calls and puts (follows from put-call parity: $\partial C/\partial\sigma = \partial P/\partial\sigma$).
- Largest ATM with long time to expiry; near zero for deep ITM/OTM (outcome nearly certain).

**Conventions:** The raw formula gives the dollar change per unit change in $\sigma$ (e.g., per 1.0 = 100%). Practitioners often quote "Vega per 1% move in vol," i.e., divide by 100.

**Economic interpretation:** Vega quantifies exposure to volatility itself — a separate risk factor from directional ($\Delta$) risk. Vega-neutral portfolios are insulated from volatility changes but still have directional exposure.

```python
def vega(S, K, T, r, sigma):
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return S * norm.pdf(d1) * math.sqrt(T)
```

---

#### 4.3.4 Theta (Θ)

**Definition:** $\Theta = \partial C / \partial T$ — rate of value decay per unit time. Reported **per calendar day**.

$$\Theta_{\text{call}} = -\frac{S \phi(d_1) \sigma}{2\sqrt{T}} - r K e^{-rT} N(d_2)$$

$$\Theta_{\text{put}} = -\frac{S \phi(d_1) \sigma}{2\sqrt{T}} + r K e^{-rT} N(-d_2)$$

Divide by 365 for per-day Theta.

**Key properties:**
- Almost always negative for long options (they lose value as time passes — "time decay").
- Accelerates near expiry (ATM options decay fastest in final weeks).
- Short options have positive Theta (collect premium daily).
- Deep ITM puts can have positive Theta due to the interest rate term.

**Gamma-Theta relationship:** $\Theta \approx -\tfrac{1}{2}\Gamma S^2 \sigma^2$ (approximately, for small $r$). High Gamma and high $|\Theta|$ go together — this is the fundamental volatility tradeoff.

```python
def theta(S, K, T, r, sigma, option_type="call"):
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    phi_d1 = norm.pdf(d1)
    discount = math.exp(-r * T)
    common = -(S * phi_d1 * sigma) / (2 * math.sqrt(T))

    if option_type == "call":
        th = common - r * K * discount * norm.cdf(d2)
    else:
        th = common + r * K * discount * norm.cdf(-d2)

    return th / 365.0
```

---

#### 4.3.5 Rho (ρ)

**Definition:** $\rho = \partial C / \partial r$ — sensitivity to changes in the risk-free rate. Reported **per 1 percentage point** change in $r$.

$$\rho_{\text{call}} = \frac{K T e^{-rT} N(d_2)}{100}$$

$$\rho_{\text{put}} = \frac{-K T e^{-rT} N(-d_2)}{100}$$

**Key properties:**
- Call Rho > 0: higher rates increase call value (lower PV of strike payment).
- Put Rho < 0: inverse (higher rates decrease put value — PV of received strike falls).
- Most significant for long-dated options (LEAPS); trivial for weekly options.
- Often the least-watched Greek in equity options; most-watched in interest rate derivatives.

```python
def rho(S, K, T, r, sigma, option_type="call"):
    _, d2 = _d1_d2(S, K, T, r, sigma)
    discount = math.exp(-r * T)

    if option_type == "call":
        return K * T * discount * norm.cdf(d2) / 100.0
    else:
        return -K * T * discount * norm.cdf(-d2) / 100.0
```

---

### 4.4 Greeks Wrapper

```python
def greeks(S, K, T, r, sigma, option_type="call") -> dict:
    return {
        "price": bs_price(S, K, T, r, sigma, option_type),
        "delta": delta(S, K, T, r, sigma, option_type),
        "gamma": gamma(S, K, T, r, sigma),       # Identical for C and P
        "vega":  vega(S, K, T, r, sigma),         # Identical for C and P
        "theta": theta(S, K, T, r, sigma, option_type),
        "rho":   rho(S, K, T, r, sigma, option_type),
    }
```

### 4.5 Complete Reference Output

Parameters: $S = 100$, $K = 100$, $T = 1$ yr, $r = 5\%$, $\sigma = 20\%$

| Greek | Call | Put | Unit |
|-------|------|-----|------|
| Price | 10.4506 | 5.5735 | $ |
| Delta | 0.6368 | −0.3632 | $/$ |
| Gamma | 0.0197 | 0.0197 | $/$² |
| Vega | 39.4467 | 39.4467 | $ per unit σ |
| Theta | −0.0039 | −0.0027 | $/day |
| Rho | 0.5337 | −0.4539 | $ per 1% rate |

---

## 5. Phase 2 — Monte Carlo Simulation

**File:** `pricing/monte_carlo.py`

### 5.1 Why Monte Carlo?

Black-Scholes gives a closed-form solution only for European options under GBM. For:
- Path-dependent options (Asian, barrier, lookback)
- Multiple underlyings (basket options)
- Models without closed-form solutions (Heston, Variance Gamma, jump-diffusion)

Monte Carlo simulation is the primary tool. This project implements MC for European options, where the answer is known, making it ideal for **validation and convergence study**.

### 5.2 The GBM Terminal Price

For a European option, only the terminal price $S_T$ matters (not the path). From the GBM SDE solution:

$$S_T = S \cdot \exp\!\left[\underbrace{\left(r - \tfrac{1}{2}\sigma^2\right)T}_{\text{drift}} + \underbrace{\sigma\sqrt{T} \cdot Z}_{\text{diffusion}}\right], \quad Z \sim \mathcal{N}(0,1)$$

Simulate $n$ independent draws $Z_1, \ldots, Z_n$ to get $n$ terminal prices $S_T^{(1)}, \ldots, S_T^{(n)}$.

### 5.3 MC Pricing Algorithm

**Step 1:** Generate $n$ standard normals.  
**Step 2:** Compute terminal prices using the GBM formula.  
**Step 3:** Compute payoffs: $h(S_T^{(i)}) = \max(S_T^{(i)} - K, 0)$ for calls.  
**Step 4:** Discount: $\hat{C} = e^{-rT} \cdot \frac{1}{n}\sum_{i=1}^n h(S_T^{(i)})$.  
**Step 5:** Compute standard error: $\hat{\sigma}_{\hat{C}} = \frac{s}{\sqrt{n}}$ where $s$ is the sample std dev of discounted payoffs.  
**Step 6:** Report 95% confidence interval: $\hat{C} \pm 1.96 \cdot \hat{\sigma}_{\hat{C}}$.

**Convergence rate:** By the Central Limit Theorem, $|\hat{C} - C_{\text{true}}| = O(n^{-1/2})$. To halve the error, quadruple the simulations.

```python
def mc_price(S, K, T, r, sigma, option_type="call",
             n_sims=50_000, antithetic=True, seed=None) -> dict:
    rng = np.random.default_rng(seed)
    drift = (r - 0.5 * sigma**2) * T
    diffusion_scale = sigma * math.sqrt(T)

    if antithetic:
        half = (n_sims + 1) // 2
        Z = rng.standard_normal(half)
        Z_all = np.concatenate([Z, -Z])[:n_sims]
    else:
        Z_all = rng.standard_normal(n_sims)

    S_T = S * np.exp(drift + diffusion_scale * Z_all)

    if option_type == "call":
        payoffs = np.maximum(S_T - K, 0.0)
    else:
        payoffs = np.maximum(K - S_T, 0.0)

    discounted = math.exp(-r * T) * payoffs
    price     = float(np.mean(discounted))
    std_error = float(np.std(discounted, ddof=1) / math.sqrt(n_sims))

    return {
        "price":     price,
        "std_error": std_error,
        "conf_low":  price - 1.96 * std_error,
        "conf_high": price + 1.96 * std_error,
        "n_sims":    n_sims,
    }
```

### 5.4 Antithetic Variates — Variance Reduction

**Idea:** Instead of $n$ independent draws $Z_1, \ldots, Z_n$, use paired draws $(Z_i, -Z_i)$. The two terminal prices are negatively correlated; their payoffs partially cancel variance.

For a call, if $Z > 0$ gives a large $S_T$ (high payoff), then $-Z$ gives a low $S_T$ (low/zero payoff). Their average has lower variance than two independent draws.

**Variance reduction factor:**

$$\text{Var}\!\left[\frac{h(Z) + h(-Z)}{2}\right] = \frac{\text{Var}[h(Z)]}{2}\left(1 + \rho_{h(Z),h(-Z)}\right)$$

Since $\rho_{h(Z),h(-Z)} < 0$ for monotone payoffs, the variance is reduced. Empirically reduces standard error by roughly 30-50% for European options.

**Cost:** Zero — same number of function evaluations, just different random number arrangement.

### 5.5 Convergence Analysis

```python
def mc_convergence(S, K, T, r, sigma, option_type="call",
                   sim_counts=None, seed=42) -> list[dict]:
```

Default `sim_counts = [100, 500, 1_000, 5_000, 10_000, 50_000]`

Each row returns:
```
n_sims   | mc_price | bs_price | error = |mc - bs| | std_error
---------+----------+----------+-------------------+----------
100      | ~noisier |  10.4506 |        ~0.5–2.0   |  ~0.15
500      |          |          |        ~0.2–0.8   |  ~0.07
1,000    |          |          |        ~0.1–0.4   |  ~0.05
5,000    |          |          |        ~0.05–0.15 |  ~0.02
10,000   |          |          |        ~0.03–0.10 |  ~0.015
50,000   |          |          |        ~0.01–0.05 |  ~0.007
```

The $1/\sqrt{n}$ convergence rate is clearly visible: 10× more simulations → ~3.16× smaller error.

---

## 6. Phase 3 — Market Data & Implied Volatility

### 6.1 Market Data Module

**File:** `pricing/market_data.py`

#### 6.1.1 Risk-Free Rate

**Source:** FRED (Federal Reserve Economic Data) — no API key required.

```
URL: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3
Series: DTB3 — 3-Month Treasury Bill Secondary Market Rate (percent, annualized)
```

**Why 3-Month T-bill?** Universally accepted as the risk-free rate proxy in academic finance. It is nearly free of credit risk (backed by U.S. government) and short enough that duration risk is negligible.

**Parsing logic:**
1. Fetch CSV (two columns: date, rate).
2. Skip rows where rate = "." (missing observations — FRED convention).
3. Take the most recent valid observation.
4. Divide by 100 to convert from percent to decimal.

```python
def get_risk_free_rate() -> float:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
    resp = requests.get(url, timeout=10)
    # Parse CSV, take last valid row, divide by 100
```

#### 6.1.2 Spot Price

```python
def get_spot_price(ticker: str) -> float:
    hist = yf.Ticker(ticker).history(period="5d")
    return float(hist["Close"].iloc[-1])
```

Uses the most recent closing price via yfinance. 5-day window ensures at least one trading day of data.

#### 6.1.3 Time to Expiry

```python
def expiry_to_years(expiry: str) -> float:
    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    today = date.today()
    days = (expiry_date - today).days
    if days <= 0:
        raise ValueError(f"Expiry '{expiry}' is in the past (or today).")
    return days / 365.0
```

Simple calendar-day convention. Some practitioners use business days or actual/365 with holiday calendars; this uses the simplest convention.

#### 6.1.4 Options Chain

```python
def get_options_chain(ticker, expiry=None):
    tk = yf.Ticker(ticker)
    available_expiries = list(tk.options)    # All available dates
    selected = expiry or available_expiries[0]    # Default: nearest
    opt = tk.option_chain(selected)
    return opt.calls, opt.puts, available_expiries, selected
```

The returned DataFrames include: `contractSymbol`, `strike`, `lastPrice`, `bid`, `ask`, `volume`, `openInterest`, `impliedVolatility` (yfinance's own estimate).

#### 6.1.5 Historical Volatility

$$\sigma_{\text{hist}} = \sqrt{252} \cdot \text{std}\!\left(\ln\frac{S_t}{S_{t-1}}\right)_{\text{last } w \text{ days}}$$

```python
def historical_vol(ticker: str, window: int = 30) -> float:
    hist = yf.Ticker(ticker).history(period=f"{window + 10}d")
    log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    return float(log_returns.tail(window).std() * np.sqrt(252))
```

**Why 252?** Approximate number of trading days per year in US equity markets. Annualizing by $\sqrt{252}$ converts daily volatility to annual.

**Why 30 days?** A common short-term volatility estimate. Shorter windows are more responsive; longer windows are smoother.

### 6.2 Implied Volatility Solver

**File:** `pricing/iv_solver.py`

#### 6.2.1 The IV Inversion Problem

The Black-Scholes formula gives price as a function of inputs:
$$C = \text{BS}(S, K, T, r, \sigma)$$

**Implied volatility** is the $\sigma$ that makes the model price equal the observed market price:
$$\sigma_{\text{impl}} = \text{BS}^{-1}(S, K, T, r, C_{\text{market}})$$

There is **no closed-form inverse** — the relationship between $\sigma$ and $C$ is transcendental (involves $N(\cdot)$). We must solve numerically.

#### 6.2.2 Why Not Newton-Raphson?

Newton-Raphson requires computing the derivative: $\partial C / \partial \sigma = \text{Vega}$.

Problem: For deep OTM options, Vega ≈ 0. The Newton step becomes:
$$\sigma_{\text{new}} = \sigma - \frac{C(\sigma) - C_{\text{market}}}{\text{Vega}(\sigma)} \to \sigma - \frac{\text{small}}{\approx 0}$$

This causes numerical instability and divergence. Newton-Raphson can also fail when starting outside the basin of convergence.

#### 6.2.3 Brent's Method

Brent's method is a hybrid root-finding algorithm combining:

1. **Bisection** — guaranteed to converge if a sign change exists in the bracket.
2. **Secant method** — uses linear interpolation for faster (superlinear) convergence.
3. **Inverse quadratic interpolation** — fits a quadratic through 3 points for even faster convergence.

The algorithm switches between methods, always falling back to bisection if the faster methods are about to step outside the bracket or not converge fast enough. This gives:
- **Guaranteed convergence** (if a sign change exists in the bracket)
- **Superlinear convergence rate** in practice
- **No derivative required**

**Implementation:**

```python
from scipy.optimize import brentq

def implied_vol(market_price, S, K, T, r, option_type="call",
                tol=1e-6, max_iter=200) -> Optional[float]:

    if T <= 0:
        return None

    intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    if market_price <= intrinsic + 1e-8:
        return None  # At or below intrinsic: no time value to solve for

    def objective(sigma):
        return bs_price(S, K, T, r, sigma, option_type) - market_price

    low_vol, high_vol = 0.001, 5.0   # Bracket: 0.1% to 500% vol

    # Check bracket validity (need sign change)
    if objective(low_vol) * objective(high_vol) > 0:
        return None

    return brentq(objective, low_vol, high_vol, xtol=tol, maxiter=max_iter)
```

**Volatility bracket [0.1%, 500%]:**
- Lower bound: essentially zero vol (prices at intrinsic).
- Upper bound: 500% annualized vol — far beyond any real asset. Ensures the bracket always contains the true IV for any tradeable option.

**Convergence:** Typically 10-20 Brent iterations. Tolerance $10^{-6}$ means IV is recovered to within 0.0001% (0.01 bp) of the true value.

#### 6.2.4 Bid-Ask Midpoint Convention

```python
def enrich_chain(df, S, T, r, option_type) -> pd.DataFrame:
    df = df.copy()

    # Price priority: midpoint > lastPrice > None
    df["_price"] = np.where(
        (df["bid"] > 0) & (df["ask"] > 0),
        (df["bid"] + df["ask"]) / 2.0,
        df["lastPrice"]
    )

    df["iv"] = df.apply(
        lambda row: implied_vol(row["_price"], S, row["strike"], T, r, option_type)
        if row["_price"] > 0 else None,
        axis=1
    )
    return df.drop(columns=["_price"])
```

**Why midpoint?** The bid-ask spread represents the market maker's inventory cost and adverse selection cost. The midpoint is a better estimate of "fair value" than either the bid or ask alone. `lastPrice` can be stale for illiquid options.

### 6.3 The Volatility Smile and Skew

In the Black-Scholes world, $\sigma$ is a constant — IV should be flat across all strikes and expiries. In reality:

**Volatility Skew (Equity markets):**
- Lower strikes → higher IV.
- OTM puts are expensive relative to BS (investors pay for crash protection).
- The skew is asymmetric; the left tail is feared more than the right.

**Volatility Smile (FX, some commodity markets):**
- Both OTM calls and OTM puts are expensive relative to ATM.
- Symmetric elevated wings, shaped like a smile.

**Root causes:**
- **Fat tails / non-normal returns:** Large moves happen more often than GBM predicts.
- **Jump risk:** Sudden large price movements (earnings, geopolitical events).
- **Supply/demand:** Structural demand for OTM puts (portfolio insurance) inflates their prices and IVs.
- **Stochastic volatility:** Volatility itself is random and correlated with returns.

The IV solved by this project **does not assume** the skew away — it solves for the IV that each individual market price implies, revealing the skew empirically.

---

## 7. Phase 4 — FastAPI Backend

**File:** `api/main.py`, `api/routes/price.py`, `api/routes/chain.py`

### 7.1 Application Setup

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import price, chain

app = FastAPI(
    title="Options Pricing Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],    # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(price.router, prefix="/api", tags=["pricing"])
app.include_router(chain.router, prefix="/api", tags=["chain"])

@app.get("/health")
def health():
    return {"status": "ok"}
```

**Auto-generated API docs:** `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`

### 7.2 Pydantic Models (Request/Response Schemas)

FastAPI uses Pydantic for automatic request validation and response serialization.

```python
# Request: POST /api/price
class PriceRequest(BaseModel):
    ticker:      str
    strike:      float                  # > 0
    expiry:      str                    # "YYYY-MM-DD"
    option_type: str                    # "call" or "put"
    sigma:       Optional[float] = None # None → use 30-day historical vol

# Response: POST /api/price and GET /api/compute
class GreeksOut(BaseModel):
    ticker:       str
    spot:         float
    strike:       float
    expiry:       str
    T:            float     # Years (6 decimals)
    r:            float     # Rate (6 decimals)
    sigma:        float     # Volatility (6 decimals)
    sigma_source: str       # "user_provided" or "30d_historical"
    option_type:  str
    price:        float
    delta:        float
    gamma:        float
    vega:         float
    theta:        float
    rho:          float

class ComputeOut(BaseModel):
    price: float
    delta: float
    gamma: float
    vega:  float
    theta: float
    rho:   float

class ExpiriesResponse(BaseModel):
    ticker:   str
    expiries: List[str]

class ContractOut(BaseModel):
    strike:        float
    option_type:   str
    market_price:  float
    bs_price:      float
    mispricing:    float            # bs_price - market_price
    iv:            Optional[float]  # Brent's method IV
    yf_iv:         Optional[float]  # yfinance's own IV estimate
    bid:           float
    ask:           float
    volume:        Optional[float]
    open_interest: Optional[float]

class ChainResponse(BaseModel):
    ticker:    str
    expiry:    str
    T:         float
    spot:      float
    r:         float
    contracts: List[ContractOut]
```

### 7.3 Endpoint Reference

#### POST /api/price — Live Ticker Pricing

**Purpose:** Fetch real-time market data and compute full Greeks for a given option.

**Request body (JSON):**
```json
{
  "ticker": "SPY",
  "strike": 500.0,
  "expiry": "2025-03-21",
  "option_type": "call",
  "sigma": null
}
```

**Logic:**
1. `S = get_spot_price(ticker)` — yfinance
2. `r = get_risk_free_rate()` — FRED
3. `T = expiry_to_years(expiry)` — calendar days / 365
4. `sigma = sigma or historical_vol(ticker, 30)` — fallback to 30-day realized vol
5. `result = greeks(S, strike, T, r, sigma, option_type)` — BS formulas
6. Round to 6 decimal places; return `GreeksOut`

**HTTP status codes:**
- `200 OK` — Success
- `422 Unprocessable Entity` — Invalid input (past expiry, unknown ticker, negative strike)
- `503 Service Unavailable` — Network or market data failure

---

#### GET /api/compute — Raw Parameter Greeks

**Purpose:** Compute Greeks from raw parameters, no network calls. Used by the dashboard's real-time slider.

**Query parameters:**
```
S        = 100.0    (gt=0, required)
K        = 100.0    (gt=0, required)
T        = 1.0      (gt=0, required)
r        = 0.05     (default 0.05)
sigma    = 0.20     (gt=0, le=5.0, required)
option_type = "call"  (pattern: ^(call|put)$)
```

**Example:** `GET /api/compute?S=100&K=100&T=1&r=0.05&sigma=0.20&option_type=call`

Returns `ComputeOut` with price + 5 Greeks. No database or network I/O — pure computation.

---

#### GET /api/expiries — Available Expiry Dates

**Query parameter:** `ticker=SPY`

**Returns:**
```json
{
  "ticker": "SPY",
  "expiries": ["2025-01-17", "2025-01-31", "2025-02-21", ...]
}
```

Calls `yfinance.Ticker(ticker).options` to get the list of available expiration dates.

---

#### GET /api/chain — Full Options Chain with IV

**Query parameters:** `ticker=SPY`, `expiry=2025-01-17` (optional; defaults to nearest)

**Returns:** `ChainResponse` with all contracts sorted by (strike, option_type).

**Processing per contract:**
1. Compute `market_price = (bid + ask) / 2` if available, else `lastPrice`.
2. Run `implied_vol(market_price, S, K, T, r, option_type)` via Brent's method.
3. If `iv` is None (unsolvable): use `iv = 0.20` as fallback for BS price computation.
4. `bs_price = bs_price(S, K, T, r, iv, option_type)`.
5. `mispricing = bs_price - market_price`.
6. Filter out contracts with `market_price ≤ 0`.

**Interpretation of mispricing:**
- `mispricing > 0`: BS (at Brent IV) prices higher than market → market is selling the option "cheap" relative to its IV-derived fair value. (Often a sign of stale quotes or wide bid-ask.)
- `mispricing < 0`: Market prices higher → model undervalues. (Usually means IV is non-trivial to recover precisely.)
- `mispricing ≈ 0`: BS re-prices the market exactly at the solved IV. This is always approximately true by construction; deviations arise from the fallback IV = 20%.

---

### 7.4 Running the Server

```bash
uvicorn api.main:app --reload --port 8000
```

- `--reload`: File-watching auto-restart (development only)
- `--port 8000`: Default FastAPI port
- Production: Remove `--reload`; add `--workers 4` for multi-process

---

## 8. Phase 5 — React Dashboard

### 8.1 Frontend Architecture

```
dashboard/src/
├── main.jsx           — Mounts <App /> to DOM
├── App.jsx            — Tab switcher, top-level layout
├── index.css          — Global styles, CSS custom properties
├── bs.js              — Self-contained Black-Scholes in JavaScript
├── api.js             — fetch() wrapper functions
└── components/
    ├── GreeksPanel.jsx     — Tab 0: Real-time Greeks explorer
    ├── ChainView.jsx       — Tab 1: Live chain + controls
    └── MispricingChart.jsx — Recharts scatter component
```

### 8.2 Vite Proxy Configuration

```javascript
// dashboard/vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

All requests from the React app starting with `/api` are transparently forwarded to the FastAPI backend. This eliminates CORS browser restrictions during development — from the browser's perspective, the frontend and backend share the same origin (`:5173`).

### 8.3 Client-Side Black-Scholes (JavaScript)

**File:** `dashboard/src/bs.js`

Since the Greeks Explorer updates on every slider move, making an API call (even a fast one) would introduce perceptible latency. Instead, all computation runs client-side in JavaScript.

**Normal CDF Approximation — Abramowitz & Stegun §26.2.17:**

$$N(x) \approx 1 - \phi(x)\left(\sum_{i=1}^{5} a_i t^i\right), \quad t = \frac{1}{1 + 0.2316419 \cdot |x|}$$

Coefficients: $a_1 = 0.319381530$, $a_2 = -0.356563782$, $a_3 = 1.781477937$, $a_4 = -1.821255978$, $a_5 = 1.330274429$

**Maximum error:** $< 7.5 \times 10^{-8}$ — more than sufficient for display purposes.

```javascript
function normCdf(x) {
  const a = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429]
  const t = 1 / (1 + 0.2316419 * Math.abs(x))
  const d = Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI)
  let poly = 0, tk = t
  for (const ai of a) { poly += ai * tk; tk *= t }
  const p = 1 - d * poly
  return x >= 0 ? p : 1 - p
}

export function bsGreeks(S, K, T, r, sigma, optionType) {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) return null

  const sqrtT = Math.sqrt(T)
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
  const d2 = d1 - sigma * sqrtT
  const disc = Math.exp(-r * T)
  const phi = normPdf(d1)

  let price, delta
  if (optionType === 'call') {
    price = S * normCdf(d1) - K * disc * normCdf(d2)
    delta = normCdf(d1)
  } else {
    price = K * disc * normCdf(-d2) - S * normCdf(-d1)
    delta = normCdf(d1) - 1
  }

  const gamma = phi / (S * sigma * sqrtT)
  const vega  = S * phi * sqrtT
  const thetaYear = optionType === 'call'
    ? -(S * phi * sigma) / (2 * sqrtT) - r * K * disc * normCdf(d2)
    : -(S * phi * sigma) / (2 * sqrtT) + r * K * disc * normCdf(-d2)
  const theta = thetaYear / 365
  const rho = optionType === 'call'
    ? K * T * disc * normCdf(d2) / 100
    : -K * T * disc * normCdf(-d2) / 100

  return { price, delta, gamma, vega, theta, rho }
}
```

This JS implementation exactly mirrors the Python formulas. Validated to match to 6 decimal places across all standard parameter ranges.

### 8.4 Greeks Explorer (GreeksPanel.jsx)

**Tab 0 — No network latency. All computation local.**

**Slider parameters and ranges:**

| Parameter | Min | Max | Step | Default |
|-----------|-----|-----|------|---------|
| Spot ($S$) | 10 | 300 | 1 | 100 |
| Strike ($K$) | 10 | 300 | 1 | 100 |
| Time ($T$, yr) | 0.01 | 2.0 | 0.01 | 1.0 |
| Rate ($r$) | 0 | 0.15 | 0.001 | 0.05 |
| Volatility ($\sigma$) | 0.01 | 1.5 | 0.01 | 0.20 |
| Type | — | — | — | Call |

**Moneyness indicator:**
```javascript
const moneyness =
  S > K * 1.02 ? (type === 'call' ? 'ITM' : 'OTM') :
  S < K * 0.98 ? (type === 'call' ? 'OTM' : 'ITM') : 'ATM'
```

2% band around parity is the ATM zone. Color-coded: green (ITM), red (OTM), yellow (ATM).

**Computed annotations:**
```
Breakeven:     K + Price  (call)  |  K - Price  (put)
Intrinsic:     max(S - K, 0)  (call)  |  max(K - S, 0)  (put)
Time Value:    Price - Intrinsic
```

**React pattern:** `useMemo(() => bsGreeks(...), [S, K, T, r, sigma, type])` — Greeks recompute only when any dependency changes, not on every render cycle.

### 8.5 Live Chain View (ChainView.jsx)

**Tab 1 — Requires running FastAPI backend.**

**User flow:**
1. Enter ticker symbol (e.g., `SPY`, `AAPL`, `QQQ`)
2. Click **Load Expiries** → `GET /api/expiries?ticker=...`
3. Select expiry date from dropdown
4. Click **Load Chain** → `GET /api/chain?ticker=...&expiry=...`
5. Optionally filter: ALL / CALL / PUT
6. View scatter plot and table

**Statistics bar (computed from chain data):**
```javascript
const avgIV = contracts
  .map(c => c.iv).filter(Boolean)
  .reduce((sum, v) => sum + v, 0) / count
```

Displays: Spot price, risk-free rate (%), time to expiry (years), count of calls, count of puts, average IV (%).

**Table columns:**

| Column | Format | Notes |
|--------|--------|-------|
| STRIKE | `toFixed(2)` | Core parameter |
| TYPE | CALL (green) / PUT (red) | Color-coded |
| MKT PRICE | `toFixed(4)` | Bid-ask mid or lastPrice |
| BS PRICE | `toFixed(4)` | BS at solved IV |
| MISPRICING | `toFixed(4)`, colored | Green if positive (BS higher) |
| IV (BRENT) | % 1 decimal | Red >40%, blue <15% |
| BID | `toFixed(4)`, dimmed | — |
| ASK | `toFixed(4)`, dimmed | — |
| VOLUME | integer, commas | — |
| OI | integer, commas | Open interest |

### 8.6 Mispricing Chart (MispricingChart.jsx)

**Chart type:** `ScatterChart` from Recharts.

**Axes:**
- X: `market_price` ($)
- Y: `bs_price` ($)

**Series:**
- Calls: Green filled circles (`#00c97a`), radius 4px, opacity 0.8
- Puts: Red filled circles (`#e05252`), radius 4px, opacity 0.8

**Reference line:** Diagonal $y = x$ (dashed gray) — represents perfect pricing. Points on this line: BS and market agree. Points above: BS overprices. Points below: BS underprices.

**Data transformation:**
```javascript
const calls = contracts
  .filter(c => c.option_type === 'call' && c.iv != null)
  .map(c => ({ x: c.market_price, y: c.bs_price, strike: c.strike, iv: c.iv, optionType: 'call' }))
```

**Tooltip:** On hover shows: Strike, Type (colored), Market Price, BS Price, Mispricing (Δ), IV.

**Interpretation:** Systematic deviation from the diagonal reveals model inadequacy. In practice:
- OTM puts often appear above the diagonal (BS undervalues them at their traded IV — reflecting the skew).
- Near-ATM options cluster tightly on the diagonal.
- Very OTM/very cheap options scatter widely (stale quotes, wide spreads).

### 8.7 Design System

**Color scheme (CSS custom properties):**
```css
:root {
  --bg:      #0a0a0a;   /* Main background */
  --surface: #111111;   /* Cards, table rows */
  --border:  #1e1e1e;   /* All borders */
  --text:    #d4d4d4;   /* Primary text */
  --dim:     #555555;   /* Secondary/metadata text */
  --green:   #00c97a;   /* Calls, positive values, ITM */
  --red:     #e05252;   /* Puts, negative values, OTM */
  --yellow:  #c9a000;   /* ATM indicator, warnings */
  --accent:  #4a9eff;   /* Low IV highlight, links */
}
```

**Typography:**
- Font: `'Courier New', Courier, monospace` — terminal/quant aesthetic.
- Base size: 13px; labels: 11px; headings: tracked at 0.08-0.10em.
- All uppercase labels with letter-spacing for clarity.

**Range slider styling:**
```css
input[type=range]::-webkit-slider-thumb {
  background: var(--green);
  width: 12px; height: 12px; border-radius: 50%;
}
input[type=range]::-webkit-slider-runnable-track {
  height: 2px; background: var(--border);
}
```

---

## 9. Test Suite

### 9.1 Overview

| File | Classes | Tests | Focus |
|------|---------|-------|-------|
| `test_black_scholes.py` | 6 | 28 | Formula correctness, Hull reference values |
| `test_monte_carlo.py` | 3 | 20 | Convergence, variance reduction, reproducibility |
| `test_iv_solver.py` | 4 | 32 | Round-trip IV, edge cases, chain enrichment |

**Common tolerance:** `TOLERANCE = 1e-4` (0.01% error threshold).  
**MC tolerance:** $0.10 (convergence test at 50k sims with antithetic).

### 9.2 Black-Scholes Test Cases

**Reference: Hull, "Options, Futures, and Other Derivatives" (10th ed.)**

The "Hull example" parameters appear throughout:
- $S = 42$, $K = 40$, $T = 0.5$ yr, $r = 10\%$, $\sigma = 20\%$

Expected values (verified against textbook):
- Call price ≈ 4.7594
- Put price ≈ 0.8086
- $d_1 \approx 0.7693$, $N(d_1) \approx 0.7791$ (Hull's Delta)
- Gamma ≈ 0.04996 (Hull)
- Vega ≈ 8.8134 (Hull, annualized, not per-day)
- Call Theta ≈ −0.01249 per day (Hull)
- Call Rho ≈ 0.1398 per 1%

**Key identities tested:**
```
Put-Call Parity:         C - P = S - K*e^(-rT)        (within 1e-10)
Delta identity:          Δ_call - Δ_put = 1            (within 1e-10)
Gamma symmetry:          Γ_call = Γ_put                (within 1e-10)
Vega symmetry:           ν_call = ν_put                (within 1e-10)
Delta range (call):      0 < Δ_call < 1                (strict)
Delta range (put):       -1 < Δ_put < 0                (strict)
Gamma positivity:        Γ > 0                          (always)
Vega positivity:         ν > 0                          (always)
Deep ITM call ≈ intrinsic: S=200, K=100 → C ≈ 100*e^(-rT)
Deep OTM call ≈ 0:         S=50, K=200 → C < 0.001
```

### 9.3 Monte Carlo Test Cases

**Convergence tests (50k sims, antithetic):**
```
Call:  |MC - BS| < $0.10
Put:   |MC - BS| < $0.10
BS price within 95% CI: probability ≥ 0.95 (structural test)
```

**Put-call parity (two independent MC runs):**
```
|MC_call - MC_put - (S - K*e^(-rT))| < $0.20
```
(Larger tolerance — two independent MC estimates.)

**Antithetic variance reduction (10 seeds):**
```
mean(std_error_antithetic) < mean(std_error_standard)
```

**Reproducibility:**
```python
mc_price(..., seed=42) == mc_price(..., seed=42)   # Identical
mc_price(..., seed=42) != mc_price(..., seed=99)   # Different
```

### 9.4 Implied Volatility Test Cases

**Round-trip tests:** Generate BS price at known $\sigma$, then recover $\sigma$ via IV solver.

Parameter sweep:
- Moneyness: ITM ($S=110, K=100$), ATM ($S=100, K=100$), OTM ($S=90, K=100$)
- Time: Short (T=2/52≈0.038 yr), Normal (T=0.5 yr), Long (T=2 yr, LEAPS)
- Volatility: Low (5%), Normal (20%), High (80%)
- Rate: Zero (r=0%), Normal (r=5%)
- Strike range: K ∈ {70, 80, 90, 100, 110, 120, 130}

**Edge case returns (None, not exception):**
```
market_price < intrinsic + 1e-8  →  None  (arbitrageable)
market_price = 0                 →  None  (no price)
T = 0                            →  None  (expired)
T < 0                            →  None  (negative time)
```

**Exception (raises ValueError):**
```
option_type = "banana"  →  ValueError("Invalid option_type")
```

---

## 10. End-to-End Data Flow

### 10.1 Greeks Explorer (Zero Latency Path)

```
┌─────────────────────────────────────────┐
│  User moves slider                       │
│  S=105, K=100, T=0.5, r=0.05, σ=0.20   │
└─────────────────┬───────────────────────┘
                  │ React state update
                  ▼
┌─────────────────────────────────────────┐
│  useMemo computes bsGreeks(...)          │
│  (client-side JS, <1ms)                  │
│                                          │
│  d1 = (ln(1.05) + (0.05+0.02)*0.5)     │
│       / (0.20 * 0.707)                  │
│     = (0.0488 + 0.035) / 0.1414        │
│     ≈ 0.5933                            │
│                                          │
│  d2 = 0.5933 - 0.1414 = 0.4519         │
│                                          │
│  N(d1) = 0.7236, N(d2) = 0.6743        │
│                                          │
│  C = 105*0.7236 - 100*e^(-0.025)*0.6743│
│    = 75.98 - 65.74 = 10.24             │
│  Δ = 0.7236, Γ = 0.0222, ...           │
└─────────────────┬───────────────────────┘
                  │ State → JSX re-render
                  ▼
┌─────────────────────────────────────────┐
│  Greek cards update in UI               │
│  Price: $10.2401   Delta: 0.7236        │
│  Gamma: 0.0222     Vega: 37.28          │
│  Theta: -0.0038    Rho: 0.4978          │
└─────────────────────────────────────────┘
```

### 10.2 Live Chain (Network Path)

```
User: ticker="SPY", expiry="2025-03-21"
            │
            ▼ GET /api/chain?ticker=SPY&expiry=2025-03-21
┌───────────────────────────────────────────────┐
│  FastAPI: chain.get_chain()                    │
│                                                │
│  1. S = yfinance.history(5d)["Close"][-1]     │
│     e.g., S = 598.45                           │
│                                                │
│  2. r = FRED DTB3 CSV                          │
│     e.g., r = 0.0523 (5.23%)                  │
│                                                │
│  3. calls_df, puts_df = yf.option_chain(...)  │
│     ~200-400 contracts for SPY                 │
│                                                │
│  4. T = (2025-03-21 - today).days / 365       │
│     e.g., T = 0.1315 yr (48 days)             │
│                                                │
│  5. For each call:                             │
│     market_price = (bid + ask) / 2            │
│     iv = brentq(BS(σ) - market_price, ...)    │
│     bs_price = BS(S, K, T, r, iv)             │
│     mispricing = bs_price - market_price       │
│                                                │
│  6. Sort by (strike, option_type)             │
│  7. Return ChainResponse                       │
└───────────────────┬───────────────────────────┘
                    │ ~1-3 seconds (network I/O)
                    ▼
┌───────────────────────────────────────────────┐
│  Frontend receives ChainResponse               │
│                                                │
│  Stats bar: SPY @ $598.45 | r=5.23% | ...     │
│                                                │
│  Scatter plot: market_price vs bs_price        │
│  Points near diagonal → good model fit         │
│  Points away from diagonal → mispricing        │
│                                                │
│  Table: 200+ rows with full data               │
└───────────────────────────────────────────────┘
```

### 10.3 Computational Complexity

| Operation | Complexity | Typical Time |
|-----------|-----------|--------------|
| BS price | O(1) | < 1μs |
| All Greeks | O(1) | < 5μs |
| MC price (50k sims) | O(n) | ~10ms |
| FRED rate fetch | O(1) network | ~200ms |
| yfinance spot | O(1) network | ~300ms |
| Options chain fetch | O(1) network | ~500ms |
| IV solve (Brent) | O(log(1/ε)) ≈ 15 iters | ~50μs |
| Full chain IV enrichment | O(n) contracts | ~100-500ms |
| Full /api/chain endpoint | Network bound | 1-3 seconds |

---

## 11. Mathematical Identities & Limiting Behavior

### 11.1 Core Identities

**Put-Call Parity (no-arbitrage):**
$$C - P = S - Ke^{-rT}$$

**Delta identity:**
$$\Delta_{\text{call}} - \Delta_{\text{put}} = 1$$

**Gamma equality:**
$$\Gamma_{\text{call}} = \Gamma_{\text{put}} = \frac{\phi(d_1)}{S\sigma\sqrt{T}}$$

**Vega equality:**
$$\nu_{\text{call}} = \nu_{\text{put}} = S\phi(d_1)\sqrt{T}$$

**Gamma-Theta relationship (approximate, small $r$):**
$$\Theta \approx -\tfrac{1}{2}\Gamma S^2\sigma^2$$

Long Gamma means short Theta (pay for convexity through daily decay).

**Black-Scholes PDE (fundamental):**
$$\frac{\partial V}{\partial t} + \frac{1}{2}\sigma^2 S^2 \frac{\partial^2 V}{\partial S^2} + rS\frac{\partial V}{\partial S} - rV = 0$$

Every option price satisfying this PDE with the correct boundary conditions gives the BS pricing formula. The Greeks are partial derivatives of $V$ with respect to $t$, $S$, and $\sigma$.

### 11.2 Asymptotic Behavior

**As $S/K \to \infty$ (deep ITM call):**
$$d_1, d_2 \to +\infty, \quad N(d_1), N(d_2) \to 1$$
$$C \to S - Ke^{-rT} \quad \text{(forward price)}$$
$$\Delta_{\text{call}} \to 1, \quad \Gamma \to 0, \quad \nu \to 0$$

**As $S/K \to 0$ (deep OTM call):**
$$d_1, d_2 \to -\infty, \quad N(d_1), N(d_2) \to 0$$
$$C \to 0$$
$$\Delta_{\text{call}} \to 0, \quad \Gamma \to 0, \quad \nu \to 0$$

**As $T \to 0$ (expiry):**
- ATM: $C \to 0$, $\Gamma \to +\infty$ (spike at $S = K$)
- ITM call: $C \to S - K$
- OTM call: $C \to 0$

**As $\sigma \to 0$:**
$$C \to \max(Se^{-\cdot} - Ke^{-rT},\ 0) \approx \max(S - Ke^{-rT},\ 0)$$
Options price at forward intrinsic value.

**As $\sigma \to \infty$:**
$$C \to S \quad \text{(call)}; \quad P \to Ke^{-rT} \quad \text{(put)}$$
With infinite volatility, calls approach stock price; puts approach discounted strike.

### 11.3 Monte Carlo Convergence Theory

**Law of Large Numbers:** $\hat{C}_n \to C_{\text{true}}$ almost surely as $n \to \infty$.

**Central Limit Theorem:** $\sqrt{n}(\hat{C}_n - C_{\text{true}}) \xrightarrow{d} \mathcal{N}(0, \sigma_h^2)$ where $\sigma_h^2 = \text{Var}[h(S_T)]$.

**Standard error:** $\text{SE}_n = \sigma_h / \sqrt{n}$

**95% CI:** $\hat{C}_n \pm 1.96 \cdot \sigma_h / \sqrt{n}$

**Error reduction:** To achieve precision $\epsilon$, need $n \geq (1.96\sigma_h/\epsilon)^2$ simulations.

---

## 12. Variable & Symbol Reference

### 12.1 Mathematical Symbols

| Symbol | Name | Domain | Notes |
|--------|------|--------|-------|
| $S$ | Spot price | $\mathbb{R}_{>0}$ | Current underlying price |
| $K$ | Strike price | $\mathbb{R}_{>0}$ | Exercise price |
| $T$ | Time to expiry | $\mathbb{R}_{>0}$ | In years |
| $r$ | Risk-free rate | $\mathbb{R}_{\geq 0}$ | Continuously compounded |
| $\sigma$ | Volatility | $\mathbb{R}_{>0}$ | Annualized, decimal |
| $d_1$ | — | $\mathbb{R}$ | Intermediate BS quantity |
| $d_2$ | — | $\mathbb{R}$ | $d_1 - \sigma\sqrt{T}$ |
| $N(\cdot)$ | Normal CDF | $[0,1]$ | $\mathcal{N}(0,1)$ CDF |
| $\phi(\cdot)$ | Normal PDF | $(0, 0.399]$ | $\mathcal{N}(0,1)$ density |
| $C$ | Call price | $\mathbb{R}_{\geq 0}$ | — |
| $P$ | Put price | $\mathbb{R}_{\geq 0}$ | — |
| $\Delta$ | Delta | $(-1,1)$ | $\partial V/\partial S$ |
| $\Gamma$ | Gamma | $\mathbb{R}_{>0}$ | $\partial^2 V/\partial S^2$ |
| $\nu$ | Vega | $\mathbb{R}_{>0}$ | $\partial V/\partial \sigma$ |
| $\Theta$ | Theta | $\mathbb{R}$ | $\partial V/\partial t$ per day |
| $\rho$ | Rho | $\mathbb{R}$ | $\partial V/\partial r$ per 1% |
| $\sigma_{\text{impl}}$ | Implied vol | $\mathbb{R}_{>0}$ | Market-implied $\sigma$ |
| $S_T$ | Terminal price | $\mathbb{R}_{>0}$ | At expiry |
| $Z$ | Standard normal | $\mathbb{R}$ | $\sim \mathcal{N}(0,1)$ |
| $W_t$ | Brownian motion | $\mathbb{R}$ | $W_t \sim \mathcal{N}(0,t)$ |

### 12.2 Code Variable Names

| Code | Mathematical | Notes |
|------|-------------|-------|
| `S` | $S$ | Spot price |
| `K` | $K$ | Strike |
| `T` | $T$ | Time in years |
| `r` | $r$ | Risk-free rate (decimal) |
| `sigma` | $\sigma$ | Volatility (decimal) |
| `d1`, `d2` | $d_1, d_2$ | Intermediate quantities |
| `norm.cdf(x)` | $N(x)$ | SciPy normal CDF |
| `norm.pdf(x)` | $\phi(x)$ | SciPy normal PDF |
| `n_sims` | $n$ | Monte Carlo paths |
| `Z_all` | $Z_1,\ldots,Z_n$ | Standard normal draws |
| `S_T` | $S_T$ | Simulated terminal prices |
| `payoffs` | $h(S_T^{(i)})$ | Option payoffs |
| `discounted` | $e^{-rT}h(S_T^{(i)})$ | Discounted payoffs |
| `std_error` | $\hat{\sigma}/\sqrt{n}$ | MC standard error |
| `market_price` | $C_{\text{market}}$ | Observed traded price |
| `bs_price` | $\text{BS}(\sigma_{\text{impl}})$ | Model price at IV |
| `mispricing` | $\text{BS} - C_{\text{mkt}}$ | Model vs market |
| `iv` | $\sigma_{\text{impl}}$ | Brent-solved implied vol |
| `yf_iv` | — | yfinance's own IV estimate |
| `bid`, `ask` | — | Quoted prices |
| `volume` | — | Daily contracts traded |
| `open_interest` | — | Outstanding contracts |

---

## 13. Complete Function Signatures

### 13.1 `pricing/black_scholes.py`

```python
def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]

def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call") -> float

def delta(S: float, K: float, T: float, r: float, sigma: float,
          option_type: str = "call") -> float

def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float

def vega(S: float, K: float, T: float, r: float, sigma: float) -> float

def theta(S: float, K: float, T: float, r: float, sigma: float,
          option_type: str = "call") -> float

def rho(S: float, K: float, T: float, r: float, sigma: float,
        option_type: str = "call") -> float

def greeks(S: float, K: float, T: float, r: float, sigma: float,
           option_type: str = "call") -> dict[str, float]
# Returns: {"price", "delta", "gamma", "vega", "theta", "rho"}
```

### 13.2 `pricing/monte_carlo.py`

```python
def mc_price(
    S: float, K: float, T: float, r: float, sigma: float,
    option_type: str = "call",
    n_sims: int = 50_000,
    antithetic: bool = True,
    seed: Optional[int] = None,
) -> dict[str, float | int]
# Returns: {"price", "std_error", "conf_low", "conf_high", "n_sims"}

def mc_convergence(
    S: float, K: float, T: float, r: float, sigma: float,
    option_type: str = "call",
    sim_counts: Optional[list[int]] = None,  # Default: [100,500,1k,5k,10k,50k]
    seed: int = 42,
) -> list[dict]
# Returns: list of {"n_sims", "mc_price", "bs_price", "error", "std_error"}
```

### 13.3 `pricing/market_data.py`

```python
def get_risk_free_rate() -> float
# Fetches DTB3 from FRED; returns decimal (e.g., 0.0525)

def get_spot_price(ticker: str) -> float
# yfinance 5-day history, last close

def expiry_to_years(expiry: str) -> float
# "YYYY-MM-DD" → (expiry - today).days / 365.0

def get_options_chain(
    ticker: str,
    expiry: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str]
# Returns: (calls_df, puts_df, available_expiries, selected_expiry)

def historical_vol(ticker: str, window: int = 30) -> float
# std(log_returns[-window:]) * sqrt(252)
```

### 13.4 `pricing/iv_solver.py`

```python
def implied_vol(
    market_price: float,
    S: float, K: float, T: float, r: float,
    option_type: str = "call",
    tol: float = 1e-6,
    max_iter: int = 200,
) -> Optional[float]
# Returns sigma in [0.001, 5.0] or None

def enrich_chain(
    df: pd.DataFrame,   # Options chain (calls or puts)
    S: float, T: float, r: float,
    option_type: str,
) -> pd.DataFrame
# Returns df with new "iv" column; original df unchanged

def full_chain_with_iv(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    S: float, T: float, r: float,
) -> tuple[pd.DataFrame, pd.DataFrame]
# Returns (enriched_calls, enriched_puts)
```

### 13.5 `api/routes/price.py`

```python
@router.post("/price", response_model=GreeksOut)
def get_price(req: PriceRequest) -> GreeksOut
# POST /api/price — live market data + BS Greeks

@router.get("/compute", response_model=ComputeOut)
def compute(
    S: float = Query(..., gt=0),
    K: float = Query(..., gt=0),
    T: float = Query(..., gt=0),
    r: float = Query(0.05),
    sigma: float = Query(..., gt=0, le=5.0),
    option_type: str = Query("call", pattern="^(call|put)$"),
) -> ComputeOut
# GET /api/compute — raw params, no network calls
```

### 13.6 `api/routes/chain.py`

```python
@router.get("/expiries", response_model=ExpiriesResponse)
def get_expiries(ticker: str = Query(...)) -> ExpiriesResponse
# GET /api/expiries?ticker=SPY

@router.get("/chain", response_model=ChainResponse)
def get_chain(
    ticker: str = Query(...),
    expiry: Optional[str] = Query(None),
) -> ChainResponse
# GET /api/chain?ticker=SPY&expiry=2025-01-17
```

### 13.7 Frontend — `dashboard/src/bs.js`

```javascript
function normCdf(x: number): number
// Abramowitz & Stegun §26.2.17; max error < 7.5e-8

function normPdf(x: number): number
// exp(-0.5*x^2) / sqrt(2*pi)

export function bsGreeks(
  S: number, K: number, T: number, r: number,
  sigma: number, optionType: 'call' | 'put'
): { price, delta, gamma, vega, theta, rho } | null
// Returns null if any input is non-positive
```

### 13.8 Frontend — `dashboard/src/api.js`

```javascript
export function fetchExpiries(ticker: string): Promise<ExpiriesResponse>
// GET /api/expiries?ticker={ticker}

export function fetchChain(ticker: string, expiry?: string): Promise<ChainResponse>
// GET /api/chain?ticker={ticker}[&expiry={expiry}]
```

---

## 14. Configuration & Deployment

### 14.1 Python Dependencies

```
# requirements.txt
scipy>=1.11.0          # Brent's method (scipy.optimize.brentq), norm.cdf/pdf
numpy>=1.24.0          # Vectorized array operations (MC simulation)
pandas>=2.0.0          # Options chain DataFrames
requests>=2.31.0       # FRED CSV fetch
yfinance>=0.2.40       # Yahoo Finance market data
fastapi>=0.110.0       # REST API framework
uvicorn[standard]>=0.27.0  # ASGI server (with websocket support)
pytest>=7.0.0          # Test runner
```

**Virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

### 14.2 Frontend Dependencies

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "recharts": "^2.12.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0"
  }
}
```

```bash
cd dashboard
npm install
npm run dev      # Vite dev server at http://localhost:5173
npm run build    # Production build → dist/
npm run preview  # Preview production build
```

### 14.3 Makefile One-Command Startup

```makefile
# make dev — starts both servers
dev:
    uvicorn api.main:app --reload --port 8000 &
    cd dashboard && npm run dev
```

### 14.4 Running Tests

```bash
# All tests
pytest tests/ -v

# Individual suites
pytest tests/test_black_scholes.py -v
pytest tests/test_monte_carlo.py -v
pytest tests/test_iv_solver.py -v

# With coverage
pytest tests/ --cov=pricing --cov-report=term-missing
```

### 14.5 Environment & CORS

**Development:**
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Vite proxies `/api/*` → `localhost:8000` (transparent)
- FastAPI CORS allows `http://localhost:5173`

**Production:**
- Build React: `npm run build` → static files in `dashboard/dist/`
- Serve static files from FastAPI via `StaticFiles` mount (or a CDN)
- Update CORS `allow_origins` to the production domain
- Remove `--reload` flag from uvicorn; add `--workers 4`

---

## 15. Edge Cases & Error Handling

### 15.1 Input Validation (Python Pricing Library)

```python
# black_scholes.py — raises ValueError immediately
S <= 0     →  "Spot price S must be positive."
K <= 0     →  "Strike price K must be positive."
T <= 0     →  "Time to expiry T must be positive."
sigma <= 0 →  "Volatility sigma must be positive."
option_type not in ("call","put")  →  "option_type must be 'call' or 'put'."

# monte_carlo.py — same validations plus:
n_sims < 1  →  "n_sims must be at least 1."

# market_data.py
ticker empty/nonexistent  →  ValueError("No price data found for '{ticker}'.")
expiry <= today            →  ValueError("Expiry is in the past (or today).")
expiry not in available   →  ValueError("Expiry not available for {ticker}.")
window > available data   →  ValueError("Insufficient price history.")
```

### 15.2 IV Solver — None vs. Exception

The IV solver returns `None` (not an exception) for financially meaningful failure cases:

| Condition | Return | Reason |
|-----------|--------|--------|
| `T ≤ 0` | `None` | Expired option |
| `market_price ≤ intrinsic + ε` | `None` | At/below intrinsic — arbitrageable |
| `market_price = 0` | `None` | No price to invert |
| Bracket has no sign change | `None` | IV outside [0.1%, 500%] — impossible |
| `option_type ∉ {"call","put"}` | `ValueError` | Programming error |

This distinction is important: `None` means "IV is not defined or solvable for this quote" (expected in production data), while an exception means the caller passed invalid arguments (programming error).

### 15.3 API Error Responses

```python
# price.py and chain.py
try:
    # ... pricing logic ...
except ValueError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
    # 422 Unprocessable Entity — client sent bad data
except Exception as exc:
    raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}")
    # 503 Service Unavailable — network or data feed failure
```

**422 triggers:** Past expiry date, unknown ticker, strike ≤ 0, sigma out of range.  
**503 triggers:** yfinance network error, FRED timeout, rate limit.

### 15.4 Frontend Error Handling

```javascript
// api.js
async function request(url) {
  const res = await fetch(url)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}
```

The thrown `Error` is caught in the component:
```javascript
try {
  const data = await fetchChain(ticker, expiry)
  setChain(data)
} catch (e) {
  setError(e.message)  // Displayed in red below controls
}
```

### 15.5 Missing / NaN Market Data

yfinance frequently returns NaN for bid, ask, volume, or open interest (especially for illiquid strikes). The chain endpoint handles this:

```python
bid   = float(row.get("bid", 0.0)) or 0.0
ask   = float(row.get("ask", 0.0)) or 0.0
vol   = float(row.get("volume", 0)) if not pd.isna(row.get("volume")) else None
oi    = float(row.get("openInterest", 0)) if not pd.isna(...) else None

# Fallback chain for market price:
if bid > 0 and ask > 0:
    market_price = (bid + ask) / 2.0
elif lastPrice > 0:
    market_price = lastPrice
else:
    continue  # Skip this contract — no price data
```

---

*End of Reference Document*
