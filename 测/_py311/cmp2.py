# -*- coding: utf-8 -*-
"""v50 vs 当前版：逐场景对拍（v2：已按真实平台协议校准）。

【校准要点（从真实日志 botbattle_log 反推）】
  · history **只含动作**，不含盲注条目；盲注由 GameState 从 my_chips 推导。
  · `action`：raise 是 **raise-to 累计额**；call/check 为 0；fold 为 -1；allin 为 -2。
  · 牌号 n = rank*4 + suit（rank 2..14）：
      2=0..3  3=4..7  4=8..11  5=12..15  6=16..19  7=20..23  8=24..27
      9=28..31  T=32..35  J=36..39  Q=40..43  K=44..47  A=48..51
      花色 0=♠ 1=♥ 2=♦ 3=♣
  · 单挑：dealer = SB，翻前 dealer 先行动；翻后非 dealer(BB) 先行动。
"""
import io
import marshal
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"

V = {"__name__": "v50mod", "__file__": "poker_bot.py"}
exec(marshal.loads(open(BASE + "/测/_v50_body.bin", "rb").read()), V)

sys.path.insert(0, BASE + "/内容")
import strategy as NOW          # noqa: E402
import game_state as NG         # noqa: E402
import opponent as NO           # noqa: E402
import match_ctx as NC          # noqa: E402


def A(pid, act, at, rnd):
    return {"player_id": pid, "action": act, "action_type": at, "round": rnd}


def req(cards, board=(), my_chips=19950, twc=(0, 0), hand=10, dealer=0, hist=None):
    return {"num_players": 2, "dealer_id": dealer, "my_id": 0,
            "my_chips": my_chips, "my_cards": list(cards),
            "public_cards": list(board), "history": list(hist or []),
            "hand": hand, "max_hand": 70,
            "total_win_chips": list(twc), "total_win_games": [0, 0]}


def run_v50(r):
    try:
        st = V["parse_request"](r)
        return V["decide"](st, V["OpponentModel"](), None), st
    except Exception as e:
        return {"act": "!!EXC %r" % (e,)}, None


def run_now(r):
    try:
        st = NG.parse_request(r)
        m = NO.OpponentModel()
        return NOW.decide(st, m, NC.MatchContext.from_dict(m.ctx_dict),
                          debug=False), st
    except Exception as e:
        return {"act": "!!EXC %r" % (e,)}, None


def fmt(a):
    if a is None:
        return "None"
    return "%s%s" % (a.get("act"), a.get("num") or "")


def line(tag, r, extra=""):
    av, sv = run_v50(r)
    an, sn = run_now(r)
    same = fmt(av) == fmt(an)
    print("  %-22s v50=%-13s now=%-13s %s%s" % (
        tag, fmt(av), fmt(an), "" if same else "★不同", extra))
    return (tag, fmt(av), fmt(an)) if not same else None


# ================= 状态自检 =================
print("=" * 96)
print("① 状态自检：翻前我 SB(dealer=0) 未行动 / 翻后我 BB(dealer=1) 先行动")
print("=" * 96)
r1 = req((48, 49))
av, sv = run_v50(r1)
an, sn = run_now(r1)
print("  翻前: v50(to_call=%s pot=%s stage=%s)  now(to_call=%s pot=%s stage=%s)" % (
    sv.to_call, sv.pot, sv.stage, sn.to_call, sn.pot, sn.stage))
# 翻后：对手SB平跟 → 我check → 翻牌我先行动
FLOP_PRE = [A(1, 0, "call", 0), A(0, 0, "check", 0)]
r2 = req((45, 41), board=(44, 21, 2), my_chips=19900, dealer=1, hist=FLOP_PRE)
av, sv = run_v50(r2)
an, sn = run_now(r2)
print("  翻后: v50(to_call=%s pot=%s stage=%s)  now(to_call=%s pot=%s stage=%s)" % (
    sv.to_call, sv.pot, sv.stage, sn.to_call, sn.pot, sn.stage))
print("  公面 K♠7♥2♦ = %s；手牌 K♥Q♥ = %s → 应为顶对" % ([44, 21, 2], [45, 41]))
print("  now 牌型判定 = %s (0高牌/1一对/2两对/3三条)" % NOW._effective_category(sn))

