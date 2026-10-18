# -*- coding: utf-8 -*-
"""2026-10-18 两场（vs 秋十一）专项审计：后期全押 + 对着过牌。

只用日志里的事件（不重放），所以是平台真实行为。
"""
import collections
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

from botbattle_log import card_to_platform            # noqa: E402
from evaluator import evaluate_7                      # noqa: E402
from ranges import hand_percentile                    # noqa: E402

CAT = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子",
       5: "同花", 6: "葫芦", 7: "四条", 8: "同花顺"}
LOGS = ["20261018103549-5d89ed5d", "20261018104218-eaec11b5"]


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def build(ev):
    H, cur = {}, None
    for e in ev:
        t = e.get("type")
        if t == "hand_start":
            cur = {"h": e["hand"], "sb": e.get("sb"), "board": [], "acts": [],
                   "holes": None, "settle": None}
            H[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _nb=len(cur["board"]),
                                    _board=list(cur["board"])))
        elif t == "settle" and cur is not None:
            cur["settle"] = e
            cur = None
    return H


def cat_at(hole, board):
    if len(board) < 3:
        return -1
    ev = evaluate_7(internal(hole) + internal(board))
    return ev[0] if ev else -1


def pot_track(x, seat):
    """返回 [(actor, action, amount, board_len, pot_before, to_call)]"""
    sb = x["sb"]
    sc = [0, 0]
    sc[sb] = 50
    sc[1 - sb] = 100
    pot = 150
    rows = []
    for a in x["acts"]:
        pl = int(a["player"])
        act = a["action"]
        amt = int(a.get("amount") or 0)
        if len(a["_board"]) == 0 and not hasattr(x, "_noop"):
            pass
        to_call = max(0, sc[1 - pl] - sc[pl])
        rows.append((pl, act, amt, len(a["_board"]), pot, to_call, list(a["_board"])))
        if act == "fold":
            continue
        if act == "call":
            sc[pl] += amt
            pot += amt
        elif act in ("raise", "allin"):
            d = amt - sc[pl]
            sc[pl] = amt
            pot += max(0, d)
        # check: 0
    return rows


print("=" * 100)
print("A. 全押总览（我方）")
for n in LOGS:
    o = json.loads((Path.home() / "Downloads" /
                    ("botbattle-holdem-%s-log.json" % n)).read_bytes())
    H = build(o["replay"]["events"])
    print("-" * 100)
    print(n)
    lead = 0
    for h in sorted(H):
        x = H[h]
        if not x["settle"]:
            continue
        d = int(x["settle"]["deltas"][0])
        ours = [a for a in x["acts"] if int(a["player"]) == 0]
        allin = [a for a in ours if a["action"] == "allin"]
        if allin:
            a = allin[0]
            nb = len(a["_board"])
            stage = ["preflop", "flop", "turn", "river"][{0: 0, 3: 1, 4: 2, 5: 3}[nb]]
            c = cat_at(x["holes"][0], a["_board"])
            print("  手%-3d %s 我%-8s 牌型%-4s 全押@%s 净%+7d  lead前%+7d  hl=%d" % (
                h + 1, "", "".join(x["holes"][0]), CAT.get(c, c), stage, d,
                lead, 70 - (h + 1)))
        lead += d

print()
print("=" * 100)
print("B. 双方全程过牌（翻后无人下注）的手")
tot = collections.Counter()
for n in LOGS:
    o = json.loads((Path.home() / "Downloads" /
                    ("botbattle-holdem-%s-log.json" % n)).read_bytes())
    H = build(o["replay"]["events"])
    print("-" * 100)
    print(n)
    for h in sorted(H):
        x = H[h]
        if not x["settle"]:
            continue
        post = [a for a in x["acts"] if len(a["_board"]) >= 3]
        if not post:
            continue
        bets = [a for a in post if a["action"] in ("raise", "allin")]
        reached = len(x["board"]) >= 3
        if bets:
            continue
        d = int(x["settle"]["deltas"][0])
        c = cat_at(x["holes"][0], x["board"])
        pot = int(x["settle"].get("pot") or 0)
        print("  手%-3d 净%+6d 底池%-5d 我%-8s 最终牌型%-4s 牌面%s  动作:%s" % (
            h + 1, d, pot, "".join(x["holes"][0]), CAT.get(c, c),
            " ".join(x["board"]),
            " ".join("%s%d@%d" % ("我" if int(a["player"]) == 0 else "对",
                                  0, len(a["_board"]))
                     for a in post if a["action"] == "check") or ""))
        tot["checkdown"] += 1
        tot["checkdown_net"] += d
        if d == 0:
            tot["split"] += 1
print("\n  合计 check-down 手数 %d，净 %+d，其中平分 %d" %
      (tot["checkdown"], tot["checkdown_net"], tot["split"]))
