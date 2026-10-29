"""Printing: every trade, totals, buy-and-hold comparison and a rules check."""
from __future__ import annotations

from datetime import datetime, timezone

from .engine import Result
from .strategy import MIN_TRADES


def ts(t: int) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def money(x: float) -> str:
    return "{:,.2f}".format(x)


def signed(x: float) -> str:
    return ("+" if x >= 0 else "-") + money(abs(x))


def print_report(res: Result, source: str, run_at: int, strategy_name: str) -> bool:
    w0, w1 = res.window_first, res.window_last
    print()
    print("BTC/USD paper-trading bot - %s" % strategy_name)
    print("Run at:  %s UTC" % ts(run_at))
    print("Window:  %s -> %s UTC (%d one-minute candles, last 24h)" % (ts(w0.t), ts(w1.t + 60), res.n_candles))
    print("Feed:    %s (public, no API key)" % source)
    print("Start:   %s USD paper money, fee 0.1%% per buy and per sell, long only" % money(res.start_cash))
    print()

    hdr = "%-3s %-16s %11s  %-16s %11s  %10s %10s %7s %10s %7s  %s" % (
        "#", "Buy time (UTC)", "Buy price", "Sell time (UTC)", "Sell price",
        "Size BTC", "Size USD", "Fees", "P/L USD", "P/L %", "Exit")
    print(hdr)
    print("-" * len(hdr))
    for n, t in enumerate(res.trades, 1):
        tag = "" if t.kind == "signal" else " [%s]" % t.kind
        print("%-3d %-16s %11s  %-16s %11s  %10.6f %10s %7s %10s %+6.2f%%  %s%s" % (
            n, ts(t.buy_time), money(t.buy_price), ts(t.sell_time), money(t.sell_price),
            t.qty, money(t.cost), money(t.fees), signed(t.pnl), t.pnl_pct, t.exit_reason, tag))
    if not res.trades:
        print("(no trades)")
    print("-" * len(hdr))

    bh_final, bh_move = res.buy_and_hold()
    fees = sum(t.fees for t in res.trades)
    wins = sum(1 for t in res.trades if t.pnl > 0)
    print()
    print("TOTALS")
    print("  Trades (buy + closing sell): %d  (%d winners, %d losers)" % (len(res.trades), wins, len(res.trades) - wins))
    print("  Fees paid:                   %s USD" % money(fees))
    print("  Final balance:               %s USD" % money(res.final_cash))
    print("  Profit:                      %s USD  (%+.3f%%)" % (signed(res.profit), res.profit_pct))
    print("  Buy-and-hold, same 24h:      %s USD  (%s USD, %+.3f%% after fees; BTC moved %+.2f%%)" % (
        money(bh_final), signed(bh_final - res.start_cash), (bh_final / res.start_cash - 1) * 100, bh_move))
    print("  Bot vs buy-and-hold:         %s USD" % signed(res.final_cash - bh_final))

    ok_profit = res.final_cash > res.start_cash
    ok_trades = len(res.trades) >= MIN_TRADES
    ok_flat = res.final_btc == 0.0
    print()
    print("RULES CHECK")
    print("  [%s] Profitable after fees (final balance > 10,000 USD)" % ("PASS" if ok_profit else "FAIL"))
    print("  [%s] At least %d trades" % ("PASS" if ok_trades else "FAIL", MIN_TRADES))
    print("  [%s] Flat at the end (0 BTC held)" % ("PASS" if ok_flat else "FAIL"))
    print()
    return ok_profit and ok_trades and ok_flat
