# -*- coding: utf-8 -*-
"""FLUSH_MADE_PASS 三臂 A/B（公面同花威胁下，已成两对+ 不再被规则11 硬弃）。

A = 现状（FLUSH_MADE_PASS=False）
B = 开（WB_FLUSH_MADE=1；`FLUSH_MADE_NO_RAISE`/`_NO_ALLIN` 保持默认 → 只跟不推、全下不豁免）
C = 对照（与 A 同配置，测跨进程噪声）

用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/flushmade_ab.py
"""
import glob
import json
import os
import subprocess
import sys

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
            a = S.decide(st, m, ctx, debug=False)
            out.append("%s|%s|%s|%s|%s" % (os.path.basename(p)[18:32], req.get("hand"),
                                            st.stage, a.get("act"), a.get("num") or ""))
    except Exception as e:
        out.append("ERR|%s|%s" % (os.path.basename(p)[18:32], repr(e)[:60]))
print("\n".join(out))
'''
with open(os.path.join(BASE, '测', '_fm_snip.py'), 'w', encoding='utf-8') as f:
    f.write(SNIP)


def arm(env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run([PYEXE, os.path.join(BASE, '测', '_fm_snip.py')],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print("ARM FAILED", r.stderr[-800:])
    return [x for x in r.stdout.strip().split("\n") if x]


print("跑 A（现状 三开关全关）...")
A = arm({})
print("跑 B1（只开 WB_FLUSH_MADE=1）...")
B1 = arm({'WB_FLUSH_MADE': '1'})
print("跑 B2（三开关：FLUSH_MADE + PAIRED_MADE + BIGMONEY_TWOPAIR）...")
B2 = arm({'WB_FLUSH_MADE': '1', 'WB_PAIRED_MADE': '1',
          'WB_BIGMONEY_TWOPAIR': '1'})
print("跑 C（对照=与A同）...")
C = arm({})
print("决策点总数 A/B1/B2/C = %d/%d/%d/%d"
      % (len(A), len(B1), len(B2), len(C)))


def diff(X, Y, name):
    ab = [i for i in range(min(len(X), len(Y))) if X[i] != Y[i]]
    print("A vs %s 变化 = %d" % (name, len(ab)))
    for i in ab[:60]:
        print("  %-46s  A=%-16s  %s=%s"
              % (A[i][:46], A[i].split('|')[-2:], name, Y[i].split('|')[-2:]))
    return ab


ab1 = diff(A, B1, "B1")
print()
ab2 = diff(A, B2, "B2")
print()
ab2c = diff(A, C, "对照C（跨进程噪声）")
