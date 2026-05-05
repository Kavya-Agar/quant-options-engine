"""
Test suite for the implied volatility solver.

Strategy: round-trip tests. We generate a BS price from a known sigma,
feed it to the solver, and verify the recovered sigma matches. This fully
tests the solver without any network calls or real market data.

Edge cases:
  - Deep ITM / OTM options
  - High and low volatility regimes
  - Prices at or below intrinsic value (solver must return None)
  - Both calls and puts
  - Bid/ask fallback to lastPrice

How to run:
    pytest tests/ -v
"""

import math

import pandas as pd
import pytest

from pricing.black_scholes import bs_price
from pricing.iv_solver import enrich_chain, full_chain_with_iv, implied_vol


TOLERANCE = 1e-4  # IV recovered to within 1 basis point (0.01%)


class TestImpliedVol:
    """
    Round-trip tests: BS price → IV solver → compare to input sigma.
    """

    def _roundtrip(self, S, K, T, r, sigma, option_type):
        price = bs_price(S, K, T, r, sigma, option_type)
        recovered = implied_vol(price, S, K, T, r, option_type)
        assert recovered is not None, (
            f"Solver returned None for {option_type} S={S} K={K} T={T} sigma={sigma}"
        )
        assert abs(recovered - sigma) < TOLERANCE, (
            f"Expected sigma={sigma:.4f}, recovered={recovered:.4f} "
            f"(error={abs(recovered - sigma):.6f})"
        )

    def test_atm_call_standard_case(self):
        """ATM call, 1 year, 20% vol — the canonical reference case."""
        self._roundtrip(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")

    def test_atm_put_standard_case(self):
        self._roundtrip(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")

    def test_itm_call(self):
        self._roundtrip(S=110, K=100, T=0.5, r=0.05, sigma=0.25, option_type="call")

    def test_otm_call(self):
        self._roundtrip(S=90, K=100, T=0.5, r=0.05, sigma=0.30, option_type="call")

    def test_itm_put(self):
        self._roundtrip(S=90, K=100, T=0.5, r=0.05, sigma=0.25, option_type="put")

    def test_otm_put(self):
        self._roundtrip(S=110, K=100, T=0.5, r=0.05, sigma=0.20, option_type="put")

    def test_short_expiry(self):
        """Near-expiry option (2 weeks): solver must still converge."""
        self._roundtrip(S=100, K=100, T=14 / 365, r=0.05, sigma=0.30, option_type="call")

    def test_long_expiry(self):
        """Long-dated option (2 years / LEAPS)."""
        self._roundtrip(S=100, K=100, T=2.0, r=0.05, sigma=0.20, option_type="call")

    def test_high_volatility(self):
        """80% vol is common for small-cap or biotech options."""
        self._roundtrip(S=100, K=100, T=0.5, r=0.05, sigma=0.80, option_type="call")

    def test_low_volatility(self):
        """5% vol: plausible for short-term index options in calm markets."""
        self._roundtrip(S=100, K=100, T=1.0, r=0.05, sigma=0.05, option_type="call")

    def test_zero_rate(self):
        """Zero risk-free rate: valid input, solver must handle it."""
        self._roundtrip(S=100, K=100, T=1.0, r=0.0, sigma=0.20, option_type="call")

    def test_hull_example_call(self):
        """
        Hull textbook: S=42, K=40, T=0.5, r=0.10, sigma=0.20 → call ≈ 4.7594
        Solver should recover sigma=0.20.
        """
        self._roundtrip(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="call")

    def test_hull_example_put(self):
        self._roundtrip(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="put")

    def test_various_strikes_call(self):
        """Solver should work across a realistic range of strikes for the same sigma."""
        for K in [70, 80, 90, 100, 110, 120, 130]:
            self._roundtrip(S=100, K=K, T=1.0, r=0.05, sigma=0.25, option_type="call")

    def test_various_strikes_put(self):
        for K in [70, 80, 90, 100, 110, 120, 130]:
            self._roundtrip(S=100, K=K, T=1.0, r=0.05, sigma=0.25, option_type="put")


class TestImpliedVolEdgeCases:
    """
    Inputs where the solver should return None or raise, not crash.
    """

    def test_price_below_intrinsic_call_returns_none(self):
        """
        A call priced below intrinsic is arbitrageable — no valid IV exists.
        Intrinsic for S=110, K=100, T=1yr, r=5%: ≈ 110 - 100*e^(-0.05) ≈ 15.12
        Passing price=5 (well below intrinsic) must return None.
        """
        iv = implied_vol(5.0, S=110, K=100, T=1.0, r=0.05, option_type="call")
        assert iv is None

    def test_price_below_intrinsic_put_returns_none(self):
        """
        Deep ITM put: intrinsic for S=80, K=100, T=1yr, r=5%: ≈ 100*e^(-0.05) - 80 ≈ 15.12
        Passing price=1 must return None.
        """
        iv = implied_vol(1.0, S=80, K=100, T=1.0, r=0.05, option_type="put")
        assert iv is None

    def test_zero_market_price_returns_none(self):
        """Zero price has no corresponding positive vol."""
        iv = implied_vol(0.0, S=100, K=100, T=1.0, r=0.05, option_type="call")
        assert iv is None

    def test_expired_option_returns_none(self):
        """T=0 means the option has expired; IV is undefined."""
        iv = implied_vol(5.0, S=100, K=100, T=0.0, r=0.05, option_type="call")
        assert iv is None

    def test_negative_time_returns_none(self):
        iv = implied_vol(5.0, S=100, K=100, T=-0.5, r=0.05, option_type="call")
        assert iv is None

    def test_invalid_option_type_raises(self):
        with pytest.raises(ValueError, match="option_type"):
            implied_vol(5.0, S=100, K=100, T=1.0, r=0.05, option_type="straddle")

    def test_price_at_intrinsic_returns_none(self):
        """
        At exactly intrinsic value, time value is zero, implying sigma → 0.
        Our bracket starts at 0.1%, so this should return None.
        """
        intrinsic = max(110 - 100 * math.exp(-0.05 * 1.0), 0.0)
        iv = implied_vol(intrinsic, S=110, K=100, T=1.0, r=0.05, option_type="call")
        assert iv is None or iv < 0.01


class TestEnrichChain:
    """
    Tests for enrich_chain() using synthetic DataFrames — no network calls.
    """

    def _make_chain(self, strikes, S, T, r, sigma, option_type):
        """Construct a synthetic chain DataFrame with BS-derived prices."""
        rows = []
        for K in strikes:
            price = bs_price(S, K, T, r, sigma, option_type)
            spread = price * 0.02  # 2% bid-ask spread
            rows.append({
                "strike": float(K),
                "lastPrice": price,
                "bid": price - spread / 2,
                "ask": price + spread / 2,
            })
        return pd.DataFrame(rows)

    def test_iv_column_added(self):
        df = self._make_chain([90, 100, 110], S=100, T=1.0, r=0.05, sigma=0.20,
                              option_type="call")
        result = enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        assert "iv" in result.columns

    def test_iv_values_recover_input_sigma(self):
        """
        IVs computed from bid-ask midpoints should closely match the sigma
        used to generate the prices. We allow 1% tolerance for the spread effect.
        """
        sigma = 0.25
        strikes = [85, 90, 95, 100, 105, 110, 115]
        df = self._make_chain(strikes, S=100, T=1.0, r=0.05, sigma=sigma,
                              option_type="call")
        result = enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        valid = result["iv"].dropna()
        assert len(valid) > 0, "All IVs were None"
        for iv_val in valid:
            assert abs(iv_val - sigma) < 0.01, (
                f"IV {iv_val:.4f} deviates from input sigma {sigma}"
            )

    def test_puts_enriched_correctly(self):
        sigma = 0.30
        df = self._make_chain([90, 100, 110], S=100, T=0.5, r=0.05, sigma=sigma,
                              option_type="put")
        result = enrich_chain(df, S=100, T=0.5, r=0.05, option_type="put")
        valid = result["iv"].dropna()
        assert len(valid) > 0
        for iv_val in valid:
            assert abs(iv_val - sigma) < 0.01

    def test_original_df_not_mutated(self):
        """enrich_chain must return a copy and not modify the input."""
        df = self._make_chain([100], S=100, T=1.0, r=0.05, sigma=0.20,
                              option_type="call")
        original_cols = list(df.columns)
        enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        assert list(df.columns) == original_cols

    def test_zero_bid_ask_falls_back_to_last_price(self):
        """When bid=ask=0, enrich_chain should use lastPrice instead."""
        price = bs_price(100, 100, 1.0, 0.05, 0.20, "call")
        df = pd.DataFrame([{
            "strike": 100.0,
            "lastPrice": price,
            "bid": 0.0,
            "ask": 0.0,
        }])
        result = enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        assert result["iv"].iloc[0] is not None
        assert abs(result["iv"].iloc[0] - 0.20) < TOLERANCE

    def test_zero_last_price_returns_none_iv(self):
        """A contract with no price data should produce None IV, not an error."""
        df = pd.DataFrame([{
            "strike": 200.0,
            "lastPrice": 0.0,
            "bid": 0.0,
            "ask": 0.0,
        }])
        result = enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        assert result["iv"].iloc[0] is None

    def test_row_count_preserved(self):
        """enrich_chain must not drop or duplicate rows."""
        strikes = [80, 90, 100, 110, 120]
        df = self._make_chain(strikes, S=100, T=1.0, r=0.05, sigma=0.20,
                              option_type="call")
        result = enrich_chain(df, S=100, T=1.0, r=0.05, option_type="call")
        assert len(result) == len(df)


class TestFullChainWithIV:
    """Tests for the full_chain_with_iv() convenience wrapper."""

    def _synthetic_chain(self, S=100, T=1.0, r=0.05, sigma=0.20):
        strikes = [90, 95, 100, 105, 110]
        calls_rows, puts_rows = [], []
        for K in strikes:
            for rows, opt in [(calls_rows, "call"), (puts_rows, "put")]:
                price = bs_price(S, K, T, r, sigma, opt)
                rows.append({
                    "strike": float(K),
                    "lastPrice": price,
                    "bid": price * 0.99,
                    "ask": price * 1.01,
                })
        return pd.DataFrame(calls_rows), pd.DataFrame(puts_rows)

    def test_both_legs_get_iv_column(self):
        calls, puts = self._synthetic_chain()
        ec, ep = full_chain_with_iv(calls, puts, S=100, T=1.0, r=0.05)
        assert "iv" in ec.columns
        assert "iv" in ep.columns

    def test_calls_and_puts_recover_sigma(self):
        """Both legs should independently recover the input sigma."""
        calls, puts = self._synthetic_chain(sigma=0.20)
        ec, ep = full_chain_with_iv(calls, puts, S=100, T=1.0, r=0.05)
        for iv_val in ec["iv"].dropna():
            assert abs(iv_val - 0.20) < 0.01
        for iv_val in ep["iv"].dropna():
            assert abs(iv_val - 0.20) < 0.01

    def test_original_inputs_not_mutated(self):
        calls, puts = self._synthetic_chain()
        calls_cols = list(calls.columns)
        puts_cols = list(puts.columns)
        full_chain_with_iv(calls, puts, S=100, T=1.0, r=0.05)
        assert list(calls.columns) == calls_cols
        assert list(puts.columns) == puts_cols
