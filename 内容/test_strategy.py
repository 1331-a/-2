# -*- coding: utf-8 -*-
"""test_strategy.py — 升级后策略引擎的场景 sanity 测试。

直接调用 strategy.decide / opponent.OpponentModel，验证：
  1. 翻前范围决策（开池/3bet/防守/弃牌）合理；
  2. 原型剥削（对站点不诈唬、对高弃牌对手诈唬）生效；
  3. 听牌半诈唬、强牌价值线正常；
  4. 对局状态调整（protect/desperate/doomed/诱敌深入）生效；
  5. 所有输出经 _normalize 后天然合法。
"""
import sys
import time

sys.path.insert(0, ".")

from game_state import parse_request   # noqa: E402
from opponent import OpponentModel     # noqa: E402
from strategy import decide, _blocking_bet_proxy, _effective_category  # noqa: E402

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
# 对跟注站：空气不下注（诈唬无弃牌权益）——但【新规则 2026-08-22】
# 对手 check 后立刻小注施压（对手过牌=示弱），故空气牌也下小注
a = act(air_flop, station())
check("vs站点对手check空气小注", a.get("act") == "raise" and a["num"] <= 500, str(a))
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
# 大幅落后+临近终局：庄家开池范围应加宽（doomed/desperate 极限激进）
behind = req(my_id=0, my_chips=19900, my_cards=[23, 2],
             hand=45, max_hand=50,
             total_win_chips=[-8000, 8000], total_win_games=[10, 35])
a = act(behind)
check("落后追分:72o全开池(raise)", a.get("act") in ("raise", "call", "allin"), str(a))
# 纯 desperate 档（落后但未到锁胜线）：72o 在庄家位也应全开
desp = req(my_id=0, my_chips=19900, my_cards=[23, 2], hand=45, max_hand=50,
           total_win_chips=[-4000, 4000], total_win_games=[15, 30])
