# -*- coding: utf-8 -*-
"""test_bet_resp.py — 对手响应学习模块（我方下注后对手反应）测试。

验证：
  1. 同手牌采集：我方下注 → 对手 call/raise 记录（按尺寸分桶）；
  2. 跨手推断：上一手以我方下注结尾 → 新手牌补记对手弃牌；
  3. 桶统计 / 弃牌率 / 价值桶选择（选弃牌率最低的尺寸）；
  4. 策略接入：价值注用学习尺寸、诈唬用实测弃牌率；
  5. JSON 序列化往返。
"""
import sys

sys.path.insert(0, ".")

from game_state import parse_request     # noqa: E402
from opponent import OpponentModel, build_model_from_history  # noqa: E402
from strategy import decide              # noqa: E402

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
            "my_chips": 19500, "my_cards": [48, 44], "public_cards": [],
            "history": [], "hand": 0, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


# ---------- 1. 同手牌采集：我翻前开池 → 对手 call（pf 桶） ----------
m = OpponentModel()
r = req(hand=0, my_cards=[48, 44],
        history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"}])
build_model_from_history(m, r, parse_request(r))
check("采集:翻前开池后对手call已记录",
      len(m.bet_resp_events) >= 1 and m.bet_resp_events[0][3] == "call",
      str(m.bet_resp_events))

# ---------- 2. 同手牌采集：我翻牌下注 → 对手加注（sf 桶） ----------
r = req(hand=0, public_cards=[46, 6, 1],
        history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                 {"round": 1, "player_id": 0, "action": 800, "action_type": "raise"},
                 {"round": 1, "player_id": 1, "action": 2000, "action_type": "raise"}])
build_model_from_history(m, r, parse_request(r))
has_sf_raise = any(e[1] is False and e[3] == "raise" for e in m.bet_resp_events)
check("采集:翻牌下注后对手加注已记录", has_sf_raise, str(m.bet_resp_events))

# ---------- 3. 跨手推断：上一手以我方下注结尾 → 新手牌补记弃牌 ----------
r_prev = req(hand=1, public_cards=[46, 6, 1],
             history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                      {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                      {"round": 1, "player_id": 1, "action": 0, "action_type": "check"},
                      {"round": 1, "player_id": 0, "action": 420, "action_type": "raise"}])
build_model_from_history(m, r_prev, parse_request(r_prev))
check("跨手:上一手尾部识别为我方下注", m.resp_tail is not None and m.resp_tail[3], str(m.resp_tail))
r_new = req(hand=2, my_id=1, my_cards=[23, 2], history=[])
build_model_from_history(m, r_new, parse_request(r_new))
has_sf_fold = any(e[3] == "fold" for e in m.bet_resp_events)
check("跨手:新手牌补记对手弃牌", has_sf_fold, str(m.bet_resp_events))

# ---------- 4. 桶统计 / 弃牌率 / 价值桶选择 ----------
m2 = OpponentModel()
# sf_s（小注）3 次：对手都跟 → 弃牌率 0；sf_l（大注）3 次：对手都弃 → 弃牌率 100%
for h in (3, 4, 5):
    m2._add_bet_resp(h, False, "sf_s", "call")
    m2._add_bet_resp(h, False, "sf_l", "fold")
st_s = m2.bet_resp_stats("sf_s", cur_hand=5)
st_l = m2.bet_resp_stats("sf_l", cur_hand=5)
check("统计:sf_s 3样本弃牌率0", st_s and st_s["n"] == 3 and st_s["fold_rate"] == 0.0, str(st_s))
check("统计:sf_l 3样本弃牌率1", st_l and st_l["fold_rate"] == 1.0, str(st_l))
check("统计:样本不足返回None", m2.bet_resp_stats("sf_m", cur_hand=5) is None, "")
# 价值桶选择：应选弃牌率最低的 sf_s
vb = m2.learned_value_bucket(False, cur_hand=5)
check("价值桶:选弃牌率最低的sf_s", vb is not None and vb[0] == "sf_s", str(vb))
# 实测弃牌率查询
lf = m2.learned_fold_rate(False, 800, 100, 1000, cur_hand=5)  # 800/1000=0.8 → sf_l
check("弃牌率:sf_l实测=1.0", lf == 1.0, str(lf))

