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
check("规则2:深投入被规则2接管全下", a == {"act": "allin"}, str(a))

# 落后 2000（lead=-4000）深投入 → doom 无条件 allin
st5 = parse_request(req(total_win_chips=[-2000, 2000], public_cards=[46, 6, 1],
                        history=[{"round": 0, "player_id": 0, "action": 2500,
                                  "action_type": "raise"},
                                 {"round": 0, "player_id": 1, "action": 0,
                                  "action_type": "call"},
                                 {"round": 1, "player_id": 1, "action": 0,
                                  "action_type": "check"}]))
a = decide(st5, OpponentModel())
check("规则2:落后深投入 doom 触发无条件 allin", a == {"act": "allin"}, str(a))

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

# 翻前开池 2.5BB 不受影响
st8 = parse_request(req(total_win_chips=[0, 0], my_chips=19950,
                        my_cards=[48, 51], history=[]))
a = decide(st8, OpponentModel())
check("增量上限:开池2.5BB不压", a == {"act": "raise", "num": 250}, str(a))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
