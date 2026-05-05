"""
Market Data — Phase 3
=====================
Fetches live market data needed for options pricing:
  - Spot price via yfinance
  - Risk-free rate (3-month T-bill) from FRED (no API key required)
  - Full options chain (calls + puts) via yfinance

The FRED DTB3 series (3-Month Treasury Bill: Secondary Market Rate) is the
standard risk-free rate proxy used in academic and practitioner settings.
"""

from datetime import datetime, date
from typing import Optional

import pandas as pd
import requests
import yfinance as yf


FRED_DTB3_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"


def get_risk_free_rate() -> float:
    """
    Fetch the most recent 3-month T-bill rate from FRED.

    Returns the rate as a decimal (e.g., 5.25% → 0.0525).
    The public CSV endpoint requires no API key.
    FRED marks missing observations with "."; we skip those.
    """
    resp = requests.get(FRED_DTB3_URL, timeout=10)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    for line in reversed(lines[1:]):  # skip header, walk backwards for latest value
        parts = line.split(",")
        if len(parts) == 2 and parts[1].strip() not in (".", ""):
            return float(parts[1]) / 100.0
    raise ValueError("Could not parse a valid rate from FRED DTB3 data.")


def get_spot_price(ticker: str) -> float:
    """
    Fetch the most recent closing price for a ticker via yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "SPY", "AAPL")

    Returns:
        Most recent closing price as a float.
    """
    t = yf.Ticker(ticker.upper())
    hist = t.history(period="5d")
    if hist.empty:
        raise ValueError(f"No price data found for ticker '{ticker}'.")
    return float(hist["Close"].iloc[-1])


def expiry_to_years(expiry: str) -> float:
    """
    Convert an expiry date string (YYYY-MM-DD) to time-to-expiry in years.

    Uses calendar days / 365. Raises ValueError if the expiry is in the past.
    """
    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    today = date.today()
    days = (expiry_date - today).days
    if days <= 0:
        raise ValueError(f"Expiry '{expiry}' is in the past (or today).")
    return days / 365.0


def get_options_chain(
    ticker: str,
    expiry: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str]:
    """
    Fetch the options chain for a ticker via yfinance.

    Args:
        ticker: Stock ticker symbol
        expiry: Expiry date (YYYY-MM-DD). If None, uses the nearest available expiry.

    Returns:
        (calls_df, puts_df, available_expiries, selected_expiry)

    The DataFrames include: contractSymbol, strike, lastPrice, bid, ask,
    volume, openInterest, impliedVolatility (yfinance's own estimate).
    """
    t = yf.Ticker(ticker.upper())
    available = list(t.options)
    if not available:
        raise ValueError(f"No options data found for ticker '{ticker}'.")

    if expiry is None:
        expiry = available[0]
    elif expiry not in available:
        raise ValueError(
            f"Expiry '{expiry}' not available for {ticker}. "
            f"Available: {available[:5]}{'...' if len(available) > 5 else ''}"
        )

    chain = t.option_chain(expiry)
    return chain.calls, chain.puts, available, expiry
