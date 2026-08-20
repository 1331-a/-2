# -*- coding: utf-8 -*-
"""
simulate.py — 本地单挑对局模拟器（用于调试与验证）。

实现一个精简但规则正确的双人（heads-up）无限注德州扑克引擎，
可让策略机器人（strategy.decide）与简单对手（跟注站 / 随机）对打，
验证机器人动作合法、牌型评估正确，并统计胜率与盈利。

运行：
    python simulate.py 500             # 打 500 手，对抗跟注站
    python simulate.py 500 random      # 对抗随机对手
"""

import random
import sys

import cards
import evaluator
import game_state
import opponent
import ranges
import strategy


# ---------------- 机器人包装 ----------------
class StrategyBot:
    """我方策略机器人。"""

    def __init__(self):
        self.model = opponent.OpponentModel()

    def act(self, state):
        return strategy.decide(state, self.model)


class CallingStation:
    """跟注站：几乎永远 check/call，只在顶级牌时加注。"""

    def __init__(self):
        self.model = opponent.OpponentModel()

    def act(self, state):
        chen = ranges.chen_score(state.hole)
        if state.to_call == 0:
            if chen >= 12:
                return {"act": "raise", "num": state.curbet[state.my_id] + 3 * state.big_blind}
            return {"act": "check"}
        if state.to_call >= state.my_left:
            return {"act": "call"}
        if chen >= 12:
            return {"act": "raise", "num": state.min_raise_to() * 2}
        return {"act": "call"}


class RandomBot:
    """随机对手：在所有合法动作中随机选择。"""

    def __init__(self):
        self.model = opponent.OpponentModel()

    def act(self, state):
        return random.choice(_legal_actions(state))


def _legal_actions(state):
    actions = []
    if state.to_call == 0:
        actions.append({"act": "check"})
        actions.append({"act": "raise", "num": state.min_raise_to()})
    else:
        actions.append({"act": "fold"})
        actions.append({"act": "call"})
        if state.to_call < state.my_left:
            actions.append({"act": "raise", "num": state.min_raise_to()})
    return actions


