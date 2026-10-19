# -*- coding: utf-8 -*-
"""STEAL_GUARD 三臂 A/B：对手爱加注时，把「弱牌小注偷」改成过牌。

A = 开（默认，STEAL_GUARD_ON=True）
B = 关（WB_NO_STEAL_GUARD=1，逐字回到旧行为）
C = 对照（与 A 同配置，测跨进程噪声）

用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/stealguard_ab.py
"""
import glob
import json
import os
import subprocess
import sys

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"

SNIP = r'''
import sys, time, json, glob, os
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
paths = sorted(set(glob.glob(r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json")
                   + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
out = []
for p in paths:
    o = json.load(open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    _owners = [da, db]
    _hits = [i for i, v in enumerate(_owners) if "j1331" in v]
    if len(_hits) == 1:
        seat = _hits[0]
    else:
        _hs = m0.get("human_seat")
        if _hs is None:
            continue
        seat = 1 - int(_hs)
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    try:
        for req, meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            try: O.build_model_from_history(m, req, st)
            except Exception: pass
            try: ctx.update(st)
            except Exception: pass
            S._DECISION_STARTED_WALL = time.time()
            S._LAST_REQ_INFO = None
            a = S.decide(st, m, ctx, debug=False)
            out.append("%s|%s|%s|%s|%s|%s" % (os.path.basename(p)[18:32], req.get("hand"),
                                               st.stage, a.get("act"), a.get("num") or "",
                                               st.to_call))
    except Exception as e:
        out.append("ERR|%s|%s" % (os.path.basename(p)[18:32], repr(e)[:60]))
print(json.dumps(out, ensure_ascii=False))
'''


def arm(env_extra):
    env = dict(os.environ)
    env.update({"WB_MC_ITERS": env.get("WB_MC_ITERS", "1500"),
                "WB_MC_BUDGET": env.get("WB_MC_BUDGET", "0.25")})
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-u", "-X", "utf8", "-c", SNIP],
                         capture_output=True, text=True, env=env,
                         cwd=BASE, timeout=3600)
    txt = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "[]"
    return json.loads(txt)


print("跑 A（开：弱牌小注改过牌）...")
A = arm({})
print("跑 B（关：WB_NO_STEAL_GUARD=1）...")
B = arm({"WB_NO_STEAL_GUARD": "1"})
print("跑 C（对照=与A同）...")
C = arm({})

print("决策点 A/B/C = %d/%d/%d" % (len(A), len(B), len(C)))
ab = [i for i in range(min(len(A), len(B))) if A[i] != B[i]]
ac = [i for i in range(min(len(A), len(C))) if A[i] != C[i]]
print("A vs B 变化 = %d | A vs C（对照噪声）= %d" % (len(ab), len(ac)))
print()
print("=== A(开) vs B(关) 差异点 ===")
for i in ab:
    print("  %-46s  A=%-16s  B=%s"
          % (A[i][:46], "/".join(A[i].split("|")[3:5]), "/".join(B[i].split("|")[3:5])))
print()
noise = set(A[i] for i in ac)
real = [i for i in ab if A[i] not in noise or B[i] not in noise]
print("对照臂也复现的噪声点数 = %d" % len(ac))
print("净效应（变化点 − 噪声点）= %d" % (len(ab) - len(ac)))
