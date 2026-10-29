"""Paper-trading engine: cash/BTC accounting, 0.1% fees, long-only, flat at end.

The engine walks the 24-hour window one closed candle at a time. At candle i
the strategy may only see candles[0..i] (see Strategy.decide); orders fill
at that candle's close, i.e. the latest price known at that moment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .data import Candle

START_CASH = 10_000.0
FEE_RATE = 0.001  # 0.1% on every buy and every sell


@dataclass
class Position:
    entry_idx: int
    entry_time: int
    entry_price: float
    qty: float           # BTC held
    cost: float          # USD paid for the BTC (excl. fee)
    buy_fee: float
    kind: str            # "signal", "relaxed" or "probe"


@dataclass
class Trade:
    buy_time: int
    buy_price: float
    sell_time: int
    sell_price: float
    qty: float
    cost: float          # USD value bought (excl. fee)
    proceeds: float      # USD value sold (excl. fee)
    buy_fee: float
    sell_fee: float
    kind: str
    exit_reason: str

    @property
    def fees(self) -> float:
        return self.buy_fee + self.sell_fee

    @property
    def pnl(self) -> float:
        return (self.proceeds - self.sell_fee) - (self.cost + self.buy_fee)

    @property
    def pnl_pct(self) -> float:
        return self.pnl / (self.cost + self.buy_fee) * 100.0


@dataclass
class State:
    """What the strategy is allowed to know about the account."""
    i: int                       # index of the candle that just closed
    window_start: int            # index of the first candle in the 24h window
    window_end: int              # index of the last candle in the window
    cash: float
    position: Optional[Position]
    trades_done: int
    realized_pnl: float

    @property
    def candles_left(self) -> int:
        return self.window_end - self.i


@dataclass
class Result:
    trades: List[Trade]
    start_cash: float
    final_cash: float
    final_btc: float
    window_first: Candle
    window_last: Candle
    n_candles: int
    events: List[str] = field(default_factory=list)

    @property
    def profit(self) -> float:
        return self.final_cash - self.start_cash

    @property
    def profit_pct(self) -> float:
        return self.profit / self.start_cash * 100.0

    def buy_and_hold(self):
        """Buy at the window's first price, sell at its last, same fees."""
        p0, p1 = self.window_first.o, self.window_last.c
        cost = self.start_cash / (1 + FEE_RATE)
        qty = cost / p0
        proceeds = qty * p1
        final = proceeds * (1 - FEE_RATE)
        return final, (p1 / p0 - 1) * 100.0


def _buy(cash: float, usd: float, price: float):
    usd = min(usd, cash)
    cost = usd / (1 + FEE_RATE)
    fee = cost * FEE_RATE
    return cost / price, cost, fee


def run(candles: List[Candle], window_start: int, window_end: int, strategy) -> Result:
    """Simulate trading candles[window_start .. window_end] (inclusive).

    candles before window_start are history only (indicator warm-up); no
    trades happen there. `strategy` must have been prepared on `candles`.
    """
    cash = START_CASH
    pos: Optional[Position] = None
    trades: List[Trade] = []
    realized = 0.0

    def close(i: int, reason: str):
        nonlocal cash, pos, realized
        price = candles[i].c
        proceeds = pos.qty * price
        fee = proceeds * FEE_RATE
        cash += proceeds - fee
        t = Trade(pos.entry_time, pos.entry_price, candles[i].t, price, pos.qty,
                  pos.cost, proceeds, pos.buy_fee, fee, pos.kind, reason)
        trades.append(t)
        realized += t.pnl
        pos = None

    for i in range(window_start, window_end + 1):
        st = State(i, window_start, window_end, cash, pos, len(trades), realized)
        action = strategy.decide(i, st)
        if pos is not None and action.kind == "sell":
            close(i, action.reason)
        elif pos is None and action.kind == "buy" and i < window_end:
            usd = cash * max(0.0, min(1.0, action.fraction))
            if usd >= 1.0:
                qty, cost, fee = _buy(cash, usd, candles[i].c)
                cash -= cost + fee
                pos = Position(i, candles[i].t, candles[i].c, qty, cost, fee, action.tag)

    # Rule: flat at the end. Anything still open is sold at the last close.
    if pos is not None:
        close(window_end, "end of window")
    btc_held = pos.qty if pos is not None else 0.0

    return Result(trades, START_CASH, cash, btc_held, candles[window_start], candles[window_end],
                  window_end - window_start + 1)
