"""
Black-Scholes Options Pricer + Greeks Calculator
=================================================
Phase 1 of the Options Pricing Engine project.

The Black-Scholes model prices European options under these assumptions:
  - The underlying follows geometric Brownian motion (log-normal returns)
  - No dividends, no transaction costs, continuous trading
  - Constant risk-free rate and volatility over the option's life
  - The option can only be exercised at expiry (European-style)

Real markets violate every one of these assumptions — that's what makes
the model interesting. It's a useful benchmark, not a ground truth.

Parameters used throughout this module:
  S     : Current spot price of the underlying asset
  K     : Strike price of the option
  T     : Time to expiry in years  (e.g., 90 days → T = 90/365)
  r     : Risk-free interest rate, continuously compounded (e.g., 0.05 = 5%)
  sigma : Implied or historical volatility of the underlying (e.g., 0.2 = 20%)
"""

import math
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Core Black-Scholes formula
# ---------------------------------------------------------------------------

def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """
    Compute the intermediate quantities d1 and d2 used throughout Black-Scholes.

    d1 and d2 can be interpreted as follows:
      - N(d2) is the risk-neutral probability that the option expires in-the-money
      - N(d1) is the Delta of a call — the hedge ratio (shares needed to replicate the option)

    The formula:
        d1 = [ln(S/K) + (r + 0.5 * sigma^2) * T] / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)

    The term ln(S/K) captures how far in- or out-of-the-money the option is.
    The (r + 0.5*sigma^2)*T term is the risk-adjusted drift over time T.
    sigma*sqrt(T) is the total volatility accumulated over the option's life.
    """
    if T <= 0:
        raise ValueError("Time to expiry T must be positive.")
    if sigma <= 0:
        raise ValueError("Volatility sigma must be positive.")
    if S <= 0 or K <= 0:
        raise ValueError("Spot price S and strike K must be positive.")

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Compute the theoretical Black-Scholes price for a European call or put.

    Call formula:  C = S * N(d1) - K * e^(-rT) * N(d2)
    Put formula:   P = K * e^(-rT) * N(-d2) - S * N(-d1)

    Intuition for the call formula:
      - S * N(d1)         : expected value of receiving the stock if exercised
      - K * e^(-rT) * N(d2): present value of paying the strike if exercised
      The difference is what you'd pay today to lock in that exchange.

    Put-Call Parity (useful sanity check):
      C - P = S - K * e^(-rT)
    This must always hold for European options, regardless of model.

    Args:
        S           : Spot price
        K           : Strike price
        T           : Time to expiry in years
        r           : Risk-free rate (continuously compounded)
        sigma       : Volatility
        option_type : "call" or "put"

    Returns:
        Theoretical option price (float)
    """
    option_type = option_type.lower().strip()
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'.")

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    discount = math.exp(-r * T)  # present value factor: e^(-rT)

    if option_type == "call":
        price = S * norm.cdf(d1) - K * discount * norm.cdf(d2)
    else:
        # Put: profit when stock falls below K, so we use N(-d1), N(-d2)
        # N(-x) = 1 - N(x) by symmetry of the normal distribution
        price = K * discount * norm.cdf(-d2) - S * norm.cdf(-d1)

    return price


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------
# The Greeks measure how sensitive an option's price is to changes in its
# inputs. Traders use them to understand and hedge risk.
#
# Each Greek answers a specific question:
#   Delta  → "If spot moves $1, how much does my option move?"
#   Gamma  → "How much does my Delta change per $1 move in spot?"
#   Vega   → "How much does my option move per 1% change in vol?"
#   Theta  → "How much value do I lose each day just by waiting?"
#   Rho    → "How much does my option move per 1% change in rates?"
# ---------------------------------------------------------------------------

def delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Delta: rate of change of option price with respect to spot price.

    Call Delta ∈ (0, 1):   Deep ITM call → Delta ≈ 1 (moves like stock)
                            ATM call      → Delta ≈ 0.5
                            Deep OTM call → Delta ≈ 0 (barely moves)

    Put Delta ∈ (-1, 0):   Mirror image — deep ITM put → Delta ≈ -1

    Delta is also used as the hedge ratio: to delta-hedge 1 long call,
    short Delta shares of the underlying. The position is then
    "delta-neutral" — insensitive to small price moves.

    Formula:
        Call: Δ =  N(d1)
        Put:  Δ = N(d1) - 1   [equivalently, -N(-d1)]
    """
    option_type = option_type.lower().strip()
    d1, _ = _d1_d2(S, K, T, r, sigma)

    if option_type == "call":
        return norm.cdf(d1)
    elif option_type == "put":
        return norm.cdf(d1) - 1
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'.")


