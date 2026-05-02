# Quantitative Bitcoin 1-hour price-range forecasting engine.
#
# Basically:
#  - EWMA for vol (reactive to clustering)
#  - Student-t for the fat tails (BTC special)
#  - Monte Carlo simulation (10k paths)
#  - Adaptive calibration (learned from backtest)

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gammaln
from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional
import warnings

warnings.filterwarnings("ignore")

# Basic model configs
N_SIM          = 10_000   # 10k is usually enough for convergence
ALPHA          = 0.05     # 95% CI
MIN_DF         = 2.5      # student-t floor (anything lower is just too crazy)
MAX_DF         = 30.0     # basically gaussian at this point
SHRINK_LAMBDA  = 0.15     # shrink drift to zero to avoid over-betting on trends
CALIB_ALPHA    = 0.05     # learning rate for the scaling factor
CALIB_MIN      = 0.70
CALIB_MAX      = 1.80
EWMA_FAST      = 12       
EWMA_SLOW      = 26       
ROLL_WINDOWS   = [10, 20, 50]


#  Data classes
@dataclass
class VolatilityFeatures:
    sigma_fast:    float   # EWMA fast
    sigma_slow:    float   # EWMA slow
    sigma_roll10:  float
    sigma_roll20:  float
    sigma_roll50:  float
    atr:           float
    regime:        str     # 'calm' | 'medium' | 'volatile'
    df:            float   # estimated Student-t degrees of freedom


@dataclass
class ForecastResult:
    lower:   float
    upper:   float
    mu_est:  float
    sigma:   float
    df:      float
    regime:  str
    calib:   float


@dataclass
class BacktestMetrics:
    coverage:     float
    avg_width:    float
    winkler:      float
    n_samples:    int
    details:      List[Dict] = field(default_factory=list)

#  Feature engineering

def compute_log_returns(closes: np.ndarray) -> np.ndarray:
    """Vectorised log returns."""
    return np.diff(np.log(closes))


def ewma_volatility(returns: np.ndarray, span: int) -> float:
    """EWMA standard deviation (annualised to per-bar scale)."""
    alpha = 2.0 / (span + 1)
    weights = (1 - alpha) ** np.arange(len(returns) - 1, -1, -1)
    weights /= weights.sum()
    mu = np.dot(weights, returns)
    var = np.dot(weights, (returns - mu) ** 2)
    return float(np.sqrt(var))


def rolling_vol(returns: np.ndarray, window: int) -> float:
    if len(returns) < window:
        window = len(returns)
    return float(np.std(returns[-window:], ddof=1))


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                window: int = 14) -> float:
    """Average True Range (percentage of close)."""
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    atr_val = np.mean(tr[-window:]) if len(tr) >= window else np.mean(tr)
    return float(atr_val / closes[-1])   # percentage ATR


def estimate_df(returns: np.ndarray, window: int = 50) -> float:
    # Estimate Student-t degrees of freedom from excess kurtosis.
    # Excess kurtosis κ of t_ν is 6/(ν-4) for ν > 4.
    sample = returns[-window:] if len(returns) >= window else returns
    k = stats.kurtosis(sample, fisher=True)
    k = max(k, 0.01) # avoid zero div
    
    if k >= 6: # super fat tails
        df = MIN_DF
    elif k < 0.01:
        df = MAX_DF
    else:
        df = 6.0 / k + 4.0
    return float(np.clip(df, MIN_DF, MAX_DF))

def classify_regime(sigma_fast: float, sigma_slow: float, atr: float) -> str:
    # Simple ratio logic to see if things are heating up
    ratio = sigma_fast / (sigma_slow + 1e-12)
    if ratio > 1.5 or atr > 0.008:
        return "volatile"
    elif ratio < 0.75 and atr < 0.003:
        return "calm"
    return "medium"


