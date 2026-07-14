"""
MCP Server for Options Pricing Engine
======================================
Wraps the existing quantitative options pricing functions as Claude MCP tools.

This server makes the pricing engine conversational by exposing:
  - get_greeks: Compute Black-Scholes Greeks for a single option
  - get_implied_vol: Solve for implied volatility from market price
  - get_chain_snapshot: Fetch full options chain (with 10-min cache to avoid rate limits)
  - price_strategy: Sum Greeks/P&L across multi-leg strategies, with exact payoff-at-expiry analysis
  - validate_trade: Check strategy against risk constraints
"""

import asyncio
import json
import logging
from datetime import datetime, date
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from pricing.black_scholes import greeks as bs_greeks
from pricing.iv_solver import implied_vol as solve_iv
from pricing.market_data import (
    get_spot_price,
    get_risk_free_rate,
    get_options_chain,
    expiry_to_years,
    historical_vol,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTRACT_MULTIPLIER = 100

# Cache for get_chain_snapshot, keyed by (ticker, expiry)
_chain_cache: dict = {}
_chain_cache_ttl = 600  # 10 minutes


def _get_cached_chain(cache_key: tuple) -> Optional[dict]:
    """Retrieve chain from cache if fresh, else None."""
    if cache_key in _chain_cache:
        cached_at, data = _chain_cache[cache_key]
        if (datetime.now() - cached_at).total_seconds() < _chain_cache_ttl:
            return data
    return None


def _set_cached_chain(cache_key: tuple, data: dict) -> None:
    """Store chain in cache with timestamp."""
    _chain_cache[cache_key] = (datetime.now(), data)


def _serialize_chain(ticker: str, calls_df, puts_df, available_expiries: list, selected_expiry: str) -> dict:
    """Convert chain DataFrames to JSON-serializable format."""

    def _row_dict(row) -> dict:
        return {
            "strike": float(row.get("strike", 0)),
            "bid": float(row["bid"]) if row.get("bid") else None,
            "ask": float(row["ask"]) if row.get("ask") else None,
            "lastPrice": float(row["lastPrice"]) if row.get("lastPrice") is not None else None,
            "volume": int(row["volume"]) if row.get("volume") is not None else 0,
            "openInterest": int(row["openInterest"]) if row.get("openInterest") is not None else 0,
            "impliedVolatility": float(row["impliedVolatility"]) if row.get("impliedVolatility") else None,
        }

    calls = [_row_dict(row) for _, row in calls_df.iterrows()]
    puts = [_row_dict(row) for _, row in puts_df.iterrows()]

    return {
        "ticker": ticker,
        "calls": calls,
        "puts": puts,
        "available_expiries": available_expiries,
        "selected_expiry": selected_expiry,
    }


def _is_leg_covered(leg: dict, all_legs: list) -> bool:
    """
    Check if a short leg is covered (i.e. the position has bounded, defined risk).

    A short call is covered if there's a long call at the same expiry (any
    strike — this is what makes a vertical call spread risk-defined) or a
    long stock position (a covered call).

    A short put is covered if there's a long put at the same expiry (any
    strike — a vertical put spread).
    """
    if leg.get("side", "long").lower() == "long":
        return True

    expiry = leg["expiry"]
    option_type = leg.get("option_type", "call").lower()

    for other in all_legs:
        if other is leg or other.get("side", "").lower() != "long" or other["expiry"] != expiry:
            continue
        other_type = other.get("option_type", "").lower()
        if option_type == "call" and other_type in ("call", "stock"):
            return True
        if option_type == "put" and other_type == "put":
            return True

    return False


# ---------------------------------------------------------------------------
# Payoff-at-expiry analysis
#
# Stock and option payoffs are piecewise-linear in the terminal underlying
# price S_T, with slope changes ("kinks") only at each option's strike.
# So the exact max gain/loss/breakeven of any combination can be found by
# evaluating P&L at S_T=0, at every strike present, and at a point beyond
# the highest strike to detect whether the position is unbounded above.
# ---------------------------------------------------------------------------

def _leg_payoff_dollars(leg: dict, S_T: float) -> float:
    """Signed dollar payoff of one leg if the underlying settles at S_T at expiry."""
    side = leg.get("side", "long").lower()
    option_type = leg.get("option_type", "call").lower()
    strike = float(leg.get("strike", 0))
    quantity = int(leg.get("quantity", 1))
    sign = 1.0 if side == "long" else -1.0

    if option_type == "stock":
        # quantity = number of shares (not contracts)
        return sign * S_T * quantity
    elif option_type == "call":
        return sign * max(S_T - strike, 0.0) * quantity * CONTRACT_MULTIPLIER
    elif option_type == "put":
        return sign * max(strike - S_T, 0.0) * quantity * CONTRACT_MULTIPLIER
    else:
        raise ValueError(f"Unknown option_type '{option_type}' for leg {leg}")


def _pnl_at(legs: list, S_T: float, net_cost: float) -> float:
    """Total strategy P&L if underlying settles at S_T at expiry."""
    return sum(_leg_payoff_dollars(leg, S_T) for leg in legs) - net_cost


def _analyze_payoff(legs: list, net_cost: float, spot: float) -> dict:
    """
    Compute exact max gain, max loss, and breakeven price(s) via piecewise-linear
    payoff analysis. max_gain is None if the strategy has unbounded upside
    (e.g. a protective put's long stock leg).
    """
    strikes = sorted({float(leg["strike"]) for leg in legs if leg.get("option_type") in ("call", "put")})
    reference = max(strikes + [spot]) if (strikes or spot) else spot
    cap = reference * 3.0

    sample_points = sorted(set([0.0] + strikes + [cap]))
    pnl_values = [(sp, _pnl_at(legs, sp, net_cost)) for sp in sample_points]

    # Slope of the outermost (highest-price) segment tells us whether gain is unbounded.
    (s_last, pnl_last) = pnl_values[-1]
    (s_prev, pnl_prev) = pnl_values[-2]
    upper_slope = (pnl_last - pnl_prev) / (s_last - s_prev) if s_last != s_prev else 0.0
    unbounded_gain = upper_slope > 1e-9

    pnl_only = [v for _, v in pnl_values]
    max_gain = None if unbounded_gain else round(max(pnl_only), 2)
    max_loss = round(-min(pnl_only), 2) if min(pnl_only) < 0 else 0.0

    # Breakeven: linear interpolation between consecutive sample points where P&L crosses zero.
    breakevens = []
    for (s0, v0), (s1, v1) in zip(pnl_values, pnl_values[1:]):
        if v0 == 0:
            breakevens.append(round(s0, 2))
        elif (v0 < 0) != (v1 < 0):
            be = s0 + (0 - v0) * (s1 - s0) / (v1 - v0)
            breakevens.append(round(be, 2))
    if pnl_values[-1][1] == 0:
        breakevens.append(round(pnl_values[-1][0], 2))

    return {
        "max_gain": max_gain,
        "max_loss": max_loss,
        "breakeven": sorted(set(breakevens)),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_get_greeks(ticker: str, strike: float, expiry: str, option_type: str, sigma: Optional[float] = None) -> dict:
    """
    Compute Black-Scholes Greeks for a single option.

    If sigma is not provided, uses 30-day historical volatility.
    """
    try:
        ticker = ticker.upper()
        option_type = option_type.lower()

        spot = get_spot_price(ticker)
        rate = get_risk_free_rate()
        T = expiry_to_years(expiry)

        if sigma is None:
            sigma = historical_vol(ticker, window=30)

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
            **g,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_get_implied_vol(ticker: str, strike: float, expiry: str, option_type: str, market_price: float) -> dict:
    """Solve for implied volatility from a market price."""
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
                "error": f"Could not solve for IV: price ${market_price} is at or below intrinsic value",
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

    Returns calls and puts with strikes, bid/ask, implied vols, open interest.
    Uses a 10-minute cache (keyed by ticker + expiry) to avoid rate-limiting yfinance.
    """
    try:
        ticker = ticker.upper()
        cache_key = (ticker, expiry)

        cached = _get_cached_chain(cache_key)
        if cached is not None:
            logger.info(f"Using cached chain for {ticker} (expiry={expiry})")
            return {"success": True, "cached": True, **cached}

        calls_df, puts_df, available, selected = get_options_chain(ticker, expiry)

        chain_data = _serialize_chain(ticker, calls_df, puts_df, available, selected)
        _set_cached_chain(cache_key, chain_data)

        return {"success": True, "cached": False, **chain_data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_price_strategy(legs: list, ticker: str = "SPY") -> dict:
    """
    Compute net P&L and Greeks for a multi-leg strategy.

    Each leg is a dict: {side, strike, expiry, option_type, quantity}.
    side: "long" or "short". For option legs, quantity is number of contracts
    (100 shares each). For a "stock" leg, quantity is number of shares.

    Returns net cost, exact max gain/loss/breakeven (via payoff-at-expiry
    analysis), and aggregate per-share Greeks scaled to the position size.
    """
    try:
        ticker = ticker.upper()
        spot = get_spot_price(ticker)
        rate = get_risk_free_rate()
        sigma = historical_vol(ticker, window=30)

        net_cost = 0.0
        net_greeks = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
        naked_shorts = []

        for leg in legs:
            side = leg.get("side", "long").lower()
            option_type = leg.get("option_type", "call").lower()
            quantity = int(leg.get("quantity", 1))
            sign = 1.0 if side == "long" else -1.0

            if option_type == "stock":
                # Stock: price = spot per share, delta = 1/share, no gamma/vega/theta/rho.
                net_cost += sign * spot * quantity
                net_greeks["delta"] += sign * quantity
            else:
                strike = float(leg["strike"])
                expiry = leg["expiry"]
                T = expiry_to_years(expiry)
                g = bs_greeks(spot, strike, T, rate, sigma, option_type)

                net_cost += sign * g["price"] * quantity * CONTRACT_MULTIPLIER
                for greek_key in net_greeks:
                    net_greeks[greek_key] += sign * g[greek_key] * quantity * CONTRACT_MULTIPLIER

                if side == "short" and not _is_leg_covered(leg, legs):
                    naked_shorts.append(f"{option_type} @ {strike}")

        payoff = _analyze_payoff(legs, net_cost, spot)

        return {
            "success": True,
            "net_cost": round(net_cost, 2),
            "net_greeks": {k: round(v, 4) for k, v in net_greeks.items()},
            "max_gain": payoff["max_gain"],
            "max_loss": payoff["max_loss"],
            "breakeven": payoff["breakeven"],
            "warnings": (
                ["Detected naked short legs: " + ", ".join(naked_shorts)]
                if naked_shorts else []
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_validate_trade(
    legs: list,
    max_loss_usd: float = 5000,
    min_dte: int = 7,
    min_oi: int = 100,
    ticker: str = "SPY",
) -> dict:
    """
    Validate a strategy against risk constraints.

    Checks:
      1. Max loss <= limit (computed via exact payoff analysis)
      2. All legs have >= min_dte days to expiration
      3. All option legs have >= min_oi open interest
      4. No naked short legs
    """
    try:
        ticker = ticker.upper()
        violations = []

        chain_result = tool_get_chain_snapshot(ticker)
        if not chain_result.get("success"):
            return {"success": False, "error": "Could not fetch chain for validation"}

        calls = {c["strike"]: c for c in chain_result.get("calls", [])}
        puts = {p["strike"]: p for p in chain_result.get("puts", [])}

        for leg in legs:
            option_type = leg.get("option_type", "call").lower()
            side = leg.get("side", "long").lower()

            if option_type == "stock":
                continue  # Stock has no expiry or open interest to check.

            strike = float(leg["strike"])
            expiry = leg["expiry"]

            dte = (datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days
            if dte < min_dte:
                violations.append(f"{option_type} @ {strike} expires in {dte} days (min: {min_dte})")

            book = calls if option_type == "call" else puts
            contract = book.get(strike)
            if contract:
                oi = contract.get("openInterest", 0)
                if oi < min_oi:
                    violations.append(f"{option_type.capitalize()} @ {strike} has OI {oi} (min: {min_oi})")
            else:
                violations.append(f"{option_type.capitalize()} @ {strike} not found in chain")

            if side == "short" and not _is_leg_covered(leg, legs):
                violations.append(f"Short {option_type} @ {strike} is naked (not covered)")

        strategy_result = tool_price_strategy(legs, ticker)
        if strategy_result.get("success"):
            max_loss = strategy_result.get("max_loss", 0)
            if max_loss > max_loss_usd:
                violations.append(f"Max loss ${max_loss:.2f} exceeds limit ${max_loss_usd:.2f}")

        return {
            "success": True,
            "valid": len(violations) == 0,
            "violations": violations,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# MCP server wiring
# ---------------------------------------------------------------------------

server = Server("options-pricing-engine")

LEG_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "side": {"type": "string", "enum": ["long", "short"]},
        "strike": {"type": "number"},
        "expiry": {"type": "string", "description": "YYYY-MM-DD"},
        "option_type": {"type": "string", "enum": ["call", "put", "stock"]},
        "quantity": {"type": "integer", "default": 1},
    },
    "required": ["side", "strike", "expiry", "option_type"],
}


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
            description="Fetch full options chain with bid/ask/IV/OI (cached 10 min per ticker+expiry)",
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
            description="Compute net cost, exact max gain/loss/breakeven, and net Greeks for a multi-leg strategy",
            inputSchema={
                "type": "object",
                "properties": {
                    "legs": {
                        "type": "array",
                        "description": "List of legs: {side, strike, expiry, option_type, quantity}",
                        "items": LEG_ITEM_SCHEMA,
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
                        "items": LEG_ITEM_SCHEMA,
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


_TOOL_DISPATCH = {
    "get_greeks": tool_get_greeks,
    "get_implied_vol": tool_get_implied_vol,
    "get_chain_snapshot": tool_get_chain_snapshot,
    "price_strategy": tool_price_strategy,
    "validate_trade": tool_validate_trade,
}


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info(f"Tool called: {name} with args: {arguments}")

    tool_fn = _TOOL_DISPATCH.get(name)
    if tool_fn is None:
        result = {"success": False, "error": f"Unknown tool: {name}"}
    else:
        result = tool_fn(**arguments)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        logger.info("Options Pricing MCP Server started")
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
