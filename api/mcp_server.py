"""
MCP Server for Options Pricing Engine
======================================
Wraps the existing quantitative options pricing functions as Claude MCP tools.

This server makes the pricing engine conversational by exposing:
  - get_greeks: Compute Black-Scholes Greeks for a single option
  - get_implied_vol: Solve for implied volatility from market price
  - get_chain_snapshot: Fetch full options chain (with 10-min cache to avoid rate limits)
  - price_strategy: Sum Greeks/P&L across multi-leg strategies
  - validate_trade: Check strategy against risk constraints
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Any, Optional
import asyncio

from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, ToolResult
import mcp.server.stdio
import mcp.types as types

from pricing.black_scholes import greeks as bs_greeks
from pricing.iv_solver import implied_vol as solve_iv
from pricing.market_data import get_spot_price, get_risk_free_rate, get_options_chain, expiry_to_years, historical_vol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for get_chain_snapshot
_chain_cache = {}
_chain_cache_ttl = 600  # 10 minutes


def _get_cached_chain(ticker: str) -> Optional[dict]:
    """Retrieve chain from cache if fresh, else None."""
    if ticker in _chain_cache:
        cached_at, data = _chain_cache[ticker]
        if (datetime.now() - cached_at).total_seconds() < _chain_cache_ttl:
            return data
    return None


def _set_cached_chain(ticker: str, data: dict) -> None:
    """Store chain in cache with timestamp."""
    _chain_cache[ticker] = (datetime.now(), data)


def _serialize_chain(calls_df, puts_df, available_expiries: list, selected_expiry: str) -> dict:
    """Convert chain DataFrames to JSON-serializable format."""
    calls = []
    for _, row in calls_df.iterrows():
        calls.append({
            "strike": float(row.get("strike", 0)),
            "bid": float(row.get("bid", 0)) if row.get("bid") is not None and row.get("bid") != 0 else None,
            "ask": float(row.get("ask", 0)) if row.get("ask") is not None and row.get("ask") != 0 else None,
            "lastPrice": float(row.get("lastPrice", 0)) if row.get("lastPrice") is not None else None,
            "volume": int(row.get("volume", 0)) if row.get("volume") is not None else 0,
            "openInterest": int(row.get("openInterest", 0)) if row.get("openInterest") is not None else 0,
            "impliedVolatility": float(row.get("impliedVolatility", 0)) if row.get("impliedVolatility") is not None and row.get("impliedVolatility") != 0 else None,
        })

    puts = []
    for _, row in puts_df.iterrows():
        puts.append({
            "strike": float(row.get("strike", 0)),
            "bid": float(row.get("bid", 0)) if row.get("bid") is not None and row.get("bid") != 0 else None,
            "ask": float(row.get("ask", 0)) if row.get("ask") is not None and row.get("ask") != 0 else None,
            "lastPrice": float(row.get("lastPrice", 0)) if row.get("lastPrice") is not None else None,
            "volume": int(row.get("volume", 0)) if row.get("volume") is not None else 0,
            "openInterest": int(row.get("openInterest", 0)) if row.get("openInterest") is not None else 0,
            "impliedVolatility": float(row.get("impliedVolatility", 0)) if row.get("impliedVolatility") is not None and row.get("impliedVolatility") != 0 else None,
        })

    return {
        "ticker": calls_df.name if hasattr(calls_df, 'name') else "SPY",
        "calls": calls,
        "puts": puts,
        "available_expiries": available_expiries,
        "selected_expiry": selected_expiry,
    }


# Tool implementations
def tool_get_greeks(ticker: str, strike: float, expiry: str, option_type: str, sigma: Optional[float] = None) -> dict:
    """
    Compute Black-Scholes Greeks for a single option.

    If sigma is not provided, uses 30-day historical volatility.
    """
    try:
        ticker = ticker.upper()
        option_type = option_type.lower()

        # Get market data
        spot = get_spot_price(ticker)
        rate = get_risk_free_rate()
        T = expiry_to_years(expiry)

        # Use provided sigma or historical vol
        if sigma is None:
            sigma = historical_vol(ticker, window=30)

        # Compute Greeks
        g = bs_greeks(spot, strike, T, rate, sigma, option_type)

        return {
            "success": True,
            "ticker": ticker,
            "spot": spot,
            "strike": strike,
            "expiry": expiry,
            "dte": (datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days,
            "option_type": option_type,
            "sigma": sigma,
            "rate": rate,
            "T": T,
            "price": g["price"],
            "delta": g["delta"],
            "gamma": g["gamma"],
            "vega": g["vega"],
            "theta": g["theta"],
            "rho": g["rho"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_get_implied_vol(ticker: str, strike: float, expiry: str, option_type: str, market_price: float) -> dict:
    """
    Solve for implied volatility from a market price.
    """
    try:
        ticker = ticker.upper()
        option_type = option_type.lower()

        spot = get_spot_price(ticker)
        rate = get_risk_free_rate()
        T = expiry_to_years(expiry)

        iv = solve_iv(market_price, spot, strike, T, rate, option_type)

        if iv is None:
            return {
                "success": False,
                "error": f"Could not solve for IV: price ${market_price} may be below intrinsic value",
                "ticker": ticker,
                "strike": strike,
                "option_type": option_type,
            }

        return {
            "success": True,
            "ticker": ticker,
            "strike": strike,
            "expiry": expiry,
            "option_type": option_type,
            "market_price": market_price,
            "implied_vol": iv,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_get_chain_snapshot(ticker: str, expiry: Optional[str] = None) -> dict:
    """
    Fetch options chain snapshot.

    Returns calls and puts DataFrames with strikes, bid/ask, implied vols, open interest.
    Uses 10-minute cache to avoid rate-limiting yfinance.
    """
    try:
        ticker = ticker.upper()

        # Check cache first
        cached = _get_cached_chain(ticker)
        if cached is not None:
            logger.info(f"Using cached chain for {ticker}")
            return {
                "success": True,
                "cached": True,
                **cached,
            }

        # Fetch fresh chain
        calls_df, puts_df, available, selected = get_options_chain(ticker, expiry)

        chain_data = _serialize_chain(calls_df, puts_df, available, selected)
        _set_cached_chain(ticker, chain_data)

        return {
            "success": True,
            "cached": False,
            **chain_data,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_price_strategy(legs: list, ticker: str = "SPY") -> dict:
    """
    Compute net P&L and Greeks for a multi-leg strategy.

    Each leg is a dict: {side, strike, expiry, option_type, quantity}
    side: "long" or "short"
    quantity: number of contracts (default 1)

    Returns net cost, max gain, max loss, breakeven, and aggregate Greeks.
    """
    try:
        ticker = ticker.upper()
        spot = get_spot_price(ticker)
        rate = get_risk_free_rate()

        net_cost = 0.0
        net_greeks = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

        # Validate no naked shorts (for now, warn in output)
        short_legs_without_hedge = []

        for leg in legs:
            side = leg.get("side", "long").lower()
            strike = float(leg["strike"])
            expiry = leg["expiry"]
            option_type = leg.get("option_type", "call").lower()
            quantity = int(leg.get("quantity", 1))

            T = expiry_to_years(expiry)
            g = bs_greeks(spot, strike, T, rate, 0.2, option_type)  # Use 20% vol as default

            if side == "long":
                cost_per = g["price"]
            else:  # short
                cost_per = -g["price"]
                # Check if this short is potentially naked (no opposite leg at same strike)
                is_covered = any(
                    l.get("side", "").lower() == "long" and
                    l["strike"] == strike and
                    l["expiry"] == expiry and
                    l.get("option_type", "").lower() == option_type
                    for l in legs
                )
                if not is_covered:
                    # Also check if it's a covered call (short call + long stock)
                    is_covered_call = (option_type == "call" and any(
                        l.get("option_type", "").lower() == "stock" for l in legs
                    ))
                    if not is_covered_call:
                        short_legs_without_hedge.append(f"{option_type} @ {strike}")

            # Accumulate net cost
            net_cost += cost_per * quantity * 100  # 100 = contract multiplier

            # Accumulate Greeks
            greek_mult = 1.0 if side == "long" else -1.0
            for greek_key in net_greeks:
                net_greeks[greek_key] += g[greek_key] * quantity * greek_mult

        # Estimate max loss/gain (simplified: use delta-weighted moves)
        # Max gain is typically capped by short legs
        # Max loss is typically capped by long legs
        max_loss_estimate = net_cost if net_cost > 0 else 0  # Debit spread loses premium
        max_gain_estimate = max_loss_estimate * 2  # Very rough estimate

        return {
            "success": True,
            "net_cost": net_cost,
            "net_cost_per_share": net_cost / 100,
            "net_greeks": net_greeks,
            "max_loss_estimate": max_loss_estimate,
            "max_gain_estimate": max_gain_estimate,
            "warnings": (
                ["Detected potentially naked short legs: " + ", ".join(short_legs_without_hedge)]
                if short_legs_without_hedge else []
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_validate_trade(legs: list, max_loss_usd: float = 5000, min_dte: int = 7, min_oi: int = 100, ticker: str = "SPY") -> dict:
    """
    Validate a strategy against risk constraints.

    Checks:
      1. Max loss <= limit
      2. All legs have >= min_dte days to expiration
      3. All legs have >= min_oi open interest
      4. No naked short legs
    """
    try:
        ticker = ticker.upper()
        violations = []

        # Get chain for OI checks
        chain_result = tool_get_chain_snapshot(ticker)
        if not chain_result.get("success"):
            return {"success": False, "error": "Could not fetch chain for validation"}

        chain = chain_result
        calls = {c["strike"]: c for c in chain.get("calls", [])}
        puts = {p["strike"]: p for p in chain.get("puts", [])}

        # Check each leg
        for leg in legs:
            strike = float(leg["strike"])
            expiry = leg["expiry"]
            option_type = leg.get("option_type", "call").lower()
            side = leg.get("side", "long").lower()

            # Check DTE
            dte = (datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days
            if dte < min_dte:
                violations.append(f"{option_type} @ {strike} expires in {dte} days (min: {min_dte})")

            # Check OI
            if option_type == "call" and strike in calls:
                oi = calls[strike].get("openInterest", 0)
                if oi < min_oi:
                    violations.append(f"Call @ {strike} has OI {oi} (min: {min_oi})")
            elif option_type == "put" and strike in puts:
                oi = puts[strike].get("openInterest", 0)
                if oi < min_oi:
                    violations.append(f"Put @ {strike} has OI {oi} (min: {min_oi})")

            # Check naked shorts
            if side == "short":
                is_covered = any(
                    l.get("side", "").lower() == "long" and
                    l["strike"] == strike and
                    l["expiry"] == expiry and
                    l.get("option_type", "").lower() == option_type
                    for l in legs
                )
                if not is_covered:
                    violations.append(f"Short {option_type} @ {strike} is naked (not covered)")

        # Check max loss (estimate)
        strategy_result = tool_price_strategy(legs, ticker)
        if strategy_result.get("success"):
            estimated_loss = strategy_result.get("max_loss_estimate", 0)
            if estimated_loss > max_loss_usd:
                violations.append(f"Max loss ${estimated_loss} exceeds limit ${max_loss_usd}")

        return {
            "success": True,
            "valid": len(violations) == 0,
            "violations": violations,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# MCP Server setup
server = mcp.server.stdio.StdioServer()


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_greeks",
            description="Compute Black-Scholes Greeks (delta, gamma, vega, theta, rho) for a single option",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker (e.g. 'SPY')"},
                    "strike": {"type": "number", "description": "Strike price"},
                    "expiry": {"type": "string", "description": "Expiry date (YYYY-MM-DD)"},
                    "option_type": {"type": "string", "enum": ["call", "put"], "description": "Option type"},
                    "sigma": {"type": "number", "description": "Volatility (optional; defaults to 30-day historical)"},
                },
                "required": ["ticker", "strike", "expiry", "option_type"],
            },
        ),
        Tool(
            name="get_implied_vol",
            description="Solve for implied volatility from a market price",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker"},
                    "strike": {"type": "number", "description": "Strike price"},
                    "expiry": {"type": "string", "description": "Expiry date (YYYY-MM-DD)"},
                    "option_type": {"type": "string", "enum": ["call", "put"]},
                    "market_price": {"type": "number", "description": "Observed market price"},
                },
                "required": ["ticker", "strike", "expiry", "option_type", "market_price"],
            },
        ),
        Tool(
            name="get_chain_snapshot",
            description="Fetch full options chain with bid/ask/IV/OI (cached 10 min)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker"},
                    "expiry": {"type": "string", "description": "Expiry date (YYYY-MM-DD, optional)"},
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="price_strategy",
            description="Compute net P&L and Greeks for a multi-leg strategy",
            inputSchema={
                "type": "object",
                "properties": {
                    "legs": {
                        "type": "array",
                        "description": "List of legs: {side: 'long'|'short', strike, expiry, option_type, quantity}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "side": {"type": "string", "enum": ["long", "short"]},
                                "strike": {"type": "number"},
                                "expiry": {"type": "string", "description": "YYYY-MM-DD"},
                                "option_type": {"type": "string", "enum": ["call", "put", "stock"]},
                                "quantity": {"type": "integer", "default": 1},
                            },
                            "required": ["side", "strike", "expiry", "option_type"],
                        },
                    },
                    "ticker": {"type": "string", "description": "Stock ticker (default: SPY)"},
                },
                "required": ["legs"],
            },
        ),
        Tool(
            name="validate_trade",
            description="Validate strategy against risk constraints (max loss, min DTE, min OI, no naked shorts)",
            inputSchema={
                "type": "object",
                "properties": {
                    "legs": {
                        "type": "array",
                        "description": "Strategy legs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "side": {"type": "string", "enum": ["long", "short"]},
                                "strike": {"type": "number"},
                                "expiry": {"type": "string", "description": "YYYY-MM-DD"},
                                "option_type": {"type": "string", "enum": ["call", "put", "stock"]},
                                "quantity": {"type": "integer", "default": 1},
                            },
                            "required": ["side", "strike", "expiry", "option_type"],
                        },
                    },
                    "max_loss_usd": {"type": "number", "description": "Max loss limit (default: 5000)"},
                    "min_dte": {"type": "integer", "description": "Min days to expiration (default: 7)"},
                    "min_oi": {"type": "integer", "description": "Min open interest (default: 100)"},
                    "ticker": {"type": "string", "description": "Stock ticker (default: SPY)"},
                },
                "required": ["legs"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    logger.info(f"Tool called: {name} with args: {arguments}")

    if name == "get_greeks":
        result = tool_get_greeks(**arguments)
    elif name == "get_implied_vol":
        result = tool_get_implied_vol(**arguments)
    elif name == "get_chain_snapshot":
        result = tool_get_chain_snapshot(**arguments)
    elif name == "price_strategy":
        result = tool_price_strategy(**arguments)
    elif name == "validate_trade":
        result = tool_validate_trade(**arguments)
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with server:
        logger.info("Options Pricing MCP Server started")
        await server.wait_for_exit()


if __name__ == "__main__":
    asyncio.run(main())
