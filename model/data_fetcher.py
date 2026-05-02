# Binance public API data fetcher
# No keys needed for basic market data
import httpx
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import asyncio

BINANCE_BASE = "https://api.binance.com"
SYMBOL       = "BTCUSDT"
INTERVAL     = "1h"
MAX_KLINES   = 1000          # Binance max per request


async def fetch_klines_async(
    symbol: str = SYMBOL,
    interval: str = INTERVAL,
    limit: int = 900
) -> List[dict]:
    # Fetch klines asynchronously from Binance
    url    = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        raw = resp.json()

    return _parse_klines(raw)


def fetch_klines_sync(
    symbol: str = SYMBOL,
    interval: str = INTERVAL,
    limit: int = 900
) -> List[dict]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, fetch_klines_async(symbol, interval, limit))
                return future.result()
        else:
            return loop.run_until_complete(fetch_klines_async(symbol, interval, limit))
    except RuntimeError:
        return asyncio.run(fetch_klines_async(symbol, interval, limit))


def _parse_klines(raw: List[list]) -> List[dict]:
    # Convert the nested list from Binance into something readable
    result = []
    for k in raw:
        result.append({
            "timestamp":  datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
            "open":       float(k[1]),
            "high":       float(k[2]),
            "low":        float(k[3]),
            "close":      float(k[4]),
            "volume":     float(k[5]),
        })
    return result


def klines_to_arrays(klines: List[dict]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    opens  = np.array([k["open"]  for k in klines], dtype=np.float64)
    highs  = np.array([k["high"]  for k in klines], dtype=np.float64)
    lows   = np.array([k["low"]   for k in klines], dtype=np.float64)
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    return opens, highs, lows, closes


async def fetch_ticker_price(symbol: str = SYMBOL) -> float:
    # Fetch current ticker price.
    url = f"{BINANCE_BASE}/api/v3/ticker/price"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        return float(resp.json()["price"])


async def fetch_24h_stats(symbol: str = SYMBOL) -> Dict:
    # Fetch 24-hour statistics
    url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        d = resp.json()
        return {
            "price_change_pct": float(d["priceChangePercent"]),
            "high_24h":         float(d["highPrice"]),
            "low_24h":          float(d["lowPrice"]),
            "volume_24h":       float(d["volume"]),
            "last_price":       float(d["lastPrice"]),
        }
