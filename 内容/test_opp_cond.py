# -*- coding: utf-8 -*-
"""test_opp_cond.py — 【2026-09-25 用户规则】A/B 两个方案「按对手画像条件化」。

用户原话：
  「AB 应对的情况不同吧？B 适用于开局，A 主要是跟注计算，既然这样，应该把
    对手模型算入考量，比如对手如果一直硬跟就降低 B 的权重，A 主要考虑对手
    打法激进的情况」

对应两处实现：
  · B 条件化：`_open_size_bb` / `_open_weight` —— 用 eff_vpip 把开池尺寸在
    [OPEN_SIZE_HARD_CALL_BB(2.5) .. OPEN_SIZE_BB(3.5)] 之间插值；
    对手一直硬跟（VPIP 高）→ 回退 2.5（开大无弃牌权益，白送钱）。
  · A 条件化：`_future_aggr_factor(model)` —— 用 avg_bets_per_hand 把
    后续投入折算缩放到 [FUTURE_AGGR_MIN(0.15) .. 1.0]；
    被动对手（不连街开火）→ 折算≈0（不存在「被赶走」的付费链）。
"""
import sys

sys.path.insert(0, ".")

import strategy                                            # noqa: E402
from game_state import parse_request                      # noqa: E402
from opponent import OpponentModel                        # noqa: E402
from strategy import (decide, _open_size_bb, _open_weight,  # noqa: E402
                      _future_aggr_factor, _future_cost,
                      OPEN_SIZE_BB, OPEN_SIZE_HARD_CALL_BB,
                      OPEN_SAMPLE_HANDS, FUTURE_DRAW_IMPLIED_CAP,
                      BIG_BET_FOLD_MIN_AGGR)

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
            "my_chips": 19950, "my_cards": [48, 51], "public_cards": [],
            "history": [], "hand": 10, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


def m_caller(n=60):
    """一直硬跟型：翻前几乎不弃（VPIP → 1）。"""
    m = OpponentModel()
    m.preflop_call = n
    m.preflop_fold = 0
    m.preflop_raise = 0
    m.hands_seen = 999        # 样本充足（否则被 OPEN_SAMPLE_HANDS 门控压到 0）
    return m


def m_folder(n=60):
    """爱弃型：翻前几乎全弃（VPIP → 0）。"""
    m = OpponentModel()
    m.preflop_fold = n
    m.preflop_call = 0
    m.preflop_raise = 0
    m.hands_seen = 999
    return m


def m_passive(n=20):
    """被动型：几乎不主动下注（bets/hand → 0）。"""
    m = OpponentModel()
    m.hand_bet_counts = [0] * n
    return m


def m_aggro(n=20):
    """持续施压型：每手多次主动下注（bets/hand → 2+）。"""
    m = OpponentModel()
    m.hand_bet_counts = [2] * n
    return m


_mx = OpponentModel()      # 无样本（收缩到先验）

# ============================================================
#  一、B 条件化：开池尺寸随对手跟注倾向
# ============================================================
print("--- B 条件化：_open_weight / _open_size_bb ---")

check("无样本:w = 0（被样本门控压到 0，B 不生效）",
      _open_weight(_mx) == 0.0, "%.3f" % _open_weight(_mx))
check("硬跟型:w = 0（VPIP→1）",
      _open_weight(m_caller()) == 0.0, "%.3f" % _open_weight(m_caller()))
check("爱弃型:w = 1（VPIP→0）",
      _open_weight(m_folder()) == 1.0, "%.3f" % _open_weight(m_folder()))

check("尺寸·硬跟 → 下限 %.1fBB" % OPEN_SIZE_HARD_CALL_BB,
      abs(_open_size_bb(m_caller()) - OPEN_SIZE_HARD_CALL_BB) < 0.02,
      "%.3f" % _open_size_bb(m_caller()))
check("尺寸·爱弃 → 上限 %.1fBB" % OPEN_SIZE_BB,
      abs(_open_size_bb(m_folder()) - OPEN_SIZE_BB) < 0.02,
      "%.3f" % _open_size_bb(m_folder()))
check("尺寸单调：硬跟 < 爱弃",
      _open_size_bb(m_caller()) < _open_size_bb(m_folder()),
      "%.3f / %.3f" % (_open_size_bb(m_caller()), _open_size_bb(m_folder())))

# 【样本门控】样本不足 → B 不生效（w=0 → 回到旧尺寸 2.5）
check("样本门控·无样本 w = 0（B 不生效）",
      _open_weight(_mx) == 0.0, "%.3f" % _open_weight(_mx))
check("样本门控·无样本 尺寸 = 旧值 2.5BB",
      abs(_open_size_bb(_mx) - OPEN_SIZE_HARD_CALL_BB) < 0.02,
      "%.3f" % _open_size_bb(_mx))
