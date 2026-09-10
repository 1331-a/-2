# -*- coding: utf-8 -*-
"""botbattle_log.py — BotBattle 对局日志（botbattle.match.log）→ 逐决策 request。

【为什么需要】BotBattle 日志是「事件流」格式：
    match_start / hand_start / deal_hole / deal_board / action / settle
  而策略入口 decide() 吃的是 botzone 风格 request（my_cards/history/
  total_win_chips...）。本模块把事件流重建成逐决策 request，供本地重放。

事件字段速查：
    hand_start: {hand, chips:[a,b], sb:谁是小盲(0/1), bb:(1-sb)}
    deal_hole : {hand, holes:[[c1,c2],[c3,c4]]}          牌面字符串 "4c"
    deal_board: {hand, street:"flop"/"turn"/"river", board:[...]}
    action    : {hand, player, action:"fold|call|raise|check|allin", amount}
                amount = 该玩家本轮累计总注额（与 botzone 语义一致）
    settle    : {hand, chips, deltas, net:[a,b], pot, winners, reason}
"""
import json

_RANK = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6, '9': 7,
         'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}
_SUIT = {'c': 0, 'd': 1, 'h': 2, 's': 3}
_STREET_ROUND = {"preflop": 1, "flop": 2, "turn": 3, "river": 4}


def card_to_platform(s):
    """BotBattle 牌面字符串（'4c'）→ platform 整数（rank*4 + suit，0-51）。"""
    try:
        s = str(s).strip()
        r = _RANK[s[0].upper()]
        su = _SUIT[s[1].lower()]
        return r * 4 + su
    except Exception:
        return None


def _action_to_history(ev, street):
    """action 事件 → botzone history 条目。"""
    act = str(ev.get("action", "")).lower()
    amount = int(ev.get("amount", 0) or 0)
    if act == "fold":
        a, at = -1, "fold"
    elif act == "allin":
        a, at = -2, "allin"
    elif act in ("call", "check"):
        a, at = 0, ("call" if act == "call" else "check")
    else:  # raise / bet
        a, at = amount, "raise"
    return {"round": _STREET_ROUND.get(street, 1), "player_id": ev.get("player", 0),
            "action": a, "action_type": at}


def load_botbattle(path, my_seat=0, use_hand=None):
    """把 BotBattle 日志转成 request 列表（每个我方决策点一条）。

    my_seat : 我是哪个座位（0/1）——由调用方指定（日志里双方可能同名）
    use_hand: 只取某手（1-based，None=全部）
    返回 [(request_dict, meta), ...]
    """
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not (isinstance(obj, dict) and obj.get("format") == "botbattle.match.log"):
        return None

    events = (obj.get("replay") or {}).get("events") or []
    num_hands = int((obj.get("match") or {}).get("num_hands", 70) or 70)
    out = []

    chips = [20000, 20000]
    total_win = [0, 0]
    hand_idx = None
    holes = None
    board = []
    dealer = 0
    street = "preflop"
    actions = []          # [(event, street)]
    my_invested = 0       # 本手我方累计投入（含盲注）

    for ev in events:
        t = ev.get("type")
        if t == "hand_start":
            hand_idx = int(ev.get("hand", 0))
            chips = list(ev.get("chips") or [20000, 20000])
            dealer = int(ev.get("sb", 0) or 0)     # HU：小盲=庄家
            holes = None
            board = []
            actions = []
            street = "preflop"
            # 【2026-09-10 修正】hand_start.chips 是「盲注已扣」后的筹码，
            # 因此本手后续投入从 0 起算（若再计盲注会双重扣减，导致
            # invested 偏大、锁赢门槛虚高、判定失真）。
            my_invested = 0
        elif t == "deal_hole":
            holes = ev.get("holes")
        elif t == "deal_board":
            board = list(ev.get("board") or [])
            street = str(ev.get("street", "flop"))
        elif t == "action":
            if int(ev.get("player", -1)) == my_seat:
                if use_hand is None or (hand_idx + 1) == use_hand:
                    req = {
                        "num_players": 2,
                        "dealer_id": dealer,
                        "my_id": my_seat,
                        "my_chips": chips[my_seat] - my_invested,
                        "my_cards": [card_to_platform(c)
                                     for c in (holes or [[], []])[my_seat]],
                        "public_cards": [card_to_platform(c) for c in board],
                        "history": [_action_to_history(a, st) for a, st in actions],
                        "hand": (hand_idx or 0) + 1,     # botzone 用 1-based
                        "max_hand": num_hands,
                        "total_win_chips": total_win[:],
                        "total_win_games": [0, 0],
                    }
                    out.append((req, {"hand": (hand_idx or 0) + 1,
                                      "street": street,
                                      "chips": chips[:],
                                      "dealer": dealer}))
                amt = int(ev.get("amount", 0) or 0)
                # amount = 本轮累计总注额（含盲注）→ 减掉盲注才是「后续投入」
                _blind = 50 if dealer == my_seat else 100
                my_invested = max(my_invested, amt - _blind)
            actions.append((ev, street))
        elif t == "settle":
            # 【2026-09-10 修正】必须用 deltas（本手筹码变化）累加——
            # deltas 累加 == match.result.deltas（已验证 20029/-20029）；
            # 而 net 是平台显示值（累加会得到 77680 完全错误）。
            # 累加结果即 total_win_chips（零和：我 +X / 对手 -X）。
            d = ev.get("deltas") or [0, 0]
            try:
                total_win[0] += int(d[0])
                total_win[1] += int(d[1])
            except Exception:
                pass
    return out
