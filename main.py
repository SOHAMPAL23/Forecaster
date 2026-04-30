# main.py — BTC Forecasting System Backend
# Simple FastAPI server to handle data fetching and predictions

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from model.data_fetcher import (
    fetch_klines_async,
    fetch_ticker_price,
    fetch_24h_stats,
    klines_to_arrays,
)
from model.forecaster import BTCForecaster, BacktestMetrics, winkler_score

# ──────────────────────────────────────────────────────────
app = FastAPI(title="BTC Forecasting API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances and simple caching
# We don't want to hit Binance API too hard
forecaster        = BTCForecaster()
_klines_cache     = []
_klines_ts: float = 0.0        # last fetch timestamp
_klines_ttl       = 60         # refresh every min
_backtest_cache   = None
_backtest_ts: float = 0.0
_backtest_ttl     = 300        # backtest is expensive, cache for 5 min


async def _get_klines(limit: int = 900):
    global _klines_cache, _klines_ts
    now = time.time()
    if now - _klines_ts > _klines_ttl or not _klines_cache:
        _klines_cache = await fetch_klines_async(limit=limit)
        _klines_ts = now
    return _klines_cache


async def _get_backtest() -> BacktestMetrics:
    global _backtest_cache, _backtest_ts, forecaster
    now = time.time()
    if now - _backtest_ts > _backtest_ttl or _backtest_cache is None:
        klines = await fetch_klines_async(limit=900)
        _, highs, lows, closes = klines_to_arrays(klines)
        forecaster_bt = BTCForecaster()
        _backtest_cache = forecaster_bt.backtest(
            closes, highs, lows, n_test=720, warmup=100
        )
        # Update live forecaster calibration factor with backtest result
        forecaster.calib_factor   = forecaster_bt.calib_factor
        forecaster._coverage_ema  = forecaster_bt._coverage_ema
        _backtest_ts = now
    return _backtest_cache


# ──────────────────────────────────────────────────────────
#  API routes
# ──────────────────────────────────────────────────────────

@app.get("/api/forecast")
async def get_forecast():
    """Return current forecast + live price + backtest metrics."""
    try:
        klines = await _get_klines()
        _, highs, lows, closes = klines_to_arrays(klines)

        # Live forecast (use all available bars)
        forecast = forecaster.predict(closes, highs, lows)

        # Live price
        live_price = await fetch_ticker_price()

        # 24h stats
        stats = await fetch_24h_stats()

        # Backtest (cached)
        bt = await _get_backtest()

        # Most recent 50 candles for charting
        recent_klines = klines[-50:]

        return {
            "timestamp":   datetime.now(tz=timezone.utc).isoformat(),
            "live_price":  live_price,
            "forecast": {
                "lower":  forecast.lower,
                "upper":  forecast.upper,
                "mu":     forecast.mu_est,
                "sigma":  forecast.sigma,
                "df":     forecast.df,
                "regime": forecast.regime,
                "calib":  forecast.calib,
            },
            "stats_24h": stats,
            "backtest": {
                "coverage":  bt.coverage,
                "avg_width": bt.avg_width,
                "winkler":   bt.winkler,
                "n_samples": bt.n_samples,
            },
            "candles": recent_klines,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtest_details")
async def get_backtest_details(limit: int = 100):
    """Return last N backtest data points for visualisation."""
    try:
        bt = await _get_backtest()
        details = bt.details[-limit:]
        return {"details": details, "total": bt.n_samples}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/price")
async def get_price():
    try:
        price = await fetch_ticker_price()
        stats = await fetch_24h_stats()
        return {"price": price, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/candles")
async def get_candles(limit: int = 50):
    try:
        klines = await _get_klines()
        return {"candles": klines[-limit:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(tz=timezone.utc).isoformat()}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Stop browsers from complaining about missing icon
    return FileResponse(static_dir / "favicon.ico") if (static_dir / "favicon.ico").exists() else {}

# Standard static file mounting
static_dir = Path(__file__).parent / "frontend"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir / "static")), name="static")

    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        return FileResponse(str(static_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
