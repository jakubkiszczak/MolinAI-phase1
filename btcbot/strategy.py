"""Dip & Bank: buy a short-term dip, take a small profit, then only risk "house money".

Core idea
  BTC's 24-hour range is almost always much wider than a 0.3% move. If the
  bot buys after a short-term dip and asks for only +0.3% (about +0.1%
  after the 0.2% round-trip fee), price usually reaches that target within
  the day. Once the day is in profit, the bot "banks" it: every later
  trade is sized so that even a stop-out can cost at most 30% of the
  profit made so far. This is the "protect the green day" rule many
  discretionary traders use, made mechanical.

  The trade-off, stated honestly: this maximises the *chance* of ending
  the day green, not the average profit. On a day when BTC falls steadily
  and never bounces 0.3% above the entry, the bot holds and loses. See
  README for backtest numbers.

Rules (defaults in Params; every decision uses only candles up to now)
  BUY  (100% of cash until the first win, then house-money size) when:
       - the close is >= 2.0 standard deviations below its 60-min average
         (this candle or one of the previous two) and >= 0.1% below it,
       - this candle closed higher than the previous one (the drop stalled),
       - the last 4 hours did not fall more than 1% (don't buy a slide),
       - there are >= 45 minutes left in the window.
  SELL when the first of these happens:
       - take-profit: +0.3% above entry (gross),
       - stop-loss: -3% (a wide, disaster-only stop),
       - end-of-day: <= 2 h left and at least break-even after fees,
       - the window ends (engine force-sells, so the bot always ends flat).

Banking and rule-compliance layers
  - Bank: while the day's realised P/L is positive, each new trade is
    sized so a -3% stop-out (plus fees) costs <= 30% of that profit.
  - Trade-count guard: if fewer than 5 trades are done with 6 h left,
    thresholds relax (1.5 sd, 0.25% gap, +0.25% target), size <= 25%.
  - Last-resort probes: if 5 trades are otherwise impossible, tiny $25
    one-minute round trips fill the count (cost: a few cents each).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import List, NamedTuple

from .data import Candle
from .engine import FEE_RATE, State

ROUND_TRIP_FEE = 2 * FEE_RATE
MIN_TRADES = 5


@dataclass
class Params:
    mean_len: int = 60              # minutes for the moving average / stdev
    z_entry: float = 2.0            # stdevs below the average to buy
    min_gap: float = 0.001          # min distance below the average
    trend_len: int = 240            # slide filter lookback (minutes)
    max_trend_drop: float = 0.01    # skip entries if the last 4h fell more than this
    take_profit: float = 0.003      # gross take-profit (~+0.1% after fees)
    stop_loss: float = 0.03         # disaster stop
    breakeven: float = ROUND_TRIP_FEE + 0.0002  # gross gain that nets >= 0 after fees
    no_entry_last: int = 45         # no new signal entries in the last N minutes
    derisk_last: int = 120          # last N minutes: exit as soon as break-even
    protect_share: float = 0.3      # once the day is green, a stop-out may cost <= this share of the profit
    guard_start: int = 360          # minutes left when the trade-count guard starts
    guard_z: float = 1.5
    guard_gap: float = 0.0025
    guard_tp: float = 0.0025
    guard_fraction: float = 0.25
    probe_usd: float = 25.0

    def override(self, **kw):
        names = {f.name for f in fields(self)}
        for k, v in kw.items():
            if k not in names:
                raise KeyError("unknown parameter %r" % k)
            setattr(self, k, type(getattr(self, k))(v))
        return self


class Action(NamedTuple):
    kind: str              # "hold", "buy", "sell"
    fraction: float = 0.0  # share of cash to spend (buys)
    tag: str = ""          # buy type: signal / guard / probe
    reason: str = ""       # sell reason


HOLD = Action("hold")


def _rolling_mean_std(x: List[float], n: int):
    """Causal rolling mean/stdev: value at i uses x[i-n+1 .. i] only."""
    mean = [math.nan] * len(x)
    std = [math.nan] * len(x)
    if not x:
        return mean, std
    ref = x[0]  # centre values for numerical stability
    s = s2 = 0.0
    for i, v in enumerate(x):
        d = v - ref
        s += d
        s2 += d * d
        if i >= n:
            old = x[i - n] - ref
            s -= old
            s2 -= old * old
        if i >= n - 1:
            m = s / n
            mean[i] = m + ref
            std[i] = math.sqrt(max(s2 / n - m * m, 0.0))
    return mean, std


class DipAndBank:
    name = "Dip & Bank"

    def __init__(self, params: Params = None):
        self.p = params or Params()

    # Indicators are computed once, causally: index i depends only on
    # candles[0..i]. tests/test_rules.py checks this by truncating the data.
    def prepare(self, candles: List[Candle]):
        self.close = [c.c for c in candles]
        self.mean, self.std = _rolling_mean_std(self.close, self.p.mean_len)
        return self

    def _z(self, i: int) -> float:
        sd = self.std[i]
        return (self.close[i] - self.mean[i]) / sd if sd > 0 else 0.0

    def _size(self, st: State) -> float:
        p = self.p
        if st.realized_pnl <= 0:
            return 1.0
        worst = st.cash * (p.stop_loss + ROUND_TRIP_FEE)
        return min(1.0, p.protect_share * st.realized_pnl / worst)

    def decide(self, i: int, st: State) -> Action:
        p, c = self.p, self.close
        if i < max(p.mean_len, p.trend_len, 3):
            return HOLD
        price = c[i]
        left = st.candles_left
        needed = MIN_TRADES - st.trades_done

        # ------------------------------------------------------------- exits
        pos = st.position
        if pos is not None:
            if pos.kind == "probe":
                return Action("sell", reason="probe closed")
            gain = price / pos.entry_price - 1
            target = p.guard_tp if pos.kind == "guard" else p.take_profit
            if gain >= target:
                return Action("sell", reason="take-profit")
            if gain <= -p.stop_loss:
                return Action("sell", reason="stop-loss")
            if left <= p.derisk_last and gain >= p.breakeven:
                return Action("sell", reason="end-of-day break-even")
            # Leave just enough time to finish the remaining required trades.
            if needed > 1 and left <= 2 * (needed - 1) + 2:
                return Action("sell", reason="make room for required trades")
            return HOLD

        # ------------------------------------------------------------ entries
        # Last resort: tiny 1-minute round trips so the 5-trade rule always holds.
        if needed > 0 and left <= 2 * needed + 2:
            return Action("buy", fraction=p.probe_usd / max(st.cash, 1.0), tag="probe") if left >= 1 else HOLD

        guard = needed > 0 and left <= p.guard_start
        if left < p.no_entry_last:
            return HOLD

        z_need = p.guard_z if guard else p.z_entry
        gap_need = p.guard_gap if guard else p.min_gap
        stretched = min(self._z(i), self._z(i - 1), self._z(i - 2)) <= -z_need
        gap = self.mean[i] / price - 1
        stalled = price > c[i - 1]
        trend = price / c[i - p.trend_len] - 1
        if stretched and gap >= gap_need and stalled and trend >= -p.max_trend_drop:
            size = self._size(st)
            if guard:
                return Action("buy", fraction=min(size, p.guard_fraction), tag="guard")
            return Action("buy", fraction=size, tag="signal")
        return HOLD
