# -*- coding: utf-8 -*-
"""对比：锁门开 / 关 在这份日志上的决策差异 + 每手的 lead/阈值。"""
import sys, os, json, io, glob, time, subprocess
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PYEXE = r"C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe"
LOG = sys.argv[1]
SNIP = os.path.join(BASE, "测", "_lg_snip.py")
open(SNIP, "w", encoding="utf-8").write(r'''
import sys, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
p = sys.argv[1]
o = __import__("json").load(open(p, encoding="utf-8")); m0 = o["match"]
seat = 0 if "j1331" in str((m0.get("bot_a") or {}).get("owner_display","")) else 1
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
out = []
for req, meta in load_botbattle(p, my_seat=seat):
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    S._DECISION_STARTED_WALL = time.time()
    a = S.decide(st, m, ctx, debug=False)
    lead = st.total_win_chips[st.my_id] - st.total_win_chips[st.opp_id]
    hl = S._hands_left(st)
    try: locked = S._locked_loss(st)
    except Exception: locked = None
    try: dz = S._match_adjust(st)
    except Exception: dz = "?"
    out.append("%s|%s|%s|%s|%s|%s|%s|%s" % (req.get("hand"), st.stage, a.get("act"),
               a.get("num") or "", lead, hl, locked, dz))
print("\n".join(out))
''')
def arm(env_extra):
    env = dict(os.environ); env.update(env_extra)
    env["WB_MC_ITERS"] = "1500"; env["WB_MC_BUDGET"] = "0.2"
    r = subprocess.run([PYEXE, SNIP, LOG], capture_output=True, text=True, env=env)
    return [x.split("|") for x in r.stdout.strip().split("\n") if x]
A = arm({})
B = arm({"WB_NO_DOOM_LOCK": "1"})
print("决策点 锁门开/关 = %d / %d" % (len(A), len(B)))
byhand = {}
for x in A: byhand.setdefault(x[0], []).append(x)
for x in B: byhand.setdefault(x[0], []).append(x)
first = {}
for h in sorted(byhand, key=lambda z: int(z)):
    a0 = [x for x in byhand[h] if x[6] == "True"]
    b0 = [x for x in byhand[h] if x[6] == "True"]
print()
print("%-4s %-8s %-14s %-14s %-10s %-8s %s" % ("手","街","锁门开","锁门关","lead","剩手","锁定?"))
n = 0
for h in sorted(byhand, key=lambda z: int(z)):
    aa = [x for x in byhand[h][:len(A)//1] ]  # placeholder
    pass
# 逐点对齐（用顺序）
for x, y in zip(A, B):
    if (x[2], x[3]) != (y[2], y[3]) or x[0] != y[0]:
        print("%-4s %-8s %-14s %-14s %-10s %-8s %s" % (
            x[0], x[1], x[2] + ("/" + x[3] if x[3] else ""), y[2] + ("/" + y[3] if y[3] else ""),
            x[4], x[5], x[6]))
        n += 1
print()
print("差异点 =", n)
