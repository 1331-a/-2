# -*- coding: utf-8 -*-
"""用户 10-19 反馈：「小注偷 → 对手加注 → 还硬跟 → 大亏」的真值审计。

筛选：我方翻后主动下注/加注，尺寸 ≤ 0.5×底池（"小注偷"）→ 对手在同一街加注 →
我方**没有弃牌**（call / allin / 再 raise）。对每个决策点：
  · 用对手那一手真实底牌算精确胜率（只作离线标签）；
  · 与当时赔率门槛 required 比较 ⇒ 区分「跟对了」与「跟错了」；
  · 记录本手最终净额（我方座位）。

口径说明（必须随结论引用）：
  · `true_eq` 是「对那一手具体底牌」的胜率，不是对范围的期望 ⇒ 只能当下界证据；
  · 跟错的判据是 `true_eq < required` —— 这一手确实是负 EV；
  · 反过来 `true_eq > required` 不代表对范围也该跟（对手真实牌可能偏弱）。

用法: python 测/_smallbet_raise_call.py
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
from _fold_truth import eq_postflop              # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))

STREETS = ["翻前", "翻牌", "转牌", "河牌"]
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
by_hand = {}

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
        small_bet = False
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pnb = nb
                small_bet = False
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)

            if pl == seat and act in ("bet", "raise", "allin"):
                size = amt - sc[pl]
                small_bet = (nb >= 3 and 0 < size <= 0.5 * pot)

            if pl == opp and act in ("raise", "allin") and small_bet:
                nxt = None
                for z in x["acts"][i + 1:]:
                    if int(z["player"]) == seat and z["_nb"] == nb:
                        nxt = z
                        break
                if nxt is not None and str(nxt["action"]).lower() != "fold":
                    to_call = max(0, amt - sc[seat])
                    pot_now = pot + max(0, amt - sc[opp])
                    if to_call > 0:
                        req = to_call / float(pot_now + to_call)
                        hole = internal(x["holes"][seat])
                        th = internal(x["holes"][opp])
                        bd = internal(x["board"][:nb])
                        try:
                            eq = eq_postflop(hole, bd, th) if nb >= 3 else None
                        except Exception:
                            eq = None
                        rows.append(dict(
                            m=ident, hand=h + 1, street=nb, pot=pot_now,
                            to_call=to_call, req=round(req, 3),
                            eq=(round(eq, 3) if eq is not None else None),
                            resp=str(nxt["action"]).lower(),
                            cat=evaluate_7(hole + bd)[0] if nb >= 3 else -1,
                            delta=delta))
                        by_hand.setdefault((ident, h + 1), []).append(rows[-1])

            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

print("「我方小注(≤0.5池) → 对手加注 → 我方未弃牌」共 %d 次，涉及 %d 手"
      % (len(rows), len(by_hand)))
if not rows:
    raise SystemExit(0)

valid = [r for r in rows if r["eq"] is not None]
bad = [r for r in valid if r["eq"] < r["req"]]
print("其中可算真值 %d 次；**真实胜率 < 赔率门槛（跟错）%d 次（%.0f%%）**"
      % (len(valid), len(bad), 100.0 * len(bad) / max(1, len(valid))))
print()

print("=== 跟错（true_eq < required）明细 ===")
print("%-16s %-5s %-5s %-7s %-7s %-6s %-6s %-8s %-6s"
      % ("对局", "手", "街", "底池", "跟注", "需要", "真实", "牌型", "本手净"))
for r in sorted(bad, key=lambda z: (z["eq"] - z["req"])):
    print("%-16s 手%-3d %-5s %-7d %-7d %-6.2f %-6.3f %-8s %+7d"
          % (r["m"], r["hand"], STREETS[min(3, r["street"])], r["pot"],
             r["to_call"], r["req"], r["eq"], NAMES.get(r["cat"], "?"), r["delta"]))

print()
print("=== 按街拆 ===")
for st in (3, 4):
    sub = [r for r in valid if r["street"] == st]
    if not sub:
        continue
    b = [r for r in sub if r["eq"] < r["req"]]
    print("  %s: n=%-3d 跟错 %-2d (%.0f%%)  跟错手净额合计 %+d"
          % (STREETS[st], len(sub), len(b), 100.0 * len(b) / len(sub),
             sum(r["delta"] for r in b)))

print()
print("=== 跟对（true_eq >= required）但本手仍大亏（< -3000）===")
big = [r for r in valid if r["eq"] >= r["req"] and r["delta"] < -3000]
for r in sorted(big, key=lambda z: z["delta"]):
    print("  %-16s 手%-3d %-5s 需要%.2f 真实%.3f 牌型%-4s 本手%+8d"
          % (r["m"], r["hand"], STREETS[min(3, r["street"])], r["req"],
             r["eq"], NAMES.get(r["cat"], "?"), r["delta"]))
