# -*- coding: utf-8 -*-
"""STEAL_GUARD（2026-10-19）：对手反复加注时，弱牌小注改为过牌。

背景：人机对局 12 手翻后小注净 −22,898，其中 9 手（75%）被加注。
阈值不是拍的 —— 用真值 EV 扫出来的（测/_steal_thresh.py，162 个点）：
  0.30 → 误伤 28 个盈利点；0.45 → 仍偏宽；**0.60 → 省 1,858、误伤 2**。

本测试只断言作用域与边界（不依赖 MC / 不依赖真实牌局）：
  ① 高档位弱牌小注 → 过牌；② 两对不压；③ 有听牌不压；④ 大注不压；
  ⑤ 中低档位不压；⑥ 面对下注时不适用；⑦ 样本不足不压；⑧ 开关回退。
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


class FakeModel:
    """只实现 `_opp_raise_vs_bet` 用到的接口。"""

    def __init__(self, rate=None, n=0, faces=0):
        self._rate = rate
        self._n = n
        self.check_faces = faces
        self.check_raise = 0
        self.bet_resp_events = []

    @staticmethod
    def _bet_size_bucket(is_preflop, total, bb, pot):
        return "sf_small"

    def bet_resp_stats(self, bucket, cur_hand=None, min_samples=4):
        if self._rate is None:
            return None
        return {"fold": 0, "call": 0, "raise": int(self._rate * 10),
                "n": 10, "raise_rate": self._rate}

    def check_raise_rate(self):
        return (self._rate or 0.10)


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 15000, "my_cards": [48, 50], "public_cards": [],
            "history": [], "hand": 30, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# 公面 Q 8 4；我方 8♦8♥ = 一对 8（cat=1）
FLOP = [40, 22, 1]
H = [{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
     {"round": 0, "player_id": 1, "action": 0, "action_type": "call"}]
st = parse_request(req(my_cards=[32, 33], public_cards=FLOP, history=H))
print("夹具：stage=%s to_call=%s pot=%s cat=%s"
      % (st.stage, st.to_call, st.pot, S._effective_category(st)))

ACT = {"act": "raise", "num": int(st.curbet[st.my_id] + st.pot * 0.33)}

# ---------- 1. 高档位（0.75）+ 弱牌 + 小注 → 过牌 ----------
m = FakeModel(rate=0.75, n=10)
check("加注率0.75 + 一对 + 小注 → check",
      S._steal_guard(st, m, dict(ACT), S.ONE_PAIR) == {"act": "check"},
      str(S._steal_guard(st, m, dict(ACT), S.ONE_PAIR)))

# ---------- 2. 两对不压 ----------
check("两对 → 不压",
      S._steal_guard(st, m, dict(ACT), S.TWO_PAIR) == ACT)

# ---------- 3. 有听牌不压 ----------
check("big_draw → 不压",
      S._steal_guard(st, m, dict(ACT), S.ONE_PAIR, big_draw=True) == ACT)
check("draw → 不压",
      S._steal_guard(st, m, dict(ACT), S.ONE_PAIR, draw=True) == ACT)

# ---------- 4. 大注不压 ----------
big = {"act": "raise", "num": int(st.curbet[st.my_id] + st.pot * 0.75)}
check("大注(>0.5池) → 不压",
      S._steal_guard(st, m, dict(big), S.ONE_PAIR) == big)

# ---------- 5. 中低档位不压 ----------
check("加注率0.45 → 不压",
      S._steal_guard(st, FakeModel(rate=0.45, n=10), dict(ACT), S.ONE_PAIR) == ACT)
check("加注率0.30 → 不压",
      S._steal_guard(st, FakeModel(rate=0.30, n=10), dict(ACT), S.ONE_PAIR) == ACT)

# ---------- 6. 样本不足 → 不压 ----------
check("无统计样本 → 不压",
      S._steal_guard(st, FakeModel(rate=None), dict(ACT), S.ONE_PAIR) == ACT)

# ---------- 7. 面对下注时不适用 ----------
s2 = parse_request(req(my_cards=[32, 33], public_cards=FLOP,
                       history=H + [{"round": 1, "player_id": 1,
                                     "action": 200, "action_type": "bet"}]))
check("面对下注(to_call>0) → 不动",
      S._opp_raise_vs_bet(m, s2) is not None
      and S._steal_guard(s2, m, {"act": "call"}, S.ONE_PAIR) == {"act": "call"})

# ---------- 8. 开关回退 ----------
_old = S.STEAL_GUARD_ON
try:
    S.STEAL_GUARD_ON = False
    check("开关关闭 → 逐字保持",
          S._steal_guard(st, m, dict(ACT), S.ONE_PAIR) == ACT)
finally:
    S.STEAL_GUARD_ON = _old

# ---------- 9. 常量口径 ----------
check("常量：MAX_FRAC=0.5 / RAISE_MIN=0.6",
      abs(S.STEAL_GUARD_MAX_FRAC - 0.5) < 1e-9
      and abs(S.STEAL_GUARD_RAISE_MIN - 0.60) < 1e-9,
      "%s/%s" % (S.STEAL_GUARD_MAX_FRAC, S.STEAL_GUARD_RAISE_MIN))

print()
if FAILS:
    print("有 %d 项失败：%s" % (len(FAILS), FAILS))
    raise SystemExit(1)
print("全部通过")
