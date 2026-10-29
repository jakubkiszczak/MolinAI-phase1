"""Grid search on real data; report in-sample (older) vs out-of-sample (recent)."""
import sys, itertools, bisect, statistics as st
from multiprocessing import Pool
sys.path.insert(0, ".")
from backtest import load_csv
from btcbot.engine import run
from btcbot.strategy import Params, DipAndBank, MIN_TRADES
C = load_csv(sys.argv[1]); T = [c.t for c in C]
SPLIT = T[-1] - 30 * 86400  # last 30 days = out-of-sample
STEP = int(sys.argv[2]) if len(sys.argv) > 2 else 120
def evaluate(kw):
    s = DipAndBank(Params().override(**kw)).prepare(C)
    res = {"is": [], "oos": []}
    e = T[-1]
    while e >= T[0] + (360 + 1439) * 60:
        hi = bisect.bisect_right(T, e) - 1; lo = bisect.bisect_left(T, e - 1439 * 60)
        r = run(C, lo, hi, s)
        ok = r.final_cash > r.start_cash and len(r.trades) >= MIN_TRADES
        res["oos" if e - 1439*60 >= SPLIT else "is"].append((ok, r.profit_pct))
        e -= STEP * 60
    f = lambda L: (100*sum(o for o,_ in L)/len(L), st.mean(x for _,x in L), min(x for _,x in L))
    return kw, f(res["is"]), f(res["oos"])
if __name__ == "__main__":
    grid = eval(sys.argv[3])
    keys = list(grid); combos = [dict(zip(keys, v)) for v in itertools.product(*grid.values())]
    with Pool() as pool:
        out = pool.map(evaluate, combos)
    out.sort(key=lambda r: -r[1][0])
    for kw, a, b in out[:int(sys.argv[4]) if len(sys.argv)>4 else 25]:
        print("IS pass %5.1f%% mean %+.3f%% worst %+.2f%% | OOS pass %5.1f%% mean %+.3f%% worst %+.2f%% | %s" % (*a, *b, kw))