_mid = m_folder()
_mid.hands_seen = OPEN_SAMPLE_HANDS // 2      # 样本半开
check("样本门控·样本半开 → w 减半",
      abs(_open_weight(_mid) - 0.5) < 0.02, "%.3f" % _open_weight(_mid))
_full = m_folder()
_full.hands_seen = OPEN_SAMPLE_HANDS * 3      # 样本充足
check("样本门控·样本充足 → w 不被门控（=1）",
      abs(_open_weight(_full) - 1.0) < 0.02, "%.3f" % _open_weight(_full))

# 学习尺寸同样被折减：pf_l 学到 4.5BB，硬跟型应回退到 B 前值 4.0
check("学习尺寸·硬跟 → 回退到 B 前的 4.0（pf_l）",
      abs(_open_size_bb(m_caller(), None, 4.5) - 4.0) < 0.02,
      "%.3f" % _open_size_bb(m_caller(), None, 4.5))
check("学习尺寸·爱弃 → 保持 4.5（pf_l）",
      abs(_open_size_bb(m_folder(), None, 4.5) - 4.5) < 0.02,
      "%.3f" % _open_size_bb(m_folder(), None, 4.5))
check("学习尺寸·无样本（门控）→ 回退到 B 前的 2.2（pf_s）",
      abs(_open_size_bb(_mx, None, 2.5) - 2.2) < 0.02,
      "%.3f" % _open_size_bb(_mx, None, 2.5))

# 端到端：同样的牌、同样位置，只换对手画像 → 开池尺寸不同
_hard = decide(parse_request(req()), m_caller())
_soft = decide(parse_request(req()), m_folder())
check("端到端·硬跟 → 开池 250", _hard == {"act": "raise", "num": 250}, str(_hard))
check("端到端·爱弃 → 开池 350", _soft == {"act": "raise", "num": 350}, str(_soft))

# ============================================================
#  二、A 条件化：future_cost 随对手是否继续开火
# ============================================================
print("\n--- A 条件化：_future_aggr_factor / _future_cost ---")

check("因子·被动 → FUTURE_AGGR_MIN",
      abs(_future_aggr_factor(m_passive()) - 0.15) < 0.01,
      "%.3f" % _future_aggr_factor(m_passive()))
check("因子·施压 → 1.0",
      abs(_future_aggr_factor(m_aggro()) - 1.0) < 0.01,
      "%.3f" % _future_aggr_factor(m_aggro()))
check("因子·无样本 → 0.36（bets/hand 先验 0.9）",
      abs(_future_aggr_factor(_mx) - 0.3625) < 0.01,
      "%.3f" % _future_aggr_factor(_mx))
check("因子单调：被动 < 无样本 < 施压",
      _future_aggr_factor(m_passive()) < _future_aggr_factor(_mx)
      < _future_aggr_factor(m_aggro()),
      "%.3f / %.3f / %.3f" % (_future_aggr_factor(m_passive()),
                              _future_aggr_factor(_mx),
                              _future_aggr_factor(m_aggro())))
check("因子·model=None → 1.0（缺数据不缩水，维持旧口径）",
      _future_aggr_factor(None) == 1.0, "%.3f" % _future_aggr_factor(None))

# 同一个翻牌跟注点：三个对手 → 折算额递增
st = parse_request(req(
    my_cards=[48, 51], public_cards=[20, 41, 24], my_chips=19420,
    history=[{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 280, "action_type": "raise"}]))
_tc = st.to_call
_fc_p = _future_cost(st, _tc, m_passive())[0]
_fc_m = _future_cost(st, _tc, _mx)[0]
_fc_a = _future_cost(st, _tc, m_aggro())[0]
print("    翻牌 to_call=%d  折算额：被动 %.0f / 无样本 %.0f / 施压 %.0f" %
      (_tc, _fc_p, _fc_m, _fc_a))
check("折算额·被动远小于施压（≈1/6）", _fc_p < _fc_a * 0.25,
      "%.0f vs %.0f" % (_fc_p, _fc_a))
check("折算额·施压 = 满额（与 model=None 旧口径一致）",
      abs(_fc_a - _future_cost(st, _tc, None)[0]) < 1.0,
      "%.0f vs %.0f" % (_fc_a, _future_cost(st, _tc, None)[0]))
check("折算额·model=None 不退化为 0",
      _future_cost(st, _tc, None)[0] > 0,
      "%.0f" % _future_cost(st, _tc, None)[0])

