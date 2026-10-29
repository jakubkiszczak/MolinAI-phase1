# 5-minute Loom outline (not required in the repo — delete before submitting if you like)

**0:00–0:30 · What it is**
Run `python3 bot.py` live on screen. Point to: trade log, totals, buy-and-hold, the three PASS lines.

**0:30–1:30 · The core idea**
- "I don't try to predict direction. Within a day, BTC almost always trades
  more than 0.3% above any given entry at some point."
- Buy a short dip, sell at +0.3% (~+0.1% after fees).
- The bank rule: once the day is green, later trades can lose at most 30%
  of that profit. That turns "one small win" into "a green day".

**1:30–3:00 · How I got there (show research results / README table)**
- Tried classic mean reversion first. Dips bounce only ~0.1–0.2%, and the 0.2% fee eats it. Pass rate 53%.
- Switched the question from "how do I predict?" to "how do I maximise the chance a day ends green?"
- Small target + wide stop: ~70%. Add the bank rule: ~84%. Without the bank rule: 49%.
- Honest: the dip filter barely matters. The payoff structure does the work.

**3:00–4:15 · Why I expect it to keep working, and when it won't**
- 2,160 hourly-shifted 24h windows over 90 days: 84% pass.
- Older 60 days vs newest 30: 84% vs 84%. Binance data instead of Coinbase: 84%.
- Fails on steady down-days with no 0.3% bounce (58% pass when BTC falls >2%).
- The average day is slightly negative. It's built to win often, not to
  make money on average. A long-only bot can't be profitable on *every* 24h
  after 0.2% fees, and that's my answer to "is this possible as set?"

**4:15–5:00 · Rules and engineering**
- The 5-trade safety net: tiny $25 probes, disclosed and marked in the output.
- No look-ahead test (scrambles future prices). Stdlib only, Python 3.9+, feed fallbacks.
