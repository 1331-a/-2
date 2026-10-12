# -*- coding: utf-8 -*-
"""【2026-10-12】B 类归因：我方 lead 过、且最终弃牌的手（−48,052）到底发生在什么场景。

分类：
  S1 同街：我方 lead → 同一街被对手加注 → 我方在该街弃牌
  S2 跨街：我方在某街 lead（对手跟）→ 后面某街对手下注 → 我方弃牌
  S3 其他：我方 lead 后我方弃牌，但不符合上面（少见）

同时记录：我方弃牌时的 to_call / 底池、我方 lead 时与弃牌时的牌力。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
from evaluator import evaluate_7, CATEGORY_NAMES

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"
SUIT = "cdhs"
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

cats = collections.defaultdict(lambda: {"n": 0, "net": 0})
detail = []
ratio_bins = collections.Counter()
str_bins = collections.Counter()

for p in logs:
    o = json.load(io.open(p, encoding="utf-8"))
    m = o["match"]
    seat = 0
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
                   "acts": [], "my_lead_streets": [], "my_fold_at": None,
                   "opp_bet_before_my_fold": None, "pot_before_fold": 0, "invest": 0}
        elif t == "deal_hole" and cur is not None:
            cur["hole"] = [p2i(c) for c in e["holes"][seat]]
        elif t == "deal_board" and cur is not None:
            cur["board"] = [p2i(c) for c in (e.get("board") or [])]
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            st = cur["street"]
            cur["acts"].append((st, pl, at, amt))
            if pl == seat:
                if at in ("raise", "allin"):
                    if st not in cur["my_lead_streets"]:
                        cur["my_lead_streets"].append(st)
                if at == "fold" and cur["my_fold_at"] is None:
                    cur["my_fold_at"] = st
                    for (st2, pl2, at2, amt2) in reversed(cur["acts"][:-1]):
                        if pl2 == opp and at2 in ("raise", "allin", "bet"):
                            cur["opp_bet_before_my_fold"] = amt2
                            break
                    cur["pot_before_fold"] = sum(
                        a[3] for a in cur["acts"] if a[2] in ("raise", "allin", "call"))
                    cur["board_at_fold"] = list(cur["board"])
            if pl == opp and at in ("raise", "allin"):
                cur["opp_raised_on"] = cur.get("opp_raised_on", [])
                cur["opp_raised_on"].append(st)
        elif t == "settle" and cur is not None:
            if cur["my_lead_streets"] and cur["my_fold_at"]:
                d = e["deltas"][seat]
                lead_st = cur["my_lead_streets"][-1]
                fold_st = cur["my_fold_at"]
                if lead_st == fold_st:
                    # 同街 vs 跨街：我方 lead 后是否"同街被加注"
                    same = False
                    for (st, pl, at, amt) in cur["acts"]:
                        if st == lead_st and pl == seat and at in ("raise", "allin"):
                            same = "lead"
                        elif st == lead_st and pl == opp and at in ("raise", "allin") and same:
                            same = "opp_raised"
                    k = "S1 同街被加注后弃" if same == "opp_raised" else "S1' 同街(未被加注)"
                else:
                    k = "S2 跨街被反超后弃"
                g = cats[k]
                g["n"] += 1
                g["net"] += d
                detail.append((k, tag, cur["hand"], lead_st, fold_st, d,
                               cur.get("opp_bet_before_my_fold"),
                               cur.get("pot_before_fold"),
                               made(cur["hole"], cur.get("board_at_fold") or []),
                               made(cur["hole"], [])))
                ob = cur.get("opp_bet_before_my_fold") or 0
                pb = cur.get("pot_before_fold") or 0
                ratio_bins["to_call/pot %.2f" % (ob / max(pb, 1))] += 1
                str_bins[made(cur["hole"], cur.get("board_at_fold") or [])] += 1
            cur = None

print("=== B 类场景分类 ===")
tot = 0
for k in sorted(cats):
    g = cats[k]
    tot += g["net"]
    print("  %-22s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, g["n"], g["net"], g["net"] / max(1, g["n"])))
print("  合计 %d 手，%+d" % (sum(v["n"] for v in cats.values()), tot))

print()
print("=== 弃牌时 to_call/底池 分布 ===")
for k, v in sorted(ratio_bins.items(), key=lambda x: -x[1]):
    print("  %-22s %3d" % (k, v))

print()
print("=== 弃牌时的牌力分布 ===")
for k, v in sorted(str_bins.items(), key=lambda x: -x[1]):
    print("  %-12s %3d" % (k, v))

print()
print("=== 明细（按净变升序，前 35）===")
print("  %-22s %-8s %4s %-8s %-8s %8s %8s %8s %-8s %s" % (
    "类别", "日志", "手", "lead街", "弃牌街", "净变", "对手注", "底池", "弃时牌力", "lead时"))
for r in sorted(detail, key=lambda x: x[5])[:35]:
    print("  %-22s %-8s %4d %-8s %-8s %8d %8s %8s %-8s %s" % (
        r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
