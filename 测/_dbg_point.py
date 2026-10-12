# -*- coding: utf-8 -*-
"""忠实重放（不跳过任何决策点），对指定手插桩：
  - _stability_mode 返回值
  - _check_side / _check_side_stable 是否被调用、返回什么
  - _opp_check_bet 返回什么
  - opp_checked / lead / 锁赢线
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

path = sys.argv[1]
want = set(int(x) for x in sys.argv[2:])       # req['hand'] (0-based)

LOG = []


def wrap(name, store):
    orig = getattr(S, name)

    def w(*a, **kw):
        r = orig(*a, **kw)
        store.append((name, r))
        return r
    setattr(S, name, w)


for nm in ("_check_side", "_check_side_stable", "_opp_check_bet", "_stability_mode"):
    if hasattr(S, nm):
        wrap(nm, LOG)

o = json.load(io.open(path, encoding="utf-8"))
m0 = o["match"]
seat = 0
for i, k in ((0, "bot_a"), (1, "bot_b")):
    if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
        seat = i

m = O.OpponentModel()
ctx = M.MatchContext.from_dict(m.ctx_dict)
for req, meta in load_botbattle(path, my_seat=seat):
    st = G.parse_request(req)
    try:
        O.build_model_from_history(m, req, st)
    except Exception:
        pass
    try:
        ctx.update(st)
    except Exception:
        pass
    S._DECISION_STARTED_WALL = time.time()
    LOG.clear()
    a = S.decide(st, m, ctx, debug=False)
    h = req.get("hand")
    if h in want:
        try:
            lead = st.total_win_chips[seat] - st.total_win_chips[1 - seat]
        except Exception:
            lead = None
        try:
            hl = S._hands_left(st)
            line = 75 * hl
        except Exception:
            hl, line = None, None
        print("手%-3d %-8s tc%-6d pot%-6d 我=%-12s 模型=%s%-6s | lead=%s 剩手=%s 锁赢线=%s" % (
            h, st.stage, st.to_call, st.pot, meta.get("actual"),
            a.get("act"), a.get("num") or "", lead, hl, line))
        print("     opp_checked=%s  is_button=%s  arch=%s  adj=%s" % (
            S._opp_checked_this_round(st), getattr(st, "is_button", None),
            m.archetype(), S._match_adjust(st)))
        for nm, r in LOG:
            print("     %-20s -> %s" % (nm, r))
