"""
Implied Volatility Solver — Phase 3
=====================================
Given an observed market price, find the volatility sigma such that
Black-Scholes(sigma) = market_price.

Why Brent's method?
  - Newton-Raphson requires Vega != 0 and can diverge for deep OTM options.
  - Pure bisection is robust but slow (linear convergence).
  - Brent's method combines bisection (guaranteed bracket) with inverse
    quadratic interpolation (superlinear convergence near the root).
    It's the standard choice for production IV solvers.

The volatility smile/skew:
  If BS were a perfect model, IV would be flat across strikes. In practice,
  OTM puts have higher IV than ATM options (the "volatility skew"), and both
  wings can be elevated (the "volatility smile"). This reflects fat tails in
  real return distributions and asymmetric demand for crash protection.
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .black_scholes import bs_price


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "call",
    tol: float = 1e-6,
    max_iter: int = 200,
) -> Optional[float]:
    """
    Solve for implied volatility using Brent's method.

    Args:
        market_price : Observed mid-market price of the option
        S            : Current spot price
        K            : Strike price
        T            : Time to expiry in years
        r            : Risk-free rate (continuously compounded)
        option_type  : "call" or "put"
        tol          : Convergence tolerance on sigma (1e-6 = 0.0001% vol)
        max_iter     : Maximum Brent iterations

    Returns:
        Implied volatility as a decimal (e.g., 0.25 = 25%), or None if:
          - T <= 0 (expired option)
          - market_price is at or below intrinsic value (no valid IV exists)
          - The price is outside the solvable range [0.1%, 500%] vol bracket
    """
    option_type = option_type.lower().strip()
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'.")
    if T <= 0:
        return None

    # Intrinsic value is a lower bound on a valid option price.
    # A price at or below intrinsic implies zero or negative time value,
    # which no positive volatility can produce.
    discount = np.exp(-r * T)
    if option_type == "call":
        intrinsic = max(S - K * discount, 0.0)
    else:
        intrinsic = max(K * discount - S, 0.0)

    if market_price <= intrinsic + 1e-8:
        return None

    def objective(sigma: float) -> float:
        return bs_price(S, K, T, r, sigma, option_type) - market_price

    low_vol, high_vol = 1e-3, 5.0  # 0.1% to 500% annualized vol

    try:
        if objective(low_vol) * objective(high_vol) > 0:
            # No sign change in the bracket — price is outside the solvable range
            return None
        iv = brentq(objective, low_vol, high_vol, xtol=tol, maxiter=max_iter)
        return float(iv)
    except (ValueError, RuntimeError):
        return None


def enrich_chain(
    df: pd.DataFrame,
    S: float,
    T: float,
    r: float,
    option_type: str,
) -> pd.DataFrame:
    """
    Add a Brent-method implied volatility column to an options chain DataFrame.

    Uses the bid-ask midpoint as the market price. Falls back to lastPrice
    when bid/ask is unavailable or zero (illiquid contracts).

    Args:
        df          : Options chain DataFrame (calls or puts) from yfinance
        S           : Current spot price
        T           : Time to expiry in years
        r           : Risk-free rate
        option_type : "call" or "put"

    Returns:
        Copy of df with an additional 'iv' column (None where unsolvable).
    """
    df = df.copy()

    def _iv_for_row(row: pd.Series) -> Optional[float]:
        bid = row.get("bid", 0.0) or 0.0
        ask = row.get("ask", 0.0) or 0.0
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
        else:
            mid = row.get("lastPrice", 0.0) or 0.0
        if mid <= 0:
            return None
        return implied_vol(mid, S, row["strike"], T, r, option_type)

    df["iv"] = df.apply(_iv_for_row, axis=1)
    return df


def full_chain_with_iv(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    S: float,
    T: float,
    r: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Enrich both legs of an options chain with implied volatility.

    Args:
        calls : Calls DataFrame from yfinance
        puts  : Puts DataFrame from yfinance
        S     : Spot price
        T     : Time to expiry in years
        r     : Risk-free rate

    Returns:
        (enriched_calls, enriched_puts) — both DataFrames with 'iv' column.
    """
    enriched_calls = enrich_chain(calls, S, T, r, option_type="call")
    enriched_puts = enrich_chain(puts, S, T, r, option_type="put")
    return enriched_calls, enriched_puts
