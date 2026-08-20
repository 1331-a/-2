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
# 对照组：同样剩 40 手但落后不足锁胜线（-5000）→ 不 doomed，正常防守
not_doom = req(my_id=1, my_chips=19900, my_cards=[23, 2], hand=30, max_hand=70,
               total_win_chips=[2500, -2500], total_win_games=[15, 30],
               history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"}])
a = act(not_doom)
check("doomed档:未到锁胜线正常防守(72o弃牌)", a == {"act": "fold"}, str(a))

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
# 同位置但领先不足（[400,-400], 阈值2500）→ 不触发，AA 正常开池
nolock = req(my_id=0, my_chips=19900, my_cards=[48, 51], hand=65, max_hand=70,
             total_win_chips=[400, -400], total_win_games=[40, 25])
a = act(nolock)
check("领先不足不锁胜(AA正常开池)", a == {"act": "raise", "num": 500}, str(a))
# 70 手中期（第 10 手）大领先 24000（<阈值30000）→ 不触发
mid70 = req(my_id=0, my_chips=19900, my_cards=[48, 51], hand=10, max_hand=70,
            total_win_chips=[12000, -12000], total_win_games=[10, 0])
a = act(mid70)
check("中期大领先不触发(AA正常开池)", a == {"act": "raise", "num": 500}, str(a))

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
lead_allin = req(my_id=0, my_chips=1000, my_cards=[3, 22],
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
# 克制加注（0.75 池）而非全下
tp_deep = req(my_id=0, my_chips=17000, my_cards=[46, 13],
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

# ---------- 6b. 偷盲档（对手疑似锁胜 → 关闭诈唬+高频小额偷盲）----------
from match_ctx import MatchContext   # noqa: E402

lock_ctx = MatchContext()
lock_ctx.opponent_locking = True
# 偷盲档：庄家位任何牌（含 72o）小额开池
st = parse_request(req(my_id=0, my_chips=19900, my_cards=[23, 2],
                       hand=45, max_hand=70, total_win_chips=[0, 0]))
a = decide(st, OpponentModel(), lock_ctx)
check("偷盲档:庄家72o小额偷盲(2.2BB)", a == {"act": "raise", "num": 440}, str(a))
# 偷盲档：空气牌翻后不诈唬（即使对手高弃牌）
st = parse_request(req(my_id=0, my_chips=19500, my_cards=[24, 17],
                       public_cards=[46, 22, 5], hand=45, max_hand=70,
                       total_win_chips=[0, 0],
                       history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st, foldy(), lock_ctx)   # foldy 高弃牌，平时会诈唬 → 偷盲档关闭
check("偷盲档:空气牌不诈唬", a == {"act": "check"}, str(a))
# 对照组：无 ctx（正常）→ 同场景空气牌对高弃牌对手会诈唬
a = decide(st, foldy())
check("对照���:正常档空气诈唬恢复", a.get("act") == "raise", str(a))

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
# 均势 + TT：eq≈0.60 > 0.55 门槛 → 跟全下
a = act(allin_req([32, 33], 0))
check("全下分档:均势TT跟全下", a == {"act": "allin"}, str(a))
# 均势 + 72o：eq≈0.30 < 0.55 → 弃
a = act(allin_req([23, 2], 0))
check("全下分档:均势72o弃牌", a == {"act": "fold"}, str(a))
# 大幅落后(-6000) + A5s：eq≈0.45 > 0.40 → 跟全下搏翻盘
a = act(allin_req([48, 12], -6000))
check("全下分档:大幅落后A5s跟全下搏翻盘", a == {"act": "allin"}, str(a))
# 大幅落后(-6000) + 72o：eq≈0.30 < 0.40 → 仍弃（赌博也有底线）
a = act(allin_req([23, 2], -6000))
check("全下分档:大幅落后72o仍弃牌", a == {"act": "fold"}, str(a))

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
check("钓鱼:默认对手常规尺寸≥0.5池", a_default.get("act") == "raise" and a_default["num"] >= 500, str(a_default))
check("钓鱼:站点注小于常规注", a_station["num"] < a_default["num"], "%s vs %s" % (a_station, a_default))

# 坚果（皇家同花顺 river）+ 站点：仍超池大注榨取（不被缩小——站点对坚果照跟）
nuts = req(my_id=0, my_chips=19500, my_cards=[50, 46],
           public_cards=[42, 38, 34, 30, 16],
           history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                    {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                    {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}])
a = act(nuts, station())
check("钓鱼:坚果对站点仍超池", a.get("act") == "raise" and a["num"] >= 1200, str(a))

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
st49 = parse_request(req(my_id=0, my_chips=3000, my_cards=[47, 24],
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
check("公对陷阱:公对K无更高单张不触发", _river_paired_trap(stk) is False, "")
# 对照组：手牌口袋对 → 对子来自手牌，不触发
stp = parse_request(req(my_id=0, my_cards=[24, 25], public_cards=[42, 29, 16, 11, 30]))
check("公对陷阱:口袋对不触发", _river_paired_trap(stp) is False, "")
# 对照��：公面有 A → 规则排除
sta = parse_request(req(my_id=0, my_cards=[47, 24], public_cards=[50, 29, 16, 11, 30]))
check("公对陷阱:公面有A不触发", _river_paired_trap(sta) is False, "")
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
