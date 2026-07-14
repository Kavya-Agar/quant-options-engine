"""
Options Strategy Planner Agent

Uses Claude to convert natural language goals into concrete multi-leg strategy proposals.
Calls MCP tools to fetch market data and compute Greeks/P&L.

Core loop:
  1. Parse user intent
  2. Fetch current chain snapshot
  3. Identify 2-3 candidate strategies
  4. Price each strategy using price_strategy tool
  5. Rank by fit to user's goal
  6. Return structured proposals
"""

import json
import logging
from typing import Optional
from datetime import datetime, date

from anthropic import Anthropic
from pricing.models import StrategyProposal, Leg, RiskConstraints

logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = Anthropic()

# System prompt for the planner agent
PLANNER_SYSTEM_PROMPT = """
You are an expert options strategy planner. Your job is to convert natural language
investment goals into concrete multi-leg options strategies.

## Your Capabilities
You have access to these tools:
1. get_chain_snapshot(ticker) — Fetch current options chain (bid/ask/IV/OI)
2. get_greeks(ticker, strike, expiry, option_type, sigma?) — Compute Greeks for a single option
3. price_strategy(legs, ticker?) — Calculate net P&L and Greeks across multiple legs
4. validate_trade(legs, max_loss_usd?, min_dte?, min_oi?, ticker?) — Check strategy against constraints
5. get_implied_vol(ticker, strike, expiry, option_type, market_price) — Solve for IV

## Supported Strategies (Pick 1)
- **Covered Call**: Long stock + short call. Income strategy, capped upside.
- **Protective Put**: Long stock + long put. Hedge against downside.
- **Vertical Spread**: Buy call/put + sell call/put at different strikes. Lower cost, defined risk.

## Critical Rules
1. Only propose SPY strategies (no multi-ticker spreads)
2. Maximum 4 legs per strategy
3. All short options must be covered or hedged (no naked shorts)
4. Always call price_strategy() to get real Greeks — do NOT hallucinate prices
5. Every Greek must come from an actual tool call
6. Strikes must exist in the chain (check bid/ask > 0)
7. Explain max loss, max gain, breakeven clearly

## Your Process

Step 1: Parse the user's intent
  - What asset do they own or want exposure to?
  - What's their goal? (hedge, income, reduce cost, speculate, lock in gains)
  - What's their risk tolerance? (max loss, time horizon, etc.)

Step 2: Fetch current market data
  - Call get_chain_snapshot(ticker) to see available strikes, expiries, IV, OI
  - Note: Prefer liquid strikes with OI > 100

Step 3: Identify candidate strategies (pick the 1-3 best fits)
  - Protective Put: if goal is hedge
  - Covered Call: if goal is income
  - Vertical Spread: if goal is reduce cost or risk

Step 4: Build each candidate
  - Select strikes based on user's risk profile
  - Ensure all legs exist in the chain (OI > 0)
  - Call price_strategy(legs) to get real P&L and Greeks
  - Document the rationale (why this strategy fits)

Step 5: Return a JSON response with all proposals

## Example Output Format

```json
{
  "proposals": [
    {
      "strategy_name": "Protective Put",
      "rationale": "Hedge 100 shares against 10% drop. Buy 90%-strike put (485) for $285 debit. Max loss locked at $1,285.",
      "legs": [
        {"side": "long", "strike": 500, "expiry": "2024-08-16", "option_type": "stock", "quantity": 1},
        {"side": "long", "strike": 485, "expiry": "2024-08-16", "option_type": "put", "quantity": 1}
      ],
      "net_cost": 285.00,
      "max_loss": 1285.00,
      "max_gain": 0,
      "breakeven": [500],
      "net_greeks": {"delta": 0.8, "gamma": 0.01, "vega": 0.1, "theta": -0.02, "rho": 0.0}
    }
  ]
}
```

Be precise, be cautious, and always verify Greeks from tools.
"""


