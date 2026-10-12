# -*- coding: utf-8 -*-
"""【2026-10-12】正确口径：我方各街真实投入 + 翻后投入的去向。

★ 口径（见项目记忆）：action.amount 对 raise/allin 是**本街 raise-to**，
  对 call 是**本次增量** ⇒ 本街投入 = 最后一次 raise-to 或 call 累加；跨街累加。
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

# 我方在各街的投入（正确口径）
inv_by_street = collections.defaultdict(lambda: [0, 0])   # 街 -> [手数, 投入合计]
hand_rows = []

for p in logs:
    o = json.load(io.open(p, encoding="utf-8"))
    m = o["match"]; seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            seat = i
    tag = os.path.basename(p)[17:25]
    cur = None
    for e in o["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "street": "preflop", "board": [], "hole": None,
                   "sb": [0, 0], "done": {"preflop": 0, "flop": 0, "turn": 0, "river": 0},
                   "last": None, "last_st": None}
        elif t == "deal_hole" and cur is not None:
            cur["hole"] = [p2i(c) for c in e["holes"][seat]]
        elif t == "deal_board" and cur is not None:
            cur["done"][cur["street"]] = cur["sb"][seat]     # 结束本街：落账
            cur["sb"] = [0, 0]                               # 新街清零
            cur["board"] = [p2i(c) for c in (e.get("board") or [])]
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            st = cur["street"]
            if at in ("raise", "allin"):
                cur["sb"][pl] = amt                     # raise-to
            elif at == "call":
                cur["sb"][pl] = cur["sb"][pl] + amt     # 增量
            if pl == seat:
                cur["last"] = at
                cur["last_st"] = st
        elif t == "deal_board" or t == "settle":
            pass
        if t == "settle" and cur is not None:
            if e.get("type") == "settle":
                # 结算：把各街 sb 汇总
                d = e["deltas"][seat]
                # 注意：sb 是本街累计，但街切换时没清零 —— 用「最后值」近似
                cur["done"][cur["street"]] = cur["sb"][seat]
                post_inv = sum(v for k2, v in cur["done"].items() if k2 != "preflop")
                pre_inv = cur["done"]["preflop"]
                for k2, v in cur["done"].items():
                    if v:
                        g = inv_by_street[k2]; g[0] += 1; g[1] += v
                hand_rows.append((tag, cur["hand"], pre_inv, post_inv, d,
                                  cur["last"], cur["last_st"],
                                  eff_cat(cur["hole"], cur["board"])))
            cur = None

print("=== 我方各街真实投入（正确口径）===")
for k in ("preflop", "flop", "turn", "river"):
    n, v = inv_by_street.get(k, [0, 0])
    print("  %-8s %3d 手 | 投入合计 %7d | 均 %5.0f" % (k, n, v, v / max(1, n)))

print()
print("=== 按「翻后总投入」分桶 × 该手净变 ===")
buck = collections.defaultdict(lambda: [0, 0])
for r in hand_rows:
    v = r[3]
    k = "0(无翻后投入)" if v == 0 else ("1~500" if v <= 500 else ("500~1500" if v <= 1500 else ">1500"))
    g = buck[k]; g[0] += 1; g[1] += r[4]
for k in ("0(无翻后投入)", "1~500", "500~1500", ">1500"):
    if k in buck:
        n, d = buck[k]
        print("  %-14s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, n, d, d / max(1, n)))

print()
print("=== 翻后投入 500~1500 的手（★ 均亏最大的桶）===")
print("  %-9s %4s %7s %8s %8s %-8s %-10s" % ("日志", "手", "翻前", "翻后", "净变", "末动作", "有效牌型"))
for r in sorted(hand_rows, key=lambda x: x[4]):
    if 500 <= r[3] <= 1500:
        print("  %-9s %4d %7d %8d %8d %-8s %-10s" % (r[0], r[1], r[2], r[3], r[4], str(r[5]), r[7]))

print()
print("=== 汇总 ===")
print("  总手数 %d | 净变合计 %+d | 有翻后投入的手 %d（投入合计 %d）" % (
    len(hand_rows), sum(r[4] for r in hand_rows),
    sum(1 for r in hand_rows if r[3] > 0),
    sum(r[3] for r in hand_rows)))
