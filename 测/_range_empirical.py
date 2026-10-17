# -*- coding: utf-8 -*-
"""对手范围宽度的**经验分布**：模型假设「均匀 top-X%」，实际观测到什么？

若模型的范围是「均匀取 top-X%」，则其手牌百分位的中位数 = X/2。
所以：**X_应取 ≈ 2 × 实测中位数**。本工具算实测分布，并与 `_opp_range_pct` 的实际取值对照。
"""
import collections
import glob
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

import game_state as G                                  # noqa: E402
import match_ctx as M                                   # noqa: E402
import opponent as O                                    # noqa: E402
import strategy as S                                    # noqa: E402
from botbattle_log import load_botbattle                # noqa: E402
from ranges import hand_percentile                       # noqa: E402
from _range_condition_audit import hole_map, match_id, match_seat  # noqa: E402


def q(v, p):
    v = sorted(v)
    if not v:
        return float("nan")
    i = min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))
    return v[i]


paths = sorted(set(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
               | set(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
groups = collections.defaultdict(list)
model_vals = collections.defaultdict(list)

for p in paths:
    obj = json.loads(Path(p).read_bytes())
    seat = match_seat(obj)
    if seat is None:
        continue
    holes = hole_map(obj, seat)
    # 对手动作序列（按手/街）
    opp_act = collections.defaultdict(list)
    for ev in obj["replay"]["events"]:
        if ev.get("type") == "action" and int(ev.get("player", -1)) != seat:
            opp_act[(int(ev.get("hand", -1)), ev.get("round", 0))].append(
                str(ev.get("action")))
        if ev.get("type") == "deal_board":
            opp_act[("street", int(ev.get("hand", -1)))] = ev.get("street")
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    seen = set()
    for request, _meta in load_botbattle(p, my_seat=seat):
        state = G.parse_request(request)
        try:
            O.build_model_from_history(model, request, state)
        except Exception:
            pass
        try:
            ctx.update(state)
        except Exception:
            pass
        if len(state.board) < 3 or state.to_call <= 0:
            continue
        key = (int(state.hand_num), state.stage)
        if key in seen:
            continue
        seen.add(key)
        theirs = holes[int(state.hand_num)][1]
        pct = hand_percentile(theirs)
        rp = S._opp_range_pct(model, S._last_preflop_raiser(state) == state.opp_id,
                              S._opp_street_raises(state))
        grp = "%s_%s" % ("翻前有加注" if S._last_preflop_raiser(state) == state.opp_id
                         else "翻前无加注", state.stage)
        groups[grp].append(pct)
        model_vals[grp].append(rp)

print("%-22s %5s %7s %7s %7s %9s %9s" %
      ("分组", "n", "中位", "下四分", "上四分", "实测应取X", "模型实际X"))
for k in sorted(groups):
    v = groups[k]
    mv = model_vals[k]
    implied = 2.0 * statistics.median(v)
    print("%-22s %5d %7.3f %7.3f %7.3f %9.2f %9.2f"
          % (k, len(v), statistics.median(v), q(v, 0.25), q(v, 0.75),
             min(1.0, implied), statistics.median(mv)))

allv = [x for v in groups.values() for x in v]
allm = [x for v in model_vals.values() for x in v]
print("\n合计 n=%d 中位 %.3f ⇒ 实测应取 X ≈ %.2f ；模型实际 X 中位 %.2f"
      % (len(allv), statistics.median(allv),
         min(1.0, 2 * statistics.median(allv)), statistics.median(allm)))
print("模型比实测宽了约 %.2f 倍" %
      (statistics.median(allm) / max(1e-9, 2 * statistics.median(allv))))
