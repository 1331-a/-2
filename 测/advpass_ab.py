# -*- coding: utf-8 -*-
"""ADV_PASS（优势局不硬弃）分臂 A/B + 变化点映射回真实结果。

  A 默认(两者都开) / B 全关 / C 对照(=A) / D 只硬规则豁免 / E 只兜底赔率
用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.2 python 测/advpass_ab.py
"""
import os, subprocess, sys
from collections import Counter

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PYEXE = r"C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe"
SNIP = os.path.join(BASE, "测", "_ap_snip.py")
ARMS = [
    ("A 默认(都开)", {}),
    ("B 全关", {"WB_NO_ADV_PASS": "1", "WB_NO_ADV_ODDS_FALLBACK": "1"}),
    ("C 对照(同A)", {}),
    ("D 只硬规则豁免", {"WB_NO_ADV_ODDS_FALLBACK": "1"}),
    ("E 只兜底赔率", {"WB_NO_ADV_PASS": "1"}),
]
res = {}
for name, env_extra in ARMS:
    env = dict(os.environ); env.update(env_extra)
    env.setdefault("WB_MC_ITERS", "1500"); env.setdefault("WB_MC_BUDGET", "0.2")
    r = subprocess.run([PYEXE, SNIP], capture_output=True, text=True, env=env)
    lines = [x for x in r.stdout.strip().split("\n") if x]
    res[name] = [x.split("|") for x in lines]
    print("  %-14s 决策点 %d %s" % (name, len(lines), r.stderr[-120:] if r.returncode else ""))
A, B, C = res["A 默认(都开)"], res["B 全关"], res["C 对照(同A)"]
D, E = res["D 只硬规则豁免"], res["E 只兜底赔率"]

def key(x): return (x[0], x[1], x[2])
def cmp2(X, Y):
    d = [(x, y) for x, y in zip(X, Y) if key(x) != key(y) or x[3:5] != y[3:5]]
    return d
for nm, Y in (("B 全关", B), ("C 对照", C), ("D 只硬规则", D), ("E 只兜底", E)):
    print("A vs %-12s 变化 = %d" % (nm, len(cmp2(A, Y))))

print()
print("=== A vs B 的方向与真实结果 ===")
dirs = Counter(); hands = {}
for x, y in cmp2(A, B):
    dirs[(y[3], x[3])] += 1          # (关=B, 开=A)
    hands[(x[0], x[1])] = int(x[5])
for k, v in dirs.most_common():
    print("   %-10s -> %-10s %d" % (k[0], k[1], v))
print()
print("受影响的手 = %d | 这些手整手真实净变合计 = %+d" % (len(hands), sum(hands.values())))
for (t, h), v in sorted(hands.items(), key=lambda z: z[1]):
    print("   %-14s 手%-4s %+7d" % (t, h, v))
print()
print("=== 明细（A 开 vs B 关）===")
for x, y in cmp2(A, B)[:40]:
    print("   %-14s 手%-4s %-8s  A=%s%-6s  B=%s%-6s  整手%+d" % (
        x[0], x[1], x[2], x[3], x[4], y[3], y[4], int(x[5])))
