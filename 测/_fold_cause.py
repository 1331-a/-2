# -*- coding: utf-8 -*-
"""【2026-10-12】归属：28 个「eq 够却 fold」的点，分别由哪个（决策层）判据造成。

候选：
  C1 `_cheap_call_cap_hit`（方案A 便宜跟注封顶）
  C2 `_river_paired_trap`（河牌裸公对陷阱）
  C3 medium 分支的额外 +0.03
  C4 其它（记录 eq/eff_req/分支）
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))


def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8"))
    m0 = o.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


cnt = collections.Counter()
rows = []
for p in logs:
    seat = seat_of(p)
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[17:25]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._LAST_REQ_INFO = None
        a = S.decide(st, m, ctx, debug=False)
        ri = S._LAST_REQ_INFO
        if not ri or int(st.to_call) <= 0 or a.get("act") != "fold":
            continue
        eq, eff_req, margin = map(float, ri)
        slack = eq - (eff_req + margin)
        if slack < 0:
            continue
        # 逐项判定
        try:
            cap_hit = S._cheap_call_cap_hit(st, S._effective_category(st) >= S.TWO_PAIR)
        except Exception:
            cap_hit = None
        try:
            trap = S._river_paired_trap(st) if st.stage == "river" else False
        except Exception:
            trap = None
        inv = S.INIT_CHIPS - st.my_chips
        to_call = int(st.to_call); pot = int(st.pot)
        scale = min(1.0, (st.hand_num or 0) / float(max(S.FUTURE_COST_CAP_MIN_HANDS, 1)))
        cap = S.FUTURE_COST_CHEAP_MAX * scale
        exempt = (to_call >= S.FUTURE_COST_CAP_MIN_RATIO * pot)
        tagc = ("C1 便宜跟注封顶" if cap_hit else
                ("C2 河牌裸公对陷阱" if trap else
                 ("C-margin(medium +0.03)" if slack < 0.03 else "C4 其它")))
        cnt[tagc] += 1
        rows.append((tagc, tag, req.get("hand"), st.stage, to_call, pot, eq, slack,
                     inv, cap, exempt))

print("「面对下注 & eq 够 & 最终 fold」= %d 点" % sum(cnt.values()))
print()
for k, v in cnt.most_common():
    print("  %-24s %3d" % (k, v))
print()
print("=== 明细（按 slack 降序前 30）===")
print("  %-24s %-9s %4s %-7s %7s %7s %6s %7s %8s %7s %s" % (
    "归属", "日志", "手", "街", "to_call", "pot", "eq", "slack", "本手已投", "cap", "豁免?"))
for r in sorted(rows, key=lambda x: -x[7])[:30]:
    print("  %-24s %-9s %4d %-7s %7d %7d %6.3f %7.3f %8d %7.0f %s" % (
        r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], "是" if r[10] else "否"))
