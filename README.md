<img src="assets/logo.svg" alt="Jakub Kiszczak for Molin AI, Phase 1 task" width="292">

# BTC/USD paper-trading bot — "Dip & Bank"

Replays the last 24 hours of 1-minute BTC/USD candles and paper-trades them
with 10,000 USD, 0.1% fees per side, long only, no look-ahead, and always flat
at the end.

## Run it in the browser (one button)

**Hosted:** <https://molinai-phase1.streamlit.app/> — press **Run on the last 24 hours**.

The page (`app.py`) calls exactly the same function as `python3 bot.py`, so the
trades are identical. It adds a price chart with every buy and sell marked.
To run the page locally: `pip install -r requirements.txt && streamlit run app.py`.

## Run it (locally Mac or Windows)

Prerequisite: **Python 3.9 or newer**. Nothing else: no packages, no API keys.
macOS's own `python3` (from Xcode Command Line Tools) is fine. If `python3`
isn't installed, macOS offers to install it the first time you type it.

```bash
git clone <REPO_URL> https://github.com/jakubkiszczak/molinai
python3 bot.py
```

That's the one command. Every run uses the 24 hours before the moment it runs.

Optional:

```bash
python3 -m unittest -v      # checks the rules (fees, >=5 trades, flat, no look-ahead, 24h window)
python3 backtest.py         # the same bot on every 24h window of the last 60 days (~1 min download)
```

Prices come from **Coinbase BTC-USD** public candles. If Coinbase is
unreachable, the bot falls back to Binance BTCUSDT, then to Binance's public data
mirror. The report always prints which feed it used. If Python's HTTPS
certificates are missing (common on python.org installs), it uses the system
`curl` instead.

## The strategy in a few sentences

- **When it buys:** after a short, sharp dip. Price closes at least 2 standard
  deviations and at least 0.1% below its 60-minute average, and the drop has
  stalled (this minute closed higher than the last). It skips dips when BTC
  has fallen more than 1% over the last 4 hours.
- **When it sells:** as soon as the trade is **+0.3%** (about +0.1% after the
  0.2% round-trip fee). It also sells at a wide disaster stop of -3%, at
  break-even in the last 2 hours, or at the end of the window.
- **What makes it work, the "bank" rule:** until the day is in profit, it
  trades with all its cash. After the first win, every later trade is sized
  so that even a -3% stop can cost at most 30% of the profit made so far.

**Why this should keep working:** it doesn't bet on predicting
direction. It relies on a stable property of BTC: within a day, price
almost always moves more than +0.3% above any given entry at some point. A
small target gets hit most days, and the bank rule keeps later trades from
giving that gain back. Over the last 90 days of 1-minute data this held in
**~84% of all 24h windows**, on both Coinbase and Binance, and equally in the
older 60 days and the most recent 30.

**When it fails, stated honestly:** on a day when BTC slides steadily and
never bounces 0.3% above the entry, the bot holds and loses (the worst window
was -4.3%). The design maximizes the *chance* of a green day, not the average
profit. The average 24h result is slightly negative (-0.12%), because the rare
losing days are larger than the many small winning days. A guaranteed-profitable
long-only bot over *any* 24 hours isn't possible after 0.2% fees, and the data
below shows why.

**Rule safety nets (disclosed):** if fewer than 5 trades are done with 6 hours
left, entry thresholds relax and size drops to at most 25%. If 5 trades
would otherwise be impossible, the bot makes tiny $25 one-minute round trips
in the last minutes (cost: about 5 cents each) so the 5-trade rule always holds.
These filler trades occur in about 75% of windows and are marked `[probe]` in
the output.

## How I got here, and what didn't work

All numbers below come from `backtest.py`: 2,160 overlapping 24h windows (one
every hour) over 90 days of Coinbase 1-minute candles, traded exactly like the
live bot.

1. **Classic mean reversion ("buy the stretch, sell at the average"): it
   failed.** I first measured whether dips bounce at all (`research/edge.py`).
   They do, a little: buying 0.5–0.8% below the 60-minute average beats a random
   entry by roughly +0.1–0.2% gross. But the 0.2% round-trip fee eats all of it.
   Every variant had a negative net average, and the first full version passed
   only **53%** of windows.
2. **Payoff structure instead of prediction.** The question became: what
   maximizes the chance a day ends green? A small fixed target with a wide stop
   raised the pass rate to ~70%. Banking the day after the first win raised it to
   ~82%, and keeping trading on "house money" instead of stopping raised it to
   **~84%**.
