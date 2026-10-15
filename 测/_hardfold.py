# -*- coding: utf-8 -*-
"""【2026-10-15 v2】优势局(lead>0) 面对下注却 fold —— 直接记录「谁返回了 fold」(+行号+函数名)。

不预设 _face_bet：trace 全部函数，凡是 return 出 {'act':'fold'} 的帧都记下来。
"""
import io, os, sys, ast, json, glob, collections, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle
from evaluator import CATEGORY_NAMES

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
SRC = os.path.join(BASE, "内容", "strategy.py")
src = io.open(SRC, encoding="utf-8").read()
lines = src.split("\n")


def make_tracer(store):
    def tracer(frame, event, arg):
        if event == "call":
            fn = frame.f_code.co_filename
            if fn.endswith("strategy.py"):
                return local_tracer
            return None
        return None

    def local_tracer(frame, event, arg):
        if event == "return" and isinstance(arg, dict) and arg.get("act") == "fold":
            store.append((frame.f_code.co_name, frame.f_lineno,
                          lines[frame.f_lineno - 1].strip()[:70]
                          if frame.f_code.co_filename.endswith("strategy.py") else ""))
        return local_tracer
    return tracer


def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8"))
    m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    if "j1331" in da and "j1331" in db:
        return None
    return 0 if "j1331" in da else 1


logs = sorted(set(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                  + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))

# 记录每次 fold：最内层 fold 帧 / 最外层 fold 帧
inner = collections.Counter()
outer = collections.Counter()
targets = []
for p in logs:
    seat = seat_of(p)
    if seat is None:
        continue
    o = json.load(io.open(p, encoding="utf-8"))
    real = {e["hand"]: e["deltas"][seat] for e in o["replay"]["events"] if e.get("type") == "settle"}
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[18:32]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        lead = st.total_win_chips[st.my_id] - st.total_win_chips[st.opp_id]
        store = []
        sys.settrace(make_tracer(store))
        S._DECISION_STARTED_WALL = time.time()
        a = S.decide(st, m, ctx, debug=False)
        sys.settrace(None)
        if a.get("act") != "fold" or lead <= 0 or int(st.to_call) <= 0:
            continue
        if store:
            inner[(store[0][0], store[0][1])] += 1
            outer[(store[-1][0], store[-1][1])] += 1
        try:
            catn = CATEGORY_NAMES.get(S._effective_category(st), "?")
            top = bool(S._pair_is_top(st)); tier = S._adv_tier(st)
        except Exception:
            catn, top, tier = "?", False, None
        targets.append((tag, req.get("hand"), st.stage, int(st.to_call), int(st.pot),
                        lead, catn, top, tier, real.get(req.get("hand"), 0),
                        store[0][0] if store else "?", store[-1][0] if store else "?"))
        S._DECISION_STARTED_WALL = time.time()

print("=== 优势局(lead>0) 面对下注却 fold：最内层 fold 返回者（行号×次数）===")
for (nm, ln), c in inner.most_common(20):
    print("  %-26s 行%-5s ×%-3d  %s" % (nm, ln, c, lines[ln - 1].strip()[:64]))
print()
print("=== 最外层（最终返回 fold 的帧）===")
for (nm, ln), c in outer.most_common(20):
    print("  %-26s 行%-5s ×%-3d  %s" % (nm, ln, c, lines[ln - 1].strip()[:64]))
print()
print("总计 %d 点 | 整手净变合计 %+d" % (len(targets), sum(t[9] for t in targets)))
print()
print("%-10s %4s %-8s %7s %7s %7s %-9s %-5s %-7s %9s %s" % (
    "日志", "手", "街", "to_call", "pot", "注/池", "牌型", "顶对", "档", "净变", "最内层"))
for t in sorted(targets, key=lambda x: x[9])[:40]:
    print("%-10s %4d %-8s %7d %7d %7.2f %-9s %-5s %-7s %9d %s" % (
        t[0], t[1], t[2], t[3], t[4], t[3] / max(1, t[4]), t[6], t[7], t[8], t[9], t[10]))
