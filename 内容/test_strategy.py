# -*- coding: utf-8 -*-
"""test_strategy.py — 升级后策略引擎的场景 sanity 测试。

直接调用 strategy.decide / opponent.OpponentModel，验证：
  1. 翻前范围决策（开池/3bet/防守/弃牌）合理；
  2. 原型剥削（对站点不诈唬、对高弃牌对手诈唬）生效；
  3. 听牌半诈唬、强牌价值线正常；
  4. 对局状态调整（protect/catchup）生效；
  5. 所有输出经 _normalize 后天然合法。
"""
import sys
import time

sys.path.insert(0, ".")

from game_state import parse_request   # noqa: E402
from opponent import OpponentModel     # noqa: E402
from strategy import decide            # noqa: E402

# 牌号 -> BotZone 编码（内部 = n+8）
HA, DA, SA, CA = 48, 49, 50, 51  # 四张 A


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 1,
            "my_chips": 19800, "my_cards": [51, 23], "public_cards": [],
            "history": [], "hand": 0, "max_hand": 50,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


def act(request, model=None):
    st = parse_request(request)
    m = model or OpponentModel()
    return decide(st, m)


fails = 0


def check(name, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# ---------- 1. 翻前范围 ----------
# 庄家 AA 开池到 500（2.5BB）
a = act(req(my_id=0, my_chips=19900, my_cards=[48, 44], history=[]))
check("庄家AA开池=raise500", a == {"act": "raise", "num": 500}, str(a))
# 庄家 72o 弃牌（对手先验偏凶）
a = act(req(my_id=0, my_chips=19900, my_cards=[23, 2], history=[]))
check("庄家72o弃牌", a == {"act": "fold"}, str(a))
# 大盲面对溜入：AA 隔离加注，72o 过牌
limp = [{"round": 0, "player_id": 0, "action": 0, "action_type": "call"}]
a = act(req(my_cards=[48, 51], history=limp))
check("大盲AA隔离>=640", a.get("act") == "raise" and a["num"] >= 640, str(a))
a = act(req(my_cards=[23, 2], history=limp))
check("大盲72o过牌", a == {"act": "check"}, str(a))
# 大盲面对 2.5x 加注：AA 3bet，72o 弃牌
r500 = [{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"}]
a = act(req(my_cards=[48, 51], history=r500))
check("大盲AA 3bet>=1000(2x500)", a.get("act") == "raise" and a["num"] >= 1000, str(a))
a = act(req(my_cards=[23, 2], history=r500))
check("大盲72o弃牌", a == {"act": "fold"}, str(a))

# ---------- 2. 对手原型剥削 ----------
def station():
    """跟注站画像：松+被动+不弃牌。"""
    m = OpponentModel()
    for _ in range(20):
        m.update("call", True)
    for _ in range(6):
        m.update("call", False)
    for _ in range(4):
        m.update("check", False)
    return m


def foldy():
    """高弃牌（岩石）画像：紧+被动+爱弃。"""
    m = OpponentModel()
    for _ in range(16):
        m.update("fold", True)
    for _ in range(8):
        m.update("fold", False)
    for _ in range(4):
        m.update("check", False)
    return m


# 翻后空气牌面（K♠7♠3♦，我 8♥6♦ 无任何听牌）
air_flop = req(my_id=0, my_chips=19500, my_cards=[24, 17],
               public_cards=[46, 22, 5],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                        {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                        {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
# 对跟注站：空气不下注（诈唬无弃牌权益）
a = act(air_flop, station())
check("vs站点空气不下注", a == {"act": "check"}, str(a))
# 对高弃牌对手：空气诈唬
a = act(air_flop, foldy())
check("vs岩石空气诈唬下注", a.get("act") == "raise" and a["num"] >= 200, str(a))

# ---------- 3. 听牌半诈唬与强牌价值 ----------
# 同花听牌（A♥5♥ + 3♥9♥K♦，4 张红桃 = 9 outs）应下注半诈唬
fd = req(my_id=0, my_chips=19500, my_cards=[48, 12],
         public_cards=[4, 28, 45],
         history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
a = act(fd)
check("同花听牌半诈唬", a.get("act") == "raise", str(a))

# 两对（K♦7♦ + K♠7♠3♦）面对下注应加注或全下
two_pair = req(my_id=0, my_chips=19500, my_cards=[45, 21],
               public_cards=[46, 22, 5],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                        {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                        {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}])
a = act(two_pair)
check("两对面对下注加注/全下", a.get("act") in ("raise", "allin"), str(a))

# ---------- 4. 对局状态调整 ----------
# 大幅落后+临近终局：庄家开池范围应加宽（catchup）
behind = req(my_id=0, my_chips=19900, my_cards=[23, 2],
             hand=45, max_hand=50,
             total_win_chips=[-8000, 8000], total_win_games=[10, 35])
a = act(behind)
check("落后追分:72o至少不保守弃牌(开池/溜入)",
      a.get("act") in ("raise", "call", "allin"), str(a))

# 大幅领先+临近终局：空气不诈唬（protect）
ahead_air = req(my_id=0, my_chips=19500, my_cards=[24, 17],
                public_cards=[46, 22, 5], hand=45, max_hand=50,
                total_win_chips=[8000, -8000], total_win_games=[35, 10],
                history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                         {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                         {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
m = foldy()  # 即使对手爱弃牌，领先时也降波动
a = act(ahead_air, m)
check("领先保收益:空气控池过牌", a == {"act": "check"}, str(a))

# ---------- 5. 耗时 ----------
t0 = time.time()
for _ in range(10):
    act(air_flop, station())
dt = (time.time() - t0) / 10
check("单步耗时<0.5s", dt < 0.5, "%.0fms" % (dt * 1000))

# ---------- 6. 河牌超池下注（坚果价值最大化）----------
# A♠K♠ + Q♠J♠T♠9♠2♥ = 皇家同花顺，河牌对手过牌给我 → 超池榨取
from strategy import _match_adjust, _is_4bet_bluff   # noqa: E402
royal = req(my_id=0, my_chips=19500, my_cards=[50, 46],
            public_cards=[42, 38, 34, 30, 16],
            history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                     {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                     {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                     {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                     {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                     {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                     {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}])
a = act(royal)
check("河牌坚果超池下注(>池)", a.get("act") == "raise" and a["num"] > 1000, str(a))

# ---------- 7. 极化 4-Bet 诈唬（A5s 阻挡牌）----------
# SB A♠5♠ 开池被 BB 3-bet 到 1200；对手高弃牌 → A5s 诈唬 4-bet
sb_3bet = req(my_id=0, my_chips=19500, my_cards=[50, 14],
              history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                       {"round": 0, "player_id": 1, "action": 1200, "action_type": "raise"}])
a = act(sb_3bet, foldy())
check("A5s 极化 4-bet 诈唬", a.get("act") == "raise" and a["num"] >= 2 * 1200, str(a))

# ---------- 8. ICM 压力模式 ----------
# 领先 40BB + 剩 10 手 + 对手短码 → pressure（直接检测调整函数）
pressure_st = parse_request(req(my_id=0, my_chips=19500, my_cards=[50, 14],
                                hand=40, max_hand=50,
                                total_win_chips=[8000, -8000],
                                history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                                         {"round": 0, "player_id": 1, "action": 10000, "action_type": "raise"}]))
check("ICM 压力模式触发", _match_adjust(pressure_st) == "pressure",
      _match_adjust(pressure_st))
# 普通领先（对手不短）→ protect
protect_st = parse_request(req(my_id=0, my_chips=19500, my_cards=[50, 14],
                                hand=40, max_hand=50,
                                total_win_chips=[8000, -8000],
                                history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                                         {"round": 0, "player_id": 1, "action": 600, "action_type": "raise"}]))
check("普通领先=protect", _match_adjust(protect_st) == "protect",
      _match_adjust(protect_st))

# ---------- 9. 对手模型衰减 ----------
m = foldy()
before = m.preflop_fold
m.decay(0.5)
check("decay 半衰计数", m.preflop_fold == before // 2,
      "%d->%d" % (before, m.preflop_fold))

# ---------- 10. 街级特征 ----------
m = OpponentModel()
for _ in range(5):
    m.update("raise", False, street=2)   # 转牌加注 5 次
    m.update("call", False, street=2)    # 转牌跟注 5 次
check("转牌加注率识别", m.turn_aggr() >= 0.40, "%.2f" % m.turn_aggr())
m2 = OpponentModel()
for _ in range(6):
    m2.update("fold", False, street=3)
    m2.update("call", False, street=3)
check("河牌弃牌率识别", m2.river_fold_rate() >= 0.40, "%.2f" % m2.river_fold_rate())

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
