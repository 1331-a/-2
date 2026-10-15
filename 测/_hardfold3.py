# -*- coding: utf-8 -*-
"""优势局(lead>0)+面对下注+fold：逐点打印 行号/eq/门槛/牌力，供精确设计。"""
import io, os, sys, ast, json, glob, collections, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from evaluator import CATEGORY_NAMES
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
lines = io.open(os.path.join(BASE,"内容","strategy.py"), encoding="utf-8").read().split("\n")

def make_tracer(store):
    def tracer(frame, event, arg):
        if event == "call" and frame.f_code.co_filename.endswith("strategy.py"):
            return lt
        return None
    def lt(frame, event, arg):
        if event == "return" and isinstance(arg, dict) and arg.get("act") == "fold":
            store.append((frame.f_code.co_name, frame.f_lineno))
        return lt
    return tracer

def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display","")); db = str((m0.get("bot_b") or {}).get("owner_display",""))
    if "j1331" in da and "j1331" in db: return None
    return 0 if "j1331" in da else 1

logs = sorted(set(glob.glob(os.path.join(BASE,"内容","记录","*log.json")) + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
rows=[]
for p in logs:
    seat = seat_of(p)
    if seat is None: continue
    o = json.load(io.open(p, encoding="utf-8"))
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[18:32]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req); 
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        lead = st.total_win_chips[st.my_id]-st.total_win_chips[st.opp_id]
        S._LAST_REQ_INFO=None; store=[]
        sys.settrace(make_tracer(store)); S._DECISION_STARTED_WALL=time.time()
        a = S.decide(st, m, ctx, debug=False)
        sys.settrace(None)
        if a.get("act")!="fold" or lead<=0 or int(st.to_call)<=0: continue
        fn, ln = store[0] if store else ("?","?")
        if fn != "_face_bet": continue
        ri = S._LAST_REQ_INFO or (None,None,None)
        eq, eff, mg = (ri if ri[0] is not None else (None,None,None))
        try:
            cat = CATEGORY_NAMES.get(S._effective_category(st),"?")
            nuts = bool(S._has_nuts_or_strong_draw(st)); top = bool(S._pair_is_top(st))
            outs = S._count_outs(st.hole, st.board)
        except Exception: cat,nuts,top,outs="?",False,False,0
        rows.append((ln, tag, req.get("hand"), st.stage, int(st.to_call), int(st.pot),
                     eq, eff, mg, cat, top, nuts, outs, lead))
print("_face_bet 内 fold 点 = %d" % len(rows))
print("%-5s %-10s %4s %-8s %7s %7s %6s %7s %7s %7s %-8s %-5s %-5s %5s" % (
    "行","日志","手","街","to_call","pot","注/池","eq","eff_req","margin","牌型","顶对","nuts","outs"))
for r in sorted(rows, key=lambda x:x[0]):
    ln,tag,h,stg,tc,pot,eq,eff,mg,cat,top,nuts,outs,lead = r
    f = lambda v: ("%7.3f"%v) if isinstance(v,float) else "      -"
    print("%-5s %-10s %4d %-8s %7d %7d %6.2f %s %s %s %-8s %-5s %-5s %5d" % (
        ln,tag,h,stg,tc,pot,tc/max(1,pot),f(eq),f(eff),f(mg),cat,top,nuts,outs))
c = collections.Counter(r[0] for r in rows)
print()
for ln,n in c.most_common(): print("  行%-5s ×%-3d %s" % (ln,n,lines[ln-1].strip()[:70]))
