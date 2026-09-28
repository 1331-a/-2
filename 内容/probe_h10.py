# -*- coding: utf-8 -*-
"""probe_h10.py — 复现实战第 10 手（跟注 807 输掉 → 对手锁赢）的判定链。

实战数据（截图 + 日志）：
  河牌：我方 J♥Q♣，公面 6♥K♥K♦10♠10♥，对手 A♦5♠
  对手河牌下注 807，我方**跟注 807**，输掉本手 1,614（本手净 −1,614）
  本场净胜结算后 −4,603（对手 +4,603）→ 即**本手开始时我们 −2,989**
  本手双方各投入 1,614；决策点上：已投入 807、to_call 807、底池 2,421
  显示「第10手」= hand 索引 9（界面 hand+1）→ 剩余 60 手
  座位：我方 = 小盲/庄家（my_id == dealer_id）

目的：确认「跟注即锁赢」的判据是否成立，以及哪道闸门把它挡掉了。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategy                                              # noqa: E402
from game_state import parse_request                         # noqa: E402
from opponent import OpponentModel                           # noqa: E402
from strategy import (decide, _blind_line, _invested, _exposure,  # noqa: E402
                      _doom_risk, _sealed_by_call, _endgame_matters,
                      _match_adjust, _hands_left, _lock_win_unified,
                      UA_SEALED_MARGIN)

# 内部牌号 → 平台牌号 = 内部 − 8
# J♥ = 11*4+1 = 45 → 37 ; Q♣ = 12*4+3 = 51 → 43
# 公面 6♥=25→17  K♥=53→45  K♦=54→46  10♠=40→32  10♥=41→33
HOLE = [37, 43]
BOARD = [17, 45, 46, 32, 33]

# 决策点：双方各已投入 807、底池 2,421、对手河牌下注 807 → to_call=807
# 注意 history 的 amount 是**本街累计总额**（raise-to 语义），按街给：
#   翻前：双方各 489（我方开池 489、对手跟）→ 978
#   转牌：我方下注 318、对手跟 318        → 636（累计各 807）
#   河牌：对手下注 807                     → to_call 807，底池 2,421
HISTORY = [
    {"round": 0, "player_id": 0, "action": 489, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 489, "action_type": "call"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
    {"round": 2, "player_id": 0, "action": 318, "action_type": "raise"},
    {"round": 2, "player_id": 1, "action": 318, "action_type": "call"},
    {"round": 3, "player_id": 1, "action": 807, "action_type": "raise"},
]

REQ = {
    "num_players": 2, "dealer_id": 0, "my_id": 0,
    "my_chips": 20000 - 807,
    "my_cards": HOLE, "public_cards": BOARD,
    "history": HISTORY, "hand": 9, "max_hand": 70,
    "total_win_chips": [-2989, 2989],      # 本手开始时我们 −2,989（结算后 −4,603）
    "total_win_games": [0, 0],
}

st = parse_request(REQ)
print("=" * 84)
print("第10手重建：stage=%s  to_call=%s  pot=%s  my_chips=%s" % (
    st.stage, st.to_call, st.pot, st.my_chips))
print("=" * 84)

lead = int(st.total_win_chips[st.my_id]) - int(st.total_win_chips[st.opp_id])
inv = _invested(st)
exp = _exposure(st)
left = _hands_left(st)
line = _blind_line(st, left, own=False)
print("lead（我方−对手）           = %+d" % lead)
print("已投入 invested            = %d" % inv)
print("敞口 exposure(=inv+to_call) = %d" % exp)
print("剩余手数 hands_left         = %d" % left)
print("追回线 _blind_line(own=F)   = %d   → 2×线 = %d" % (line, 2 * line))
print("-" * 84)
print("① 弃牌口径  lead − 2×invested  = %+d   vs −2×线 = %+d   → doom=%s"
      % (lead - 2 * inv, -2 * line, lead - 2 * inv <= -2 * line))
print("② 跟注口径  lead − 2×exposure  = %+d   vs −2×线 = %+d   → doom=%s"
      % (lead - 2 * exp, -2 * line, lead - 2 * exp <= -2 * line))
print("③ 明显被锁 _sealed_by_call     = %s   （需 ≤ %+d，即再超线 %.0f%%）"
      % (_sealed_by_call(st), -2 * line * (1 + UA_SEALED_MARGIN),
         UA_SEALED_MARGIN * 100))
print("④ 终局触发面 _endgame_matters  = %s" % _endgame_matters(st, {"act": "call"}))
print("⑤ 入口 match_adjust 档位       = %s" % _match_adjust(st))
print("⑥ 规则2 统一入口返回            = %s" % _lock_win_unified(st))
print("-" * 84)
print("实际决策（无对手样本）        = %s" % decide(st, OpponentModel()))
m = OpponentModel()
m.preflop_call, m.preflop_fold, m.hands_seen = 5, 3, 8
print("实际决策（普通对手画像）      = %s" % decide(st, m))
print("-" * 84)
over = (lead - 2 * exp) - (-2 * line)
print("★结论：跟注口径越线幅度 = %+d 筹码（%+.1f%% 相对 2×线）；"
      % (over, 100.0 * over / (2 * line)))
print("  `_sealed_by_call` 要求再超 %.0f%% → 本手未达「明显被锁」→ 强制全押不触发；"
      % (UA_SEALED_MARGIN * 100))
print("  同时规则2-A（弃牌口径）也不成立 → 于是走了常规策略的**便宜跟注**。")
