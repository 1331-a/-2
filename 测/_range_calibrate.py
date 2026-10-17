# -*- coding: utf-8 -*-
"""eq 范围校准：扫描「范围宽度倍数 k」，并用**留一法（LOOCV）**验证。

问题：`eq` 系统性高估我方胜率（旧口径 +0.15 ~ +0.28）。假设原因是
`_opp_range_pct`（按对手 VPIP 推 top-X%）**把对手范围估得太宽** ⇒ 我方 eq 偏高。

做法：
  对每个「翻后有对手下注」的决策点，用日志里**对手真实底牌**算精确真值 truth；
  再用同一 state 以 `range_pct × k` 重算 eq；扫描 k，看 MAE / 偏差。
  ★ 关键：k 必须在**留出的对局**上评估（LOOCV），否则就是自证。

用法：
  python -X utf8 测/_range_calibrate.py --iterations 3000
  python -X utf8 测/_range_calibrate.py --match 20261012185239-b586268f   # 单场明细
"""
import argparse
import collections
import glob
import json
import random
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

import equity as E                                      # noqa: E402
import game_state as G                                  # noqa: E402
import match_ctx as M                                   # noqa: E402
import opponent as O                                    # noqa: E402
import strategy as S                                    # noqa: E402
from botbattle_log import load_botbattle                # noqa: E402
from _range_condition_audit import (                    # noqa: E402
    exact_vs_hole, hole_map, match_id, match_seat)

KS = [0.25, 0.40, 0.55, 0.70, 0.85, 1.00, 1.15]


def eq_at(state, range_pct, seed, iterations):
    if len(state.board) >= 4:
        return E.exact_equity(state.hole, state.board,
                              opp_range_pct=range_pct, deadline=None)
    return E.monte_carlo_equity(
        state.hole, state.board, iterations=iterations,
        opp_range_pct=range_pct, rng=random.Random(seed), deadline=None)


def build_rows(paths, iterations, only_match=None):
    rows = []
    for p in paths:
        ident = match_id(p)
        if only_match and ident != only_match:
            continue
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
            if mine != state.hole:
                raise ValueError("hole mismatch %r" % ((ident, state.hand_num),))
            last = S._last_preflop_raiser(state)
            street_raises = S._opp_street_raises(state)
            rp = S._opp_range_pct(model, last == state.opp_id, street_raises)
            seed = S._decision_seed(state)
            truth = exact_vs_hole(state.hole, state.board, theirs)
            eqs = {}
            for k in KS:
                eqs[k] = eq_at(state, max(0.02, min(1.0, rp * k)), seed, iterations)
            rows.append(dict(m=ident, hand=int(state.hand_num), stage=state.stage,
                             rp=rp, truth=truth, eqs=eqs,
                             need=state.to_call / float(state.pot + state.to_call),
                             lead=state.total_win_chips[state.my_id]
                             - state.total_win_chips[state.opp_id]))
            n += 1
        print("%-30s %3d 个点" % (ident, n), flush=True)
    return rows


def mae(rows, k):
    return statistics.mean(abs(r["eqs"][k] - r["truth"]) for r in rows)


def bias(rows, k):
    return statistics.mean(r["eqs"][k] - r["truth"] for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=3000)
    ap.add_argument("--match")
    ap.add_argument("--output", type=Path,
                    default=BASE / "\u6d4b" / "_range_calibrate.json")
    a = ap.parse_args()
    paths = sorted(set(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
                   | set(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
    paths = [Path(p) for p in paths]
    rows = build_rows(paths, a.iterations, a.match)
    if not rows:
        print("没有样本")
        return
    print("\n样本 %d 个点、%d 场、%d 手"
          % (len(rows), len({r["m"] for r in rows}), len({(r["m"], r["hand"]) for r in rows})))
    print("真值 eq 均值 %.3f | 需要胜率均值 %.3f" %
          (statistics.mean(r["truth"] for r in rows),
           statistics.mean(r["need"] for r in rows)))

    print("\n=== 全局扫描（同一份数据，仅作参考；结论看 LOOCV） ===")
    print("%-6s %8s %8s %8s" % ("k", "MAE", "偏差", "RMSE"))
    for k in KS:
        print("%-6.2f %8.4f %+8.3f %8.4f"
              % (k, mae(rows, k), bias(rows, k),
                 (statistics.mean((r["eqs"][k] - r["truth"]) ** 2
                                  for r in rows)) ** 0.5))

    print("\n=== 留一法（LOOCV）：在 7 场上选 k，在留出的那场上报 MAE ===")
    matches = sorted({r["m"] for r in rows})
    if len(matches) < 3:
        print("对局数 < 3，无法做留出验证")
    else:
        base_all, tuned_all, tuned_ks = [], [], []
        for held in matches:
            train = [r for r in rows if r["m"] != held]
            test = [r for r in rows if r["m"] == held]
            kb = min(KS, key=lambda k: mae(train, k))
            tuned_ks.append(kb)
            base_all.append(mae(test, 1.00))
            tuned_all.append(mae(test, kb))
            print("  留出 %-26s 训练选 k=%.2f | 留出集 MAE 基线(1.00) %.4f → 校准后 %.4f"
                  % (held[-26:], kb, base_all[-1], tuned_all[-1]))
        print("  ---- LOOCV 汇总：基线 MAE %.4f → 校准后 %.4f（%+.1f%%）"
              % (statistics.mean(base_all), statistics.mean(tuned_all),
                 100.0 * (statistics.mean(tuned_all) / statistics.mean(base_all) - 1)))
        print("  选出的 k 分布：", collections.Counter(tuned_ks))

    # 分档诊断：偏差是否随「需要胜率」变化
    print("\n=== 偏差结构（按需要的胜率分档，k=1.00） ===")
    bins = collections.defaultdict(list)
    for r in rows:
        b = min(4, int(r["need"] * 5))       # 0~0.2, ... 0.8~1.0
        bins[b].append(r["eqs"][1.00] - r["truth"])
    for b in sorted(bins):
        v = bins[b]
        print("  need %.1f~%.1f : n=%2d 偏差 %+0.3f" % (b / 5.0, (b + 1) / 5.0,
                                                       len(v), statistics.mean(v)))

    # 分街
    print("\n=== 分街（k=1.00） ===")
    for st in ("flop", "turn", "river"):
        v = [r for r in rows if r["stage"] == st]
        if v:
            print("  %-6s n=%2d MAE %.4f 偏差 %+0.3f"
                  % (st, len(v), mae(v, 1.00), bias(v, 1.00)))

    a.output.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n明细已写 %s" % a.output)


if __name__ == "__main__":
    main()
