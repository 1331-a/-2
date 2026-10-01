# -*- coding: utf-8 -*-
"""tail_impact.py — 测量「范围软尾巴」修正对胜率估计的影响。

对比三者的均值：
  · 对模型范围（硬截断，旧行为，RANGE_SOFT_TAIL=0）
  · 对模型范围（软尾巴，新行为，RANGE_SOFT_TAIL=1）
  · 对真实底牌（参考基准，由日志的 deal_hole 得知）
若软尾巴让「对模型范围」更接近「对真实底牌」，说明修正在校准方向上。
（注：翻后取样存在「对手牌强→下注大→我方弃牌」的选择偏差，故三者都偏，
  这里只比较**相对**变化。）
"""
import glob
import io
import json
import os
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True,
                              write_through=True)
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"
sys.path.insert(0, BASE + "/内容")

import equity as E                                   # noqa: E402
import strategy as S                                 # noqa: E402
import game_state as G                               # noqa: E402
import opponent as O                                 # noqa: E402
import match_ctx as M                                # noqa: E402
from botbattle_log import load_botbattle, card_to_platform   # noqa: E402

ITERS = 6000
LOGS = sorted(set(glob.glob(BASE + "/内容/记录/*botbattle*log.json")
                  + glob.glob("C:/Users/HP/Downloads/botbattle*log.json")))


def seat_of(obj):
    m = obj.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            return i
    return 0


old, new, act = [], [], []
for p in LOGS:
    obj = json.load(open(p, encoding="utf-8"))
    seat = seat_of(obj)
    opp = 1 - seat
    holes = {}
    for ev in (obj.get("replay") or {}).get("events") or []:
        if ev.get("type") == "deal_hole":
            holes[int(ev.get("hand", -1))] = ev.get("holes") or [[], []]
    reqs = load_botbattle(p, my_seat=seat) or []
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    seen = set()
    for req, meta in reqs:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(model, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        h0 = int(req.get("hand", 0))
        if h0 in seen or not req.get("public_cards"):
            continue
        seen.add(h0)
        hs = holes.get(h0)
        if not hs:
            continue
        oh = [card_to_platform(c) + 8 for c in hs[opp]]
        if any(c is None for c in oh) or len(oh) != 2:
            continue
        hole, board = st.hole, st.board
        rp = float(S._opp_range_pct(model, bool(S._opp_raised_preflop(st)), 0))
        E.RANGE_SOFT_TAIL = 0.0
        e_old = E.monte_carlo_equity(hole, board, iterations=ITERS,
                                     opp_range_pct=rp)
        E.RANGE_SOFT_TAIL = 1.0
        e_new = E.monte_carlo_equity(hole, board, iterations=ITERS,
                                     opp_range_pct=rp)
        e_act = E.equity_best(hole, board, iterations=ITERS,
                              opp_weights={(min(oh), max(oh)): 1.0})
        old.append(e_old)
        new.append(e_new)
        act.append(e_act)
E.RANGE_SOFT_TAIL = 1.0

print("样本 n=%d（8 份日志的翻后决策点，每手一个）\n" % len(old))
print("  对模型范围（硬截断，旧） 均值 = %.4f" % statistics.mean(old))
print("  对模型范围（软尾巴，新） 均值 = %.4f   Δ=%+.4f"
      % (statistics.mean(new), statistics.mean(new) - statistics.mean(old)))
print("  对真实底牌（参考）       均值 = %.4f" % statistics.mean(act))
d_old = statistics.mean(old) - statistics.mean(act)
d_new = statistics.mean(new) - statistics.mean(act)
print("  与真实底牌差距: 硬截断 %+.4f   软尾巴 %+.4f   → %s"
      % (d_old, d_new,
         "改善" if abs(d_new) < abs(d_old) else "变差"))
print("  逐点 eq 变化: 平均 %+.4f  最大 %+.4f  最小 %+.4f"
      % (statistics.mean([n - o for n, o in zip(new, old)]),
         max(n - o for n, o in zip(new, old)),
         min(n - o for n, o in zip(new, old))))
