# -*- coding: utf-8 -*-
"""【2026-10-12】B 类「我方 lead 后弃牌」的下注**路径归因**：
我方主动下注的那一刻，对手在该街是否已经过牌？

  · 对手已过牌 → 走规则12（`_opp_check_bet` + `_check_bet_weight`，下限 0.55）
  · 对手未动   → 走 `_check_side` 的 c-bet/价值/诈唬分支
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
from evaluator import evaluate_7, CATEGORY_NAMES

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"
RANKN = {c: i for i, c in enumerate(PLAT)}


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


def made(hole, board):
    if not hole:
        return "?"
    if len(board) >= 3:
        try:
            return CATEGORY_NAMES.get(evaluate_7(hole + board)[0], "?")
        except Exception:
            return "?"
    r = sorted(c // 4 for c in hole)
    return "口袋对" if r[0] == r[1] else "高牌"


logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))

by_path = collections.defaultdict(lambda: {"n": 0, "net": 0})
by_strength = collections.defaultdict(lambda: {"n": 0, "net": 0})
detail = []

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
                   "opp_checked_street": set(), "my_lead": None, "my_fold": False}
        elif t == "deal_hole" and cur is not None:
            cur["hole"] = [p2i(c) for c in e["holes"][seat]]
        elif t == "deal_board" and cur is not None:
            cur["board"] = [p2i(c) for c in (e.get("board") or [])]
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            st = cur["street"]
            if pl == opp and at == "check":
                cur["opp_checked_street"].add(st)
            if pl == seat and at in ("raise", "allin") and cur["my_lead"] is None:
                cur["my_lead"] = (st, amt, st in cur["opp_checked_street"], list(cur["board"]))
            if pl == seat and at == "fold":
                cur["my_fold"] = True
        elif t == "settle" and cur is not None:
            if cur["my_lead"] and cur["my_fold"]:
                st, amt, opp_checked, bd = cur["my_lead"]
                k = ("规则12路径(对手已过牌)" if opp_checked else "c-bet/主动路径(对手未动)")
                if st == "preflop":
                    k = "翻前开池"
                g = by_path[k]; g["n"] += 1; g["net"] += e["deltas"][seat]
                ms = made(cur["hole"], bd)
                g2 = by_strength[(k, ms)]; g2["n"] += 1; g2["net"] += e["deltas"][seat]
                detail.append((k, tag, cur["hand"], st, amt, ms, e["deltas"][seat]))
            cur = None

print("=== B 类（我方 lead 后弃牌）的路径归因 ===")
for k in sorted(by_path, key=lambda x: -by_path[x]["n"]):
    g = by_path[k]
    print("  %-26s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, g["n"], g["net"], g["net"] / max(1, g["n"])))

print()
print("=== 路径 × 下注时牌力 ===")
for k in sorted(by_strength, key=lambda x: (-by_strength[x]["n"])):
    g = by_strength[k]
    print("  %-26s %-8s %3d 手 | 净变 %+8d | 均 %+7.0f" % (
        k[0], k[1], g["n"], g["net"], g["net"] / max(1, g["n"])))

print()
print("=== 明细（净变升序前 30）===")
for r in sorted(detail, key=lambda x: x[6])[:30]:
    print("  %-26s %-9s 手%-4d %-8s 注%-7d %-6s %8d" % r)
