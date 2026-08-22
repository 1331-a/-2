# -*- coding: utf-8 -*-
"""test_match_ctx.py — 赛制上下文（对手弃牌推断/激进等级/回撤保护）单元测试。

直接构造轻量状态桩驱动 MatchContext.update，验证：
  1. 直接收盲率推断 → 疑似锁胜标记；
  2. 激进等级分档（累计盈亏 ±20%）；
  3. 回撤降档 + 连续盈利升档；
  4. 序列化往返。
"""
import sys

sys.path.insert(0, ".")

from match_ctx import (MatchContext, LEVEL_CONSERVATIVE, LEVEL_NORMAL,  # noqa: E402
                       LEVEL_AGGRESSIVE)
from game_state import INIT_CHIPS  # noqa: E402

fails = 0


def check(name, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class StubState:
    """轻量状态桩：只需 hand_num / total_win_chips / my_id / opp_id。"""

    def __init__(self, hand, wins):
        self.hand_num = hand
        self.total_win_chips = list(wins)  # [p0, p1]
        self.my_id = 0
        self.opp_id = 1


def seq_states(hands, wins_seq, my_id=0):
    """构造连续手牌序列，wins_seq[i] = 第 i 手结束时我方累计净赢。"""
    out = []
    for h, w in zip(hands, wins_seq):
        s = StubState(h, [w, -w])
        s.my_id = my_id
        out.append(s)
    return out


# ---------- 1. 疑似锁胜推断 ----------
# 连续 15 手净赢交替 +50/+100（对手弃 SB/BB）→ 直接收盲率 100% → 疑似锁胜
ctx = MatchContext()
hands = list(range(0, 16))
wins = []
acc = 0
for i in range(16):
    acc += 50 if i % 2 == 0 else 100
    wins.append(acc)
for s in seq_states(hands, wins):
    ctx.update(s)
check("锁胜推断:直接收盲率=100%", abs(ctx.direct_blind_rate - 1.0) < 1e-9,
      "%.2f" % ctx.direct_blind_rate)
check("锁胜推断:opponent_locking=True", ctx.opponent_locking is True)
check("锁胜推断:窗口≤20局", len(ctx.recent_hands) <= 20,
      str(len(ctx.recent_hands)))

# 对照组：正常胜负交替（非盲注额）→ 不标记锁胜
ctx2 = MatchContext()
acc = 0
for i in range(16):
    acc += 500 if i % 2 == 0 else -200
    ctx2.update(StubState(i, [acc, -acc]))
check("锁胜推断:正常波动不误判", ctx2.opponent_locking is False,
      "rate=%.2f" % ctx2.direct_blind_rate)

# 对照组：收盲率 90%>65% 但 对手全下频率 = 10%（不 <10%）→ 不标记锁胜（规则1 双条件）
class StubStateR(StubState):
    def __init__(self, hand, wins, opp_allin=False):
        super().__init__(hand, wins)
        self.request = {"history": [
            {"player_id": 1,
             "action_type": "allin" if opp_allin else "call"}]}

ctx2b = MatchContext()
acc = 0
for i in range(20):
    if i >= 18:            # 第 19、20 手对手全下（频率 10%）
        acc += -1000
        ctx2b.update(StubStateR(i, [acc, -acc], opp_allin=True))
    else:                  # 前 18 手直接收盲（90%）
        acc += 50
        ctx2b.update(StubStateR(i, [acc, -acc]))
check("锁胜推断:全下频率10%不标记",
      ctx2b.opponent_locking is False,
      "allin_freq=%.2f rate=%.2f" % (ctx2b.opp_allin_freq, ctx2b.direct_blind_rate))

# ---------- 2. 激进等级分档（模块二）----------
# 大盈利 > +20% → 保守
ctx3 = MatchContext()
acc = 0
for i in range(10):
    acc += 1000
    ctx3.update(StubState(i, [acc, -acc]))
    ctx3.sync_baseline(StubState(i, [acc, -acc]))
check("等级分档:盈利>20%→保守", ctx3.level == LEVEL_CONSERVATIVE,
      "level=%d" % ctx3.level)
# 大亏损 < -20% → 激进
ctx4 = MatchContext()
acc = 0
for i in range(10):
    acc -= 1000
    ctx4.update(StubState(i, [acc, -acc]))
    ctx4.sync_baseline(StubState(i, [acc, -acc]))
check("等级分档:亏损>20%→激进", ctx4.level == LEVEL_AGGRESSIVE,
      "level=%d" % ctx4.level)

# ---------- 3. 回撤保护（模块三）----------
# 正常档遭遇单局大败（-25% = -5000）→ 降到保守
ctx5 = MatchContext()
ctx5.level = LEVEL_NORMAL
acc = 0
for i in range(5):
    acc += 200
    ctx5.update(StubState(i, [acc, -acc]))
# 第 6 手大败 -5000
acc -= 5000
ctx5.update(StubState(5, [acc, -acc]))
check("回撤:大败后降档", ctx5.level == LEVEL_CONSERVATIVE,
      "level=%d (期望 %d)" % (ctx5.level, LEVEL_CONSERVATIVE))

# 保守档连续 3 局盈利 → 升回正常
ctx5.consec_profit = 0
for i in range(3):
    acc += 300
    ctx5.update(StubState(6 + i, [acc, -acc]))
check("回撤:保守连续3盈利升档", ctx5.level == LEVEL_NORMAL,
      "level=%d" % ctx5.level)

# ---------- 4. 阈值偏移 ----------
ctx6 = MatchContext()
ctx6.level = LEVEL_AGGRESSIVE
check("偏移:激进=负偏移", ctx6.threshold_offset(None) == -6)
ctx6.level = LEVEL_CONSERVATIVE
check("偏移:保守=正偏移", ctx6.threshold_offset(None) == 6)
ctx6.level = LEVEL_NORMAL
check("偏移:正常=0", ctx6.threshold_offset(None) == 0)

# ---------- 5. 序列化往返 ----------
d = ctx5.to_dict()
ctx7 = MatchContext.from_dict(d)
check("序列化:往返一致", ctx7.level == ctx5.level and
      ctx7.consec_profit == ctx5.consec_profit and
      ctx7.opponent_locking == ctx5.opponent_locking)
ctx8 = MatchContext.from_dict({"bad": "data", "level": 2})
check("序列化:脏数据防护", ctx8.level == 2 and ctx8.consec_profit == 0)

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
