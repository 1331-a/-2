# -*- coding: utf-8 -*-
"""搏命/末日新规的 A/B（真实日志重放，全部非自对弈）。

  A 基线 : WB_GAMBLE_LINE=0.95 + 关闭太差不推   （= 改动前行为）
  B 新规 : 默认 —— 搏命线 0.80 + 太差的牌不推
  C 对照 : 与 A 同配置（噪声底）

并把变化点映射回真实 `settle.deltas`（吸取 open_pct 教训）。

用法: WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/gamble_ab.py
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
    ("A 基线(0.95+不拦)", {"WB_GAMBLE_LINE": "0.95", "WB_NO_GAMBLE_TRASH": "1"}),
    ("B 新规(0.80+拦太差)", {"WB_GAMBLE_LINE": "0.80"}),
    ("C 对照", {"WB_GAMBLE_LINE": "0.95", "WB_NO_GAMBLE_TRASH": "1"}),
]

CHILD = r'''
import io, json, os, sys, glob, time
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
logs = sorted(glob.glob(r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json")
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))
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
                          str(meta.get("actual")), "%s%s" % (a.get("act"), a.get("num") or "")],
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
    A, B, C = got["A 基线(0.95+不拦)"], got["B 新规(0.80+拦太差)"], got["C 对照"]
    n = min(len(A), len(B))
    dAB = [i for i in range(n) if A[i][6] != B[i][6]]
    nC = min(len(A), len(C))
    dAC = [i for i in range(nC) if A[i][6] != C[i][6]]
    print()
    print("A vs B 变化 %d / %d (%.2f%%)" % (len(dAB), n, 100.0 * len(dAB) / max(1, n)))
    print("A vs C 变化 %d / %d  ← 对照臂（应 0）" % (len(dAC), nC))
    print()
    print("=== 变化点（前 40）===")
    for i in dAB[:40]:
        r = A[i]
        print("   %-14s 手%-3s %-8s tc%-6d pot%-6d  旧=%-14s 新=%s" % (
            r[0], r[1], r[2], r[3], r[4], r[6], B[i][6]))
    # ★ 方向统计
    import collections as _c
    dirn = _c.Counter()
    same_act = 0
    for i in dAB:
        oa, na = A[i][6], B[i][6]
        ao = oa if oa in ("fold", "check", "call", "allin") else "raise"
        an = na if na in ("fold", "check", "call", "allin") else "raise"
        if ao == an:
            same_act += 1
            dirn[("仅尺寸", ao)] += 1
        else:
            dirn[("%s→%s" % (ao, an), "动作")] += 1
    print()
    print("=== 方向统计 ===")
    for k in sorted(dirn, key=lambda x: -dirn[x]):
        print("   %-18s %3d" % (k[0], dirn[k]))
    print("   （其中「仅尺寸变化」%d 个）" % same_act)
    # 映射回真实结果
    print()
    logs = {}
    for p in sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                    + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")):
        o = json.load(io.open(p, encoding="utf-8")); m0 = o["match"]
        a, b = (m0.get("bot_a") or {}), (m0.get("bot_b") or {})
        if "j1331" in str(a.get("owner_display", "")) and "j1331" in str(b.get("owner_display", "")):
            continue
        seat = 0 if "j1331" in str(a.get("owner_display", "")) else 1
        logs[os.path.basename(p)[18:32]] = {
            e["hand"]: e["deltas"][seat]
            for e in o["replay"]["events"] if e.get("type") == "settle"}
    tot = 0
    k = 0
    seen = set()
    for i in dAB:
        tag, hand = A[i][0], A[i][1]
        if (tag, hand) in seen:
            continue
        seen.add((tag, hand))
        v = logs.get(tag, {}).get(hand)
        if v is not None:
            tot += v
            k += 1
    print("   可映射的**不同手** %d 手，这些手真实净变合计 = %+d（均 %+.0f）" % (k, tot, tot / max(1, k)))
    print("   ★ 口径：整手净变，只作方向参考。")


if __name__ == "__main__":
    main()
