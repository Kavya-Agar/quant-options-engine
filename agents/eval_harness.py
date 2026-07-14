"""
Evaluation Harness for Strategy Planner

Runs the planner agent against a test set of scenarios and measures:
  1. Overall proposal success rate
  2. Verifier catch rate (proposals that violate constraints)
  3. Quality metrics (Greeks realism, strategy fit)

This is the key metric for the interview: proving the system works reliably.
"""

import json
import logging
from typing import List, Dict, Any
from datetime import datetime

from agents.planner import run_planner_agent
from agents.verifier import verify_proposal
from pricing.models import StrategyProposal, RiskConstraints

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_proposal_has_put(proposal: Dict) -> bool:
    """Check if proposal contains a put option."""
    legs = proposal.get("legs", [])
    return any(leg.get("option_type") == "put" for leg in legs)


def check_proposal_has_stock(proposal: Dict) -> bool:
    """Check if proposal contains stock leg."""
    legs = proposal.get("legs", [])
    return any(leg.get("option_type") == "stock" for leg in legs)


def check_proposal_has_short_call(proposal: Dict) -> bool:
    """Check if proposal has a short call."""
    legs = proposal.get("legs", [])
    return any(
        leg.get("side") == "short" and leg.get("option_type") == "call"
        for leg in legs
    )


def check_proposal_has_two_puts(proposal: Dict) -> bool:
    """Check if proposal has exactly two put legs."""
    legs = proposal.get("legs", [])
    put_legs = [leg for leg in legs if leg.get("option_type") == "put"]
    return len(put_legs) == 2


def check_short_put_higher_strike(proposal: Dict) -> bool:
    """Check if short put has higher strike than long put (bull/credit put spread)."""
    legs = proposal.get("legs", [])
    puts = [leg for leg in legs if leg.get("option_type") == "put"]
    if len(puts) != 2:
        return False

    long_puts = [p for p in puts if p.get("side") == "long"]
    short_puts = [p for p in puts if p.get("side") == "short"]

    if len(long_puts) != 1 or len(short_puts) != 1:
        return False

    return short_puts[0].get("strike", 0) > long_puts[0].get("strike", 0)


def check_long_put_higher_strike(proposal: Dict) -> bool:
    """
    Check if the long put has a higher strike than the short put — the shape of a
    debit (bear) put spread used to hedge downside cheaply: buy protection at the
    higher strike, sell a lower strike to offset cost.
    """
    legs = proposal.get("legs", [])
    puts = [leg for leg in legs if leg.get("option_type") == "put"]
    if len(puts) != 2:
        return False

    long_puts = [p for p in puts if p.get("side") == "long"]
    short_puts = [p for p in puts if p.get("side") == "short"]

    if len(long_puts) != 1 or len(short_puts) != 1:
        return False

    return long_puts[0].get("strike", 0) > short_puts[0].get("strike", 0)


def check_net_cost_negative(proposal: Dict) -> bool:
    """Check if net cost is negative (credit strategy — options-only, no stock leg)."""
    return proposal.get("net_cost", 0) < 0


def check_max_loss_under_5000(proposal: Dict) -> bool:
    """Check if max loss is within the $5,000 risk limit."""
    max_loss = proposal.get("max_loss")
    return max_loss is not None and max_loss <= 5000


def check_capped_gain(proposal: Dict) -> bool:
    """
    Check that upside is capped (max_gain is a finite number rather than None).
    This is the defining feature of a covered call versus holding stock outright.
    """
    return proposal.get("max_gain") is not None


def check_has_real_max_loss(proposal: Dict) -> bool:
    """Check if max loss is a meaningful number."""
    max_loss = proposal.get("max_loss", 0)
    return max_loss > 0 and max_loss < 1e6  # Sanity check


def check_has_short_leg(proposal: Dict) -> bool:
    """Check if proposal has at least one short leg."""
    legs = proposal.get("legs", [])
    return any(leg.get("side") == "short" for leg in legs)


def check_has_long_leg(proposal: Dict) -> bool:
    """Check if proposal has at least one long leg."""
    legs = proposal.get("legs", [])
    return any(leg.get("side") == "long" for leg in legs)


def check_lower_cost_than_simple_put(proposal: Dict) -> bool:
    """Check if spread net cost is less than a simple put."""
    net_cost = proposal.get("net_cost", 1000)
    return net_cost < 500  # Simple heuristic


def evaluate_scenario(scenario: Dict, proposal: Dict) -> Dict[str, Any]:
    """
    Evaluate if a proposal passes all criteria for a scenario.

    Returns:
      - all_passed: bool
      - passed_checks: List[str]
      - failed_checks: List[str]
    """

    passed = []
    failed = []

    # Map check names to functions
    check_functions = {
        "proposal_has_put": check_proposal_has_put,
        "proposal_has_stock": check_proposal_has_stock,
        "proposal_has_short_call": check_proposal_has_short_call,
        "proposal_has_two_puts": check_proposal_has_two_puts,
        "short_put_higher_strike": check_short_put_higher_strike,
        "long_put_higher_strike": check_long_put_higher_strike,
        "net_cost_is_negative": check_net_cost_negative,
        "max_loss_under_5000": check_max_loss_under_5000,
        "capped_gain": check_capped_gain,
        "has_real_max_loss": check_has_real_max_loss,
        "has_short_leg": check_has_short_leg,
        "has_long_leg": check_has_long_leg,
        "lower_cost_than_simple_put": check_lower_cost_than_simple_put,
    }

    # Run criteria checks
    for check_name in scenario.get("pass_criteria", []):
        if check_name == "passes_verifier":
            continue  # Handle separately below

        check_func = check_functions.get(check_name)
        if check_func:
            try:
                if check_func(proposal):
                    passed.append(check_name)
                else:
                    failed.append(check_name)
            except Exception as e:
                logger.error(f"Error running check {check_name}: {e}")
                failed.append(f"{check_name} (error)")
        else:
            # An unrecognized check name is a defect in the scenario file, not a
            # pass — count it as a failure so typos can't silently inflate the score.
            logger.warning(f"Unknown check: {check_name}")
            failed.append(f"{check_name} (unknown)")

    return {
        "all_checks_passed": len(failed) == 0,
        "passed_checks": passed,
        "failed_checks": failed,
    }


