# -*- coding: utf-8 -*-
"""诊断当前版在「推光密集段」走的到底是哪条规则。"""
import io
import json
import marshal
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

with open(os.path.join(BASE, "测", "_v50_body.bin"), "rb") as f:
    V50 = {"__name__": "v50mod", "__file__": "poker_bot.py"}
    exec(marshal.loads(f.read()), V50)

import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

try:
    import equity as EQ
    EQ._rng.seed(20260930)
except Exception:
    pass

LOG = sys.argv[1]
SEAT = 0
SHOVE_HANDS = set(int(x) for x in (sys.argv[2:] or
                                   ["49", "51", "53", "55", "56", "59", "60", "61"]))

S.DecisionLogger._quiet = True
reqs = load_botbattle(LOG, my_seat=SEAT)
m = O.OpponentModel()
ctx = M.MatchContext.from_dict(m.ctx_dict)

print("座%d（指纹判定 = 当前版）—— 推光段的规则归因" % SEAT)
print("=" * 96)
print("%-5s %-8s %-9s %-11s %-13s %-9s %-9s" %
      ("手", "底牌", "实际", "规则标签", "决策", "赛前lead", "doom/搏命"))

for req, meta in reqs:
    h1 = meta.get("hand")
    try:
        st = G.parse_request(req)
    except Exception:
        continue
    try:
        O.build_model_from_history(m, req, st)
    except Exception:
        pass
    try:
        ctx.update(st)
    except Exception:
        pass

    S.DecisionLogger.reset()
    S.DecisionLogger._quiet = True
    S.DecisionLogger.enable(True)
    try:
        act = S.decide(st, m, ctx, debug=True)
    except Exception as e:
        act = {"err": repr(e)}
    recs = list(S.DecisionLogger._records)
    rule = recs[-1].get("rule") if recs else "?"
    act_txt = act.get("act") if isinstance(act, dict) else act

    if h1 not in SHOVE_HANDS:
        continue

    lead = int(st.total_win_chips[st.my_id]) - int(st.total_win_chips[st.opp_id])
    try:
        adj = S._match_adjust(st)
    except Exception:
        adj = "?"
    try:
        dooms = "doom" if S._doom_risk(st) else "-"
    except Exception:
        dooms = "?"
    try:
        gz = "搏命" if S._gamble_zone(st) else "-"
    except Exception:
        gz = "?"
    try:
        inv = S._invested(st)
        hl = S._hands_left(st)
        line = S._blind_line(st, hl, own=False)
    except Exception:
        inv = hl = line = None

    print("%-5s %-8s %-9s %-11s %-13s %-9s %-9s" %
          (h1, "/".join(map(str, meta.get("hole") or [])), meta.get("actual"),
           str(rule)[:11], str(act_txt)[:13], "%+d" % lead, "%s/%s" % (dooms, gz)))
    print("       to_call=%-6s invested=%-6s hands_left=%-3s 追回线=%-6s adj=%s"
          % (st.to_call, inv, hl, line, adj))
    print("       ── 决策链（最近几条）──")
    for r in recs[-4:]:
        info = r.get("info") or {}
        extra = {k: info.get(k) for k in ("eq", "cat", "lock") if info.get(k) is not None}
        print("         act=%-7s rule=%-26s %s" %
              (str(r.get("action"))[:7], str(r.get("rule"))[:26],
               json.dumps(extra, ensure_ascii=False)[:90]))
    print()
