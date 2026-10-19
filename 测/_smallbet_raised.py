# -*- coding: utf-8 -*-
"""GPT 建议②：小注被加注后弃牌，弃对了吗？

筛选：我方翻后主动下注/加注，尺寸 ≤ 0.5×底池（"小注"）→ 对手在同一街加注 → 我方弃牌。
对每个弃牌点，用**对手那一手真实底牌**算精确胜率（只作离线标签，不作上线依据），
与当时的赔率门槛比较，区分「弃对了」与「弃错了」。

口径说明（务必随结论一起引用）：
  · `true_eq` 是「对那一手具体底牌」的胜率，**不是对范围的期望** ⇒ 只能当下界证据；
  · 若 `true_eq > required` ⇒ 这一手弃掉是负 EV（下界证据），但**不代表对范围也该跟**。

用法: python 测/_smallbet_raised.py
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


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


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
def bot_seat(obj):
    """我方（bot）座位。人机对局用 `human_seat` 反推（`match_seat` 只看 owner 会返回 None）。"""
    s0 = match_seat(obj)
    if s0 is not None:
        return s0
    hs = (obj.get("match") or {}).get("human_seat")
    if hs is not None:
        return 1 - int(hs)
    return None


for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
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
        # 本街我方是否已下过小注
        small_bet = False
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pot = pot            # 底池跨街保留
                pnb = nb
                small_bet = False
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)
            opp = 1 - seat
            if pl == seat and act in ("bet", "raise", "allin"):
                size = amt - sc[pl]
                if nb >= 3 and size > 0 and size <= 0.5 * pot:
                    small_bet = True
                else:
                    small_bet = False
            # 对手在我方小注之后加注，然后我方弃牌
            if pl == opp and act in ("raise", "allin") and small_bet:
                nxt = None
                for z in x["acts"][i + 1:]:
                    if int(z["player"]) == seat and z["_nb"] == nb:
                        nxt = z
                        break
                if nxt is not None and str(nxt["action"]).lower() == "fold":
                    # ★ 必须用**对手这次加注后**的口径：`amt` 是他的 raise-to，
                    #   此时 sc 尚未更新（旧写法 `sc[opp]-sc[seat]` 在对手本街
                    #   首次出手时恒为负 ⇒ 一个点都抓不到，实测 0 次）。
                    to_call = max(0, amt - sc[seat])
                    pot_now = pot + max(0, amt - sc[opp])
                    if to_call > 0:
                        req = to_call / float(pot_now + to_call)
                        hole = internal(x["holes"][seat])
                        th = internal(x["holes"][opp])
                        bd = internal(x["board"][:nb])
                        try:
                            eq = (eq_postflop(hole, bd, th) if nb >= 3
                                  else eq_preflop(hole, th))
                        except Exception:
                            eq = None
                        rows.append(dict(
                            m=ident, hand=h + 1, street=nb, pot=pot_now,
                            to_call=to_call, req=round(req, 3),
                            eq=(round(eq, 3) if eq is not None else None),
                            over=(eq is not None and eq > req),
                            cat=evaluate_7(hole + bd)[0] if nb >= 3 else -1))
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

print("「我方小注 → 对手加注 → 我方弃牌」共 %d 次" % len(rows))
if not rows:
    raise SystemExit(0)
bad = [r for r in rows if r["over"]]
print("其中 **真实胜率 > 赔率门槛**（弃掉的是负 EV）：%d 次（%.0f%%）"
      % (len(bad), 100.0 * len(bad) / len(rows)))
print()
NAMES = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子", 5: "同花", 6: "葫芦"}
print("%-16s %-5s %-7s %-7s %-7s %-7s %-5s" % ("对局", "手", "街", "底池", "跟注", "需要", "真实"))
for r in sorted(rows, key=lambda z: -(z["eq"] or 0) + z["req"]):
    mark = "  ★弃错" if r["over"] else ""
    print("%-16s 手%-3d %-7s %-7d %-7d %-7.2f %-7.2f%s"
          % (r["m"], r["hand"], ["翻前", "翻牌", "转牌", "河牌"][min(3, r["street"])],
             r["pot"], r["to_call"], r["req"],
             (r["eq"] if r["eq"] is not None else -1), mark))
print()
if bad:
    print("弃错的 %d 手，牌型分布：%s"
          % (len(bad), {NAMES.get(c, c): sum(1 for r in bad if r["cat"] == c)
                        for c in sorted({r["cat"] for r in bad})}))
