# -*- coding: utf-8 -*-
"""【2026-10-11】ramp A/B 的**对照臂**：两臂配置完全相同，只换进程。

用途：跨进程重放自带约 0.5~1% 噪声下限 ⇒ 报「变化 N 点」前必须先知道 N 的噪声底。
用法：WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/ramp_control.py
"""
import glob
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
CONTENT = os.path.join(BASE, "内容")

CHILD = r'''
import sys, io, json
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
p = sys.argv[1]; seat = int(sys.argv[2])
reqs = load_botbattle(p, my_seat=seat)
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
out = []
for req, meta in reqs:
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    a = S.decide(st, m, ctx, debug=False)
    out.append(["h%s|%s|tc%s|%s%s" % (meta.get("hand"), st.stage, st.to_call,
                                      a.get("act"), a.get("num") or ""), a])
print(json.dumps(out))
'''

# 两组对照，各自的 env 完全相同
CONTROLS = [
    ("对照1 现状vs现状", {"WB_NO_BIGCALL_RAMP": "1"}, {"WB_NO_BIGCALL_RAMP": "1"}),
    ("对照2 ramp+§5 vs 自身", {"WB_FLUSH_MADE": "1", "WB_PAIRED_MADE": "1",
                               "WB_BIGMONEY_TWOPAIR": "1"},
                              {"WB_FLUSH_MADE": "1", "WB_PAIRED_MADE": "1",
                               "WB_BIGMONEY_TWOPAIR": "1"}),
]


def run(path, seat, env):
    e = dict(os.environ)
    e.update(env)
    r = subprocess.run([sys.executable, "-c", CHILD, path, str(seat)],
                       capture_output=True, text=True, env=e, cwd=CONTENT)
    if r.returncode != 0:
        return None, r.stderr[-400:]
    return json.loads(r.stdout.strip().splitlines()[-1]), None


ALL = sorted(set(glob.glob(os.path.join(CONTENT, "记录", "*botbattle*log.json"))
                 + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
print("日志 %d 份" % len(ALL))

for lab, e1, e2 in CONTROLS:
    tot = 0
    diff = []
    for p in ALL:
        try:
            obj = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        m0 = obj.get("match") or {}
        mine = 0
        for i, k in ((0, "bot_a"), (1, "bot_b")):
            if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
                mine = i
        a, err1 = run(p, mine, e1)
        b, err2 = run(p, mine, e2)
        if a is None or b is None:
            print("ERR", os.path.basename(p)[17:31], err1 or err2)
            continue
        tot += len(a)
        for i in range(len(a)):
            if a[i][1] != b[i][1]:
                diff.append((os.path.basename(p)[17:31], a[i][0], b[i][0]))
    print("=== %s ：%d / %d 点不同 ===" % (lab, len(diff), tot))
    for d in diff:
        print("   %-15s %-30s | %-30s" % d)
    print()
