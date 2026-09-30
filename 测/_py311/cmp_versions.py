# -*- coding: utf-8 -*-
"""v50 vs 当前版：同环境（Python 3.11）逐场景决策对拍。

v50 从 ELF 解出的 marshal 字节码直接 exec 加载；
当前版直接从 内容/ 目录 import。
两版共用同一份 request（协议 holdem_action_v1），保证输入完全一致。
"""
import io
import json
import marshal
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"

# ---------------- v50 ----------------
V = {"__name__": "v50mod", "__file__": "poker_bot.py"}
exec(marshal.loads(open(BASE + "/测/_v50_body.bin", "rb").read()), V)

# ---------------- 当前版 ----------------
sys.path.insert(0, BASE + "/内容")
import strategy as NOW          # noqa: E402
import game_state as NG         # noqa: E402
import opponent as NO           # noqa: E402
import match_ctx as NC          # noqa: E402

# ---------------- 工具 ----------------
BL = [{"player_id": 0, "action": -4, "action_type": "blind", "amount": 50, "round": 0},
      {"player_id": 1, "action": -4, "action_type": "blind", "amount": 100, "round": 0}]
BL2 = [{"player_id": 1, "action": -4, "action_type": "blind", "amount": 50, "round": 0},
       {"player_id": 0, "action": -4, "action_type": "blind", "amount": 100, "round": 0}]


def req(cards, board=(), my_chips=19950, twc=(0, 0), hand=10, dealer=0,
        hist=None, opp_chips=None):
    opp_chips = 20000 - 100 if opp_chips is None else opp_chips
    return {"num_players": 2, "dealer_id": dealer, "my_id": 0,
            "my_chips": my_chips, "my_cards": list(cards),
            "public_cards": list(board), "history": list(hist or BL),
            "hand": hand, "max_hand": 70,
            "total_win_chips": list(twc), "total_win_games": [0, 0]}


def run_v50(r):
    try:
        st = V["parse_request"](r)
        m = V["OpponentModel"]()
        a = V["decide"](st, m, None)
        return a, st
    except Exception as e:
        return {"act": "!!EXC %r" % (e,)}, None


def run_now(r):
    try:
        st = NG.parse_request(r)
        m = NO.OpponentModel()
        ctx = NC.MatchContext.from_dict(m.ctx_dict)
        a = NOW.decide(st, m, ctx, debug=False)
        return a, st
    except Exception as e:
        return {"act": "!!EXC %r" % (e,)}, None


def fmt(a):
    if a is None:
        return "None"
    act = a.get("act")
    n = a.get("num")
    return "%s%s" % (act, n if n else "")


# ---------------- 状态一致性自检 ----------------
print("=" * 92)
print("① 状态解析一致性自检（保证两版看到同一个局面）")
print("=" * 92)
probe = req((48, 49), hist=BL)
sv, sn = run_v50(probe)[1], run_now(probe)[1]
for k in ("stage", "to_call", "my_left", "pot", "my_round_bet"):
    v = getattr(sv, k, None) if sv else None
    n = getattr(sn, k, None) if sn else None
    flag = "OK " if v == n else "★差异"
    print("  %-12s v50=%-8s now=%-8s %s" % (k, v, n, flag))

# ---------------- 场景集 ----------------
HANDS = [
    ("AA", (48, 49)), ("KK", (44, 45)), ("QQ", (40, 41)), ("JJ", (36, 37)),
    ("TT", (32, 33)), ("88", (24, 25)), ("55", (12, 13)), ("22", (0, 1)),
    ("AKs", (48, 44)), ("AKo", (48, 45)), ("AQs", (48, 40)), ("AQo", (48, 41)),
    ("KQs", (44, 40)), ("KQo", (44, 41)), ("A9s", (48, 28)), ("A5s", (48, 12)),
    ("KTo", (44, 33)), ("Q8s", (40, 24)), ("76s", (20, 16)), ("54s", (12, 8)),
    ("J9o", (36, 29)), ("T8o", (32, 25)), ("72o", (20, 1)), ("32o", (4, 1)),
]

print()
print("=" * 92)
print("② 翻前 · BTN(我SB) 开池  — 对手无画像")
print("=" * 92)
diffs_pf = []
for name, c in HANDS:
    r = req(c, hist=BL, my_chips=19950)
    av, sn = run_v50(r)[0], run_now(r)[0]
    mark = "" if fmt(av) == fmt(sn) else "   ★不同"
    if mark:
        diffs_pf.append((name, fmt(av), fmt(sn)))
    print("  %-5s  v50=%-12s  now=%-12s%s" % (name, fmt(av), fmt(sn), mark))

