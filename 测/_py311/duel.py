# -*- coding: utf-8 -*-
"""v50 vs 当前版：真实对弈（70 手/场，双方各用自己的 parse_request/decide）。

用法：
    python duel.py <场数> [seed]
"""
import io
import marshal
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"
sys.path.insert(0, BASE + "/内容")

V = {"__name__": "v50mod", "__file__": "poker_bot.py"}
exec(marshal.loads(open(BASE + "/测/_v50_body.bin", "rb").read()), V)

import bot as NOW_B          # noqa: E402
import strategy as NOW_S     # noqa: E402

SB, BB, INIT, MAX_HAND = 50, 100, 20000, 70
STREET_N = (0, 3, 1, 1)


BODY = open(BASE + "/测/_v50_body.bin", "rb").read()


def load_v50(tag):
    """v50：每个实例独立 exec 一份命名空间（全局变量天然隔离）。"""
    ns = {"__name__": "v50_" + tag, "__file__": "poker_bot.py"}
    exec(marshal.loads(BODY), ns)
    return ns


def load_now(tag):
    """当前版：每个实例独立加载一份 strategy 模块副本。

    【关键】真实对局里双方是**独立进程**，模块级全局（_CTX/_LAST_EQ/
    _LAST_ADJ/_DECISION_STARTED_AT 等）天然隔离；若在同一进程共享同一份
    strategy 模块，两个 bot 会互相污染 → 自对弈都不均衡（实测 now vs now
    6 场差 43,304，而 v50 因为全局依赖少只差 4,180）。
    """
    import importlib.util
    import types
    path = BASE + "/内容/strategy.py"
    key = "strategy_" + tag
    spec = importlib.util.spec_from_file_location(key, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[key] = m
    spec.loader.exec_module(m)
    m.__dict__.setdefault("_ISOLATED_COPY", True)
    return m


class BotV50:
    name = "v50"

    def __init__(self, tag="a"):
        self.V = load_v50(tag)
        self.parse = self.V["parse_request"]
        self.decide = self.V["decide"]
        self.to_resp = self.V["_to_response"]
        self.model = self.V["OpponentModel"]()

    def act(self, req):
        st = self.parse(req)
        a = self.decide(st, self.model, None)
        return int(self.to_resp(a)), st

    def reset(self):
        self.model = self.V["OpponentModel"]()


class BotNow:
    name = "now"

    def __init__(self, tag="a"):
        import game_state as G
        import opponent as O
        import match_ctx as M
        self.S = load_now(tag)
        self.G, self.O, self.M = G, O, M
        self.model = O.OpponentModel()
        self.ctx = M.MatchContext.from_dict(self.model.ctx_dict)

    def act(self, req):
        st = self.G.parse_request(req)
        a = self.S.decide(st, self.model, self.ctx, debug=False)
        return int(NOW_B._final_guard(st, NOW_B._to_response(a))), st

    def reset(self):
        self.model = self.O.OpponentModel()
        self.ctx = self.M.MatchContext.from_dict(self.model.ctx_dict)


def evaluate5(cards):
    return V["evaluate_7"](list(cards))


def play_hand(bots, chips_in, twc, hand, dealer, rng, log=None):
    """返回 (各座位净变化, holes, board)。"""
    start = list(chips_in)                       # 本手开始时的筹码（算投入用）
    chips = list(chips_in)
    deck = list(range(52))
    rng.shuffle(deck)
    holes = [sorted(deck[:2]), sorted(deck[2:4])]
    rest = deck[4:]
    board = []
    street_bet = [0, 0]
    street_bet[dealer] = SB
    street_bet[1 - dealer] = BB
    chips[dealer] -= SB
    chips[1 - dealer] -= BB
    pot = SB + BB
    hist = []
    last_full_raise = BB

    for street in range(4):
        if street > 0:
            board.extend(rest[:STREET_N[street]])
            rest = rest[STREET_N[street]:]
            street_bet = [0, 0]
            last_full_raise = BB
        acted = set()
        # 翻后由非 dealer 先行动；翻前由 dealer 先行动
        seat = dealer if street == 0 else 1 - dealer
        for _ in range(24):                      # 每街动作上限（防死循环）
            if len(acted) >= 2 and street_bet[0] == street_bet[1]:
                break
            to_call = max(0, street_bet[1 - seat] - street_bet[seat])
            req = {"num_players": 2, "dealer_id": dealer, "my_id": seat,
                   "my_chips": chips[seat], "my_cards": list(holes[seat]),
                   "public_cards": list(board), "history": list(hist),
                   "hand": hand, "max_hand": MAX_HAND,
                   "total_win_chips": [twc[seat], twc[1 - seat]],
                   "total_win_games": [0, 0]}
            try:
                resp, _st = bots[seat].act(req)
            except Exception as e:
                if log is not None:
                    log.append("EXC seat%d %r" % (seat, e))
                resp = -1
            # ---- 应用动作 ----
            if resp == -1:
                hist.append({"round": street, "player_id": seat,
                             "action": -1, "action_type": "fold"})
                return _settle_fold(seat, chips, pot, start)
            elif resp == -2:
                # 全下：按**有效筹码**封顶（对手本街最多还能投多少）
                opp_cap = street_bet[1 - seat] + chips[1 - seat]
                max_add = max(0, opp_cap - street_bet[seat])
                add = min(chips[seat], max_add)
                chips[seat] -= add
                street_bet[seat] += add
                pot += add
                hist.append({"round": street, "player_id": seat,
                             "action": -2, "action_type": "allin"})
                acted.add(seat)
            elif resp == 0:
                add = min(chips[seat], to_call)
                chips[seat] -= add
                street_bet[seat] += add
                pot += add
                hist.append({"round": street, "player_id": seat,
                             "action": 0,
                             "action_type": "call" if to_call > 0 else "check"})
                acted.add(seat)
            else:
                target = int(resp)
                add = min(chips[seat], max(0, target - street_bet[seat]))
                chips[seat] -= add
                street_bet[seat] += add
                pot += add
                hist.append({"round": street, "player_id": seat,
                             "action": street_bet[seat], "action_type": "raise"})
                acted = {seat}                   # 加注后对方需再行动
            seat = 1 - seat
        if chips[0] == 0 or chips[1] == 0:
            # 有人全下且已匹配 → 直接发完剩余公共牌摊牌
            for s in range(street + 1, 4):
                board.extend(rest[:STREET_N[s]])
                rest = rest[STREET_N[s]:]
            break
    else:
        pass
    # ---- 摊牌 ----
    inv = [start[0] - chips[0], start[1] - chips[1]]
    s0 = evaluate5(holes[0] + board)
    s1 = evaluate5(holes[1] + board)
    if s0 > s1:
        return [pot - inv[0], -inv[1]], holes, board
    if s1 > s0:
        return [-inv[0], pot - inv[1]], holes, board
    # 平局：各自退回本手投入（近似处理，底池死钱忽略）
    return [0, 0], holes, board


def _settle_fold(folder, chips, pot, start):
    """弃牌：对手拿走底池。净变化按本手开始筹码计算。"""
    win = 1 - folder
    inv = [start[0] - chips[0], start[1] - chips[1]]
    d = [0, 0]
    d[win] = pot - inv[win]
    d[folder] = -inv[folder]
    return d, None, None


def play_match(b0, b1, rng, hand_log=None):
    bots = [b0, b1]
    for b in bots:
        b.reset()
    chips = [INIT, INIT]
    twc = [0, 0]
    for hand in range(MAX_HAND):
        dealer = (hand + 0) % 2
        log = [] if hand_log is not None else None
        try:
            d, _h, _b = play_hand(bots, chips, twc, hand, dealer, rng, log)
        except Exception as e:
            if hand_log is not None:
                hand_log.append("hand%d EXC %r" % (hand, e))
            d = [0, 0]
        chips[0] += d[0]
        chips[1] += d[1]
        twc[0] += d[0]
        twc[1] += d[1]
        # 破产保护：筹码 <=0 视为出局
        if chips[0] <= 0 or chips[1] <= 0:
            break
    return twc[0] - twc[1]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 12345
    ta = sys.argv[3] if len(sys.argv) > 3 else "v50"
    tb = sys.argv[4] if len(sys.argv) > 4 else "now"
    MK = {"v50": BotV50, "now": BotNow}
    rng = random.Random(seed)
    a_wins = b_wins = 0
    nets = []
    for i in range(n):
        if i % 2 == 0:
            diff = play_match(MK[ta]("a"), MK[tb]("b"), rng)
            a_net = diff
        else:
            diff = play_match(MK[tb]("b"), MK[ta]("a"), rng)
            a_net = -diff
        nets.append(a_net)
        if a_net > 0:
            a_wins += 1
        elif a_net < 0:
            b_wins += 1
        print("  第%3d场: %s净胜 %+7d   (%s %d : %d %s)" % (
            i + 1, ta, a_net, ta, a_wins, b_wins, tb), flush=True)
    print()
    print("=" * 70)
    print("对阵：%s(seat交替) vs %s —— %d 场，每场 %d 手，盲注 %d/%d，起始 %d" % (
        ta, tb, n, MAX_HAND, SB, BB, INIT))
    print("  %s 胜 %d 场 / %s 胜 %d 场 / 平 %d 场" % (
        ta, a_wins, tb, b_wins, n - a_wins - b_wins))
    print("  %s 累计净胜: %+d  场均 %+.1f" % (ta, sum(nets), sum(nets) / n))
    print("=" * 70)


if __name__ == "__main__":
    main()
