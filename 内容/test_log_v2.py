# -*- coding: utf-8 -*-
"""日志 v2 专项测试：explain 快照 / 候选规则归因 / 对手过牌后统计 / 下注模式。

运行：python test_log_v2.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request                     # noqa: E402
from opponent import OpponentModel, build_model_from_history  # noqa: E402
from strategy import (decide, explain, _candidate_rules,  # noqa: E402
                      _winning_rule, DecisionLogger,
                      _fmt_card, BetPatternDetector, ONE_PAIR)

_PASS = []
_FAIL = []


def check(name, cond, detail=""):
    if cond:
        _PASS.append(name)
    else:
        _FAIL.append("%s  %s" % (name, detail))


def req(**kw):
    base = {"num_players": 2, "dealer_id": 1, "my_id": 0, "my_chips": 19500,
            "my_cards": [34, 17], "public_cards": [13, 49, 29],
            "history": [], "hand": 40, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# ---------- 1. 牌面显示 ----------
check("牌面:34→8h", _fmt_card(34) == "8\u2665", _fmt_card(34))
check("牌面:17→4d", _fmt_card(17) == "4\u2666", _fmt_card(17))

# ---------- 2. explain 锁赢段 ----------
st = parse_request(req(total_win_chips=[879, -879], hand=60, max_hand=70,
                       my_chips=19900))
info = explain(st, OpponentModel())
lk = info.get("lock") or {}
check("explain.lock 存在", bool(lk), str(info.keys()))
check("lead = 单边×2 = 1758", lk.get("lead") == 1758, str(lk.get("lead")))
from strategy import _hands_left as _hl, _blind_line as _bl
# 【2026-09-11】平台 hand 为 0-based：本手之后剩余 = max_hand - 1 - hand
check("_hands_left: hand=0,max=70 → 69",
      _hl(parse_request(req(hand=0, max_hand=70))) == 69)
check("_hands_left: hand=60,max=70 → 9（本手之后还剩 9 手）", _hl(st) == 9, str(_hl(st)))
check("_hands_left: hand=59,max=70 → 10", _hl(parse_request(req(hand=59, max_hand=70))) == 10)
check("_hands_left: 最后一手 hand=69,max=70 → 0",
      _hl(parse_request(req(hand=69, max_hand=70))) == 0)
check("_blind_line(70, own=True) == 5250  # 35小盲+35大盲",
      _bl(st, 70, True) == 5250, str(_bl(st, 70, True)))
check("锁赢线 = 2×(盲注线+已投)（与 _hands_left 自洽）",
      lk.get("line") == 2 * (_bl(st, _hl(st), True) + (20000 - st.my_chips)),
      "line=%s hl=%s" % (lk.get("line"), _hl(st)))
check("状态为已锁赢", "\u5df2\u9501\u8d62" in (lk.get("status") or ""), lk.get("status"))
check("进度封顶 1.0", 0.0 <= lk.get("progress", -1) <= 1.0, str(lk.get("progress")))
check("位置=大盲(my=0,dealer=1)", lk.get("position") == "\u5927\u76f2", lk.get("position"))

# 落后情形
st2 = parse_request(req(total_win_chips=[-879, 879], hand=60, my_chips=19900))
lk2 = explain(st2, OpponentModel()).get("lock") or {}
check("落后 → 状态未锁赢", "\u672a\u9501\u8d62" in (lk2.get("status") or ""), lk2.get("status"))
check("落后 lead 为负", lk2.get("lead") == -1758, str(lk2.get("lead")))

# ---------- 3. explain 牌力段 ----------
st3 = parse_request(req(public_cards=[13, 49, 29], my_cards=[34, 17]))
hm = explain(st3, OpponentModel()).get("hand") or {}
check("explain.hand 有牌型名", bool(hm.get("cat_name")), str(hm))
check("explain.hand 有胜率", hm.get("eq") is not None, str(hm.get("eq")))

# ---------- 4. 候选规则 + 归因 ----------
# doom 场景：剩 1 手 + 落后 → 规则2 allin
std = parse_request(req(hand=70, max_hand=70, my_chips=19900,
                        total_win_chips=[-100, 100], my_cards=[2, 4],
                        public_cards=[]))
a = decide(std, OpponentModel(), debug=False)
cands = _candidate_rules(std, OpponentModel(), 0)
check("候选含规则2", any("\u89c4\u52192" in c["name"] for c in cands), str(cands))
check("doom 决策=allin", a.get("act") == "allin", str(a))
check("归因命中规则2", "\u89c4\u52192" in _winning_rule(cands, a),
      _winning_rule(cands, a))

# 锁赢场景：领先 → fold
sl = parse_request(req(total_win_chips=[879, -879], hand=60, my_chips=19900))
al = decide(sl, OpponentModel(), debug=False)
cl = _candidate_rules(sl, OpponentModel(), 0)
check("锁赢决策:不投入(fold/check)", al.get("act") in ("fold", "check"), str(al))
check("锁赢决策:to_call==0 → check", al.get("act") == "check", str(al))
check("归因命中规则2(锁胜)", "\u89c4\u52192" in _winning_rule(cl, al),
      _winning_rule(cl, al))

# ---------- 5. 对手「过牌后」统计 ----------
m = OpponentModel()
for _ in range(4):
    m._add_bet_resp(1, False, "sf_m", "fold", after_check=True)
m._add_bet_resp(1, False, "sf_m", "raise", after_check=True)
check("check_faces 计数", m.check_faces == 5, str(m.check_faces))
check("check_fold 计数", m.check_fold == 4, str(m.check_fold))
check("check_raise 计数", m.check_raise == 1, str(m.check_raise))
check("check_fold_rate 高于先验", m.check_fold_rate() > 0.55,
      str(m.check_fold_rate()))
check("check_raise_rate 高于先验", m.check_raise_rate() > 0.10,
      str(m.check_raise_rate()))
check("无样本时回退先验",
      abs(OpponentModel().check_fold_rate() - 0.55) < 1e-6,
      str(OpponentModel().check_fold_rate()))

# ---------- 6. 下注模式被喂入（含常用总注额）----------
# 数值型 = 金额固定(2000) 而底池变化 → BPR 剧烈波动 → 判 numeric
bp = BetPatternDetector()
for _p in (600, 900, 1200, 700, 1500, 800):
    bp.observe(_p, 2000)
check("固定金额+底池变化 → numeric", bp.get_pattern() == "numeric",
      "%s %s" % (bp.get_pattern(), [round(x, 2) for x in bp.bprs]))
check("常用总注额 = 2000", bp.main_size() == 2000, str(bp.main_size()))
check("序列化含 sizes",
      "sizes" in BetPatternDetector.from_json(bp.to_json()).to_json(),
      "to_json 缺 sizes")

bp2 = BetPatternDetector()
for p, b in [(1000, 660), (2000, 1330), (1500, 1000), (3000, 2000), (800, 530),
             (2500, 1660)]:
    bp2.observe(p, b)
check("比例型 → proportional", bp2.get_pattern() == "proportional",
      "%s %s" % (bp2.get_pattern(), bp2.bprs[:3]))

# ---------- 7. build_model_from_history 喂下注模式 ----------
m2 = OpponentModel()
rq = req(hand=5, history=[
    {"round": 0, "player_id": 1, "action": 300, "action_type": "raise"},
    {"round": 0, "player_id": 0, "action": 300, "action_type": "call"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
    {"round": 1, "player_id": 1, "action": 400, "action_type": "raise"},
])
build_model_from_history(m2, rq, parse_request(rq))
check("历史喂入下注模式", len(m2.bet_pattern.sizes) >= 1,
      str(m2.bet_pattern.sizes))
# 重复喂同一历史不应重复计数（增量游标）
n1 = len(m2.bet_pattern.sizes)
build_model_from_history(m2, rq, parse_request(rq))
check("增量游标不重复计数", len(m2.bet_pattern.sizes) == n1,
      "%d → %d" % (n1, len(m2.bet_pattern.sizes)))

# ---------- 8. 日志：静默模式不产生 stderr ----------
DecisionLogger.reset()
DecisionLogger.enable(True)
DecisionLogger._quiet = True
recs_before = len(DecisionLogger.records())
decide(st, OpponentModel(), debug=True)
check("静默模式仍记录", len(DecisionLogger.records()) > recs_before,
      "%d → %d" % (recs_before, len(DecisionLogger.records())))
rec0 = DecisionLogger.records()[-1]
check("记录含 info/cands", bool(rec0.get("info")) and "cands" in rec0,
      str(list(rec0.keys())))
DecisionLogger._quiet = False

# ---------- 9. 规则健康度 ----------
lines = DecisionLogger.health_lines()
check("健康度有输出", len(lines) > 0, str(lines[:1]))
check("健康度含表头", any("\u89c4\u5219\u5065\u5eb7\u5ea6" in x for x in lines),
      str(lines[:2]))

# ---------- 10. 进度条 ----------
check("进度条 0%%", "0%" in DecisionLogger.progress_bar(0.0),
      DecisionLogger.progress_bar(0.0))
check("进度条 100%%", "100%" in DecisionLogger.progress_bar(1.5),
      DecisionLogger.progress_bar(1.5))



# ============ 2026-09-11 五项审查修复专项 ============
from strategy import (_lock_line, _safe_fallback_action,
                      _LW_UNSET, _decide_impl, _stability_mode)
import strategy as _S2
from bot import _final_guard


def _mk(twc, hand=30, my_chips=19900):
    return parse_request({"num_players": 2, "dealer_id": 1, "my_id": 0,
                          "my_chips": my_chips, "my_cards": [34, 17],
                          "public_cards": [], "history": [], "hand": hand,
                          "max_hand": 70, "total_win_chips": twc,
                          "total_win_games": [0, 0]})


# --- 优势锁定（LEAD_LOCK）已于 2026-09-14 移除 ---
check("0914:_LEAD_LOCK 全局已移除", not hasattr(_S2, "_LEAD_LOCK"))
check("0914:_is_lead_lock 已移除", not hasattr(_S2, "_is_lead_lock"))
check("0914:LEAD_NO_ALLIN / LEAD_MAX_BET 常量已移除",
      not hasattr(_S2, "LEAD_NO_ALLIN") and not hasattr(_S2, "LEAD_MAX_BET"))
# 领先 10000（旧 LEAD_LOCK 区间）面对全下：强牌不再被强制弃牌
_u_p0 = _S2._lock_win_unified(_mk([5000, -5000]))
check("0914:领先时 _lock_win_unified 仍可给出锁胜/防锁赢",
      _u_p0 is None or _u_p0.get("act") in ("check", "fold", "allin"), str(_u_p0))

# --- M1：_lock_line 含 2× 与 本手已投；求稳阈值 = 80%×锁赢线 ---
_st_m1 = _mk([1516, -1516], hand=47)
_line_m1 = _lock_line(_st_m1)
check("M1:_lock_line = 2×(盲注线+已投)", _line_m1 == 2 * (
    _bl(_st_m1, _hl(_st_m1), True) + (20000 - _st_m1.my_chips)),
    "line=%s" % _line_m1)
check("M1:锁赢线 3500（第48手）", _line_m1 == 3500, str(_line_m1))
# 旧写法阈值(0.8×blind_line=1400)会误触发；新写法 2800
_st_m1b = _mk([(1400 // 2), -(1400 // 2)], hand=47)
check("M1:lead 仅 40% 锁赢线 → 不该求稳",
      _stability_mode(_st_m1b, OpponentModel()) is False,
      "lead=%d line=%d" % (1400, _lock_line(_st_m1b)))
_st_m1c = _mk([(3000 // 2), -(3000 // 2)], hand=47)
check("M1:lead >80% 锁赢线 → 求稳",
      _stability_mode(_st_m1c, OpponentModel()) is True,
      "lead=%d line=%d" % (3000, _lock_line(_st_m1c)))

# --- M2：_decide_impl 支持复用外层算好的 _lw（避免重复调用）---
_st_m2 = _mk([0, 0], hand=30)
_u_m2 = _S2._lock_win_unified(_st_m2)
_a_m2 = _decide_impl(_st_m2, OpponentModel(), None, False, _u_m2)
check("M2:_decide_impl 接受 _lw 参数且不报错",
      isinstance(_a_m2, dict) and "act" in _a_m2, str(_a_m2))
check("M2:哨兵 _LW_UNSET 存在", _LW_UNSET is not None)

# --- M3：doomed 兜底必须 allin ---
check("M3:doomed 兜底 → allin",
      _safe_fallback_action(_mk([-100, 100], hand=69)) == {"act": "allin"},
      str(_safe_fallback_action(_mk([-100, 100], hand=69))))
check("M3:非 doomed 且 to_call<=0 → check",
      _safe_fallback_action(_mk([0, 0], hand=30)) == {"act": "check"},
      str(_safe_fallback_action(_mk([0, 0], hand=30))))

# --- D2：bot._final_guard 在 to_call==0 时不能返回 fold ---
_st_d2 = _mk([0, 0], hand=30, my_chips=20000)
_st_d2.opp_round_bet = 0
_st_d2._to_call = 0
check("D2:to_call==0 时 fold(-1) → 0(过牌)",
      _final_guard(_st_d2, -1) == 0, str(_final_guard(_st_d2, -1)))
_st_d2b = _mk([0, 0], hand=30, my_chips=19900)
_st_d2b.opp_round_bet = 300
_st_d2b._to_call = 200
check("D2:to_call>0 时 fold(-1) 仍为 -1",
      _final_guard(_st_d2b, -1) == -1, str(_final_guard(_st_d2b, -1)))




# ============ 2026-09-11 M4：decide 入口刷新全部模块级全局 ============
from strategy import _prepare_globals, _match_adjust
from match_ctx import (MatchContext, LEVEL_AGGRESSIVE, LEVEL_CONSERVATIVE)
import time as _time

_m4 = OpponentModel()
_st_m4 = parse_request({"num_players": 2, "dealer_id": 1, "my_id": 0,
                        "my_chips": 19900, "my_cards": [34, 17],
                        "public_cards": [], "history": [], "hand": 63,
                        "max_hand": 70, "total_win_chips": [-120, 120],
                        "total_win_games": [0, 0]})
_ctx_cons = MatchContext.from_dict(OpponentModel().ctx_dict)
_ctx_cons.level = LEVEL_CONSERVATIVE          # 正偏移 → 更难 doomed
_ctx_aggr = MatchContext.from_dict(OpponentModel().ctx_dict)
_ctx_aggr.level = LEVEL_AGGRESSIVE            # 负偏移 → 更易 doomed

# 【2026-09-14 修复】ctx 偏移只作用于 protect/pressure/desperate 的阈值，
# **不再影响 doom**（doom 是确定性硬规则，只用原始 lead 判定）——所以这里
# 改用 ±30BB(3000) 的 protect 边界来验证「ctx 确实生效」。
_st_m4b = parse_request({"num_players": 2, "dealer_id": 1, "my_id": 0,
                         "my_chips": 19900, "my_cards": [34, 17],
                         "public_cards": [], "history": [], "hand": 63,
                         "max_hand": 70, "total_win_chips": [1400, -1400],
                         "total_win_games": [0, 0]})
_S2._prepare_globals(_st_m4b, _m4, _ctx_cons)
_adj_cons = _match_adjust(_st_m4b)
_S2._prepare_globals(_st_m4b, _m4, _ctx_aggr)
_adj_aggr = _match_adjust(_st_m4b)
check("M4:同一状态在保守/激进档下 adjust 不同（ctx 生效）",
      _adj_cons != _adj_aggr, "%s vs %s" % (_adj_cons, _adj_aggr))
check("M4:保守档(正偏移)更早 protect（lead2800→3400≥30BB）",
      _adj_cons == "protect" and _adj_aggr == "normal",
      "%s vs %s" % (_adj_cons, _adj_aggr))

# 【2026-09-14 修复】doom 用原始 lead（不叠加 ctx 偏移）——decide 断言见下方。
_S2._prepare_globals(_st_m4, _m4, _ctx_cons)
_doom_c = _S2._doom_risk(_st_m4)
_S2._prepare_globals(_st_m4, _m4, _ctx_aggr)
_doom_a = _S2._doom_risk(_st_m4)
check("M4:doom 判定两档一致（确定性公式不受 ctx 影响）",
      _doom_c == _doom_a, "%s vs %s" % (_doom_c, _doom_a))

# 把全局故意留成「上一手的保守档」，本手传激进档 → 入口必须刷新
_S2._CTX = _ctx_cons
_S2._DECISION_STARTED_AT = 0.0
_a_m4 = decide(_st_m4, _m4, _ctx_aggr)
check("M4:入口已把 _CTX 刷新为本手 ctx", _S2._CTX is _ctx_aggr)
check("M4:入口已刷新 _OPP_JUMPED", isinstance(_S2._OPP_JUMPED, bool))
check("M4:入口已复位 _DECISION_STARTED_AT", _S2._DECISION_STARTED_AT > 0,
      str(_S2._DECISION_STARTED_AT))
# 【2026-09-14 修复】doom 用原始 lead（不叠加 ctx 偏移）：本场景 lead=-240、
# 本手已投 100（弃牌只损失 100，安全）→ 激进档也不该被判 doomed 无脑 allin。
check("M4:doom 不受 ctx 偏移污染 → 不误 allin", _a_m4.get("act") != "allin",
      str(_a_m4))
# 【2026-09-14】原断言「M4:doomed 边界按本手 ctx 判定 → allin」已删除：
# 该断言依赖「ctx 偏移能把 doom 边界推过线」的旧行为，而这正是本次修复的缺陷
# （会拿没牌的牌无条件 allin）。新断言见上方「doom 不受 ctx 偏移污染」两行。

# _prepare_globals 刷新 _OPP_JUMPED / _OPP_BETS_PER_HAND
_prepare_globals(_st_m4, _m4, _ctx_aggr)
check("M4:_OPP_JUMPED 已刷新(布尔)", isinstance(_S2._OPP_JUMPED, bool),
      str(_S2._OPP_JUMPED))
check("M4:_OPP_BETS_PER_HAND 已刷新(数值)",
      isinstance(_S2._OPP_BETS_PER_HAND, float),
      str(_S2._OPP_BETS_PER_HAND))




# ============ 2026-09-11 修复专项 ============
from strategy import (_lock_win_unified, _lock_win_legal,
                      _safe_fallback_action, _normalize)

# A. 锁胜 + to_call>0（面对下注）→ 仍然 fold
lk_fold = parse_request(req(total_win_chips=[879, -879], hand=59, max_hand=70,
                            my_chips=19900,
                            history=[{"round": 0, "player_id": 0, "action": 100,
                                      "action_type": "raise"},
                                     {"round": 0, "player_id": 1, "action": 300,
                                      "action_type": "raise"}]))
_u = _lock_win_unified(lk_fold)
check("0911:锁胜+to_call>0 → fold", _u is not None and _u.get("act") == "check"
      or (_u is not None and _u.get("act") == "fold"), str(_u))

# B. _lock_win_legal：to_call==0 时把 fold 改成 check
st_zero = parse_request(req(total_win_chips=[879, -879], hand=59, max_hand=70,
                            my_chips=19900, history=[]))
check("0911:_lock_win_legal 在 to_call==0 时 fold→check",
      _lock_win_legal(st_zero, {"act": "fold"}) == {"act": "check"},
      str(st_zero.to_call))

# C. 入口拦截：即使 _decide_impl 抛异常，锁赢动作仍然生效
import strategy as _S
_calls = {"n": 0}
_orig_impl = _S._decide_impl


def _boom(*a, **k):
    _calls["n"] += 1
    raise RuntimeError("boom")


_S._decide_impl = _boom
try:
    a_boom = decide(lk_fold, OpponentModel(), None)
finally:
    _S._decide_impl = _orig_impl
check("0911:锁赢状态下 _decide_impl 异常不影响锁赢动作",
      a_boom.get("act") in ("fold", "check", "allin"), str(a_boom))
check("0911:锁赢状态下 _decide_impl 根本没被调用(入口拦截生效)",
      _calls["n"] == 0, "called=%d" % _calls["n"])

# D. 异常兜底：非锁赢状态下 _decide_impl 抛异常 → 返回合法保守动作
st_plain = parse_request(req(total_win_chips=[0, 0], hand=10, max_hand=70,
                             my_chips=19900, history=[]))
_S._decide_impl = _boom
try:
    a_fb = decide(st_plain, OpponentModel(), None)
finally:
    _S._decide_impl = _orig_impl
check("0911:_decide_impl 异常 → 合法兜底动作",
      a_fb.get("act") in ("check", "fold"), str(a_fb))

# E. BOT_VERSION 存在
from strategy import BOT_VERSION as _BV
check("0911:BOT_VERSION 存在", isinstance(_BV, str) and len(_BV) > 0, str(_BV))


# ============ 2026-09-14 修复专项：禁止「只投入不搏」（双口径 doom） ============
# 用户截图第35手河牌：对手加注至 300，我方只跟注 300 → 输掉后对手锁赢。
# 根因：doom 只按「已投入」估损失，没算尚未跟注的 to_call → 跟注后失败
#       才导致的锁赢被判成「不 doomed」→ 只跟注（慢性死亡）。
# 修法：两个口径分开——
#   · 弃牌口径（ie. _match_adjust）：敞口 = 已投入  → 「弃牌是否送掉比赛」
#   · 跟注口径：敞口 = 已投入 + to_call → 「跟注是否送掉」
# 2026-09-24 起「跟注口径」不再用「改写动作」的补丁实现，改由决策出口的
# `_endgame_arbitrate` 把弃牌/过牌/跟注/加注/全押放在同一终局效用尺度上比较。
from strategy import (_exposure, _invested, _doom_risk,            # noqa: E402
                      _fold_out_active, _profit_lock_allin,
                      _win_utility, _endgame_eu, _endgame_matters,
                      _endgame_arbitrate)

# A. 截图场景精确复现（本场结算后 -2881 → 决策时单边 -481 → lead -962）
pic = parse_request(req(
    my_chips=17900, hand=34, max_hand=70, dealer_id=1, my_id=0,
    my_cards=[10, 44], public_cards=[24, 0, 49, 33, 46],
    history=[{"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
             {"round": 0, "player_id": 0, "action": 200, "action_type": "call"},
             {"round": 1, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 1, "player_id": 1, "action": 300, "action_type": "call"},
             {"round": 2, "player_id": 0, "action": 600, "action_type": "raise"},
             {"round": 2, "player_id": 1, "action": 600, "action_type": "call"},
             {"round": 3, "player_id": 1, "action": 300, "action_type": "raise"}],
    total_win_chips=[-481, 481]))
check("0914:已投入 = 2100", _invested(pic) == 2100, str(_invested(pic)))
check("0914:敞口 = 已投入 + to_call = 2400", _exposure(pic) == 2400,
      str(_exposure(pic)))
check("0914:弃牌口径不 doom（弃牌尚可翻身 → 保持 normal）",
      _doom_risk(pic) is False and _match_adjust(pic) == "normal",
      "doom=%s adj=%s" % (_doom_risk(pic), _match_adjust(pic)))
check("0914:跟注口径 doom 成立（跟注即送掉比赛）",
      _doom_risk(pic, include_to_call=True) is True, "应 True")

# B. 【2026-09-24 架构调整】不再「改写动作」，改为终局效用比较：
#    同一触发面上把 弃牌/过牌/跟注/加注/全押 放在一起比 EU，取最优；
#    仲裁只往「少冒风险」方向修正（不制造新的加注/全押）。
_eu_pic = _endgame_eu(pic, OpponentModel(), 0.5, {"act": "call"}, "normal")
check("0924仲裁:第35手各动作 EU 齐全（弃牌是平权候选）",
      set(_eu_pic) >= {"fold", "check", "call", "allin"}, str(_eu_pic))
check("0924仲裁:弃牌有价值（不为 0）",
      0.0 < _eu_pic["fold"] < 1.0, str(_eu_pic["fold"]))
check("0924仲裁:触发面 = 敞口 doom",
      _endgame_matters(pic, {"act": "call"}) is True, "")
check("0924仲裁:硬性弃牌不被翻案（fold 不被改成 allin）",
      _endgame_arbitrate(pic, OpponentModel(), {"act": "fold"}, 0.5,
                         "normal") == {"act": "fold"},
      str(_endgame_arbitrate(pic, OpponentModel(), {"act": "fold"}, 0.5, "normal")))
check("0924仲裁:便宜跟注不被升成全押",
      _endgame_arbitrate(pic, OpponentModel(), {"act": "call"}, 0.5,
                         "normal") == {"act": "call"},
      str(_endgame_arbitrate(pic, OpponentModel(), {"act": "call"}, 0.5, "normal")))
check("0924仲裁:端到端 —— 第35手不再输出 allin",
      decide(pic, OpponentModel()).get("act") != "allin",
      str(decide(pic, OpponentModel())))
# 对手下注 3000（重投入）：跟注与全押的风险接近，此时才可能允许全押倾向
pic_big = parse_request(req(
    my_chips=17900, hand=34, max_hand=70, dealer_id=1, my_id=0,
    my_cards=[10, 44], public_cards=[24, 0, 49, 33, 46],
    history=[{"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
             {"round": 0, "player_id": 0, "action": 200, "action_type": "call"},
             {"round": 1, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 1, "player_id": 1, "action": 300, "action_type": "call"},
             {"round": 2, "player_id": 0, "action": 600, "action_type": "raise"},
             {"round": 2, "player_id": 1, "action": 600, "action_type": "call"},
             {"round": 3, "player_id": 1, "action": 3000, "action_type": "raise"}],
    total_win_chips=[-481, 481]))
_eu_big = _endgame_eu(pic_big, OpponentModel(), 0.5, {"act": "call"}, "normal")
check("0924仲裁:重投入时 EU 仍可比较（不抛异常）",
      isinstance(_eu_big.get("allin"), float), str(_eu_big))

# C. to_call=0 时敞口 = 已投入（与修复前一致，不回归）
zero = parse_request(req(my_chips=17900, hand=34, max_hand=70,
                         total_win_chips=[-481, 481]))
check("0914:to_call=0 时敞口 = 已投入 2100",
      _exposure(zero) == 2100, str(_exposure(zero)))

# D. 不会误触发：早期手数 + 小额跟注 + lead 很小
early = parse_request(req(my_chips=19800, hand=8, max_hand=70,
                          total_win_chips=[-50, 50],
                          history=[{"round": 0, "player_id": 1, "action": 100,
                                    "action_type": "raise"}]))
check("0914:早期小额跟注不误判 doomed",
      _match_adjust(early) == "normal" and _doom_risk(early) is False,
      _match_adjust(early))

# E. 弃牌本来就安全的场景（均势翻前面对大额全下）→ 不应被升级
# 均势翻前：只投了大盲 100，对手加注到 5300（to_call=5200）。
# 弃牌只损失 100 → 完全安全；若跟注 5200 输了才锁定败局。
safe_fold = parse_request(req(
    my_chips=19900, hand=20, max_hand=70, dealer_id=1, my_id=0,
    my_cards=[40, 43], public_cards=[],
    history=[{"round": 0, "player_id": 1, "action": 5300,
              "action_type": "raise"}],
    total_win_chips=[0, 0]))
check("0914:均势弃大注：弃牌口径不 doom（弃牌只亏 100，安全）",
      _doom_risk(safe_fold) is False, "应 False")
check("0914:均势弃大注：跟注口径 doom（跟 5200 输了才送掉）",
      _doom_risk(safe_fold, include_to_call=True) is True, "应 True")
check("0924:该类场景若本要弃牌 → 维持 fold（不被翻案）",
      _endgame_arbitrate(safe_fold, OpponentModel(), {"act": "fold"}, 0.5,
                         "normal") == {"act": "fold"})

# F. 两口径可由同一不等式开关切换（公式单点，避免各自演化）
check("0914:include_to_call 开关生效（True 比 False 更易触发）",
      (_doom_risk(pic, include_to_call=True)
       and not _doom_risk(pic, include_to_call=False)))
check("0914:盈利锁胜复用 _doom_risk（公式单点）",
      "_doom_risk" in __import__("inspect").getsource(_profit_lock_allin))



# ============ 2026-09-14 规则14：我过牌后对手小注 → 假定诈唬 ============
# 用户规则：自己过牌后对手立刻（小额）加注，默认 <300 视作诈唬；
# 激进派（maniac / bet_freq≥0.52）阈值放宽到 <500。此时可跟注或反加小注，
# 而不是弃牌。
from strategy import (_small_bet_bluff_read, _my_checked_this_round,  # noqa: E402
                      _bluff_read_threshold, _effective_category,
                      BLUFF_READ_BET, BLUFF_READ_BET_AGGRO,
                      BLUFF_READ_RAISE_MULT)

_PRE14 = [{"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
          {"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
          {"round": 0, "player_id": 0, "action": 200, "action_type": "call"}]
_CHK14 = {"round": 3, "player_id": 0, "action": 0, "action_type": "check"}


def _st14(hist, **kw):
    base = {"num_players": 2, "dealer_id": 1, "my_id": 0, "my_chips": 19900,
            "my_cards": [10, 44], "public_cards": [24, 0, 49, 33, 46],
            "history": hist, "hand": 34, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return parse_request(base)


_m14 = OpponentModel()

# A. 过牌／跟注识别（action=0 + call 是 check 的等价编码）
_st_chk = _st14(_PRE14 + [_CHK14])
check("0914规则14:我方 check 被识别",
      _my_checked_this_round(_st_chk) is True)
_st_call = _st14(_PRE14 + [
    {"round": 3, "player_id": 1, "action": 200, "action_type": "raise"},
    {"round": 3, "player_id": 0, "action": 200, "action_type": "call"},
    {"round": 3, "player_id": 1, "action": 300, "action_type": "raise"}])
check("0914规则14:真·跟注(action>0)不算过牌",
      _my_checked_this_round(_st_call) is False)

# B. 阈值随对手风格变化
check("0914规则14:默认对手阈值 = 300",
      _bluff_read_threshold(_m14) == BLUFF_READ_BET)
_agg14 = OpponentModel()
_agg14.postflop_bet = 8; _agg14.postflop_call = 1
_agg14.postflop_fold = 1; _agg14.postflop_check = 1
check("0914规则14:激进对手(bet_freq≥0.52)阈值放宽到 500",
      _bluff_read_threshold(_agg14) == BLUFF_READ_BET_AGGRO,
      "bet_freq=%.2f thr=%d" % (_agg14.bet_freq, _bluff_read_threshold(_agg14)))

# C. 触发：我过牌 + 对手下注 300（默认对手）
_small = _st14(_PRE14 + [_CHK14, {"round": 3, "player_id": 1, "action": 300,
                                 "action_type": "raise"}])
_a14 = _small_bet_bluff_read(_small, _m14, _effective_category(_small), False)
check("0914规则14:过牌后对手下注300 → 触发(不弃牌)",
      _a14 is not None and _a14.get("act") in ("call", "raise"), str(_a14))
check("0914规则14:触发时反加尺度 = 3× 对手注额",
      _a14.get("act") == "call" or _a14.get("num") == int(
          BLUFF_READ_RAISE_MULT * 300), str(_a14))

# D. 不触发：超过阈值（400 > 300，非激进对手）
_over = _st14(_PRE14 + [_CHK14, {"round": 3, "player_id": 1, "action": 400,
                                "action_type": "raise"}])
check("0914规则14:非激进对手下注400 → 不触发",
      _small_bet_bluff_read(_over, _m14, _effective_category(_over), False) is None)
check("0914规则14:同一 400 对激进对手 → 触发",
      _small_bet_bluff_read(_over, _agg14, _effective_category(_over), False)
      is not None)

# E. 不触发：翻前 / 对手全押 / 我方未过牌 / 强牌
_pre14s = _st14([{"round": 0, "player_id": 1, "action": 300,
                  "action_type": "raise"}], public_cards=[])
check("0914规则14:翻前小额不触发",
      _small_bet_bluff_read(_pre14s, _m14, _effective_category(_pre14s), False)
      is None)
_allin14 = _st14([_CHK14, {"round": 3, "player_id": 1, "action": -2,
                          "action_type": "allin"}])
check("0914规则14:对手全押不触发",
      _small_bet_bluff_read(_allin14, _m14, _effective_category(_allin14), False)
      is None)
check("0914规则14:我方未过牌(对手先下注)不触发",
      _small_bet_bluff_read(_st_call, _m14, _effective_category(_st_call), False)
      is None)
check("0914规则14:强牌(strong)不被接管",
      _small_bet_bluff_read(_small, _m14, _effective_category(_small), True)
      is None)

# F. 决策层：过牌后对手下 300 永不弃牌（跨随机化采样）
_acts14 = set()
for _ in range(120):
    _acts14.add(decide(_small, _m14).get("act"))
check("0914规则14:决策层对 300 小注从不弃牌",
      _acts14.issubset({"call", "raise"}), str(_acts14))
check("0914规则14:决策层两种动作都出现(跟注/反加都试)",
      len(_acts14) >= 2, str(_acts14))


# ============ 2026-09-14 规则15：未成牌时本手最多诈唬两次 ============
# 用户规则：手牌没有与公共牌成牌、采用小额诈唬策略时，本手最多诈唬两次；
# 第三次对手还不弃牌就撤（不再主动投入）。
# 实现：_my_bluff_count 从 history 按「当时」公面张数还原牌力计数；
#       _bluff_cap_guard 在 _normalize 之前把超限的 raise 降级。
from strategy import (_my_bluff_count, _bluff_cap_guard,  # noqa: E402
                      BLUFF_MAX_PER_HAND)

# 公面 [0,4,13,21,26]：无对、无三同花，且与手牌 [10,44] 全程不成牌
_B15 = [0, 4, 13, 21, 26]


def _st15(hist, cards=(10, 44)):
    return parse_request({"num_players": 2, "dealer_id": 1, "my_id": 0,
                          "my_chips": 19500, "my_cards": list(cards),
                          "public_cards": _B15, "history": hist,
                          "hand": 40, "max_hand": 70,
                          "total_win_chips": [0, 0], "total_win_games": [0, 0]})


_PRE15 = [{"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
          {"round": 0, "player_id": 1, "action": 200, "action_type": "raise"},
          {"round": 0, "player_id": 0, "action": 200, "action_type": "call"}]
_F15 = [{"round": 1, "player_id": 0, "action": 300, "action_type": "raise"},
        {"round": 1, "player_id": 1, "action": 300, "action_type": "call"}]
_T15 = [{"round": 2, "player_id": 0, "action": 600, "action_type": "raise"},
        {"round": 2, "player_id": 1, "action": 600, "action_type": "call"}]
_R15 = [{"round": 3, "player_id": 1, "action": 0, "action_type": "check"}]

# A. 计数：翻前不算、每次未成牌的下注各计一次
check("0914规则15:未成牌基准牌型 = HIGH_CARD",
      _effective_category(_st15(_PRE15)) == 0,
      str(_effective_category(_st15(_PRE15))))
check("0914规则15:0 次诈唬", _my_bluff_count(_st15(_PRE15)) == 0)
check("0914规则15:flop 下注(未成牌) → 1 次",
      _my_bluff_count(_st15(_PRE15 + _F15)) == 1,
      str(_my_bluff_count(_st15(_PRE15 + _F15))))
check("0914规则15:flop+turn 下注 → 2 次",
      _my_bluff_count(_st15(_PRE15 + _F15 + _T15)) == 2,
      str(_my_bluff_count(_st15(_PRE15 + _F15 + _T15))))
check("0914规则15:翻前加注不计入诈唬",
      _my_bluff_count(_st15(_PRE15)) == 0)

# B. 当时已成牌的下注不计（flop 就配成一对）
check("0914规则15:flop 已成对的下注不计诈唬",
      _my_bluff_count(_st15(_PRE15 + _F15, cards=(12, 44))) == 0,
      str(_my_bluff_count(_st15(_PRE15 + _F15, cards=(12, 44)))))

# C. 上限：第 3 次机会 → 不再主动投入
_capped = _st15(_PRE15 + _F15 + _T15 + _R15)
check("0914规则15:达到上限(2 次)", _my_bluff_count(_capped) == BLUFF_MAX_PER_HAND)
check("0914规则15:超限 raise + 可过牌 → 改 check",
      _bluff_cap_guard(_capped, {"act": "raise", "num": 800}) == {"act": "check"},
      str(_bluff_cap_guard(_capped, {"act": "raise", "num": 800})))
_facing = _st15(_PRE15 + _F15 + _T15 +
                [{"round": 3, "player_id": 1, "action": 400, "action_type": "raise"}])
check("0914规则15:超限 raise + 面对下注 → 改 call（不再加注诈唬）",
      _bluff_cap_guard(_facing, {"act": "raise", "num": 1200}) == {"act": "call"},
      str(_bluff_cap_guard(_facing, {"act": "raise", "num": 1200})))

# D. 只降级 raise；fold/check/call/allin 一律不动
check("0914规则15:fold 不动",
      _bluff_cap_guard(_capped, {"act": "fold"}) == {"act": "fold"})
check("0914规则15:check 不动",
      _bluff_cap_guard(_capped, {"act": "check"}) == {"act": "check"})
check("0914规则15:call 不动",
      _bluff_cap_guard(_capped, {"act": "call"}) == {"act": "call"})

# E. 未达上限（只诈唬 1 次）→ 不受限
_one = _st15(_PRE15 + _F15 + _R15)
check("0914规则15:仅 1 次诈唬时不受限",
      _bluff_cap_guard(_one, {"act": "raise", "num": 800}) == {"act": "raise",
                                                              "num": 800},
      str(_bluff_cap_guard(_one, {"act": "raise", "num": 800})))

# F. 已成牌（当前一对）→ 无论诈唬几次都不受限
_made = _st15(_PRE15 + _F15 + _T15, cards=(26, 44))
check("0914规则15:已成牌时不受诈唬上限约束",
      _effective_category(_made) != 0
      and _bluff_cap_guard(_made, {"act": "raise", "num": 800})
      == {"act": "raise", "num": 800},
      "cat=%d" % _effective_category(_made))

# G. 决策层：第 3 次机会不再出现 raise
_acts15 = set()
for _ in range(80):
    _acts15.add(decide(_capped, _m14).get("act"))
check("0914规则15:决策层第 3 次机会不再主动加注",
      "raise" not in _acts15, str(_acts15))


# ============ 2026-09-14 规则16：跟 all-in 门槛随局数/对手习惯放宽 ============
# 用户规则：对手 allin 时，剩余局数越少、对手 allin 次数越多，跟的条件越宽；
# 但「弃牌会导致对手锁赢 / 最后一局弃牌直接输」由防锁赢规则优先（在下层）。
from strategy import (_call_allin_relax, _preflop_allin_decide,  # noqa: E402
                      ALLIN_RELAX_CAP, ALLIN_RELAX_HANDS_FULL)


def _st16(hand, cards=(48, 45), my_chips=19900, twc=(0, 0)):
    return parse_request({"num_players": 2, "dealer_id": 1, "my_id": 0,
                          "my_chips": my_chips, "my_cards": list(cards),
                          "public_cards": [],
                          "history": [{"round": 0, "player_id": 1,
                                       "action": 20000,
                                       "action_type": "allin"}],
                          "hand": hand, "max_hand": 70,
                          "total_win_chips": list(twc),
                          "total_win_games": [0, 0]})


def _m16(hands, allins):
    m = OpponentModel()
    m.hands_seen = hands
    m.allin_count = allins
    m.preflop_raise = 3
    m.preflop_call = 5
    m.preflop_fold = 2
    return m


_m16_quiet = _m16(10, 0)
_m16_aggro = _m16(10, 3)

# A. 剩余局数越少 → 放宽越多（对手 allin 频率为 0）
_r_hi = _call_allin_relax(_st16(0), _m16_quiet)     # 剩 69 手
_r_lo = _call_allin_relax(_st16(61), _m16_quiet)    # 剩 8 手
check("0914规则16:剩余局数越少放宽越多",
      _r_lo > _r_hi, "剩69=%.3f 剩8=%.3f" % (_r_hi, _r_lo))
check("0914规则16:剩余充足(≥45手)不放宽", _r_hi == 0.0, str(_r_hi))
check("0914规则16:剩余≤8手时局数维度放宽到满",
      _r_lo > 0.04, str(_r_lo))

# B. 对手 allin 频率越高 → 放宽越多，且小样本折算置信度
_r_f0 = _call_allin_relax(_st16(0), _m16(10, 0))
_r_f1 = _call_allin_relax(_st16(0), _m16(10, 1))
_r_f3 = _call_allin_relax(_st16(0), _m16(10, 3))
check("0914规则16:对手 allin 频率越高放宽越多",
      _r_f0 < _r_f1 < _r_f3,
      "%.3f < %.3f < %.3f" % (_r_f0, _r_f1, _r_f3))
check("0914规则16:小样本按置信度折算(4手1次 < 10手3次)",
      _call_allin_relax(_st16(0), _m16(4, 1)) < _r_f3,
      "%.3f" % _call_allin_relax(_st16(0), _m16(4, 1)))

# C. 上限
check("0914规则16:叠加放宽不超过上限",
      _call_allin_relax(_st16(61), _m16_aggro) <= ALLIN_RELAX_CAP + 1e-9,
      str(_call_allin_relax(_st16(61), _m16_aggro)))

# D. 决策层：中等牌「早期+对手保守」弃 → 「末期+对手爱 allin」跟
#    （用 KQs / ATs：实测这两张的翻转最稳健；AQs 恰在阈值边界，MC 噪声大）
for _nm, _cards in (("KQs", (44, 41)), ("ATs", (48, 33))):
    _e = _preflop_allin_decide(_st16(10, cards=_cards), _m16_quiet).get("act")
    _l = _preflop_allin_decide(_st16(61, cards=_cards), _m16_aggro).get("act")
    check("0914规则16:%s 早期+保守对手 → fold" % _nm, _e == "fold", str(_e))
    check("0914规则16:%s 末期+爱 allin 对手 → allin(条件放宽)" % _nm,
          _l == "allin", str(_l))
check("0914规则16:强牌(AA)任何情况都跟",
      _preflop_allin_decide(_st16(10, cards=(48, 49)), _m16_quiet).get("act")
      == "allin")
check("0914规则16:边缘烂牌(K6o)即使末期+爱 allin 也不跟",
      _preflop_allin_decide(_st16(61, cards=(44, 18)), _m16_aggro).get("act")
      == "fold")

# E. 优先级：防锁赢（doomed）在下层之上——弃牌即送掉比赛时无条件 allin
_doom = _st16(66, cards=(23, 2), my_chips=15000, twc=(-3000, 3000))
check("0914规则16:doomed 状态由规则2 先接管",
      _match_adjust(_doom) == "doomed", _match_adjust(_doom))
check("0914规则16:doomed 时无条件 allin（不受跟注门槛影响）",
      (_lock_win_unified(_doom) or {}).get("act") == "allin",
      str(_lock_win_unified(_doom)))
check("0914规则16:doomed 决策 = allin",
      decide(_doom, _m16_quiet).get("act") == "allin",
      str(decide(_doom, _m16_quiet)))

# ============ 2026-09-14 规则10 强化：靠近锁赢线/终局领先 → 不主动加注 ============
from strategy import _stability_mode, _stability_guard   # noqa: E402


def _st10(hand=65, lead=67, cards=(32, 22), board=(), hist=()):
    return parse_request(dict(num_players=2, dealer_id=1, my_id=0,
                              my_chips=19900, my_cards=list(cards),
                              public_cards=list(board), history=list(hist),
                              hand=hand, max_hand=70,
                              total_win_chips=[lead, -lead],
                              total_win_games=[0, 0]))


check("0914规则10:剩4手+领先 → 求稳",
      _stability_mode(_st10(), _m16_quiet) is True)
check("0914规则10:剩9手+持平 → 不求稳",
      _stability_mode(_st10(hand=60, lead=0), _m16_quiet) is False)
check("0914规则10:落后 → 不求稳(继续施压)",
      _stability_mode(_st10(hand=62, lead=-50), _m16_quiet) is False)
_st10a = _st10()
check("0914规则10:求稳时主动加注→过牌",
      _stability_guard(_st10a, _m16_quiet, {"act": "raise", "num": 500})
      == {"act": "check"},
      str(_stability_guard(_st10a, _m16_quiet, {"act": "raise", "num": 500})))
check("0914规则10:求稳时主动全下→过牌",
      _stability_guard(_st10a, _m16_quiet, {"act": "allin"}) == {"act": "check"},
      str(_stability_guard(_st10a, _m16_quiet, {"act": "allin"})))
_st10b = _st10(board=(31, 13, 24),
               hist=({"round": 0, "player_id": 1, "action": 50,
                      "action_type": "call"},
                     {"round": 1, "player_id": 0, "action": 0,
                      "action_type": "check"},
                     {"round": 1, "player_id": 1, "action": 343,
                      "action_type": "raise"}))
check("0914规则10:求稳时面对下注反加→跟注",
      _stability_guard(_st10b, _m16_quiet, {"act": "raise", "num": 800})
      == {"act": "call"},
      str(_stability_guard(_st10b, _m16_quiet, {"act": "raise", "num": 800})))
_st10c = _st10(cards=(28, 29), board=(30, 44, 40))
check("0914规则10:求稳时强牌(三条)仍可加注",
      _stability_guard(_st10c, _m16_quiet,
                       {"act": "raise", "num": 900}).get("act") == "raise",
      str(_stability_guard(_st10c, _m16_quiet, {"act": "raise", "num": 900})))

# ============ 2026-09-15 规则17：当前盈利越多，跟 all-in 条件越严格 ============
from strategy import _lead_allin_shift, LEAD_ALLIN_SHIFT   # noqa: E402


def _st17(lead, cards=(27, 49)):
    """截图第23手：翻前各100 → 翻牌 8♠Q♠8♥ 双方check → 转牌 J♦ 对手全押。"""
    return parse_request(dict(
        num_players=2, dealer_id=0, my_id=0, my_chips=19900,
        my_cards=list(cards), public_cards=[24, 40, 25, 38],
        hand=22, max_hand=70, total_win_chips=[lead, -lead],
        total_win_games=[0, 0],
        history=[{"round": 0, "player_id": 0, "action": 50, "action_type": "call"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "check"},
                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                 {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                 {"round": 2, "player_id": 1, "action": 19900, "action_type": "allin"}]))


check("0915规则17:大领先(>+50BB) → +0.12",
      _lead_allin_shift(_st17(7084)) == LEAD_ALLIN_SHIFT["big_lead"],
      str(_lead_allin_shift(_st17(7084))))
check("0915规则17:小领先(>+10BB) → +0.07",
      _lead_allin_shift(_st17(1200)) == LEAD_ALLIN_SHIFT["lead"],
      str(_lead_allin_shift(_st17(1200))))
check("0915规则17:均势(±10BB) → +0.02",
      _lead_allin_shift(_st17(0)) == LEAD_ALLIN_SHIFT["even"],
      str(_lead_allin_shift(_st17(0))))
check("0915规则17:小落后(<-10BB) → -0.03",
      _lead_allin_shift(_st17(-1200)) == LEAD_ALLIN_SHIFT["behind"],
      str(_lead_allin_shift(_st17(-1200))))
check("0915规则17:大落后(<-50BB) → -0.08",
      _lead_allin_shift(_st17(-8000)) == LEAD_ALLIN_SHIFT["big_behind"],
      str(_lead_allin_shift(_st17(-8000))))
# 端到端：同一手三条8（对手突袭全押 → eq 打折）——大领先收紧则弃，均势/落后跟
check("0915规则17:大领先时三条8弃(条件更严格)",
      decide(_st17(7084), _m16_quiet).get("act") == "fold",
      str(decide(_st17(7084), _m16_quiet)))
check("0915规则17:均势时三条8跟(不被过度收紧)",
      decide(_st17(0), _m16_quiet).get("act") == "allin",
      str(decide(_st17(0), _m16_quiet)))
check("0915规则17:大落后时三条8跟(搏翻盘)",
      decide(_st17(-8000), _m16_quiet).get("act") == "allin",
      str(decide(_st17(-8000), _m16_quiet)))

# ============ 2026-09-15 方案B：主动下注若「投进去就锁赢」→ 过牌 ============
from strategy import _doom_risk   # noqa: E402

# 真实日志（botbattle-...2f10d6cf 第9手）：我方(座位1)落后 3418、河牌已投 906、
# 剩 61 手（追平线 9100）。再投 815 → 输掉即锁赢（-10278 ≤ -9100）。
_H9 = [{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
       {"round": 0, "player_id": 1, "action": 200, "action_type": "call"},
       {"round": 1, "player_id": 0, "action": 228, "action_type": "raise"},
       {"round": 1, "player_id": 1, "action": 228, "action_type": "call"},
       {"round": 2, "player_id": 0, "action": 378, "action_type": "raise"},
       {"round": 2, "player_id": 1, "action": 378, "action_type": "call"}]
_st9 = parse_request(dict(
    num_players=2, dealer_id=0, my_id=0, my_chips=19094,
    my_cards=[25, 40], public_cards=[19, 24, 39, 50, 4],
    hand=8, max_hand=70, total_win_chips=[-3418, 3418], total_win_games=[0, 0],
    history=list(_H9)))
check("0915方案B:已投口径不 doom(不投入是安全的)",
      _doom_risk(_st9) is False, str(_doom_risk(_st9)))
check("0915方案B:extra 参数生效(再投815即锁赢)",
      _doom_risk(_st9, extra=815) is True, str(_doom_risk(_st9, extra=815)))
check("0915方案B:主动下注会让投入后锁赢 → 触发终局仲裁",
      _endgame_matters(_st9, {"act": "raise", "num": 815}) is True, "")
check("0915方案B:仲裁保留该硬规则（投 815 会越线 → 过牌）",
      _endgame_arbitrate(_st9, _m16_quiet, {"act": "raise", "num": 815},
                         0.5, "normal") == {"act": "check"},
      str(_endgame_arbitrate(_st9, _m16_quiet, {"act": "raise", "num": 815},
                             0.5, "normal")))
check("0915方案B:小额下注(不会越线)不触发硬规则",
      _endgame_matters(_st9, {"act": "raise", "num": 20}) is False, "")
check("0915方案B:端到端=过牌(截图第9手)",
      decide(_st9, _m16_quiet).get("act") == "check",
      str(decide(_st9, _m16_quiet)))
# 对手先加注（过不了牌）→ 原来会升级全押；现在改为终局效用比较
_st9b = parse_request(dict(
    num_players=2, dealer_id=0, my_id=0, my_chips=19094,
    my_cards=[25, 40], public_cards=[19, 24, 39, 50, 4],
    hand=8, max_hand=70, total_win_chips=[-3418, 3418], total_win_games=[0, 0],
    history=list(_H9) + [{"round": 3, "player_id": 1, "action": 815,
                          "action_type": "raise"}]))
# 【2026-09-24】本手 to_call 815 / 剩余 19094 = 4.3%（便宜跟注），
# 弃牌仍有价值 → 仲裁不会升级全押（这是对 09-15「过不了牌就 allin」的收紧）。
check("0924仲裁:便宜跟注(815/19094)不被升成全押",
      _endgame_arbitrate(_st9b, _m16_quiet, {"act": "call"}, 0.5,
                         "normal") == {"act": "call"},
      str(_endgame_arbitrate(_st9b, _m16_quiet, {"act": "call"}, 0.5, "normal")))
_eu9b = _endgame_eu(_st9b, _m16_quiet, 0.5, {"act": "call"}, "normal")
check("0924仲裁:第9手 EU 齐全且全押不是最优（超池全押被跟胜率低）",
      set(_eu9b) >= {"fold", "check", "call", "allin"}
      and _eu9b["allin"] < _eu9b["call"],
      str({k: round(v, 3) for k, v in _eu9b.items()}))
# 决策层若判「弃牌」→ 保持弃牌：弃牌只损失已投 906（lead −8648 未越线）✓
# （端到端只断言「不会被升成 allin」——决策层是 fold 还是 call 受 MC 抽样影响）
check("0915方案B:对手加注时端到端不再出现 allin",
      decide(_st9b, _m16_quiet).get("act") != "allin",
      str(decide(_st9b, _m16_quiet)))

# ---- 转换器：本手投入必须按街累加（旧实现只用本街最大值）----
import json as _json      # noqa: E402
import os as _os          # noqa: E402
import tempfile           # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

_log = {"format": "botbattle.match.log", "format_version": 1,
        "match": {"num_hands": 70},
        "replay": {"events": [
            {"type": "hand_start", "hand": 0, "chips": [19950, 19900],
             "sb": 0, "bb": 1},
            {"type": "deal_hole", "hand": 0,
             "holes": [["8h", "Qs"], ["Jh", "4h"]]},
            {"type": "action", "hand": 0, "player": 0, "action": "raise",
             "amount": 300},
            {"type": "deal_board", "hand": 0, "street": "flop",
             "board": ["6c", "8s", "Jc"], "dealt": ["6c", "8s", "Jc"]},
            {"type": "action", "hand": 0, "player": 0, "action": "raise",
             "amount": 228},
            {"type": "deal_board", "hand": 0, "street": "turn",
             "board": ["6c", "8s", "Jc", "Ad"], "dealt": ["Ad"]},
            {"type": "action", "hand": 0, "player": 0, "action": "raise",
             "amount": 378},
            {"type": "deal_board", "hand": 0, "street": "river",
             "board": ["6c", "8s", "Jc", "Ad", "3s"], "dealt": ["3s"]},
            {"type": "action", "hand": 0, "player": 0, "action": "raise",
             "amount": 815}]}}
_tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                  encoding="utf-8")
_json.dump(_log, _tf)
_tf.close()
_rows = load_botbattle(_tf.name, my_seat=0)
_os.unlink(_tf.name)
_inv = [20000 - _r["my_chips"] for _r, _meta in _rows]
check("0915转换器:投入按街累加(应为 50/300/528/906)",
      _inv == [50, 300, 528, 906], str(_inv))

# ====== 2026-09-16 规则18：搏命区（牌烂开局梭哈 / 牌好慢打再 allin） ======
from strategy import _gamble_zone, _gamble_hand_good, _gamble_plan   # noqa: E402

_A18 = [48, 49]        # 口袋 A（牌好）
_W18 = [25, 11]        # 9♥4♦（烂牌）
_B18 = [44, 25, 6]     # 翻牌 K♠ 9♥ 3♣（彩虹面）
_B18R = [44, 25, 6, 41, 3]   # 河牌（K♠ 9♥ 3♣ + J♦ + 4♠）
_H_LIMP = [{"round": 0, "player_id": 0, "action": 50, "action_type": "call"}]
_H_RAISE = [{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"}]
_H_FCHK = _H_LIMP + [{"round": 1, "player_id": 0, "action": 0,
                      "action_type": "check"}]
_H_FBET = _H_LIMP + [{"round": 1, "player_id": 1, "action": 0,
                      "action_type": "check"},
                     {"round": 1, "player_id": 0, "action": 500,
                      "action_type": "raise"}]
_H_RCHK = _H_LIMP + [{"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
                     {"round": 2, "player_id": 0, "action": 0, "action_type": "check"},
                     {"round": 3, "player_id": 0, "action": 0, "action_type": "check"}]


def _st18(mine, cards=_W18, board=(), hist=None, my_id=1, my_chips=19900,
          hand=16):
    """截图第17手：我方(座位2/player1)本场 mine；翻前双方各 100。"""
    h = _H_LIMP if hist is None else hist
    twc = [-mine, mine] if my_id == 1 else [mine, -mine]
    return parse_request(dict(
        num_players=2, dealer_id=0, my_id=my_id, my_chips=my_chips,
        my_cards=list(cards), public_cards=list(board), history=list(h),
        hand=hand, max_hand=70, total_win_chips=twc,
        total_win_games=[0, 0]))


# ---- 1. 搏命区触发面 ----
check("0916规则18:落后 3822(≈0.96 追平线) → 进搏命区",
      _gamble_zone(_st18(-3822)) is True)
check("0916规则18:中等落后(0.5) → 不进区",
      _gamble_zone(_st18(-2000)) is False
      and decide(_st18(-2000), _m16_quiet).get("act") != "allin",
      str(decide(_st18(-2000), _m16_quiet)))
check("0916规则18:均势 → 不进区", _gamble_zone(_st18(0)) is False)
check("0916规则18:领先 → 不进区", _gamble_zone(_st18(3000)) is False)
check("0916规则18:已越线(追不回) → 仍 allin",
      decide(_st18(-4000), _m16_quiet).get("act") == "allin",
      str(decide(_st18(-4000), _m16_quiet)))

# ---- 2. 牌烂 → 开局 all-in（区内任何街都梭） ----
check("0916规则18b:烂牌(9♥4♦)翻前 → 开局 allin",
      _gamble_hand_good(_st18(-3822)) is False
      and decide(_st18(-3822), _m16_quiet).get("act") == "allin",
      str(decide(_st18(-3822), _m16_quiet)))
check("0916规则18b:烂牌翻后仍 allin（区内每街可搏）",
      _gamble_plan(_st18(-3822, board=_B18, hist=_H_FCHK)) == {"act": "allin", "lk": 1}
      and decide(_st18(-3822, board=_B18, hist=_H_FCHK),
                 _m16_quiet).get("act") == "allin")

# ---- 3. 牌好 → 多过牌再 all-in ----
check("0916规则18b:AA 翻前大盲免费 → 过牌慢打",
      _gamble_hand_good(_st18(-3822, cards=_A18)) is True
      and decide(_st18(-3822, cards=_A18), _m16_quiet) == {"act": "check"},
      str(decide(_st18(-3822, cards=_A18), _m16_quiet)))
check("0916规则18b:AA 翻前需补大盲 → 溜入 call",
      _gamble_plan(_st18(-3822, cards=_A18, my_id=0, my_chips=19950,
                         hist=[])) == {"act": "call"})
check("0916规则18b:AA 翻前遇对手加注 → 收网 allin",
      decide(_st18(-3822, cards=_A18, hist=_H_RAISE),
             _m16_quiet).get("act") == "allin")
check("0916规则18b:AA 翻牌免费(超对) → 过牌",
      _gamble_plan(_st18(-3822, cards=_A18, board=_B18, hist=_H_FCHK))
      == {"act": "check"}
      and decide(_st18(-3822, cards=_A18, board=_B18, hist=_H_FCHK),
                 _m16_quiet) == {"act": "check"})
check("0916规则18b:AA 翻牌面对下注 500 → 收网 allin",
      _gamble_plan(_st18(-3822, cards=_A18, board=_B18, hist=_H_FBET))
      == {"act": "allin", "lk": 1}
      and decide(_st18(-3822, cards=_A18, board=_B18, hist=_H_FBET),
                 _m16_quiet).get("act") == "allin")
check("0916规则18b:AA 一路免费到河牌 → allin（最后一条街不再等）",
      _gamble_plan(_st18(-3822, cards=_A18, board=_B18R, hist=_H_RCHK))
      == {"act": "allin", "lk": 1}
      and decide(_st18(-3822, cards=_A18, board=_B18R, hist=_H_RCHK),
                 _m16_quiet).get("act") == "allin")

# ---- 4. 不在搏命区 → 本规则不接管（交回常规策略） ----
check("0916规则18:均势/领先 → 本规则不接管",
      _gamble_plan(_st18(0, cards=_A18)) is None
      and _gamble_plan(_st18(3000, cards=_A18)) is None)

# ====== 2026-09-16 修复：全下金额未知（协议 -2）不再让 to_call 塌缩 ======
# 背景（截图第1手）：一对 9 跟了 19,160 全下。复现发现只要对手全下在
# history 里没带金额，翻后重放会把它夹到「本轮最大注」→ to_call=1 →
# bot 以为只要跟 1 个筹码 → 任何牌都跟 → _normalize 变成全押。
_allin_neg = parse_request(dict(
    num_players=2, dealer_id=0, my_id=1, my_chips=18606,
    my_cards=[46, 25], public_cards=[29, 36, 8, 30],
    history=[{"round": 0, "player_id": 0, "action": 300, "action_type": "raise"},
             {"round": 0, "player_id": 1, "action": 200, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 0, "action": 540, "action_type": "raise"},
             {"round": 1, "player_id": 1, "action": 540, "action_type": "call"},
             {"round": 2, "player_id": 1, "action": 554, "action_type": "raise"},
             {"round": 2, "player_id": 0, "action": -2, "action_type": "allin"}],
    hand=0, max_hand=70, total_win_chips=[0, 0], total_win_games=[0, 0]))
check("0916解析:全下金额未知(-2)→to_call 按我方剩余筹码(不再塌缩成1)",
      _allin_neg.to_call == 18606 and _allin_neg.pot == 21394,
      "to_call=%s pot=%s" % (_allin_neg.to_call, _allin_neg.pot))
check("0916解析:一对9面对(未知金额)全下 → 弃牌（与有金额时一致）",
      decide(_allin_neg, _m16_quiet) == {"act": "fold"},
      str(decide(_allin_neg, _m16_quiet)))

# ====== 2026-09-16 规则19（对手吓不走→停用小注）+ 规则学习（赢的重复/输的避开） ======
import strategy as _S19                                     # noqa: E402
from match_ctx import MatchContext                           # noqa: E402
from strategy import (_small_bet_futile, _opp_check_bet,      # noqa: E402
                      _blocking_bet_proxy, _lead_bet_proxy,
                      _rule_learn_adjust)


def _m19(resps, hand=10):
    """构造对手「面对我方小注（sf_s 桶）」的反应样本。"""
    m = OpponentModel()
    m.hands_seen = 20
    for i, r in enumerate(resps):
        m.bet_resp_events.append([hand - 5 + i, False, m._BUCKET_SF_SMALL, r])
    return m


_st19 = parse_request(dict(
    num_players=2, dealer_id=0, my_id=1, my_chips=19800,
    my_cards=[46, 25], public_cards=[29, 36, 8],
    history=[{"round": 0, "player_id": 0, "action": 50, "action_type": "call"},
             {"round": 0, "player_id": 1, "action": 100, "action_type": "raise"},
             {"round": 0, "player_id": 0, "action": 50, "action_type": "call"},
             {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 0, "action": 0, "action_type": "check"}],
    hand=10, max_hand=70, total_win_chips=[0, 0], total_win_games=[0, 0]))
_m_stop = _m19(["fold", "call", "call", "call", "call"])   # 小注弃牌率 0.20
_m_fold = _m19(["fold", "fold", "fold", "call", "call"])   # 小注弃牌率 0.60

check("0916规则19:小注样本不足 → 不判「吓不走」",
      _small_bet_futile(_st19, _m19(["call", "call"])) is False)
check("0916规则19:小注弃牌率 0.20 → 判「吓不走」",
      _small_bet_futile(_st19, _m_stop) is True)
check("0916规则19:小注弃牌率 0.60 → 不判「吓不走」",
      _small_bet_futile(_st19, _m_fold) is False)
_S19._prepare_globals(_st19, _m_stop, None)
check("0916规则19:吓不走 → 对手过牌后不再强制小注（改过牌）",
      _opp_check_bet(_st19, True) == {"act": "check"},
      str(_opp_check_bet(_st19, True)))
check("0916规则19:吓不走 → 阻隔注(1/3池)作废",
      _blocking_bet_proxy(_st19, _m_stop, 1) is None)
check("0916规则19:吓不走 → 先手 lead(1/3池)作废",
      _lead_bet_proxy(_st19, _m_stop, 1) is None)
_S19._prepare_globals(_st19, _m_fold, None)
check("0916规则19:对手会弃(0.60) → 小注保留（raise）",
      _opp_check_bet(_st19, True).get("act") == "raise",
      str(_opp_check_bet(_st19, True)))

_ctx19 = MatchContext()
_ctx19.note_rule("规则12 过牌后小注")
_ctx19.note_rule("规则1/4 大注弃牌")        # 归因兜底标签 → 排除
_ctx19.note_rule("规则12 过牌后小注")       # 同手重复 → 只记一次
check("0916规则学习:登记本手规则（去重 + 排除兜底标签）",
      _ctx19.cur_hand_rules == ["规则12 过牌后小注"], str(_ctx19.cur_hand_rules))
_ctx19._record_hand(_st19, net=-100, opp_allin=False)
check("0916规则学习:输掉本手 → 该规则记 1 负",
      _ctx19.rule_stats.get("规则12 过牌后小注") == {"w": 0, "l": 1},
      str(_ctx19.rule_stats))
for _ in range(4):
    _ctx19.note_rule("规则12 过牌后小注")
    _ctx19._record_hand(_st19, net=-100, opp_allin=False)
check("0916规则学习:5 负 0 胜 → 判「输的规则」(-1)",
      _ctx19.rule_score("规则12 过牌后小注") == -1, str(_ctx19.rule_stats))
check("0916规则学习:样本不足 → 不判（0）",
      _ctx19.rule_score("规则13 强牌激进") == 0)
_ctx19.rule_stats["规则10 求稳"] = {"w": 4, "l": 1}
check("0916规则学习:4 胜 1 负 → 判「赢的规则」(+1)",
      _ctx19.rule_score("规则10 求稳") == 1)
_c19 = [{"name": "规则12 过牌后小注", "act": "raise", "suggest": ""},
        {"name": "规则10 求稳", "act": "check", "suggest": ""}]
_a19, _l19 = _rule_learn_adjust(_st19, _m_fold, _ctx19,
                                {"act": "raise", "num": 500}, _c19)
check("0916规则学习:采纳输的规则+加注 → 降级过牌，改记赢的规则",
      _a19 == {"act": "check"} and _l19 == "规则10 求稳",
      "%s / %s" % (_a19, _l19))
_a19b, _ = _rule_learn_adjust(_st19, _m_fold, _ctx19, {"act": "allin"}, _c19)
check("0916规则学习:全下动作不受学习干预", _a19b == {"act": "allin"}, str(_a19b))
_a19c, _ = _rule_learn_adjust(_st19, _m_fold, _ctx19,
                              {"act": "raise", "num": 500},
                              [{"name": "规则13 强牌激进", "act": "raise"}])
check("0916规则学习:记录未知 → 保持加注", _a19c.get("act") == "raise", str(_a19c))

# ============ 2026-09-24 终局效用仲裁：实战第51手（源码根因 + 修复） ============
# 实战第51手（对局日志 hand=50、界面显示「第51手」；我方 = 座位2 = player1）：
#   河牌 9♦A♠8♠6♠7♦ · 我方 A♦4♣（一对 A）· 对手 6♣9♥（两对 9/6）
#   我方 check → 对手下注 192 → 我方 all-in 19,600 → 被跟 → 输掉整场
# 【关键口径】界面「底池 20,592」是 **all-in 之后**的显示值（992 + 19,600）；
#   决策时底池只有 992（双方河牌前各 400 的 800 + 对手这 192）——
#   对手那注只是 19% 池的小注，不是「超池大注」。
# 复原实测：已投 400 / 需跟 192 / 剩余 19,600 / 落后 914 / 剩 19 手（追回线 1450）
#   · 弃牌口径 −1828−2×400 = −2628 > −2900 → 不 doom（弃牌安全）
#   · 跟注口径 −1828−2×592 = −3012 ≤ −2900 → doom（**余量仅 112 筹码**）
#   → 旧结构：决策层按赔率算出「加注 576」，出口补丁把它改写成 19,600 全押。
#   → 新结构：仲裁把 弃牌0.19 / 跟注0.286 / 加注0.322 / 全押0.188 摆开比 EU，
#     并只允许「更保守」的方向 → 全押不再出现。
from strategy import UA_CALL_DAMP   # noqa: E402

_H51 = [{"round": 0, "player_id": 0, "action": 100, "action_type": "call"},
        {"round": 0, "player_id": 1, "action": 100, "action_type": "check"},
        {"round": 1, "player_id": 0, "action": 100, "action_type": "raise"},
        {"round": 1, "player_id": 1, "action": 100, "action_type": "call"},
        {"round": 2, "player_id": 0, "action": 200, "action_type": "raise"},
        {"round": 2, "player_id": 1, "action": 200, "action_type": "call"}]


def _st51(bet=192, hole=(50, 11), chips=19600):
    """第51手河牌决策点：我方(座位2)落后 914，河牌 check 后面对对手下注。"""
    return parse_request(dict(
        num_players=2, dealer_id=0, my_id=1, my_chips=chips,
        my_cards=list(hole), public_cards=[30, 48, 24, 16, 22],
        hand=50, max_hand=70, total_win_chips=[914, -914], total_win_games=[0, 0],
        history=list(_H51) + [
            {"round": 3, "player_id": 1, "action": 0, "action_type": "check"},
            {"round": 3, "player_id": 0, "action": bet, "action_type": "raise"}]))


_h51 = _st51()
check("0924第51手:决策点底池 = 992（非界面 20,592）", _h51.pot == 992, str(_h51.pot))
check("0924第51手:需跟 192 / 已投 400",
      (_h51.to_call, _invested(_h51)) == (192, 400),
      "%s / %s" % (_h51.to_call, _invested(_h51)))
check("0924第51手:弃牌口径不 doom（弃牌安全）",
      _doom_risk(_h51) is False, str(_doom_risk(_h51)))
check("0924第51手:跟注口径 doom（余量仅 112）",
      _doom_risk(_h51, include_to_call=True) is True, "应 True")
check("0924第51手:触发终局仲裁", _endgame_matters(_h51, {"act": "call"}) is True, "")
_eu51 = _endgame_eu(_h51, _m16_quiet, 0.5, {"act": "call"}, "normal")
check("0924第51手:EU 中全押最差（超池全押只剩更强的牌跟）",
      _eu51["allin"] < min(_eu51["call"], _eu51["fold"]),
      {k: round(v, 3) for k, v in _eu51.items()})
check("0924第51手:弃牌的价值被算成非 0（0.19）",
      abs(_eu51["fold"] - 0.190) < 0.03, str(round(_eu51["fold"], 3)))
check("0924第51手:端到端不再输出全押（MC 抖动下也成立）",
      decide(_h51, _m16_quiet).get("act") != "allin",
      str(decide(_h51, _m16_quiet)))
check("0924第51手:单元仲裁（eq 固定 0.5）→ call 192",
      _endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5,
                         "normal") == {"act": "call"},
      str(_endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5, "normal")))
check("0924第51手:全押不会再被生成（仲裁不制造新全押）",
      _endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5,
                         "normal").get("act") != "allin",
      str(_endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5, "normal")))
# 成本函数边界：超池全押的「被跟胜率」必须大幅收窄
check("0924第51手:19.8 倍超池 → 被跟时 eq 收窄到 <2%",
      (0.5 ** (1 + UA_CALL_DAMP * 19600 / 992)) < 0.02, "")
# 强牌（A♦ + 公面 A♠ / 6♥ + 公面 6♠ = 两对）→ 继续明显优于弃牌
_eu_pair = _endgame_eu(_st51(hole=(50, 17)), _m16_quiet, 0.9,
                       {"act": "call"}, "normal")
check("0924第51手:两对时「继续」的 EU 明显高于弃牌",
      _eu_pair["call"] > _eu_pair["fold"] + 0.1,
      str({k: round(v, 3) for k, v in _eu_pair.items()}))
# 真 doom（弃牌口径成立：已投 17,000）→ 规则2-A 无条件全押，不豁免
check("0924:真 doom（筹码只剩 3000）→ 无条件 allin",
      decide(_st51(chips=3000), _m16_quiet).get("act") == "allin",
      str(decide(_st51(chips=3000), _m16_quiet)))

# ============ 2026-09-24 防锁赢全押：越线 → 无条件 allin（用户规则） ============
# 用户规则：「对方快锁赢（再投这笔、输掉就把胜局送出去）→ 直接 all-in」，
# 并明确「越线就全压是合理的」；唯一不算的是**擦线**（用户在第51手指出过）。
# 实战第32手（截图，界面 1-based；我方=座位1）：
#   河牌 2♦4♥3♠9♥K♦ · 我方 9♣J♥（一对 9）· 对手 10♣K♥（一对 K）
#   我方 check → 对手加注至 1,765 → 我方跟注 → 输掉（本场 −1,588）
# 【口径】截图「底池 5,982」是**跟注之后**的显示值；决策点底池 4,217
#   （双方各投 2,991 = 5,982/2；河牌跟注 1,765 → 河牌前各已投 1,226）
from strategy import _sealed_by_call, UA_SEALED_MARGIN   # noqa: E402

_H32 = [{"round": 0, "player_id": 0, "action": 100, "action_type": "raise"},
        {"round": 0, "player_id": 1, "action": 100, "action_type": "call"},
        {"round": 1, "player_id": 0, "action": 300, "action_type": "raise"},
        {"round": 1, "player_id": 1, "action": 300, "action_type": "call"},
        {"round": 2, "player_id": 0, "action": 826, "action_type": "raise"},
        {"round": 2, "player_id": 1, "action": 826, "action_type": "call"},
        {"round": 3, "player_id": 1, "action": 0, "action_type": "check"},
        {"round": 3, "player_id": 0, "action": 1765, "action_type": "raise"}]


def _st32(chips=18774, lead=1588, hand=31):
    """第32手河牌决策点：本场我方 -1,588（lead -3176）、剩 38 手。"""
    return parse_request(dict(
        num_players=2, dealer_id=0, my_id=1, my_chips=chips,
        my_cards=[31, 37], public_cards=[2, 9, 4, 29, 46],
        history=list(_H32), hand=hand, max_hand=70,
        total_win_chips=[lead, -lead], total_win_games=[0, 0]))


_h32 = _st32()
check("0924第32手:决策点底池 4,217（非界面 5,982）", _h32.pot == 4217, str(_h32.pot))
check("0924第32手:弃牌口径不 doom（弃牌仍安全，但只余 72 筹码）",
      _doom_risk(_h32) is False, str(_doom_risk(_h32)))
check("0924第32手:跟注口径越线 3,458（61% 追回线）→ 判为「明显被锁」",
      _doom_risk(_h32, include_to_call=True) is True
      and _sealed_by_call(_h32) is True, "")
check("0924第32手:越线 → 防锁赢全押（带 lk 免检）",
      _endgame_arbitrate(_h32, _m16_quiet, {"act": "call"}, 0.5,
                         "normal") == {"act": "allin", "lk": 1},
      str(_endgame_arbitrate(_h32, _m16_quiet, {"act": "call"}, 0.5, "normal")))
# 【2026-09-24 规则20 收紧】本手牌型 = 一对 9（< 三条）→ 不允许**主动**全押
# （用户规则：主动 allin 只在 防锁赢 / 搏命区 / ≥三条）。仲裁内部仍会升成全押，
# 但出口 `_big_money_guard` 会把它降回决策层动作（跟注 1,765 ≤ 3,000 ✓）。
check("0924第32手:规则20 把关 → 弱牌不再主动全押（降为 call）",
      decide(_h32, _m16_quiet).get("act") == "call",
      str(decide(_h32, _m16_quiet)))
# 关掉硬规则 → 回到效用比较（调参入口）
_keep_sealed = _S2.UA_SEALED_ALLIN
_S2.UA_SEALED_ALLIN = False
check("0924第32手:关掉硬规则 → 回落到 call（调参入口有效）",
      _endgame_arbitrate(_h32, _m16_quiet, {"act": "call"}, 0.5,
                         "normal") == {"act": "call"},
      str(_endgame_arbitrate(_h32, _m16_quiet, {"act": "call"}, 0.5, "normal")))
_S2.UA_SEALED_ALLIN = _keep_sealed
# 擦线不算：第51手只越线 112 筹码（3.9%）< 15% → 不触发全押
check("0924:第51手是擦线（越线 3.9%% 低于门槛 %.0f%%）→ 不触发防锁赢全押"
      % (100 * UA_SEALED_MARGIN),
      _sealed_by_call(_h51) is False
      and _endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5,
                             "normal") == {"act": "call"},
      str(_endgame_arbitrate(_h51, _m16_quiet, {"act": "call"}, 0.5, "normal")))
check("0924:擦线门槛 = %.2f（调 0 = 只要越线就全押）" % UA_SEALED_MARGIN,
      UA_SEALED_MARGIN == 0.15, str(UA_SEALED_MARGIN))

# ============ 2026-09-24 规则20：大额投入闸门（用户规则） ============
# 实战第21手（UI 第21手 = log hand 20）：河牌 10♠6♦A♣3♥K♦，我方 8♣6♣ = 一对 6，
#   对手 8♦A♦ = 一对 A。事件：对手加注至 6,318（1.14 池），我方全押 17,226。
# 【筹码复原（与截图完全吻合）】底池 11,866 = 双方各投 2,774 + 对手这注 6,318；
#   我方剩余 17,226 = 20,000 − 2,774；对手 10,908 = 20,000 − 2,774 − 6,318
#   → 本场 0:0（不存在 doom，也不在搏命区）→ 全押只可能来自「跟注即越线 → 全押」
#   的升级（`UA_SEALED_ALLIN`，本手越线 146% ≥ 15%），而其前提是决策层原本要跟注
#   —— 这正是「对手模型把门槛压到 ~0.21 / 把范围估宽把 eq 抬到 0.46」的地方。
# 用户规则（2026-09-24）：
#   · 需跟 > BIG_CALL_LIMIT(3000) 且有效牌型 < 三条 → 弃牌；
#   · **主动**全押只在 [有效牌型 ≥ 三条 / 翻前超强牌] 时允许（防锁赢、搏命区在
#     decide 入口已经返回，不走这里）。
#   豁免（09-14 用户规则）：应对**对手全下**（any_allin 或需跟 ≥ 剩余筹码）
#     属定向决策，不受金额/牌型限制。
from strategy import (_big_money_guard, _strong_for_big_money,     # noqa: E402
                      BIG_CALL_LIMIT)
from evaluator import THREE_OF_A_KIND                              # noqa: E402


def _st20(cards=(27, 19), lead=0, chips=17226):
    """第21手决策点：翻前各 100，翻牌各 765，转牌各 1,909，河牌对手加注 6,318。"""
    hist = [{"round": 0, "player_id": 1, "action": 100, "action_type": "call"},
            {"round": 0, "player_id": 0, "action": 0, "action_type": "check"},
            {"round": 1, "player_id": 1, "action": 765, "action_type": "raise"},
            {"round": 1, "player_id": 0, "action": 765, "action_type": "call"},
            {"round": 2, "player_id": 1, "action": 1909, "action_type": "raise"},
            {"round": 2, "player_id": 0, "action": 1909, "action_type": "call"},
            {"round": 3, "player_id": 1, "action": 6318, "action_type": "raise"}]
    return parse_request(dict(
        num_players=2, dealer_id=1, my_id=0, my_chips=chips,
        my_cards=list(cards), public_cards=[32, 18, 51, 5, 46],
        hand=20, max_hand=70,
        total_win_chips=[lead, -lead], total_win_games=[0, 0], history=hist))


_h20 = _st20()
check("0924第21手:复原 —— 需跟 6,318 / 底池 11,866 / 已投 2,774 / 一对",
      (_h20.to_call, _h20.pot, _invested(_h20),
       _effective_category(_h20)) == (6318, 11866, 2774, ONE_PAIR),
      "%s/%s/%s" % (_h20.to_call, _h20.pot, _invested(_h20)))
check("0924第21手:本场 0:0 → 不 doom、不在搏命区",
      _doom_risk(_h20) is False and _gamble_zone(_h20) is False, "")
check("0924第21手:跟注口径越线 146% → sealed 成立（内部仍判「明显被锁」）",
      _sealed_by_call(_h20) is True, "")
check("0924第21手:一对 6 → 不属于「大额可投」的牌",
      _strong_for_big_money(_h20) is False,
      str(_strong_for_big_money(_h20)))
check("0924第21手:规则20 —— 弱牌主动全押被降级为弃牌（需跟 6,318 > 3,000）",
      _big_money_guard(_h20, {"act": "allin", "lk": 1}) == {"act": "fold"},
      str(_big_money_guard(_h20, {"act": "allin", "lk": 1})))
check("0924第21手:规则20 —— 大额跟注（6,318 > 3,000）也降级为弃牌",
      _big_money_guard(_h20, {"act": "call"}) == {"act": "fold"},
      str(_big_money_guard(_h20, {"act": "call"})))
check("0924第21手:端到端 = fold（不再跟注 / 不再全押）",
      decide(_h20, _m16_quiet).get("act") == "fold",
      str(decide(_h20, _m16_quiet)))
# 三条（6♣6♥ + 公面 6♦）→ 允许大额投入
_h20set = _st20(cards=(19, 17))
check("0924第21手:三条 → 允许（主动全押保留）",
      _strong_for_big_money(_h20set) is True
      and _big_money_guard(_h20set, {"act": "allin", "lk": 1})
      == {"act": "allin", "lk": 1}, "")
# 真 doom（落后 1,109 → 弃牌口径成立）→ 入口规则2-A 无条件全押，不受本闸门影响
check("0924第21手:落后 1,109（真 doom）→ 仍无条件全押",
      decide(_st20(lead=-2218), _m16_quiet).get("act") == "allin",
      str(decide(_st20(lead=-2218), _m16_quiet)))
# 豁免：应对对手全下（需跟 ≥ 剩余筹码）
_h20allin = parse_request(dict(
    num_players=2, dealer_id=0, my_id=0, my_chips=17226,
    my_cards=[27, 19], public_cards=[32, 18, 51, 5, 46], hand=20, max_hand=70,
    total_win_chips=[0, 0], total_win_games=[0, 0],
    history=[{"round": 0, "player_id": 0, "action": 100, "action_type": "call"},
             {"round": 0, "player_id": 1, "action": 100, "action_type": "check"},
             {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 1, "action": 17226, "action_type": "allin"}]))
check("0924第21手:应对对手全下 → 豁免（闸门不改动动作）",
      _big_money_guard(_h20allin, {"act": "allin", "lk": 1})
      == {"act": "allin", "lk": 1}
      and _big_money_guard(_h20allin, {"act": "call"}) == {"act": "call"}, "")
# 小额跟注（≤3,000）不受影响
_h20small = parse_request(dict(
    num_players=2, dealer_id=1, my_id=0, my_chips=17226,
    my_cards=[27, 19], public_cards=[32, 18, 51, 5, 46], hand=20, max_hand=70,
    total_win_chips=[0, 0], total_win_games=[0, 0],
    history=[{"round": 0, "player_id": 1, "action": 100, "action_type": "call"},
             {"round": 0, "player_id": 0, "action": 0, "action_type": "check"},
             {"round": 1, "player_id": 1, "action": 765, "action_type": "raise"},
             {"round": 1, "player_id": 0, "action": 765, "action_type": "call"},
             {"round": 2, "player_id": 1, "action": 1909, "action_type": "raise"},
             {"round": 2, "player_id": 0, "action": 1909, "action_type": "call"},
             {"round": 3, "player_id": 1, "action": 2000, "action_type": "raise"}]))
check("0924第21手:小额跟注（2,000 ≤ 3,000）放行",
      _h20small.to_call <= BIG_CALL_LIMIT
      and _big_money_guard(_h20small, {"act": "call"}) == {"act": "call"},
      str(_big_money_guard(_h20small, {"act": "call"})))
check("0924规则20:闸门参数（大额跟注线 = %d）" % BIG_CALL_LIMIT,
      BIG_CALL_LIMIT == 3000 and THREE_OF_A_KIND == 3, str(BIG_CALL_LIMIT))

print("\n\u901a\u8fc7 %d / %d" % (len(_PASS), len(_PASS) + len(_FAIL)))
if _FAIL:
    print("\u5931\u8d25:")
    for f in _FAIL:
        print("  FAIL:", f)
    sys.exit(1)
print("\u5168\u90e8\u901a\u8fc7")

