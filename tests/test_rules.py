"""Checks every rule from the brief that can be tested offline.

    python3 -m unittest -v
"""
import random
import unittest

from bot import window_bounds
from btcbot.data import Candle
from btcbot.engine import FEE_RATE, START_CASH, run
from btcbot.strategy import MIN_TRADES, DipAndBank, Params
from btcbot.synthetic import generate

WARMUP, WINDOW = 360, 1440


def simulate(candles):
    s = DipAndBank(Params()).prepare(candles)
    return run(candles, WARMUP, WARMUP + WINDOW - 1, s)


class Rules(unittest.TestCase):
    def setUp(self):
        self.days = [generate(WARMUP + WINDOW, kind=k, seed=seed, drift_per_day=d)
                     for k in ("rw", "mr") for seed in range(1, 6) for d in (-0.05, 0.0, 0.05)]

    def test_at_least_five_trades_and_flat(self):
        for candles in self.days:
            r = simulate(candles)
            self.assertGreaterEqual(len(r.trades), MIN_TRADES)
            self.assertEqual(r.final_btc, 0.0)

    def test_every_trade_inside_window_and_long_only(self):
        for candles in self.days:
            r = simulate(candles)
            t0, t1 = candles[WARMUP].t, candles[-1].t
            last_sell = 0
            for t in r.trades:
                self.assertTrue(t0 <= t.buy_time < t.sell_time <= t1)
                self.assertGreaterEqual(t.buy_time, last_sell)  # one position at a time
                self.assertGreater(t.qty, 0)
                self.assertLessEqual(t.cost + t.buy_fee, START_CASH * 1.5)
                last_sell = t.sell_time

    def test_fees_are_point_one_percent_each_side(self):
        for candles in self.days[:3]:
            for t in simulate(candles).trades:
                self.assertAlmostEqual(t.buy_fee, t.cost * FEE_RATE, places=9)
                self.assertAlmostEqual(t.sell_fee, t.proceeds * FEE_RATE, places=9)

    def test_balance_adds_up(self):
        for candles in self.days:
            r = simulate(candles)
            self.assertAlmostEqual(r.final_cash, START_CASH + sum(t.pnl for t in r.trades), places=6)

    def test_no_look_ahead(self):
        """Scrambling future prices must not change any earlier decision."""
        rng = random.Random(7)
        for candles in self.days[:6]:
            base = simulate(candles)
            for _ in range(3):
                k = rng.randrange(WARMUP + 10, WARMUP + WINDOW - 10)
                cut = candles[k].t
                future = [Candle(c.t, *(x * rng.uniform(0.9, 1.1) for x in c[1:5]), c.v) for c in candles[k + 1:]]
                alt = simulate(candles[:k + 1] + future)
                before = [t for t in base.trades if t.sell_time <= cut]
                alt_before = [t for t in alt.trades if t.sell_time <= cut]
                self.assertEqual(before, alt_before)
                open_base = [t.buy_time for t in base.trades if t.buy_time <= cut]
                open_alt = [t.buy_time for t in alt.trades if t.buy_time <= cut]
                self.assertEqual(open_base, open_alt)

    def test_window_is_last_24h(self):
        fs, ws, we = window_bounds(1_761_753_812)
        self.assertEqual(we - ws, 24 * 3600)
        self.assertLessEqual(we, 1_761_753_812)
        self.assertGreater(we, 1_761_753_812 - 60)
        self.assertEqual(ws - fs, 6 * 3600)

    def test_buy_and_hold_includes_fees(self):
        r = simulate(self.days[0])
        final, move = r.buy_and_hold()
        expected = START_CASH / (1 + FEE_RATE) / r.window_first.o * r.window_last.c * (1 - FEE_RATE)
        self.assertAlmostEqual(final, expected, places=6)


if __name__ == "__main__":
    unittest.main()
