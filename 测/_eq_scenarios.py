# -*- coding: utf-8 -*-
"""阶段二（影子诊断）：eq 的多场景敏感性 —— 不改变线上行为。

思路（外部审计建议）：不再让**单一 eq 一票决定**放行，而是对同一个决策点
算三个**候选范围**下的胜率，看结论是否稳健：

  A 现有范围        opp_range_pct = rp
  B 价值偏重范围    opp_range_pct = rp × 0.60   （对手更可能在价值下注）
  C 允许诈唬范围    opp_range_pct = min(1.0, rp × 1.40)

判定（相对赔率门槛 req = to_call / (pot + to_call)）：
  · 三场景都 ≥ req → `unanimous_call`（稳健跟注）
  · 三场景都 <  req → `unanimous_fold`（稳健弃牌）
  · 其余           → `split`（分歧，**保留基线判断，不用 eq 翻案**）

★ 这里只是"待验证的敏感性场景"，不是统计置信区间。
★ 本脚本只统计，不修改策略。

用法:
    python 测/_eq_scenarios.py                 # 默认 2000 次 MC
    python 测/_eq_scenarios.py --iters 1200
"""
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

import strategy as S                          # noqa: E402
import game_state as G                        # noqa: E402
import opponent as O                          # noqa: E402
import match_ctx as M                         # noqa: E402
from equity import monte_carlo_equity         # noqa: E402
from botbattle_log import load_botbattle      # noqa: E402
from _range_condition_audit import match_seat  # noqa: E402

ITERS = 2000
if "--iters" in sys.argv:
    try:
        ITERS = int(sys.argv[sys.argv.index("--iters") + 1])
    except Exception:
        pass

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))


def three_eq(state, model, rp):
    """三种范围下的 eq（同一 RNG 无关，MC 独立抽样）。"""
    out = []
    for k in (1.0, 0.60, 1.40):
        r = max(0.02, min(1.0, rp * k))
        out.append(monte_carlo_equity(state.hole, state.board,
                                      iterations=ITERS, opp_range_pct=r))
    return out


rows = []
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = match_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    try:
        for req, meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            try:
                O.build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
            except Exception:
                pass
            S._DECISION_STARTED_WALL = time.time()
            a = S.decide(st, model, ctx, debug=False)
            # 只看「翻后 + 面对下注 + 非全下」的决策点
            if len(st.board) < 3 or int(st.to_call) <= 0:
                continue
            if int(st.to_call) >= int(st.my_left):
                continue
            try:
                rp = S._opp_range_pct(model, S._opp_raised_preflop(st) == st.opp_id,
                                      S._opp_street_raises(st))
            except Exception:
                continue
            tc, pot = int(st.to_call), int(st.pot)
            req_ratio = tc / float(pot + tc) if (pot + tc) > 0 else 1.0
            e_now, e_val, e_mix = three_eq(st, model, rp)
            votes = [e_now >= req_ratio, e_val >= req_ratio, e_mix >= req_ratio]
            if all(votes):
                verdict = "unanimous_call"
            elif not any(votes):
                verdict = "unanimous_fold"
            else:
                verdict = "split"
            rows.append(dict(m=ident, hand=int(st.hand_num) + 1,
                             stage=st.stage, act=a.get("act"),
                             rp=round(rp, 3), req=round(req_ratio, 3),
                             e_now=round(e_now, 3), e_val=round(e_val, 3),
                             e_mix=round(e_mix, 3), verdict=verdict))
    except Exception as e:
        print("  skip %s %r" % (ident, e))

print("翻后 + 面对下注 + 非全下的决策点：%d（MC %d 次）" % (len(rows), ITERS))
print()
c = Counter(r["verdict"] for r in rows)
print("三场景判定的分布：")
for k in ("unanimous_call", "unanimous_fold", "split"):
    print("  %-16s %4d  (%.1f%%)" % (k, c[k], 100.0 * c[k] / max(1, len(rows))))
print()

print("分歧点的基线动作分布（这些点「不用 eq 翻案」= 保持现状）：")
cc = Counter(r["act"] for r in rows if r["verdict"] == "split")
for k, v in cc.most_common():
    print("  %-10s %d" % (k, v))
print()

print("若严格按「三场景都支持才跟注」，相对基线的翻转点：")
flip = []
for r in rows:
    is_call = r["act"] in ("call", "allin")
    if is_call and r["verdict"] == "unanimous_fold":
        flip.append(("基线跟注 → 应弃", r))
    elif (not is_call) and r["verdict"] == "unanimous_call":
        flip.append(("基线弃/加 → 应跟", r))
print("  合计 %d 点" % len(flip))
for tag, r in flip[:25]:
    print("  %-16s %-14s 手%-3d %-7s req=%.2f e=(%.2f/%.2f/%.2f) → %s"
          % (tag, r["m"], r["hand"], r["stage"], r["req"],
             r["e_now"], r["e_val"], r["e_mix"], r["act"]))
print()

# 场景之间的离散度：判断「价值偏重」到底把 eq 拉低多少
import statistics
d_val = [r["e_val"] - r["e_now"] for r in rows]
d_mix = [r["e_mix"] - r["e_now"] for r in rows]
print("范围收缩对 eq 的影响（相对现有范围）：")
print("  价值偏重(rp×0.60)：中位 %+0.3f，均值 %+0.3f，P10 %+0.3f"
      % (statistics.median(d_val), statistics.mean(d_val),
         sorted(d_val)[max(0, int(0.1 * len(d_val)))]))
print("  带诈唬(rp×1.40)  ：中位 %+0.3f，均值 %+0.3f"
      % (statistics.median(d_mix), statistics.mean(d_mix)))

outp = BASE / "测" / "_eq_scenarios.json"
outp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n已写入 %s" % outp.name)
