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
DEFAULT_BIG_BLIND = 100   # 盲注默认值（平台 HU 固定 50/100；翻前由 my_total_in
                          # 动态推导覆盖，翻后无法从 request 得知官方盲注 → 用此默认值，
                          # 2026-08-25 由 200 修正为 100：翻后 doom/阈值曾按 2 倍漂移）


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
