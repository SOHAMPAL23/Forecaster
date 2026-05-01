# Quantitative Bitcoin 1-hour price-range forecasting engine.
#
# Upgrades included for maximum accuracy:
#  - Parkinson Volatility (High/Low) combined with EWMA
#  - Student-t Jump-Diffusion Monte Carlo
#  - PI Controller for Adaptive Calibration
#  - Momentum-adjusted drift

import numpy as np
import pandas as pd
from scipy import stats
from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional
import warnings

warnings.filterwarnings("ignore")

# Basic model configs
N_SIM          = 10_000   
ALPHA          = 0.05     # 95% CI
MIN_DF         = 2.5      
MAX_DF         = 30.0     
SHRINK_LAMBDA  = 0.10     # Slightly less shrinkage to respect momentum
CALIB_ALPHA    = 0.05     
CALIB_MIN      = 0.60
CALIB_MAX      = 2.00
EWMA_FAST      = 12       
EWMA_SLOW      = 26       

# ─────────────────────────────────────────────
#  Data classes
# ─────────────────────────────────────────────
@dataclass
class VolatilityFeatures:
    sigma_fast:    float   
    sigma_slow:    float   
    sigma_park:    float   # Parkinson Volatility
    atr:           float
    regime:        str     
    df:            float   

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

# ─────────────────────────────────────────────
#  Feature engineering
# ─────────────────────────────────────────────

def compute_log_returns(closes: np.ndarray) -> np.ndarray:
    return np.diff(np.log(closes))

def ewma_volatility(returns: np.ndarray, span: int) -> float:
    alpha = 2.0 / (span + 1)
    weights = (1 - alpha) ** np.arange(len(returns) - 1, -1, -1)
    weights /= weights.sum()
    mu = np.dot(weights, returns)
    var = np.dot(weights, (returns - mu) ** 2)
    return float(np.sqrt(var))

def parkinson_volatility(highs: np.ndarray, lows: np.ndarray, window: int = 20) -> float:
    """Parkinson estimator using high and low prices, more efficient than close-close."""
    h = highs[-window:] if len(highs) >= window else highs
    l = lows[-window:] if len(lows) >= window else lows
    hl_ratio = np.log(h / l)
    var = (1.0 / (4.0 * np.log(2.0))) * np.mean(hl_ratio**2)
    return float(np.sqrt(var))

def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, window: int = 14) -> float:
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    atr_val = np.mean(tr[-window:]) if len(tr) >= window else np.mean(tr)
    return float(atr_val / closes[-1])

def estimate_df(returns: np.ndarray, window: int = 50) -> float:
    sample = returns[-window:] if len(returns) >= window else returns
    k = stats.kurtosis(sample, fisher=True)
    k = max(k, 0.01)
    if k >= 6: return MIN_DF
    if k < 0.01: return MAX_DF
    df = 6.0 / k + 4.0
    return float(np.clip(df, MIN_DF, MAX_DF))

def classify_regime(sigma_fast: float, sigma_slow: float, atr: float) -> str:
    ratio = sigma_fast / (sigma_slow + 1e-12)
    if ratio > 1.3 or atr > 0.007:
        return "volatile"
    elif ratio < 0.8 and atr < 0.003:
        return "calm"
    return "medium"

