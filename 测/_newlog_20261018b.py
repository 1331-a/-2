# -*- coding: utf-8 -*-
"""2026-10-18 两场专项：C 下注后被反加就弃 / D 我们过牌的时点 / E 对手画像。

全部基于日志事件 + 对手真实底牌做离线标签（只评估，不进预测）。
"""
import collections
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

from botbattle_log import card_to_platform            # noqa: E402
from evaluator import evaluate_7                      # noqa: E402

CAT = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子",
       5: "同花", 6: "葫芦", 7: "四条"}
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


def eq_vs_hole(hole, board, opp, n=4000):
    """翻后精确枚举；翻前抽样。"""
    cardsset = set(hole + board + opp)
    deck = [c for c in range(8, 60) if c not in cardsset]
    if len(board) >= 3:
        wins = tot = 0.0
        for run in combinations(deck, 5 - len(board)):
            bd = board + list(run)
            m = evaluate_7(hole + bd)
            o = evaluate_7(opp + bd)
            wins += 1.0 if m > o else 0.5 if m == o else 0.0
            tot += 1.0
        return wins / tot if tot else 0.5
    import random
    rng = random.Random(7)
    w = 0.0
    for _ in range(n):
        bd = rng.sample(deck, 5)
        m = evaluate_7(hole + bd)
        o = evaluate_7(opp + bd)
        w += 1.0 if m > o else 0.5 if m == o else 0.0
    return w / n


def walk(x, seat):
    """产出 (idx, actor, act, amt, nb, pot_before, to_call, board)"""
    sb = x["sb"]
    sc = [0, 0]
    sc[sb] = 50
    sc[1 - sb] = 100
    pot = 150
    out = []
    prev_nb = 0
    for i, a in enumerate(x["acts"]):
        nb = len(a["_board"])
        if nb != prev_nb:
            sc = [0, 0]
            prev_nb = nb
        pl = int(a["player"])
        act = a["action"]
        amt = int(a.get("amount") or 0)
        to_call = max(0, sc[1 - pl] - sc[pl])
        out.append(dict(i=i, pl=pl, act=act, amt=amt, nb=nb, pot=pot,
                        to_call=to_call, board=list(a["_board"])))
        if act == "fold":
            continue
        if act == "call":
            sc[pl] += amt
            pot += amt
        elif act in ("raise", "allin"):
            d = amt - sc[pl]
            sc[pl] = amt
            pot += max(0, d)
    return out


print("=" * 100)
print("C. 我方翻后下注/加注 → 对手反加 → 我方弃牌（用真实底牌判该不该跟）")
tot = dict(n=0, chips=0, over=0, ok=0, forgone=0.0)
for n in LOGS:
    o = json.loads((Path.home() / "Downloads" /
                    ("botbattle-holdem-%s-log.json" % n)).read_bytes())
    H = build(o["replay"]["events"])
    print("-" * 96)
    print(n)
    for h in sorted(H):
        x = H[h]
        if not x["settle"] or not x["holes"]:
            continue
        seq = walk(x, 0)
        mine = internal(x["holes"][0])
        theirs = internal(x["holes"][1])
        for j, ev in enumerate(seq):
            if ev["pl"] != 0 or ev["act"] not in ("raise", "allin") or ev["nb"] < 3:
                continue
            # 找对手的下一次动作
            nxt = next((z for z in seq[j + 1:] if z["pl"] == 1), None)
            if not nxt or nxt["act"] not in ("raise", "allin"):
                continue
            # 找我们之后是否弃牌
            fol = next((z for z in seq[j + 1:] if z["pl"] == 0 and z["act"] == "fold"), None)
            if not fol:
                continue
            req = fol["to_call"] / float(fol["pot"] + fol["to_call"])
            bd_i = internal(fol["board"])
            eq = eq_vs_hole(mine, bd_i, theirs)
            c = evaluate_7(mine + bd_i)[0]
            d = int(x["settle"]["deltas"][0])
            tag = "弃错" if eq > req else "弃对"
            print("  手%-3d %-6s 我%-7s %-4s 我加%5d→对手%-6s%6d→我弃  需要%.2f 真实%.2f %s 本手净%+6d"
                  % (h + 1, ["pre", "flop", "turn", "river"][{0: 0, 3: 1, 4: 2, 5: 3}[ev["nb"]]],
                     "".join(x["holes"][0]), CAT.get(c, c), ev["amt"],
                     nxt["act"], nxt["amt"], req, eq, tag, d))
            tot["n"] += 1
            tot["chips"] += d
            if eq > req:
                tot["over"] += 1
                tot["forgone"] += (eq - req) * (fol["pot"] + fol["to_call"])
            else:
                tot["ok"] += 1
print("\n  合计 %d 次｜弃错 %d / 弃对 %d｜这些手合计净 %+d｜弃错放弃的底池权益 ≈ %+.0f"
      % (tot["n"], tot["over"], tot["ok"], tot["chips"], tot["forgone"]))

print()
print("=" * 100)
print("D. 我方在「无人下注」（to_call==0）时的选择分布")
for n in LOGS:
    o = json.loads((Path.home() / "Downloads" /
                    ("botbattle-holdem-%s-log.json" % n)).read_bytes())
    H = build(o["replay"]["events"])
    cnt = collections.Counter()
    for h in sorted(H):
        x = H[h]
        if not x["settle"]:
            continue
        for ev in walk(x, 0):
            if ev["pl"] != 0 or ev["to_call"] != 0:
                continue
            cnt[(ev["act"], ev["nb"])] += 1
    print("  %s" % n)
    for k in sorted(cnt, key=lambda z: (z[1], z[0])):
        stage = {0: "翻前", 3: "翻牌", 4: "转牌", 5: "河牌"}.get(k[1], k[1])
        print("     %s to_call=0 → %-6s %d 次" % (stage, k[0], cnt[k]))

print()
print("=" * 100)
print("E. 对手画像（秋十一）：对我方翻后下注的反应")
for n in LOGS:
    o = json.loads((Path.home() / "Downloads" /
                    ("botbattle-holdem-%s-log.json" % n)).read_bytes())
    H = build(o["replay"]["events"])
    cnt = collections.Counter()
    for h in sorted(H):
        x = H[h]
        if not x["settle"]:
            continue
        seq = walk(x, 0)
        for j, ev in enumerate(seq):
            if ev["pl"] != 0 or ev["amt"] == 0 or ev["nb"] < 3:
                continue
            if ev["act"] not in ("raise", "allin"):
                continue
            nxt = next((z for z in seq[j + 1:] if z["pl"] == 1), None)
            if nxt is None:
                cnt["我方下注即收池"] += 1
            else:
                cnt[nxt["act"]] += 1
    print("  %s  %s" % (n, dict(cnt)))
