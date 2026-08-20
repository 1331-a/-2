# -*- coding: utf-8 -*-
# 由 bundle.py 自动生成的单文件提交版本（BotZone 用）。

# -*- coding: utf-8 -*-
"""
cards.py — 扑克牌表示与解析工具。

内部统一用一个整数表示一张牌：card = rank * 4 + suit
  - rank（点数）: 2..14（11=J, 12=Q, 13=K, 14=A）
  - suit（花色）: 0=黑桃S, 1=红桃H, 2=方块D, 3=梅花C

BotZone 牌字符串格式："花色 + 点数"，例如
  "SA" -> 黑桃 A，  "HT" -> 红桃 10，  "C3" -> 梅花 3，  "DQ" -> 方块 Q
"""

# 花色
SUIT_NAMES = {0: "S", 1: "H", 2: "D", 3: "C"}
SUITS = {"S": 0, "H": 1, "D": 2, "C": 3}

# 点数
RANK_NAMES = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
              9: "9", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}
RANK_STR = {v: k for k, v in RANK_NAMES.items()}
RANK_STR["t"] = 10  # 兼容小写 t 表示 10


def parse_card(s):
    """把 BotZone 牌字符串解析为整数。例如 'SA' -> 56。"""
    s = s.strip()
    return RANK_STR[s[1]] * 4 + SUITS[s[0]]


