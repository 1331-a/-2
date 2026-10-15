# -*- coding: utf-8 -*-
"""日志 hand=27（平台第28手，我 KhAs / 对手 QhJh）全部决策点内部量。"""
import sys, os, json, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
p = r"C:\Users\HP\Downloads\botbattle-holdem-20261015175104-cef0ad86-log.json"
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
n = 0
for req, meta in load_botbattle(p, my_seat=0):
    if req.get("hand") != 27:
        S._DECISION_STARTED_WALL = time.time()
        S.decide(st=G.parse_request(req), m=m, ctx=ctx, debug=False) if False else None
        continue
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    n += 1
    S._LAST_REQ_INFO = None
    S._DECISION_STARTED_WALL = time.time()
    cat = S._effective_category(st)
    rp = S._opp_range_pct(m, S._opp_raised_preflop(st), S._opp_street_raises(st))
    eq_short = S.equity_best(st.hole, st.board, iterations=20000, opp_range_pct=rp,
                             deadline=S._eq_deadline(6.0))
    a = S.decide(st, m, ctx, debug=False)
    ri = S._LAST_REQ_INFO
    print("--- 决策点%d  tc=%-6s pot=%-6s req=%.3f | 牌型=%s | adj=%s | OPP_JUMPED=%s" % (
        n, st.to_call, st.pot, st.to_call/float(st.pot+st.to_call), cat,
        S._match_adjust(st), S._OPP_JUMPED))
    print("    eq(短算) = %.4f | _opp_range_pct = %.3f | opp_vpip = %.3f | arch = %s" % (
        eq_short, rp, m.eff_vpip(), m.archetype()))
    if ri is not None:
        print("    _LAST_REQ_INFO: eq=%.4f eff_req=%.4f margin=%.3f  ⇒ 余量 %+.4f" % (
            ri[0], ri[1], ri[2], ri[0] - ri[1] - ri[2]))
    print("    模型 = %s  日志 = %s" % (a, meta.get("actual")))
    S._DECISION_STARTED_WALL = time.time()
    S.decide(st, m, ctx, debug=False)
