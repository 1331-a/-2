# -*- coding: utf-8 -*-
"""probe_real_ab.py — 在**真实日志**上隔离「A 感知硬规则」对决策的影响。

做法：同一份日志（历史固定）分别用新旧口径重放，逐决策点对比动作。
因为历史取自日志本身，两次重放面对的是同一个输入 → 差异只来自该规则。

用法：python probe_real_ab.py [记录/botbattle-*.json ...]
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategy                                    # noqa: E402
from game_state import parse_request               # noqa: E402
from opponent import OpponentModel, build_model_from_history   # noqa: E402
from match_ctx import MatchContext                 # noqa: E402
from botbattle_log import load_botbattle           # noqa: E402


def replay(path, bigbet_a_on, seat=0):
    """返回该日志下我方每个决策点的动作列表。"""
    reqs = load_botbattle(path, my_seat=seat) or []
    strategy.BIG_BET_FOLD_A_ON = bigbet_a_on
    strategy.DecisionLogger.enable(False)
    acts = []
    for req, _meta in reqs:
        model = OpponentModel()
        ctx = MatchContext.from_dict(model.ctx_dict)
        try:
            st = parse_request(req)
            build_model_from_history(model, req, st)
            ctx.update(st)
            ctx.sync_baseline(st)
            a = strategy.decide(st, model, ctx, debug=False)
            acts.append((st.stage, a.get("act"), a.get("num"),
                         st.to_call, st.pot))
        except Exception:
            pass
    return acts


if __name__ == "__main__":
    pats = sys.argv[1:] or ["记录/botbattle-holdem-20260924*.json"]
    files = []
    for p in pats:
        files += sorted(glob.glob(p)) if any(c in p for c in "*?") else [p]

    tot_new = tot_old = 0
    for path in files:
        new = replay(path, True)
        old = replay(path, False)
        n = min(len(new), len(old))
        diff = [k for k in range(n) if new[k][1] != old[k][1]]
        tot_new += sum(1 for x in new if x[1] == "fold")
        tot_old += sum(1 for x in old if x[1] == "fold")
        print("%-56s 决策 %d 个，口径改动影响 %d 个" % (
            os.path.basename(path), n, len(diff)))
        for k in diff[:4]:
            print("    #%-3d %-6s tc=%-6s pot=%-7s 旧 %s  →  新 %s" % (
                k, old[k][0], old[k][3], old[k][4], old[k][1], new[k][1]))
    print("-" * 76)
    print("全部日志合计：fold 数 旧口径 %d → 新口径 %d" % (tot_old, tot_new))
