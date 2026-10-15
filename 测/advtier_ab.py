# -*- coding: utf-8 -*-
"""ADV_TIER（优势局按牌力分档）三臂 A/B + 变化点映射回真实结果。
A=默认(开) / B=关(WB_NO_ADV_TIER=1) / C=对照(=A)
"""
import sys, os, glob, subprocess, json

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
    real = {e["hand"]: e["deltas"][seat] for e in o["replay"]["events"] if e.get("type")=="settle"}
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
            out.append("%s|%s|%s|%s|%s|%s" % (os.path.basename(p)[18:32], req.get("hand"),
                        st.stage, a.get("act"), a.get("num") or "", real.get(req.get("hand"), 0)))
    except Exception as e:
        out.append("ERR|%s|%s" % (os.path.basename(p)[18:32], repr(e)[:60]))
print("\n".join(out))
'''
with open(os.path.join(BASE, '测', '_at_snip.py'), 'w', encoding='utf-8') as f:
    f.write(SNIP)

def arm(env_extra):
    env = dict(os.environ); env.update(env_extra)
    r = subprocess.run([PYEXE, os.path.join(BASE, '测', '_at_snip.py')],
                       capture_output=True, text=True, env=env)
    return [x for x in r.stdout.strip().split("\n") if x]

print("跑 A（开）..."); A = arm({})
print("跑 B（关）..."); B = arm({'WB_NO_ADV_TIER': '1'})
print("跑 C（对照）..."); C = arm({})
print("决策点 A/B/C = %d/%d/%d" % (len(A), len(B), len(C)))
ab = [i for i in range(min(len(A), len(B))) if A[i].split('|')[:4] != B[i].split('|')[:4]]
ac = [i for i in range(min(len(A), len(C))) if A[i].split('|')[:4] != C[i].split('|')[:4]]
print("A vs B 变化 = %d | A vs C（对照噪声）= %d" % (len(ab), len(ac)))
from collections import Counter
dirs = Counter()
hands = {}
for i in ab:
    pa, pb = A[i].split('|'), B[i].split('|')
    dirs[(pb[3], pa[3])] += 1           # (旧=关=B, 新=开=A)
    hands[(pa[0], pa[1])] = int(pa[5])
print("\n方向（关 → 开）：")
for k, v in dirs.most_common():
    print("   %-14s -> %-14s %d" % (k[0], k[1], v))
tot = sum(hands.values())
print("\n受影响的手数 = %d | 这些手整手净变合计 = %+d" % (len(hands), tot))
print("（只显示 |净变|≥300 的手）")
for (tag, h), d in sorted(hands.items(), key=lambda x: x[1]):
    if abs(d) >= 300:
        print("    %-14s 手%-4s 整手净变 %+7d" % (tag, h, d))