print()
print("=" * 92)
print("③ 翻前 · BB 面对对手 open to 300  — 需跟 200")
print("=" * 92)
H_OPEN = BL2 + [{"player_id": 1, "action": 300, "action_type": "raise", "amount": 300, "round": 0}]
diffs_bb = []
for name, c in HANDS:
    r = req(c, hist=H_OPEN, my_chips=19900, dealer=1)
    av, sn = run_v50(r)[0], run_now(r)[0]
    mark = "" if fmt(av) == fmt(sn) else "   ★不同"
    if mark:
        diffs_bb.append((name, fmt(av), fmt(sn)))
    print("  %-5s  v50=%-12s  now=%-12s%s" % (name, fmt(av), fmt(sn), mark))

print()
print("=" * 92)
print("④ 翻后 · 我主动（to_call=0）干面 K♠7♥2♦，底池 600")
print("=" * 92)
# K=52..55(♠=52), 7=20..23(♥=21), 2=0..3(♦=2)
BOARD_DRY = [52, 21, 2]
FLOP_H = BL + [{"player_id": 0, "action": 0, "action_type": "check", "round": 0},
               {"player_id": 1, "action": 0, "action_type": "check", "round": 0},
               {"player_id": 1, "action": 0, "action_type": "check", "round": 1}]
FLOP_CASES = [
    ("顶对KQ", (44, 40)), ("三条77", (20, 21)), ("中一对88", (24, 25)),
    ("听牌A5s", (48, 12)), ("空气QJ", (40, 36)), ("空气T8", (32, 25)),
    ("口袋22", (0, 1)), ("AA超对", (48, 49)),
]
diffs_fl = []
for name, c in FLOP_CASES:
    r = req(c, board=BOARD_DRY, hist=FLOP_H, my_chips=19400)
    av = run_v50(r)[0]
    an = run_now(r)[0]
    mark = "" if fmt(av) == fmt(an) else "   ★不同"
    if mark:
        diffs_fl.append((name, fmt(av), fmt(an)))
    print("  %-9s v50=%-12s now=%-12s%s" % (name, fmt(av), fmt(an), mark))

print()
print("=" * 92)
print("⑤ 翻后 · 面对对手下注（底池 600 → 对手 bet 400，需跟 400）")
print("=" * 92)
FLOP_BET = BL + [{"player_id": 0, "action": 0, "action_type": "check", "round": 0},
                 {"player_id": 1, "action": 0, "action_type": "check", "round": 0},
                 {"player_id": 1, "action": 400, "action_type": "raise", "amount": 400, "round": 1}]
diffs_fb = []
for name, c in FLOP_CASES:
    r = req(c, board=BOARD_DRY, hist=FLOP_BET, my_chips=19400)
    av = run_v50(r)[0]
    an = run_now(r)[0]
    mark = "" if fmt(av) == fmt(an) else "   ★不同"
    if mark:
        diffs_fb.append((name, fmt(av), fmt(an)))
    print("  %-9s v50=%-12s now=%-12s%s" % (name, fmt(av), fmt(an), mark))

print()
print("=" * 92)
print("⑥ 领先 / 落后状态对比（BTN 开池，AKo）")
print("=" * 92)
for label, tw in (("均势", (0, 0)), ("领先 3000", (3000, -3000)),
                  ("落后 3000", (-3000, 3000)), ("落后 8000", (-8000, 8000)),
                  ("落后 13000", (-13000, 13000))):
    r = req((48, 45), hist=BL, twc=tw)
    av = run_v50(r)[0]
    an = run_now(r)[0]
    mark = "" if fmt(av) == fmt(an) else "   ★不同"
    print("  %-10s v50=%-12s now=%-12s%s" % (label, fmt(av), fmt(an), mark))

print()
print("=" * 92)
print("差异汇总")
print("=" * 92)
for tag, ds in (("翻前开池", diffs_pf), ("翻前BB防守", diffs_bb),
                ("翻后主动", diffs_fl), ("翻后面对下注", diffs_fb)):
    print("  %s：%d 处差异" % (tag, len(ds)))
    for name, a, b in ds:
        print("      %-9s v50=%-12s now=%s" % (name, a, b))
