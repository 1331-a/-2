# -*- coding: utf-8 -*-
"""【2026-10-12】修正版：翻后究竟是谁先动 + 我方翻后「跟注」的代价。

★ 关键：所有统计都必须带 player。单挑里翻前 SB 先动、翻后 BB 先动。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
from evaluator import evaluate_7, CATEGORY_NAMES

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"
RANKN = {c: i for i, c in enumerate(PLAT)}


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


def eff_cat(hole, board):
    if not hole:
        return "?"
    if len(board) < 3:
        r = sorted(c // 4 for c in hole)
        return "口袋对" if r[0] == r[1] else "高牌"
    try:
        cat = evaluate_7(hole + board)[0]
    except Exception:
        return "?"
    cnt = collections.Counter(c // 4 for c in board)
    bmax = max(cnt.values()) if cnt else 0
    if bmax >= 3:
        return "公面三条"
    if bmax == 2:
        mine = set(c // 4 for c in hole)
        pairs = [r for r, n in cnt.items() if n >= 2]
        if not (mine & set(pairs)):
            return "公面一对"
    return CATEGORY_NAMES.get(cat, "?")


logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))

first_mover = collections.Counter()
call_cost = collections.defaultdict(lambda: [0, 0, 0])   # 街 -> [手数, 我方跟注总额, 这些手净变]
rows = []

for p in logs:
    o = json.load(io.open(p, encoding="utf-8"))
    m = o["match"]; seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            seat = i
    opp = 1 - seat
    tag = os.path.basename(p)[17:25]
    cur = None
    for e in o["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "street": "preflop", "board": [], "hole": None,
                   "acts": [], "pf_open": None, "folded": False}
        elif t == "deal_hole" and cur is not None:
            cur["hole"] = [p2i(c) for c in e["holes"][seat]]
        elif t == "deal_board" and cur is not None:
            cur["board"] = [p2i(c) for c in (e.get("board") or [])]
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            cur["acts"].append((cur["street"], pl, at, amt))
            if pl == seat and at == "raise" and cur["street"] == "preflop" and cur["pf_open"] is None:
                cur["pf_open"] = amt
            if pl == seat and at == "fold":
                cur["folded"] = True
        elif t == "settle" and cur is not None:
            # 翻后第一条动作是谁？
            for (s, pl, a, am) in cur["acts"]:
                if s != "preflop":
                    first_mover[("我" if pl == seat else "对手", s)] += 1
                    break
            if cur["pf_open"] and cur["folded"]:
                per_street = collections.defaultdict(int)
                for (s, pl, a, am) in cur["acts"]:
                    if pl == seat and a == "call" and s != "preflop":
                        per_street[s] += am
                d = e["deltas"][seat]
                if per_street:
                    for s, v in per_street.items():
                        g = call_cost[s]; g[0] += 1; g[1] += v; g[2] += d
                    rows.append((tag, cur["hand"], sum(per_street.values()), d,
                                 cur["folded"], eff_cat(cur["hole"], cur["board"]),
                                 cur["board"]))
            cur = None

print("=== 翻后谁先动（每手翻后第一条动作）===")
for k in sorted(first_mover, key=lambda x: -first_mover[x]):
    print("  %s 先动 @ %-8s %d 次" % (k[0], k[1], first_mover[k]))

print()
print("=== 我方翻后「跟注」的代价（仅统计翻前开池且最终弃牌的手）===")
for k in sorted(call_cost, key=lambda x: -call_cost[x][0]):
    n, v, d = call_cost[k]
    print("  街%-8s %3d 手 | 我方跟注总额 %6d | 这些手净变 %+8d | 均 %+7.0f" % (
        k, n, v, d, d / max(1, n)))
tot_v = sum(v for _, v, _ in call_cost.values())
print("  合计跟注投入 %d" % tot_v)

print()
print("=== 明细（我方翻后跟注总额最大 20 手）===")
print("  %-9s %4s %8s %8s %-10s %s" % ("日志", "手", "翻后跟注", "净变", "有效牌型", "牌面"))
for r in sorted(rows, key=lambda x: -x[2])[:20]:
    print("  %-9s %4d %8d %8d %-10s %s" % (
        r[0], r[1], r[2], r[3], r[5], ' '.join(PLAT[(c - 8) // 4] + SUIT[(c - 8) % 4] for c in r[6])))
