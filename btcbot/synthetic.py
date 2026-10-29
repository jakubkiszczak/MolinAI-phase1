"""Synthetic 1-minute candles, used only for offline tests of the mechanics.

kind="rw": pure random walk (no edge for any strategy; fees make it lose).
kind="mr": random walk plus a mean-reverting component (the effect the
           strategy is designed to harvest).
"""
from __future__ import annotations

import math
import random
from typing import List

from .data import Candle


def generate(n: int, kind: str = "mr", seed: int = 1, start_price: float = 100_000.0,
             start_t: int = 1_760_000_000, daily_vol: float = 0.025, drift_per_day: float = 0.0) -> List[Candle]:
    rng = random.Random(seed)
    sig = daily_vol / math.sqrt(1440)
    if kind == "mr":
        rw_sig, ou_sig, ou_k = sig * 0.75, sig * 0.9, 1 - 0.5 ** (1 / 30)  # 30-min half-life
    elif kind == "rw":
        rw_sig, ou_sig, ou_k = sig, 0.0, 0.0
    else:
        raise ValueError(kind)
    drift = drift_per_day / 1440
    trend = math.log(start_price)
    ou = 0.0
    vol_mult = 1.0
    out: List[Candle] = []
    prev = start_price
    for i in range(n):
        vol_mult = min(3.0, max(0.4, vol_mult * math.exp(rng.gauss(0, 0.02)) * (1 + 0.001 * (1 - vol_mult))))
        trend += drift + rng.gauss(0, rw_sig * vol_mult)
        ou += -ou_k * ou + rng.gauss(0, ou_sig * vol_mult)
        close = math.exp(trend + ou)
        o = prev
        wick = abs(rng.gauss(0, sig * vol_mult * 0.5)) * close
        h = max(o, close) + wick
        l = min(o, close) - abs(rng.gauss(0, sig * vol_mult * 0.5)) * close
        out.append(Candle(start_t + 60 * i, o, h, l, close, 1.0))
        prev = close
    return out
