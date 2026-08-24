# -*- coding: utf-8 -*-
"""专项测试：翻牌前总注额上限 + 前几步强牌小注钓鱼（用户规则，2026-08-22）"""
import sys
sys.path.insert(0, '.')

from game_state import parse_request
from opponent import OpponentModel
from strategy import decide

fails = 0


def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1
        print("FAIL: %s  %s" % (name, info))


def req(**kw):
    base = {'num_players': 2, 'dealer_id': 0, 'my_id': 0, 'my_chips': 19950,
            'my_cards': [48, 44], 'public_cards': [], 'history': [],
            'hand': 10, 'max_hand': 70,
            'total_win_chips': [0, 0], 'total_win_games': [0, 0]}
    base.update(kw)
    return base


# ============ A. 翻牌前总注额上限（2026-08-24：所有手牌 ≤1000） ============
# A1) BB 位 KQo 面对按钮 raise 400 → 3-bet → 总注额 ≤ 1000
r = req(my_id=1, my_chips=19500, my_cards=[46, 30],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:非超强牌KQo 3-bet≤1000",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# A2) BB 位 AA 面对 raise 400 → 3-bet → 超强牌也 ≤1000（用户新规：翻前投入≤1000）
r = req(my_id=1, my_chips=19500, my_cards=[48, 50],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:AA 也≤1000(2026-08-24)",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# A3) BB 位 AKs 面对 raise 400 → 3-bet → 也 ≤1000
r = req(my_id=1, my_chips=19500, my_cards=[48, 44],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:AKs 也≤1000(2026-08-24)",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# A4) BB 位 KQo 面对 raise 2000（最小加注>1000）→ 无法合法加注 → 降级 call/fold
r = req(my_id=1, my_chips=19000, my_cards=[46, 30],
        history=[{"round": 0, "player_id": 0, "action": 2000, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:非超强牌面对超大反加降级call/fold",
      a.get("act") in ("call", "fold"), str(a))

# A5) 开池 2.5BB（250 ≤ 1000）不受影响：中等牌 A9o 开池正常
r = req(my_cards=[48, 21], history=[])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:正常开池不受影响",
      a.get("act") == "raise" and a["num"] == 250, str(a))

# ============ B. 前几步（翻牌/转牌）强牌小注钓鱼 ============
pf = [{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
      {"round": 0, "player_id": 1, "action": 0, "action_type": "call"}]

# B1) 翻牌顶对 K（good 级）→ 小注钓鱼（≤0.55 池，pot=1000）
r = req(my_chips=19500, my_cards=[46, 13], public_cards=[44, 38, 30],
        history=pf + [{"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
st = parse_request(r)
a = decide(st, OpponentModel())
check("前几步钓鱼:flop顶对小注(≤0.55池)",
      a.get("act") == "raise" and a["num"] <= 0.55 * st.pot + 1, str(a))

# B2) 转牌两对（strong 级）→ 小注钓鱼
r = req(my_chips=19000, my_cards=[42, 13], public_cards=[43, 22, 29, 20],
        history=pf + [{"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                      {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                      {"round": 2, "player_id": 1, "action": 0, "action_type": "check"}])
st = parse_request(r)
a = decide(st, OpponentModel())
check("前几步钓鱼:turn两对小注(≤0.55池)",
      a.get("act") == "raise" and a["num"] <= 0.55 * st.pot + 1, str(a))

# B3) 河牌顶对 → 恢复正常价值注（≥0.5 池，不再小注钓）
cc = [{"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
      {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
      {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
      {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
      {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}]
r = req(my_chips=19500, my_cards=[46, 13], public_cards=[44, 30, 20, 12, 6],
        history=pf + cc)
st = parse_request(r)
a = decide(st, OpponentModel())
check("前几步钓鱼:river顶对恢复正常注(≥0.5池)",
      a.get("act") in ("raise", "check") and
      (a.get("act") == "check" or a["num"] >= 0.5 * st.pot), str(a))

# ============ C. 翻后大注牌型门槛：只有牌型≥三条才能下注超过2000 ============
deep_pf = [{"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"},
           {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
           {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
           {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
           {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
           {"round": 2, "player_id": 0, "action": 0, "action_type": "check"}]

# C1) river 对手下注 1500，我顺子级（≥三条）→ 允许大注/全下（绝不只是跟）
r = req(my_chips=17000, my_cards=[36, 32], public_cards=[44, 30, 29, 16, 12],
        history=deep_pf + [{"round": 3, "player_id": 1, "action": 1500, "action_type": "raise"}])
st = parse_request(r)
a = decide(st, OpponentModel())
check("牌型门槛:顺子面对1500可大注(raise/allin)",
      a.get("act") in ("raise", "allin"), str(a))

# C2) river 对手下注 1500，我两对（<三条）→ 绝不 raise 超 2000（call/弃）
r = req(my_chips=17000, my_cards=[42, 13], public_cards=[43, 22, 29, 16, 12],
        history=deep_pf + [{"round": 3, "player_id": 1, "action": 1500, "action_type": "raise"}])
st = parse_request(r)
a = decide(st, OpponentModel())
check("牌型门槛:两对面对1500不超限(call/fold)",
      a.get("act") in ("call", "fold") or
      (a.get("act") == "raise" and a["num"] <= 2000), str(a))

# C3) 翻前 2000 封顶（用户规则：每次下注≤2000，翻前无牌面例外）：
# AKs 4-bet 2760 → 压到 2000；若最小加注已超 2000 → 降级跟注
r = req(my_chips=19600, my_cards=[48, 44],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 1200, "action_type": "raise"}])
st = parse_request(r)
a = decide(st, OpponentModel())
check("翻前2000封顶:AKs 4-bet≤2000或降级",
      (a.get("act") == "call") or
      (a.get("act") == "raise" and a["num"] <= 2000), str(a))

# ============ D. 超强牌扩展（AQ/AK/KQ）============
from strategy import _is_super_hand, _is_sub_strong   # noqa: E402


def _I(n):
    return n + 8   # 平台牌号 → 内部编码


check("超强牌:AKo是次强非超强", _is_super_hand([_I(48), _I(45)]) is False and _is_sub_strong([_I(48), _I(45)]) is True, "")
check("超强牌:AQo是次强非超强", _is_super_hand([_I(48), _I(41)]) is False and _is_sub_strong([_I(48), _I(41)]) is True, "")
check("超强牌:KQo是次强非超强", _is_super_hand([_I(44), _I(41)]) is False and _is_sub_strong([_I(44), _I(41)]) is True, "")
check("超强牌:AJo不是", _is_super_hand([_I(48), _I(37)]) is False, "")
check("超强牌:KJo不是", _is_super_hand([_I(44), _I(37)]) is False, "")

# D6) AKo（超强牌）翻前 3-bet 可超 1000（豁免）
r = req(my_id=1, my_chips=19500, my_cards=[48, 45],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("超强牌:AKo次强正常档3-bet≤1000",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# ============ E. 弃牌亏损线：弃牌致累计亏损超 -3000 → 无条件 allin ============
# E1) pnl=-2000 + 已投1500 → 弃牌后-3500 < -3000 → 72o 也 allin
r = req(my_cards=[23, 2], my_chips=18500, total_win_chips=[-2000, 2000])
a = decide(parse_request(r), OpponentModel())
# 【2026-08-23】despair 已删除统一 doomed：该场景（pnl=-2000 未到 doomed）
# 弃牌不再升级 allin
check("despair删除:弃牌-3500不再强制allin", a.get("act") != "allin", str(a))

# E2) pnl=-5000 + 已投500 → 弃牌后-5500 → allin
r = req(my_cards=[23, 2], my_chips=19500, total_win_chips=[-5000, 5000])
a = decide(parse_request(r), OpponentModel())
check("despair删除:弃牌-5500不再强制allin", a.get("act") != "allin", str(a))

# E3) 对照组：pnl=-1000 + 已投1500 → 弃牌后-2500 未超线 → 不触发（正常决策）
r = req(my_cards=[23, 2], my_chips=18500, total_win_chips=[-1000, 1000])
a = decide(parse_request(r), OpponentModel())
check("弃牌亏损线:弃牌-2500未超线不触发", a.get("act") != "allin", str(a))

# E4) 翻后触发：我方翻前投1500（pnl=-2000），对手flop全下 → 弃牌即-3500 → allin
r = req(my_id=0, my_cards=[23, 2], my_chips=18500, total_win_chips=[-2000, 2000],
        public_cards=[46, 22, 5],
        history=[{"round": 0, "player_id": 0, "action": 1500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}])
a = decide(parse_request(r), OpponentModel())
check("despair删除:翻后弱牌面对全下不再allin", a.get("act") != "allin", str(a))

# ============ F. allin 金额 ≤2000（仅翻后，用户反馈修复） ============
# F1) 翻后两对 + 对手全下 + 深筹码（非 despair）→ 跟全下超限 → 弃
r = req(my_cards=[42, 13], my_chips=19500, public_cards=[43, 22, 29, 20],
        history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 1, "player_id": 1, "action": -2, "action_type": "allin"}])
a = decide(parse_request(r), OpponentModel())
check("allin上限:两对跟全下超2000→弃", a == {"act": "fold"}, str(a))

# F2) 翻后顺子（牌面≥三条）→ 允许 allin
r = req(my_cards=[36, 32], my_chips=8000, public_cards=[44, 30, 29, 16, 12],
        history=[{"round": 0, "player_id": 0, "action": 6000, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                 {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                 {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
                 {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                 {"round": 3, "player_id": 1, "action": 0, "action_type": "check"}])
a = decide(parse_request(r), OpponentModel())
check("allin上限:顺子允许allin", a == {"act": "allin"}, str(a))

# F3) 翻前跟全下不受金额上限约束（翻前全下分档控制）——回归
r = req(my_id=0, my_chips=19500, my_cards=[32, 34],  # TT 均势面对翻前全下
        history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": -2, "action_type": "allin"}])
a = decide(parse_request(r), OpponentModel())
check("allin上限:翻前均势TT大额全下→弃(2026-08-24)",
      a == {"act": "fold"}, str(a))

# ============ G. 翻前投入 ≤1000（2026-08-24 新规，doomed 例外） ============
# G1) 翻前对手 raise 1500，我 AA（BB 已投 100）→ to_call=1400 > 1000 → 弃
#     （超强牌也不豁免翻前大额跟注；raise 降级 call 同样受约束）
r = req(my_id=1, my_chips=19900, my_cards=[48, 50],
        history=[{"round": 0, "player_id": 0, "action": 1500, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:AA面对1500跟注超限→弃", a == {"act": "fold"}, str(a))

# G2) 翻前 doomed（本局输即对手锁胜）→ 仍无条件 allin（第一优先级例外）
r = req(my_id=1, my_cards=[23, 2], hand=60, max_hand=70,
        total_win_chips=[5000, -5000],   # my_id=1 落后 10000
        history=[{"round": 0, "player_id": 0, "action": 3000, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:doomed仍可allin(防锁赢)", a == {"act": "allin"}, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
