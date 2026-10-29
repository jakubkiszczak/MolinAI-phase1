#!/usr/bin/env python3
"""Robustness check: run the bot on many past 24-hour windows.

    python3 backtest.py                    # last 60 days, a window every hour
    python3 backtest.py --days 90 --step 30
    python3 backtest.py --save data.csv    # keep the download for re-runs
    python3 backtest.py --load data.csv --set z_entry=2.5 --set min_gap=0.005
    python3 backtest.py --synthetic mr     # offline, simulated prices

Every window is traded exactly like bot.py trades the latest one (same
rules, same 6h warm-up, same forced close), so the share of windows that
pass is an estimate of the chance the rerun passes.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import statistics
import sys
import time

from btcbot.data import Candle, fetch_candles
from btcbot.engine import run
from btcbot.strategy import MIN_TRADES, Params, DipAndBank
from btcbot.synthetic import generate

WINDOW = 24 * 60
WARMUP = 6 * 60


def load_csv(path):
    with open(path, newline="") as f:
        return [Candle(int(r[0]), *map(float, r[1:6])) for r in csv.reader(f) if r and r[0] != "t"]


def save_csv(path, candles):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        w.writerows(candles)


def get_candles(args):
    if args.synthetic:
        n = (args.days * 1440) + WARMUP + WINDOW
        return generate(n, kind=args.synthetic, seed=args.seed), "synthetic (%s, seed %d)" % (args.synthetic, args.seed)
    if args.load:
        return load_csv(args.load), "file " + args.load
    now = int(time.time())
    end = now - now % 60
    start = end - (args.days * 1440 + WINDOW + WARMUP) * 60
    print("Downloading %d days of 1-minute candles (this can take a minute)..." % (args.days + 1))

    def progress(n):
        if n % 10000 < 1000 or not sys.stdout.isatty():
            return
        sys.stdout.write("\r  %d candles" % n)
        sys.stdout.flush()

    candles, source = fetch_candles(start, end, progress=progress)
    print()
    if args.save:
        save_csv(args.save, candles)
        print("Saved to %s" % args.save)
    return candles, source


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=60, help="how many days of windows to test (default 60)")
    ap.add_argument("--step", type=int, default=60, help="minutes between window end times (default 60)")
    ap.add_argument("--save", help="save downloaded candles to CSV")
    ap.add_argument("--load", help="load candles from CSV instead of downloading")
    ap.add_argument("--synthetic", choices=["rw", "mr"], help="use simulated prices (offline)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a strategy parameter")
    args = ap.parse_args()

    params = Params().override(**dict(s.split("=", 1) for s in args.set))
    candles, source = get_candles(args)
    times = [c.t for c in candles]
    strategy = DipAndBank(params).prepare(candles)

    rows = []
    last_t = times[-1]
    first_allowed = times[0] + (WARMUP + WINDOW - 1) * 60
    end_t = last_t
    while end_t >= first_allowed:
        hi = bisect.bisect_right(times, end_t) - 1
        lo = bisect.bisect_left(times, end_t - (WINDOW - 1) * 60)
        res = run(candles, lo, hi, strategy)
        bh_final, _ = res.buy_and_hold()
        kinds = [t.kind for t in res.trades]
        rows.append(dict(
            end=end_t, ret=res.profit_pct, trades=len(res.trades), bh=(bh_final / res.start_cash - 1) * 100,
            ok=res.final_cash > res.start_cash and len(res.trades) >= MIN_TRADES and res.final_btc == 0,
            profit=res.final_cash > res.start_cash, enough=len(res.trades) >= MIN_TRADES,
            probes=kinds.count("probe"), guard=kinds.count("guard"), signal=kinds.count("signal")))
        end_t -= args.step * 60

    n = len(rows)
    if not n:
        sys.exit("Not enough data for a single 24h window.")
    rets = sorted(r["ret"] for r in rows)
    print()
    print("Source:   %s" % source)
    print("Windows:  %d overlapping 24h windows, one every %d min" % (n, args.step))
    if args.set:
        print("Params:   %s" % ", ".join(args.set))
    print()
    print("  PASS all rules (profit, >=5 trades, flat):  %5.1f%%" % pct(sum(r["ok"] for r in rows), n))
    print("  Profitable after fees:                      %5.1f%%" % pct(sum(r["profit"] for r in rows), n))
    print("  At least 5 trades:                          %5.1f%%" % pct(sum(r["enough"] for r in rows), n))
    print("  Return per 24h   mean %+.3f%%  median %+.3f%%  worst %+.3f%%  best %+.3f%%" % (
        statistics.mean(rets), statistics.median(rets), rets[0], rets[-1]))
    print("  Buy-and-hold     mean %+.3f%%  (bot beat it in %.1f%% of windows)" % (
        statistics.mean(r["bh"] for r in rows), pct(sum(r["ret"] > r["bh"] for r in rows), n)))
    print("  Trades per day   mean %.1f  (signal %.1f, guard %.1f, probe %.1f)" % (
        statistics.mean(r["trades"] for r in rows), statistics.mean(r["signal"] for r in rows),
        statistics.mean(r["guard"] for r in rows), statistics.mean(r["probes"] for r in rows)))
    print("  Windows that needed probe trades:           %5.1f%%" % pct(sum(r["probes"] > 0 for r in rows), n))
    for label, sel in (("BTC down > 2%", lambda r: r["bh"] < -2), ("BTC -2%..+2%", lambda r: -2 <= r["bh"] <= 2),
                       ("BTC up > 2%", lambda r: r["bh"] > 2)):
        sub = [r for r in rows if sel(r)]
        if sub:
            print("  %-14s %4d windows: pass %5.1f%%, mean %+.3f%%" % (
                label, len(sub), pct(sum(r["ok"] for r in sub), len(sub)), statistics.mean(r["ret"] for r in sub)))
    print()


if __name__ == "__main__":
    main()
