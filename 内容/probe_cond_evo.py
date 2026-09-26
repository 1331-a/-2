# -*- coding: utf-8 -*-
"""probe_cond_evo.py — 在**真实日志**上观察两个条件化的实际取值演化。

输出：
  · 每次翻前开池：对手 eff_vpip、B 权重 w、实际开池尺寸
  · 每次翻后跟注评估：对手 bets/hand、A 折算因子

用途：确认条件化在真实对手画像下「取到了合理值」，而不是只在合成测试里成立。
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from game_state import parse_request                     # noqa: E402
from strategy import (decide, DecisionLogger, _open_weight,  # noqa: E402
                      _future_aggr_factor, _future_cost)
from opponent import OpponentModel, build_model_from_history  # noqa: E402
from match_ctx import MatchContext                       # noqa: E402
from botbattle_log import load_botbattle                 # noqa: E402


def replay(path, seat=0):
    reqs = load_botbattle(path, my_seat=seat) or []
    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)
    DecisionLogger.enable(False)
    opens, calls = [], []
    for req, meta in reqs:
        try:
            st = parse_request(req)
            try:
                build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
                ctx.sync_baseline(st)
            except Exception:
                pass
            a = decide(st, model, ctx, debug=False)
            if st.stage == "preflop" and a.get("act") == "raise":
                opens.append((meta.get("hand"), model.eff_vpip(),
                              _open_weight(model), a.get("num"),
                              model.avg_bets_per_hand()))
            if st.stage in ("flop", "turn") and st.to_call > 0:
                fc, _ = _future_cost(st, st.to_call, model)
                calls.append((meta.get("hand"), st.stage,
                              model.avg_bets_per_hand(),
                              _future_aggr_factor(model), fc))
        except Exception:
            pass
    return opens, calls


if __name__ == "__main__":
    pats = sys.argv[1:] or ["记录/botbattle-holdem-20260924*.json"]
    files = []
    for p in pats:
        files += sorted(glob.glob(p)) if any(c in p for c in "*?") else [p]

    for path in files:
        opens, calls = replay(path)
        name = os.path.basename(path)
        print("=" * 86)
        print("%s   翻前开池 %d 次 / 翻后跟注点 %d 个" % (name, len(opens), len(calls)))
        if opens:
            vp = [o[1] for o in opens]
            w = [o[2] for o in opens]
            sz = [o[3] for o in opens]
            print("  【B】对手 eff_vpip：首 %.2f → 末 %.2f（min %.2f / max %.2f）"
                  % (vp[0], vp[-1], min(vp), max(vp)))
            print("       B 权重 w：首 %.2f → 末 %.2f   开池尺寸：%s"
                  % (w[0], w[-1], sorted(set(sz))))
            print("      逐次：", end="")
            for h, v, ww, s, bph in opens[:12]:
                print(" H%s(vpip%.2f→w%.2f→%s)" % (h, v, ww, s), end="")
            print()
        if calls:
            f = [c[3] for c in calls]
            fc = [c[4] for c in calls]
            print("  【A】bets/hand：首 %.2f → 末 %.2f   折算因子：首 %.2f → 末 %.2f"
                  % (calls[0][2], calls[-1][2], f[0], f[-1]))
            print("       折算额：", end="")
            for h, stg, bph, ff, fcv in calls[:8]:
                print(" H%s/%s(bph%.2f→f%.2f→%.0f)" % (h, stg, bph, ff, fcv), end="")
            print()
