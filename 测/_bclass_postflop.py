# -*- coding: utf-8 -*-
"""【2026-10-12】B 类「翻前开池且最终弃牌」61 手：翻后到底做了什么？

输出每手的完整动作序列（街/方/动作/金额）+ 我方翻后投入总额 + 该手净变。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
from evaluator import evaluate_7, CATEGORY_NAMES

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"
RANKN = {c: i for i, c in enumerate(PLAT)}


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


def c2s(n):
    return PLAT[(n - 8) // 4] + SUIT[(n - 8) % 4]


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
            if pl == seat and at == "raise" and cur["pf_open"] is None and cur["street"] == "preflop":
                cur["pf_open"] = amt
            if pl == seat and at == "fold":
                cur["folded"] = True
        elif t == "settle" and cur is not None:
            if cur["pf_open"] and cur["folded"]:
                # 翻后我方投入
                post = [(s, a, am) for (s, pl, a, am) in cur["acts"]
                        if pl == seat and s != "preflop"]
                post_inv = sum(am for (_, a, am) in post if a in ("call", "raise", "allin"))
                fold_st = next((s for (s, pl, a, am) in cur["acts"]
                                if pl == seat and a == "fold"), None)
                seq = " ".join("%s:%s%d" % (s[:2], a[:4], am) for (s, pl, a, am) in cur["acts"])
                rows.append((tag, cur["hand"], cur["pf_open"], post_inv, fold_st,
                             e["deltas"][seat], seq,
                             eff_cat(cur["hole"], cur["board"])))
            cur = None

print("共 %d 手（翻前开池且最终弃牌）" % len(rows))
print()
byseq = collections.defaultdict(lambda: [0, 0])
for r in rows:
    post = [(s, a, am) for (s, pl, a, am) in [(x[0], x[1], x[2]) for x in []]]
    # 归类：翻后是否有我方主动投入
    post_acts = [x for x in r[6].split() if x.startswith(("fl:", "tu:", "ri:"))]
    mine = [x for x in post_acts if ":call" in x or ":rais" in x or ":alli" in x]
    k = "翻后我方有投入" if mine else "翻后我方无投入（只弃）"
    byseq[k][0] += 1
    byseq[k][1] += r[5]
print("=== 翻后我方是否有投入 ===")
for k in sorted(byseq, key=lambda x: -byseq[x][0]):
    n, d = byseq[k]
    print("  %-26s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, n, d, d / max(1, n)))

print()
print("=== 明细（净变升序前 25）===")
print("  %-9s %4s %6s %7s %7s %8s  %s" % ("日志", "手", "开池", "翻后投入", "弃于", "净变", "动作序列"))
for r in sorted(rows, key=lambda x: x[5])[:25]:
    print("  %-9s %4d %6d %7d %7s %8d  %s" % (r[0], r[1], r[2], r[3], r[4], r[5], r[6][:78]))
