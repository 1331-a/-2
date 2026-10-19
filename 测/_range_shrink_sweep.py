# -*- coding: utf-8 -*-
"""条件化收窄扫描：对手「翻后累计 ≥2 次下注/加注」时，把范围缩到多少才准？

对同一批「翻后面对下注」的可算真值点，固定 MC 迭代次数（deterministic，无 deadline），
对每个 shrink 系数重算 eq，比较 bias / MAE，并**按对局拆开**看有没有哪几场变差
（这是 10-17 两次否掉全局常数的那道关）。

  shrink 只作用于 `cum_raises >= 2` 的点；其余点 rp 不变。
  也就是「对手连续两街开火 ⇒ 范围收紧」，不是全局打折。

用法: python 测/_range_shrink_sweep.py
"""
import glob
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

import strategy as S                       # noqa: E402
import game_state as G                     # noqa: E402
import opponent as O                       # noqa: E402
import match_ctx as M                      # noqa: E402
from botbattle_log import load_botbattle, card_to_platform  # noqa: E402
from _range_condition_audit import match_seat               # noqa: E402
from _fold_truth import eq_postflop                         # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))

SHRINKS = [1.00, 0.80, 0.65, 0.50, 0.40]
ITERS = 2000


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def bot_seat(obj):
    s0 = match_seat(obj)
    if s0 is not None:
        return s0
    hs = (obj.get("match") or {}).get("human_seat")
    if hs is not None:
        return 1 - int(hs)
    return None


def opp_hole(obj, hand, seat):
    for e in obj["replay"]["events"]:
        if e.get("type") == "deal_hole" and e.get("hand") == hand:
            return e["holes"][seat]
    raise KeyError


samples = []          # (match, rp_base, cum_raises, truth, eq_by_shrink dict)
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    opp = 1 - seat
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    try:
        stream = list(load_botbattle(str(p), my_seat=seat))
    except Exception:
        continue
    for req, meta in stream:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(model, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        if st.to_call <= 0 or len(st.board) < 3:
            continue
        # 只量翻牌之后（本工具不碰翻前）
        rp = S._opp_range_pct(model, S._opp_raised_preflop(st),
                              S._opp_street_raises(st), S._opp_hand_raises(st))
        cum = S._opp_hand_raises(st)
        try:
            th = internal(opp_hole(obj, int(st.hand_num), opp))
            truth = eq_postflop(list(st.hole), list(st.board), th)
        except Exception:
            continue
        if not (0.0 <= truth <= 1.0):
            continue
        eqs = {}
        for k in SHRINKS:
            rpk = rp * (k if cum >= 2 else 1.0)
            # ★ 用固定种子的 MC（equity_best 在翻牌点走精确枚举 ≈60s/点，跑不完）。
            #   同一种子 ⇒ 各 shrink 之间的差异只来自 rp，可配对比较。
            eqs[k] = S.monte_carlo_equity(
                list(st.hole), list(st.board), iterations=ITERS,
                opp_range_pct=rpk, deadline=None,
                rng=__import__("random").Random(20261019))
        samples.append(dict(m=ident, rp=rp, cum=cum, truth=truth, eqs=eqs))

print("样本点 %d（其中 cum>=2 的 %d 个）"
      % (len(samples), sum(1 for s in samples if s["cum"] >= 2)))
print()
print("%-8s %8s %8s %8s %8s %8s" % ("shrink", "bias", "MAE", "变好场数", "变差场数", "净"))
base_per = defaultdict(list)
for s in samples:
    base_per[s["m"]].append(abs(s["eqs"][1.00] - s["truth"]))
base_mae = {k: statistics.mean(v) for k, v in base_per.items()}

for k in SHRINKS:
    b = [s["eqs"][k] - s["truth"] for s in samples]
    mae = statistics.mean(abs(x) for x in b)
    per = defaultdict(list)
    for s in samples:
        per[s["m"]].append(abs(s["eqs"][k] - s["truth"]))
    better = worse = 0
    detail = []
    for m, v in per.items():
        d = statistics.mean(v) - base_mae[m]
        if d < -0.005:
            better += 1
        elif d > 0.005:
            worse += 1
        detail.append((m, d))
    print("%-8.2f %+8.3f %8.3f %8d %8d %+8d"
          % (k, statistics.mean(b), mae, better, worse, better - worse))
    if k != 1.00 and worse:
        keep = sorted(detail, key=lambda z: -z[1])[:4]
        print("        变差最多的场：%s" % ", ".join("%s %+.3f" % (m, d) for m, d in keep))

Path(str(BASE / "测" / "_range_shrink_sweep.json")).write_text(
    json.dumps(samples, ensure_ascii=False), encoding="utf-8")
