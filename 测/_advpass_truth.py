# -*- coding: utf-8 -*-
"""决定性验证：对 A/B 翻转的 11 个点，用**日志里对手的真实底牌**算精确胜率，比赔率。

若 true_eq >> required ⇒ 当时确实是"被更差的牌逼走"，改成 call 是对的。
"""
import sys, os, io, json, glob, time
from itertools import combinations
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from evaluator import evaluate_7, CATEGORY_NAMES
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"

TARGETS = [("0261012170738-", 2, "flop"), ("0261012170738-", 30, "flop"),
           ("0261012170738-", 32, "flop"), ("0261012172157-", 32, "flop"),
           ("0261012172157-", 34, "flop"), ("0261012172157-", 40, "flop"),
           ("0261012172157-", 57, "turn"), ("0261012185239-", 28, "flop"),
           ("0261012185239-", 29, "turn"), ("0260924154120-", 8, "turn"),
           ("0260924160802-", 12, "flop")]

def p2i(s):
    return PLAT.index(s[0]) * 4 + SUIT.index(s[1]) + 8


def cs(cards):
    return " ".join(PLAT[(c - 8) // 4] + SUIT[(c - 8) % 4] for c in cards)

def exact_vs(hole, board, opp):
    """精确胜率：枚举剩余公共牌，逐步比较 evaluate_7。"""
    deck = [c for c in range(8, 60) if c not in set(hole) | set(board) | set(opp)]
    need = 5 - len(board)
    if need == 0:
        m, o = evaluate_7(list(hole) + list(board)), evaluate_7(list(opp) + list(board))
        return 1.0 if m > o else (0.5 if m == o else 0.0)
    win = tot = 0
    for combo in combinations(deck, need):
        bd = list(board) + list(combo)
        m, o = evaluate_7(list(hole) + bd), evaluate_7(list(opp) + bd)
        win += 1.0 if m > o else (0.5 if m == o else 0.0)
        tot += 1
    return win / tot

logs = sorted(set(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                  + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
print("%-14s %4s %-7s %8s %7s %7s %7s %-9s %-9s %s" % (
    "日志", "手", "街", "to_call", "pot", "需eq", "真实eq", "我方", "对手", "判定"))
tot_slack = 0; n = 0
for p in logs:
    tag = os.path.basename(p)[18:32]
    tg = [t for t in TARGETS if t[0] == tag]
    if not tg:
        continue
    o = json.load(io.open(p, encoding="utf-8"))
    ev = o["replay"]["events"]
    m0 = o["match"]
    seat = 0 if "j1331" in str((m0.get("bot_a") or {}).get("owner_display", "")) else 1
    opp = 1 - seat
    # 对手底牌（internal）
    holes = {}
    for e in ev:
        if e.get("type") == "deal_hole":
            holes[e["hand"]] = ([p2i(c) for c in e["holes"][seat]],
                                [p2i(c) for c in e["holes"][opp]])
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    for req, meta in load_botbattle(p, my_seat=seat):
        h = req.get("hand")
        tgs = [t for t in tg if t[1] == h]
        if not tgs:
            continue
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        if st.stage == tgs[0][2] and int(st.to_call) > 0:
            hp = holes.get(h)
            if not hp:
                continue
            mine, theirs = hp
            eq_t = exact_vs(list(st.hole), list(st.board), list(theirs))
            need = st.to_call / float(st.pot + st.to_call)
            try:
                mc = CATEGORY_NAMES.get(S._effective_category(st), "?")
                oc = CATEGORY_NAMES.get(evaluate_7(list(theirs) + list(st.board))[0], "?")
            except Exception:
                mc = oc = "?"
            tot_slack += (eq_t - need); n += 1
            print("%-14s %4d %-7s %8d %7d %7.3f %7.3f %-9s %-9s %s" % (
                tag, h, st.stage, st.to_call, st.pot, need, eq_t, mc, oc,
                "★该跟" if eq_t >= need else "该弃"))
        S._DECISION_STARTED_WALL = time.time()
        S.decide(st, m, ctx, debug=False)
print()
print("命中 %d 点 | 平均余量 (真实eq − 需eq) = %+.3f" % (n, tot_slack / max(1, n)))
