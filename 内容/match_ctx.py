# -*- coding: utf-8 -*-
"""
match_ctx.py — 赛制上下文（对手弃牌推断 / 激进等级 / 回撤保护）。

【整合原则】三个模块只做一件事：给现有状态机 protect/pressure/
desperate/doomed 的**触发阈值提供偏移**，不新增独立决策路径。

  模块一 对手弃牌率推断器：
    本平台只在轮到我行动时发 request —— 对手直接弃牌的手牌我们
    根本看不到，VPIP/C-Bet 无法直接观测。因此用 globaldata 持久化
    「我方累计净赢 total_win_chips」，每手牌用净赢增量推断：
      +50 = 对手 SB 弃牌（我是 BB 收盲）
      +100 = 对手 BB 弃牌（我是 SB 收盲）
    最近 WINDOW 局「直接收盲率」> LOCK_RATE → 标记 opponent_locking
    （疑似锁胜）。注意：只是行为信号，不假设对手真的会锁。

  模块二 激进等级切换器：
    基于 total_win_chips（平台每手牌筹码重置，my_chips 不是累计值，
    必须用累计净赢）。三档：保守(>+20%) / 正常(±20%) / 激进(<-20%)。
    激进档让状态机阈值偏向「追分」（负偏移），保守档偏向「保收益」。

  模块三 回撤保护：
    单局亏损 > DRAWDOWN_PCT → 降档一级；保守连续 UP_CONSEC_CONSERVATIVE
    局盈利 / 正常连续 UP_CONSEC_NORMAL 局盈利且累计盈亏 > 门槛 → 升档。
    作为阈值偏移使用，不硬切决策路径。

所有阈值均为可配置常量。
"""

from game_state import INIT_CHIPS

# ---------------- 可配置常量 ----------------
WINDOW = 20                     # 滑动窗口：最近 20 局（规则1：对手最近20局行为）
BLIND_NETS = (50, 100)          # 直接收盲的单局净赢（对手弃 SB/BB）→ 对手弃牌
LOCK_RATE = 0.65                # 弃牌率阈值：最近20局直接收盲率 > 65%（规则1）
LOCK_ALLIN_FREQ = 0.10          # 全下频率上限：最近20局对手全下 < 10%（规则1）
LOCK_MIN_SAMPLES = 8            # 判定疑似锁胜所需的最少样本局数

LEVEL_CONSERVATIVE = 0          # 保守：正常策略，不额外激进
LEVEL_NORMAL = 1                # 正常
LEVEL_AGGRESSIVE = 2            # 激进：追分

BRACKET_PCT = 0.20              # 激进等级分档：累计盈亏 ±20% 初始筹码
DRAWDOWN_PCT = 0.15             # 单局亏损阈值 → 大败降档
UP_CONSEC_CONSERVATIVE = 3      # 保守档连续盈利升档局数
UP_CONSEC_NORMAL = 5            # 正常档连续盈利升档局数
UP_NORMAL_MIN_PNL = -0.10       # 正常档升档的累计盈亏下限（-10%）
LEVEL_SHIFT_BB = 6              # 激进等级对状态机阈值的偏移（大盲单位）