# ============================================================
#  三、A 扩展：听牌也计入后续投入（修正 future_cost / implied 的结构性互斥）
# ============================================================
# 背景：原实现里 future_cost 只在 `not big_draw` 时计入，而 implied 加成只给
# `big_draw` → 两者作用集合**不相交**，听牌这条最容易被赶走的链从未被 A 触及。
# 修正后：听牌也计入折算，并取消其隐含赔率加成（implied 压到 FUTURE_DRAW_IMPLIED_CAP）。
print("\n--- A 扩展：听牌（big_draw）的隐含赔率不再与折算互斥 ---")

# 同花+顺子听（outs=17）：手牌 2 红桃 + 公面 2 红桃，深筹码（>4×池）
_draw_req = dict(
    my_cards=[12, 16], public_cards=[20, 24, -6], my_chips=18200,
    history=[{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}])
_st_d = parse_request(_draw_req)

# 打开调试钩子读回内部量（eff_req / implied / fc 都是确定性的，不受 MC 噪声影响）
strategy.WB_FACE_DEBUG = True


def _face_rec(model):
    strategy.WB_FACE_LOG.clear()
    decide(_st_d, model)
    return strategy.WB_FACE_LOG[-1] if strategy.WB_FACE_LOG else None


_r_pas = _face_rec(m_passive())
_r_agg = _face_rec(m_aggro())
strategy.WB_FACE_DEBUG = False

if _r_pas is None or _r_agg is None:
    check("听牌扩展·能取到跟注点记录", False, "无 WB_FACE_LOG")
else:
    print("    听牌点 to_call=%d　被动 implied=%.2f eff_req=%.3f fc=%.0f"
          "　施压 implied=%.2f eff_req=%.3f fc=%.0f" % (
              _st_d.to_call, _r_pas["implied"], _r_pas["eff_req"], _r_pas["fc"],
              _r_agg["implied"], _r_agg["eff_req"], _r_agg["fc"]))
    check("听牌扩展·施压 → implied 压到上限 %.2f" % FUTURE_DRAW_IMPLIED_CAP,
          abs(_r_agg["implied"] - FUTURE_DRAW_IMPLIED_CAP) < 0.01,
          "%.2f" % _r_agg["implied"])
    check("听牌扩展·被动 → 保留隐含赔率加成（>1.0）",
          _r_pas["implied"] > 1.0, "%.2f" % _r_pas["implied"])
    check("听牌扩展·施压时听牌也计入折算（fc>0）",
          _r_agg["fc"] > 0, "%.0f" % _r_agg["fc"])
    check("听牌扩展·施压门槛显著高于被动（≥2 倍）",
          _r_agg["eff_req"] > _r_pas["eff_req"] * 2.0,
          "%.3f vs %.3f" % (_r_agg["eff_req"], _r_pas["eff_req"]))
    check("听牌扩展·被动时不折算（fc=0，不凭空抬门槛）",
          _r_pas["fc"] == 0.0, "%.0f" % _r_pas["fc"])

# ============================================================
#  四、【A 感知硬规则】「大注 + 无坚果 → 弃」的口径含后续投入
# ============================================================
# 原实现：`to_call > 0.6×池` 一刀切，**完全不咨询门槛** → A 永远够不着
#   （实测 aggro：20 个 fold 里 12 个由它决定，占 60%）。
# 改后：`to_call + W×future_cost > 0.6×池` → 对手爱连街开火时更早弃；
#   对手被动 / 河牌（fc=0）时**逐字等价于原规则**，不会反向过度弃牌。
#
# 【默认关闭】隔离检验显示该改动收益不显著（p=0.734）而亏损显著（p=0.036），
# 且门控无法分离两类对手 → 默认 `BIG_BET_FOLD_A_ON=False`（代码保留备用）。
# 本节测试显式开启该开关，验证的是**开关打开时**的行为契约。
print("\n--- A 感知硬规则：大注弃牌口径含后续投入（默认关，本节显式开启）---")
_prev_bigbet = strategy.BIG_BET_FOLD_A_ON
strategy.BIG_BET_FOLD_A_ON = True
check("A 感知·默认关闭（未被显式开启时不生效）",
      _prev_bigbet is False, "默认值=%s" % _prev_bigbet)

# 翻牌、高张（无坚果无强听），面对 700 下注；池 5100 → 0.6×池 = 3060
_big_req = dict(
    my_cards=[45, 42], public_cards=[12, 33, 16], my_chips=17800,
    history=[{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 300, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 700, "action_type": "raise"}])
_st_big = parse_request(_big_req)
_bar = strategy.BIG_BET_FOLD_FRAC * _st_big.pot
_commit_agg = _st_big.to_call + strategy.BIG_BET_FOLD_FUTURE_W * \
    _future_cost(_st_big, _st_big.to_call, m_aggro())[0]
_commit_pas = _st_big.to_call + strategy.BIG_BET_FOLD_FUTURE_W * \
    _future_cost(_st_big, _st_big.to_call, m_passive())[0]
