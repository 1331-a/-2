# -*- coding: utf-8 -*-
"""【2026-10-12】抓出「eq 够却 fold」的点，`_face_bet` 走的是哪条 return。

用 ast 列出 `_face_bet` 内所有 return 行号，再用 sys.settrace 记录该函数实际
命中的最后一行 return ⇒ 即归属分支。
"""
import io, os, sys, ast, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
SRC = os.path.join(BASE, "内容", "strategy.py")

# 1) 找 _face_bet 的行范围与 return 行
src = io.open(SRC, encoding="utf-8").read()
tree = ast.parse(src)
fb = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_face_bet":
        fb = node
        break
START, END = fb.lineno, max(getattr(n, "lineno", 0) for n in ast.walk(fb))
rets = sorted({n.lineno for n in ast.walk(fb) if isinstance(n, ast.Return)})
lines = src.split("\n")
ret_map = {ln: lines[ln - 1].strip()[:70] for ln in rets}
print("_face_bet 范围 %d~%d，return 行 %d 个" % (START, END, len(rets)))

# 2) trace
hits = collections.Counter()
targets = []


def make_tracer(store):
    def tracer(frame, event, arg):
        if event == "call" and frame.f_code.co_name == "_face_bet":
            store["lines"] = []
            return local_tracer
        return None

    def local_tracer(frame, event, arg):
        if event == "line":
            store["lines"].append(frame.f_lineno)
        elif event == "return":
            store["ret"] = store.get("ret", [])
            store["ret"].append(store["lines"][-1] if store["lines"] else None)
            return None
        return local_tracer

    return tracer


logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))


def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8"))
    m0 = o.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


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
        store = {}
        tr = make_tracer(store)
        sys.settrace(tr)
        a = S.decide(st, m, ctx, debug=False)
        sys.settrace(None)
        ri = S._LAST_REQ_INFO
        if not ri or int(st.to_call) <= 0 or a.get("act") != "fold":
            continue
        eq, eff_req, margin = map(float, ri)
        slack = eq - (eff_req + margin)
        if slack < 0:
            continue
        rets_hit = store.get("ret") or []
        last = rets_hit[-1] if rets_hit else None
        # 取最后一个属于 _face_bet 范围的 return 行
        cand = [r for r in rets_hit if r and START <= r <= END]
        ln = cand[-1] if cand else last
        hits[ln] += 1
        targets.append((ln, tag, req.get("hand"), st.stage, int(st.to_call), int(st.pot),
                        eq, slack))

print()
print("=== 28 个点的 return 行归属 ===")
for ln, c in hits.most_common():
    print("  行 %-5d ×%-3d  %s" % (ln, c, ret_map.get(ln, "?")))
print()
print("=== 明细 ===")
for t in sorted(targets, key=lambda x: -x[7]):
    print("  行%-5s %-9s 手%-4d %-7s tc%-6d pot%-6d eq%.3f slack%+.3f  %s" % (
        t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], ret_map.get(t[0], "?")))
