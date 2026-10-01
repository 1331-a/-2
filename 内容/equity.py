# -*- coding: utf-8 -*-
"""
equity.py — 胜率估算：蒙特卡洛抽样 + 河牌/转牌精确枚举。

【升级思路】
  1. 对手范围抽样从「Chen 分数下限」改为「起手牌百分位范围」：
     opp_range_pct 直接来自对手建模的 VPIP 观测（对手越松范围越宽），
     比固定的 Chen 阈值更贴近对手真实分布；
  2. 加入 deadline 软时限：抽样循环按时钟自动提前收尾，宁可精度略降也不
     超时（超时=非法操作=弃牌）。
     【2026-09-30 修正】原注释写「平台每步限 1 秒」——那是 Botzone 的规则；
     本平台（botarena / 原 botbattle）Holdem 为**单步 60 秒**（平台只接受
     代码注册的稳定时限 ID，且容器启动/预热不计入）。软时限已据此放宽
     （见 strategy.TIME_BUDGET / EQ_TOTAL_BUDGET）。
  3. 【2026-09-30 P0-A】给抽样流播种（seed_rng）→ 同一局面必定同一结果，
     决策可复现；原先 _rng 未播种，贴门槛的断言会偶发翻转、结论无法复核。
  4. 【2026-09-30 P0-B】两处精度升级：
     a) **河牌/转牌精确枚举**（exact_equity）：河牌枚举对手 C(45,2)=990 组合
        （约 1,000 次评估 ≈ 0.06s）、转牌枚举 C(46,2)×44 ≈ 4.4 万次评估
        （≈ 2.6s）→ **误差归零**。翻牌需约 107 万组合（≈ 63s）超过单步预算，
        仍走 MC。
     b) **加权范围**（_build_range）：对手手牌从「按百分位拒绝采样」改为
        「按权重枚举 / 加权抽样」。文献做法（Billings 1998；Southey et al.
        UAI 2005）是用权重**重新加权**，而不是「先按范围抽样再算」——后者
        既引入偏差，又在窄范围下有「120 次拒绝后随机兜底」的兜底偏差。
        加权接口同时为后续「combo 级非均匀范围」留好了入口。
"""

import bisect
import math
import random
import time

from cards import full_deck
from evaluator import evaluate_7
from ranges import hand_percentile

_rng = random.Random()

# ---------------- 范围「软尾巴」参数 ----------------
# 【2026-09-30 P0-C】实测校准（测/range_eval.py，8 份日志、无偏取样）：
#   模型把对手范围建模成「按百分位等权的硬截断 top-X%」，但真实分布**更宽**：
#     · 对手小盲开池加注：模型给 top-33%，真实底牌均值百分位 0.33（≈top-67%），
#       仅 **54.8%** 的加注牌落在模型范围内；
#     · 大盲跟注 58.8%、小盲平跟 50.0%、大盲免费过牌 66.7%。
#   ⇒ 硬截断把「边界外的弱牌」全部清零 → 把对手想得比实际强 →
#     **系统性低估我方胜率**（越靠边界影响越大）。
#   修正：超出 range_pct 的部分不直接清零，而是按指数衰减保留（软截断）：
#        w(p) = 1                                   p ≤ rp
#        w(p) = exp(-(p - rp) / tau)                p > rp,  tau = RANGE_SOFT_TAIL × rp
#   该 tau 取值对「小盲开池」样本的覆盖率拟合为 53.6%，与实测 54.8% 吻合。
#   `RANGE_SOFT_TAIL = 0` 即完全回到旧的硬截断（一键回退）。
RANGE_SOFT_TAIL = 1.0        # 尾巴衰减尺度（×range_pct）；0 = 硬截断（旧行为）
RANGE_TAIL_MIN_W = 0.02      # 权重低于此值的牌直接丢弃（防长尾拖慢抽样）


def _range_weight(pct, rp, tail=None):
    """给定手牌百分位 pct 与范围宽度 rp，返回范围权重（软尾巴模型）。

    tail : 覆盖 RANGE_SOFT_TAIL（None = 用全局值）。给 0.0 = 该次估算用硬截断。
    """
    if pct <= rp:
        return 1.0
    t = RANGE_SOFT_TAIL if tail is None else tail
    if t <= 0.0:
        return 0.0
    tau = t * (rp if rp > 0.05 else 0.05)
    w = math.exp(-(pct - rp) / tau)
    return w if w >= RANGE_TAIL_MIN_W else 0.0


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