def extract_features(closes: np.ndarray,
                     highs: np.ndarray,
                     lows: np.ndarray) -> VolatilityFeatures:
    ret = compute_log_returns(closes)
    sf   = ewma_volatility(ret, EWMA_FAST)
    ss   = ewma_volatility(ret, EWMA_SLOW)
    r10  = rolling_vol(ret, 10)
    r20  = rolling_vol(ret, 20)
    r50  = rolling_vol(ret, 50)
    atr  = compute_atr(highs, lows, closes)
    df   = estimate_df(ret)
    reg  = classify_regime(sf, ss, atr)
    return VolatilityFeatures(
        sigma_fast=sf, sigma_slow=ss,
        sigma_roll10=r10, sigma_roll20=r20, sigma_roll50=r50,
        atr=atr, regime=reg, df=df
    )

<<<<<<< Updated upstream

# ─────────────────────────────────────────────
#  Drift estimation with shrinkage
# ─────────────────────────────────────────────
=======
#  Drift estimation
>>>>>>> Stashed changes

def estimate_drift(returns: np.ndarray, window: int = 50) -> float:
    # Rolling mean of log returns, shrunk towards zero to
    # avoid overfitting short-period trends.
    sample = returns[-window:] if len(returns) >= window else returns
    raw_mu = float(np.mean(sample))
    return raw_mu * (1 - SHRINK_LAMBDA)

def regime_sigma_scale(regime: str) -> float:
    return {"calm": 0.85, "medium": 1.0, "volatile": 1.30}[regime]

<<<<<<< Updated upstream
=======
#  Monte Carlo with Jump Diffusion
>>>>>>> Stashed changes

def simulate_paths(
    last_price: float,
    mu: float,
    sigma: float,
    df: float,
    regime: str,
    calib_factor: float,
    n_sim: int = N_SIM,
    bootstrap_returns: Optional[np.ndarray] = None
) -> np.ndarray:
    # terminal prices after 1 bar.
    # 50% paths: Student-t GBM
    # 50% paths: Bootstrap resampling
    
    sig = sigma * regime_sigma_scale(regime) * calib_factor
    half = n_sim // 2

    # T-distribution paths
    z_t = stats.t.rvs(df=df, size=half)
    log_ret_t = mu + sig * z_t
    prices_t = last_price * np.exp(log_ret_t)

    # Bootstrap paths (real historical data)
    if bootstrap_returns is not None and len(bootstrap_returns) >= 10:
        idx = np.random.randint(0, len(bootstrap_returns), size=n_sim - half)
        log_ret_b = bootstrap_returns[idx] * calib_factor
        prices_b = last_price * np.exp(log_ret_b)
    else:
        # Fallback if we don't have enough data
        z_b = stats.t.rvs(df=df, size=n_sim - half)
        log_ret_b = mu + sig * z_b
        prices_b = last_price * np.exp(log_ret_b)

    return np.concatenate([prices_t, prices_b])

<<<<<<< Updated upstream

# ─────────────────────────────────────────────
=======
>>>>>>> Stashed changes
#  Forecaster class

