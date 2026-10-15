# -*- coding: utf-8 -*-
"""扫「翻前 to_call > 1000（非全下）却被弃」的点 —— 即"翻前 1000 上限"作用到跟注上的牺牲品。

判据：`_over_limit(state, to_call)` 翻前 = to_call > 1000 且非 doomed 且非 super_hand。
用**日志里对手的真实底牌**算精确胜率 ⇒ 判定"该弃 / 该跟"。
"""
import sys, os, glob, json, time, collections
from itertools import combinations
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from evaluator import evaluate_7, CATEGORY_NAMES
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"
def p2i(s): return PLAT.index(s[0]) * 4 + SUIT.index(s[1]) + 8
def cs(cards): return " ".join(PLAT[(c-8)//4] + SUIT[(c-8)%4] for c in cards)
def exact_vs(hole, board, opp):
    deck = [c for c in range(8, 60) if c not in set(hole) | set(board) | set(opp)]
    need = 5 - len(board)
    if need == 0:
        m, o = evaluate_7(list(hole)+list(board)), evaluate_7(list(opp)+list(board))
        return 1.0 if m > o else (0.5 if m == o else 0.0)
    win = tot = 0
    for combo in combinations(deck, need):
        bd = list(board) + list(combo)
        m, o = evaluate_7(list(hole)+bd), evaluate_7(list(opp)+bd)
        win += 1.0 if m > o else (0.5 if m == o else 0.0); tot += 1
    return win / tot

logs = sorted(set(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                  + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
rows = []
for p in logs:
    o = json.load(open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    if "j1331" in da and "j1331" in db: continue
    seat = 0 if "j1331" in da else 1
    real = {e["hand"]: e["deltas"][seat] for e in o["replay"]["events"] if e.get("type") == "settle"}
    ev = o["replay"]["events"]
    holes = {}
    for e in ev:
        if e.get("type") == "deal_hole":
            holes[e["hand"]] = [p2i(c) for c in e["holes"][1-seat]]
    tag = os.path.basename(p)[18:32]
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._DECISION_STARTED_WALL = time.time()
        if st.stage == "preflop" and int(st.to_call) > 1000 \
                and int(st.to_call) < int(st.my_left):
            a = S.decide(st, m, ctx, debug=False)
            if a.get("act") == "fold":
                oh = holes.get(req.get("hand"))
                need = st.to_call / float(st.pot + st.to_call)
                te = exact_vs(list(st.hole), list(st.board), oh) if oh else None
                rows.append((tag, req.get("hand"), cs(st.hole), cs(oh) if oh else "?",
                             int(st.to_call), int(st.pot), need, te, real.get(req.get("hand"), 0),
                             S._match_adjust(st), S._is_super_hand(st.hole)))
        else:
            S._DECISION_STARTED_WALL = time.time()
            S.decide(st, m, ctx, debug=False)

print("「翻前 to_call>1000（非全下）却弃」= %d 点" % len(rows))
hd = {(r[0], r[1]): r[8] for r in rows}
print("涉及手数 = %d | 整手真实净变合计 = %+d" % (len(hd), sum(hd.values())))
n_ok = n_bad = 0
for r in rows:
    if r[7] is None: continue
    if r[7] >= r[6]: n_ok += 1
    else: n_bad += 1
print("有真值的点：该跟 %d / 该弃 %d" % (n_ok, n_bad))
print()
print("%-14s %4s %-9s %-9s %8s %7s %7s %7s %9s %-10s" % (
    "日志","手","我方","对手","to_call","pot","需eq","真实eq","整手净变","裁决"))
for r in sorted(rows, key=lambda x: x[8]):
    v = "★该跟" if (r[7] is not None and r[7] >= r[6]) else ("该弃" if r[7] is not None else "-")
    te = ("%7.3f" % r[7]) if r[7] is not None else "      -"
    print("%-14s %4d %-9s %-9s %8d %7d %7.3f %s %9d %-10s" % (
        r[0], r[1], r[2], r[3], r[4], r[5], r[6], te, r[8], v))
