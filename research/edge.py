"""Does BTC mean-revert after dips? Forward returns after stretched closes."""
import sys, statistics as st
sys.path.insert(0, ".")
from backtest import load_csv
from btcbot.strategy import _rolling_mean_std
c = load_csv(sys.argv[1]); cl = [x.c for x in c]; n = len(cl)
print("candles", n, "price", cl[0], "->", cl[-1])
# daily range
for L in (30, 60, 120, 240):
    m, s = _rolling_mean_std(cl, L)
    for gap in (0.002, 0.003, 0.005, 0.008):
        for H in (30, 60, 180):
            fw = []; i = L
            while i < n - H:
                g = m[i] / cl[i] - 1
                if g >= gap:
                    fw.append(cl[i + H] / cl[i] - 1 - 0.002)
                    i += H  # non-overlapping
                else:
                    i += 1
            if len(fw) > 20:
                print("SMA%-3d gap>=%.1f%% hold %3dm  n=%4d  mean net %+.3f%%  win %.0f%%" % (L, gap*100, H, len(fw), st.mean(fw)*100, 100*sum(f>0 for f in fw)/len(fw)))
# baseline: random entries
for H in (30, 60, 180):
    fw = [cl[i+H]/cl[i]-1-0.002 for i in range(0, n-H, H)]
    print("RANDOM hold %3dm n=%d mean net %+.3f%% win %.0f%%" % (H, len(fw), st.mean(fw)*100, 100*sum(f>0 for f in fw)/len(fw)))
