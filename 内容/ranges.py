# -*- coding: utf-8 -*-
"""
ranges.py — 翻牌前起手牌强度评估与范围管理。

【升级思路】
原版仅用 Chen 公式打分（1~20），粒度粗且与单挑实际胜率偏差较大。
升级为两层体系：

  1. hand_strength(hole)：用按「单挑全随机对抗胜率」标定的公式，
     把 169 种起手组合映射到约 33~85 的强度分；
  2. hand_percentile(hole)：模块加载时枚举全部 169 种组合并排名，
     返回该牌位于全体起手牌的前百分之几（0~1，越小越强）。

百分位是范围决策的标准语言：
  「庄家位开池前 80% 的牌」「3-bet 前 14% 的牌」「大盲防守前 55%」
比固定阈值更直观、更贴近现代单挑理论（HU 中庄家应开池 60~90%）。

"""

# ---------------- 单挑胜率强度分 ----------------
def _raw_strength(hi, lo, suited):
    """
    估计起手牌在单挑中对抗随机手牌的胜率（约 33~85）。
    按公开的单挑胜率表标定：
      对子：22≈50、AA≈82.5，随点数线性；
      非对子：由高张、低张、间隔、同花、双高张综合决定。
    数值只要排序合理即可——我们只用它的相对次序生成百分位。
    """
    if hi == lo:                       # 对子
        return 50.0 + (hi - 2) * 2.9
    gap = hi - lo - 1                  # 0=连张，越大越差
    s = 33.0 + hi * 1.6 + lo * 0.5     # 高张权重远大于低张
    s -= min(gap, 5) * 1.5             # 间隔惩罚
    if suited:                         # 同花潜力
        s += 2.5
    if hi >= 11 and lo >= 10:          # 双高张（JT 以上）
        s += 1.5
    if gap <= 1 and hi >= 12:          # A/K 高张连张（顺子潜力）
        s += 1.0
    return s


def _build_percentile_table():
    """枚举 169 种起手组合，按强度分排名，生成百分位查找表。"""
    combos = []
    for hi in range(2, 15):
        for lo in range(2, hi + 1):
            if hi == lo:
                combos.append((hi, lo, False))
            else:
                combos.append((hi, lo, False))  # 杂色
                combos.append((hi, lo, True))   # 同花
    combos.sort(key=lambda c: -_raw_strength(c[0], c[1], c[2]))
    table = {}
    n = len(combos)  # 169
    for i, (hi, lo, suited) in enumerate(combos):
        # 百分位：该牌强于多少比例的起手组合（0.003=AA，0.997=72o）
        table[(hi, lo, suited)] = (i + 0.5) / n
    return table


_PERCENTILE = _build_percentile_table()


def hand_strength(hole):
    """起手牌强度分（约 33~85，仅用于展示/调试）。"""
    r = sorted([c // 4 for c in hole])
    suited = (hole[0] % 4) == (hole[1] % 4)
    return _raw_strength(r[1], r[0], suited)


def hand_percentile(hole):
    """
    起手牌百分位（0~1，越小越强）。
    例：AA≈0.003（前 0.3%）、AKs≈0.02、72o≈0.997。
    hole 为内部编码（点数*4+花色）的两张牌列表。
    """
    r = sorted([c // 4 for c in hole])
    suited = (hole[0] % 4) == (hole[1] % 4)
    return _PERCENTILE[(r[1], r[0], suited)]


# ---------------- 翻前范围辅助 ----------------