class BTCForecaster:
    """
    Walk-forward Bitcoin 1-hour 95% confidence interval forecaster.
    """

    def __init__(self):
        self.calib_factor: float = 1.0   # adaptive calibration
        self._coverage_ema: float = 0.95  # EMA of recent coverage

    # ------------------------------------------------------------------
    def predict(self,
                closes: np.ndarray,
                highs: np.ndarray,
                lows: np.ndarray,
                min_history: int = 60) -> ForecastResult:
        """
        Predict the 95% CI for the next 1-hour close.

        Parameters
        ----------
        closes, highs, lows : 1-D arrays in chronological order.
            Last element is the most-recent completed bar.
        """
        assert len(closes) >= min_history, \
            f"Need at least {min_history} bars; got {len(closes)}"

        feats = extract_features(closes, highs, lows)
        ret   = compute_log_returns(closes)
        mu    = estimate_drift(ret)

        # Blend volatility signals: weight fast more in volatile regimes
        if feats.regime == "volatile":
            sigma = 0.60 * feats.sigma_fast + 0.30 * feats.sigma_roll20 \
                    + 0.10 * feats.atr
        elif feats.regime == "calm":
            sigma = 0.30 * feats.sigma_fast + 0.50 * feats.sigma_roll50 \
                    + 0.20 * feats.sigma_roll20
        else:
            sigma = 0.45 * feats.sigma_fast + 0.40 * feats.sigma_roll20 \
                    + 0.15 * feats.sigma_roll10

        last_price = float(closes[-1])

        paths = simulate_paths(
            last_price=last_price,
            mu=mu,
            sigma=sigma,
            df=feats.df,
            regime=feats.regime,
            calib_factor=self.calib_factor,
            bootstrap_returns=ret
        )

        lo = float(np.percentile(paths, 100 * ALPHA / 2))
        hi = float(np.percentile(paths, 100 * (1 - ALPHA / 2)))

        return ForecastResult(
            lower=lo, upper=hi,
            mu_est=mu, sigma=sigma,
            df=feats.df, regime=feats.regime,
            calib=self.calib_factor
        )

    # ------------------------------------------------------------------
    def update_calibration(self, lower: float, upper: float,
                           actual: float) -> None:
        """
        Online calibration: if actual is outside interval, widen;
        if consistently inside, tighten.
        Uses EMA of coverage + gradient step on calibration factor.
        """
        hit = 1.0 if lower <= actual <= upper else 0.0
        self._coverage_ema = (1 - CALIB_ALPHA) * self._coverage_ema \
                             + CALIB_ALPHA * hit
        gap = self._coverage_ema - 0.95          # target 95%

        # Gradient step: if coverage low → increase calib
        step = -0.5 * gap                         # negative gap → increase
        self.calib_factor = float(
            np.clip(self.calib_factor + step, CALIB_MIN, CALIB_MAX)
        )

    # ------------------------------------------------------------------
    def backtest(self,
                 closes: np.ndarray,
                 highs: np.ndarray,
                 lows: np.ndarray,
                 n_test: int = 720,
                 warmup: int = 100) -> BacktestMetrics:
        """
        Walk-forward back-test on the last n_test bars.
        Returns BacktestMetrics with coverage, avg_width, Winkler score.
        """
        n = len(closes)
        assert n > n_test + warmup, \
            f"Need {n_test + warmup + 1} bars; got {n}"

        # Reset calibration for clean backtest
        self.calib_factor   = 1.0
        self._coverage_ema  = 0.95

        start_idx = n - n_test
        details   = []
        hits      = []
        widths    = []
        winklers  = []

        for i in range(start_idx, n - 1):
            # train on everything BEFORE i
            train_c = closes[:i]
            train_h = highs[:i]
            train_l = lows[:i]

            if len(train_c) < warmup:
                continue

            result = self.predict(train_c, train_h, train_l)
            actual = float(closes[i + 1])

            self.update_calibration(result.lower, result.upper, actual)

            hit  = int(result.lower <= actual <= result.upper)
            w    = result.upper - result.lower
            wink = winkler_score(result.lower, result.upper, actual,
                                 alpha=ALPHA)

            hits.append(hit)
            widths.append(w)
            winklers.append(wink)
            details.append({
                "lower":  result.lower,
                "upper":  result.upper,
                "actual": actual,
                "hit":    hit,
                "width":  w,
                "winkler": wink,
                "regime": result.regime,
                "calib":  result.calib,
            })

        coverage = float(np.mean(hits))
        avg_w    = float(np.mean(widths))
        avg_wink = float(np.mean(winklers))

        return BacktestMetrics(
            coverage=coverage,
            avg_width=avg_w,
            winkler=avg_wink,
            n_samples=len(hits),
            details=details
        )


# ─────────────────────────────────────────────
#  Winkler Score
# ─────────────────────────────────────────────

def winkler_score(lower: float, upper: float,
                  actual: float, alpha: float = 0.05) -> float:
    """
    Winkler interval score (lower is better).
    Score = width + (2/alpha)*max(lower-actual, 0)
                  + (2/alpha)*max(actual-upper, 0)
    """
    width = upper - lower
    penalty = (2.0 / alpha) * (
        max(lower - actual, 0.0) + max(actual - upper, 0.0)
    )
    return width + penalty