def extract_features(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> VolatilityFeatures:
    ret = compute_log_returns(closes)
    sf   = ewma_volatility(ret, EWMA_FAST)
    ss   = ewma_volatility(ret, EWMA_SLOW)
    park = parkinson_volatility(highs, lows, 20)
    atr  = compute_atr(highs, lows, closes)
    df   = estimate_df(ret)
    reg  = classify_regime(sf, ss, atr)
    return VolatilityFeatures(
        sigma_fast=sf, sigma_slow=ss, sigma_park=park,
        atr=atr, regime=reg, df=df
    )

# ─────────────────────────────────────────────
#  Drift estimation
# ─────────────────────────────────────────────

def estimate_drift(closes: np.ndarray, returns: np.ndarray, window: int = 20) -> float:
    """Momentum-based drift. Uses recent trend instead of just rolling mean."""
    # Simple EMA of returns to catch short-term momentum
    alpha = 2.0 / (window + 1)
    weights = (1 - alpha) ** np.arange(len(returns) - 1, -1, -1)
    weights /= weights.sum()
    ema_mu = np.dot(weights, returns)
    return float(ema_mu * (1 - SHRINK_LAMBDA))

def regime_sigma_scale(regime: str) -> float:
    return {"calm": 0.90, "medium": 1.0, "volatile": 1.25}[regime]

# ─────────────────────────────────────────────
#  Monte Carlo with Jump Diffusion
# ─────────────────────────────────────────────

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
    
    sig = sigma * regime_sigma_scale(regime) * calib_factor
    half = n_sim // 2

    # 1. T-distribution paths with Jump Diffusion (Merton-style)
    # Bitcoin has random extreme jumps. We model this as a Poisson process.
    jump_intensity = 0.03 if regime != "volatile" else 0.08  # higher jump prob in volatile
    jump_std = sig * 2.5 # Jumps are ~2.5x normal volatility
    
    z_t = stats.t.rvs(df=df, size=half)
    # Random Poisson jumps
    num_jumps = np.random.poisson(jump_intensity, size=half)
    # The jump magnitudes
    jump_sizes = np.random.normal(0, jump_std, size=half) * num_jumps
    
    log_ret_t = mu + sig * z_t + jump_sizes
    prices_t = last_price * np.exp(log_ret_t)

    # 2. Bootstrap paths (real historical data)
    if bootstrap_returns is not None and len(bootstrap_returns) >= 20:
        idx = np.random.randint(0, len(bootstrap_returns), size=n_sim - half)
        log_ret_b = bootstrap_returns[idx] * calib_factor + mu # apply momentum drift
        prices_b = last_price * np.exp(log_ret_b)
    else:
        # Fallback
        z_b = stats.t.rvs(df=df, size=n_sim - half)
        log_ret_b = mu + sig * z_b
        prices_b = last_price * np.exp(log_ret_b)

    return np.concatenate([prices_t, prices_b])

# ─────────────────────────────────────────────
#  Forecaster class
# ─────────────────────────────────────────────

class BTCForecaster:
    def __init__(self):
        self.calib_factor: float = 1.0   
        self._coverage_ema: float = 0.95  
        self._integral_gap: float = 0.0  # For PI Controller

    def predict(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, min_history: int = 60) -> ForecastResult:
        assert len(closes) >= min_history, f"Need at least {min_history} bars; got {len(closes)}"

        feats = extract_features(closes, highs, lows)
        ret   = compute_log_returns(closes)
        mu    = estimate_drift(closes, ret)

        # Blend volatility signals (Advanced)
        # Parkinson vol is great for intraday chop, EWMA is great for tail clustering
        if feats.regime == "volatile":
            sigma = 0.50 * feats.sigma_fast + 0.30 * feats.sigma_park + 0.20 * feats.atr
        elif feats.regime == "calm":
            sigma = 0.20 * feats.sigma_fast + 0.40 * feats.sigma_slow + 0.40 * feats.sigma_park
        else:
            sigma = 0.40 * feats.sigma_fast + 0.40 * feats.sigma_park + 0.20 * feats.atr

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

    def update_calibration(self, lower: float, upper: float, actual: float) -> None:
        """
        Online calibration using a Proportional-Integral (PI) Controller.
        This adapts much faster and more stably than a simple gradient step.
        """
        hit = 1.0 if lower <= actual <= upper else 0.0
        self._coverage_ema = (1 - CALIB_ALPHA) * self._coverage_ema + CALIB_ALPHA * hit
        
        gap = self._coverage_ema - 0.95  # Target 95%
        self._integral_gap += gap * 0.1  # Anti-windup scaled integral
        
        # PI Controller Constants
        Kp = -0.8  # Proportional term (reacts to immediate error)
        Ki = -0.2  # Integral term (fixes sustained bias)
        
        step = (Kp * gap) + (Ki * self._integral_gap)
        
        self.calib_factor = float(
            np.clip(self.calib_factor + step, CALIB_MIN, CALIB_MAX)
        )

    def backtest(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, n_test: int = 720, warmup: int = 100) -> BacktestMetrics:
        n = len(closes)
        assert n > n_test + warmup, f"Need {n_test + warmup + 1} bars; got {n}"

        self.calib_factor   = 1.0
        self._coverage_ema  = 0.95
        self._integral_gap  = 0.0

        start_idx = n - n_test
        details   = []
        hits      = []
        widths    = []
        winklers  = []

        for i in range(start_idx, n - 1):
            train_c = closes[:i]
            train_h = highs[:i]
            train_l = lows[:i]

            if len(train_c) < warmup: continue

            result = self.predict(train_c, train_h, train_l)
            actual = float(closes[i + 1])

            self.update_calibration(result.lower, result.upper, actual)

            hit  = int(result.lower <= actual <= result.upper)
            w    = result.upper - result.lower
            wink = winkler_score(result.lower, result.upper, actual, alpha=ALPHA)

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

        return BacktestMetrics(
            coverage=float(np.mean(hits)),
            avg_width=float(np.mean(widths)),
            winkler=float(np.mean(winklers)),
            n_samples=len(hits),
            details=details
        )

def winkler_score(lower: float, upper: float, actual: float, alpha: float = 0.05) -> float:
    width = upper - lower
    penalty = (2.0 / alpha) * (max(lower - actual, 0.0) + max(actual - upper, 0.0))
    return width + penalty
