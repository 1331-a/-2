# -*- coding: utf-8 -*-
"""
equity.py — 蒙特卡洛胜率估算（升级版）。

【升级思路】
  1. 对手范围抽样从「Chen 分数下限」改为「起手牌百分位范围」：
     opp_range_pct 直接来自对手建模的 VPIP 观测（对手越松范围越宽），
     比固定的 Chen 阈值更贴近对手真实分布；
  2. 加入 deadline 软时限：抽样循环按时钟自动提前收尾，宁可精度略降也不
     超时（超时=非法操作=弃牌）。
     【2026-09-30 修正】原注释写「平台每步限 1 秒」——那是 Botzone 的规则；
     本平台（botarena / 原 botbattle）Holdem 为**单步 60 秒**（平台只接受
     代码注册的稳定时限 ID，且容器启动/预热不计入）。软时限已据此放宽
     （见 strategy.TIME_BUDGET），真正的约束变为 iterations 上限。
  3. 每次迭代同时估算「成牌型分布」，供策略层做摊牌价值判断。
"""

import random
import time

from cards import full_deck
from evaluator import evaluate_7
from ranges import hand_percentile

_rng = random.Random()


def seed_rng(seed):
    """【2026-09-30】给抽样流播种 —— 让决策可复现。

    原先 `_rng` 从未播种：同一局面每次运行的抽样流都不同，导致
    「同一手牌重放两次结论不同」，实测结论无法复核，贴门槛的断言
    也会偶发翻转。播种后同一决策点必定得到同一结果。

    种子由 strategy._prepare_globals 按「决策上下文」确定性生成
    （同一局面 → 同一种子），因此不影响策略的多样性与随机化。
    """
    try:
        _rng.seed(int(seed))
    except Exception:
        pass


def monte_carlo_equity(hole, board, iterations=500, opp_range_pct=1.0,
                       rng=None, deadline=None):
    """
    估算我方底牌对抗对手范围的平均胜率（含平局折半）。

    hole           : 我的两张底牌（内部编码）
    board          : 公共牌（0~5 张）
    iterations     : 最大抽样次数（软上限，受 deadline 约束）
    opp_range_pct  : 对手起手范围（0~1，=对手只拿前 x% 的起手牌），
                     由 opponent 模型给出；1.0 表示完全随机
    deadline       : 单调时钟软时限（time.time()），到点提前收敛
    """
    rng = rng or _rng
    deck = [c for c in full_deck() if c not in hole and c not in board]
    need = 5 - len(board)

    wins = 0
    ties = 0
    total = 0
    for i in range(iterations):
        # 软时限：每 16 次检查一次时钟，避免超时被判非法
        if deadline is not None and (i & 15) == 0 and time.time() >= deadline:
            break
        opp = _sample_opponent(deck, opp_range_pct, rng)
        remaining = [c for c in deck if c not in opp]
        runout = rng.sample(remaining, need) if need else []

        my_score = evaluate_7(hole + board + runout)
        opp_score = evaluate_7(opp + board + runout)
        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            ties += 1
        total += 1

    if total == 0:
        return 0.5
    return (wins + 0.5 * ties) / total


def _sample_opponent(deck, range_pct, rng):
    """按起手百分位范围拒绝采样对手底牌。"""
    if range_pct >= 1.0:
        return rng.sample(deck, 2)
    for _ in range(120):
        h = rng.sample(deck, 2)
        if hand_percentile(h) <= range_pct:
            return h
    return rng.sample(deck, 2)  # 范围极窄时兜底随机

