import React, { useState } from "react";
import "./PlannerForm.css";

export function PlannerForm() {
  const [goal, setGoal] = useState("");
  const [proposals, setProposals] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setProposals(null);

    try {
      const response = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate strategies");
      }

      const data = await response.json();
      setProposals(data.proposals);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="planner-container">
      <h1>Options Strategy Planner</h1>

      <form onSubmit={handleSubmit} className="planner-form">
        <div className="form-group">
          <label htmlFor="goal">What's your investment goal?</label>
          <textarea
            id="goal"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g., hedge my 100 shares against a 10% drop, generate income from my SPY holding, reduce my cost basis..."
            rows={4}
            disabled={loading}
          />
        </div>

        <button type="submit" disabled={loading || !goal.trim()}>
          {loading ? "Planning strategies..." : "Generate Strategies"}
        </button>
      </form>

      {error && <div className="error-message">Error: {error}</div>}

      {proposals && proposals.length > 0 && (
        <div className="proposals-container">
          <h2>Proposed Strategies</h2>

          {proposals.map((proposal, idx) => (
            <StrategyCard key={idx} proposal={proposal} index={idx + 1} />
          ))}
        </div>
      )}

      {proposals && proposals.length === 0 && !loading && (
        <div className="info-message">No strategies generated. Try a different goal.</div>
      )}
    </div>
  );
}

function StrategyCard({ proposal, index }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className={`strategy-card ${proposal.verified ? "verified" : "unverified"}`}>
      <div className="strategy-header">
        <h3>
          Strategy {index}: {proposal.strategy_name}
        </h3>
        <span className={`verify-badge ${proposal.verified ? "valid" : "invalid"}`}>
          {proposal.verified ? "✓ Verified" : "⚠ Needs Review"}
        </span>
      </div>

      <div className="strategy-rationale">
        <p>{proposal.rationale}</p>
      </div>

      <div className="strategy-metrics">
        <MetricBox label="Net Cost" value={`$${proposal.net_cost.toFixed(2)}`} />
        <MetricBox
          label="Max Gain"
          value={proposal.max_gain == null ? "Unbounded" : `$${proposal.max_gain.toFixed(2)}`}
        />
        <MetricBox label="Max Loss" value={`$${proposal.max_loss.toFixed(2)}`} />
      </div>

      <div className="strategy-greeks">
        <h4>Net Greeks</h4>
        <div className="greeks-grid">
          {Object.entries(proposal.net_greeks).map(([key, value]) => (
            <div key={key} className="greek">
              <span className="greek-label">{key.toUpperCase()}</span>
              <span className="greek-value">{value.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="strategy-legs">
        <h4>Legs</h4>
        <table className="legs-table">
          <thead>
            <tr>
              <th>Side</th>
              <th>Type</th>
              <th>Strike</th>
              <th>Expiry</th>
            </tr>
          </thead>
          <tbody>
            {proposal.legs.map((leg, idx) => (
              <tr key={idx}>
                <td className={`side ${leg.side}`}>{leg.side.toUpperCase()}</td>
                <td>{leg.option_type.toUpperCase()}</td>
                <td>${leg.strike.toFixed(2)}</td>
                <td>{leg.expiry}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {proposal.violations && proposal.violations.length > 0 && (
        <div className="violations">
          <h4>⚠ Violations</h4>
          <ul>
            {proposal.violations.map((v, idx) => (
              <li key={idx}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      <button
        className="details-toggle"
        onClick={() => setShowDetails(!showDetails)}
      >
        {showDetails ? "Hide Payoff Chart" : "Show Payoff Chart"}
      </button>

      {showDetails && <PayoffChart proposal={proposal} />}
    </div>
  );
}

function MetricBox({ label, value }) {
  return (
    <div className="metric-box">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

function PayoffChart({ proposal }) {
  // Simple payoff diagram showing P&L at different spot prices
  // For now, just show a placeholder
  return (
    <div className="payoff-chart">
      <p>📊 Payoff diagram would show profit/loss at different SPY prices</p>
      <p style={{ fontSize: "0.9em", color: "#999" }}>
        Max Gain: {proposal.max_gain == null ? "Unbounded" : `$${proposal.max_gain.toFixed(2)}`} | Max Loss: ${proposal.max_loss.toFixed(2)}
      </p>
    </div>
  );
}