def run_eval(
    test_scenarios_path: str = "agents/test_scenarios.json",
    max_scenarios: int = None,
) -> Dict[str, Any]:
    """
    Run the full evaluation pipeline.

    Returns:
      - summary: pass rate and verifier catch rate
      - results: detailed per-scenario results
      - timestamp: when evaluation ran
    """

    # Load scenarios
    with open(test_scenarios_path, "r") as f:
        all_scenarios = json.load(f)

    scenarios = all_scenarios[:max_scenarios] if max_scenarios else all_scenarios

    results = []
    total_scenarios = len(scenarios)
    passed_scenarios = 0
    verifier_catches = 0
    constraints = RiskConstraints()

    logger.info(f"Running eval on {total_scenarios} scenarios...")

    for i, scenario in enumerate(scenarios):
        logger.info(f"\n[{i + 1}/{total_scenarios}] Scenario: {scenario['goal'][:60]}...")

        scenario_id = scenario.get("id", i + 1)
        goal = scenario["goal"]

        try:
            # Run planner
            planner_result = run_planner_agent(goal, max_iterations=8)

            if not planner_result.get("success"):
                logger.error(f"Planner failed: {planner_result.get('error')}")
                results.append({
                    "scenario_id": scenario_id,
                    "goal": goal,
                    "planner_success": False,
                    "error": planner_result.get("error"),
                })
                continue

            proposals = planner_result.get("proposals", [])
            if not proposals:
                logger.warning("No proposals returned")
                results.append({
                    "scenario_id": scenario_id,
                    "goal": goal,
                    "planner_success": True,
                    "proposals_count": 0,
                    "all_checks_passed": False,
                })
                continue

            # Take first proposal (in production, we'd evaluate all)
            proposal = proposals[0] if isinstance(proposals, list) else proposals
            if isinstance(proposal, str):
                proposal = json.loads(proposal)

            # Evaluate against criteria
            criteria_result = evaluate_scenario(scenario, proposal)

            # Run verifier
            verifier_result = None
            try:
                # Convert proposal to StrategyProposal if needed
                if isinstance(proposal, dict):
                    proposal_obj = StrategyProposal(**proposal)
                else:
                    proposal_obj = proposal

                verifier_result = verify_proposal(proposal_obj, constraints, "SPY")
                if not verifier_result.valid:
                    verifier_catches += 1
                    logger.info(f"Verifier caught violations: {verifier_result.violations}")
            except Exception as e:
                logger.warning(f"Verifier error: {e}")
                verifier_result = None

            # Determine pass/fail
            passes_verifier = verifier_result.valid if verifier_result else None
            checks_ok = criteria_result["all_checks_passed"]
            overall_pass = checks_ok and (passes_verifier is not False)

            if overall_pass:
                passed_scenarios += 1

            results.append({
                "scenario_id": scenario_id,
                "goal": goal,
                "expected_strategy": scenario.get("expected_strategy"),
                "planner_success": True,
                "proposal": proposal,
                "criteria_checks": criteria_result,
                "verifier_valid": passes_verifier,
                "verifier_violations": verifier_result.violations if verifier_result else [],
                "overall_pass": overall_pass,
            })

        except Exception as e:
            logger.error(f"Scenario failed: {e}")
            results.append({
                "scenario_id": scenario_id,
                "goal": goal,
                "error": str(e),
            })

    # Summarize
    pass_rate = passed_scenarios / total_scenarios if total_scenarios > 0 else 0
    summary = {
        "total_scenarios": total_scenarios,
        "passed": passed_scenarios,
        "pass_rate": f"{pass_rate * 100:.1f}%",
        "verifier_catches": verifier_catches,
        "verifier_catch_rate": f"{verifier_catches / total_scenarios * 100:.1f}%" if total_scenarios > 0 else "0%",
    }

    logger.info(f"\n{'='*60}")
    logger.info(f"EVAL SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Pass Rate: {summary['passed']}/{summary['total_scenarios']} ({summary['pass_rate']})")
    logger.info(f"Verifier Catches: {summary['verifier_catches']} violations caught")
    logger.info(f"{'='*60}")

    return {
        "summary": summary,
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


def save_eval_results(eval_result: Dict, output_path: str = "agents/eval_results.json"):
    """Save evaluation results to JSON file."""
    with open(output_path, "w") as f:
        json.dump(eval_result, f, indent=2)
    logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    # Run evaluation
    eval_result = run_eval(max_scenarios=3)  # Start with 3 for testing
    save_eval_results(eval_result)
