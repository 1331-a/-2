# -*- coding: utf-8 -*-
"""test_rule123.py — 用户三条优先级规则专项测试。

  规则1（最高优先级）：对手锁胜 → BTN 任意牌 2.5BB 偷盲 + 翻后 C-Bet 85%
                        + 被加注/全下立即弃牌；
  规则2（第二优先级）：盈利且本局已投 > 盈利+2000 且胜率>30% → 立即全下
                        （LEAD_LOCK 优先，仅领先≤2000 时生效）；
  规则3（第三优先级）：非超强牌（AA/KK/QQ/JJ/AKs 外）主动下注总注额>1000
                        → 降级（底池≤2000 下 50%，否则过牌/跟注）。
"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request  # noqa: E402
from opponent import OpponentModel  # noqa: E402
from match_ctx import MatchContext  # noqa: E402
from strategy import decide, _is_super_hand, _is_sub_strong, _match_adjust  # noqa: E402

fails = 0


def check(name, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0, "my_chips": 19950,
            "my_cards": [23, 2], "public_cards": [], "history": [],
            "hand": 40, "max_hand": 70,
            "total_win_chips": [800, -800], "total_win_games": [0, 0]}
    base.update(kw)
    return base


def locking_ctx():
    """对手锁胜上下文：最近20局收盲率100%、全下频率0。"""
    c = MatchContext()
    c.recent_hands = [[50, False]] * 20
    c.direct_blind_rate = 1.0
    c.opp_allin_freq = 0.0
    c.opponent_locking = True
    return c


# ================= 规则1：对手锁胜激进调整 =================
print("===== 规则1 =====")
# 1) BTN 任意两张牌（72o）→ 2.5BB=250 开池，频率100%
a = decide(parse_request(req()), OpponentModel(), locking_ctx())
check("规则1:BTN 72o 开池 2.5BB",
      a == {"act": "raise", "num": 250}, str(a))

# 2) 翻后空气牌 → 高频 C-Bet（50~60% 池；my_chips 须与翻前 250×2 一致）
st2 = parse_request(req(my_chips=19750, public_cards=[46, 22, 5], my_cards=[24, 17],
                        history=[{"round": 0, "player_id": 0, "action": 250, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st2, OpponentModel(), locking_ctx())
check("规则1:翻后空气牌C-Bet",
      a.get("act") == "raise" and 0.4 <= a["num"] / max(st2.pot, 1) <= 0.65, str(a))

# 3) 被加注（空气牌）→ 立即弃牌不纠缠
st3 = parse_request(req(my_chips=19750, public_cards=[46, 22, 5], my_cards=[24, 17],
                        history=[{"round": 0, "player_id": 0, "action": 250, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 600, "action_type": "raise"}]))
check("规则1:被加注(空气)立即弃牌",
      decide(st3, OpponentModel(), locking_ctx()) == {"act": "fold"}, "")

# 4) 被加注但持顺子 → 例外，正常决策（不无脑弃）
st4 = parse_request(req(my_chips=19750, public_cards=[50, 46, 42], my_cards=[36, 32],
                        history=[{"round": 0, "player_id": 0, "action": 250, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 2000, "action_type": "raise"}]))
a = decide(st4, OpponentModel(), locking_ctx())
check("规则1:被加注(顺子)例外正常决策", a.get("act") in ("raise", "allin"), str(a))

# 5) 对照组：对手正常（非锁胜）→ 72o 开池按常规（弃牌），不误伤
a = decide(parse_request(req()), OpponentModel(), MatchContext())
check("规则1:对照组正常对手72o不偷盲", a.get("act") == "fold", str(a))

# ================= 规则2：盈利锁胜全下 =================
print("===== 规则2 =====")
# 6) 盈利800（lead1600 ≤ 2000 未锁）+ 已投4000 > 800+2000 → 全下锁胜
st6 = parse_request(req(my_chips=16000, my_cards=[48, 44],
                        public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st6, OpponentModel())
check("规则2:盈利+深投入→全下锁胜", a == {"act": "allin"}, str(a))

# 7) 已投不足（2000 < 2800）→ 不触发
st7 = parse_request(req(my_chips=18000, my_cards=[48, 44],
                        public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 1000, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st7, OpponentModel())
check("规则2:已投不足不触发", a.get("act") != "allin", str(a))

# 8) MUST-WIN 覆盖 LEAD_LOCK：盈利2500（lead5000>2000 本应锁定不 allin），
#    但本局已深投入（8000）且牌面有利（AKs 顶对，eq~0.75）——落败即致对手
#    锁胜（2×投入后-领先 > 2.5bb×剩余手数）→ 按用户新规则【无条件全下】。
#    （LEAD_LOCK 的小注方案同样会输掉生死局，故 MUST-WIN 优先）
st8 = parse_request(req(my_chips=12000, my_cards=[48, 44],
                        total_win_chips=[2500, -2500],
                        public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st8, OpponentModel())
# 【2026-08-23】MUST-WIN 已删除统一 doomed：本场景 LEAD_LOCK 生效（注≤1000）
check("规则2:领先2500深投入受LEAD_LOCK限(≤1000非allin)",
      a.get("act") != "allin" and (a.get("act") != "raise" or a["num"] <= 1000), str(a))

# 9) 盈利≤0 → 规则2 本身不触发；但本局为生死局（深投入+AKs 顶对）→
#    由 MUST-WIN 无条件全下接管（新规则 2026-08-23）
st9 = parse_request(req(my_chips=16000, my_cards=[48, 44],
                        total_win_chips=[0, 0],
                        public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st9, OpponentModel())
# MUST-WIN 已删：盈利0 非 doomed → 正常决策（受 2000 封顶）
check("规则2:不盈利不再MUST-WIN全下", a.get("act") != "allin", str(a))

# ================= 规则3：下注额限制 =================
print("===== 规则3 =====")
# 10) 非生死局 pot>2000（已投1500×2）非超强牌（顶对K）→ 放弃主动下注（check）。
#     用剩 65 手把 MUST-WIN 隔离掉（2×投入后 6900 < 2.5×100×64=16000）→ 规则3 生效
st10 = parse_request(req(my_chips=18500, my_cards=[46, 13],
                         total_win_chips=[0, 0], hand=5,
                         public_cards=[44, 38, 30],
                         history=[{"round": 0, "player_id": 0, "action": 1500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st10, OpponentModel())
check("规则3:pot>2000非超强牌只过牌/跟注",
      a.get("act") in ("check", "call"), str(a))

# 10b) 生死局 pot>2000（已投2500×2,剩30手）+ 顶对K（eq≈0.69 明显占优）→
#      MUST-WIN 覆盖规则3：无条件全下（用户规则 2026-08-23）
st10b = parse_request(req(my_chips=15000, my_cards=[46, 13],
                          total_win_chips=[0, 0],
                          public_cards=[44, 38, 30],
                          history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                   {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                   {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st10b, OpponentModel())
# MUST-WIN 已删：非 doomed → 规则3/2000 封顶正常生效
check("规则3:非doomed不再MUST-WIN全下", a.get("act") != "allin", str(a))

# 11) pot≤2000 触发降级 → 总注额 ≤ 1000
st11 = parse_request(req(my_chips=19200, my_cards=[46, 13],
                         total_win_chips=[0, 0],
                         public_cards=[44, 38, 30],
                         history=[{"round": 0, "player_id": 0, "action": 800, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st11, OpponentModel())
check("规则3:pot≤2000降级总注额≤1000",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# 12) 超强牌豁免：AA 在 pot>2000 时不受规则3 限制（强牌可下注/全下）
st12 = parse_request(req(my_chips=15000, my_cards=[48, 50],
                         total_win_chips=[0, 0],
                         public_cards=[44, 38, 30],
                         history=[{"round": 0, "player_id": 0, "action": 2500, "action_type": "raise"},
                                  {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                                  {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}]))
a = decide(st12, OpponentModel())
check("规则3:AA超强牌豁免仍可下注", a.get("act") in ("raise", "allin"), str(a))

# 13) 单元：超强牌识别（hole 为内部编码：点数 = c//4，A=14/K=13/Q=12/J=11/T=10）
check("规则3:AA超强", _is_super_hand([56, 58]) is True, "")
check("规则3:KK超强", _is_super_hand([52, 54]) is True, "")
check("规则3:JJ超强", _is_super_hand([44, 46]) is True, "")
check("规则3:AKs超强", _is_super_hand([56, 52]) is True, "")
check("规则3:AKo次强非超强(2026-08-23)", _is_super_hand([56, 53]) is False and _is_sub_strong([56, 53]) is True, "")
check("规则3:AQo次强非超强(2026-08-23)", _is_super_hand([56, 49]) is False and _is_sub_strong([56, 49]) is True, "")
check("规则3:KQo次强非超强(2026-08-23)", _is_super_hand([52, 49]) is False and _is_sub_strong([52, 49]) is True, "")
check("规则3:TT非超强", _is_super_hand([40, 42]) is False, "")

# ================= 规则4：大于三条的牌型不能仅由公共牌组成 =================
print("\n===== 规则4：公共牌拼强牌型净化 =====")
from strategy import _effective_category  # noqa: E402
from evaluator import STRAIGHT, FLUSH, FOUR_OF_A_KIND, HIGH_CARD  # noqa: E402


def river_req(**kw):
    """河牌完整过牌到底的 request 基础（my_id=0，对手=1；默认 public_cards=9♠8♦7♥6♣5♠）。"""
    base = {"my_cards": [56, 55], "my_chips": 19500,
            "public_cards": [36, 33, 30, 27, 20],
            "history": [
                {"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}]}
    base.update(kw)
    return base


# 4-1) 单元：board 彩虹顺子 9 8 7 6 5 + 手里 A♠K♣（未用到手牌）→ 降级高牌
st = parse_request(river_req())
check("规则4:board顺子+AK无增强→降级高牌",
      _effective_category(st) == HIGH_CARD,
      "cat=%s" % _effective_category(st))

# 4-2) 对照：同 board + 手里 T♦（升级成 T 高顺子）→ 真顺子保留
st = parse_request(river_req(my_cards=[42, 55]))
check("规则4:board顺子+手里T→真顺子保留",
      _effective_category(st) == STRAIGHT,
      "cat=%s" % _effective_category(st))

# 4-3) 单元：board 同花 A♠9♠7♠4♠2♠ + 手里 K♣Q♦（无黑桃）→ 降级高牌
st = parse_request(river_req(public_cards=[56, 36, 28, 16, 8], my_cards=[55, 50]))
check("规则4:board同花+无同花手牌→降级高牌",
      _effective_category(st) == HIGH_CARD,
      "cat=%s" % _effective_category(st))

# 4-4) 对照：同 board + 手里 K♠（补成 K 高同花）→ 真同花保留
st = parse_request(river_req(public_cards=[56, 36, 28, 16, 8], my_cards=[52, 55]))
check("规则4:board同花+手里K♠→真同花保留",
      _effective_category(st) == FLUSH,
      "cat=%s" % _effective_category(st))

# 4-5) 单元：board 葫芦 T♥T♦T♣9♠9♣ + 手里 7♣2♦（未用到手牌）→ 降级高牌
st = parse_request(river_req(public_cards=[41, 42, 43, 36, 39], my_cards=[31, 10]))
check("规则4:board葫芦+无升级手牌→降级高牌",
      _effective_category(st) == HIGH_CARD,
      "cat=%s" % _effective_category(st))

# 4-6) 对照：同 board + 手里 T♠（补成四条 T）→ 真四条保留
st = parse_request(river_req(public_cards=[41, 42, 43, 36, 39], my_cards=[40, 10]))
check("规则4:board葫芦+手里T→真四条保留",
      _effective_category(st) == FOUR_OF_A_KIND,
      "cat=%s" % _effective_category(st))


def allin_river_req(**kw):
    """河牌对手全下的 request（翻前双方 3000，河牌对手 allin；默认 board 葫芦）。"""
    base = {"my_id": 0, "my_chips": 16000, "my_cards": [31, 10], "hand": 40,
            "max_hand": 70, "total_win_chips": [0, 0], "total_win_games": [0, 0],
            "public_cards": [41, 42, 43, 36, 39],
            "history": [
                {"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"},
                {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                {"round": 3, "player_id": 1, "action": -2, "action_type": "allin"}]}
    base.update(kw)
    return base


# 4-7) 行为：河牌公对（board 葫芦）+ 对手全下 + 手里 72 → 弃牌
#      （假葫芦不再豁免公对陷阱：对手有 T 即四条，有 9 即同款葫芦平局）
st = parse_request(allin_river_req())
a = decide(st, OpponentModel())
check("规则4:board葫芦+72 对手全下→弃牌", a == {"act": "fold"}, str(a))

# 4-8) 对照：同 board + 手里 T♠（真四条）→ 不弃
st = parse_request(allin_river_req(my_cards=[40, 10]))
a = decide(st, OpponentModel())
check("规则4:board葫芦+手里T 对手全下→不弃",
      a.get("act") in ("call", "raise", "allin"), str(a))

# 4-9) 单元：board 三条 K♥K♦K♣9♠7♣ + 手里 7♦2♦（未用手牌）→ 降级高牌
#      （2026-08-23 严格化：纯公共牌组成的牌型含三条也降级）
st = parse_request(river_req(public_cards=[53, 54, 55, 36, 31], my_cards=[10, 15]))
check("规则4:board三条+无升级手牌→降级高牌",
      _effective_category(st) == HIGH_CARD,
      "cat=%s" % _effective_category(st))

# 4-10) 对照：同 board + 手里 K♠（补成四条 K）→ 真四条保留
st = parse_request(river_req(public_cards=[53, 54, 55, 36, 31], my_cards=[52, 10]))
check("规则4:board三条+手里K→真四条保留",
      _effective_category(st) == FOUR_OF_A_KIND,
      "cat=%s" % _effective_category(st))

# 4-11) 行为：river 对手下注 1500，board 三条 K + 手里 72（假三条降级）→
#       不投入超过 2000（call/fold/raise≤2000）
st = parse_request(allin_river_req(
    public_cards=[53, 54, 55, 36, 31], my_cards=[10, 15],
    history=[{"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 3, "player_id": 1, "action": 1500, "action_type": "raise"}]))
a = decide(st, OpponentModel())
check("规则4:board三条+72 面对1500不超2000",
      a.get("act") in ("call", "fold") or
      (a.get("act") == "raise" and a["num"] <= 2000), str(a))

# 4-12) 对照：同 board + 手里 K♠（真四条）→ 可大注/全下
st = parse_request(allin_river_req(
    public_cards=[53, 54, 55, 36, 31], my_cards=[52, 10],
    history=[{"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 3, "player_id": 1, "action": 1500, "action_type": "raise"}]))
a = decide(st, OpponentModel())
check("规则4:board三条+手里K 面对1500可大注",
      a.get("act") in ("raise", "allin"), str(a))

# 4-13) 单元：>2000 限制豁免集 = steal/doomed/有效牌型≥三条
#      （2026-08-24 恢复 steal 豁免：强制下注防锁赢为第二优先级，高于 >2000 限制）
import strategy as _S  # noqa: E402
from strategy import _allin_high_bet_allowed  # noqa: E402
_S._CTX = locking_ctx()                     # 对手锁胜 → _match_adjust 返回 steal
st = parse_request(allin_river_req(public_cards=[53, 54, 55, 36, 31], my_cards=[10, 15]))
check("规则4:steal档弱牌豁免allin>2000(第二优先级)",
      _allin_high_bet_allowed(st) is True,
      "allowed=%s" % _allin_high_bet_allowed(st))
# 对照：doomed（防锁赢 allin）仍豁免——需普通 ctx（非锁胜档）
_S._CTX = None
st = parse_request(allin_river_req(total_win_chips=[-5000, 5000],
                                   public_cards=[53, 54, 55, 36, 31], my_cards=[10, 15]))
check("规则4:doomed仍豁免allin>2000",
      _allin_high_bet_allowed(st) is True,
      "allowed=%s" % _allin_high_bet_allowed(st))
_S._CTX = None

# 4-14) 行为：steal（强制下注防锁赢）第二优先级——对手锁胜预警 + 我大幅领先
#       本可锁胜弃牌（fold_out: lead 16000 > 7500），但 steal 优先 → 强制开池
st = parse_request(req(my_id=0, my_chips=19950, my_cards=[23, 2], hand=45, max_hand=70,
                       total_win_chips=[8000, -8000], total_win_games=[40, 5]))
a = decide(st, OpponentModel(), locking_ctx())
check("规则4:steal第二优先级覆盖锁胜弃牌(强制下注)",
      a == {"act": "raise", "num": 250}, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
