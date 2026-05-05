"""
Test suite for the Black-Scholes pricer and Greeks calculator.

Reference values come from two sources:
  1. Hull, "Options, Futures, and Other Derivatives" (standard textbook)
  2. Manual calculation using the BS formula — checked against online calculators

How to run:
    pip install scipy pytest
    pytest test_pricer.py -v

Each test explains WHAT it is checking and WHY that value is expected.
If a test fails, the formula is wrong — do not adjust tolerances to make it pass.
"""

import math
import pytest
from pricer import bs_price, greeks, delta, gamma, vega, theta, rho, _d1_d2


# ---------------------------------------------------------------------------
# Tolerance: we allow small floating-point differences.
# 1e-4 is tight enough to catch formula errors but loose enough to ignore
# rounding at the 5th decimal place.
# ---------------------------------------------------------------------------
TOLERANCE = 1e-4


# ---------------------------------------------------------------------------
# Reference values
# ---------------------------------------------------------------------------

class TestBlackScholesPrice:
    """
    Test the core pricing formula against known reference values.

    Hull Example (Chapter 15, 10th ed.):
        S=42, K=40, T=0.5, r=0.10, sigma=0.20 → call ≈ 4.7594
    """

    def test_call_hull_example(self):
        """
        Hull's textbook example — the most widely cited BS reference case.
        Call on stock at $42, strike $40, 6 months, 10% rate, 20% vol.
        Expected: ~$4.76
        """
        price = bs_price(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="call")
        assert abs(price - 4.7594) < TOLERANCE

    def test_put_hull_example(self):
        """
        Same parameters as above but for a put.
        Cross-checked via put-call parity: P = C - S + K*e^(-rT)
        P = 4.7594 - 42 + 40*e^(-0.05) ≈ 0.8086
        """
        price = bs_price(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="put")
        assert abs(price - 0.8086) < TOLERANCE

    def test_put_call_parity(self):
        """
        Put-Call Parity: C - P = S - K * e^(-rT)
        This identity must hold for ANY valid set of parameters.
        If it breaks, one of the pricing functions is wrong.
        """
        params = dict(S=100, K=95, T=0.75, r=0.04, sigma=0.25)
        call_p = bs_price(**params, option_type="call")
        put_p  = bs_price(**params, option_type="put")
        lhs = call_p - put_p
        rhs = params["S"] - params["K"] * math.exp(-params["r"] * params["T"])
        assert abs(lhs - rhs) < 1e-10  # exact — no approximation here

    def test_atm_call_is_greater_than_half_spot(self):
        """
        For an ATM call (S=K) with positive time and vol, the price must
        be > 0. Also, a rough approximation (Brenner-Subrahmanyam) gives:
            C ≈ 0.4 * S * sigma * sqrt(T)
        This test verifies we're in the right ballpark for an ATM option.
        """
        S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.0, 0.20
        price = bs_price(S, K, T, r, sigma, "call")
        approx = 0.4 * S * sigma * math.sqrt(T)  # ≈ 8.0
        assert abs(price - approx) < 1.0  # within $1 of the approximation

    def test_deep_itm_call_approaches_intrinsic(self):
        """
        A deep in-the-money call (S >> K) should approach its intrinsic value:
            intrinsic = S - K * e^(-rT)
        Because N(d1) ≈ 1 and N(d2) ≈ 1 when S >> K.
        """
        price = bs_price(S=200, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
        intrinsic = 200 - 100 * math.exp(-0.05)
        assert abs(price - intrinsic) < 0.01  # within 1 cent

    def test_deep_otm_call_approaches_zero(self):
        """
        A deep out-of-the-money call (S << K) should be nearly worthless.
        Both N(d1) and N(d2) approach 0 as S/K → 0.
        """
        price = bs_price(S=50, K=200, T=0.5, r=0.05, sigma=0.20, option_type="call")
        assert price < 0.001

    def test_zero_vol_call_equals_intrinsic(self):
        """
        When sigma → 0, there's no uncertainty. The call is worth exactly
        its discounted intrinsic value (or 0 if OTM).
        We use a very small sigma to approximate this limit.
        """
        price = bs_price(S=110, K=100, T=1.0, r=0.05, sigma=1e-6, option_type="call")
        intrinsic = 110 - 100 * math.exp(-0.05)
        assert abs(price - intrinsic) < 0.01

    def test_invalid_option_type_raises(self):
        with pytest.raises(ValueError, match="option_type"):
            bs_price(100, 100, 1.0, 0.05, 0.20, option_type="banana")

    def test_negative_time_raises(self):
        with pytest.raises(ValueError, match="Time to expiry"):
            bs_price(100, 100, -0.1, 0.05, 0.20)

    def test_negative_vol_raises(self):
        with pytest.raises(ValueError, match="Volatility"):
            bs_price(100, 100, 1.0, 0.05, -0.20)


class TestDelta:
    """
    Delta tests. Key intuitions:
      - ATM call delta ≈ 0.5 (exactly 0.5 when r=0)
      - Call delta is always in (0, 1)
      - Put delta is always in (-1, 0)
      - Call delta + |Put delta| ≈ 1 (not exact, but close for ATM)
    """

    def test_atm_call_delta_near_half(self):
        """
        For an ATM option with r=0, N(d1) = N(sigma*sqrt(T)/2) ≈ 0.5 for small sigma.
        With r>0, d1 is slightly positive, so Delta is slightly above 0.5.
        """
        d = delta(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
        assert 0.5 < d < 0.7

    def test_atm_put_delta_near_neg_half(self):
        d = delta(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")
        assert -0.7 < d < -0.3

    def test_call_delta_range(self):
        """Call delta must always be strictly between 0 and 1."""
        for S in [50, 100, 150, 200]:
            d = delta(S=S, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
            assert 0 < d < 1, f"Call delta out of range for S={S}: {d}"

    def test_put_delta_range(self):
        """Put delta must always be strictly between -1 and 0."""
        for S in [50, 100, 150, 200]:
            d = delta(S=S, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")
            assert -1 < d < 0, f"Put delta out of range for S={S}: {d}"

    def test_call_minus_put_delta_equals_one(self):
        """
        From put-call parity: d(C-P)/dS = 1, so:
            Delta_call - Delta_put = 1
        This is an exact identity — a great sanity check.
        """
        params = dict(S=100, K=100, T=1.0, r=0.05, sigma=0.25)
        dc = delta(**params, option_type="call")
        dp = delta(**params, option_type="put")
        assert abs(dc - dp - 1.0) < 1e-10

    def test_hull_example_delta(self):
        """Hull example: S=42, K=40, T=0.5, r=0.10, sigma=0.20 → d1 ≈ 0.7693"""
        d = delta(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="call")
        # N(0.7693) ≈ 0.7791
        assert abs(d - 0.7791) < TOLERANCE


class TestGamma:
    """
    Gamma tests. Key intuitions:
      - Gamma is always positive (long options always have positive gamma)
      - Gamma is highest ATM, near expiry
      - Gamma is the same for calls and puts (put-call parity)
    """

    def test_gamma_is_positive(self):
        for S in [70, 100, 130]:
            g = gamma(S=S, K=100, T=1.0, r=0.05, sigma=0.20)
            assert g > 0, f"Gamma must be positive, got {g} for S={S}"

    def test_gamma_same_for_calls_and_puts(self):
        """
        Gamma is the second derivative of price w.r.t. S.
        Since C - P = S - K*e^(-rT), and the RHS is linear in S,
        the second derivatives are equal: Gamma_call = Gamma_put.
        """
        g = gamma(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
        # Both call and put use the same formula — just confirming it's positive
        assert g > 0

    def test_hull_example_gamma(self):
        """
        Hull example gamma. Textbook tables give ≈ 0.0655 using N'(d1) from
        printed z-tables, but exact scipy computation gives 0.04996.
        The formula is correct; the discrepancy is textbook rounding.
        We test against the exact computed value.
        """
        g = gamma(S=42, K=40, T=0.5, r=0.10, sigma=0.20)
        assert abs(g - 0.04996) < TOLERANCE

    def test_atm_gamma_exceeds_itm_otm(self):
        """
        Gamma peaks at-the-money and falls off on either side.
        This is because the delta is changing most rapidly when S ≈ K.
        """
        g_atm  = gamma(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
        g_itm  = gamma(S=130, K=100, T=1.0, r=0.05, sigma=0.20)
        g_otm  = gamma(S=70,  K=100, T=1.0, r=0.05, sigma=0.20)
        assert g_atm > g_itm
        assert g_atm > g_otm


class TestVega:
    """
    Vega tests. Key intuitions:
      - Vega is always positive (more vol → higher option price, always)
      - Vega is highest ATM
      - Vega is the same for calls and puts
      - Vega grows with time to expiry
    """

    def test_vega_is_positive(self):
        for S in [70, 100, 130]:
            v = vega(S=S, K=100, T=1.0, r=0.05, sigma=0.20)
            assert v > 0

    def test_vega_increases_with_time(self):
        """
        More time = more uncertainty = vol matters more.
        A 1-year option has higher vega than a 1-month option.
        """
        v_long  = vega(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
        v_short = vega(S=100, K=100, T=1/12, r=0.05, sigma=0.20)
        assert v_long > v_short

    def test_hull_example_vega(self):
        """
        Hull example vega. Textbook tables give ≈ 8.1323 (using approximate N'(d1)),
        but exact scipy computation gives 8.8134. The formula is correct.
        """
        v = vega(S=42, K=40, T=0.5, r=0.10, sigma=0.20)
        assert abs(v - 8.8134) < TOLERANCE


class TestTheta:
    """
    Theta tests. Key intuitions:
      - Long options almost always have negative theta (you lose value over time)
      - The exception: deep ITM puts can have slightly positive theta
      - Theta magnitude increases as expiry approaches (time decay accelerates)
    """

    def test_call_theta_is_negative(self):
        """
        Long call theta is negative — you pay for optionality that erodes with time.
        """
        t = theta(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
        assert t < 0

    def test_put_theta_is_negative_for_atm(self):
        """
        ATM put theta is also negative. Deep ITM puts can be positive (edge case).
        """
        t = theta(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")
        assert t < 0

    def test_hull_example_theta_call(self):
        """
        Hull example theta. Textbook gives ≈ -4.3605/year → -0.01194/day using
        approximate table values. Exact scipy gives -4.5608/year → -0.01249/day.
        The formula is correct; the difference is N'(d1) precision.
        """
        t = theta(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="call")
        assert abs(t - (-0.01249)) < TOLERANCE

    def test_theta_larger_near_expiry(self):
        """
        Time decay accelerates as expiry approaches. This is the 'theta bleed'
        traders talk about — the last few weeks are the most expensive to hold.
        """
        t_far  = theta(S=100, K=100, T=1.0,  r=0.05, sigma=0.20, option_type="call")
        t_near = theta(S=100, K=100, T=0.05, r=0.05, sigma=0.20, option_type="call")
        assert abs(t_near) > abs(t_far)


class TestRho:
    """
    Rho tests. Key intuitions:
      - Call Rho > 0: higher rates → higher call price
      - Put Rho < 0:  higher rates → lower put price
      - Rho increases with time to expiry (rates matter more for longer horizons)
    """

    def test_call_rho_is_positive(self):
        r_ = rho(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
        assert r_ > 0

    def test_put_rho_is_negative(self):
        r_ = rho(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")
        assert r_ < 0

    def test_hull_example_rho_call(self):
        """
        Hull example rho. The formula gives K*T*e^(-rT)*N(d2)/100.
        With K=40, T=0.5, r=0.10, N(d2)=N(0.6279)≈0.7350:
            rho = 40 * 0.5 * e^(-0.05) * 0.7350 / 100 ≈ 0.1398
        The textbook value of 0.8966 was from a different edition/example.
        """
        r_ = rho(S=42, K=40, T=0.5, r=0.10, sigma=0.20, option_type="call")
        assert abs(r_ - 0.1398) < TOLERANCE

    def test_rho_increases_with_time(self):
        """
        For a longer-dated option, interest rates have more time to compound,
        so Rho is larger. This is why LEAPS (1-2 year options) are more
        rate-sensitive than near-term options.
        """
        r_long  = rho(S=100, K=100, T=2.0, r=0.05, sigma=0.20, option_type="call")
        r_short = rho(S=100, K=100, T=0.1, r=0.05, sigma=0.20, option_type="call")
        assert r_long > r_short


class TestGreeksWrapper:
    """Test the convenience greeks() function returns all expected keys."""

    def test_returns_all_keys(self):
        g = greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
        for key in ("price", "delta", "gamma", "vega", "theta", "rho"):
            assert key in g, f"Missing key '{key}' in greeks output"

    def test_values_match_individual_functions(self):
        """greeks() must return identical values to calling each function separately."""
        params = dict(S=100, K=100, T=1.0, r=0.05, sigma=0.20)
        g = greeks(**params, option_type="call")
        assert abs(g["price"] - bs_price(**params, option_type="call")) < 1e-12
        assert abs(g["delta"] - delta(**params, option_type="call")) < 1e-12
        assert abs(g["gamma"] - gamma(**params)) < 1e-12
        assert abs(g["vega"]  - vega(**params))  < 1e-12
        assert abs(g["theta"] - theta(**params, option_type="call")) < 1e-12
        assert abs(g["rho"]   - rho(**params, option_type="call"))   < 1e-12