print("    to_call=%d  0.6×池=%.0f　施压 commit=%.0f　被动 commit=%.0f" % (
    _st_big.to_call, _bar, _commit_agg, _commit_pas))

check("A 感知·本街下注本身未达 0.6×池（原规则不会触发）",
      _st_big.to_call <= _bar, "%.0f vs %.0f" % (_st_big.to_call, _bar))
check("A 感知·施压口径被推过 0.6×池（新规则触发）",
      _commit_agg > _bar, "%.0f vs %.0f" % (_commit_agg, _bar))
check("A 感知·被动口径仍在 0.6×池以内（不触发，等价原规则）",
      _commit_pas <= _bar, "%.0f vs %.0f" % (_commit_pas, _bar))

_a_agg4 = decide(_st_big, m_aggro())
check("A 感知·施压 → fold", _a_agg4 == {"act": "fold"}, str(_a_agg4))

# 「规则是否触发」比「最终动作」更准确：规则在 `_face_bet` 里**早于门槛逻辑**
# return，因此触发时**不会**留下跟注点记录；未触发才会走到后面写记录。
# （被动档最终也可能因别的规则弃牌，故不能拿最终动作当判据。）


def _rule_fired(model):
    strategy.WB_FACE_DEBUG = True
    strategy.WB_FACE_LOG.clear()
    decide(_st_big, model)
    got = len(strategy.WB_FACE_LOG) > 0
    strategy.WB_FACE_LOG.clear()
    strategy.WB_FACE_DEBUG = False
    return not got          # 没留下记录 = 规则提前 return 了


check("A 感知·施压档该规则触发（早于门槛 return）",
      _rule_fired(m_aggro()) is True, "未触发")
check("A 感知·被动档该规则不触发（放行给门槛逻辑）",
      _rule_fired(m_passive()) is False, "误触发")

# 单独开关：关掉后口径回到「只用本街 to_call」→ 该夹具不应再触发
strategy.BIG_BET_FOLD_A_ON = False
check("A 感知·开关关闭后该规则不触发（回到旧口径）",
      _rule_fired(m_aggro()) is False, "开关失效")
strategy.BIG_BET_FOLD_A_ON = True
check("A 感知·开关恢复后重新触发",
      _rule_fired(m_aggro()) is True, "开关无法恢复")

# 【门控】只有对手确实是施压型才放大口径；顺带兼作样本门控（无样本→不启用）
_m_bph10 = m_aggro()
_m_bph10.hand_bet_counts = [1] * 20          # 每局 1 次下注 → 因子 0.469
print("    门控：无样本 %.3f / bph=1.0 %.3f / bph=2.0 %.3f　阈值 %.2f" % (
    _future_aggr_factor(OpponentModel()), _future_aggr_factor(_m_bph10),
    _future_aggr_factor(m_aggro()), BIG_BET_FOLD_MIN_AGGR))
check("门控·无样本（先验 0.9）→ 因子低于阈值（开局不启用）",
      _future_aggr_factor(OpponentModel()) < BIG_BET_FOLD_MIN_AGGR,
      "%.3f" % _future_aggr_factor(OpponentModel()))
check("门控·bph=1.0 → 因子低于阈值（不放大口径）",
      _future_aggr_factor(_m_bph10) < BIG_BET_FOLD_MIN_AGGR,
      "%.3f" % _future_aggr_factor(_m_bph10))
check("门控·bph=2.0 → 因子高于阈值（放行）",
      _future_aggr_factor(m_aggro()) >= BIG_BET_FOLD_MIN_AGGR,
      "%.3f" % _future_aggr_factor(m_aggro()))
check("门控·bph=1.0 档该规则不触发",
      _rule_fired(_m_bph10) is False, "误触发")

# 河牌：无后续街 → future_cost=0 → 口径逐字等于 to_call（原规则原样）
_riv_req = dict(_big_req)
_riv_req["public_cards"] = [12, 33, 16, 40]
_riv_req["history"] = _big_req["history"] + [
    {"round": 2, "player_id": 1, "action": 0, "action_type": "check"},
    {"round": 3, "player_id": 1, "action": 700, "action_type": "raise"}]
_st_riv = parse_request(_riv_req)
_fc_riv = _future_cost(_st_riv, _st_riv.to_call, m_aggro())[0]
check("A 感知·河牌 future_cost=0（口径等价原规则）",
      _fc_riv == 0.0, "%.0f" % _fc_riv)

# 收尾：恢复该开关的默认值（默认关闭）
strategy.BIG_BET_FOLD_A_ON = _prev_bigbet
check("A 感知·测试收尾恢复默认（关闭）",
      strategy.BIG_BET_FOLD_A_ON is False, "%s" % strategy.BIG_BET_FOLD_A_ON)

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
