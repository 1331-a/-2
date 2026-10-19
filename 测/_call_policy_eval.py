# -*- coding: utf-8 -*-
"""政策评估：对「面对下注仍跟注」的点，用**真实胜率**算跟注 EV，比较几条收紧规则。

EV_call = e×pot_now − (1−e)×to_call        （e = 对手真实底牌下的精确胜率）
  · 不含后续街投入 ⇒ 只是**单街下界估计**，用来排序与筛规则，不作上线依据。
  · 基线 = 日志里真实发生的动作（call/allin 记为「跟」）。

候选规则（只收紧，不放宽）：
  R1  对手翻后累计下注/加注 ≥2 且 我方 ≤一对 且 req > 0.25 → 弃
  R2  对手翻后累计下注/加注 ≥2 且 我方 ≤一对 → 要求 req ≤ 0.20 才跟
  R3  我方 ≤一对 且 req > 0.33 → 弃（不看对手次数）

输出每条规则改了哪些点、EV 净变化（按点求和）、以及「误杀」的正 EV 点有多少。

用法: python 测/_call_policy_eval.py
"""
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

from botbattle_log import card_to_platform       # noqa: E402
from evaluator import evaluate_7                 # noqa: E402
from _range_condition_audit import match_seat    # noqa: E402
from _fold_truth import eq_postflop, eq_preflop  # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))

STREETS = {0: "翻前", 3: "翻牌", 4: "转牌", 5: "河牌"}


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def bot_seat(obj):
    s0 = match_seat(obj)
    if s0 is not None:
        return s0
    hs = (obj.get("match") or {}).get("human_seat")
    if hs is not None:
        return 1 - int(hs)
    return None


def build(obj):
    H = {}
    cur = None
    for e in obj["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = dict(h=e["hand"], sb=e.get("sb"), board=[], acts=[],
                       holes=None, settle=None)
            H[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _nb=len(cur["board"])))
        elif t == "settle" and cur is not None:
            cur["settle"] = e
            cur = None
    return H


pts = []
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    opp = 1 - seat
    H = build(obj)
    for h in sorted(H):
        x = H[h]
        if not x["settle"] or not x["holes"]:
            continue
        sb = x["sb"]
        sc = [0, 0]
        sc[sb] = 50
        sc[1 - sb] = 100
        pot = 150
        pnb = 0
        aggr = 0                      # 对手翻后累计下注/加注次数
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pnb = nb
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)

            if pl == opp and act in ("bet", "raise", "allin"):
                if nb >= 1:
                    aggr += 1            # 本手下注后，后续（含本街）计为已开火
                to_call = max(0, amt - sc[seat])
                pot_now = pot + max(0, amt - sc[opp])
                nxt = None
                for z in x["acts"][i + 1:]:
                    if int(z["player"]) == seat and z["_nb"] == nb:
                        nxt = z
                        break
                if (nxt is not None and to_call > 0
                        and str(nxt["action"]).lower() in ("call", "allin")):
                    hole = internal(x["holes"][seat])
                    th = internal(x["holes"][opp])
                    bd = internal(x["board"][:nb]) if nb >= 3 else []
                    try:
                        e = (eq_postflop(hole, bd, th) if nb >= 3
                             else eq_preflop(hole, th))
                    except Exception:
                        e = None
                    if e is not None:
                        pts.append(dict(
                            m=ident, hand=h + 1, street=nb, pot=pot_now,
                            to_call=to_call,
                            req=to_call / float(pot_now + to_call),
                            truth=e, aggr=aggr,
                            cat=(evaluate_7(hole + bd)[0] if nb >= 3 else -1),
                            ev=e * pot_now - (1 - e) * to_call))

            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

print("面对下注仍跟注、可算真值的点：%d（%d 手）" % (len(pts), len({(p["m"], p["hand"]) for p in pts})))
neg = [p for p in pts if p["ev"] < 0]
print("基线里 EV<0 的跟注：%d 个（%.0f%%），合计 EV %+d"
      % (len(neg), 100.0 * len(neg) / len(pts), sum(p["ev"] for p in neg)))
print("基线总 EV：%+d" % sum(p["ev"] for p in pts))
print()

RULES = [
    ("R1 连开≥2 & ≤一对 & req>0.25 → 弃",
     lambda p: p["aggr"] >= 2 and p["cat"] <= 1 and p["req"] > 0.25),
    ("R2 连开≥2 & ≤一对 & req>0.20 → 弃",
     lambda p: p["aggr"] >= 2 and p["cat"] <= 1 and p["req"] > 0.20),
    ("R3 ≤一对 & req>0.33 → 弃",
     lambda p: p["cat"] <= 1 and p["req"] > 0.33),
    ("R4 连开≥2 & 高牌 & req>0.20 → 弃",
     lambda p: p["aggr"] >= 2 and p["cat"] <= 0 and p["req"] > 0.20),
]

print("%-38s %5s %10s %6s %6s" % ("规则", "命中", "EV 净变化", "救对", "误杀"))
for name, f in RULES:
    hit = [p for p in pts if f(p)]
    if not hit:
        print("%-38s %5d %+10d" % (name, 0, 0))
        continue
    # 弃掉 = EV 归零；净变化 = −ΣEV
    delta = -sum(p["ev"] for p in hit)
    saved = sum(1 for p in hit if p["ev"] < 0)
    killed = sum(1 for p in hit if p["ev"] > 0)
    print("%-38s %5d %+10d %6d %6d" % (name, len(hit), delta, saved, killed))

print()
print("=== R1 会改掉的点（逐条）===")
for p in sorted([q for q in pts if RULES[0][1](q)], key=lambda z: z["ev"]):
    print("  %-16s 手%-3d %-5s req=%.2f 真实=%.3f 跟注%-6d EV%+8d 牌型%s 连开%d次"
          % (p["m"], p["hand"], STREETS.get(p["street"], "?"), p["req"],
             p["truth"], p["to_call"], p["ev"],
             {0: "高牌", 1: "一对"}.get(p["cat"], p["cat"]), p["aggr"]))