3. **Ablations (each changes one thing from the final version):**

   | Variant | Pass rate | Avg 24h result |
   |---|---|---|
   | **Final (Dip & Bank)** | **83.8%** | -0.12% |
   | No bank rule (always 100% size) | 48.7% | -0.41% |
   | Tight stop -1.5% instead of -3% | 80.1% | -0.21% |
   | Target +0.6% instead of +0.3% | 72.6% | -0.08% |
   | Target +1.0% | 61.2% | -0.12% |
   | No 4h slide filter | 83.5% | -0.12% |
   | No dip filter (buy any uptick) | 84.2% | -0.14% |

   Honest takeaway: the **bank rule and the small target do the work**. The dip
   filter barely changes the pass rate. It slightly improves the average result
   and cuts trades, so I kept it.
4. **Out-of-sample and cross-venue checks:** tuned on the older 60 days and
   tested on the newest 30: 84.4% vs 83.7% pass rate. On Binance BTCUSDT data
   for the same 90 days: 84.1%.
5. **By market regime** (Coinbase, 90 days):

   | BTC over the window | Windows | Bot pass rate |
   |---|---|---|
   | Down more than 2% | 215 | 58% |
   | -2% to +2% | 1,755 | 85% |
   | Up more than 2% | 190 | 99.5% |

   Caveat: these 90 days were mostly rising (BTC went from about $64k to
   $81k), so a long bearish stretch would lower the pass rate.

## Output of my run

`python3 bot.py`, run 2026-10-29 15:36 UTC (16:36 Warsaw):

```
Trades
Type 'probe': tiny $25 one-minute trades the bot makes only when needed to reach the 5-trade minimum. 'guard': smaller trades with relaxed entry rules in the last 6 hours when fewer than 5 trades are done.

Full text report (identical to python3 bot.py)

BTC/USD paper-trading bot - Dip & Bank
Run at:  2026-10-29 20:59 UTC
Window:  2026-10-28 20:59 -> 2026-10-29 20:58 UTC (1439 one-minute candles, last 24h)
Feed:    Coinbase BTC-USD (public, no API key)
Start:   10,000.00 USD paper money, fee 0.1% per buy and per sell, long only

#   Buy time (UTC)     Buy price  Sell time (UTC)   Sell price    Size BTC   Size USD    Fees    P/L USD   P/L %  Exit
----------------------------------------------------------------------------------------------------------------------
1   2026-10-29 00:31   81,103.89  2026-10-29 15:09   81,351.11    0.123175   9,990.01   20.01     +10.44  +0.10%  take-profit
2   2026-10-29 16:22   81,365.85  2026-10-29 20:44   78,790.59    0.001202      97.79    0.19      -3.29  -3.36%  stop-loss [guard]
3   2026-10-29 20:49   78,892.10  2026-10-29 20:50   79,209.76    0.000317      24.98    0.05      +0.05  +0.20%  probe closed [probe]
4   2026-10-29 20:51   79,007.50  2026-10-29 20:52   78,908.55    0.000316      24.98    0.05      -0.08  -0.32%  probe closed [probe]
5   2026-10-29 20:53   79,138.09  2026-10-29 20:54   79,018.09    0.000316      24.98    0.05      -0.09  -0.35%  probe closed [probe]
----------------------------------------------------------------------------------------------------------------------

TOTALS
  Trades (buy + closing sell): 5  (2 winners, 3 losers)
  Fees paid:                   20.35 USD
  Final balance:               10,007.04 USD
  Profit:                      +7.04 USD  (+0.070%)
  Buy-and-hold, same 24h:      9,687.67 USD  (-312.33 USD, -3.123% after fees; BTC moved -2.93%)
  Bot vs buy-and-hold:         +319.36 USD

RULES CHECK
  [PASS] Profitable after fees (final balance > 10,000 USD)
  [PASS] At least 5 trades
  [PASS] Flat at the end (0 BTC held)
```

## Project layout

```
bot.py              one-command entry point (the latest 24h)
app.py              one-button web page (Streamlit), same code path as bot.py
backtest.py         same bot on many past 24h windows (robustness)
btcbot/data.py      public candle feeds with fallbacks
btcbot/engine.py    accounting: fees, long-only, forced close at window end
btcbot/strategy.py  Dip & Bank rules (all parameters in one Params class)
btcbot/report.py    trade log, totals, buy-and-hold, rules check
tests/              offline checks of every rule in the brief
research/           the experiments behind the decisions above
```

Implementation notes: each decision at minute *i* uses only candles up to
*i*, and orders fill at that minute's close (the latest known price). The
no-look-ahead test scrambles all future prices and checks that no earlier
decision changes. Six hours of candles before the window are used only to
warm up the 60-minute and 4-hour indicators. No trades happen in that period.
Buy-and-hold buys at the window's first price and sells at its last, with the
same fees.

## AI tools used

- **Claude (Anthropic, Opus 5.5)**: <
  designed and wrote the code with it, ran the backtests and parameter sweeps
  Claude suggested all the solutions step by step and whet wrote the code as well as designed interface. I give all credits to it.