# ---------- 5. 策略接入：价值注用学习尺寸（对手弃大注→用小注钓） ----------
tptk = req(hand=6, my_cards=[48, 44], public_cards=[46, 6, 1],
           history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                    {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                    {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
a = decide(parse_request(tptk), m2)
check("策略:价值注用学习尺寸(弃小注0%→0.35池≈350)", a == {"act": "raise", "num": 350}, str(a))
# 对照组：无学习数据 → 常规 0.65 池
a0 = decide(parse_request(tptk), OpponentModel())
check("策略:无数据回退常规尺寸(650)", a0 == {"act": "raise", "num": 650}, str(a0))

# ---------- 6. 策略接入：诈唬用实测弃牌率（对手对 medium 弃牌率高 → 敢诈唬） ----------
m3 = OpponentModel()
for h in (7, 8, 9):
    m3._add_bet_resp(h, False, "sf_m", "fold")
air = req(hand=9, my_cards=[24, 17], public_cards=[46, 22, 5],  # 空气牌 K♠7♠3♦
          history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                   {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                   {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}])
a = decide(parse_request(air), m3)
check("策略:实测弃牌率100%→空气诈唬", a.get("act") == "raise", str(a))
# 对照组：无学习数据 → 不诈唬（默认弃牌权益不足）
a0 = decide(parse_request(air), OpponentModel())
check("策略:无数据空气不诈唬", a0.get("act") == "check", str(a0))

# ---------- 7. JSON 序列化往返 ----------
m4 = OpponentModel()
m4._add_bet_resp(0, False, "sf_s", "call")
s = m4.to_json()
m5 = OpponentModel.from_json(s)
check("序列化:事件往返保留", m5.bet_resp_events == m4.bet_resp_events,
      "%s vs %s" % (m5.bet_resp_events, m4.bet_resp_events))

# ---------- 8. 学习优先：翻前开池尺寸（学习覆盖常规 2.5BB） ----------
m6 = OpponentModel()
# 对手对翻前小注(≤2.5BB)全跟、对大注(>4BB)全弃 → 学习选 pf_s → 开池 2.2BB
for h in (10, 11, 12):
    m6._add_bet_resp(h, True, "pf_s", "call")
    m6._add_bet_resp(h, True, "pf_l", "fold")
btn = req(hand=13, my_id=0, my_chips=19950, my_cards=[48, 51], history=[])   # 按钮 SB 已投 50，AA 开池
a = decide(parse_request(btn), m6)
check("学习优先:翻前开池用学习尺寸(2.2BB=220)", a == {"act": "raise", "num": 220}, str(a))
a0 = decide(parse_request(btn), OpponentModel())
check("学习优先:无数据常规开池(2.5BB=250)", a0 == {"act": "raise", "num": 250}, str(a0))

# ---------- 9. 学习优先：面对下注强牌加注（学习覆盖 fishy/常规） ----------
m7 = OpponentModel()
# 对手对翻后小注(≤0.4池)全跟、对大注(>0.75池)全弃 → 学习选 sf_s → 加注 0.35 池
for h in (14, 15, 16):
    m7._add_bet_resp(h, False, "sf_s", "call")
    m7._add_bet_resp(h, False, "sf_l", "fold")
aa_bet2 = req(hand=16, my_id=0, my_chips=19500, my_cards=[48, 50],
              public_cards=[46, 6, 1],
              history=[{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                       {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                       {"round": 1, "player_id": 1, "action": 300, "action_type": "raise"}])
a = decide(parse_request(aa_bet2), m7)
check("学习优先:面对下注加注用学习尺寸(0.35池≈860)", a == {"act": "raise", "num": 860}, str(a))
a0 = decide(parse_request(aa_bet2), OpponentModel())
check("学习优先:无数据常规加注(0.75池≈1500)", a0 == {"act": "raise", "num": 1500}, str(a0))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
