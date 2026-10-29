"""One-button web page for the bot (Streamlit).

    pip install -r requirements.txt
    streamlit run app.py

It calls exactly the same code as `python3 bot.py` (bot.run_latest), so the
trades on this page and in the terminal are identical for the same minute.
"""
import io
from contextlib import redirect_stdout
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st

from bot import run_latest
from btcbot.data import FetchError
from btcbot.report import print_report
from btcbot.strategy import MIN_TRADES

st.set_page_config(page_title="BTC Dip & Bank bot", page_icon="📈", layout="wide")


def utc(t):
    return datetime.fromtimestamp(t, tz=timezone.utc)


st.title("BTC/USD paper-trading bot: Dip & Bank")
st.markdown(
    "Replays the **last 24 hours** of 1-minute BTC/USD prices and paper-trades them with "
    "**10,000 USD**: 0.1% fee per buy and per sell, long only, no look-ahead, flat at the end. "
    "It buys short dips, sells at **+0.3%**, and once the day is in profit, it sizes every later "
    "trade so a stop-out can cost at most 30% of that profit."
)

run = st.button("Run on the last 24 hours", type="primary")
st.caption("Each press downloads fresh prices, so the window is always the 24 hours before the click. Takes a few seconds.")

if run:
    notes = []
    with st.spinner("Downloading prices and trading the last 24 hours..."):
        try:
            result, candles, first, source, now, name = run_latest(log=notes.append)
        except FetchError as e:
            st.error("Could not download prices from any public feed.\n\n%s" % e)
            st.stop()
    st.session_state["last"] = (result, candles, first, source, now, name, notes)

if "last" in st.session_state:
    result, candles, first, source, now, name, notes = st.session_state["last"]
    trades = result.trades
    bh_final, bh_move = result.buy_and_hold()
    ok_profit = result.final_cash > result.start_cash
    ok_trades = len(trades) >= MIN_TRADES
    ok_flat = result.final_btc == 0.0

    w0, w1 = result.window_first, result.window_last
    st.subheader("Results")
    st.caption("Run at %s UTC · window %s → %s UTC · feed: %s" % (
        utc(now).strftime("%Y-%m-%d %H:%M"), utc(w0.t).strftime("%Y-%m-%d %H:%M"),
        utc(w1.t + 60).strftime("%Y-%m-%d %H:%M"), source))
    for n in notes:
        st.caption("Note: " + n.strip(" !"))

    c1, c2, c3 = st.columns(3)
    for col, ok, label in ((c1, ok_profit, "Profitable after fees"),
                           (c2, ok_trades, "At least %d trades" % MIN_TRADES),
                           (c3, ok_flat, "Flat at the end (0 BTC)")):
        (col.success if ok else col.error)(("PASS · " if ok else "FAIL · ") + label)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Final balance", "${:,.2f}".format(result.final_cash), "{:+,.2f} USD".format(result.profit))
    m2.metric("Profit", "{:+.3f}%".format(result.profit_pct))
    m3.metric("Trades", len(trades), "%d profitable" % sum(t.pnl > 0 for t in trades), delta_color="off")
    m4.metric("Buy-and-hold (same 24h)", "${:,.2f}".format(bh_final),
              "{:+.3f}% after fees".format((bh_final / result.start_cash - 1) * 100), delta_color="off")

    # Price chart with buys and sells
    window = candles[first:]
    price = pd.DataFrame({"time": [utc(c.t) for c in window], "price": [c.c for c in window]})
    marks = pd.DataFrame(
        [{"time": utc(t.buy_time), "price": t.buy_price, "side": "Buy", "trade": i, "kind": t.kind} for i, t in enumerate(trades, 1)]
        + [{"time": utc(t.sell_time), "price": t.sell_price, "side": "Sell", "trade": i, "kind": t.kind} for i, t in enumerate(trades, 1)])
    lo, hi = price.price.min(), price.price.max()
    pad = (hi - lo) * 0.05 or 1
    base = alt.Chart(price).mark_line(strokeWidth=1.2, color="#7a8699").encode(
        x=alt.X("time:T", title="Time (UTC)"),
        y=alt.Y("price:Q", title="BTC/USD", scale=alt.Scale(domain=[lo - pad, hi + pad])),
        tooltip=[alt.Tooltip("time:T", format="%H:%M"), alt.Tooltip("price:Q", format=",.2f")])
    layers = [base]
    if len(marks):
        layers.append(alt.Chart(marks).mark_point(size=110, filled=True, opacity=0.95).encode(
            x="time:T", y="price:Q",
            shape=alt.Shape("side:N", scale=alt.Scale(domain=["Buy", "Sell"], range=["triangle-up", "triangle-down"])),
            color=alt.Color("side:N", scale=alt.Scale(domain=["Buy", "Sell"], range=["#16a34a", "#dc2626"]), title=None),
            tooltip=["trade:Q", "side:N", "kind:N", alt.Tooltip("time:T", format="%H:%M"), alt.Tooltip("price:Q", format=",.2f")]))
    st.altair_chart(alt.layer(*layers).properties(height=360), width="stretch")

    st.subheader("Trades")
    if trades:
        st.dataframe(pd.DataFrame([{
            "#": i,
            "Buy time (UTC)": utc(t.buy_time).strftime("%Y-%m-%d %H:%M"),
            "Buy price": round(t.buy_price, 2),
            "Sell time (UTC)": utc(t.sell_time).strftime("%Y-%m-%d %H:%M"),
            "Sell price": round(t.sell_price, 2),
            "Size BTC": round(t.qty, 6),
            "Size USD": round(t.cost, 2),
            "Fees USD": round(t.fees, 2),
            "P/L USD": round(t.pnl, 2),
            "P/L %": round(t.pnl_pct, 3),
            "Exit": t.exit_reason,
            "Type": t.kind,
        } for i, t in enumerate(trades, 1)]), hide_index=True, width="stretch")
        if any(t.kind == "probe" for t in trades):
            st.caption("Type 'probe': tiny $25 one-minute trades the bot makes only when needed to reach the "
                       "5-trade minimum. 'guard': smaller trades with relaxed entry rules in the last 6 hours "
                       "when fewer than 5 trades are done.")
    else:
        st.write("No trades.")

    with st.expander("Full text report (identical to `python3 bot.py`)"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_report(result, source, now, name)
        st.code(buf.getvalue(), language=None)

st.divider()
st.caption("Source code, strategy explanation and 90-day backtest: see the repository README. "
           "Paper trading only, no real money.")
