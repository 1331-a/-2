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


# ============ A. 翻牌前总注额上限（非超强牌 ≤1000，超强牌豁免） ============
# A1) BB 位 KQo 面对按钮 raise 400 → 3-bet → 总注额 ≤ 1000
r = req(my_id=1, my_chips=19500, my_cards=[46, 30],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:非超强牌KQo 3-bet≤1000",
      a.get("act") == "raise" and a["num"] <= 1000, str(a))

# A2) BB 位 AA 面对 raise 400 → 3-bet → 超强牌豁免可超 1000
r = req(my_id=1, my_chips=19500, my_cards=[48, 50],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:AA 超强牌豁免>1000",
      a.get("act") == "raise" and a["num"] > 1000, str(a))

# A3) BB 位 AKs 面对 raise 400 → 3-bet → 超强牌豁免
r = req(my_id=1, my_chips=19500, my_cards=[48, 44],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:AKs 超强牌豁免>1000",
      a.get("act") == "raise" and a["num"] > 1000, str(a))

# A4) BB 位 KQo 面对 raise 2000（最小加注>1000）→ 无法合法加注 → 降级 call
r = req(my_id=1, my_chips=19000, my_cards=[46, 30],
        history=[{"round": 0, "player_id": 0, "action": 2000, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("翻前上限:非超强牌面对超大反加降级call",
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

# C3) 翻前不受牌型门槛约束：AKs 4-bet 2600 保持（超强牌翻前豁免）
r = req(my_chips=18700, my_cards=[48, 44],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 1200, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("牌型门槛:翻前AKs 4-bet保持>2000",
      a.get("act") == "raise" and a["num"] > 2000, str(a))

# ============ D. 超强牌扩展（AQ/AK/KQ）============
from strategy import _is_super_hand   # noqa: E402


def _I(n):
    return n + 8   # 平台牌号 → 内部编码


check("超强牌:AKo是", _is_super_hand([_I(48), _I(45)]) is True, "")
check("超强牌:AQo是", _is_super_hand([_I(48), _I(41)]) is True, "")
check("超强牌:KQo是", _is_super_hand([_I(44), _I(41)]) is True, "")
check("超强牌:AJo不是", _is_super_hand([_I(48), _I(37)]) is False, "")
check("超强牌:KJo不是", _is_super_hand([_I(44), _I(37)]) is False, "")

# D6) AKo（超强牌）翻前 3-bet 可超 1000（豁免）
r = req(my_id=1, my_chips=19500, my_cards=[48, 45],
        history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
a = decide(parse_request(r), OpponentModel())
check("超强牌:AKo 3-bet豁免>1000",
      a.get("act") == "raise" and a["num"] > 1000, str(a))

# ============ E. 弃牌亏损线：弃牌致累计亏损超 -3000 → 无条件 allin ============
# E1) pnl=-2000 + 已投1500 → 弃牌后-3500 < -3000 → 72o 也 allin
r = req(my_cards=[23, 2], my_chips=18500, total_win_chips=[-2000, 2000])
a = decide(parse_request(r), OpponentModel())
check("弃牌亏损线:弃牌-3500→无条件allin", a == {"act": "allin"}, str(a))

# E2) pnl=-5000 + 已投500 → 弃牌后-5500 → allin
r = req(my_cards=[23, 2], my_chips=19500, total_win_chips=[-5000, 5000])
a = decide(parse_request(r), OpponentModel())
check("弃牌亏损线:弃牌-5500→allin", a == {"act": "allin"}, str(a))

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
check("弃牌亏损线:翻后弱牌面对全下allin", a == {"act": "allin"}, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
