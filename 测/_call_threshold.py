# -*- coding: utf-8 -*-
"""【2026-10-12】重放：我方「面对下注」的决策点 —— eq 与门槛的差、牌型、结果。

`_face_bet` 会把最近的 (eq, eff_req, margin) 写进 S._LAST_REQ_INFO，
我们在每个决策点后立即读出来 ⇒ 可判断「这次跟注是按门槛该跟，还是不该跟」。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle
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

def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8"))
    m0 = o.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


rows = []
for p in logs:
    seat = seat_of(p)
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[17:25]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._LAST_REQ_INFO = None
        a = S.decide(st, m, ctx, debug=False)
        ri = S._LAST_REQ_INFO
        if ri and int(st.to_call) > 0:
            eq, eff_req, margin = ri
            rows.append({
                "tag": tag, "hand": req.get("hand"), "stage": st.stage,
                "to_call": int(st.to_call), "pot": int(st.pot),
                "act": a.get("act"), "eq": float(eq), "req": float(eff_req),
                "margin": float(margin),
                "slack": float(eq) - (float(eff_req) + float(margin)),
                "cat": eff_cat(st.hole, st.board),
                "ratio": int(st.to_call) / max(st.pot, 1),
            })

print("面对下注的决策点 =", len(rows))
print()
print("=== 按动作 × 牌型 ===")
g = collections.defaultdict(lambda: [0, 0.0])
for r in rows:
    k = (r["act"], r["cat"])
    g[k][0] += 1; g[k][1] += r["slack"]
for k in sorted(g, key=lambda x: -g[x][0])[:20]:
    n, s = g[k]
    print("  %-6s %-10s %3d 次 | 平均余量 %+.3f" % (k[0], k[1], n, s / max(1, n)))

print()
print("=== 我方 call 的点：按余量(slack)分桶 ===")
calls = [r for r in rows if r["act"] == "call"]
print("  call 共 %d 次" % len(calls))
bins = collections.defaultdict(lambda: [0, 0.0])
for r in calls:
    s = r["slack"]
    k = ("<0 (不该跟)" if s < 0 else
         "0~0.05 (勉强)" if s < 0.05 else
         "0.05~0.15" if s < 0.15 else ">0.15 (很够)")
    bins[k][0] += 1; bins[k][1] += s
for k in ("<0 (不该跟)", "0~0.05 (勉强)", "0.05~0.15", ">0.15 (很够)"):
    if k in bins:
        n, s = bins[k]
        print("  %-14s %3d 次 | 平均余量 %+.3f" % (k, n, s / max(1, n)))

print()
print("=== 我方 fold 的点：按余量分桶（负=按门槛本该弃）===")
folds = [r for r in rows if r["act"] == "fold"]
for r in folds:
    s = r["slack"]
    k = ("<0 (该弃)" if s < 0 else ">=0 (本可按门槛跟却弃)")
    bins[k] = bins.get(k, [0, 0.0])
    bins[k][0] += 1; bins[k][1] += s
for k in ("<0 (该弃)", ">=0 (本可按门槛跟却弃)"):
    if k in bins:
        n, s = bins[k]
        print("  %-26s %3d 次 | 平均余量 %+.3f" % (k, n, s / max(1, n)))

print()
print("=== 我方 call 且余量 <0（不该跟）的明细（前 25）===")
print("  %-9s %4s %-8s %7s %7s %7s %8s %-10s" % ("日志", "手", "街", "to_call", "倍池", "eq", "余量", "牌型"))
for r in sorted([x for x in calls if x["slack"] < 0], key=lambda x: x["slack"])[:25]:
    print("  %-9s %4d %-8s %7d %7.2f %7.3f %8.3f %-10s" % (
        r["tag"], r["hand"], r["stage"], r["to_call"], r["ratio"], r["eq"], r["slack"], r["cat"]))
