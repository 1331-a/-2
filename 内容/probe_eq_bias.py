# -*- coding: utf-8 -*-
"""probe_eq_bias.py — 定位「A 为何翻不动跟注决策」：门槛不够 vs eq 被高估。

做法：从 `sim_early.py` 的跟注点全景日志（WB_FACE_DEBUG=1）里取记录，
对每条记录做三件事：
  ① 计算「门槛缺口」 gap = eq −(eff_req+margin)：gap>0 却仍然 fold 的，
     说明该 fold 来自**硬规则**（突袭大注等），A 的门槛杠杆根本够不着；
  ② 用**收窄后的对手范围**重算 MC 胜率，量化 eq 被高估多少；
  ③ 统计：fold 决策里有多少条 gap>0（硬规则造成）vs gap<0（门槛造成）。

用法（先跑 sim 抓日志）：
  WB_DIAG=1 WB_FACE_DEBUG=1 python sim_early.py 3 aggro 20 2>face.txt
  python probe_eq_bias.py face.txt
"""
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from equity import monte_carlo_equity          # noqa: E402
from strategy import _opp_range_pct            # noqa: E402


def load(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("FACE "):
                try:
                    out.append(json.loads(line[5:]))
                except Exception:
                    pass
    return out


def main():
    recs = load(sys.argv[1])
    if not recs:
        print("没有记录（确认 WB_DIAG=1 + WB_FACE_DEBUG=1，并把 stderr 重定向到文件）")
        return
    print("=" * 96)
    print("跟注点全景   共 %d 条" % len(recs))
    print("=" * 96)

    # ---- ① 门槛缺口分布 ----
    gaps = []
    above = below = 0
    for r in recs:
        thr = r["eff_req"] + r["margin"]
        g = r["eq"] - thr
        gaps.append(g)
        if g > 0:
            above += 1
        else:
            below += 1
    print("门槛缺口 gap = eq −(eff_req+margin)")
    print("  gap > 0（eq 已过门槛）%d 条    gap ≤ 0（被门槛挡住）%d 条" % (above, below))
    print("  中位 gap %+.3f   最小 %+.3f   最大 %+.3f" % (
        statistics.median(gaps), min(gaps), max(gaps)))

    # ---- ② eq 高估量化：收窄对手范围后重算 ----
    print()
    print("eq 对「对手范围」的敏感度（同一手牌/公面，只改抽样范围）")
    print("%-12s %-10s %-10s %-10s %-10s %s" % (
        "范围系数", "×1.00", "×0.60", "×0.40", "×0.30", "（当前→×0.40 的降幅）"))
    sample = recs[:16]
    drops = {1.00: [], 0.60: [], 0.40: [], 0.30: []}
    rows = []
    for r in sample:
        hole = r.get("hole") or []
        board = r.get("board") or []
        if len(hole) != 2 or len(board) < 3:
            continue
        # 用真实 bot 的口径复算基准范围
        try:
            import opponent as _O
            m = _O.OpponentModel()
            m.preflop_raise = int(r["vpip"] * 10)
            m.preflop_call = int((1 - r["vpip"]) * 10)
            base = _opp_range_pct(m, bool(r.get("i_aggressor")))
        except Exception:
            base = 0.55
        vals = {}
        for k in drops:
            random.seed(7)
            vals[k] = monte_carlo_equity(hole, board, iterations=900,
                                         opp_range_pct=max(0.02, base * k))
            drops[k].append(vals[k])
        rows.append((base, vals, hole, board, r["eq"]))
        print("%-12s %-10.3f %-10.3f %-10.3f %-10.3f %+.3f" % (
            "base=%.2f" % base, vals[1.0], vals[0.6], vals[0.4], vals[0.3],
            vals[0.4] - vals[1.0]))
    if drops[1.0]:
        print("-" * 96)
        print("平均：×1.00 %.3f → ×0.60 %.3f → ×0.40 %.3f → ×0.30 %.3f" % (
            statistics.mean(drops[1.0]), statistics.mean(drops[0.6]),
            statistics.mean(drops[0.4]), statistics.mean(drops[0.3])))
        print("→ 仅把对手范围收窄到 40%%，我方胜率平均下降 **%.3f**" % (
            statistics.mean(drops[1.0]) - statistics.mean(drops[0.4])))

    # ---- ③ fold 的来源分类（只统计真正 fold 的记录） ----
    print()
    print("fold 决策的来源：阈值挡住 vs 硬规则先返回")
    folds = [r for r in recs if r.get("action") == "fold"]
    f_pos = [r for r in folds if r["eq"] - (r["eff_req"] + r["margin"]) > 0]
    f_neg = [r for r in folds if r["eq"] - (r["eff_req"] + r["margin"]) <= 0]
    print("  fold 共 %d 条：gap>0（门槛没挡住、被更早的硬规则弃）%d 条，"
          "gap≤0（门槛正常挡住）%d 条" % (len(folds), len(f_pos), len(f_neg)))
    if f_pos:
        from collections import Counter
        print("    gap>0 的 fold 中位超出门槛 %+.3f → 抬高门槛**无法**挽回这些弃牌"
              % statistics.median([r["eq"] - (r["eff_req"] + r["margin"])
                                    for r in f_pos]))
        print("    牌型 cat 分布：", dict(Counter(r["cat"] for r in f_pos)))
        print("    jumped 分布：", dict(Counter(bool(r.get("jumped"))
                                             for r in f_pos)))
    calls = [r for r in recs if r.get("action") == "call"]
    if calls:
        print("  call 共 %d 条：gap 中位 %+.3f；gap≤0（靠门槛以外分支放行）%d 条"
              % (len(calls),
                 statistics.median([r["eq"] - (r["eff_req"] + r["margin"])
                                    for r in calls]),
                 sum(1 for r in calls
                     if r["eq"] - (r["eff_req"] + r["margin"]) <= 0)))


if __name__ == "__main__":
    main()
