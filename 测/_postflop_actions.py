# -*- coding: utf-8 -*-
"""【2026-10-12】全量读透：我方「最后一次翻后动作」× 有效牌型 × 该手真实净变。

用**有效牌型**（公面成牌降级，近似 strategy._effective_category），
避免把"公面三条"误当"三条"。
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
    """近似 _effective_category：公面已成的牌型降级（双方共享）。"""
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
        # 我方是否参与了这个对子
        mine = set(c // 4 for c in hole)
        pairs = [r for r, n in cnt.items() if n >= 2]
        if not (mine & set(pairs)):
            return "公面一对"
    return CATEGORY_NAMES.get(cat, "?")


logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))
# ★ 2026-10-12：排除「自对弈」日志（两边 owner_display 都是 j1331）——
#   那些日志无法确定我方座位，会把对手动作误当我方。
_ONLY_REAL = os.environ.get("ONLY_REAL", "") == "1"


def _is_selfplay(path):
    o = json.load(io.open(path, encoding="utf-8"))
    m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    return ("j1331" in da) and ("j1331" in db)


if _ONLY_REAL:
    logs = [p for p in logs if not _is_selfplay(p)]

by_last = collections.defaultdict(lambda: [0, 0])
by_street = collections.defaultdict(lambda: [0, 0])
by_cat = collections.defaultdict(lambda: [0, 0])
river9 = []
call_stats = collections.defaultdict(lambda: [0, 0])   # 我方跟注（按街）

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
                   "last": None, "last_street": None, "last_ctx": None}
        elif t == "deal_hole" and cur is not None:
            cur["hole"] = [p2i(c) for c in e["holes"][seat]]
        elif t == "deal_board" and cur is not None:
            cur["board"] = [p2i(c) for c in (e.get("board") or [])]
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            if pl == seat:
                cur["last"] = at
                cur["last_street"] = cur["street"]
                cur["last_ctx"] = (list(cur["board"]), list(cur["hole"]), amt)
        elif t == "settle" and cur is not None:
            if cur["last"] and cur["last_street"] != "preflop":
                d = e["deltas"][seat]
                cat = eff_cat(cur["last_ctx"][1], cur["last_ctx"][0])
                g = by_last[cur["last"]]; g[0] += 1; g[1] += d
                g2 = by_street[(cur["last_street"], cur["last"])]; g2[0] += 1; g2[1] += d
                g3 = by_cat[cat]; g3[0] += 1; g3[1] += d
                if cur["last"] == "call":
                    g4 = call_stats[cur["last_street"]]; g4[0] += 1; g4[1] += d
                if cur["last_street"] == "river" and cur["last"] == "fold":
                    river9.append((tag, cur["hand"], cat, d, cur["last_ctx"][2],
                                   cur["last_ctx"][0]))
            cur = None

print("=== 我方「最后一次翻后动作」的收益 ===")
for k in sorted(by_last, key=lambda x: -by_last[x][0]):
    n, d = by_last[k]
    print("  %-8s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, n, d, d / max(1, n)))

print()
print("=== 按街 × 动作 ===")
for k in sorted(by_street, key=lambda x: -by_street[x][0]):
    n, d = by_street[k]
    print("  %-8s %-8s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k[0], k[1], n, d, d / max(1, n)))

print()
print("=== 我方跟注（按街）===")
for k in sorted(call_stats, key=lambda x: -call_stats[x][0]):
    n, d = call_stats[k]
    print("  %-8s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, n, d, d / max(1, n)))

print()
print("=== 按有效牌型（我方最后一次翻后动作时）===")
for k in sorted(by_cat, key=lambda x: -by_cat[x][0]):
    n, d = by_cat[k]
    print("  %-12s %3d 手 | 净变 %+8d | 均 %+7.0f" % (k, n, d, d / max(1, n)))

print()
print("=== 弃于 river 的全部 %d 手 ===" % len(river9))
print("  %-9s %4s %-12s %8s %8s" % ("日志", "手", "有效牌型", "净变", "对手注"))
for r in sorted(river9, key=lambda x: x[3]):
    print("  %-9s %4d %-12s %8d %8s" % (r[0], r[1], r[2], r[3], r[4]))
