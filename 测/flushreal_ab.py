# -*- coding: utf-8 -*-
"""FLUSH_REAL_PASS 三臂 A/B（真同花不再被规则11 硬弃）。
A = 默认(开) / B = 关(WB_NO_FLUSH_REAL_PASS=1) / C = 对照(与 A 同配置)
用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/flushreal_ab.py
"""
import sys, os, glob, subprocess, time, json

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
with open(os.path.join(BASE, '测', '_fr_snip.py'), 'w', encoding='utf-8') as f:
    f.write(SNIP)

def arm(env_extra):
    env = dict(os.environ); env.update(env_extra)
    r = subprocess.run([PYEXE, os.path.join(BASE, '测', '_fr_snip.py')],
                       capture_output=True, text=True, env=env)
    return [x for x in r.stdout.strip().split("\n") if x]

print("跑 A（默认开）...")
A = arm({})
print("跑 B（关）...")
B = arm({'WB_NO_FLUSH_REAL_PASS': '1'})
print("跑 C（对照=与A同）...")
C = arm({})
print("决策点总数 A/B/C = %d/%d/%d" % (len(A), len(B), len(C)))
ab = [i for i in range(min(len(A), len(B))) if A[i] != B[i]]
ac = [i for i in range(min(len(A), len(C))) if A[i] != C[i]]
print("A vs B 变化 = %d | A vs C（对照噪声）= %d" % (len(ab), len(ac)))
print("\n=== A 与 B 的差异点 ===")
for i in ab[:40]:
    print("  %-46s  A(开)=%-16s  B(关)=%s" % (A[i][:46], A[i].split('|')[-2:], B[i].split('|')[-2:]))
