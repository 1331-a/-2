# -*- coding: utf-8 -*-
"""0.80 vs 0.95 决策差异（真实日志）。"""
import sys, os, json, subprocess, glob

BASE = r'C:\Users\HP\WorkBuddy\德扑双人机器人测试'
PYEXE = r'C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe'
LOGS = [r'C:\Users\HP\Downloads\botbattle-holdem-20261015%s-log.json' % s
        for s in ('125604-40fdce53', '125758-b5b4ee0e', '130657-65f64d5a', '132040-a2af77d5')]

SNIP = r'''
import sys, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
p = sys.argv[1]
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
out = []
for req, meta in load_botbattle(p, my_seat=0):
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    S._DECISION_STARTED_WALL = time.time()
    a = S.decide(st, m, ctx, debug=False)
    out.append("%s/%s/%s" % (req.get("hand"), st.stage, a.get("act")))
print(";".join(out))
'''
with open(os.path.join(BASE, '测', '_gl_snip.py'), 'w', encoding='utf-8') as f:
    f.write(SNIP)

def arm(path, env_extra):
    env = dict(os.environ); env.update(env_extra)
    r = subprocess.run([PYEXE, os.path.join(BASE, '测', '_gl_snip.py'), path],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print('ERR', r.stderr[-300:]); return []
    return [x for x in r.stdout.strip().split(';') if x]

for p in LOGS:
    a = arm(p, {})                       # 默认 0.80
    b = arm(p, {'WB_GAMBLE_LINE': '0.95'})
    na = sum(1 for x in a if x.split('/')[2] == 'allin')
    nb = sum(1 for x in b if x.split('/')[2] == 'allin')
    diff = [(x.split('/')[0], x.split('/')[1], x.split('/')[2], y.split('/')[2])
            for x, y in zip(a, b) if x != y]
    print('%-9s 全押 0.80=%d 0.95=%d | 决策差异=%d' % (p[-18:-11], na, nb, len(diff)))
    for d in diff[:10]:
        print('     手%-3s %-8s 0.80:%s -> 0.95:%s' % d)
