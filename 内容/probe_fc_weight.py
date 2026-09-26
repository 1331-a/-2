# -*- coding: utf-8 -*-
"""probe_fc_weight.py — 离线扫描 future_cost 的权重，找「真正能改变决策」的量级。

背景（实测）：当前 `FUTURE_COST_WEIGHT=0.50 / GAIN=0.50` 只把门槛抬 ~+0.03，
而跟注点「eq 超出门槛」的中位幅度是 **+0.38** → 门槛杠杆完全够不着。
所以问题不是「权重调一点点」，而是**要多大才够**。

做法：用 `WB_FACE_DEBUG=1` 抓的跟注点全景（含 fc / eff_no_fc / eq / 决策），
离线对候选 (WEIGHT, GAIN) 重算 eff_req 与门槛，统计：
  · 决策翻转数（当前 call → 变 fold 的条数）
  · 「本该弃却仍在跟」的收敛情况
并给出「抬升幅度 vs 翻转数」曲线，用来选最小够用的权重。

用法：
  WB_DIAG=1 WB_FACE_DEBUG=1 python sim_early.py 4 aggro 20 > face.txt 2>/dev/null
  python probe_fc_weight.py face.txt
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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


def eff_req_for(r, w, g):
    """按候选 (w, g) 重算 eff_req。fc=0 时保持原状（不动的分支）。"""
    fc = r.get("fc") or 0.0
    base = r.get("eff_no_fc") or r["eff_req"]
    if fc <= 0:
        return base
    to_call = r["to_call"]
    pot = r["pot"]
    cost = w * fc
    gain = g * fc
    return ((to_call + cost) / (pot + to_call + cost + gain))


def main():
    recs = load(sys.argv[1])
    if not recs:
        print("没有记录（需 WB_DIAG=1 + WB_FACE_DEBUG=1）")
        return
    print("=" * 96)
    print("future_cost 权重离线扫描   共 %d 个跟注点" % len(recs))
    print("当前档：WEIGHT=0.50 / GAIN=0.50")
    print("=" * 96)

    base_lift = []
    for r in recs:
        if (r.get("fc") or 0) > 0:
            base_lift.append(eff_req_for(r, 0.5, 0.5) - eff_req_for(r, 0.0, 0.0))
    if base_lift:
        print("当前档抬升：中位 %+.4f  最大 %+.4f（%d/%d 条触发折算）" % (
            statistics.median(base_lift), max(base_lift),
            len(base_lift), len(recs)))

    calls = [r for r in recs if r.get("action") == "call"]
    print("当前 call 共 %d 条，其 eq 超出门槛中位 %+.3f" % (
        len(calls),
        statistics.median([r["eq"] - (r["eff_req"] + r["margin"])
                           for r in calls]) if calls else 0.0))
    print()
    print("%-18s %-10s %-10s %-12s %-12s" % (
        "候选 (W,G)", "抬升中位", "抬升最大", "call→fold", "其中 eq 仍超新门槛"))

    best = None
    for w, g in [(0.5, 0.5), (0.8, 0.4), (1.0, 0.25), (1.0, 0.0),
                 (1.5, 0.0), (2.0, 0.0), (3.0, 0.0)]:
        lifts, flips, flips_bad = [], 0, 0
        for r in recs:
            if (r.get("fc") or 0) > 0:
                lifts.append(eff_req_for(r, w, g) - eff_req_for(r, 0.0, 0.0))
        for r in calls:
            new_thr = eff_req_for(r, w, g) + r["margin"]
            if r["eq"] < new_thr:
                flips += 1
                flips_bad += 0
        print("%-18s %-10.4f %-10.4f %-12s %-12s" % (
            "(%.1f, %.1f)" % (w, g),
            statistics.median(lifts) if lifts else 0.0,
            max(lifts) if lifts else 0.0,
            "%d/%d" % (flips, len(calls)), "—"))
        if best is None and flips > 0:
            best = (w, g, flips)

    print()
    if best:
        print("→ 最小能开始翻转的候选：(W=%.1f, G=%.1f)，翻 %d/%d 个跟注" % best)
    else:
        print("→ 即使 W=3.0 也翻不动任何一个跟注：**门槛杠杆在这些对手上无效**，")
        print("   必须改别的旋钮（eq 口径 / 硬规则 / 权益实现率）。")

    # ============================================================
    #  换个旋钮：权益实现率（implied 打折）——乘法杠杆，比权重有力
    # ============================================================
    print()
    print("=" * 96)
    print("旋钮二：implied（隐含赔率加成）打折 —— 对手越爱连街开火，我方实现率越低")
    print("=" * 96)
    print("  思路：A 的原始版本是**加法**抬门槛（+0.03 量级，够不着 +0.38 的缺口）；")
    print("        而 `implied` 是**乘法**作用在分母上，同样幅度能带来大得多的位移。")
    print("        「跟一手再被赶走」的本质就是**权益实现不足** —— 该体现在 implied 上。")
    print()
    print("%-26s %-10s %-12s %-14s" % ("implied 处理", "抬升中位", "call→fold", "其中强牌误杀"))

    def eff_with_implied(r, w, g, imp_new):
        fc = r.get("fc") or 0.0
        if fc <= 0:
            return None
        to_call = r["to_call"]
        pot = r["pot"]
        cost = w * fc
        gain = g * fc
        if imp_new <= 0:
            return None
        return ((to_call + cost) / (pot + to_call + cost + gain)) / imp_new

    cands = []
    for rho in (1.0, 0.7, 0.5, 0.3, 0.0):
        cands.append(("加成×%.1f（1+(i−1)×rho）" % rho, lambda i, rho=rho: 1.0 + (i - 1.0) * rho))
    for rho in (1.0, 0.9, 0.8, 0.7):
        cands.append(("硬打折 min(i, %.2f)" % rho, lambda i, rho=rho: min(i, rho)))

    for label, fn in cands:
        lifts, flips, strong_kill = [], 0, 0
        for r in recs:
            if (r.get("fc") or 0) <= 0:
                continue
            imp_new = fn(r.get("implied") or 1.0)
            e_old = r["eff_no_fc"]
            e_new = eff_with_implied(r, 0.5, 0.5, imp_new)
            if e_new is None:
                continue
            lifts.append(e_new - e_old)
        for r in calls:
            if (r.get("fc") or 0) <= 0:
                continue
            imp_new = fn(r.get("implied") or 1.0)
            e_new = eff_with_implied(r, 0.5, 0.5, imp_new)
            if e_new is None:
                continue
            if r["eq"] < e_new + r["margin"]:
                flips += 1
                if r.get("strong") or r.get("good"):
                    strong_kill += 1
        print("%-26s %-10.4f %-12s %-14s" % (
            label,
            statistics.median(lifts) if lifts else 0.0,
            "%d/%d" % (flips, len(calls)),
            strong_kill))

    print()
    print("提示：翻转数只是「能否改变决策」，不代表改对。真正的验证要靠")
    print("      sim_early.py --decomp 看前 20 手累积的配对差异。")


if __name__ == "__main__":
    main()
