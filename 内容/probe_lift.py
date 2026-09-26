# -*- coding: utf-8 -*-
"""probe_lift.py — 用真实日志统计 future_cost 的门槛抬升分布（快，无需模拟）。

回放 4 局真实日志的每个决策点，收集 WB_FC_LOG（_face_bet 折算记录），
输出：折算触发次数、抬升幅度分布、按阶段分布，以及「抬升是否足以翻过门槛」。
"""
import glob
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["WB_FC_DEBUG"] = "1"

from game_state import parse_request
from strategy import decide, DecisionLogger
from opponent import OpponentModel, build_model_from_history
from match_ctx import MatchContext
from botbattle_log import load_botbattle
import strategy


def replay(path, seat=0):
    reqs = load_botbattle(path, my_seat=seat)
    if not reqs:
        return 0
    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)
    DecisionLogger.enable(False)
    n = 0
    for req, meta in reqs:
        try:
            state = parse_request(req)
            try:
                build_model_from_history(model, req, state)
            except Exception:
                pass
            try:
                ctx.update(state)
                ctx.sync_baseline(state)
            except Exception:
                pass
            decide(state, model, ctx, debug=False)
            n += 1
        except Exception:
            pass
    return n


if __name__ == "__main__":
    pats = sys.argv[1:] or ["记录/botbattle-holdem-20260924*.json"]
    files = []
    for p in pats:
        files += sorted(glob.glob(p)) if any(c in p for c in "*?") else [p]

    total_pts = 0
    for path in files:
        strategy.WB_FC_LOG.clear()
        n = replay(path)
        total_pts += n
        log = list(strategy.WB_FC_LOG)
        name = os.path.basename(path)
        print("=" * 74)
        print("%s  决策点 %d  折算触发 %d (%.1f%%)" %
              (name, n, len(log), (len(log) / n * 100) if n else 0))
        if not log:
            continue
        lifts = [r["eff_new"] - r["eff_old"] for r in log]
        print("  抬升：min %+.3f  中位 %+.3f  均值 %+.3f  max %+.3f" % (
            min(lifts), statistics.median(lifts),
            statistics.mean(lifts), max(lifts)))
        from collections import Counter
        print("  阶段分布：", dict(Counter(r["stage"] for r in log)))
        for r in log[:8]:
            print("    %-6s pot=%-6d tc=%-6d fc=%-7.0f  eff %.3f → %.3f  (%+.3f)" % (
                r["stage"], r["pot"], r["to_call"], r["fc"],
                r["eff_old"], r["eff_new"], r["eff_new"] - r["eff_old"]))
    print("=" * 74)
    print("总决策点 %d" % total_pts)
