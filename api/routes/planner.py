"""
FastAPI endpoints for the options strategy planner.

POST /api/plan — Submit a natural language goal, get strategy proposals
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from agents.planner import run_planner_agent
from agents.verifier import verify_proposal
from pricing.models import StrategyProposal, RiskConstraints

router = APIRouter()


class PlanRequest(BaseModel):
    """Request body for strategy planning."""
    goal: str
    constraints: Optional[dict] = None


class ProposalResponse(BaseModel):
    """Single strategy proposal response."""
    strategy_name: str
    legs: list
    net_cost: float
    max_gain: float
    max_loss: float
    breakeven: list
    net_greeks: dict
    rationale: str
    verified: bool
    violations: list = []


class PlanResponse(BaseModel):
    """Response with strategy proposals."""
    success: bool
    proposals: List[ProposalResponse]
    error: Optional[str] = None


@router.post("/plan", response_model=PlanResponse)
async def plan_strategy(request: PlanRequest):
    """
    Generate options strategies for a natural language goal.

    Takes a goal like "hedge my 100 shares against a 10% drop" and returns
    1-3 strategy proposals with full Greeks and P&L.

    Each proposal is verified against risk constraints.
    """

    try:
        # Run planner agent
        planner_result = run_planner_agent(request.goal, max_iterations=8)

        if not planner_result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Planner failed: {planner_result.get('error')}"
            )

        proposals_raw = planner_result.get("proposals", [])
        if not proposals_raw:
            raise HTTPException(
                status_code=400,
                detail="No proposals generated"
            )

        # Parse and verify proposals
        proposals_response = []
        constraints = RiskConstraints(**(request.constraints or {}))

        for proposal_data in proposals_raw:
            if isinstance(proposal_data, str):
                import json
                proposal_data = json.loads(proposal_data)

            try:
                # Create StrategyProposal object
                proposal = StrategyProposal(**proposal_data)

                # Verify against constraints
                verification = verify_proposal(proposal, constraints, "SPY")

                proposals_response.append(ProposalResponse(
                    strategy_name=proposal.strategy_name,
                    legs=proposal.legs,
                    net_cost=proposal.net_cost,
                    max_gain=proposal.max_gain,
                    max_loss=proposal.max_loss,
                    breakeven=proposal.breakeven,
                    net_greeks=proposal.net_greeks,
                    rationale=proposal.rationale,
                    verified=verification.valid,
                    violations=verification.violations,
                ))
            except Exception as e:
                # Skip malformed proposals
                print(f"Error processing proposal: {e}")
                continue

        return PlanResponse(
            success=True,
            proposals=proposals_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
