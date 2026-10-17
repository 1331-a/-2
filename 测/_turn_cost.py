# -*- coding: utf-8 -*-
"""转牌胜率：旧固定前缀精确枚举 vs 新限时加权 MC —— 耗时与精度对照。

只用估计器，不碰策略。用于回答一个具体问题：
把 `_exact_turn` 的限时分支换成 MC 之后，**在预算够用的常见情形下**
我们付出了什么代价（速度 / 精度），在预算耗尽的情形下又换回了什么。
"""
import sys
import time

sys.path.insert(0, "内容")
import equity  # noqa: E402

HOLE = [33, 12]
BOARD = [42, 18, 21, 26]          # 转牌
RP = 0.5049765395348838
ITERS = 30000


def timed(fn):
    t0 = time.time()
    v = fn()
    return v, time.time() - t0


def main():
    exact, te = timed(lambda: equity.exact_equity(HOLE, BOARD, RP,
                                                  deadline=None))
    print("完整枚举(无时限)        value=%.6f  %.2fs" % (exact, te))

    mc = equity.monte_carlo_equity(HOLE, BOARD, iterations=ITERS,
                                   opp_range_pct=RP, deadline=None,
                                   rng=__import__("random").Random(7))
    t0 = time.time()
    mc = equity.monte_carlo_equity(HOLE, BOARD, iterations=ITERS,
                                   opp_range_pct=RP, deadline=None,
                                   rng=__import__("random").Random(7))
    tm = time.time() - t0
    print("MC %d(无时限)        value=%.6f  %.2fs  误差=%+.6f"
          % (ITERS, mc, tm, mc - exact))

    # 有限时（生产口径：deadline = now + 5s）
    v, t = timed(lambda: equity.equity_best(HOLE, BOARD, iterations=ITERS,
                                            opp_range_pct=RP,
                                            deadline=time.time() + 5.0))
    print("equity_best(转牌,deadline=+5s)  value=%.6f  %.2fs  误差=%+.6f"
          % (v, t, v - exact))

    # 预算只剩一点点（旧 bug 的触发场景：0.2s）
    v2, t2 = timed(lambda: equity.equity_best(HOLE, BOARD, iterations=ITERS,
                                              opp_range_pct=RP,
                                              deadline=time.time() + 0.2))
    print("equity_best(转牌,deadline=+0.2s) value=%.6f  %.2fs  误差=%+.6f"
          % (v2, t2, v2 - exact))

    # 预算已耗尽
    v3, t3 = timed(lambda: equity.equity_best(HOLE, BOARD, iterations=ITERS,
                                              opp_range_pct=RP,
                                              deadline=time.time() - 1.0))
    print("equity_best(转牌,已过期)          value=%.6f  %.2fs" % (v3, t3))

    # 旧行为复现：固定牌序前缀（直接按 4 张抽查）
    import equity as E
    deck = [c for c in E.full_deck() if c not in HOLE and c not in BOARD]
    combos, weights, cum, tot = E._build_range(deck, RP, None, None)
    for k in (4, 8, 16, 32, len(deck)):
        w = ti = tt = 0.0
        for r in deck[:k]:
            full = BOARD + [r]
            my = E.evaluate_7(HOLE + full)
            for j in range(len(combos)):
                sc = E.evaluate_7(list(combos[j]) + full)
                if my > sc:
                    w += weights[j]
                elif my == sc:
                    ti += weights[j]
                tt += weights[j]
        print("旧前缀 前%2d 张河牌            value=%.6f" % (k, (w + 0.5 * ti) / tt))


if __name__ == "__main__":
    main()
