# -*- coding: utf-8 -*-
"""PREFLOP_BIG_CALL（翻前大额跟注放行）三臂 A/B。
A=默认(开) / B=关(WB_NO_PREFLOP_BIG_CALL=1) / C=对照(=A)
"""
import os, subprocess
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PYEXE = r"C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe"
SNIP = os.path.join(BASE, "测", "_ap_dump.py")     # 已有：输出 tag|hand|stage|act|num|eq|eff|margin
ARMS = [("A 默认(开)", {}), ("B 关", {"WB_NO_PREFLOP_BIG_CALL": "1"}), ("C 对照(=A)", {})]
res = {}
for name, env_extra in ARMS:
    env = dict(os.environ); env.update(env_extra)
    env.setdefault("WB_MC_ITERS", "1500"); env.setdefault("WB_MC_BUDGET", "0.2")
    r = subprocess.run([PYEXE, SNIP], capture_output=True, text=True, env=env,
                       cwd=BASE)
    lines = [x for x in r.stdout.strip().split("\n") if x and not x.startswith("ERR")]
    res[name] = [x.split("|") for x in lines]
    print("  %-12s 决策点 %d" % (name, len(lines)))
A, B, C = res["A 默认(开)"], res["B 关"], res["C 对照(=A)"]
def diff(X, Y):
    return [(x, y) for x, y in zip(X, Y)
            if (x[0], x[1], x[2], x[3], x[4]) != (y[0], y[1], y[2], y[3], y[4])]
ab, ac = diff(A, B), diff(A, C)
print("A vs B(关) = %d | A vs C(对照) = %d" % (len(ab), len(ac)))
for x, y in ab:
    print("   %-14s 手%-4s %-8s  A(开)=%s%-6s  B(关)=%s%-6s" % (
        x[0], x[1], x[2], x[3], x[4], y[3], y[4]))
