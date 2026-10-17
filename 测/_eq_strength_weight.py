# -*- coding: utf-8 -*-
"""原型：给对手范围加「翻后牌力」权重，看能否把 eq 的偏差压下去。

机制（`_eq_bias_mechanism.py` 已证实）：模型按**翻前百分位**给对手组合加权，
完全不看「对手已经下注」这个动作与**翻后牌力**的相关性 ⇒
  对手已成三条：pred 0.420 / truth 0.020（高估 +0.400）
  对手成顺子  ：pred 0.606 / truth 0.054（高估 +0.552）
  对手是空气  ：pred 0.416 / truth 0.563（反而低估 −0.147）

做法：把组合权重改成 `w = 翻前范围权重 × boost**(max(0, cat-1))`，
cat = 该组合在**当前牌面**上的牌型（0 高牌 / 1 一对 / 2 两对 / 3 三条 …）。
用 `_build_range` 已有的 `opp_weights` 钩子，不动生产代码。

★ 用留一法（LOOCV）在**对局层面**选 boost，避免自证。
"""
import argparse
import collections
import glob
import itertools
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

import equity as E                                       # noqa: E402
import game_state as G                                   # noqa: E402
import match_ctx as M                                    # noqa: E402
import opponent as O                                     # noqa: E402
import strategy as S                                     # noqa: E402
from botbattle_log import load_botbattle                 # noqa: E402
from cards import full_deck                              # noqa: E402
from evaluator import evaluate_7                         # noqa: E402
from ranges import hand_percentile                        # noqa: E402
from _range_condition_audit import (                     # noqa: E402
    exact_vs_hole, hole_map, match_id, match_seat)

ARMS = {"base": 1.0, "boost2": 2.0, "boost3": 3.0, "boost5": 5.0}


def eq_for(sample, boost):
    if boost == 1.0:
        weights = None
    else:
        wd = {}
        for (c1, c2), w, cat in zip(sample["combos"], sample["base_w"], sample["cats"]):
            wd[(min(c1, c2), max(c1, c2))] = w * (boost ** max(0, cat - 1))
        # 归一化与否不影响结果（_build_range 内部按总权重归一）
        weights = wd
    hole = sample["hole"]
    board = sample["board"]
    if len(board) >= 4:
        return E.exact_equity(hole, board, opp_range_pct=1.0,
                              opp_weights=weights, deadline=None)
    return E.monte_carlo_equity(hole, board, iterations=sample["iterations"],
                                opp_range_pct=1.0, opp_weights=weights,
                                rng=None, deadline=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=2000)
    a = ap.parse_args()
    paths = sorted(set(Path(p) for p in
                       glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
                   | set(Path(p) for p in
                         glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
    # 先重建 state 并缓存 hole/board（build_samples 里落盘用）
    samples = []
    for p in paths:
        ident = match_id(p)
        obj = json.loads(Path(p).read_bytes())
        seat = match_seat(obj)
        if seat is None:
            continue
        holes = hole_map(obj, seat)
        model = O.OpponentModel()
        ctx = M.MatchContext.from_dict(model.ctx_dict)
        n = 0
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
            mine, theirs = holes[int(state.hand_num)]
            rp = S._opp_range_pct(model,
                                  S._last_preflop_raiser(state) == state.opp_id,
                                  S._opp_street_raises(state))
            used = set(state.hole) | set(state.board)
            deck = [c for c in full_deck() if c not in used]
            combos, base_w, cats = [], [], []
            for c1, c2 in itertools.combinations(deck, 2):
                w = E._range_weight(hand_percentile([c1, c2]), rp, None)
                if w <= 0:
                    continue
                ev = evaluate_7([c1, c2] + list(state.board))
                combos.append((c1, c2))
                base_w.append(w)
                cats.append(ev[0] if ev else 0)
            samples.append(dict(m=ident, hand=int(state.hand_num), stage=state.stage,
                                hole=list(state.hole), board=list(state.board),
                                truth=exact_vs_hole(state.hole, state.board, theirs),
                                combos=combos, base_w=base_w, cats=cats,
                                iterations=a.iterations))
            n += 1
        print("  %-30s %2d 点" % (ident, n), flush=True)

    print("\n样本 %d" % len(samples))
    res = {}
    for name, boost in ARMS.items():
        res[name] = [eq_for(s, boost) for s in samples]
        errs = [e - s["truth"] for e, s in zip(res[name], samples)]
        print("  %-7s boost=%.1f  MAE %.4f  偏差 %+.3f"
              % (name, boost, statistics.mean(abs(x) for x in errs),
                 statistics.mean(errs)), flush=True)

    print("\n=== LOOCV（对局层面选 boost） ===")
    matches = sorted({s["m"] for s in samples})
    base_all, best_all, picks = [], [], []
    for held in matches:
        te = [i for i, s in enumerate(samples) if s["m"] == held]
        tr = [i for i, s in enumerate(samples) if s["m"] != held]
        best = min(ARMS, key=lambda k: statistics.mean(
            abs(res[k][i] - samples[i]["truth"]) for i in tr))
        picks.append(best)
        b = statistics.mean(abs(res["base"][i] - samples[i]["truth"]) for i in te)
        t = statistics.mean(abs(res[best][i] - samples[i]["truth"]) for i in te)
        base_all.append(b)
        best_all.append(t)
        print("  留出 %-26s 选 %-7s 基线 %.4f → %.4f" % (held[-26:], best, b, t))
    print("  ---- 基线 %.4f → 校准后 %.4f（%+.1f%%）  选中 %s"
          % (statistics.mean(base_all), statistics.mean(best_all),
             100.0 * (statistics.mean(best_all) / statistics.mean(base_all) - 1),
             dict(collections.Counter(picks))))


if __name__ == "__main__":
    main()