class MatchContext:
    """赛制上下文。to_dict/from_dict 存于对手模型的 ctx_dict，随 globaldata 持久化。"""

    def __init__(self):
        self.total_hands = 0         # 已结算手数
        self.last_hand = None        # 上一请求的 hand 编号（用于手牌边界检测）
        self.last_win = None         # 上一请求的我方累计净赢
        self.recent_hands = []       # FIFO：[单局净赢, 对手本手是否全下]（最近 WINDOW 局）
        self.cur_opp_allin = False   # 当前手牌对手是否全下过（跨 request 累积）
        self.direct_blind_rate = 0.0  # 最近窗口直接收盲率（= 对手弃牌率下界）
        self.opp_allin_freq = 0.0     # 最近窗口对手全下频率
        self.opponent_locking = False  # 疑似锁胜（弃牌率>65% 且 全下频率<10%）
        self.level = LEVEL_NORMAL    # 激进等级
        self.consec_profit = 0       # 连续盈利局数（用于升档）

    # ---------------- 序列化 ----------------
    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, d):
        c = cls()
        if isinstance(d, dict):
            for k in c.__dict__:
                if k in d:
                    c.__dict__[k] = d[k]
            # 旧版本兼容：recent_win（仅净赢）→ recent_hands（补 allin 标志）
            rw = d.get("recent_win")
            if rw and not c.recent_hands:
                c.recent_hands = [[w, False] for w in rw]
        return c

    # ---------------- 每回合更新（每次 request 调用一次）----------------
    def update(self, state):
        """在每次 request 时调用：检测到新手牌即结算上一手。"""
        hand = state.hand_num
        my_win = state.total_win_chips[state.my_id]
        # 检测当前手牌对手是否全下（history 可直接观测：对手 allin 后必轮到我们）
        hist = (getattr(state, "request", None) or {}).get("history") or []
        if any(r.get("player_id") == state.opp_id
               and r.get("action_type") == "allin" for r in hist):
            self.cur_opp_allin = True
        if hand != self.last_hand:
            if self.last_hand is not None and self.last_win is not None:
                # 结算上一手：此时 cur_opp_allin 仍记录着上一手的全下状态
                self._record_hand(state, my_win - self.last_win, self.cur_opp_allin)
            self.last_hand = hand
            self.last_win = my_win
            self.cur_opp_allin = False

    def _record_hand(self, state, net, opp_allin):
        """上一手已结束：记录单局净赢与对手全下标志，并更新指标。"""
        self.total_hands += 1
        q = self.recent_hands
        q.append([net, opp_allin])
        if len(q) > WINDOW:
            del q[0]

        # 模块一：直接收盲率（对手弃牌率下界）> 65% 且 对手全下频率 < 10%
        # → 疑似锁胜（规则1：对手明显收紧时主动偷盲追分）
        wins = [h[0] for h in q]
        blind = sum(1 for w in wins if w in BLIND_NETS)
        allin_cnt = sum(1 for h in q if h[1])
        self.direct_blind_rate = blind / len(wins) if wins else 0.0
        self.opp_allin_freq = allin_cnt / len(q) if q else 0.0
        self.opponent_locking = (
            len(wins) >= LOCK_MIN_SAMPLES
            and self.direct_blind_rate > LOCK_RATE
            and self.opp_allin_freq < LOCK_ALLIN_FREQ)

        # 模块三：回撤降档 + 连续盈利计数
        if net <= -DRAWDOWN_PCT * INIT_CHIPS:
            self.level = max(LEVEL_CONSERVATIVE, self.level - 1)
            self.consec_profit = 0
        elif net > 0:
            self.consec_profit += 1
        else:
            self.consec_profit = 0
        self._level_up(state)

    def _level_up(self, state):
        """模块三：连续盈利升档。"""
        pnl = state.total_win_chips[state.my_id]
        if self.level == LEVEL_CONSERVATIVE and \
                self.consec_profit >= UP_CONSEC_CONSERVATIVE:
            self.level = LEVEL_NORMAL
            self.consec_profit = 0
        elif self.level == LEVEL_NORMAL and \
                self.consec_profit >= UP_CONSEC_NORMAL and \
                pnl > UP_NORMAL_MIN_PNL * INIT_CHIPS:
            self.level = LEVEL_AGGRESSIVE
            self.consec_profit = 0

    def sync_baseline(self, state):
        """
        模块二主规则：每回合开始前让激进档向「累计盈亏分档」收敛。
        - 大盈利(>+20%)：强制不高于保守档（保护收益）；
        - 大亏损(<-20%)：强制不低于激进档（必须追分，回撤降档在大
          亏损带内被覆盖——这是有意取舍：深坑里没有冷却的资本）。
        """
        pnl = state.total_win_chips[state.my_id]
        if pnl > BRACKET_PCT * INIT_CHIPS:
            self.level = min(self.level, LEVEL_CONSERVATIVE)
        elif pnl < -BRACKET_PCT * INIT_CHIPS:
            self.level = max(self.level, LEVEL_AGGRESSIVE)

    # ---------------- 供策略层使用 ----------------
    def threshold_offset(self, state):
        """
        状态机阈值偏移（大盲单位）：
          激进 → 负偏移（把领先视为更差 → 更早进入 desperate/doomed 追分）；
          保守 → 正偏移（把领先视为更好 → 更早 protect 保收益）。
        """
        if self.level == LEVEL_AGGRESSIVE:
            return -LEVEL_SHIFT_BB
        if self.level == LEVEL_CONSERVATIVE:
            return LEVEL_SHIFT_BB
        return 0