# ---------------- 引擎 ----------------
class HeadsUpEngine:
    """双人无限注德州扑克引擎。bot0 为按钮/小盲，bot1 为大盲。"""

    def __init__(self, small_blind=10, stack=1000):
        self.sb = small_blind
        self.bb = small_blind * 2
        self.stack = stack

    def play_hand(self, bots):
        """打一手牌，bots = [按钮bot, 大盲bot]。返回 [bot0利润, bot1利润]。"""
        sb, bb = self.sb, self.bb
        deck = cards.full_deck()
        random.shuffle(deck)

        hole = [deck[0:2], deck[2:4]]
        board = []
        chips = [self.stack - sb, self.stack - bb]  # 剩余筹码
        committed = [sb, bb]                        # 累计已投入（决定底池）
        folded = [False, False]

        self._street(0, chips, committed, folded, hole, board, bots)
        if not self._live(folded):
            return self._settle(folded, chips, committed)

        for n in (3, 4, 5):  # 翻牌/转牌/河牌
            board = deck[4:4 + n]
            self._street(1, chips, committed, folded, hole, board, bots)
            if not self._live(folded):
                return self._settle(folded, chips, committed)

        return self._showdown(hole, board, chips, committed, folded)

    def _live(self, folded):
        return sum(1 for f in folded if not f) > 1

    def _street(self, first, chips, committed, folded, hole, board, bots):
        """跑完一条街的下注轮。first 为先行玩家（翻前=按钮0，翻后=大盲1）。"""
        round_bet = [0, 0]  # 本轮已投入
        to_act = first
        last_aggressor = None
        has_acted = [False, False]

        while True:
            if not self._live(folded):
                return
            if chips[0] == 0 and chips[1] == 0:
                return

            p = to_act
            if chips[p] == 0:  # 已全下，跳过
                to_act = 1 - to_act
                continue

            # 收盘判断：双方本轮注额相同，且无人再有行动义务
            if round_bet[0] == round_bet[1]:
                if last_aggressor is None:
                    if has_acted[0] and has_acted[1]:
                        return
                elif chips[last_aggressor] == 0 or p == last_aggressor:
                    return

            state = game_state.GameState(
                blind=self.sb, my_id=p,
                pot=committed[0] + committed[1],
                hand=hole[p], publiccard=board,
                curbet=list(round_bet), leftbet=list(chips))
            action = bots[p].act(state)
            kind = self._apply(p, action, chips, committed, round_bet, folded)

            # 用真实动作更新对手画像
            bots[1 - p].model.update(kind, state.stage == "preflop")

            has_acted[p] = True
            if kind in ("bet", "raise"):
                last_aggressor = p
            to_act = 1 - p

    def _apply(self, p, action, chips, committed, round_bet, folded):
        act = action.get("act", "call")
        to_call = max(round_bet) - round_bet[p]

        if act == "fold":
            folded[p] = True
            return "fold"
        if act == "check":
            return "check"
        if act == "call":
            if to_call <= 0:
                return "check"
            pay = min(to_call, chips[p])
            self._pay(p, pay, chips, committed, round_bet)
            return "call"
        if act == "raise":
            target = int(action.get("num", round_bet[p]))
            target = max(target, round_bet[p] + 1)
            pay = min(target - round_bet[p], chips[p])
            self._pay(p, pay, chips, committed, round_bet)
            return "bet" if to_call == 0 else "raise"
        if act == "allin":
            self._pay(p, chips[p], chips, committed, round_bet)
            return "bet" if to_call == 0 else "raise"
        return "check"

    def _pay(self, p, amount, chips, committed, round_bet):
        chips[p] -= amount
        committed[p] += amount
        round_bet[p] += amount

    def _settle(self, folded, chips, committed):
        pot = committed[0] + committed[1]
        winner = 0 if not folded[0] else 1
        chips[winner] += pot
        return [chips[0] - self.stack, chips[1] - self.stack]

    def _showdown(self, hole, board, chips, committed, folded):
        pot = committed[0] + committed[1]
        s0 = evaluator.evaluate_7(hole[0] + board)
        s1 = evaluator.evaluate_7(hole[1] + board)
        if s0 > s1:
            chips[0] += pot
        elif s1 > s0:
            chips[1] += pot
        else:
            chips[0] += pot // 2
            chips[1] += pot - pot // 2
        return [chips[0] - self.stack, chips[1] - self.stack]


# ---------------- 主流程 ----------------
def match(hands, opponent_factory, small_blind=10, stack=1000):
    """打 hands 手，我方策略机器人对抗指定对手，交替庄家位。"""
    engine = HeadsUpEngine(small_blind, stack)
    my_bot = StrategyBot()
    opp = opponent_factory()

    my_profit = 0
    my_wins = 0
    for i in range(hands):
        if i % 2 == 0:  # 我当庄家/小盲
            bots = [my_bot, opp]
            profit = engine.play_hand(bots)
            my_profit += profit[0]
            if profit[0] > 0:
                my_wins += 1
        else:           # 对手当庄家
            bots = [opp, my_bot]
            profit = engine.play_hand(bots)
            my_profit += profit[1]
            if profit[1] > 0:
                my_wins += 1

    return my_profit, my_wins / hands


if __name__ == "__main__":
    hands = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    opp_name = sys.argv[2] if len(sys.argv) > 2 else "calling"

    factory = {"calling": CallingStation, "random": RandomBot}[opp_name]

    profit, winrate = match(hands, factory)
    print(f"对局数      : {hands}")
    print(f"对手        : {opp_name}")
    print(f"总盈利      : {profit:+.0f} 筹码")
    print(f"每手平均    : {profit / hands:+.2f} 筹码")
    print(f"赢率        : {winrate * 100:.1f}%")