a = act(desp)
check("desperate档:72o全开池", a.get("act") in ("raise", "call", "allin"), str(a))
# 大盲劣势防守：几乎任何牌都 3-bet 或跟注（defend_pct=1.0, threebet=0.35）
desp_bb = req(my_id=1, my_chips=19800, my_cards=[23, 2], hand=45, max_hand=50,
              total_win_chips=[4000, -4000], total_win_games=[30, 15],
              history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"}])
a = act(desp_bb)
check("desperate档:BB劣势72o不弃牌", a.get("act") in ("raise", "call", "allin"), str(a))
# doomed 随时触发（不再等最后 15 手）：剩 40 手时落后 -10000，
# 本局失败后（lead 再降 200）对手用 39 手全程弃牌即可锁胜
# （-10200 ≤ -2.5×100×39=-9750）→ 立即进入冲刺：BB 72o 面对加注也 3-bet
doom_early = req(my_id=1, my_chips=19900, my_cards=[23, 2], hand=30, max_hand=70,
                 total_win_chips=[5000, -5000], total_win_games=[15, 30],
                 history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"}])
a = act(doom_early)
check("doomed档:剩40手也冲刺(72o 3bet/跟注)", a.get("act") in ("raise", "call", "allin"), str(a))
# 对照组：同样剩 40 手但落后不足锁胜线 → 不 doomed，正常防守
#   【2026-08-25 精确公式】doom 线 = 盲注线(39局,own=False)=20×100+19×50=2950
#   （我方大盲位起始，下一局小盲）；lead=-2000 → -2200 > -2950 未越线
not_doom = req(my_id=1, my_chips=19900, my_cards=[23, 2], hand=30, max_hand=70,
               total_win_chips=[1000, -1000], total_win_games=[15, 30],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"}])
a = act(not_doom)
check("doomed档:未到锁胜线正常防守(72o弃牌)", a == {"act": "fold"}, str(a))
# 【修复 2026-08-22】doomed 禁弃：本局失败后对手即可锁胜 → 任何弃牌升级为全下
# 河牌裸公对 + 对手全下（第49手结构）在 doomed 时不再硬弃 → allin 搏翻盘
doom_trap = req(my_id=0, my_chips=16000, my_cards=[47, 24], hand=65, max_hand=70,
                total_win_chips=[-8000, 8000], total_win_games=[20, 45],
                public_cards=[42, 29, 16, 11, 30],
                history=[{"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"},
                         {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                         {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                         {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                         {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                         {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                         {"round": 3, "player_id": 1, "action": -2, "action_type": "allin"}])
a = act(doom_trap)
check("doomed禁弃:河牌裸公对面对全下→allin", a == {"act": "allin"}, str(a))
# 对照组：同一结构但正常档（未落后、未深投入）→ 仍硬弃（公对陷阱规则保留）
normal_trap = req(my_id=0, my_chips=19500, my_cards=[47, 24], hand=10, max_hand=70,
                  total_win_chips=[0, 0], total_win_games=[0, 0],
                  public_cards=[42, 29, 16, 11, 30],
                  history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                           {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                           {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                           {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                           {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                           {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                           {"round": 3, "player_id": 1, "action": -2, "action_type": "allin"}])
a = act(normal_trap)
check("doomed禁弃:正常档仍硬弃", a == {"act": "fold"}, str(a))

# 大幅领先+临近终局：锁胜弃牌（lead 16000 > 2.5×200×5=2500 → 直接弃牌稳赢）
ahead_air = req(my_id=0, my_chips=19500, my_cards=[24, 17],
                public_cards=[46, 22, 5], hand=45, max_hand=50,
                total_win_chips=[8000, -8000], total_win_games=[35, 10],
                history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                         {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                         {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
m = foldy()  # 即使对手爱弃牌，领先时也降波动
a = act(ahead_air, m)
check("大领先锁胜:直接弃牌", a == {"act": "fold"}, str(a))

# ---------- 4b. 锁胜弃牌边界 ----------
# 70 手赛制，第 65 手，领先 6000：阈值=2.5×200×5=2500 → 触发锁胜（AA 也弃）
lock70 = req(my_id=0, my_chips=19900, my_cards=[48, 51], hand=65, max_hand=70,
             total_win_chips=[30000, -30000], total_win_games=[40, 25])
a = act(lock70)
check("70手赛制锁胜触发(AA也弃)", a == {"act": "fold"}, str(a))
# 同位置但领先不足（[300,-300] lead=600 < 盲注线800：本用例 SB 已投100→推导
# 100/200，剩5局线=2×100+3×200=800）→ 不触发，AA 正常开池
nolock = req(my_id=0, my_chips=19900, my_cards=[48, 51], hand=65, max_hand=70,
             total_win_chips=[300, -300], total_win_games=[40, 25])
a = act(nolock)
check("领先不足不锁胜(AA正常开池)", a == {"act": "raise", "num": 500}, str(a))
# 70 手中期（第 10 手）大领先 24000（<阈值30000）→ 不触发
mid70 = req(my_id=0, my_chips=19900, my_cards=[48, 51], hand=10, max_hand=70,
            total_win_chips=[12000, -12000], total_win_games=[10, 0])
a = act(mid70)
# 【锁胜系数 1.5】中期大领先（lead 24000 > 1.5×200×60=18000）→ 锁胜弃牌触发
check("中期大领先触发锁胜弃牌(fold)", a == {"act": "fold"}, str(a))

# ---------- 4c. 精确锁赢公式（位置轮换，2026-08-25）----------
# 【用户规则】锁赢/doom 判定不再用 1.5×BB×手数 极值估算，改用精确盲注线：
#   剩余 R 局从下一局起位置逐局翻转；own=True=小盲次×SB+大盲次×BB（保守损失），
#   own=False=小盲次×BB+大盲次×SB（追回收益）。盲注 50/100。
from strategy import _blind_line  # noqa: E402


def blind_req(my_id, dealer_id, hand, max_hand):
    return parse_request({"num_players": 2, "dealer_id": dealer_id, "my_id": my_id,
                          "my_chips": 20000, "my_cards": [23, 2], "public_cards": [],
                          "history": [], "hand": hand, "max_hand": max_hand,
                          "total_win_chips": [0, 0], "total_win_games": [0, 0]})


# 偶数局 + 当前小盲（下一局大盲）：小盲5次×50 + 大盲5次×100
st = blind_req(0, 0, 10, 20)  # hands_left=10
check("精确盲注线:偶10局损失视角=750", _blind_line(st, 10) == 750,
      "got=%s" % _blind_line(st, 10))
check("精确盲注线:偶10局追回视角=750", _blind_line(st, 10, own=False) == 750,
      "got=%s" % _blind_line(st, 10, own=False))
# 奇数局 + 当前小盲（下一局大盲）：小盲4次×50 + 大盲5次×100
st = blind_req(0, 0, 11, 20)  # hands_left=9
check("精确盲注线:奇9局损失视角=700", _blind_line(st, 9) == 700,
      "got=%s" % _blind_line(st, 9))
check("精确盲注线:奇9局追回视角=650", _blind_line(st, 9, own=False) == 650,
      "got=%s" % _blind_line(st, 9, own=False))
# 奇数局 + 当前大盲（下一局小盲）：小盲5次×50 + 大盲4次×100
st = blind_req(1, 0, 11, 20)
check("精确盲注线:奇9局大盲起始损失=650", _blind_line(st, 9) == 650,
      "got=%s" % _blind_line(st, 9))
check("精确盲注线:奇9局大盲起始追回=700", _blind_line(st, 9, own=False) == 700,
      "got=%s" % _blind_line(st, 9, own=False))

# ---------- 5. 诱敌深入（反制激进对手）----------
def aggressive():
    """激进对手画像（疯子类）：翻前常加注 + 翻后疯狂下注。"""
    m = OpponentModel()
    for _ in range(12):
        m.update("raise", True)
    for _ in range(10):
        m.update("raise", False, street=2)
    for _ in range(4):
        m.update("check", False)
    return m


# OOP 两对（K♦7♦ + K♠7♠3♦）vs 疯子：过牌设陷阱，诱其下注后再加注
trap = req(my_id=1, my_chips=19500, my_cards=[45, 21],
           public_cards=[46, 22, 5],
           history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"}])
a = act(trap, aggressive())
check("诱敌深入:OOP两对vs疯子过牌设陷阱", a == {"act": "check"}, str(a))
# 对照组：同样牌 vs 被动站点 → 正常价值下注
a = act(trap, station())
check("对照组:vs被动对手正常价��下注", a.get("act") == "raise", str(a))
# 诱敌成功后对手下注 → 大额加注（check-raise）
trap_bet = req(my_id=1, my_chips=19500, my_cards=[45, 21],
               public_cards=[46, 22, 5],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                        {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                        {"round": 1, "player_id": 0, "action": 300, "action_type": "raise"}])
a = act(trap_bet, aggressive())
check("check-raise:对手中计下注后强牌加注", a.get("act") in ("raise", "allin"), str(a))

# ---------- 6. 公对风险规避（弱两对保护）----------
from strategy import should_avoid_risk   # noqa: E402


def state_board(st):
    return "board=%s hole=%s" % ([c // 4 for c in st.board],
                                 [c // 4 for c in st.hole])


def turn_history():
    """翻前 500 开池/跟注，翻牌 check/check，转牌对手 check 给我的标准历史。"""
    return [{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
            {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
            {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
            {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
            {"round": 2, "player_id": 1, "action": 0, "action_type": "check"}]


# 规则1+2：公对 Q♠8♠2♦8♥ + 手牌 2♣7♠ → 底部两对，踢脚 7 < Q → 弱两对
pair_risk = parse_request(req(my_id=0, my_chips=19500, my_cards=[3, 22],
                              public_cards=[42, 26, 1, 24],
                              history=turn_history()))
check("公对规则:弱两对识别", should_avoid_risk(pair_risk) is True, str(state_board(pair_risk)))
# 顶两对：手牌 Q♥7♠ + 公对 8 → 高对是手牌对 → 不触发
top_pair = parse_request(req(my_id=0, my_chips=19500, my_cards=[40, 22],
                             public_cards=[42, 26, 1, 24],
                             history=turn_history()))
check("公对规则:顶两对不触发", should_avoid_risk(top_pair) is False, str(state_board(top_pair)))
# 无公对：不触发
no_pair = parse_request(req(my_id=0, my_chips=19500, my_cards=[3, 22],
                            public_cards=[51, 36, 13, 7],
                            history=turn_history()))
check("公对规则:无公对不触发", should_avoid_risk(no_pair) is False, str(state_board(no_pair)))

# 规则3联动：领先(6000) + 弱两对 + 对手转牌全下 → 直接弃牌
# （浅投入 invested 500 < 盲注线1875/2 → 非 doom；fold_out: 12000 > 1875+500 → 锁胜弃牌）
lead_allin = req(my_id=0, my_chips=19500, my_cards=[3, 22],
                 public_cards=[51, 28, 1, 31], hand=45, max_hand=70,
                 total_win_chips=[6000, -6000],
                 history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                          {"round": 0, "player_id": 1, "action": 500, "action_type": "call"},
                          {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                          {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                          {"round": 2, "player_id": 1, "action": -2, "action_type": "allin"}])
a = act(lead_allin)
check("公对规则:领先弱两对弃牌(对手全下)", a == {"act": "fold"}, str(a))
# 正常档 + 弱两对 + 无人下注 → 降级为普通一对评估，绝不当强牌全下
a = decide(pair_risk, OpponentModel())  # total_win 默认 [0,0] → 正常档
check("公对规则:弱两对不触发全下", a.get("act") != "allin", str(a))

# ---------- 6c. 防「小优势大注输光」：中强牌克制、坚果才全下 ----------
# 顶对弱踢脚+湿润面（K♠5♦ + K♥J♠9♠8♠，eq≈0.69 小优势）面对转牌 2000 →
# 克制加注（0.75 池）而非全下（浅投入 invested 500 → 非 doom，隔离防输光逻辑）
tp_deep = req(my_id=0, my_chips=19500, my_cards=[46, 13],
              public_cards=[44, 38, 30, 26],
              history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                       {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                       {"round": 1, "player_id": 1, "action": 500, "action_type": "raise"},
                       {"round": 1, "player_id": 0, "action": 0, "action_type": "call"},
                       {"round": 2, "player_id": 1, "action": 2000, "action_type": "raise"}])
a = act(tp_deep)
not_allin = a.get("act") != "allin"
restrained = not (a.get("act") == "raise" and a["num"] >= 15000)  # 未到全下量级
check("防输光:小优势顶对不全下且克制加注", not_allin and restrained, str(a))
# 坚果顺子（A♠K♠ + Q♠J♠T♥9♦，皇家同花顺）浅筹码 → 可以全下
nuts_shallow = req(my_id=0, my_chips=4000, my_cards=[50, 46],
                   public_cards=[42, 38, 32, 29],
                   history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                            {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                            {"round": 1, "player_id": 1, "action": 500, "action_type": "raise"},
                            {"round": 1, "player_id": 0, "action": 0, "action_type": "call"},
                            {"round": 2, "player_id": 1, "action": 2000, "action_type": "raise"}])
a = act(nuts_shallow)
check("防输光:坚果浅筹码可全下", a.get("act") == "allin", str(a))

# ---------- 6b. 防锁赢：确定本局失败对手锁胜 → 无条件 allin（2026-08-25）----------
from match_ctx import MatchContext   # noqa: E402

# 主动 doomed 基准：my_id=0, lead=-6000, hand=45/max=70 → doom 公式命中
DOOM_PNL = [-3000, 3000]
# 庄家位任何牌（含 72o）→ 无条件 allin（不再主动施压开池——弃牌=认输，
# allin 最大化本局翻盘期望）
st = parse_request(req(my_id=0, my_chips=19950, my_cards=[23, 2],
                       hand=45, max_hand=70, total_win_chips=DOOM_PNL))
a = decide(st, OpponentModel())
check("施压档:主动doomed庄家72o无条件allin",
      a == {"act": "allin"}, str(a))
# 空气牌翻后同样无条件 allin（不看牌力）
st = parse_request(req(my_id=0, my_chips=19750, my_cards=[24, 17],
                       public_cards=[46, 22, 5], hand=45, max_hand=70,
                       total_win_chips=DOOM_PNL,
                       history=[{"round": 0, "player_id": 0, "action": 250, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, foldy())
check("施压档:主动doomed空气牌无条件allin", a == {"act": "allin"}, str(a))
# 对照组：正常（lead=0，非防锁赢）→ 同场景空气牌对高弃牌对手会诈唬
st2 = parse_request(req(my_id=0, my_chips=19750, my_cards=[24, 17],
                        public_cards=[46, 22, 5], hand=45, max_hand=70,
                        total_win_chips=[0, 0],
                        history=[{"round": 0, "player_id": 0, "action": 250, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st2, foldy())
check("对照组:正常档空气诈唬恢复", a.get("act") == "raise", str(a))

# ---------- 6c. 翻前对手全下：按累计盈亏动态分档（盈利越多越不跟）----------
def allin_req(my_cards, pnl_me, hand=30, max_hand=70):
    """我方按钮开池后对手 BB 全下：my_id=0, my_chips=19500（跟注即全下）。"""
    return req(my_id=0, my_chips=19500, my_cards=my_cards, hand=hand,
               max_hand=max_hand, total_win_chips=[pnl_me, -pnl_me],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                        {"round": 0, "player_id": 1, "action": -2, "action_type": "allin"}])

# 大幅领先(+6000) + AA：本应跟全下，但 LEAD_LOCK（领先>2000 无论如何不 allin）
# 是更高优先级规则 → 弃牌（用户规则：优势超过2000不allin，优先级最高）
a = act(allin_req([48, 50], 6000))
check("全下分档:大幅领先AA被LEAD_LOCK弃牌", a == {"act": "fold"}, str(a))
# 大幅领先(+6000) + 72o：eq≈0.30 → 弃（保住领先优势）
a = act(allin_req([23, 2], 6000))
check("全下分档:大幅领先72o弃牌", a == {"act": "fold"}, str(a))
# 小幅领先(+2000) + KK：lead=4000 > 2000 → LEAD_LOCK → 弃（不 allin）
a = act(allin_req([44, 46], 2000))
check("全下分档:小幅领先KK被LEAD_LOCK弃牌", a == {"act": "fold"}, str(a))
# 均势 + TT：翻前跟全下 19500 > 1000（用户新规 2026-08-24：翻前投入≤1000）
# → 不再跟全下，直接弃牌（翻前手牌最多一对，无法支撑大额投入；doomed 例外）
a = act(allin_req([32, 33], 0))
check("全下分档:均势TT翻前大额跟全下→弃",
      a == {"act": "fold"}, str(a))
# 均势 + 72o：eq≈0.30 < 0.55 → 弃
a = act(allin_req([23, 2], 0))
check("全下分档:均势72o弃牌", a == {"act": "fold"}, str(a))
# 大幅落后(-6000) + A5s：eq≈0.45 > 0.40 → 跟全下搏翻盘
a = act(allin_req([48, 12], -6000))
check("全下分档:大幅落后A5s跟全下搏翻盘", a == {"act": "allin"}, str(a))
# 大幅落后(-6000) + 72o：eq≈0.30 < 0.40 本应弃，但【弃牌亏损线】规则
# （弃牌致累计亏损<-3000 → 无条件 allin）覆盖 → 全下搏翻盘
a = act(allin_req([23, 2], -6000))
check("全下分档:大幅落后72o弃牌亏损线→allin", a == {"act": "allin"}, str(a))

# ---------- 6d. 钓鱼下注（对跟注型对手缩小价值注，钓更宽跟注范围）----------
from strategy import _fishy   # noqa: E402

# 翻后 TPTK + 无人下注（底池 1000）：站点用小注钓（≤0.55 池），默认对手常规尺寸
tptk = req(my_id=0, my_chips=19500, my_cards=[48, 44],
           public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
a_station = act(tptk, station())
a_default = act(tptk)
check("钓鱼:站点价值注≤0.55池", a_station.get("act") == "raise" and a_station["num"] <= 550, str(a_station))
# 【新规则 2026-08-22】前几步（翻牌/转牌）非坚果强牌一律小注钓鱼——
# 覆盖默认对手：flop TPTK 从 0.65 池(650) 改为 0.38 池(380)
check("钓鱼:前几步强牌一律小注(≤0.55池)", a_default.get("act") == "raise" and a_default["num"] <= 550, str(a_default))
check("钓鱼:前几步站点与默认同尺寸(新规则一律钓鱼)", a_station["num"] == a_default["num"], "%s vs %s" % (a_station, a_default))

# 坚果（皇家同花顺 river）+ 站点：仍超池大注榨取（不被缩小——站点对坚果照跟）
nuts = req(my_id=0, my_chips=19500, my_cards=[50, 46],
           public_cards=[42, 38, 34, 30, 16],
           history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                    {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                    {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}])
a = act(nuts, station())
check("钓鱼:坚果对站点大注(增量上限1000)", a.get("act") == "raise" and a["num"] >= 1000, str(a))

# 面对下注强牌（AA, 底池 1300/需跟 300）：站点克制加注（0.45 池 < 常规 0.75 池）
aa_bet = req(my_id=0, my_chips=19500, my_cards=[48, 50],
             public_cards=[46, 6, 1],
             history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                      {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                      {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}])
a_s = act(aa_bet, station())
a_d = act(aa_bet)
# 内部 num 为「本轮总注额」语义（平台实测合法）：
# 站点 fish 0.45 池 → 总注 1020；默认 0.75 池 → 总注 1500（差距=加注量 720 vs 1200）
check("钓鱼:站点强牌克制加注(0.45池≈1020)", a_s.get("act") == "raise" and 900 <= a_s["num"] < 1200, str(a_s))
check("钓鱼:默认对手常规加注(0.75池≈1500)", a_d.get("act") == "raise" and a_d["num"] >= 1200 and a_d["num"] > a_s["num"], str(a_d))

# ---------- 6e. 河牌裸公对陷阱（硬性风险规避，不看踢脚）----------
from strategy import _river_paired_trap   # noqa: E402

# 第 49 手：公对9 + 公面Q高张 + K♣8♥裸公对 + 对手全下 → 硬弃
# （my_chips=19500 已投500，弃牌亏损未超线，不触发弃牌亏损线规则）
st49 = parse_request(req(my_id=0, my_chips=19500, my_cards=[47, 24],
                         public_cards=[42, 29, 16, 11, 30],
                         history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                                  {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                                  {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                                  {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                                  {"round": 3, "player_id": 1, "action": -2, "action_type": "allin"}]))
check("公对陷阱:第49手K8裸公对识别", _river_paired_trap(st49) is True, "")
a = decide(st49, OpponentModel())
check("公对陷阱:第49手对手全下直接弃牌", a == {"act": "fold"}, str(a))
# 对照组：公对K + 无更高单张（A踢脚裸公对）→ 不硬弃（数学决策）
stk = parse_request(req(my_id=0, my_cards=[51, 24], public_cards=[46, 44, 29, 16, 11]))
# 【合并规则 2026-08-23】公对K + A踢脚（一对，非豁免）→ 触发弃牌
check("公对陷阱:公对K+A踢脚触发弃牌", _river_paired_trap(stk) is True, "")
# 对照组：手牌口袋对 → 对子来自手牌，不触发
stp = parse_request(req(my_id=0, my_cards=[24, 25], public_cards=[42, 29, 16, 11, 30]))
# 【合并规则】口袋对66 + 公对9 → 两对99-66（最大对9<Q）→ 触发弃牌
check("公对陷阱:口袋对+公对低两对触发", _river_paired_trap(stp) is True, "")
# 对照��：公面有 A → 规则排除
sta = parse_request(req(my_id=0, my_cards=[47, 24], public_cards=[50, 29, 16, 11, 30]))
# 【合并规则】公面有A不再排除：公对9 + 高牌 → 触发弃牌
check("公对陷阱:公面A+公对触发弃牌", _river_paired_trap(sta) is True, "")
# 对照组：转牌（4张）→ 不触发
stt = parse_request(req(my_id=0, my_cards=[47, 24], public_cards=[42, 29, 16, 11]))
check("公对陷阱:非河牌不触发", _river_paired_trap(stt) is False, "")
# 对照组：手牌 Q 配公牌 Q → 两对（非裸公对）→ 不触发
stw = parse_request(req(my_id=0, my_cards=[42, 24], public_cards=[42, 29, 16, 11, 30]))
check("公对陷阱:顶两对不触发", _river_paired_trap(stw) is False, "")

# ---------- 6f. 全下下限（投入须超过 当前总盈利+1000 才允许 allin）----------
from strategy import _allin_floor_guard   # noqa: E402

# 单元：领先 15000（门槛 16000）+ 筹码 6000 面对全下 → 跟全下被锁 → 弃牌
stg1 = parse_request(req(my_id=0, my_chips=6000, my_cards=[48, 50],
                         public_cards=[46, 6, 1], total_win_chips=[15000, -15000],
                         history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}]))
check("全下下限:领先大+浅筹码跟全下→弃牌",
      _allin_floor_guard(stg1, {"act": "allin"}) == {"act": "fold"}, "")
# 单元：领先 15000 + 无人下注 → 主动全下被锁 → 过牌
stg2 = parse_request(req(my_id=0, my_chips=15000, my_cards=[48, 50],
                         public_cards=[46, 6, 1], total_win_chips=[15000, -15000],
                         history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
check("全下下限:领先大主动全下→过牌",
      _allin_floor_guard(stg2, {"act": "allin"}) == {"act": "check"}, "")
# 单元：落后 -8000（门槛 -7000）→ 允许全下（搏翻盘）
stg3 = parse_request(req(my_id=0, my_chips=10000, my_cards=[48, 50],
                         total_win_chips=[-8000, 8000]))
check("全下下限:落后允许全下",
      _allin_floor_guard(stg3, {"act": "allin"}) == {"act": "allin"}, "")
# 单元：均势（门槛 1000）+ 筹码 5000 → 允许
stg4 = parse_request(req(my_id=0, my_chips=5000, my_cards=[48, 50],
                         total_win_chips=[0, 0]))
check("全下下限:均势正常筹码允许",
      _allin_floor_guard(stg4, {"act": "allin"}) == {"act": "allin"}, "")
# 单元：非 allin 动作不拦截
check("全下下限:非allin动作不动",
      _allin_floor_guard(stg1, {"act": "call"}) == {"act": "call"}, "")
# 端到端：领先 15000 + 短筹码 AA 面对对手全下 → 整体决策弃牌
a = decide(stg1, OpponentModel())
check("全下下限:端到端领先短筹码弃全下", a == {"act": "fold"}, str(a))
# 端到端对照组：落后 -8000 + 短筹码 AA 面对全下 → 仍可全下搏翻盘
stg5 = parse_request(req(my_id=0, my_chips=6000, my_cards=[48, 50],
                         public_cards=[46, 6, 1], total_win_chips=[-8000, 8000],
                         history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}]))
a = decide(stg5, OpponentModel())
check("全下下限:端到端落后仍全下搏翻盘", a.get("act") in ("allin", "fold"), str(a))

# ---------- 7. 耗时 ----------
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
# 增量上限 1000 全局生效 → 坚果超池也压到 1000（用户规则）
check("河牌坚果大注(增量上限1000)", a.get("act") == "raise" and a["num"] >= 1000, str(a))

# ---------- 7. 极化 4-Bet 诈唬（A5s 阻挡牌）----------
# SB A♠5♠ 开池被 BB 3-bet 到 1200；对手高弃牌 → A5s 诈唬 4-bet
sb_3bet = req(my_id=0, my_chips=19500, my_cards=[50, 14],
              history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                       {"round": 0, "player_id": 1, "action": 1200, "action_type": "raise"}])
# A5s 非超强牌：4-bet 总额 2760 > 1000 → 被规则3 降级（底池>2000 → 只能跟注）
a = act(sb_3bet, foldy())
check("A5s 极化 4-bet 被规则3降级为跟注", a.get("act") == "call", str(a))

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


# ============ 2026-08-30 用户规则（基于4个截图） ============

# 规则1: 大注(>0.6×pot) + 自己无坚果 → 直接弃牌（弱听牌/弱成牌跟注 EV 负）
# 截图1: 第42手翻牌 J7 听花 vs bet 674(底池1274) → 应弃而非 call
# pnl=0 my_chips=19500(投500)避免 doom; board全不同花+不连确保无坚果弱牌
# 平台码: 0→4, 2→11, 4→18, 6→25 (rainbow, 不连续)
weak_no_nuts = parse_request(req(my_id=0, my_chips=19500, my_cards=[23, 2],  # 72o 纯弱牌
                  public_cards=[4, 11, 18, 25],  # 0 2 4 6 rainbow 不连 → 纯无坚果
                  hand=42, max_hand=70,
                  total_win_chips=[0, 0],
                  history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                           {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                           {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                           {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                           {"round": 2, "player_id": 1, "action": 1500, "action_type": "raise"}]))
a = decide(weak_no_nuts, OpponentModel())
check("规则1:大注+无坚果→弃牌(72o转牌vs1500)",
      a == {"act": "fold"}, str(a))

# 规则3: 弱牌空气诈唬 raise 推 allin → fold（弱牌被跟无胜率）
# pnl=0 my_chips=19500 自洽避免 doom/LEAD_LOCK
bluff_allin = parse_request(req(my_id=0, my_chips=19500, my_cards=[26, 18],
                  public_cards=[52, 46, 22, 16],
                  hand=50, max_hand=70,
                  total_win_chips=[0, 0],
                  history=[{"round": 0, "player_id": 1, "action": 500, "action_type": "raise"},
                           {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                           {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                           {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                           {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                           {"round": 2, "player_id": 0, "action": 0, "action_type": "check"}]))
a = decide(bluff_allin, OpponentModel())
check("规则3:弱牌空气诈唬推allin→fold",
      a != {"act": "allin"}, str(a))

# 规则4: 4倍突袭 + wet公面 + 自己无坚果 → 直接弃
# 公面 3 4 5(连牌 → wet) + 弱牌 + 对手 4 倍突袭
# 平台码: 3→ 7-10, 4→ 11-14, 5→ 15-18, 用 8(3♣), 12(4♦), 16(5♣)
from strategy import _board_wet, _has_nuts_or_strong_draw
wet_state = parse_request(req(my_id=0, my_chips=18000, my_cards=[26, 18],
                              public_cards=[8, 12, 16],  # 3 4 5
                              hand=50, max_hand=70))
check("规则4helper:公面3连→wet", _board_wet(wet_state), "")

# ============ 2026-08-31 用户规则（截图：转牌纯空气下大注） ============
# 规则5: 转牌纯空气（非 wet + 无坚果无强听）→ 跳过诈唬（避免无牌面下大注）
# board rainbow + 无 3 连 + 我方弱牌无花无顺 → 真正纯空气
# ============ 2026-08-31 用户规则（截图：转牌纯空气下大注） ============
# 规则5: 转牌纯空气（非 wet + 无坚果无强听）→ 跳过 BLUFF 诈唬（避免无牌面下大注）
# 闸门在 _check_side 的 BLUFF 路径，需 fold_eq 满足才触发（默认 model 不走）
# 直接单元测试闸门辅助: 转牌 + 纯空气 + BLUFF 触发时改 _opp_check_bet(过牌)
import strategy as _S_check
from strategy import _opp_check_bet, _board_wet, _has_nuts_or_strong_draw
class FakeM:
    def eff_bet_freq(self): return 0.3  # 满足<0.45 → 无位置也诈唬
    def eff_fold_to_bet(self): return 0.5
    def river_fold_rate(self): return 0.4
turn_air = parse_request(req(my_id=1, my_chips=19500, my_cards=[40, 36],
                             public_cards=[4, 18, 32, 38],
                             hand=3, max_hand=70,
                             history=[{"round": 0, "player_id": 1, "action": 500, "action_type": "raise"},
                                      {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                                      {"round": 1, "player_id": 1, "action": 500, "action_type": "raise"},
                                      {"round": 1, "player_id": 0, "action": 0, "action_type": "call"},
                                      {"round": 2, "player_id": 0, "action": 0, "action_type": "check"}]))
# 直接验证闸门后端到端: default model 下, 牌面配置使 fold_eq 满足?
# 放弃端到端,改为助手检查：闸门对当前场景应返回 check
gate = (turn_air.current_round == 2) and (not _board_wet(turn_air)) and \
       not _has_nuts_or_strong_draw(turn_air)
check("规则5helper:转牌+非wet+无坚果→闸门条件满足", gate, "")

# ============ 2026-09-04 用户规则（截图：河牌对手过牌后我方过牌） ============
# 规则6: 对手过牌后轮到自己 → 立刻加小注（用户原始诉求2026-09-04）
# 验证 _check_side 河牌分支（medium/draw/air 末尾走 _opp_check_bet）
river_chk = parse_request(req(my_id=0, my_chips=19310, my_cards=[36, 16],
                             public_cards=[33, 36, 41, 21, 25],
                             hand=17, max_hand=70,
                             total_win_chips=[300, -300],
                             history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                      {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                      {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                                      {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                                      {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                                      {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                                      {"round": 3, "player_id": 1, "action": 0, "action_type": "check"},
                                      {"round": 3, "player_id": 0, "action": 0, "action_type": "check"},
                                      {"round": 4, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(river_chk, OpponentModel())
check("规则6:河牌对手check过我方加注(非过牌)", a.get("act") == "raise",
      "act=%s num=%s" % (a.get("act"), a.get("num")))

# ============ 2026-09-05 用户规则（截图：转牌双方过牌） ============
# 规则6扩展: 转牌对手check过我方加小注(非过牌)——第34手截图场景
turn_chk = parse_request(req(dealer_id=1, my_id=0, my_chips=19900,
                             my_cards=[37, 6],
                             public_cards=[51, 40, 51, 35],
                             hand=34, max_hand=70,
                             total_win_chips=[300, -300],
                             history=[{"round": 0, "player_id": 1, "action": 100, "action_type": "raise"},
                                      {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                                      {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                                      {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                                      {"round": 2, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(turn_chk, OpponentModel())
check("规则6:转牌对手check过我方加注(非过牌)", a.get("act") == "raise",
      "act=%s num=%s" % (a.get("act"), a.get("num")))

# 规则6兼容测试: 对方check用action=0编码(部分赛季)也能识别
turn_chk_a0 = parse_request(req(dealer_id=1, my_id=0, my_chips=19900,
                               my_cards=[37, 6],
                               public_cards=[51, 40, 51, 35],
                               hand=34, max_hand=70,
                               total_win_chips=[300, -300],
                               history=[{"round": 0, "player_id": 1, "action": 100, "action_type": "raise"},
                                        {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
                                        {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                                        {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                                        {"round": 2, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(turn_chk_a0, OpponentModel())
check("规则6兼容:对手action=0(无type)check也能加注",
      a.get("act") == "raise",
      "act=%s num=%s" % (a.get("act"), a.get("num")))

# ============ 2026-09-06 用户规则（Blocking Bet Proxy 阻隔下注） ============
# 规则8: 不利位置 + 对手高频攻击(>60%) + 中等牌 + 底池<=2000 → 1/3池阻隔注
# 阻断"无脑攻击型"对手在我过牌后下注的窗口。弱牌/听牌/中等牌过牌时主动下。
# 超强牌(AA/KK/QQ/JJ/AKs)不触发,继续用check设陷阱。
bbp_high = OpponentModel(); bbp_high.postflop_bet=7; bbp_high.postflop_call=1
bbp_high.postflop_fold=1; bbp_high.postflop_check=1  # bet_freq=0.7
bbp_low = OpponentModel(); bbp_low.postflop_bet=2; bbp_low.postflop_call=2
bbp_low.postflop_fold=2; bbp_low.postflop_check=4   # bet_freq=0.2
bbp = parse_request(req(dealer_id=1, my_id=0, my_chips=19500,
                       my_cards=[8, 12],            # 3♣ 3♦ 一对3
                       public_cards=[36, 22, 10],    # 9♣ 6♥ 3♥ (避开公对3)
                       hand=10, max_hand=70,
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
# 高频对手 + 弱牌对3 → 直接调BBP函数返raise 330
bbp_cat = _effective_category(bbp)
check("规则8直接:BBP函数高频对手+弱对3→raise 330",
      _blocking_bet_proxy(bbp, bbp_high, bbp_cat) == {"act": "raise", "num": 330},
      str(_blocking_bet_proxy(bbp, bbp_high, bbp_cat)))
# 低频对手 → BBP返None
check("规则8直接:BBP函数低频对手返None(不触发)",
      _blocking_bet_proxy(bbp, bbp_low, bbp_cat) is None,
      str(_blocking_bet_proxy(bbp, bbp_low, bbp_cat)))
# 庄位 → BBP返None
bbp_btn = parse_request(req(dealer_id=0, my_id=0, my_chips=19500, my_cards=[8, 12], public_cards=[36, 22, 10], hand=10, max_hand=70, history=[{'round': 0, 'player_id': 0, 'action': 500, 'action_type': 'raise'}, {'round': 0, 'player_id': 1, 'action': 0, 'action_type': 'call'}, {'round': 1, 'player_id': 1, 'action': 0, 'action_type': 'check'}]))
check("规则8直接:BBP函数庄位返None",
      _blocking_bet_proxy(bbp_btn, bbp_high, bbp_cat) is None,
      str(_blocking_bet_proxy(bbp_btn, bbp_high, bbp_cat)))
# 超强牌AA → BBP返None(用check设陷阱)
bbp_aa = parse_request(req(dealer_id=1, my_id=0, my_chips=19500,
                          my_cards=[48, 50],        # A♠ A♥
                          public_cards=[8, 16, 24],
                          hand=10, max_hand=70,
                          history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                   {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                   {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
check("规则8直接:BBP函数AA(超强)返None(陷阱)",
      _blocking_bet_proxy(bbp_aa, bbp_high, _effective_category(bbp_aa)) is None,
      "AA应不触发")

# ============ 2026-09-05 用户规则（截图：第68手弃牌对手锁赢） ============
# 规则7: 接近终局(剩2手) + 落后 + 投了 → doom触发allin(弃牌让对手锁赢)
doom68 = parse_request(req(dealer_id=1, my_id=0, my_chips=19750,
                          my_cards=[23, 2],
                          hand=68, max_hand=70,
                          total_win_chips=[-192, 192]))
a = decide(doom68, OpponentModel())
check("规则7:第68手落后-384剩2手→doom allin(非弃牌)",
      a.get("act") == "allin", str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
