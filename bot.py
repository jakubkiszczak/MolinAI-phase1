#!/usr/bin/env python3
"""Replay the last 24 hours of BTC/USD and paper-trade them.

    python3 bot.py

No arguments, no API keys, no third-party packages (Python 3.9+).
The window is always the 24 hours before the moment it runs.
"""
from __future__ import annotations

import sys
import time

if sys.version_info < (3, 9):
    sys.exit("Python 3.9 or newer is required (found %s)." % sys.version.split()[0])

from btcbot.data import FetchError, fetch_candles  # noqa: E402
from btcbot.engine import run  # noqa: E402
from btcbot.report import print_report  # noqa: E402
from btcbot.strategy import Params, DipAndBank  # noqa: E402

WINDOW_MIN = 24 * 60
WARMUP_MIN = 6 * 60  # history before the window, only used to warm up indicators


def window_bounds(now: int):
    """(fetch_start, window_start, window_end) in unix seconds.

    The window is the 24h ending at the last fully closed minute before `now`;
    candles with open time in [window_start, window_end) are traded.
    """
    window_end = now - now % 60
    window_start = window_end - WINDOW_MIN * 60
    return window_start - WARMUP_MIN * 60, window_start, window_end


def main() -> int:
    now = int(time.time())
    fetch_start, window_start, window_end = window_bounds(now)

    print("Fetching 1-minute BTC/USD candles (24h window + 6h indicator warm-up)...")
    try:
        candles, source = fetch_candles(fetch_start, window_end)
    except FetchError as e:
        print("ERROR: could not download prices.\n%s" % e, file=sys.stderr)
        return 2

    first = next((k for k, c in enumerate(candles) if c.t >= window_start), None)
    if first is None:
        print("ERROR: not enough history returned by %s." % source, file=sys.stderr)
        return 2
    last = len(candles) - 1

    strategy = DipAndBank(Params()).prepare(candles)
    result = run(candles, first, last, strategy)
    print_report(result, source, now, strategy.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
