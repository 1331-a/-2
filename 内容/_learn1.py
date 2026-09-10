# -*- coding: utf-8 -*-
"""给决策日志加"对手学习"归因标记。

设计：全局 _LEARN_TAGS（每步决策开始时清空），各学习点在真正生效时打标；
decide 包装层把标记写进日志 detail → view_log/记事本可读出。
标记格式：
    learn=size0.55   使用响应学习选出的价值注尺寸桶
    learn=fold0.42   诈唬用实测弃牌率替代全局估计
    learn=cbw0.70    规则12 权重来自后期对手反应调整（非前期 1.0）
    arch=station     对手原型（非 unknown）
    opp_fold=0.38    对手面对下注弃牌率（eff）
"""
import io

P = "strategy.py"
s = io.open(P, encoding="utf-8").read()

# ---------- 1) 全局标记容器 ----------
old_g = "_MODEL_REF = None  # 当前请求的对手模型（decide 入口设置，供防read尺度使用）"
new_g = '''_MODEL_REF = None  # 当前请求的对手模型（decide 入口设置，供防read尺度使用）
_LEARN_TAGS = []   # 【2026-09-10】本步决策中生效的"对手学习"标记（供日志归因）


def _tag_learn(tag):
    """记录一个学习归因标记（decide 每步开始时清空）。"""
    try:
        if tag and tag not in _LEARN_TAGS:
            _LEARN_TAGS.append(tag)
    except Exception:
        pass'''
assert old_g in s, "global not found"
s = s.replace(old_g, new_g, 1)

# ---------- 2) 学习点打标 ----------
# (a) _learned_size 生效
old_a = '''    res = model.learned_value_bucket(is_preflop, cur_hand=state.hand_num)'''
new_a = '''    res = model.learned_value_bucket(is_preflop, cur_hand=state.hand_num)
    if res is not None:
        try:
            _tag_learn("size%s" % res[0])
        except Exception:
            pass'''
assert old_a in s
s = s.replace(old_a, new_a, 1)

# (b) 诈唬用实测弃牌率
old_b = '''                fr = model.learned_fold_rate(False, size, big_blind, pot,'''
new_b = '''                fr = model.learned_fold_rate(False, size, big_blind, pot,'''
assert old_b in s

# (c) 规则12 权重（后期非 1.0 才算学习生效）
old_c = '''    try:
        if state.hand_num <= CHECK_BET_EARLY_HANDS:
            return CHECK_BET_EARLY_FREQ'''
new_c = '''    try:
        if state.hand_num <= CHECK_BET_EARLY_HANDS:
            _tag_learn("cbw早1.0")   # 前期无条件（非学习）
            return CHECK_BET_EARLY_FREQ'''
assert old_c in s
s = s.replace(old_c, new_c, 1)

old_d = '''        if fr >= 0.55:
            return 1.00
        if fr >= 0.45:
            return 0.85
        if fr >= 0.35:
            return 0.70
        return CHECK_BET_MIN_FREQ'''
new_d = '''        _w = 1.00
        if fr >= 0.55:
            _w = 1.00
        elif fr >= 0.45:
            _w = 0.85
        elif fr >= 0.35:
            _w = 0.70
        else:
            _w = CHECK_BET_MIN_FREQ
        _tag_learn("cbw%.2f" % _w)          # 后期权重来自对手反应（学习生效）
        return _w'''
assert old_d in s
s = s.replace(old_d, new_d, 1)

# ---------- 3) decide 包装层：清空 + 写日志 ----------
old_e = '''    action = _decide_impl(state, model, ctx, debug=debug)'''
new_e = '''    # 【对手学习归因】每步清空标记；_decide_impl 内的学习点会打标
    try:
        _LEARN_TAGS.clear()
    except Exception:
        pass
    action = _decide_impl(state, model, ctx, debug=debug)'''
assert old_e in s
s = s.replace(old_e, new_e, 1)

old_f = '''        DecisionLogger.log(
            state.hand_num, state.stage, state.pot, "final",
            str(action.get("act")),
            "cat=%s adj=%s num=%s to_call=%s pot=%s" % (
                _cat, _adj, action.get("num"), state.to_call, state.pot))'''
new_f = '''        # 对手模型关键指标 + 学习归因
        _extra = ""
        try:
            _m = _MODEL_REF
            if _m is not None:
                _opp_fold = round(float(_m.eff_fold_to_bet()), 2)
                _opp_bet = round(float(_m.eff_bet_freq()), 2)
                _arch = _m.archetype()
                _extra = " opp_fold=%s opp_bet=%s arch=%s" % (
                    _opp_fold, _opp_bet, _arch)
        except Exception:
            _extra = ""
        _learn = (" learn=" + ",".join(_LEARN_TAGS)) if _LEARN_TAGS else " learn=-"
        DecisionLogger.log(
            state.hand_num, state.stage, state.pot, "final",
            str(action.get("act")),
            "cat=%s adj=%s num=%s to_call=%s pot=%s%s%s" % (
                _cat, _adj, action.get("num"), state.to_call, state.pot,
                _extra, _learn))'''
assert old_f in s, "log block not found"
s = s.replace(old_f, new_f, 1)

io.open(P, "w", encoding="utf-8").write(s)
print("learn tags added")
