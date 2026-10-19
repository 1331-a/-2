# -*- coding: utf-8 -*-
"""「小注偷 → 后面被加注 → 还硬跟 → 大亏」的整手级审计。

与 `_smallbet_raise_call.py`（只算**同一街**）不同：本工具按**整手**串起来。
筛选条件（全部满足）：
  ① 本手我方在翻后做过一次 ≤0.5×底池的主动下注（"小注偷"）；
  ② 之后（任意街）我方**面对对手的下注/加注**仍然继续（call / allin / 再 raise）；
  ③ 该决策点算出真实胜率（对手真实底牌，仅离线标签）；
  ④ 本手最终净额为负。

输出：每个「继续点」的 required / true_eq / 牌型，以及它所在手的净额。
按「跟错（true_eq<req）」与「跟对但仍亏」分开看，避免把「运气」当「错误」。

用法: python 测/_smallbet_leak.py
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
hands_total = 0
hands_with_small = 0

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
        hands_total += 1
        delta = int(x["settle"]["deltas"][seat])
        sb = x["sb"]
        sc = [0, 0]
        sc[sb] = 50
        sc[1 - sb] = 100
        pot = 150
        pnb = 0
        small_at = None          # 首次小注的街
        pending = []             # 本手待评估的「面对加注仍继续」点
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pnb = nb
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)

            # 记录我方「小注」的位置
            if pl == seat and act in ("bet", "raise") and nb >= 3:
                size = amt - sc[pl]
                if size > 0 and size <= 0.5 * pot and small_at is None:
                    small_at = nb

            # 对手下注/加注 → 我方如何响应
            if pl == opp and act in ("bet", "raise", "allin"):
                to_call = max(0, amt - sc[seat])
                pot_now = pot + max(0, amt - sc[opp])
                nxt = None
                for z in x["acts"][i + 1:]:
                    if int(z["player"]) == seat and z["_nb"] == nb:
                        nxt = z
                        break
                if nxt is not None and to_call > 0 and nb >= 3:
                    r = str(nxt["action"]).lower()
                    if r in ("call", "raise", "allin"):
                        pending.append(dict(
                            hand=h + 1, street=nb, pot=pot_now,
                            to_call=to_call,
                            req=to_call / float(pot_now + to_call),
                            resp=r))

            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

        if small_at is None:
            continue
        hands_with_small += 1
        hole = internal(x["holes"][seat])
        th = internal(x["holes"][opp])
        for q in pending:
            if q["street"] < small_at:
                continue          # 只算「小注之后」
            bd = internal(x["board"][:q["street"]])
            try:
                eq = eq_postflop(hole, bd, th)
            except Exception:
                eq = None
            rows.append(dict(m=ident, hand=q["hand"], street=q["street"],
                             pot=q["pot"], to_call=q["to_call"],
                             req=round(q["req"], 3),
                             eq=(round(eq, 3) if eq is not None else None),
                             resp=q["resp"],
                             cat=evaluate_7(hole + bd)[0],
                             delta=delta))

print("手数：全部 %d，含「我方翻后小注」%d 手" % (hands_total, hands_with_small))
print("「小注之后、面对加注仍继续」的点：%d 个（%d 手）"
      % (len(rows), len({(r["m"], r["hand"]) for r in rows})))
valid = [r for r in rows if r["eq"] is not None]
bad = [r for r in valid if r["eq"] < r["req"]]
print("可算真值 %d 个；**跟错（true_eq < required）%d 个（%.0f%%）**，"
      "这些手净额合计 %+d"
      % (len(valid), len(bad), 100.0 * len(bad) / max(1, len(valid)),
         sum(r["delta"] for r in bad)))
print()

print("=== 跟错的点（按亏得最多排序）===")
print("%-16s %-5s %-5s %-7s %-7s %-6s %-6s %-8s %-6s %-5s"
      % ("对局", "手", "街", "底池", "跟注", "需要", "真实", "牌型", "本手净", "响应"))
for r in sorted(bad, key=lambda z: z["delta"]):
    print("%-16s 手%-3d %-5s %-7d %-7d %-6.2f %-6.3f %-8s %+7d %-5s"
          % (r["m"], r["hand"], STREETS[min(3, r["street"])], r["pot"],
             r["to_call"], r["req"], r["eq"], NAMES.get(r["cat"], "?"),
             r["delta"], r["resp"]))

print()
print("=== 只看「跟错且本手净额 < -1000」的点会不会扎堆在某个牌型 ===")
heavy = [r for r in bad if r["delta"] < -1000]
import collections
print("  n=%d 牌型分布 %s" % (len(heavy),
      dict(collections.Counter(NAMES.get(r["cat"], "?") for r in heavy))))
print("  按街 %s" % dict(collections.Counter(STREETS[min(3, r["street"])] for r in heavy)))

print()
print("=== 对照：小注后继续、但跟对的点里，大亏（<-3000）有多少 ===")
good = [r for r in valid if r["eq"] >= r["req"] and r["delta"] < -3000]
print("  n=%d" % len(good))
for r in sorted(good, key=lambda z: z["delta"])[:8]:
    print("  %-16s 手%-3d %-5s 需要%.2f 真实%.3f 牌型%-4s 本手%+8d"
          % (r["m"], r["hand"], STREETS[min(3, r["street"])], r["req"],
             r["eq"], NAMES.get(r["cat"], "?"), r["delta"]))