def run_planner_agent(goal: str, max_iterations: int = 10) -> dict:
    """
    Run the planner agent for a user's goal.

    Returns a dict with:
      - proposals: list of StrategyProposal objects (as dicts)
      - messages: transcript of Claude's reasoning
      - success: bool
    """

    messages = []
    tools = [
        {
            "name": "get_chain_snapshot",
            "description": "Fetch options chain for a ticker (bid/ask/IV/OI)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker (e.g., 'SPY')"},
                    "expiry": {"type": "string", "description": "Optional expiry date (YYYY-MM-DD)"},
                },
                "required": ["ticker"],
            },
        },
        {
            "name": "get_greeks",
            "description": "Compute Black-Scholes Greeks for a single option",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "strike": {"type": "number"},
                    "expiry": {"type": "string", "description": "YYYY-MM-DD"},
                    "option_type": {"type": "string", "enum": ["call", "put"]},
                    "sigma": {"type": "number", "description": "Optional volatility"},
                },
                "required": ["ticker", "strike", "expiry", "option_type"],
            },
        },
        {
            "name": "price_strategy",
            "description": "Compute net P&L and Greeks for a multi-leg strategy",
            "input_schema": {
                "type": "object",
                "properties": {
                    "legs": {
                        "type": "array",
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
        },
        {
            "name": "validate_trade",
            "description": "Validate strategy against risk constraints",
            "input_schema": {
                "type": "object",
                "properties": {
                    "legs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "side": {"type": "string", "enum": ["long", "short"]},
                                "strike": {"type": "number"},
                                "expiry": {"type": "string"},
                                "option_type": {"type": "string", "enum": ["call", "put", "stock"]},
                                "quantity": {"type": "integer", "default": 1},
                            },
                            "required": ["side", "strike", "expiry", "option_type"],
                        },
                    },
                    "max_loss_usd": {"type": "number", "description": "Default: 5000"},
                    "min_dte": {"type": "integer", "description": "Default: 7"},
                    "min_oi": {"type": "integer", "description": "Default: 100"},
                    "ticker": {"type": "string", "description": "Default: SPY"},
                },
                "required": ["legs"],
            },
        },
        {
            "name": "get_implied_vol",
            "description": "Solve for implied volatility from market price",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "strike": {"type": "number"},
                    "expiry": {"type": "string", "description": "YYYY-MM-DD"},
                    "option_type": {"type": "string", "enum": ["call", "put"]},
                    "market_price": {"type": "number"},
                },
                "required": ["ticker", "strike", "expiry", "option_type", "market_price"],
            },
        },
    ]

    # Initial user message
    user_message = f"""
    Please create 1-3 options strategy proposals for this goal:

    {goal}

    Remember:
    1. Only SPY strategies
    2. Only covered calls, protective puts, or vertical spreads
    3. Always call price_strategy() to get real Greeks
    4. No hallucinated prices — verify everything with tools
    5. Explain max loss, max gain, and breakeven clearly

    When done, output a final JSON response with the proposals.
    """

    messages.append({"role": "user", "content": user_message})

    # Agentic loop
    for iteration in range(max_iterations):
        logger.info(f"Iteration {iteration + 1}")

        # Call Claude
        response = client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=4096,
            system=PLANNER_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Add assistant response to messages
        messages.append({"role": "assistant", "content": response.content})

        # Check if we're done (no more tool calls)
        if response.stop_reason == "end_turn":
            # Extract final JSON from response
            try:
                # Find the JSON in the response text
                for block in response.content:
                    if hasattr(block, "text"):
                        text = block.text
                        # Look for JSON object in the text
                        if "proposals" in text:
                            # Simple extraction: find { ... }
                            start = text.find("{")
                            end = text.rfind("}") + 1
                            if start >= 0 and end > start:
                                json_str = text[start:end]
                                proposals_data = json.loads(json_str)
                                return {
                                    "success": True,
                                    "proposals": proposals_data.get("proposals", []),
                                    "messages": messages,
                                }
                # If no JSON found, still return success with empty proposals
                return {
                    "success": True,
                    "proposals": [],
                    "messages": messages,
                    "note": "No JSON proposals found in response",
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                return {
                    "success": False,
                    "error": f"Failed to parse proposals: {e}",
                    "messages": messages,
                }

        # Handle tool use
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    logger.info(f"Tool call: {tool_name}")

                    # Call the tool (in a real implementation, this would be an RPC call)
                    try:
                        result = call_tool(tool_name, tool_input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                    except Exception as e:
                        logger.error(f"Tool error: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        })

            # Add tool results to messages
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            logger.warning(f"Unexpected stop reason: {response.stop_reason}")
            break

    return {
        "success": False,
        "error": "Max iterations reached without completion",
        "messages": messages,
    }


def call_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Call the pricing tools. In production, this would call the MCP server.
    For now, we'll import and call the functions directly.
    """

    if tool_name == "get_chain_snapshot":
        from api.mcp_server import tool_get_chain_snapshot
        return tool_get_chain_snapshot(**tool_input)

    elif tool_name == "get_greeks":
        from api.mcp_server import tool_get_greeks
        return tool_get_greeks(**tool_input)

    elif tool_name == "price_strategy":
        from api.mcp_server import tool_price_strategy
        return tool_price_strategy(**tool_input)

    elif tool_name == "validate_trade":
        from api.mcp_server import tool_validate_trade
        return tool_validate_trade(**tool_input)

    elif tool_name == "get_implied_vol":
        from api.mcp_server import tool_get_implied_vol
        return tool_get_implied_vol(**tool_input)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


if __name__ == "__main__":
    # Test the planner agent
    test_goal = "Hedge 100 shares of SPY against a 10% drop"
    print(f"\nPlanning for: {test_goal}\n")

    result = run_planner_agent(test_goal)

    print(f"Success: {result.get('success')}")
    if result.get("proposals"):
        print(f"Proposals: {json.dumps(result['proposals'], indent=2)}")
    if result.get("error"):
        print(f"Error: {result['error']}")
