# -*- coding: utf-8 -*-
"""扫「strong=True 但 eq 偏低」的点 —— 即"用名义上的强牌型（两对）主动造大池"的人群。

strong 的判据（`_postflop_decide`）：(有效牌型 ≥ 两对 且 非 avoid_risk) 或 eq ≥ 0.78
⇒ 若 eq 很低仍 strong，说明**只看牌型、不看胜率**，正是手28（22 on 9d9hTs）的病根。
"""
import sys, os, glob, json, time, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from evaluator import CATEGORY_NAMES
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
TWO_PAIR = 2

logs = sorted(set(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                  + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
rows = []
for p in logs:
    o = json.load(open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    if "j1331" in da and "j1331" in db:
        continue
    seat = 0 if "j1331" in da else 1
    real = {e["hand"]: e["deltas"][seat] for e in o["replay"]["events"] if e.get("type") == "settle"}
    tag = os.path.basename(p)[18:32]
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._DECISION_STARTED_WALL = time.time()
        if len(st.board) >= 3 and int(st.to_call) > 0:
            try:
                cat = S._effective_category(st)
                wp = S.should_avoid_risk(st)
                rp = S._opp_range_pct(m, S._opp_raised_preflop(st), S._opp_street_raises(st))
                eq = S.equity_best(st.hole, st.board, iterations=1500, opp_range_pct=rp,
                                   deadline=S._eq_deadline())
                strong = (cat >= TWO_PAIR and not wp) or eq >= 0.78
                a = S.decide(st, m, ctx, debug=False)
                if strong and eq < 0.50 and cat >= TWO_PAIR:
                    rows.append((tag, req.get("hand"), st.stage, CATEGORY_NAMES.get(cat),
                                 round(float(eq), 3), wp, str(a.get("act")),
                                 real.get(req.get("hand"), 0), int(st.to_call), int(st.pot)))
            except Exception:
                pass
        S._DECISION_STARTED_WALL = time.time()
        S.decide(st, m, ctx, debug=False)

print("「strong 但 eq<0.50」的点 = %d" % len(rows))
hand_delta = {}
for r in rows:
    hand_delta[(r[0], r[1])] = r[7]
print("涉及手数 = %d | 这些手的整手真实净变合计 = %+d" % (len(hand_delta), sum(hand_delta.values())))
print()
c = collections.Counter(r[3] for r in rows)
print("牌型分布:", dict(c))
print("动作分布:", dict(collections.Counter(r[6] for r in rows)))
print()
print("%-14s %4s %-7s %-8s %7s %-6s %-8s %9s %7s %7s" % (
    "日志", "手", "街", "牌型", "eq", "avoid", "动作", "整手净变", "to_call", "pot"))
for r in sorted(rows, key=lambda x: x[7]):
    print("%-14s %4d %-7s %-8s %7.3f %-6s %-8s %9d %7d %7d" % r)
