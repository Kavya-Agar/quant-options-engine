"""
Strategy Verifier — Deterministic Risk Constraint Checker

Validates proposals against hard risk constraints:
  - Max loss limit
  - Min days to expiration
  - No naked short legs
  - Min open interest for liquidity

This is NOT an LLM — it's pure logic. This makes it auditable and reliable.
"""

import logging
from datetime import date, datetime
from typing import Optional

from pricing.models import StrategyProposal, Leg, RiskConstraints, VerificationResult
from api.mcp_server import tool_get_chain_snapshot

logger = logging.getLogger(__name__)


def days_to_expiry(expiry: str) -> int:
    """Compute days from today to expiry date."""
    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    return (expiry_date - date.today()).days


def is_leg_covered(leg: Leg, all_legs: list[Leg]) -> bool:
    """
    Check if a short leg is covered.

    A short is covered if:
      1. There's a matching long at the same strike/expiry/option_type, OR
      2. It's a covered call (short call + long stock)
    """

    if leg.side == "long":
        return True  # Long legs are always fine

    # Check for matching long leg
    for other_leg in all_legs:
        if (other_leg.side == "long" and
            other_leg.strike == leg.strike and
            other_leg.expiry == leg.expiry and
            other_leg.option_type == leg.option_type):
            return True

    # Check for covered call (short call + long stock)
    if leg.option_type == "call":
        for other_leg in all_legs:
            if (other_leg.side == "long" and
                other_leg.option_type == "stock"):
                return True

    return False


def get_chain_data(ticker: str) -> dict:
    """Fetch chain data from cache/API."""
    result = tool_get_chain_snapshot(ticker)
    if not result.get("success"):
        logger.error(f"Failed to get chain for {ticker}")
        return {}
    return result


def verify_proposal(proposal: StrategyProposal, constraints: RiskConstraints, ticker: str = "SPY") -> VerificationResult:
    """
    Verify a strategy proposal against risk constraints.

    Returns:
      - valid: True if all constraints passed
      - violations: List of constraint violations
      - suggestion: Revised proposal if possible (not implemented yet)
    """

    violations = []

    # Check 1: Max loss
    if proposal.max_loss > constraints.max_loss_usd:
        violations.append(
            f"Max loss ${proposal.max_loss:.0f} exceeds limit ${constraints.max_loss_usd:.0f}"
        )

    # Check 2: Min DTE for all legs
    for leg in proposal.legs:
        dte = days_to_expiry(leg.expiry)
        if dte < constraints.min_dte:
            violations.append(
                f"{leg.option_type.upper()} @{leg.strike} expires in {dte} days (min: {constraints.min_dte})"
            )

    # Check 3: No naked shorts
    if constraints.no_naked_shorts:
        for leg in proposal.legs:
            if leg.side == "short" and not is_leg_covered(leg, proposal.legs):
                violations.append(
                    f"Short {leg.option_type.upper()} @{leg.strike} is naked (not covered)"
                )

    # Check 4: Min OI for all legs
    chain_data = get_chain_data(ticker)
    if chain_data:
        calls_dict = {c["strike"]: c for c in chain_data.get("calls", [])}
        puts_dict = {p["strike"]: p for p in chain_data.get("puts", [])}

        for leg in proposal.legs:
            if leg.option_type == "stock":
                continue  # No OI check for stock

            if leg.option_type == "call":
                contract = calls_dict.get(leg.strike)
                if contract:
                    oi = contract.get("openInterest", 0)
                    if oi < constraints.min_oi:
                        violations.append(
                            f"Call @{leg.strike} has OI {oi} (min: {constraints.min_oi})"
                        )
                else:
                    violations.append(f"Call @{leg.strike} not found in chain")

            elif leg.option_type == "put":
                contract = puts_dict.get(leg.strike)
                if contract:
                    oi = contract.get("openInterest", 0)
                    if oi < constraints.min_oi:
                        violations.append(
                            f"Put @{leg.strike} has OI {oi} (min: {constraints.min_oi})"
                        )
                else:
                    violations.append(f"Put @{leg.strike} not found in chain")

    return VerificationResult(
        valid=len(violations) == 0,
        violations=violations,
        suggestion=None,  # TODO: implement revised proposal generation
    )


if __name__ == "__main__":
    # Test the verifier
    test_proposal = StrategyProposal(
        strategy_name="Protective Put",
        legs=[
            Leg(side="long", strike=500, expiry="2024-08-16", option_type="stock"),
            Leg(side="long", strike=485, expiry="2024-08-16", option_type="put"),
        ],
        net_cost=285.00,
        max_loss=1285.00,
        max_gain=0,
        breakeven=[500],
        net_greeks={"delta": 0.8, "gamma": 0.01, "vega": 0.1, "theta": -0.02, "rho": 0.0},
        rationale="Hedge against 10% downside",
    )

    constraints = RiskConstraints()
    result = verify_proposal(test_proposal, constraints, "SPY")

    print(f"Valid: {result.valid}")
    print(f"Violations: {result.violations}")
