"""
Options Pricing Engine
======================
A from-scratch implementation of quantitative options pricing models.

Modules
-------
black_scholes   Closed-form BS price and all five Greeks (Phase 1)
monte_carlo     GBM simulation pricer with antithetic variance reduction (Phase 2)
market_data     Live spot price, risk-free rate, and options chain via yfinance/FRED (Phase 3)
iv_solver       Implied volatility solver using Brent's method (Phase 3)
"""

from .black_scholes import bs_price, greeks, delta, gamma, vega, theta, rho
from .monte_carlo import mc_price, mc_convergence
from .iv_solver import implied_vol, enrich_chain, full_chain_with_iv
from .market_data import get_risk_free_rate, get_spot_price, get_options_chain, expiry_to_years

__all__ = [
    # Phase 1
    "bs_price", "greeks", "delta", "gamma", "vega", "theta", "rho",
    # Phase 2
    "mc_price", "mc_convergence",
    # Phase 3
    "implied_vol", "enrich_chain", "full_chain_with_iv",
    "get_risk_free_rate", "get_spot_price", "get_options_chain", "expiry_to_years",
]
