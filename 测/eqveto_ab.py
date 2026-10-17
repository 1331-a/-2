# -*- coding: utf-8 -*-
"""EQ_VETO 三臂 A/B：开 / 关 / 重复开（对照）。

背景（2026-10-17 外部审计指出、已核对成立）：
  `_LAST_REQ_INFO` 原先在「突袭修正」**之前**取快照，而突袭分支会
  `eq -= 0.15`、`eff_req += 0.10` ⇒ 否决权比决策层乐观 0.25。
  已把快照挪到修正之后。本脚本量化「否决权到底改了多少点、其中多少是突袭点」。

用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/eqveto_ab.py
"""
import os
import subprocess

BASE = r'C:\Users\HP\WorkBuddy\德扑双人机器人测试'
PYEXE = r'C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe'

SNIP = r'''
import sys, time, json, glob, os
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
paths = sorted(set(glob.glob(os.path.join(BASE,"内容","记录","*log.json"))
                   + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
out = []
for p in paths:
    o = json.load(open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display",""))
    db = str((m0.get("bot_b") or {}).get("owner_display",""))
    if "j1331" in da and "j1331" in db: continue
    seat = 0 if "j1331" in da else 1
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
            jumped = 1 if S._OPP_JUMPED else 0
            out.append("%s|%s|%s|%s|%s|%s" % (os.path.basename(p)[18:32],
                       req.get("hand"), st.stage, a.get("act"),
                       a.get("num") or "", jumped))
    except Exception as e:
        out.append("ERR|%s|%s" % (os.path.basename(p)[18:32], repr(e)[:60]))
print("\n".join(out))
'''
with open(os.path.join(BASE, '测', '_ev_snip.py'), 'w', encoding='utf-8') as f:
    f.write(SNIP)


def arm(env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run([PYEXE, os.path.join(BASE, '测', '_ev_snip.py')],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print("ARM FAILED", r.stderr[-600:])
    return [x for x in r.stdout.strip().split("\n") if x]


print("跑 A（当前：快照已修正）...")
A = arm({})
print("跑 B（WB_NO_EQ_VETO=1，否决权关）...")
B = arm({'WB_NO_EQ_VETO': '1'})
print("跑 C（对照=与A同）...")
C = arm({})
print("决策点 A/B/C = %d/%d/%d" % (len(A), len(B), len(C)))


def cmp(X, Y, tag):
    idx = [i for i in range(min(len(X), len(Y)))
           if X[i].split('|')[:5] != Y[i].split('|')[:5]]
    jn = sum(1 for i in idx if X[i].split('|')[5] == '1')
    print("%s 变化 = %d（其中突袭点 %d）" % (tag, len(idx), jn))
    for i in idx[:40]:
        pa = X[i].split('|')
        pb = Y[i].split('|')
        print("  %-13s hand%-3s %-7s  A=%-16s B=%-16s jumped=%s"
              % (pa[0], pa[1], pa[2], "%s/%s" % (pa[3], pa[4]),
                 "%s/%s" % (pb[3], pb[4]), pa[5]))
    return idx


ab = cmp(A, B, "A(开) vs B(关)")
print()
ac = cmp(A, C, "A vs C（跨进程噪声）")