def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Gamma: rate of change of Delta with respect to spot price (second derivative
    of option price with respect to S).

    Gamma is the same for calls and puts (follows from put-call parity).

    Gamma is highest at-the-money and near expiry. This is why short-dated
    ATM options are the most "dangerous" — small moves cause large Delta shifts,
    meaning your hedge becomes stale quickly.

    A positive Gamma position benefits from large moves in either direction.
    A negative Gamma position (e.g., short options) suffers from large moves.

    Formula:
        Γ = N'(d1) / (S * sigma * sqrt(T))

    where N'(x) = φ(x) is the standard normal probability density function (PDF).
    """
    d1, _ = _d1_d2(S, K, T, r, sigma)
    phi_d1 = norm.pdf(d1)  # standard normal PDF evaluated at d1
    return phi_d1 / (S * sigma * math.sqrt(T))


def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Vega: rate of change of option price with respect to volatility.

    Vega is the same for calls and puts.

    Vega is highest for ATM options with long time to expiry. This makes
    intuitive sense: more time means more uncertainty, so volatility has
    a bigger impact. Deep ITM/OTM options have low Vega because their
    payoff profile is already more certain.

    Convention: Vega is often quoted as the price change per 1 percentage
    point change in vol (i.e., divide by 100). We return the raw value here.

    Formula:
        ν = S * N'(d1) * sqrt(T)
    """
    d1, _ = _d1_d2(S, K, T, r, sigma)
    phi_d1 = norm.pdf(d1)
    return S * phi_d1 * math.sqrt(T)


def theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Theta: rate of change of option price with respect to time (time decay).

    Theta is almost always negative for long options — you lose value as time
    passes, all else equal. This is called "time decay" or "theta bleed."

    Short options have positive Theta — you collect premium as time passes.
    The Gamma-Theta trade-off is fundamental: high Gamma (good) comes with
    high negative Theta (costly). You pay for the ability to profit from moves.

    Convention: Theta is typically quoted per calendar day, so we divide by 365.
    Some practitioners divide by 252 (trading days). Be consistent.

    Formula:
        Call: Θ = -[S * N'(d1) * sigma / (2*sqrt(T))] - r * K * e^(-rT) * N(d2)
        Put:  Θ = -[S * N'(d1) * sigma / (2*sqrt(T))] + r * K * e^(-rT) * N(-d2)
    """
    option_type = option_type.lower().strip()
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    phi_d1 = norm.pdf(d1)
    discount = math.exp(-r * T)

    # The first term is shared: the drag from time eroding optionality
    common = -(S * phi_d1 * sigma) / (2 * math.sqrt(T))

    if option_type == "call":
        th = common - r * K * discount * norm.cdf(d2)
    elif option_type == "put":
        th = common + r * K * discount * norm.cdf(-d2)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'.")

    # Convert from per-year to per-day (calendar days)
    return th / 365.0


def rho(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Rho: rate of change of option price with respect to the risk-free rate.

    Calls have positive Rho: higher rates increase call value because the
    present value of the strike payment decreases (you pay less in today's money).

    Puts have negative Rho: higher rates decrease put value for the same reason.

    Rho tends to matter more for long-dated options (LEAPS). For short-dated
    options, Rho is usually the least important Greek.

    Convention: Rho is often quoted per 1% (0.01) change in the rate,
    so we divide by 100 here.

    Formula:
        Call: ρ =  K * T * e^(-rT) * N(d2)  / 100
        Put:  ρ = -K * T * e^(-rT) * N(-d2) / 100
    """
    option_type = option_type.lower().strip()
    _, d2 = _d1_d2(S, K, T, r, sigma)
    discount = math.exp(-r * T)

    if option_type == "call":
        return K * T * discount * norm.cdf(d2) / 100.0
    elif option_type == "put":
        return -K * T * discount * norm.cdf(-d2) / 100.0
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'.")


# ---------------------------------------------------------------------------
# Convenience wrapper — all Greeks in one call
# ---------------------------------------------------------------------------

def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict:
    """
    Return all Greeks and the theoretical price in a single dict.

    This is the main entry point you'll call from the API layer.

    Returns a dict with keys:
        price, delta, gamma, vega, theta, rho
    """
    return {
        "price": bs_price(S, K, T, r, sigma, option_type),
        "delta": delta(S, K, T, r, sigma, option_type),
        "gamma": gamma(S, K, T, r, sigma),        # same for calls & puts
        "vega":  vega(S, K, T, r, sigma),          # same for calls & puts
        "theta": theta(S, K, T, r, sigma, option_type),
        "rho":   rho(S, K, T, r, sigma, option_type),
    }


# ---------------------------------------------------------------------------
# Quick demo — run this file directly to see sample output
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Standard reference case used in most textbooks:
    # ATM option, 1 year to expiry, 5% rate, 20% vol
    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.20

    print("=" * 55)
    print("  Black-Scholes Pricer — Reference Case")
    print("  S=100  K=100  T=1yr  r=5%  σ=20%")
    print("=" * 55)

    for opt in ("call", "put"):
        g = greeks(S, K, T, r, sigma, opt)
        print(f"\n  {opt.upper()}")
        print(f"    Price : {g['price']:>10.4f}")
        print(f"    Delta : {g['delta']:>10.4f}")
        print(f"    Gamma : {g['gamma']:>10.4f}")
        print(f"    Vega  : {g['vega']:>10.4f}")
        print(f"    Theta : {g['theta']:>10.4f}  (per day)")
        print(f"    Rho   : {g['rho']:>10.4f}  (per 1% rate move)")

    # Sanity check: put-call parity
    call_p = bs_price(S, K, T, r, sigma, "call")
    put_p  = bs_price(S, K, T, r, sigma, "put")
    parity = call_p - put_p
    expected = S - K * math.exp(-r * T)
    print(f"\n  Put-Call Parity check:")
    print(f"    C - P          = {parity:.6f}")
    print(f"    S - K*e^(-rT)  = {expected:.6f}")
    print(f"    Match: {abs(parity - expected) < 1e-10}")
    print("=" * 55)
