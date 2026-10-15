# -*- coding: utf-8 -*-
import sys, os, json, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from evaluator import evaluate_7, CATEGORY_NAMES
p = r"C:\Users\HP\Downloads\botbattle-holdem-20261015175104-cef0ad86-log.json"
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
TARGETS = {("27","preflop"), ("28","preflop"), ("28","flop"), ("28","turn")}
seen = set()
for req, meta in load_botbattle(p, my_seat=0):
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    key = (str(req.get("hand")), st.stage)
    if key in TARGETS and key not in seen:
        seen.add(key)
        S._DECISION_STARTED_WALL = time.time()
        cat = S._effective_category(st)
        outs = S._count_outs(st.hole, st.board)
        rp = S._opp_range_pct(m, S._opp_raised_preflop(st), S._opp_street_raises(st))
        eq = S.equity_best(st.hole, st.board, iterations=8000, opp_range_pct=rp,
                           deadline=S._eq_deadline())
        wp = S.should_avoid_risk(st)
        strong = (cat >= 2 and not wp) or eq >= 0.78
        good = (not strong) and eq >= 0.60
        med = (not good) and eq >= 0.50
        a = S.decide(st, m, ctx, debug=False)
        print("手%-3s %-8s tc%-6s pot%-6s req%.3f | cat=%-8s(原始 %s) outs=%s avoid_risk=%s" % (
            req.get("hand"), st.stage, st.to_call, st.pot,
            st.to_call/float(st.pot+st.to_call), CATEGORY_NAMES.get(cat), 
            CATEGORY_NAMES.get(evaluate_7(list(st.hole)+list(st.board))[0]) if len(st.board)>=3 else "-",
            outs, wp))
        print("        eq=%.4f | strong=%s good=%s medium=%s | adj=%s jumped=%s | 模型=%s  日志=%s" % (
            eq, strong, good, med, S._match_adjust(st), S._OPP_JUMPED, a, meta.get("actual")))
    S._DECISION_STARTED_WALL = time.time()
    S.decide(st, m, ctx, debug=False)
