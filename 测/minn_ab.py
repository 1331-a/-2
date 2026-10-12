# -*- coding: utf-8 -*-
"""规则19 样本门槛 `SMALL_BET_MIN_N` 4→10 的 A/B（真实日志重放）。

  A 现状 : MIN_N = 4  （= 现在线上的默认值）
  B 收紧 : MIN_N = 10 （重放保真度实测最优档）
  C 对照 : MIN_N = 4  （同配置再跑一遍 → 噪声底）

并做**关键一步**：把 A/B 的变化点用 `req['hand']` 映射回真实 `settle.deltas`，
看"这些被改掉的动作在真实对局里是赚还是亏"（吸取 open_pct 的教训）。

用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/minn_ab.py
"""
import glob
import io
import json
import os
import subprocess
import sys

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PY = r"C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\python.exe"

ARMS = [
    ("A 现状(4)", {"WB_SMALL_BET_MIN_N": "4"}),
    ("B 收紧(10)", {"WB_SMALL_BET_MIN_N": "10"}),
    ("C 对照(4)", {"WB_SMALL_BET_MIN_N": "4"}),
]

CHILD = r'''
import io, json, os, sys, glob, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
logs = sorted(glob.glob(r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json")
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))
changed = []
for p in logs:
    o = json.load(io.open(p, encoding="utf-8")); m0 = o["match"]
    seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")): seat = i
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[18:32]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._DECISION_STARTED_WALL = time.time()
        a = S.decide(st, m, ctx, debug=False)
        print(json.dumps([tag, req.get("hand"), st.stage, int(st.to_call), int(st.pot),
                          meta.get("actual"), "%s%s" % (a.get("act"), a.get("num") or "")],
                         ensure_ascii=False))
'''


def run_arm(env):
    e = dict(os.environ)
    e.update(env)
    e["WB_MC_ITERS"] = os.environ.get("WB_MC_ITERS", "1500")
    e["WB_MC_BUDGET"] = os.environ.get("WB_MC_BUDGET", "0.25")
    r = subprocess.run([PY, "-c", CHILD], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, cwd=BASE)
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def main():
    got = {}
    for lab, env in ARMS:
        got[lab] = run_arm(env)
        print("[%s] 决策点 = %d" % (lab, len(got[lab])))
    A, B, C = got["A 现状(4)"], got["B 收紧(10)"], got["C 对照(4)"]
    n = min(len(A), len(B))
    dAB = [i for i in range(n) if A[i][5] != B[i][5] or A[i][6] != B[i][6]]
    nC = min(len(A), len(C))
    dAC = [i for i in range(nC) if A[i][5] != C[i][5] or A[i][6] != C[i][6]]
    print()
    print("A vs B 变化 %d / %d (%.2f%%)" % (len(dAB), n, 100.0 * len(dAB) / max(1, n)))
    print("A vs C 变化 %d / %d  ← 对照臂（应 0）" % (len(dAC), nC))
    print()
    print("=== 变化点（前 30）===")
    for i in dAB[:30]:
        r = A[i]
        print("   %-14s 手%-3s %-8s tc%-6d pot%-6d  旧=%-14s 新=%s" % tuple(r))
    # ★ 映射回真实结果
    print()
    print("=== 变化点映射回真实 settle.deltas ===")
    logs = {}
    for p in sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                    + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")):
        o = json.load(io.open(p, encoding="utf-8"))
        m0 = o["match"]
        a, b = (m0.get("bot_a") or {}), (m0.get("bot_b") or {})
        if "j1331" in str(a.get("owner_display", "")) and "j1331" in str(b.get("owner_display", "")):
            continue                       # 自对弈：无法定座位，跳过
        seat = 0 if "j1331" in str(a.get("owner_display", "")) else 1
        tag = os.path.basename(p)[18:32]
        logs[tag] = {(e["hand"]): e["deltas"][seat]
                     for e in o["replay"]["events"] if e.get("type") == "settle"}
    s = 0
    k = 0
    for i in dAB:
        tag, hand = A[i][0], A[i][1]
        v = logs.get(tag, {}).get(hand)
        if v is not None:
            s += v
            k += 1
    print("   可映射到真实结果的变化点 %d 个，这些手的真实净变合计 = %+d（均 %+.0f）" % (
        k, s, s / max(1, k)))
    print("   ★ 口径提醒：取的是**整手**净变，只作方向参考；收紧小注后这些手会变成另一条路。")


if __name__ == "__main__":
    main()