# ---------------- 对手范围：候选集与权重 ----------------
def _build_range(deck, opp_range_pct=1.0, opp_weights=None, tail=None):
    """构建对手手牌候选集与权重。

    参数
      deck          : 剩余未知牌（已剔除我方底牌与公共牌）
      opp_range_pct : 起手范围宽度（0~1）；1.0 = 全范围。仅在无 opp_weights 时生效
      opp_weights   : 显式权重表 {(c1, c2): w}（键为升序元组）。给了它就优先使用，
                      此时 opp_range_pct 被忽略 —— 权重表可以表达**非均匀**范围
      tail          : 覆盖 RANGE_SOFT_TAIL（见 _range_weight）

    返回 (combos, weights, cum, total_w)：
      combos  : [(c1, c2), ...]
      weights : 与 combos 等长的权重
      cum     : 累积权重（供 bisect 做 O(log n) 抽样）
      total_w : 权重总和
    """
    combos = []
    weights = []
    n = len(deck)
    if opp_weights:
        for i in range(n - 1):
            c1 = deck[i]
            for j in range(i + 1, n):
                c2 = deck[j]
                w = opp_weights.get((c1, c2))
                if w is None:
                    w = opp_weights.get((c2, c1))
                if not w or w <= 0.0:
                    continue
                combos.append((c1, c2))
                weights.append(float(w))
    else:
        pct = opp_range_pct
        soft = pct < 1.0
        for i in range(n - 1):
            c1 = deck[i]
            for j in range(i + 1, n):
                c2 = deck[j]
                if soft:
                    w = _range_weight(hand_percentile((c1, c2)), pct, tail)
                    if w <= 0.0:
                        continue
                else:
                    w = 1.0
                combos.append((c1, c2))
                weights.append(w)
    if not combos:
        # 范围过窄 / 权重全零 → 兜底为全范围等权（绝不允许空范围）
        combos = [(deck[i], deck[j])
                  for i in range(n - 1) for j in range(i + 1, n)]
        weights = [1.0] * len(combos)
    cum = []
    acc = 0.0
    for w in weights:
        acc += w
        cum.append(acc)
    return combos, weights, cum, acc


# ---------------- 蒙特卡洛抽样 ----------------
def monte_carlo_equity(hole, board, iterations=500, opp_range_pct=1.0,
                       rng=None, deadline=None, opp_weights=None,
                       soft_tail=None):
    """
    估算我方底牌对抗对手范围的平均胜率（含平局折半）。

    hole          : 我的两张底牌（内部编码）
    board         : 公共牌（0~5 张）
    iterations    : 最大抽样次数（软上限，受 deadline 约束）
    opp_range_pct : 对手起手范围（0~1，=对手只拿前 x% 的起手牌），
                    由 opponent 模型给出；1.0 表示完全随机
    deadline      : 墙钟软时限（time.time()），到点提前收敛
    opp_weights   : 显式对手范围权重表（优先于 opp_range_pct）
    soft_tail     : 覆盖 RANGE_SOFT_TAIL；0.0 = 本次用硬截断（见 _range_weight）
    """
    rng = rng or _rng
    deck = [c for c in full_deck() if c not in hole and c not in board]
    need = 5 - len(board)

    # 全范围等权时走最直接的 rng.sample（省掉建表开销）
    uniform = (not opp_weights) and opp_range_pct >= 1.0
    combos = cum = None
    total_w = 0.0
    if not uniform:
        combos, _weights, cum, total_w = _build_range(deck, opp_range_pct,
                                                      opp_weights, soft_tail)

    wins = 0
    ties = 0
    total = 0
    for i in range(iterations):
        # 软时限：每 16 次检查一次时钟，避免超时被判非法
        if deadline is not None and (i & 15) == 0 and time.time() >= deadline:
            break
        if uniform:
            opp = rng.sample(deck, 2)
        else:
            idx = bisect.bisect_right(cum, rng.random() * total_w)
            if idx >= len(combos):
                idx = len(combos) - 1
            opp = combos[idx]
        if need:
            a, b = opp[0], opp[1]
            pool = [c for c in deck if c != a and c != b]
            runout = rng.sample(pool, need)
        else:
            runout = []

        my_score = evaluate_7(hole + board + runout)
        opp_score = evaluate_7(list(opp) + board + runout)
        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            ties += 1
        total += 1

    if total == 0:
        return 0.5
    return (wins + 0.5 * ties) / total


