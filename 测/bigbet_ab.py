# -*- coding: utf-8 -*-
"""【2026-10-11】选项B试点（大注+无坚果 → 抬高门槛交回 eq）的三臂 A/B。

  A 现状        : 默认（BIGBET_THRESH_ON=False）→ 逐字等价原硬规则
  B 选项B       : WB_BIGBET_THRESH=1（不硬弃，eff_req += bump，只允许 call/fold）
  C 对照        : 与 A 同配置（验证噪声底）

用法:
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/bigbet_ab.py
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
    out.append(["h%s|%s|nb%d|tc%s" % (meta.get("hand"), st.stage, len(st.board), st.to_call),
                "%s%s" % (a.get("act"), a.get("num") or "")])
print(json.dumps(out))
'''

ARMS = [
    ("A 现状(硬弃)", {}),
    ("B 选项B(门槛化)", {"WB_BIGBET_THRESH": "1"}),
    ("C 对照(同A)", {}),
]


def run(path, seat, env):
    e = dict(os.environ)
    e.update(env)
    e.setdefault("WB_MC_ITERS", "1500")
    e.setdefault("WB_MC_BUDGET", "0.3")
    r = subprocess.run([sys.executable, "-c", CHILD, path, str(seat)],
                       capture_output=True, text=True, env=e, cwd=CONTENT)
    if r.returncode != 0:
        return None, r.stderr[-400:]
    return json.loads(r.stdout.strip().splitlines()[-1]), None


def mine_seat(path):
    try:
        obj = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return 0
    m0 = obj.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


ALL = sorted(set(glob.glob(os.path.join(CONTENT, "记录", "*botbattle*log.json"))
                 + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
print("日志 %d 份" % len(ALL))

res = {}
tot = 0
for p in ALL:
    tag = os.path.basename(p)[17:31]
    seat = mine_seat(p)
    got = {}
    for lab, env in ARMS:
        a, err = run(p, seat, env)
        if a is None:
            print("ERR", tag, lab, err)
            continue
        got[lab] = a
    if len(got) != len(ARMS):
        continue
    res[tag] = got
    tot += len(got[ARMS[0][0]])
    print("  ✓ %-15s 决策点 %3d" % (tag, len(got[ARMS[0][0]])))

print()
print("决策点总数 %d" % tot)
print()
for lab in ("B 选项B(门槛化)", "C 对照(同A)"):
    n = 0
    rows = []
    for tag, got in res.items():
        A, X = got["A 现状(硬弃)"], got[lab]
        for i in range(min(len(A), len(X))):
            if A[i][1] != X[i][1]:
                n += 1
                rows.append((tag, A[i][0], A[i][1], X[i][1]))
    tag_ = "★ 选项B 相对现状" if lab.startswith("B") else "对照臂（应为 0）"
    print("=== %s：变化 %d / %d ===" % (tag_, n, tot))
    for r in rows:
        print("   %-15s %-26s %-14s -> %-14s" % r)
    print()
