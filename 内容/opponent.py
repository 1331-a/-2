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
        # ---- 赛制上下文（match_ctx.MatchContext.to_dict 的容器，
        #      随本模型一起经 globaldata 持久化） ----
        self.ctx_dict = {}

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