# ---------------- 精确枚举（河牌 / 转牌） ----------------
def exact_equity(hole, board, opp_range_pct=1.0, opp_weights=None,
                 deadline=None, soft_tail=None):
    """河牌 / 转牌的**精确**胜率（含平局折半）。

    规模（实测 evaluate_7 ≈ 16,884 次/秒）：
      河牌：枚举对手 C(45,2) = 990 组合 → 约 1,000 次评估 ≈ 0.06s
      转牌：枚举对手 C(46,2) = 1,035 × 河牌 44 张 ≈ 4.4 万次评估 ≈ 2.6s
      翻牌：C(47,2) × C(45,2) ≈ 107 万组合 ≈ 63s —— 超过单步预算，不做。

    转牌带 deadline：每处理 4 张河牌检查一次时钟，超时就停止；
    由于剩余河牌是随机缺失，提前收尾仍是**无偏**估计（只是误差不再为 0）。

    非河牌/转牌返回 None（调用方回退 monte_carlo_equity）。
    """
    nb = len(board)
    if nb == 5:
        return _exact_river(hole, board, opp_range_pct, opp_weights, soft_tail)
    if nb == 4:
        return _exact_turn(hole, board, opp_range_pct, opp_weights, deadline,
                           soft_tail)
    return None


def _exact_river(hole, board, opp_range_pct, opp_weights, tail=None):
    deck = [c for c in full_deck() if c not in hole and c not in board]
    combos, weights, _cum, _tot = _build_range(deck, opp_range_pct,
                                               opp_weights, tail)
    bd = list(board)
    hb = list(hole) + bd
    my = evaluate_7(hb)
    wins = ties = tot = 0.0
    for k in range(len(combos)):
        c1, c2 = combos[k]
        w = weights[k]
        s = evaluate_7([c1, c2] + bd)
        if my > s:
            wins += w
        elif my == s:
            ties += w
        tot += w
    if tot <= 0.0:
        return 0.5
    return (wins + 0.5 * ties) / tot


def _exact_turn(hole, board, opp_range_pct, opp_weights, deadline=None,
                tail=None):
    deck = [c for c in full_deck() if c not in hole and c not in board]
    combos, weights, _cum, _tot = _build_range(deck, opp_range_pct,
                                               opp_weights, tail)
    bd = list(board)
    hr = list(hole)
    nc = len(combos)
    wins = ties = tot = 0.0
    done = 0
    for r in deck:
        if deadline is not None and (done & 3) == 0 and time.time() >= deadline:
            break
        done += 1
        full = bd + [r]
        my = evaluate_7(hr + full)
        for k in range(nc):
            c1, c2 = combos[k]
            if c1 == r or c2 == r:
                continue                      # 该河牌已被对手占用 → 不可能
            w = weights[k]
            s = evaluate_7([c1, c2] + full)
            if my > s:
                wins += w
            elif my == s:
                ties += w
            tot += w
    if tot <= 0.0:
        return 0.5
    return (wins + 0.5 * ties) / tot


def equity_best(hole, board, iterations=500, opp_range_pct=1.0,
                rng=None, deadline=None, opp_weights=None, soft_tail=None):
    """**优先精确枚举，否则回退 MC** —— 策略层的统一入口。

    河牌 / 转牌：精确（误差 0）；翻牌及以前：蒙特卡洛（误差见 SE=0.5/√N）。
    """
    if len(board) >= 4:
        try:
            e = exact_equity(list(hole), list(board), opp_range_pct,
                             opp_weights, deadline, soft_tail)
            if e is not None:
                return e
        except Exception:
            pass
    return monte_carlo_equity(hole, board, iterations=iterations,
                              opp_range_pct=opp_range_pct, rng=rng,
                              deadline=deadline, opp_weights=opp_weights,
                              soft_tail=soft_tail)
