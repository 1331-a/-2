# -*- coding: utf-8 -*-
"""对指定日志的指定手，逐决策点打印：
  - 我方实际动作（来自日志）
  - 模型给的最终动作
  - 决策层走的是 `_face_bet` / `_check_side` 的哪一行 return（行级 trace）

用法: python 测/_trace_hand.py <log.json> <hand0> [hand1 ...]
"""
import ast
import io
import json
import os
import sys

sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
SRC = os.path.join(BASE, "内容", "strategy.py")
src = io.open(SRC, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")

FUNCS = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in ("_face_bet", "_check_side", "_lock_win_unified", "_gamble_plan"):
        rets = sorted({n.lineno for n in ast.walk(node) if isinstance(n, ast.Return)})
        FUNCS[node.name] = (node.lineno, max(rets) if rets else node.lineno, set(rets))

print("监控函数:", {k: (v[0], v[1], len(v[2])) for k, v in FUNCS.items()})


def make_tracer(state):
    def tracer(frame, event, arg):
        if event == "call" and frame.f_code.co_name in FUNCS:
            return local(frame.f_code.co_name)
        return None

    def local(fname):
        def lt(frame, event, arg):
            if event == "line":
                state.setdefault(fname, []).append(frame.f_lineno)
            elif event == "return":
                st = state.setdefault(fname, [])
                lo, hi, rets = FUNCS[fname]
                cand = [x for x in st if x in rets]
                if cand:
                    state.setdefault("hit", {})[fname] = cand[-1]
                return None
            return lt
        return lt
    return tracer


def main():
    path = sys.argv[1]
    want = set(int(x) for x in sys.argv[2:])
    o = json.load(io.open(path, encoding="utf-8"))
    m0 = o["match"]
    seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            seat = i
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    print("座位 =", seat)
    for req, meta in load_botbattle(path, my_seat=seat):
        h = req.get("hand")
        if h not in want:
            continue
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        S._DECISION_STARTED_WALL = __import__("time").time()
        state = {}
        sys.settrace(make_tracer(state))
        a = S.decide(st, m, ctx, debug=False)
        sys.settrace(None)
        hit = state.get("hit", {})
        hs = " ".join("%s@%d(%s)" % (k[1:], v, lines[v - 1].strip()[:46])
                      for k, v in hit.items())
        print("手%-3d %-8s nb%-2d tc%-6d pot%-6d 我%-6s -> 模型%-16s %s" % (
            h, st.stage, len(st.board), int(st.to_call), int(st.pot),
            meta.get("actual"), "%s%s" % (a.get("act"), a.get("num") or ""), hs))


if __name__ == "__main__":
    main()
