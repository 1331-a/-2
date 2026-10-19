# -*- coding: utf-8 -*-
"""「面对下注/加注仍跟注」全量审计：钱到底漏在哪种跟注上。

不预设「小注偷」形态，先把所有跟注点摊开，再按「本手我方是否主动下注 / 尺寸」分组：
  · none   —— 本手翻后我方从未主动下注（纯防守跟注）
  · small  —— 我方翻后下过 ≤0.5×底池的小注（"小注偷"后被打）
  · big    —— 我方翻后下过 >0.5×底池的大注

每个跟注点用**对手真实底牌**算精确胜率（只作离线标签），与 required 比较：
  true_eq <  required ⇒ 跟错（这一手确实是负 EV）
  true_eq >= required ⇒ 跟对（未必对范围最优，但这一手不是送）

用法: python 测/_call_leak.py
"""
import collections
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
NAMES = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子",
         5: "同花", 6: "葫芦", 7: "四条", 8: "同花顺"}


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


rows = []
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
        delta = int(x["settle"]["deltas"][seat])
        sb = x["sb"]
        sc = [0, 0]
        sc[sb] = 50
        sc[1 - sb] = 100
        pot = 150
        pnb = 0
        # 本手我方翻后主动下注的最大尺寸（相对当时底池）
        our_bet_ratio = None
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pnb = nb
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)

            if pl == seat and act in ("bet", "raise") and nb >= 3:
                size = amt - sc[pl]
                if size > 0:
                    r = size / float(max(1, pot))
                    our_bet_ratio = max(our_bet_ratio or 0.0, r)

            # 对手下注/加注 → 我方跟注
            if pl == opp and act in ("bet", "raise", "allin"):
                to_call = max(0, amt - sc[seat])
                pot_now = pot + max(0, amt - sc[opp])
                nxt = None
                for z in x["acts"][i + 1:]:
                    if int(z["player"]) == seat and z["_nb"] == nb:
                        nxt = z
                        break
                if (nxt is not None and to_call > 0
                        and str(nxt["action"]).lower() in ("call", "allin")):
                    req = to_call / float(pot_now + to_call)
                    hole = internal(x["holes"][seat])
                    th = internal(x["holes"][opp])
                    bd = internal(x["board"][:nb]) if nb >= 3 else []
                    try:
                        eq = (eq_postflop(hole, bd, th) if nb >= 3
                              else eq_preflop(hole, th))
                    except Exception:
                        eq = None
                    grp = ("none" if our_bet_ratio is None
                           else "small" if our_bet_ratio <= 0.5 else "big")
                    rows.append(dict(
                        m=ident, hand=h + 1, street=nb, pot=pot_now,
                        to_call=to_call, req=round(req, 3),
                        eq=(round(eq, 2) if eq is not None else None),
                        cat=(evaluate_7(hole + bd)[0] if nb >= 3 else -1),
                        grp=grp, delta=delta,
                        resp=str(nxt["action"]).lower()))

            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

valid = [r for r in rows if r["eq"] is not None]
print("「面对下注仍跟注」的点：%d 个（%d 手），可算真值 %d 个"
      % (len(rows), len({(r["m"], r["hand"]) for r in rows}), len(valid)))
print()

print("=== 按「本手我方翻后是否主动下注」分组 ===")
print("%-8s %-5s %-7s %-9s %-12s %-10s" %
      ("组", "n", "跟错", "跟错率", "跟错点净额合计", "占跟错总额"))
bad_all = [r for r in valid if r["eq"] < r["req"]]
bad_hands = {}
for r in bad_all:
    bad_hands[(r["m"], r["hand"])] = r["delta"]
tot_bad = sum(bad_hands.values()) or 1
print("跟错涉及 %d 手，这些手净额合计 %+d（按点合计会重复计）"
      % (len(bad_hands), sum(bad_hands.values())))
for g in ("none", "small", "big"):
    sub = [r for r in valid if r["grp"] == g]
    if not sub:
        continue
    b = [r for r in sub if r["eq"] < r["req"]]
    bh = {}
    for r in b:
        bh[(r["m"], r["hand"])] = r["delta"]
    print("%-8s %-5d %-7d %-8.0f%% %+-12d %-10.0f%%"
          % (g, len(sub), len(b), 100.0 * len(b) / len(sub),
             sum(bh.values()), 100.0 * sum(bh.values()) / tot_bad))
print()

print("=== 按街拆（跟错率 / 跟错点净额）===")
for st in (0, 3, 4, 5):
    sub = [r for r in valid if r["street"] == st]
    if not sub:
        continue
    b = [r for r in sub if r["eq"] < r["req"]]
    print("  %-5s n=%-4d 跟错 %-3d (%-3.0f%%) 净额 %+8d"
          % (STREETS[st], len(sub), len(b), 100.0 * len(b) / len(sub),
             sum(r["delta"] for r in b)))
print()

print("=== 跟错且亏得最多的 15 个点 ===")
print("%-16s %-5s %-5s %-6s %-7s %-6s %-6s %-8s %-6s %-5s"
      % ("对局", "手", "街", "底池", "跟注", "需要", "真实", "牌型", "本手净", "组"))
for r in sorted(bad_all, key=lambda z: z["delta"])[:15]:
    print("%-16s 手%-3d %-5s %-6d %-7d %-6.2f %-6.2f %-8s %+7d %-5s"
          % (r["m"], r["hand"], STREETS.get(r["street"], "?"), r["pot"], r["to_call"],
             r["req"], r["eq"], NAMES.get(r["cat"], "?"), r["delta"], r["grp"]))
print()

print("=== 跟错点的牌型分布 ===")
print("  %s" % dict(collections.Counter(NAMES.get(r["cat"], "?") for r in bad_all)))
print("=== 跟错点的 required 分布 ===")
bnd = collections.Counter()
for r in bad_all:
    x = r["req"]
    bnd["<=0.15" if x <= 0.15 else "0.15-0.25" if x <= 0.25
        else "0.25-0.35" if x <= 0.35 else ">0.35"] += 1
print("  %s" % dict(bnd))
