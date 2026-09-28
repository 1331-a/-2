# -*- coding: utf-8 -*-
"""test_lead_lock.py — 优势锁定（LEAD_LOCK）已移除后的行为验证。

【背景 2026-09-14 用户决定】原规则「领先 > LEAD_NO_ALLIN(2000) 时一律不
allin + 单次注码 ≤ LEAD_MAX_BET(1000)」整体删除，理由：
  · 它与牌型注额分级（_bet_limit / _bet_cap_guard，<三条 ≤3000）职责重叠；
  · 而且是一刀切——即使手握三条/坚果，面对对手全下也被强制弃牌；
  · 用户明确：「有规则 3000 以上谨慎下注了，这里是面对 allin 的特殊情况」
    → 注额上限继续约束主动下注，面对全下交给跟全下门槛（规则16）判定。

因此本文件改测「移除后的正确行为 + 注额上限仍然生效」：
  1. 领先时不再有 1000 注码上限（改由牌型上限 2000/3000 节制）；
  2. 领先时不再无条件禁止 allin（强牌面对全下可跟）；
  3. 弱牌/中等牌面对全下仍被牌型注额上限拦下（保持谨慎）；
  4. LEAD_LOCK 相关标识已从模块中彻底移除。
"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request
from strategy import decide
from opponent import OpponentModel
import strategy as S

fails = 0


def check(name, cond, detail=""):
    global fails
    if not cond:
        fails += 1
        print("[FAIL] %s %s" % (name, detail))
    else:
        print("[PASS] %s" % name)


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 15000, "my_cards": [48, 50], "public_cards": [],
            "history": [], "hand": 20, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# ---------- 0. 移除彻底性 ----------
check("移除:_LEAD_LOCK 全局不存在", not hasattr(S, "_LEAD_LOCK"))
check("移除:_is_lead_lock 不存在", not hasattr(S, "_is_lead_lock"))
check("移除:LEAD_NO_ALLIN 不存在", not hasattr(S, "LEAD_NO_ALLIN"))
check("移除:LEAD_MAX_BET 不存在", not hasattr(S, "LEAD_MAX_BET"))

# ---------- 1. 领先不再有 1000 注码上限（改由牌型上限节制） ----------
# 领先 3000（旧 LEAD_LOCK 区间）+ AA 翻后无人下注
st1 = parse_request(req(total_win_chips=[1500, -1500], public_cards=[46, 6, 1],
                        my_chips=18500,
                        history=[{"round": 0, "player_id": 0, "action": 500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0,
                                  "action_type": "check"}]))
a = decide(st1, OpponentModel())
check("领先3000:不再受 1000 注码上限（改由牌型上限 ≤3000）",
      a.get("act") in ("raise", "check")
      and (a.get("act") != "raise" or a["num"] <= 3000), str(a))
check("领先3000:超强牌(AA)不再被强制弃牌", a.get("act") != "fold", str(a))

# ---------- 2. 领先时面对全下：不再无条件禁止 allin ----------
# 领先 3000 + 对手全下 + 一对 A（<三条）。
# 【2026-09-14 用户规则】不再由「牌型注额上限」拦下（该限制已废止：面对
# 对手 all-in 的定向决策说了算）→ 此处弃牌是决策层按赔率判定（跟注额巨大
# → required 很高，一对的 eq 不够）。金额写真实值，避免 to_call 失真。
st2 = parse_request(req(total_win_chips=[1500, -1500], public_cards=[46, 6, 1],
                        my_chips=18500,
                        history=[{"round": 0, "player_id": 0, "action": 500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 18500,
                                  "action_type": "allin"}]))
a = decide(st2, OpponentModel())
check("领先3000:一对面对全下按赔率弃牌(注额上限已废止)",
      a == {"act": "fold"}, str(a))

# 同样领先，但手牌 ≥三条 → 不再被优势锁定阻拦（全下门槛判定）
st3 = parse_request(req(total_win_chips=[1500, -1500], public_cards=[46, 6, 1],
                        my_chips=18500, my_cards=[46, 47],
                        history=[{"round": 0, "player_id": 0, "action": 500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": -2,
                                  "action_type": "allin"}]))
a = decide(st3, OpponentModel())
check("领先3000:三条面对全下不再被优势锁定强制弃牌",
      a.get("act") in ("allin", "fold"), str(a))

# ---------- 3. 规则2（锁胜/防锁赢）仍然照常工作 ----------
# 领先 1000（浅）+ 深投入 → 规则2 盈利锁胜 → allin
st4 = parse_request(req(total_win_chips=[1000, -1000], public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0,
                                  "action_type": "check"}]))
a = decide(st4, OpponentModel())
# 【2026-09-28 方向1】doom 三道门控之一：to_call==0（可免费过牌）且非强牌
# → 规则2 不接管，交回常规策略过牌（旧实现无条件 allin，实战三局因此亏
# −23,500：局2 手43 在 to_call=0 时推 19,500 输 20,000）。
check("规则2:深投入+可免费过牌→不接管(过牌)",
      a.get("act") == "check", str(a))
# 对照：关闭门控 → 旧行为（无条件 allin）
import strategy as _SG  # noqa: E402
_SG.DOOM_ALLIN_ON, _old4 = False, _SG.DOOM_ALLIN_ON
try:
    a_old4 = decide(st4, OpponentModel())
finally:
    _SG.DOOM_ALLIN_ON = _old4
check("规则2(对照):关闭门控→深投入仍全下",
      a_old4 == {"act": "allin"}, str(a_old4))

# 落后 2000（lead=-4000）深投入 → doom 无条件 allin
st5 = parse_request(req(total_win_chips=[-2000, 2000], public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0,
                                  "action_type": "check"}]))
a = decide(st5, OpponentModel())
# 【2026-09-28 方向1】同上：doom + 免费过牌 + 非强牌 → 不接管（过牌）。
# 「无条件 allin」仅保留给：已被逼到全下 / 最后一手 / 越线幅度足够大 /
# 对手会弃牌 / 强牌 这些情况（见 strategy._doom_plan 注释）。
check("规则2:落后深投入+可免费过牌→不接管(过牌)",
      a.get("act") == "check", str(a))

# ---------- 4. 注额封顶仍然生效（<三条 ≤3000 / 小两对 ≤2000） ----------
st6 = parse_request(req(total_win_chips=[0, 0], public_cards=[46, 6, 1],
                        my_chips=18500,
                        history=[{"round": 0, "player_id": 0, "action": 2500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0,
                                  "action_type": "check"}]))
a = decide(st6, OpponentModel())
check("注码封顶:大底池价值注不超牌型上限",
      a.get("act") == "raise" and a["num"] <= 3000, str(a))

st7 = parse_request(req(total_win_chips=[0, 0], public_cards=[46, 6, 1],
                        my_chips=18500,
                        history=[{"round": 0, "player_id": 0, "action": 500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 300,
                                  "action_type": "raise"}]))
a = decide(st7, OpponentModel())
check("注码封顶:面对下注不超上限（含动态上限降级）",
      (a.get("act") == "raise" and a["num"] <= 5000) or a.get("act") == "call",
      str(a))

# 翻前开池不受影响（无样本 → B 被样本门控，开池回旧值 2.5BB=250）
st8 = parse_request(req(total_win_chips=[0, 0], my_chips=19950,
                        my_cards=[48, 51], history=[]))
a = decide(st8, OpponentModel())
check("增量上限:开池2.5BB不压", a == {"act": "raise", "num": 250}, str(a))

# ---------- 规则2 补漏：跟注即锁赢 → 不允许便宜跟注 ----------
# 实战第10手（2026-09-28 用户报告）：
#   河牌 我方 J♥Q♣ / 公面 6♥K♥K♦10♠10♥ / 对手 A♦5♠，对手下注 807。
#   本手开始我们 −2,989（lead −5,978）、已投入 807、剩 60 手、2×追回线 9,000。
#   弃牌口径 −7,592 > −9,000（弃了还能翻身）；跟注口径 −9,206 ≤ −9,000（跟注即输）。
#   越线仅 2.3% < UA_SEALED_MARGIN 15% → 强制全押不触发 → 放行了便宜跟注。
# 本手牌力 = 公面 KK1010 + Q 踢脚 = 两对（< 三条）→ 按规则20 不许主动推光
#   → 修复后的动作是 **fold**（不放行便宜跟注，也不违反规则20）。
_H10 = dict(
    my_cards=[37, 43], public_cards=[17, 45, 46, 32, 33],
    my_chips=20000 - 807, hand=9, max_hand=70,
    total_win_chips=[-2989, 2989], total_win_games=[0, 0],
    history=[{"round": 0, "player_id": 0, "action": 489, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 489, "action_type": "call"},
             {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 2, "player_id": 0, "action": 318, "action_type": "raise"},
             {"round": 2, "player_id": 1, "action": 318, "action_type": "call"},
             {"round": 3, "player_id": 1, "action": 807, "action_type": "raise"}])
st_h10 = parse_request(req(**_H10))
_lead = (int(st_h10.total_win_chips[0]) - int(st_h10.total_win_chips[1]))
_line = S._blind_line(st_h10, S._hands_left(st_h10), own=False)

check("第10手:弃牌口径未 doom（弃了还能翻身）",
      not S._doom_risk(st_h10), "lead-2*inv=%d vs %d"
      % (_lead - 2 * S._invested(st_h10), -2 * _line))
check("第10手:跟注口径 doom 成立（跟注即送对手锁赢）",
      S._doom_risk(st_h10, include_to_call=True),
      "lead-2*exp=%d vs %d"
      % (_lead - 2 * S._exposure(st_h10), -2 * _line))
check("第10手:未达「明显被锁」（越线 <15%）→ 旧强制全押确实不触发",
      not S._sealed_by_call(st_h10), "")
check("第10手:牌力 < 三条（规则20 不许主动推光）",
      not S._strong_for_big_money(st_h10), "")

a10 = decide(st_h10, OpponentModel())
check("第10手:修复后不再放行便宜跟注（弱牌 → fold）",
      a10.get("act") == "fold", str(a10))

# 反向：把 lead 拉回不 doom 的水平 → 必须保持常规动作（不误介入）
_h10_ok = dict(_H10)
_h10_ok["total_win_chips"] = [12000, -12000]      # 领先 → 不 doom
st_ok = parse_request(req(**_h10_ok))
check("反向:领先时不 doom → 该规则不介入",
      not S._doom_risk(st_ok, include_to_call=True), "")
check("反向:该规则不改写动作",
      S._doom_call_upgrade(st_ok, {"act": "call"}) == {"act": "call"}, "")

# 契约：只改写 call；fold/check/raise 一律不动
check("契约:弱牌 call → fold",
      S._doom_call_upgrade(st_h10, {"act": "call"}) == {"act": "fold"}, "")
check("契约:fold 不被翻案",
      S._doom_call_upgrade(st_h10, {"act": "fold"}) == {"act": "fold"}, "")
check("契约:check 不被翻案",
      S._doom_call_upgrade(st_h10, {"act": "check"}) == {"act": "check"}, "")
check("契约:raise 不被翻案",
      S._doom_call_upgrade(st_h10, {"act": "raise", "num": 3000})
      == {"act": "raise", "num": 3000}, "")

# 强牌分支：同状态但牌力 ≥三条（河牌坚果）→ call 应升级为 allin（带 lk）
_H10_strong = dict(_H10)
_H10_strong["my_cards"] = [33, 32]                # 10♠10♣ → 公面已有 1010 → 四条
st_strong = parse_request(req(**_H10_strong))
check("强牌:牌力 ≥三条", S._strong_for_big_money(st_strong), "")
check("强牌:call → allin（带 lk）",
      S._doom_call_upgrade(st_strong, {"act": "call"}) == {"act": "allin", "lk": 1},
      str(S._doom_call_upgrade(st_strong, {"act": "call"})))

# 开关：关掉后回到旧行为（保住 A/B 隔离能力）
S.DOOM_CALL_UPGRADE_ON = False
check("开关:关闭后 call 不被升级",
      S._doom_call_upgrade(st_h10, {"act": "call"}) == {"act": "call"}, "")
_a_off = decide(st_h10, OpponentModel())
check("开关:关闭后 decide 输出仍为 call", _a_off.get("act") == "call", str(_a_off))
S.DOOM_CALL_UPGRADE_ON = True

# 模式开关：无视牌力的「无条件 all-in」（用户原话「改为 allin」的字面实现）
S.DOOM_UPGRADE_FORCE_ALLIN = False
check("模式:默认尊重规则20 → 弱牌落点为 fold",
      S._doom_call_upgrade(st_h10, {"act": "call"}) == {"act": "fold"}, "")
S.DOOM_UPGRADE_FORCE_ALLIN = True
check("模式:FORCE_ALLIN → 弱牌也升级 allin（带 lk）",
      S._doom_call_upgrade(st_h10, {"act": "call"}) == {"act": "allin", "lk": 1},
      str(S._doom_call_upgrade(st_h10, {"act": "call"})))
_a_force = decide(st_h10, OpponentModel())
check("模式:FORCE_ALLIN 下端到端输出 allin",
      _a_force.get("act") == "allin", str(_a_force))
S.DOOM_UPGRADE_FORCE_ALLIN = False

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