def card_str(c):
    """把整数牌转回字符串。"""
    return SUIT_NAMES[c % 4] + RANK_NAMES[c // 4]


def rank(c):
    """牌的点数（2..14）。"""
    return c // 4


def suit(c):
    """牌的花色（0..3）。"""
    return c % 4


def full_deck():
    """返回一副完整 52 张牌（整数列表）。"""
    return [r * 4 + s for r in range(2, 15) for s in range(4)]


def parse_cards(seq):
    """把牌字符串列表解析为整数列表。"""
    return [parse_card(s) for s in seq]

# -*- coding: utf-8 -*-
"""
evaluator.py — 牌型评估器。

从 7 张牌（2 张底牌 + 最多 5 张公共牌）中选出最强的 5 张组合并评估牌型。

牌型等级（从高到低）：
  9  皇家同花顺  Royal Flush      A-K-Q-J-T 同花
  8  同花顺      Straight Flush
  7  四条        Four of a Kind
  6  葫芦        Full House
  5  同花        Flush
  4  顺子        Straight
  3  三条        Three of a Kind
  2  两对        Two Pair
  1  一对        One Pair
  0  高牌        High Card

评估结果统一表示为一个 6 元组：(category, t1, t2, t3, t4, t5)
Python 的元组比较规则可直接用于牌型大小比较（先比 category，再依次比各 tiebreaker）。
"""

from itertools import combinations

# 牌型等级常量
ROYAL_FLUSH = 9
STRAIGHT_FLUSH = 8
FOUR_OF_A_KIND = 7
FULL_HOUSE = 6
FLUSH = 5
STRAIGHT = 4
THREE_OF_A_KIND = 3
TWO_PAIR = 2
ONE_PAIR = 1
HIGH_CARD = 0

CATEGORY_NAMES = {
    ROYAL_FLUSH: "皇家同花顺",
    STRAIGHT_FLUSH: "同花顺",
    FOUR_OF_A_KIND: "四条",
    FULL_HOUSE: "葫芦",
    FLUSH: "同花",
    STRAIGHT: "顺子",
    THREE_OF_A_KIND: "三条",
    TWO_PAIR: "两对",
    ONE_PAIR: "一对",
    HIGH_CARD: "高牌",
}


def evaluate_5(cards):
    """评估恰好 5 张牌，返回可比 6 元组。"""
    ranks = sorted((c // 4 for c in cards), reverse=True)
    is_flush = len({c % 4 for c in cards}) == 1

    # 顺子检测（含 A-2-3-4-5 轮子）
    uniq = sorted(set(ranks), reverse=True)
    straight_high = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_high = 5  # 轮子：A 当 1 用，最高牌为 5

    # 点数计数，按 (数量, 点数) 降序分组
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)

    if is_flush and straight_high:
        if straight_high == 14:
            return (ROYAL_FLUSH, 0, 0, 0, 0, 0)
        return (STRAIGHT_FLUSH, straight_high, 0, 0, 0, 0)

    top_count = groups[0][1]

    if top_count == 4:
        return (FOUR_OF_A_KIND, groups[0][0], groups[1][0], 0, 0, 0)

    if top_count == 3 and groups[1][1] == 2:
        return (FULL_HOUSE, groups[0][0], groups[1][0], 0, 0, 0)

    if is_flush:
        return (FLUSH, ranks[0], ranks[1], ranks[2], ranks[3], ranks[4])

    if straight_high:
        return (STRAIGHT, straight_high, 0, 0, 0, 0)

    if top_count == 3:
        kickers = [g[0] for g in groups[1:]]
        return (THREE_OF_A_KIND, groups[0][0], kickers[0], kickers[1], 0, 0)

    if top_count == 2 and groups[1][1] == 2:
        return (TWO_PAIR, groups[0][0], groups[1][0], groups[2][0], 0, 0)

    if top_count == 2:
        kickers = [g[0] for g in groups[1:]]
        return (ONE_PAIR, groups[0][0], kickers[0], kickers[1], kickers[2], 0)

    return (HIGH_CARD, ranks[0], ranks[1], ranks[2], ranks[3], ranks[4])


def evaluate_7(cards):
    """从 5~7 张牌中选出最佳 5 张并评估，返回可比 6 元组。

    注：曾尝试改写为单遍位运算直达版，但纯 Python 的位运算/多趟循环
    反而比 `combinations + evaluate_5`（evaluate_5 内部用 C 实现的
    sorted/set/dict）更慢约 12%。蒙特卡洛单步仅约 50ms，离 1 秒时限
    还有 20 倍余量，评估器不是瓶颈，故沿用此实现。
    """
    best = None
    for combo in combinations(cards, 5):
        e = evaluate_5(combo)
        if best is None or e > best:
            best = e
    return best


def category_name(result):
    """返回牌型的中文名称。"""
    return CATEGORY_NAMES.get(result[0], "未知")


def compare(my_cards, opp_cards):
    """比较双方手牌（7 张），返回 1（我胜）/ 0（平）/ -1（我负）。"""
    m = evaluate_7(my_cards)
    o = evaluate_7(opp_cards)
    if m > o:
        return 1
    if m < o:
        return -1
    return 0

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
比 Chen 阈值更直观、更贴近现代单挑理论（HU 中庄家应开池 60~90%）。

Chen 公式保留（equity 的旧采样路径与调试用）。
"""

import math

# ---------------- Chen 公式（保留兼容） ----------------
_CHEN_POINTS = {
    14: 10, 13: 8, 12: 7, 11: 6, 10: 5, 9: 4.5, 8: 4,
    7: 3.5, 6: 3, 5: 2.5, 4: 2, 3: 1.5, 2: 1,
}
_GAP_PENALTY = {0: 0, 1: -1, 2: -2, 3: -4}


def chen_score(hole):
    """计算两张底牌的 Chen 分数（约 1~20，越高越强）。"""
    r = sorted([c // 4 for c in hole])
    suited = (hole[0] % 4) == (hole[1] % 4)

    if r[0] == r[1]:  # 对子
        s = _CHEN_POINTS[r[0]] * 2
        return max(s, 5)

    hi, lo = r[1], r[0]
    s = _CHEN_POINTS[hi]
    if suited:
        s += 2
    gap = hi - lo - 1
    s += _GAP_PENALTY.get(gap, -5)
    if hi < 12 and gap <= 1:
        s += 1
    return math.ceil(s * 2) / 2.0


def hand_bucket(chen):
    """把 Chen 分数归入粗略强度档位（兼容旧接口）。"""
    if chen >= 12:
        return "premium"
    if chen >= 9:
        return "strong"
    if chen >= 7:
        return "medium"
    if chen >= 5:
        return "marginal"
    return "trash"


# ---------------- 单挑胜率强度分（升级版核心） ----------------
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
def in_range(hole, pct):
    """该牌是否位于前 pct 比例的范围内（pct: 0~1，越小越紧）。"""
    return hand_percentile(hole) <= pct


def random_hand_in_range(pct, rng, excluded=()):
    """
    从「前 pct 比例」的起手范围内随机抽一手牌（拒绝采样）。
    excluded 中的内部编码牌不可用。用于蒙特卡洛对手范围抽样。
    """
    excluded = set(excluded)
    deck = [c for c in range(8, 60) if c not in excluded]
    for _ in range(120):
        h = rng.sample(deck, 2)
        if hand_percentile(h) <= pct:
            return h
    return rng.sample(deck, 2)  # 兜底：范围极窄抽不中时随机

# -*- coding: utf-8 -*-
"""
game_state.py — BotZone 德州扑克官方协议解析与牌局状态重建。

官方协议要点（只支持 JSON 交互，每步限时 1 秒）：
  - 牌用 0~51 整数编号：点数 = n//4 + 2（2~14，A=14），花色 = n%4
    （0=红桃，1=方块，2=黑桃，3=草花）。
  - request 字段：num_players / dealer_id / my_id / my_chips / my_cards /
    public_cards / history / hand / max_hand / total_win_chips / total_win_games。
    每手牌筹码重置为 INIT_CHIPS（20000）。
  - response 为单个整数：-1 弃牌 / -2 全押 / 0 跟注或过牌 / >0 加注。
  - 加注语义（raise-to）：数字 = 加注后本轮我的总下注额。合法性：
      * 非首位加注：数字 >= 本轮最大下注额的 2 倍；
      * 首位加注（本轮无人下注）：数字 >= 大盲注；
      * 数字 < 自己剩余筹码数。
  - 非法操作一律按弃牌处理，包括：崩溃/超时、非整数、
    跟注但剩余筹码 <= 需跟注额、加注不满足上述约束、
    本局有人全押后返回弃牌/全押以外的动作。

内部牌编码 = 点数*4 + 花色 = BotZone 牌号 + 8，与 evaluator/ranges 兼容。

关键设计：所有影响「合法性」的量（to_call / 最小加注 / 全下判定）都不
依赖盲注常数——翻前用 my_chips 与对手最近动作精确推导，翻后只重放当前
轮的 history。即使盲注/初始筹码假设有偏差，也只会影响下注尺寸（EV），
绝不会产生非法操作。
"""

INIT_CHIPS = 20000        # 每手牌重置的初始筹码
DEFAULT_BIG_BLIND = 200   # 盲注默认值（仅用于下注尺寸，不影响合法性）


class GameState:
    """一手牌在某个决策点的抽象状态（由 request 重建而来）。"""

    def __init__(self, request):
        self.request = request
        self.num_players = request.get("num_players", 2)
        self.dealer_id = request.get("dealer_id", 0)
        self.my_id = request.get("my_id", 0)
        self.opp_id = 1 - self.my_id  # heads-up
        self.my_chips = int(request.get("my_chips", 0))
        self.my_cards = [int(c) + 8 for c in request.get("my_cards", [])]
        self.public_cards = [int(c) + 8 for c in request.get("public_cards", [])]
        self.history = request.get("history", []) or []
        self.hand_num = request.get("hand", 0)
        self.max_hand = request.get("max_hand", 50)
        self.total_win_chips = request.get("total_win_chips", [0, 0])
        self.total_win_games = request.get("total_win_games", [0, 0])

        self.small_blind = DEFAULT_BIG_BLIND // 2
        self.big_blind = DEFAULT_BIG_BLIND

        self._analyze()

    # ---------------- 状态重建 ----------------
    def _analyze(self):
        hist = self.history
        n_pub = len(self.public_cards)
        # 当前下注轮：0 preflop / 1 flop / 2 turn / 3 river（由公共牌数决定）
        self.current_round = 0 if n_pub == 0 else (1 if n_pub <= 3 else (2 if n_pub == 4 else 3))

        # 本手牌是否有人全押（规则5：此后只能弃牌/全押）
        self.any_allin = False
        for r in hist:
            if r.get("action_type") == "allin" or r.get("action") == -2:
                self.any_allin = True

        # 本手牌我累计投入（每手牌筹码重置为 INIT_CHIPS）
        my_total_in = max(0, INIT_CHIPS - self.my_chips)

        cur = [r for r in hist if int(r.get("round", 0)) == self.current_round]
        i_acted = any(r.get("player_id") == self.my_id for r in cur)

        if self.current_round == 0:
            # ---------- 翻前：盲注无关的精确推导 ----------
            self.my_round_bet = my_total_in
            opp_last = None
            for r in cur:
                if r.get("player_id") == self.opp_id:
                    opp_last = r

            # 盲注动态推导（仅影响下注尺寸）
            if not i_acted and my_total_in > 0:
                if self.my_id == self.dealer_id:
                    # 我第一个行动 = 庄家/小盲：SB = 已投盲注，BB = 2*SB
                    self.small_blind = my_total_in
                    self.big_blind = 2 * my_total_in
                else:
                    # 我是大盲等待选项/面对加注：我的翻前投入即大盲
                    self.big_blind = my_total_in
                    self.small_blind = my_total_in // 2

            if opp_last is None:
                # 我先行动（庄家/小盲）：需补足到大盲
                self.opp_round_bet = self.big_blind
                self._opp_round_known = True
            else:
                a = opp_last.get("action", 0)
                at = opp_last.get("action_type", "")
                if at == "raise" or (isinstance(a, int) and not isinstance(a, bool) and a > 0):
                    # raise-to 语义：数字即对手本轮总注额
                    self.opp_round_bet = int(a)
                    self._opp_round_known = True
                elif at == "allin" or a == -2:
                    # 金额未知，取上界估计；any_allin 已置位，只能弃牌/全押
                    self.opp_round_bet = self.my_round_bet + self.my_chips
                    self._opp_round_known = False
                else:  # call / check：已跟平
                    self.opp_round_bet = self.my_round_bet
                    self._opp_round_known = True
        else:
            # ---------- 翻后：本轮从 0 重放（不涉及盲注） ----------
            rb = [0, 0]
            for r in cur:
                p = int(r.get("player_id", 0))
                if p != 0 and p != 1:
                    continue
                a = r.get("action", 0)
                at = r.get("action_type", "")
                if at == "raise" or (isinstance(a, int) and not isinstance(a, bool) and a > 0):
                    rb[p] = max(rb[p], int(a))       # raise-to 语义
                elif at == "allin" or a == -2:
                    rb[p] = max(rb[p], max(rb))      # 金额未知，仅估上界
                elif at == "fold" or a == -1:
                    pass
                else:                                # call / check：跟平当前最大注
                    rb[p] = max(rb)
            self.my_round_bet = rb[self.my_id]
            self.opp_round_bet = rb[self.opp_id]
            self._opp_round_known = True

        # to_call：还需跟注的筹码（0 表示可过牌）
        if self._opp_round_known:
            self._to_call = max(0, self.opp_round_bet - self.my_round_bet)
        else:
            self._to_call = self.my_chips  # 对手全押金额未知 → 按需全押应对
        if self.any_allin:
            # 规则5：有人全押后不允许 check/call，保证 to_call > 0
            self._to_call = max(self._to_call, 1)

        # 对手累计投入估计（仅用于底池规模 / SPR，不影响合法性）
        if self.current_round == 0:
            my_preflop_in = self.my_round_bet
        else:
            my_preflop_in = max(0, my_total_in - self.my_round_bet)
        opp_total_in_est = my_preflop_in + self.opp_round_bet
        self.opp_chips = max(0, INIT_CHIPS - opp_total_in_est)

    # ---------------- 派生信息 ----------------
    @property
    def stage(self):
        return ("preflop", "flop", "turn", "river")[min(self.current_round, 3)]

    @property
    def to_call(self):
        """跟注还需投入的筹码（0 表示可以过牌）。"""
        return self._to_call

    @property
    def is_button(self):
        """庄家位（heads-up 中庄家=小盲，翻前先行动）。"""
        return self.my_id == self.dealer_id

    @property
    def my_left(self):
        return self.my_chips

    @property
    def opp_left(self):
        return self.opp_chips

    @property
    def my_total(self):
        return self.round_bet_mine + self.my_chips

    @property
    def opp_total(self):
        return self.opp_round_bet + self.opp_chips

    @property
    def round_bet_mine(self):
        return self.my_round_bet

    @property
    def effective_stack(self):
        return min(self.my_chips, self.opp_chips)

    @property
    def opp_is_allin(self):
        return self.any_allin

    @property
    def pot(self):
        """底池估计 = 双方累计投入之和。"""
        return (INIT_CHIPS - self.my_chips) + (INIT_CHIPS - self.opp_chips)

    # ---------------- 兼容旧接口（供 strategy 使用） ----------------
    @property
    def curbet(self):
        """按玩家编号索引的本轮注额 [p0, p1]。"""
        rb = [0, 0]
        rb[self.my_id] = self.my_round_bet
        rb[self.opp_id] = self.opp_round_bet
        return rb

    @property
    def blind(self):
        return self.small_blind

    @property
    def hole(self):
        return self.my_cards

    @property
    def board(self):
        return self.public_cards

    # ---------------- 合法动作边界 ----------------
    def min_raise(self):
        """最小加注数（raise-to 语义）：
        本轮已有下注 → >= 2 倍本轮最大注额；本轮无人下注 → >= 大盲注。"""
        cur_max = self.my_round_bet
        if self._opp_round_known:
            cur_max = max(cur_max, self.opp_round_bet)
        if cur_max <= 0:
            return self.big_blind
        return 2 * cur_max

    def max_raise(self):
        """最大加注数（保守上界：保证任何加注语义下都不超过筹码）。"""
        return max(0, self.my_chips - self._to_call - 1)


def parse_request(request):
    """把 BotZone request JSON（dict）解析为 GameState。"""
    return GameState(request)

# -*- coding: utf-8 -*-
"""
equity.py — 蒙特卡洛胜率估算（升级版）。

【升级思路】
  1. 对手范围抽样从「Chen 分数下限」改为「起手牌百分位范围」：
     opp_range_pct 直接来自对手建模的 VPIP 观测（对手越松范围越宽），
     比固定的 Chen 阈值更贴近对手真实分布；
  2. 加入 deadline 软时限：平台每步限 1 秒，抽样循环按时钟自动
     提前收尾，宁可精度略降也不超时（超时=非法操作=弃牌）；
  3. 每次迭代同时估算「成牌型分布」，供策略层做摊牌价值判断。
"""

import random
import time


_rng = random.Random()


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


def estimate_showdown_equity(hole, board, iterations=300, rng=None, deadline=None):
    """
    估算当前成牌在摊牌时的胜率（不补发公共牌，仅评估当前牌型
    对抗随机对手成牌）。河牌决策用：纯 value/bluff 判断。
    """
    rng = rng or _rng
    if len(board) < 3:
        return monte_carlo_equity(hole, board, iterations, 1.0, rng, deadline)
    deck = [c for c in full_deck() if c not in hole and c not in board]
    wins = ties = total = 0
    for i in range(iterations):
        if deadline is not None and (i & 15) == 0 and time.time() >= deadline:
            break
        opp = rng.sample(deck, 2)
        my_score = evaluate_7(hole + board)
        opp_score = evaluate_7(opp + board)
        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            ties += 1
        total += 1
    if total == 0:
        return 0.5
    return (wins + 0.5 * ties) / total

# -*- coding: utf-8 -*-
"""
opponent.py — 对手建模（升级版）。

【升级思路】
原版只有 7 个计数器算 3 个粗糙指标。升级为「扑克统计画像」：

  1. VPIP（ voluntarily put money in pot，翻前入池率）
     PFR（翻前主动加注率）
     AF （翻后主动下注/加注频率）
     Fold-to-Bet（面对下注的弃牌率）
     Big-Raise-Freq（大注占比：加注额 >= 3 倍本轮当前最大注）
     Allin 频率
  2. 原型分类 archetype()：station(跟注站)/maniac(疯子)/
     rock(岩石)/tag(紧凶)/unknown，供策略层做剥削调整；
  3. 小样本收缩（shrinkage）：样本不足时统计量向先验收缩，
     避免被几手牌的噪声带偏——这是风控的重要一环；
  4. 跨手牌持久化（globaldata）+ 同手牌去重（last_opp_count）。
"""

import json

# 先验值：BotZone 天梯混战偏「松弱」（跟注多、爱被动），故先验 VPIP 偏高、
# PFR 偏低。注意这是单挑（heads-up）口径——HU 中 VPIP 天然远高于 6-max。
_PRIOR = {
    "vpip": 0.68, "pfr": 0.30, "af": 0.35,
    "fold_to_bet": 0.40, "big_raise": 0.25,
    "turn_aggr": 0.35, "river_fold": 0.40,
}
_SHRINK_K = 12   # 收缩强度：约 12 次观测后统计量才以数据为主
_DECAY_EVERY = 15  # 每 15 手牌做一次指数衰减（近期数据双倍权重）


class OpponentModel:
    """对手行为画像（纯计数，可 JSON 序列化，跨手牌持久化）。"""

    def __init__(self):
        # ---- 翻前动作计数 ----
        self.preflop_raise = 0
        self.preflop_call = 0
        self.preflop_fold = 0
        # ---- 翻后动作计数 ----
        self.postflop_bet = 0     # 主动下注/加注
        self.postflop_call = 0
        self.postflop_fold = 0
        self.postflop_check = 0
        # ---- 升级新增 ----
        self.postflop_big_raise = 0  # 大注（>= 3 倍本轮当前最大注）
        self.allin_count = 0         # 全押次数
        self.hands_seen = 0          # 观测到对手行动的手牌数
        self.faces_bet = 0           # 翻后面对下注的次数（call+fold）
        # ---- 街级特征（转牌/河牌独立统计，用于剥削微调）----
        self.turn_raise = 0          # 转牌主动加注次数
        self.turn_decisions = 0      # 转牌总决策次数
        self.river_fold = 0           # 河牌面对下注的弃牌次数
        self.river_faces = 0          # 河牌面对下注次数（call+fold）
        # ---- 去重游标（同一手牌的多回合不重复计数） ----
        self.last_hand = None
        self.last_opp_count = 0

    # ---------------- 原始统计量 ----------------
    @property
    def vpip(self):
        """翻前入池率（VPIP）：不弃牌的翻前决策占比。"""
        n = self.preflop_raise + self.preflop_call + self.preflop_fold
        if n == 0:
            return _PRIOR["vpip"]
        return (self.preflop_raise + self.preflop_call) / n

    @property
    def pfr(self):
        """翻前主动加注率。"""
        n = self.preflop_raise + self.preflop_call + self.preflop_fold
        if n == 0:
            return _PRIOR["pfr"]
        return self.preflop_raise / n

    @property
    def aggression(self):
        """整体激进度（主动下注/加注占全部动作的比例）。"""
        total = (self.preflop_raise + self.preflop_call + self.preflop_fold
                 + self.postflop_bet + self.postflop_call
                 + self.postflop_fold + self.postflop_check)
        if total == 0:
            return _PRIOR["af"]
        return (self.preflop_raise + self.postflop_bet) / total

    @property
    def looseness(self):
        """松紧程度（兼容旧接口，= VPIP）。"""
        return self.vpip

    @property
    def fold_to_bet(self):
        """面对下注的弃牌率（原始值）。"""
        if self.faces_bet == 0:
            return _PRIOR["fold_to_bet"]
        return self.postflop_fold / self.faces_bet

    @property
    def bet_freq(self):
        """翻后主动下注频率（有过牌/下注机会时）。"""
        n = self.postflop_bet + self.postflop_call + self.postflop_fold + self.postflop_check
        if n == 0:
            return _PRIOR["af"]
        return self.postflop_bet / n

    # ---------------- 小样本收缩后的稳定估计 ----------------
    def _shrunk(self, raw, n, key):
        k = _SHRINK_K
        return (raw * n + _PRIOR[key] * k) / (n + k)

    def eff_vpip(self):
        n = self.preflop_raise + self.preflop_call + self.preflop_fold
        return self._shrunk(self.vpip, n, "vpip")

    def eff_pfr(self):
        n = self.preflop_raise + self.preflop_call + self.preflop_fold
        return self._shrunk(self.pfr, n, "pfr")

    def eff_fold_to_bet(self):
        """收缩后的面对下注弃牌率——诈唬决策的关键输入。"""
        return self._shrunk(self.fold_to_bet, self.faces_bet, "fold_to_bet")

    def eff_bet_freq(self):
        n = self.postflop_bet + self.postflop_call + self.postflop_fold + self.postflop_check
        return self._shrunk(self.bet_freq, n, "af")

    def eff_big_raise(self):
        """大注占比：越高对手越爱用超额下注施压。"""
        if self.postflop_bet == 0:
            return _PRIOR["big_raise"]
        raw = self.postflop_big_raise / self.postflop_bet
        return self._shrunk(raw, self.postflop_bet, "big_raise")

    def turn_aggr(self):
        """转牌主动加注率：飙升时代表对手在转牌加宽范围，河牌应更严。"""
        if self.turn_decisions == 0:
            return _PRIOR["turn_aggr"]
        return self._shrunk(self.turn_raise / self.turn_decisions,
                            self.turn_decisions, "turn_aggr")

    def river_fold_rate(self):
        """河牌面对下注的弃牌率：低=爱跟到底（站点倾向），高=可诈唬。"""
        if self.river_faces == 0:
            return _PRIOR["river_fold"]
        return self._shrunk(self.river_fold / self.river_faces,
                            self.river_faces, "river_fold")

    def decay(self, factor=0.5):
        """指数衰减全部计数：每 _DECAY_EVERY 手调用一次，让近期数据权重
        相对升高。对手策略随比分变化时模型可快速「遗忘」旧数据。"""
        for k in ("preflop_raise", "preflop_call", "preflop_fold",
                  "postflop_bet", "postflop_call", "postflop_fold",
                  "postflop_check", "postflop_big_raise", "allin_count",
                  "faces_bet", "turn_raise", "turn_decisions",
                  "river_fold", "river_faces"):
            v = self.__dict__.get(k, 0)
            self.__dict__[k] = int(v * factor)

    def sample_size(self):
        """有效样本量（翻前决策次数）。"""
        return self.preflop_raise + self.preflop_call + self.preflop_fold

    # ---------------- 原型分类 ----------------
    def archetype(self):
        """
        对手风格原型：
          station  跟注站（松+被动）：少诈唬、多价值、薄价值
          maniac   疯子（松+极凶）：宽跟注、少诈唬、诱其投入
          rock     岩石（紧+被动）：多偷盲、其下注即弃
          tag      紧凶（紧+主动）：标准打法，避免过度剥削
          unknown  样本不足
        """
        if self.sample_size() < 6:
            return "unknown"
        vpip = self.eff_vpip()
        af = self.eff_bet_freq()
        loose = vpip > 0.60
        aggro = af > 0.42
        if loose and af > 0.52:
            return "maniac"
        if loose and not aggro:
            return "station"
        if not loose and not aggro:
            return "rock"
        if not loose and aggro:
            return "tag"
        return "station" if vpip > 0.5 else "tag"

    # ---------------- 登记与序列化 ----------------
    def update(self, kind, is_preflop, big=False, street=None):
        """登记对手一次动作。kind: raise/bet/allin/call/fold/check。
        street: 0=翻前,1=翻牌,2=转牌,3=河牌（用于街级特征统计）。"""
        if kind == "allin":
            self.allin_count += 1
            kind = "raise"
        if is_preflop:
            if kind in ("raise", "bet"):
                self.preflop_raise += 1
            elif kind == "call":
                self.preflop_call += 1
            elif kind == "fold":
                self.preflop_fold += 1
        else:
            if kind in ("raise", "bet"):
                self.postflop_bet += 1
                if big:
                    self.postflop_big_raise += 1
                if street == 2:
                    self.turn_raise += 1
            elif kind == "call":
                self.postflop_call += 1
                self.faces_bet += 1
                if street == 3:
                    self.river_faces += 1
            elif kind == "fold":
                self.postflop_fold += 1
                self.faces_bet += 1
                if street == 3:
                    self.river_fold += 1
                    self.river_faces += 1
            elif kind == "check":
                self.postflop_check += 1
            if street in (2, 3):
                self.turn_decisions += 1  # 转牌及以后的决策，用于街级激进度

    def to_json(self):
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, s):
        m = cls()
        if s:
            try:
                d = json.loads(s)
                if isinstance(d, dict):
                    # 只吸收本类定义过的字段（防脏数据）
                    for k in m.__dict__:
                        if k in d:
                            m.__dict__[k] = d[k]
            except Exception:
                pass
        return m


def build_model_from_history(model, request, my_id):
    """从 request 的 history 增量统计对手本手牌动作（带去重与大注识别）。

    - 用 (hand 编号, 已统计条数) 去重：平台每回合重放完整历史不重复计数；
    - 单轮重放各玩家的加注额（raise-to），对手加注额 >= 3 倍本轮当前
      最大注时记为「大注」；
    - 换手牌时 hands_seen += 1（若上一手牌观测到对手动作）。
    """
    opp = 1 - my_id
    hand = request.get("hand", None)
    if hand != model.last_hand:
        model.last_hand = hand
        if model.last_opp_count > 0:
            model.hands_seen += 1  # 上一手牌对手有动作，计一手样本
            # 指数衰减：每 _DECAY_EVERY 手让旧数据权重减半（近期数据主导）
            if model.hands_seen and model.hands_seen % _DECAY_EVERY == 0:
                model.decay(0.5)
        model.last_opp_count = 0

    hist = request.get("history") or []

    # 单轮重放：按顺序整理对手动作 (action_type, round, 是否大注)
    opp_actions = []
    cur_round = None
    round_max = 0
    for r in hist:
        rnd = int(r.get("round", 0))
        if rnd != cur_round:
            cur_round = rnd
            round_max = 0
        a = r.get("action", 0)
        at = r.get("action_type", "")
        is_raise = (at == "raise" or
                    (isinstance(a, int) and not isinstance(a, bool) and a > 0))
        if r.get("player_id") == opp:
            big = is_raise and round_max > 0 and a >= 3 * round_max
            opp_actions.append((at, rnd, big))
        if is_raise:
            round_max = max(round_max, a)

    # 防御：历史异常收缩时重新计数
    if model.last_opp_count > len(opp_actions):
        model.last_opp_count = 0

    # 增量登记新出现的对手动作（带 street 参数以驱动街级特征）
    for at, rnd, big in opp_actions[model.last_opp_count:]:
        model.update(at, rnd == 0, big=big, street=rnd)
    model.last_opp_count = len(opp_actions)

# -*- coding: utf-8 -*-
"""
strategy.py — AI 决策引擎（升级版）。

【升级总览】
  翻前：Chen 阈值 → 百分位范围体系
      - 庄家开池范围按对手原型动态调整（偷岩石盲 / 收紧打站点）；
      - 大盲防守由底池赔率推导 + 3-bet 范围按对手弃牌率极化/线性化；
      - 面对反加注按赔率+原型决定 4-bet/跟注/弃牌。
  翻后：新增三大模块
      1. 牌面纹理（湿润度）：决定下注尺寸与诈唬频率；
      2. 听牌 outs 计数：同花/两头顺/卡顺，支撑半诈唬与隐含赔率；
      3. EV 决策框架：跟注看底池赔率（隐含赔率修正），
         诈唬看弃牌权益是否超过盈亏平衡点，而非拍脑袋阈值。
  剥削：对手原型（station/maniac/rock/tag）驱动策略偏移——
      跟注站多薄价值少诈唬，疯子宽跟注，岩石的下注直接弃。
  风控：SPR 分层决策 + 对局状态调整（领先保收益、落后追分）。

对外仍只暴露 decide(state, model) -> action dict，
合法性安全程序 _normalize 保持不变（永远输出合法动作）。
"""

import time


# ============ 可调参数（单位见注释） ============
# ---- 翻前范围（百分位，0~1，越小越紧） ----
BTN_OPEN_PCT = 0.80        # 庄家开池基准：前 80% 的起手牌（HU 标准宽度）
OPEN_SIZE_BB = 2.5         # 开池尺寸（raise-to，单位大盲；最小加注为 2BB）
OPEN_SIZE_VS_STATION = 2.2  # 对跟注站小尺寸开池（其反正不弃）
BB_3BET_PCT = 0.13         # 大盲 3-bet 基准范围
BB_3BET_BLUFFY = 0.20      # 对手高弃牌率时的诈唬性 3-bet 范围
ISO_SIZE_BB = 3.2          # 大盲对溜入者的隔离加注尺寸
SB_4BET_VALUE_PCT = 0.035  # 面对反加注的价值 4-bet 范围（JJ+/AK）
SB_4BET_MULT = 2.3        # 4-bet 尺寸 = 对手 3-bet 额度 × 此倍数

# ---- 翻后下注尺寸（底池比例） ----
VALUE_BET = 0.65           # 常规价值下注
VALUE_BET_WET = 0.75       # 湿润牌面：大注锁听牌
THIN_VALUE = 0.55          # 薄价值 / 中强牌
OVERBET = 1.30             # 河牌坚果超池下注（榨取最大价值）
BLOCKER_BET = 0.33         # 干燥面不利位置小注保护
CBET = 0.55                # 持续下注 / 半诈唬
BLUFF = 0.55               # 纯诈唬
BLOCKER = 0.45             # 中等牌有位置的小注施压

# ---- 计算预算 ----
MC_ITERATIONS = 1200       # 蒙特卡洛最大抽样数（评估器已验证非瓶颈，余量充足）
TIME_BUDGET = 0.7          # 决策软时限（秒），确保 1 秒限时内完成


# ---------------- 对外入口 ----------------
def decide(state, model):
    """根据当前状态与对手模型返回动作 dict（经 _normalize 合法化）。"""
    if state.stage == "preflop":
        action = _preflop_decide(state, model)
    else:
        action = _postflop_decide(state, model)
    return _normalize(state, action)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------- 对局状态调整（风控·宏观层） ----------------
def _match_adjust(state):
    """
    50 手定胜负的比赛中，根据领先量与剩余手数调整风险偏好：
      protect  —— 大幅领先且临近终局：降波动（少诈唬、跟注更严）；
      pressure —— 领先且对手短码：ICM 压力下放宽全下/加注（对手弃牌率高）；
      catchup  —— 大幅落后且临近终局：加波动（多诈唬、宽跟注）；
      normal   —— 常规。
    """
    try:
        hands_left = state.max_hand - state.hand_num
        lead = (state.total_win_chips[state.my_id]
                - state.total_win_chips[state.opp_id])
        if hands_left <= 15:
            # 领先且对手是短码：我的全下带来淘汰压力，弃牌权益高于理论值
            if lead >= 30 * state.big_blind and state.opp_chips <= 0.7 * state.my_chips:
                return "pressure"
            if lead >= 30 * state.big_blind:
                return "protect"
            if lead <= -30 * state.big_blind:
                return "catchup"
    except Exception:
        pass
    return "normal"


# ================================================================
#  翻牌前：百分位范围决策
# ================================================================
def _preflop_decide(state, model):
    pct = hand_percentile(state.hole)   # 起手牌百分位（越小越强）
    arch = model.archetype()
    adj = _match_adjust(state)

    if state.is_button:
        if state.to_call <= state.blind:      # 面对大盲（含无人加注）
            return _button_open(state, model, pct, arch, adj)
        return _button_vs_3bet(state, model, pct, arch, adj)
    else:
        if state.to_call <= 0:                # 庄家溜入，我有选项
            return _bb_option(state, model, pct, arch)
        return _bb_defend(state, model, pct, arch, adj)


def _button_open(state, model, pct, arch, adj):
    """庄家位开池：范围随对手原型伸缩。"""
    open_pct = BTN_OPEN_PCT
    if arch == "rock":
        open_pct = 0.92     # 岩石不惩罚宽开池 → 更激进偷盲
    elif arch == "station":
        open_pct = 0.85     # 站点翻后乱跟 → 价值牌多打
    elif arch == "maniac":
        open_pct = 0.75     # 疯子爱反加 → 略收紧避免被掀翻
    if adj == "protect":
        open_pct = min(open_pct, 0.85)
    elif adj == "catchup":
        open_pct = min(0.97, open_pct + 0.15)  # 落后追分：大幅加宽开池

    if pct <= open_pct:
        size = OPEN_SIZE_VS_STATION if arch == "station" else OPEN_SIZE_BB
        return _raise_to(state, size * state.big_blind)

    # 垃圾牌：对手极少主动加注时补齐溜入看翻牌；落后追分时绝不弃庄家位
    limp_max = 1.0 if adj == "catchup" else 0.96
    if pct <= limp_max and (model.eff_pfr() < 0.25 or adj == "catchup"):
        return {"act": "call"}
    return {"act": "fold"}


def _is_4bet_bluff(hole):
    """诈唬 4-bet 候选：同花 A2s~A6s —— A 阻断对手 AA/AK，同花保留后手。"""
    r = sorted(c // 4 for c in hole)
    hi, lo = r[1], r[0]
    suited = (hole[0] % 4) == (hole[1] % 4)
    return hi == 14 and suited and 2 <= lo <= 6


def _button_vs_3bet(state, model, pct, arch, adj):
    """庄家面对反加注：极化 4-bet（价值+诈唬） / 跟注 / 弃牌。"""
    to_call = state.to_call
    pot = state.pot
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 价值 4-bet：JJ+/AK（前 ~3.5%）；对疯子放宽（其反加范围极宽）
    value_pct = SB_4BET_VALUE_PCT if arch != "maniac" else 0.08
    if adj == "pressure":              # ICM 压力：价值 4-bet 放宽
        value_pct = min(0.15, value_pct + 0.06)
    if pct <= value_pct:
        return _raise_to(state, SB_4BET_MULT * state.curbet[state.opp_id])

    # 诈唬 4-bet：Axs 阻挡牌，仅在对手有一定弃牌率或 ICM 压力下使用
    opp_fold = model.eff_fold_to_bet()
    if _is_4bet_bluff(state.hole) and (opp_fold >= 0.40 or adj == "pressure"):
        return _raise_to(state, SB_4BET_MULT * state.curbet[state.opp_id])

    # 跟注范围：赔率越好越宽；原型修正
    # 保证整体防守频率不低于底池赔率要求（即 call_pct >= required 的折算）
    call_pct = _clamp(1.0 - 2.0 * required, 0.10, 0.60)
    call_pct = max(call_pct, required)   # 防守底线：至少满足赔率
    if arch == "maniac":
        call_pct = min(0.75, call_pct + 0.15)   # 疯子反加不可信
    elif arch == "rock":
        call_pct = max(0.08, call_pct - 0.12)   # 岩石反加=大牌，弃
    if adj == "protect":
        call_pct -= 0.05
    elif adj == "catchup":
        call_pct += 0.05
    if pct <= call_pct:
        return {"act": "call"}
    return {"act": "fold"}


def _bb_option(state, model, pct, arch):
    """大盲面对溜入：强牌隔离加注，其余免费看牌。"""
    iso_pct = 0.40
    if arch == "station":
        iso_pct = 0.30     # 对站点隔离靠价值范围
    elif arch == "rock":
        iso_pct = 0.55     # 多惩罚岩石的溜入
    if pct <= iso_pct:
        return _raise_to(state, ISO_SIZE_BB * state.big_blind)
    return {"act": "check"}


def _bb_defend(state, model, pct, arch, adj):
    """大盲防守：底池赔率推导防守范围 + 极化 3-bet。"""
    to_call = state.to_call
    pot = state.pot
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 防守总范围：跟注需求越低防得越宽（HU vs 2.5x ≈ 55%）
    defend_pct = _clamp(1.15 - 1.8 * required, 0.22, 0.90)
    if arch == "maniac":
        defend_pct = min(0.95, defend_pct + 0.12)
    if adj == "catchup":
        defend_pct += 0.05

    # 3-bet 范围：对手面对加注弃牌率高 → 宽（诈唬）；
    #             跟注站 → 窄（纯价值，线性化）
    threebet_pct = BB_3BET_PCT
    if model.eff_fold_to_bet() >= 0.50:
        threebet_pct = BB_3BET_BLUFFY
    if arch == "station":
        threebet_pct = 0.10
    if adj == "catchup":
        threebet_pct += 0.05

    if pct <= threebet_pct:
        return _raise_to(state, 3.0 * state.curbet[state.opp_id])
    if pct <= defend_pct:
        # 很贵的跟注只防守范围上半区（反向隐含赔率保护）
        if required > 0.45 and pct > defend_pct * 0.7:
            return {"act": "fold"}
        return {"act": "call"}
    return {"act": "fold"}


# ================================================================
#  翻牌后：纹理 + 胜率 + EV + 剥削 + 风控
# ================================================================
def _board_texture(board):
    """
    牌面纹理评估：
      wet  湿润度 0~1（同花/顺子连通/对子面，听牌越多越湿）；
      high 高牌程度 0~1（A 高面=1，低面=0）。
    用途：湿面下注更大（拒绝给听牌好赔率），干面适合小注/诈唬。
    """
    n = len(board)
    if n == 0:
        return {"wet": 0.0, "high": 0.0}
    ranks = sorted((c // 4 for c in board), reverse=True)
    suits = {}
    for c in board:
        suits[c % 4] = suits.get(c % 4, 0) + 1
    max_suit = max(suits.values())

    wet = 0.0
    if max_suit >= 3:
        wet += 0.35            # 成花面（含三同花）
    elif max_suit == 2 and n >= 3:
        wet += 0.15            # 双色面
    rs = set(ranks)
    if 14 in rs:
        rs.add(1)
    cluster = 0
    for h in range(5, 15):
        window = {h, h - 1, h - 2, h - 3, h - 4}
        cluster = max(cluster, len(window & rs))
    if cluster >= 3:
        wet += 0.25            # 连通面
    if cluster >= 4:
        wet += 0.15            # 极湿（四连/已成顺）
    if len(set(ranks)) < n:
        wet += 0.10            # 对子面（葫芦可能）
    if n == 4:
        wet += 0.05
    return {"wet": min(wet, 1.0), "high": (ranks[0] - 2) / 12.0}


def _count_outs(hole, board):
    """
    统计改进型听牌张数（同花听 9、顺子听每缺一档 4 张）。
    两头顺会产生两个缺档（8 outs），卡顺一个缺档（4 outs）。
    用于半诈唬判定与隐含赔率折算。
    """
    if len(board) < 3 or len(board) >= 5:
        return 0
    outs = 0
    suits = {}
    for c in hole + board:
        suits[c % 4] = suits.get(c % 4, 0) + 1
    if any(v == 4 for v in suits.values()):
        outs += 9              # 同花听牌

    all_ranks = set(c // 4 for c in hole + board)
    if 14 in all_ranks:
        all_ranks.add(1)
    hole_ranks = set(c // 4 for c in hole)
    missing_ranks = set()
    for h in range(5, 15):
        window = {h, h - 1, h - 2, h - 3, h - 4}
        miss = window - all_ranks
        if len(miss) == 1 and (window & hole_ranks):
            missing_ranks |= miss
    outs += 4 * len(missing_ranks)
    return min(outs, 17)


def _last_preflop_raiser(state):
    """最后一位在翻前主动加注的玩家 ID（None 表示无人加注）。
    一次扫描同时得到「我是不是翻前主动方」与「对手是不是」。"""
    last = None
    for r in state.history:
        if int(r.get("round", 0)) != 0:
            continue
        a = r.get("action", 0)
        at = r.get("action_type", "")
        if at in ("raise", "allin") or (isinstance(a, int) and a > 0):
            last = r.get("player_id")
    return last


def _opp_raised_preflop(state):
    """对手翻前是否主动加注（判断其范围宽度与激进度）。"""
    return _last_preflop_raiser(state) == state.opp_id


def _bluff_buffer(state):
    """诈唬缓冲按阻挡牌效应调整（手握 A 阻断对手 Ax 强牌/坚果同花）。
    A→0.03，K→0.06，小废牌→0.12。"""
    ranks = {c // 4 for c in state.hole}
    if 14 in ranks:
        return 0.03
    if 13 in ranks:
        return 0.06
    return 0.12


def _opp_range_pct(model, opp_raised_preflop):
    """对手当前范围宽度估计（0~1），驱动蒙特卡洛对手抽样。"""
    vpip = model.eff_vpip()
    if opp_raised_preflop:
        base = 0.22 * (0.7 + vpip)      # 主动加注者：范围收紧
    else:
        base = 0.55 * (0.8 + 0.6 * vpip)  # 平跟入池：范围较宽
    return _clamp(base, 0.08, 0.95)


def _postflop_decide(state, model):
    adj = _match_adjust(state)
    arch = model.archetype()
    tex = _board_texture(state.board)
    is_river = state.current_round >= 3

    # 对手范围感知的胜率估算（对手越松范围越宽）
    last_raiser = _last_preflop_raiser(state)
    opp_raised = (last_raiser == state.opp_id)
    i_aggressor = (last_raiser == state.my_id)
    range_pct = _opp_range_pct(model, opp_raised)
    eq = monte_carlo_equity(
        state.hole, state.board, iterations=MC_ITERATIONS,
        opp_range_pct=range_pct,
        deadline=time.time() + TIME_BUDGET)

    category = evaluate_7(state.hole + state.board)[0]
    outs = _count_outs(state.hole, state.board)

    # ---- 强度分层（牌型 × 胜率 双口径）----
    strong = category >= TWO_PAIR or eq >= 0.75   # 两对及以上 / 压制性胜率
    good = (not strong) and eq >= 0.60            # 顶对好踢脚级别
    medium = (not good) and eq >= 0.50            # 中等成牌
    big_draw = (not is_river) and outs >= 8       # 同花/两头顺
    draw = (not is_river) and outs >= 4           # 卡顺级

    if state.to_call <= 0:
        return _check_side(state, model, eq, category, strong, good, medium,
                           big_draw, draw, tex, arch, adj, is_river,
                           i_aggressor)
    return _face_bet(state, model, eq, category, strong, good, medium,
                     big_draw, draw, arch, adj, is_river, i_aggressor)


def _fold_equity(model, adj):
    """有效弃牌权益（诈唬收益的核心输入），按对局状态打折/加成。"""
    fe = model.eff_fold_to_bet()
    if adj == "protect":
        fe *= 0.5      # 领先保收益：诈唬大幅压缩
    elif adj == "catchup":
        fe *= 1.3      # 落后追分：诈唬加码
    return _clamp(fe, 0.0, 0.9)


# ---------------- 无人下注（可过牌）----------------
def _check_side(state, model, eq, category, strong, good, medium, big_draw,
                draw, tex, arch, adj, is_river, i_aggressor):
    """主动下注侧：价值 / 保护 / 半诈唬 / 纯诈唬（EV 门控 + 阻挡牌）。"""
    fold_eq = _fold_equity(model, adj)
    spr = state.effective_stack / max(state.pot, 1)
    # 有利位置 + 翻前主动方 = 标准 C-Bet 场景，诈唬门槛下调
    cbet_spot = i_aggressor and state.is_button
    fold_eq = _fold_equity(model, adj)
    spr = state.effective_stack / max(state.pot, 1)

    if strong:
        # 河牌坚果优势 + 对手非岩石：超池下注榨取最大价值
        if is_river and (category >= STRAIGHT or eq >= 0.80) and arch != "rock":
            return _bet_fraction(state, OVERBET)
        # 湿面大注拒绝给听牌好赔率，干面稍小求跟注
        frac = VALUE_BET_WET if tex["wet"] >= 0.5 else VALUE_BET
        if is_river:
            frac = VALUE_BET
        return _bet_fraction(state, frac)

    if good:
        # SPR 很低：直接大注把后街筹码在有利时打光
        if spr <= 2.5:
            return _bet_fraction(state, 0.80)
        frac = VALUE_BET if tex["wet"] >= 0.5 else THIN_VALUE
        # 河牌对跟注站做薄价值（其会用差牌跟注）
        if is_river and arch == "station":
            frac = 0.60
        return _bet_fraction(state, frac)

    if big_draw:
        # 半诈唬优先级高于控池：强听牌即使当前胜率中等，
        # 也要么积累底池要么直接赢下（弃牌权益 + 成牌双重收益）
        if fold_eq >= 0.30 or state.is_button:
            return _bet_fraction(state, CBET)
        return {"act": "check"}

    if medium:
        # 有利位置 C-Bet 频率目标 ≥70%：湿面或主动方都下注施压/保护
        if state.is_button and (tex["wet"] >= 0.4 or cbet_spot):
            return _bet_fraction(state, BLOCKER)
        # 不利位置 + 极干面 + 中强牌：1/3 池小注保护（低成本纠缠+节省筹码）
        if not state.is_button and tex["wet"] < 0.2 and eq >= 0.55:
            return _bet_fraction(state, BLOCKER_BET)
        return {"act": "check"}

    if draw:
        return {"act": "check"}     # 弱听牌免费看牌

    # 空气：纯诈唬，EV 门控 + 阻挡牌效应
    breakeven = BLUFF / (1.0 + BLUFF)        # ≈ 0.355
    buffer = _bluff_buffer(state)            # A=0.03 / K=0.06 / 小废牌=0.12
    if cbet_spot:
        buffer = max(0.0, buffer - 0.05)     # 有利位置 C-Bet 诈唬门槛下调
    if adj == "protect":
        buffer += 0.15                       # 领先保收益：少诈唬
    elif adj == "catchup":
        buffer = max(0.0, buffer - 0.06)     # 落后追分：放宽诈唬
    if fold_eq >= breakeven + buffer:
        # 无位置时只诈唬非激进对手（避免被 check-raise 掀翻）
        if state.is_button or model.eff_bet_freq() < 0.45:
            # 河牌诈唬额外要求：对手在河牌有弃牌倾向（避免诈唬被站点抓死）
            if (not is_river) or (fold_eq >= 0.45 and
                                  model.river_fold_rate() >= 0.35):
                return _bet_fraction(state, BLUFF)
    return {"act": "check"}


# ---------------- 面对下注 ----------------
def _face_bet(state, model, eq, category, strong, good, medium, big_draw, draw,
              arch, adj, is_river, i_aggressor):
    """面对下注：底池赔率（隐含修正）+ 原型/街级修正 + 加注/跟注/弃牌。"""
    pot = state.pot
    to_call = state.to_call
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 隐含赔率：强听牌 + 深筹码时，有效跟注需求降低
    implied = 1.0
    if big_draw and state.effective_stack > 4 * pot and not is_river:
        implied = 1.4
    eff_req = required / implied

    # 跟注安全边际：默认 2%；岩石的下注≈价值 → 抬门槛；疯子乱打 → 放宽
    margin = 0.02
    if arch == "rock":
        eff_req += 0.10
    elif arch == "maniac":
        eff_req -= 0.08
    # 街级修正：对手转牌加注率飙升 → 河牌下注更可能是真强牌，跟注更严
    if is_river and model.turn_aggr() >= 0.45:
        eff_req += 0.05
    if adj == "protect":
        margin += 0.06       # 领先时只打好赔率
    elif adj == "catchup":
        margin -= 0.03       # 落后时多看几张牌

    # ---- 对手全下 / 需跟注额 ≥ 剩余筹码：纯赔率决策 ----
    if state.opp_is_allin or to_call >= state.my_left:
        # ICM 压力：领先且对手短码，放宽跟注（对手全下范围更紧）
        thr = eff_req - 0.05 if adj == "pressure" else eff_req + 0.02
        if strong or eq >= thr or (big_draw and eq >= eff_req):
            return {"act": "allin"}
        return {"act": "fold"}

    # ---- 强牌：加注求价值；浅筹码或 ICM 压力直接全下 ----
    if strong:
        spr = state.effective_stack / max(pot, 1)
        if spr <= 2.0 or adj == "pressure":
            return {"act": "allin"}
        # 河牌坚果 + 有位置：超池加注榨取
        if is_river and (category >= STRAIGHT or eq >= 0.80) and \
                state.is_button and arch != "rock":
            return _bet_fraction(state, OVERBET)
        return _raise_pot(state)

    # ---- 良好成牌：价值加注或赔率跟注 ----
    if good:
        if state.is_button and eq >= 0.68 and arch != "rock":
            return _raise_pot(state)          # 位置+明显领先 → 加注
        if eq >= eff_req + margin:
            return {"act": "call"}
        if eq >= eff_req and arch == "maniac":
            return {"act": "call"}            # 疯子的下注不可全信
        return {"act": "fold"}

    # ---- 强听牌：半诈唬加注或按（隐含）赔率抽牌（优先于中等成牌：
    #      强听牌有隐含赔率加成，按成牌口径评估会低估其价值）----
    if big_draw:
        if model.eff_fold_to_bet() >= 0.45 and required <= 0.40:
            return _raise_pot(state)          # 半诈唬加注（弃牌权益+成牌双收益）
        if eq >= eff_req:
            return {"act": "call"}
        if eq >= required * 0.75:
            return {"act": "call"}            # 隐含赔率勉强支撑
        return {"act": "fold"}

    # ---- 中等成牌：只打好赔率 ----
    if medium:
        if eq >= eff_req + margin + 0.03:
            return {"act": "call"}
        if eq >= eff_req and arch == "maniac":
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 弱听牌：只在很便宜时跟 ----
    if draw:
        if required <= 0.20 and eq >= required * 0.9:
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 空气：罕见反诈唬（对手高弃牌 + 我有位置 + 便宜）----
    if model.eff_fold_to_bet() >= 0.60 and required <= 0.30 and state.is_button:
        return _raise_pot(state)
    return {"act": "fold"}


# ---------------- 动作构造辅助（raise-to 语义） ----------------
def _raise_to(state, target_total):
    """加注到本轮总注额 target_total；越界转全下。"""
    target_total = int(round(target_total))
    if target_total < state.min_raise():
        target_total = state.min_raise()
    if target_total >= state.max_raise() or target_total >= state.my_left:
        return {"act": "allin"}
    return {"act": "raise", "num": target_total}


def _bet_fraction(state, fraction):
    """当可以过牌时，下注底池的 fraction 倍。"""
    target = state.curbet[state.my_id] + int(fraction * state.pot)
    return _raise_to(state, target)


def _raise_pot(state):
    """面对下注时，做约一个底池大小的加注。"""
    to_call = state.to_call
    target = state.curbet[state.my_id] + to_call + (state.pot + to_call)
    return _raise_to(state, target)


# ---------------- 合法性安全程序（不变，最后防线） ----------------
def _normalize(state, action):
    """
    防止非法操作触发的最终安全程序。
    - 规则5：本局有人全押 → 只能弃牌/全押；
    - check 仅当无需跟注；call 需筹码严格大于跟注额；
    - raise 夹紧到 [最小加注, 筹码上界)，越界转全下；
    - 未知动作一律退化为最安全合法动作。
    """
    act = action.get("act", "fold")
    to_call = state.to_call
    my_left = state.my_left

    # 规则5：本局有人全押 → 只允许弃牌(-1)/全押(-2)
    if state.any_allin:
        if act == "fold":
            return {"act": "fold"}
        return {"act": "allin"} if my_left > 0 else {"act": "fold"}

    if act == "fold":
        return {"act": "fold"}

    if act == "check":
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "allin":
        if my_left > 0:
            return {"act": "allin"}
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "call":
        if to_call <= 0:
            return {"act": "check"}
        if to_call >= my_left:      # 需严格 my_left > to_call 才能跟注
            return {"act": "allin"}
        return {"act": "call"}

    if act == "raise":
        try:
            num = int(round(float(action.get("num", 0))))
        except (TypeError, ValueError):
            num = 0
        min_r = state.min_raise()
        max_r = state.max_raise()
        if num < min_r:
            num = min_r
        if num >= max_r or num >= my_left:
            return {"act": "allin"}
        return {"act": "raise", "num": num}

    return {"act": "fold"}

# -*- coding: utf-8 -*-
"""
bot.py — BotZone 平台交互层（只支持 JSON 交互，每步限时 1 秒）。

BotZone JSON 交互协议：
  输入（stdin，一个 JSON 对象）：
    {"requests": [...], "responses": [...], "data": "...", "globaldata": "..."}
    requests 数组的最后一个元素是本轮的 request（可能是 JSON 字符串或对象）。
  输出（stdout，一个 JSON 对象）：
    {"response": <整数>, "data": "...", "globaldata": "..."}

response 整数语义：
  -1 弃牌(fold)  -2 全押(allin)  0 跟注/过牌(call/check)
  >0 加注（raise-to：加注后本轮我的总下注额）

安全设计：
  - 任何解析/决策异常都有兜底，保证永远输出一个合法 response；
  - _final_guard 在整数层面做最后一道合法性校验。
"""

import json
import sys


_ACT_TO_RESPONSE = {"fold": -1, "allin": -2, "call": 0, "check": 0}


def _to_response(action):
    """把内部动作 dict 转为 response 整数。"""
    act = action.get("act", "fold")
    if act == "raise":
        try:
            num = int(action.get("num", 0))
        except (TypeError, ValueError):
            return -1
        return num if num > 0 else -1
    return _ACT_TO_RESPONSE.get(act, -1)


def _final_guard(state, resp):
    """整数 response 层面的最后一道安全网，绝对保证合法。"""
    try:
        to_call = state.to_call
        my_left = state.my_left

        if resp == -1:
            return -1  # 弃牌永远合法
        if resp == -2:
            if my_left > 0:
                return -2  # 全押合法
            return -1 if to_call > 0 else 0

        # 规则5：本局有人全押 → 只能弃牌(-1)/全押(-2)
        if state.any_allin:
            return -2 if my_left > 0 else -1

        if resp == 0:
            if to_call <= 0:
                return 0          # 过牌，合法
            if my_left > to_call:
                return 0          # 跟注（需严格大于才合法）
            return -2             # 筹码不足完整跟注 → 全押

        # resp > 0：加注（raise-to 语义）
        num = int(resp)
        if num <= 0:
            return -1
        min_r = state.min_raise()
        max_r = state.max_raise()
        if num < min_r:
            num = min_r
        if num >= max_r or num >= my_left:
            return -2             # 加注空间不足 → 全押
        return num
    except Exception:
        return -1


def _fallback_resp(state):
    """决策层异常时的保守动作：能过牌就过牌，能跟就跟，否则弃牌。"""
    try:
        if state.any_allin:
            return -1
        if state.to_call <= 0:
            return 0
        if state.my_left > state.to_call:
            return 0
        return -1
    except Exception:
        return -1


def _extract_request(obj):
    """从 BotZone JSON 交互输入中取出本轮 request dict（可能为 None）。"""
    reqs = obj.get("requests") or []
    for item in reversed(reqs):
        cand = item
        if isinstance(cand, str):
            try:
                cand = json.loads(cand)
            except Exception:
                continue
        if isinstance(cand, dict) and ("my_cards" in cand or "history" in cand):
            return cand
    return None


def _persisted_str(v):
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    try:
        return json.dumps(v)
    except Exception:
        return ""


def run():
    raw = sys.stdin.read().strip()
    if not raw:
        return
    try:
        obj = json.loads(raw)
    except Exception:
        return

    json_mode = False
    data_str = gdata_str = ""
    request = None

    if isinstance(obj, dict) and "requests" in obj:
        # BotZone JSON 交互：包装结构
        json_mode = True
        data_str = _persisted_str(obj.get("data"))
        gdata_str = _persisted_str(obj.get("globaldata"))
        request = _extract_request(obj)
    elif isinstance(obj, dict) and ("my_cards" in obj or "history" in obj):
        # 本地调试：裸 request
        request = obj

    resp = 0
    data_out = ""
    try:
        if request is None:
            resp = 0  # 拿不到状态时的最保守输出（非法时裁判仅按弃牌处理）
        else:
            state = parse_request(request)
            try:
                # 对手建模：优先跨手牌的 globaldata，其次 data
                model = OpponentModel.from_json(gdata_str or data_str)
                build_model_from_history(model, request, state.my_id)
                action = decide(state, model)
                resp = _to_response(action)
                resp = _final_guard(state, resp)
                data_out = model.to_json()
            except Exception:
                resp = _fallback_resp(state)
    except Exception:
        resp = 0

    if json_mode:
        out = {"response": resp, "data": data_out, "globaldata": data_out}
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        sys.stdout.write(str(resp) + "\n")
    sys.stdout.flush()



if __name__ == '__main__':
    run()
