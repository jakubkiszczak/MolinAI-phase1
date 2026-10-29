"""Fetch 1-minute BTC/USD candles from free public feeds (no API keys).

Sources, tried in order until one returns a complete series:
  1. Coinbase Exchange  BTC-USD   (real USD pair, works worldwide incl. the US)
  2. Binance            BTCUSDT   (USDT ~ USD)
  3. Binance data mirror BTCUSDT  (data-api.binance.vision, same data)

Networking uses only the standard library. If Python's own HTTPS fails
(common on a fresh macOS python.org install that has no CA certificates
yet), it falls back to the system `curl`, which ships with every Mac.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, List, NamedTuple, Optional, Sequence, Tuple

USER_AGENT = "btc-paper-bot/1.0 (+public market data)"
MINUTE = 60


class Candle(NamedTuple):
    t: int        # open time, unix seconds (UTC)
    o: float
    h: float
    l: float
    c: float
    v: float


class FetchError(RuntimeError):
    pass


# --------------------------------------------------------------------------- HTTP
def _get_json_urllib(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json_curl(url: str, timeout: float):
    curl = shutil.which("curl")
    if not curl:
        raise FetchError("curl not available")
    out = subprocess.run(
        [curl, "-sS", "--fail", "-m", str(int(timeout)), "-A", USER_AGENT, url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise FetchError("curl failed: " + (out.stderr.strip() or "exit %d" % out.returncode))
    return json.loads(out.stdout)


def get_json(url: str, timeout: float = 20.0, retries: int = 3):
    """GET a JSON document. Retries on rate limits / transient errors."""
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return _get_json_urllib(url, timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 418, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise FetchError("HTTP %d from %s" % (e.code, url.split("?")[0]))
        except (urllib.error.URLError, OSError, ValueError) as e:
            # SSL / certificate / DNS problems: try the system curl instead.
            last = e
            try:
                return _get_json_curl(url, timeout)
            except Exception as e2:  # noqa: BLE001
                last = e2
                time.sleep(1.0 * (attempt + 1))
    raise FetchError(str(last))


# --------------------------------------------------------------------------- sources
def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_coinbase(start: int, end: int, progress: Optional[Callable[[int], None]] = None) -> List[Candle]:
    """Candles with open time in [start, end). Coinbase allows 300 per request."""
    base = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    out = {}
    step = 300 * MINUTE
    s = start
    while s < end:
        e = min(s + step, end)
        url = "%s?granularity=60&start=%s&end=%s" % (base, _iso(s), _iso(e - MINUTE))
        rows = get_json(url)
        if not isinstance(rows, list):
            raise FetchError("unexpected Coinbase response: %r" % (rows,))
        for r in rows:  # [time, low, high, open, close, volume], newest first
            t = int(r[0])
            if start <= t < end:
                out[t] = Candle(t, float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5]))
        s = e
        if progress:
            progress(len(out))
        time.sleep(0.12)  # stay well under the public rate limit
    return [out[k] for k in sorted(out)]


def _fetch_binance(host: str, start: int, end: int, progress=None) -> List[Candle]:
    base = "https://%s/api/v3/klines" % host
    out = {}
    s = start
    while s < end:
        url = "%s?symbol=BTCUSDT&interval=1m&startTime=%d&endTime=%d&limit=1000" % (
            base, s * 1000, end * 1000 - 1)
        rows = get_json(url)
        if not isinstance(rows, list):
            raise FetchError("unexpected Binance response: %r" % (rows,))
        if not rows:
            break
        for r in rows:  # [openTime ms, open, high, low, close, volume, ...]
            t = int(r[0]) // 1000
            if start <= t < end:
                out[t] = Candle(t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        s = int(rows[-1][0]) // 1000 + MINUTE
        if progress:
            progress(len(out))
        time.sleep(0.05)
    return [out[k] for k in sorted(out)]


def fetch_binance(start, end, progress=None):
    return _fetch_binance("api.binance.com", start, end, progress)


def fetch_binance_mirror(start, end, progress=None):
    return _fetch_binance("data-api.binance.vision", start, end, progress)


SOURCES: Sequence[Tuple[str, Callable]] = (
    ("Coinbase BTC-USD", fetch_coinbase),
    ("Binance BTCUSDT", fetch_binance),
    ("Binance mirror BTCUSDT", fetch_binance_mirror),
)


def fetch_candles(start: int, end: int, min_coverage: float = 0.97,
                  log: Callable[[str], None] = print, progress=None) -> Tuple[List[Candle], str]:
    """Return (candles, source_name) for open times in [start, end).

    Tries each source in turn and accepts the first that covers at least
    `min_coverage` of the expected minutes (BTC trades every minute, but a
    feed can occasionally skip one).
    """
    expected = (end - start) // MINUTE
    errors = []
    for name, fn in SOURCES:
        try:
            candles = fn(start, end, progress)
        except Exception as e:  # noqa: BLE001 - try the next feed
            errors.append("%s: %s" % (name, e))
            log("  ! %s unavailable (%s), trying next feed" % (name, e))
            continue
        if len(candles) >= expected * min_coverage:
            return candles, name
        errors.append("%s: only %d/%d candles" % (name, len(candles), expected))
        log("  ! %s returned only %d of %d candles, trying next feed" % (name, len(candles), expected))
    raise FetchError("No price feed worked:\n  " + "\n  ".join(errors))
