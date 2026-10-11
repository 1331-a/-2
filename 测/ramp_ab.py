# -*- coding: utf-8 -*-
"""【2026-10-11】「建议3：金额闸门 → 连续抬门槛」的三臂 A/B。

  A 现状        : WB_NO_BIGCALL_RAMP=1（逐字回到「>3000 且 <三条 → 弃」）
  B 仅 ramp     : 默认（BIG_CALL_RAMP_ON=True）
  C ramp + §5   : B + 规则11/河牌公对陷阱/规则20 的已成牌豁免

用法：WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/ramp_ab.py
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

ARMS = [
    ("A 现状(ramp关)", {"WB_NO_BIGCALL_RAMP": "1"}),
    ("B 仅ramp", {}),
    ("C ramp+§5三开关", {"WB_FLUSH_MADE": "1", "WB_PAIRED_MADE": "1",
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

res = {lab: {} for lab, _ in ARMS}
meta_hand = {}
tot = 0
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
    handnet = {}
    cur = None
    for ev in obj["replay"]["events"]:
        if ev.get("type") == "hand_start":
            cur = ev["hand"]
        elif ev.get("type") == "settle":
            handnet[cur] = ev.get("deltas")[mine]
    tag = os.path.basename(p)[17:31]
    meta_hand[tag] = handnet
    got = {}
    for lab, env in ARMS:
        a, err = run(p, mine, env)
        if a is None:
            print("ERR", tag, lab, err)
            continue
        got[lab] = a
    if len(got) != len(ARMS):
        continue
    tot += len(got[ARMS[0][0]])
    res.setdefault("_log", {})[tag] = got

print("决策点总数 %d" % tot)
print()

for idx in (1, 2):
    lab = ARMS[idx][0]
    base = ARMS[0][0]
    n = 0
    rows = []
    for tag, got in res["_log"].items():
        A, X = got[base], got[lab]
        for i in range(len(A)):
            if A[i][1] != X[i][1]:
                n += 1
                hh = int(A[i][0].split("|")[0][1:])
                rows.append((tag, A[i][0], X[i][0], meta_hand.get(tag, {}).get(hh - 1)))
    print("=== %s 相对现状：变化 %d 点 ===" % (lab, n))
    for r in rows:
        print("   %-15s %-30s -> %-30s 该手净 %+7s" % r)
    print()

# 五个「压线点」在三臂下的结果
WANT = [("20261011142425", "h5|river|tc3168"), ("20261011142425", "h6|river|tc3760"),
        ("20260910220029", "h2|river|tc6240"), ("20260924154120", "h21|river|tc6318"),
        ("20260924160802", "h19|turn|tc4115")]
print("=== 五个「普通下注且 >3000」的压线点在三个臂下的结果 ===")
for tag, key in WANT:
    line = "   %-15s %-22s" % (tag, key)
    for lab, _ in ARMS:
        got = res["_log"].get(tag, {}).get(lab)
        v = "-"
        if got:
            for k, a in got:
                if k.startswith(key):
                    v = "%s%s" % (a.get("act"), a.get("num") or "")
                    break
        line += " | %-8s %s" % (lab.split()[0], v)
    print(line)