# ================= 场景集 =================
print()
print("=" * 96)
print("② 翻前开池（我 SB/dealer，无历史）")
print("=" * 96)
HANDS = [("AA", (48, 49)), ("KK", (44, 45)), ("QQ", (40, 41)), ("JJ", (36, 37)),
         ("TT", (32, 33)), ("88", (24, 25)), ("55", (12, 13)), ("22", (0, 1)),
         ("AKs", (48, 44)), ("AKo", (48, 45)), ("AQs", (48, 40)), ("KQs", (44, 40)),
         ("A9s", (48, 28)), ("A5s", (48, 12)), ("KTo", (44, 33)), ("Q8s", (40, 24)),
         ("76s", (20, 16)), ("54s", (12, 8)), ("J9o", (36, 29)), ("72o", (20, 1))]
d2 = []
for n, c in HANDS:
    d = line(n, req(c, my_chips=19950, dealer=0))
    if d:
        d2.append(d)

print()
print("=" * 96)
print("③ 翻前 BB 面对 SB open to 300（需跟 200）")
print("=" * 96)
H_OPEN = [A(1, 300, "raise", 0)]
d3 = []
for n, c in HANDS:
    d = line(n, req(c, my_chips=19900, dealer=1, hist=H_OPEN))
    if d:
        d3.append(d)

print()
print("=" * 96)
print("④ 翻后主动（翻牌我先行动，公面 K♠7♥2♦ 彩虹，底池 200）")
print("=" * 96)
FLOP_CASES = [
    ("顶对KQ", (45, 41)), ("三条77", (20, 22)), ("超对88", (24, 25)),
    ("同花听A5s", (48, 12)), ("空气QJ", (41, 37)), ("空气T8", (33, 25)),
    ("小对22", (0, 1)), ("超对AA", (48, 49)), ("两对K7", (45, 22)),
]
d4 = []
for n, c in FLOP_CASES:
    d = line(n, req(c, board=(44, 21, 2), my_chips=19900, dealer=1, hist=FLOP_PRE))
    if d:
        d4.append(d)

print()
print("=" * 96)
print("⑤ 翻后面对下注（底池 200 → 对手 bet 140 ≈ 70%）")
print("=" * 96)
FLOP_BET = FLOP_PRE + [A(0, 0, "check", 1), A(1, 140, "raise", 1)]
d5 = []
for n, c in FLOP_CASES:
    d = line(n, req(c, board=(44, 21, 2), my_chips=19900, dealer=1, hist=FLOP_BET))
    if d:
        d5.append(d)

print()
print("=" * 96)
print("⑥ 翻后面对大注（底池 200 → 对手 bet 600 ≈ 3×池）")
print("=" * 96)
FLOP_BIG = FLOP_PRE + [A(0, 0, "check", 1), A(1, 600, "raise", 1)]
d6 = []
for n, c in FLOP_CASES:
    d = line(n, req(c, board=(44, 21, 2), my_chips=19900, dealer=1, hist=FLOP_BIG))
    if d:
        d6.append(d)

print()
print("=" * 96)
print("⑦ 领先 / 落后（翻前开池 AKo / 72o）")
print("=" * 96)
d7 = []
for label, tw in (("均势", (0, 0)), ("领先4000", (4000, -4000)),
                  ("落后4000", (-4000, 4000)), ("落后9000", (-9000, 9000)),
                  ("落后15000", (-15000, 15000))):
    for hn, c in (("AKo", (48, 45)), ("72o", (20, 1))):
        d = line("%s %s" % (label, hn), req(c, my_chips=19950, dealer=0, twc=tw))
        if d:
            d7.append(d)

print()
print("=" * 96)
print("差异汇总")
print("=" * 96)
for tag, ds in (("② 翻前开池", d2), ("③ BB 防守", d3), ("④ 翻后主动", d4),
                ("⑤ 面对70%注", d5), ("⑥ 面对3倍池注", d6), ("⑦ 领先/落后", d7)):
    print("  %-14s %d 处差异" % (tag, len(ds)))
