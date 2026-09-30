# -*- coding: utf-8 -*-
"""对指定手做「两版预测 vs 实际」的逐手对照，并追踪累计比分。"""
import io
import json
import marshal
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

with open(os.path.join(BASE, "测", "_v50_body.bin"), "rb") as f:
    V50 = {"__name__": "v50mod", "__file__": "poker_bot.py"}
    exec(marshal.loads(f.read()), V50)

import strategy as NOW
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

try:
    import equity as EQ
    EQ._rng.seed(20260930)
except Exception:
    pass

LOG = sys.argv[1]
TARGET = [int(x) for x in sys.argv[2:]] or [55, 59, 62]

obj = json.load(open(LOG, encoding="utf-8"))
evs = obj["replay"]["events"]

# ---- 累计比分轨迹 ----
cum = [0, 0]
settle_rows = []
hand = -1
for e in evs:
    if e.get("type") == "hand_start":
        hand = e.get("hand")
    elif e.get("type") == "settle":
        d = e.get("deltas") or [0, 0]
        cum = [cum[0] + int(d[0]), cum[1] + int(d[1])]
        settle_rows.append((hand + 1, list(cum), int(d[0]), int(d[1])))

print("=== 累计比分轨迹（每 5 手采样 + 全押密集段）===")
print("  手   座0累计   座1累计   (座0 本手)")
for (h, c, d0, d1) in settle_rows:
    if h % 5 == 0 or d0 <= -10000 or d0 >= 10000:
        print("  %-4d %8d %8d   %+d" % (h, c[0], c[1], d0))

print()
print("=== 全押密集段逐手（48-62 手，1-based）===")
for (h, c, d0, d1) in settle_rows:
    if 48 <= h <= 62:
        print("  手%-3d 赛前累计 座0=%+6d 座1=%+6d | 本手 %+d / %+d"
              % (h, c[0] - d0, c[1] - d1, d0, d1))

# ---- 逐手两版对照 ----
def act_type(a):
    if a is None:
        return "none"
    if isinstance(a, dict):
        t = str(a.get("act", "")).lower()
    else:
        t = {-1: "fold", -2: "allin", 0: "check"}.get(a, "raise")
    if t in ("allin", "all_in", "shove"):
        return "allin"
    if t in ("raise", "bet"):
        return "raise"
    return t


for seat in (0, 1):
    print()
    print("=" * 74)
    print("### 座位 %d" % seat)
    m50 = V50["OpponentModel"]()
    mnow = O.OpponentModel()
    cnow = M.MatchContext.from_dict(mnow.ctx_dict)
    reqs = load_botbattle(LOG, my_seat=seat)
    print("  手   街      底牌       实际           v50预测        当前版预测   赛前座0累计")
    for req, meta in reqs:
        try:
            st50 = V50["parse_request"](req)
            t50 = act_type(V50["decide"](st50, m50, None))
        except Exception as e:
            t50 = "err"
        try:
            stn = G.parse_request(req)
            try:
                O.build_model_from_history(mnow, req, stn)
            except Exception:
                pass
            try:
                cnow.update(stn)
            except Exception:
                pass
            tnow = act_type(NOW.decide(stn, mnow, cnow, debug=False))
        except Exception:
            tnow = "err"
        h1 = meta.get("hand")
        if h1 in TARGET:
            pre = 0
            for (hh, c, d0, d1) in settle_rows:
                if hh < h1:
                    pre = c[0] - d0
            print("  %-4s %-8s %-10s %-13s %-14s %-14s %+6d"
                  % (h1, meta.get("street"), "/".join(map(str, meta.get("hole") or [])),
                     meta.get("actual"), t50, tnow, pre))
