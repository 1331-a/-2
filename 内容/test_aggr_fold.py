# -*- coding: utf-8 -*-
"""AGGR_FOLD（2026-10-19）：对手连开≥2 街 + 我方≤一对 + 不是极便宜 → 把**跟注**改弃。

背景：用户反馈「有些场景太激进，经常小注偷但容易面对对手加注还硬跟导致大亏」。
离线真值评估（测/_call_policy_eval.py，138 个「面对下注仍跟注」的可算真值点）：
  · 窄口径（连开≥2 & ≤一对 & req>0.25）命中 4 点，全部 EV<0、零误杀、净 +8,886；
  · 宽口径（≤一对 & req>0.33）命中 47 点、误杀 33 个正 EV 点（净 −1,801）⇒ 不上。

本测试只断言守卫的**作用域与边界**，不依赖 MC：
  ① 该弃的弃；② 牌型够好不压；③ 只开火一次不压；④ 极便宜不压；
  ⑤ 只压 call（raise/allin 一律不动）；⑥ 开关能逐字回退。
"""
import strategy as S
from game_state import parse_request

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("[PASS] %s" % name)
    else:
        print("[FAIL] %s %s" % (name, detail))
        FAILS.append(name)


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 15000, "my_cards": [48, 50], "public_cards": [],
            "history": [], "hand": 20, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# 平台编码：n = rank*4 + suit。公面 Q 8 4 = [40, 22, 1]
FLOP = [40, 22, 1]
TURN = [40, 22, 1, 16]

# 对手翻牌下注 300（aggr=1），转牌再下注 900（aggr=2）
H_TWO_STREETS = [
    {"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
    {"round": 1, "player_id": 1, "action": 300, "action_type": "bet"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "call"},
    {"round": 2, "player_id": 1, "action": 8000, "action_type": "bet"},
]
# 只有本街一次加注（aggr=1）
H_ONE_STREET = [
    {"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
    {"round": 2, "player_id": 1, "action": 8000, "action_type": "bet"},
]


def st_weak(hist, cards=(32, 33), chips=15000, board=TURN):
    """一对 8（8♦8♥ + 公面 8）—— 牌型 = 一对。"""
    return parse_request(req(my_cards=list(cards), public_cards=list(board),
                             my_chips=chips, history=hist))


# ---------- 1. 连开两街 + 一对 + 不是极便宜 → 弃 ----------
s = st_weak(H_TWO_STREETS)
check("连开两街+一对+req>0.25：call → fold",
      S._aggr_fold_guard(s, {"act": "call"}, S.ONE_PAIR) == {"act": "fold"},
      "%s cat=%s aggr=%d req=%.2f"
      % (S._aggr_fold_guard(s, {"act": "call"}, S.ONE_PAIR),
         S._effective_category(s), S._opp_hand_raises(s),
         s.to_call / (s.pot + s.to_call)))

# ---------- 2. 牌型 ≥ 两对 → 不动 ----------
check("连开两街 + 两对：call 保持",
      S._aggr_fold_guard(s, {"act": "call"}, S.TWO_PAIR) == {"act": "call"},
      str(S._aggr_fold_guard(s, {"act": "call"}, S.TWO_PAIR)))

# ---------- 3. 对手只开火一次 → 不动 ----------
s1 = st_weak(H_ONE_STREET)
check("只开火一次：call 保持",
      S._opp_hand_raises(s1) == 1
      and S._aggr_fold_guard(s1, {"act": "call"}, S.ONE_PAIR) == {"act": "call"},
      "aggr=%d" % S._opp_hand_raises(s1))

# ---------- 4. 极便宜（req ≤ 0.25）→ 不动 ----------
s2 = st_weak(H_TWO_STREETS, chips=15000)
# 把对手转牌下注改小：底池 ~3000 时下 300 ⇒ req ≈ 0.09
H_SMALL = H_TWO_STREETS[:-1] + [
    {"round": 2, "player_id": 1, "action": 1000, "action_type": "bet"}]
s2 = parse_request(req(my_cards=[32, 33], public_cards=list(TURN),
                       my_chips=15000, history=H_SMALL))
req2 = s2.to_call / (s2.pot + s2.to_call)
check("极便宜(req<=0.25)：call 保持",
      req2 <= 0.25 and S._opp_hand_raises(s2) >= 2
      and S._aggr_fold_guard(s2, {"act": "call"}, S.ONE_PAIR) == {"act": "call"},
      "req=%.2f aggr=%d" % (req2, S._opp_hand_raises(s2)))

# ---------- 5. 只压 call：raise / allin / check 一律不动 ----------
check("raise 不被压成 fold",
      S._aggr_fold_guard(s, {"act": "raise", "num": 2000}, S.ONE_PAIR)
      == {"act": "raise", "num": 2000})
check("allin 不被压成 fold",
      S._aggr_fold_guard(s, {"act": "allin"}, S.ONE_PAIR) == {"act": "allin"})
check("check 不受影响",
      S._aggr_fold_guard(s, {"act": "check"}, S.ONE_PAIR) == {"act": "check"})

# ---------- 6. 开关回退 ----------
_old = S.AGGR_FOLD_ON
try:
    S.AGGR_FOLD_ON = False
    check("开关关闭：call 逐字保持",
          S._aggr_fold_guard(s, {"act": "call"}, S.ONE_PAIR) == {"act": "call"})
finally:
    S.AGGR_FOLD_ON = _old

# ---------- 7. 常量口径 ----------
check("常量：MIN_AGGR=2 / MAX_CAT=ONE_PAIR / MIN_REQ=0.25",
      S.AGGR_FOLD_MIN_AGGR == 2 and S.AGGR_FOLD_MAX_CAT == S.ONE_PAIR
      and abs(S.AGGR_FOLD_MIN_REQ - 0.25) < 1e-9,
      "%s/%s/%s" % (S.AGGR_FOLD_MIN_AGGR, S.AGGR_FOLD_MAX_CAT,
                    S.AGGR_FOLD_MIN_REQ))

print()
if FAILS:
    print("有 %d 项失败：%s" % (len(FAILS), FAILS))
    raise SystemExit(1)
print("全部通过")
