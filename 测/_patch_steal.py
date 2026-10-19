# -*- coding: utf-8 -*-
"""一次性补丁：接入 `_steal_guard`（对手爱加注 → 弱牌小注改过牌）。"""
import ast
import pathlib

p = pathlib.Path("内容/strategy.py")
s = p.read_text(encoding="utf-8")

old = """        return _check_side(state, model, eq, category, strong, good, medium,
                           big_draw, draw, tex, arch, adj, is_river,
                           i_aggressor)"""
new = """        return _steal_guard(state, model,
                            _check_side(state, model, eq, category, strong, good,
                                        medium, big_draw, draw, tex, arch, adj,
                                        is_river, i_aggressor),
                            category, big_draw, draw)"""
assert old in s, "call site not found"
s = s.replace(old, new, 1)

anchor = "def _aggr_fold_guard(state, action, category):"
impl = '''def _opp_raise_vs_bet(model, state):
    """对手「面对我方下注 → 加注」的实测比率，返回 (rate, n) 或 None。

    两个口径，优先尺寸桶（更贴近当前下注量），样本不足退回 check_raise：
      ① bet_resp_stats(bucket)：`我方下注该尺寸后对手加注` 的次数 / 总次数；
      ② check_raise_rate()：`对手过牌 → 我下注 → 他加注`（规则12 的同场景），
         带贝叶斯收缩（先验 0.10），只在 check_faces >= 5 时采用。
    返回 None 表示样本不足 —— 调用方必须按原行为处理，不许猜。
    """
    if model is None:
        return None
    try:
        probe = int(state.curbet[state.my_id] + max(state.pot, 1) * 0.35)
        b = model._bet_size_bucket(False, probe, state.big_blind, state.pot)
        st = model.bet_resp_stats(b, cur_hand=state.hand_num,
                                  min_samples=STEAL_GUARD_MIN_N)
        if st is not None and st.get("n", 0) >= STEAL_GUARD_MIN_N:
            return float(st["raise_rate"]), int(st["n"])
    except Exception:
        pass
    try:
        n = int(getattr(model, "check_faces", 0) or 0)
        if n >= max(STEAL_GUARD_MIN_N, 5):
            return float(model.check_raise_rate()), n
    except Exception:
        pass
    return None


def _steal_guard(state, model, action, category, big_draw=False, draw=False):
    """【2026-10-19】对手爱加注时，把「弱牌小注偷」改成过牌。

    依据：人机对局 12 手翻后小注净 −22,898，其中 9 手（75%）被加注；
    被加注的 9 手里 8 手一对、1 手高牌 —— 我方既没有弃牌权益（对手不弃），
    又主动把筹码投进一个会被加注的池子。而对手的加注率在模型里已经统计了
    （check_raise_rate / bet_resp_stats），只是此前没接进主动侧。

    触发条件（全部满足）：
      · 动作是下注/加注且当前无需跟注（主动侧）；
      · 我方牌型 <= 一对、无听牌（有摊牌价值或半诈唬权益时不压）；
      · 下注尺寸 <= 0.5x底池（只压「小注偷」，大注不动）；
      · 对手加注率 >= 30%（样本不足 → 不动）。
    回退：WB_NO_STEAL_GUARD=1。
    """
    if not STEAL_GUARD_ON:
        return action
    try:
        if str(action.get("act")) != "raise":
            return action
        if int(state.to_call) > 0:
            return action
        if int(category) > AGGR_FOLD_MAX_CAT:
            return action
        if big_draw or draw:
            return action
        num = action.get("num")
        if num is None:
            return action
        size = int(num) - int(state.curbet[state.my_id])
        pot = float(state.pot)
        if size <= 0 or pot <= 0 or size > STEAL_GUARD_MAX_FRAC * pot:
            return action
        info = _opp_raise_vs_bet(model, state)
        if info is None:
            return action
        if float(info[0]) >= STEAL_GUARD_RAISE_MIN:
            return {"act": "check"}
    except Exception:
        pass
    return action


def _aggr_fold_guard(state, action, category):'''

assert anchor in s, "anchor not found"
s = s.replace(anchor, impl, 1)
p.write_text(s, encoding="utf-8")
ast.parse(s)
print("patched ok")
