# -*- coding: utf-8 -*-
"""hand=27 决策点2「谁返回了 fold」。"""
import sys, os, json, time, io
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
lines = io.open(r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\strategy.py", encoding="utf-8").read().split("\n")
def mk(store):
    def tr(frame, event, arg):
        if event == "call" and frame.f_code.co_filename.endswith("strategy.py"):
            return lt
        return None
    def lt(frame, event, arg):
        if event == "return":
            store.append((frame.f_code.co_name, frame.f_lineno, repr(arg)[:40],
                          lines[frame.f_lineno-1].strip()[:60]))
        return lt
    return tr
p = r"C:\Users\HP\Downloads\botbattle-holdem-20261015175104-cef0ad86-log.json"
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
n = 0
for req, meta in load_botbattle(p, my_seat=0):
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    if req.get("hand") == 27:
        n += 1
        if n == 2:
            store = []
            sys.settrace(mk(store))
            S._DECISION_STARTED_WALL = time.time()
            a = S.decide(st, m, ctx, debug=False)
            sys.settrace(None)
            print("模型 =", a, "| 日志 =", meta.get("actual"))
            print("=== 调用栈（最内层 fold 在前）===")
            for nm, ln, val, src in store:
                if "'fold'" in val:
                    print("  %-24s 行%-5s %s" % (nm, ln, src))
            print("=== 最外层 ===")
            print("  %-24s 行%-5s" % (store[-1][0], store[-1][1]))
    S._DECISION_STARTED_WALL = time.time()
    S.decide(st, m, ctx, debug=False)
