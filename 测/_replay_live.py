# -*- coding: utf-8 -*-
"""★ 忠实模拟 bot.py 的「活路径」重放。

bot.py 的每一步实际做的是：
    model = OpponentModel.from_json(gdata)      # ← 从平台持久化字符串恢复
    build_model_from_history(model, request, state)
    ctx = MatchContext.from_dict(model.ctx_dict)   # ← ctx 也每步重建
    ctx.update(state); ctx.sync_baseline(state)
    action = decide(...)
    resp = _final_guard(state, _to_response(action))
    model.ctx_dict = ctx.to_dict(); gdata = model.to_json()

而此前所有探针/AB 用的是「内存里一直带着同一个 model/ctx、且不调 sync_baseline」
—— 两者可能不等价。本脚本按活路径跑，逐点与日志实际动作比对。

用法: python 测/_replay_live.py <log.json> [--naive]    (--naive 用旧的简写路径)
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import bot as B               # noqa: E402  （复用 _to_response / _final_guard）
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

_ACT2RESP = {"fold": -1, "call": 0, "check": 0, "allin": -2}


def log_resp(raw):
    """日志实际动作 -> response 整数。"""
    parts = str(raw or "").split()
    if not parts:
        return None
    a = parts[0]
    if a in _ACT2RESP:
        return _ACT2RESP[a]
    if a in ("raise", "bet") and len(parts) > 1:
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def main():
    path = sys.argv[1]
    naive = "--naive" in sys.argv
    o = json.load(io.open(path, encoding="utf-8"))
    m0 = o["match"]
    seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            seat = i

    gdata = ""
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    n = mism = 0
    bad = []
    for req, meta in load_botbattle(path, my_seat=seat):
        st = G.parse_request(req)
        S._DECISION_STARTED_WALL = time.time()
        if naive:
            O.build_model_from_history(model, req, st)
            try:
                ctx.update(st)
            except Exception:
                pass
            a = S.decide(st, model, ctx, debug=False)
            resp = B._final_guard(st, B._to_response(a))
        else:
            model = O.OpponentModel.from_json(gdata)        # ★ 每步从持久化恢复
            O.build_model_from_history(model, req, st)
            ctx = M.MatchContext.from_dict(model.ctx_dict)  # ★ ctx 也每步重建
            try:
                ctx.update(st)
            except Exception:
                pass
            try:
                ctx.sync_baseline(st)
            except Exception:
                pass
            a = S.decide(st, model, ctx, debug=False)
            resp = B._final_guard(st, B._to_response(a))
            model.ctx_dict = ctx.to_dict()
            gdata = model.to_json()

        want = log_resp(meta.get("actual"))
        n += 1
        if want is not None and resp != want:
            mism += 1
            bad.append((meta.get("hand"), st.stage, st.to_call, st.pot,
                        meta.get("actual"), resp))

    tag = "简写路径(旧)" if naive else "活路径(仿 bot.py)"
    print("%s: 决策点=%d 不一致=%d (%.1f%%)" % (tag, n, mism, 100.0 * mism / max(1, n)))
    for h, stg, tc, pot, raw, got in bad[:14]:
        print("   手%-3s %-8s tc%-6s pot%-6s 日志=%-14s 重放resp=%s" % (h, stg, tc, pot, raw, got))


if __name__ == "__main__":
    main()
