# -*- coding: utf-8 -*-
"""tail_actions.py — 软尾巴修正对**实际决策**的影响规模（改了几个动作）。"""
import collections
import glob
import io
import json
import os
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
from botbattle_log import load_botbattle             # noqa: E402

LOGS = sorted(set(glob.glob(BASE + "/内容/记录/*botbattle*log.json")
                  + glob.glob("C:/Users/HP/Downloads/botbattle*log.json")))


def seat_of(obj):
    m = obj.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            return i
    return 0


def run(path, tail):
    E.RANGE_SOFT_TAIL = tail
    obj = json.load(open(path, encoding="utf-8"))
    seat = seat_of(obj)
    reqs = load_botbattle(path, my_seat=seat) or []
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    out = []
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
        try:
            a = S.decide(st, model, ctx, debug=False)
            s = json.dumps(a, ensure_ascii=False, sort_keys=True) \
                if isinstance(a, dict) else str(a)
        except Exception as e:
            s = "ERR:" + repr(e)
        out.append((meta.get("hand"), meta.get("street"), s, meta.get("actual")))
    return out


tot = chg = 0
by_street = collections.Counter()
kinds = collections.Counter()
for p in LOGS:
    a0 = run(p, 0.0)
    a1 = run(p, 1.0)
    n = sum(1 for x, y in zip(a0, a1) if x[2] != y[2])
    tot += len(a0)
    chg += n
    for x, y in zip(a0, a1):
        if x[2] != y[2]:
            by_street[x[1]] += 1
            kinds["%s -> %s" % (x[2].split(":")[-1].strip("}\"'"),
                                y[2].split(":")[-1].strip("}\"'"))] += 1
    print("%-46s 决策 %3d  变化 %3d" % (os.path.basename(p)[:46], len(a0), n))

E.RANGE_SOFT_TAIL = 1.0
print()
print("合计决策点 %d，动作变化 %d（%.1f%%）" % (tot, chg, chg * 100.0 / max(tot, 1)))
print("按街分布:", dict(by_street))
print("变化类型 Top10:")
for k, v in kinds.most_common(10):
    print("   %-28s %d" % (k, v))
