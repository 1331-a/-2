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
                      _fmt_card, BetPatternDetector)

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

print("\n\u901a\u8fc7 %d / %d" % (len(_PASS), len(_PASS) + len(_FAIL)))
if _FAIL:
    print("\u5931\u8d25:")
    for f in _FAIL:
        print("  FAIL:", f)
    sys.exit(1)
print("\u5168\u90e8\u901a\u8fc7")


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

