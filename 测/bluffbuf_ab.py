# -*- coding: utf-8 -*-
"""【2026-10-12】纯诈唬缓冲补偿 A/B：BLUFF_BUFFER_EXTRA 0.0（现状） vs 0.10 / 0.20。

输出变化点带 pot，便于估算"省下的下注额"。
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/bluffbuf_ab.py
    AB_B_EXTRA=0.20 python 测/bluffbuf_ab.py
"""
import glob, io, json, os, subprocess, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
CONTENT = os.path.join(BASE, "内容")
B_EXTRA = os.environ.get("AB_B_EXTRA", "0.10")

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
    out.append(["req%s|%s|nb%d|tc%s|pot%s|hole%s" % (req.get("hand"), st.stage,
                len(st.board), st.to_call, st.pot, st.hole),
                "%s%s" % (a.get("act"), a.get("num") or "")])
print(json.dumps(out))
'''

ARMS = [
    ("A 现状(0.0)", {"WB_BLUFF_BUFFER_EXTRA": "0.0"}),
    ("B 补偿(%s)" % B_EXTRA, {"WB_BLUFF_BUFFER_EXTRA": B_EXTRA}),
    ("C 对照(0.0)", {"WB_BLUFF_BUFFER_EXTRA": "0.0"}),
]


def run(path, seat, env):
    e = dict(os.environ); e.update(env)
    e.setdefault("WB_MC_ITERS", "1500"); e.setdefault("WB_MC_BUDGET", "0.3")
    r = subprocess.run([sys.executable, "-c", CHILD, path, str(seat)],
                       capture_output=True, text=True, env=e, cwd=CONTENT)
    if r.returncode != 0:
        return None, r.stderr[-300:]
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
print("日志 %d 份 | B 臂 BLUFF_BUFFER_EXTRA = %s" % (len(ALL), B_EXTRA))

res = {}; tot = 0
for p in ALL:
    tag = os.path.basename(p)[17:25]
    seat = mine_seat(p)
    got = {}
    for lab, env in ARMS:
        a, err = run(p, seat, env)
        if a is None:
            print("ERR", tag, lab, err); continue
        got[lab] = a
    if len(got) != len(ARMS):
        continue
    res[tag] = got
    tot += len(got[ARMS[0][0]])

print("\n决策点总数 %d\n" % tot)
A_LAB, B_LAB, C_LAB = ARMS[0][0], ARMS[1][0], ARMS[2][0]

# 每份日志的 hand -> net
def hand_nets(path):
    o = json.load(io.open(path, encoding="utf-8"))
    mm = o["match"]; seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((mm.get(k) or {}).get("owner_display", "")):
            seat = i
    d = {}
    for e in o["replay"]["events"]:
        if e.get("type") == "settle":
            d[e["hand"]] = (e["deltas"][seat], e.get("reason"))
    return d


path_of = {os.path.basename(p)[17:25]: p for p in ALL}

for lab in (B_LAB, C_LAB):
    n = 0; rows = []
    for tag, got in res.items():
        A, X = got[A_LAB], got[lab]
        for i in range(min(len(A), len(X))):
            if A[i][1] != X[i][1]:
                n += 1
                rows.append((tag, A[i][0], A[i][1], X[i][1]))
    head = ("★ 补偿 buffer 相对现状" if lab.startswith("B") else "对照臂（应为 0）")
    print("=== %s：变化 %d / %d （%.1f%%）===" % (head, n, tot, 100.0 * n / max(1, tot)))
    saved = 0
    nets = []
    for tag, key, ao, an in rows:
        import re
        mp = re.search(r"pot(\d+)", key)
        pot = int(mp.group(1)) if mp else 0
        if ao.startswith("raise") and not an.startswith("raise"):
            saved += int(0.55 * pot)          # 省下的 c-bet 金额（BLUFF=0.55 池）
        mh = re.search(r"req(\d+)", key)
        net = None
        if mh:
            hn = hand_nets(path_of[tag]).get(int(mh.group(1)))
            net = hn[0] if hn else None
        nets.append(net)
        print("   %-9s %-46s %-14s -> %-12s pot%-6d 该手净变 %s" % (
            tag, key[:46], ao, an, pot, net))
    vv = [x for x in nets if x is not None]
    print("   （{:.1f}%）".format(100.0 * n / max(1, tot)))
    if vv:
        print("   这些手真实净变合计 %+d（均 %+.0f）；被砍掉的 c-bet 金额上界 ≈ %d" % (
            sum(vv), sum(vv) / len(vv), saved))
    print()
