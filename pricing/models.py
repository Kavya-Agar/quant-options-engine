"""
Pydantic models for options strategy representation.

Used by the planner and verifier agents to structure strategy proposals.
"""

from typing import List, Dict, Literal, Optional
from pydantic import BaseModel, Field


class Leg(BaseModel):
    """Single leg of an options strategy."""
    side: Literal["long", "short"]
    strike: float
    expiry: str  # "YYYY-MM-DD"
    option_type: Literal["call", "put", "stock"]
    quantity: int = Field(default=1, ge=1)


class StrategyProposal(BaseModel):
    """Complete strategy proposal with Greeks and P&L."""
    strategy_name: str  # "Protective Put", "Covered Call", "Vertical Spread", etc.
    legs: List[Leg]
    net_cost: float  # debit (positive) or credit (negative), in USD per share * 100
    max_gain: float  # maximum profit potential
    max_loss: float  # maximum loss potential
    breakeven: List[float]  # prices where profit = 0
    net_greeks: Dict[str, float]  # {delta, gamma, vega, theta, rho}
    rationale: str  # plain English explanation of the strategy


class RiskConstraints(BaseModel):
    """Risk constraints for strategy validation."""
    max_loss_usd: float = 5000.0
    min_dte: int = 7
    min_oi: int = 100
    no_naked_shorts: bool = True
    max_delta: float = 0.95
    min_delta: float = 0.05  # for short legs


class VerificationResult(BaseModel):
    """Result of strategy verification."""
    valid: bool
    violations: List[str] = Field(default_factory=list)
    suggestion: Optional['StrategyProposal'] = None


# Update forward reference
VerificationResult.model_rebuild()
