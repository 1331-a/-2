# -*- coding: utf-8 -*-
"""【2026-10-09】追踪「牌面好却一路过牌」的成因。

用法：
  python 测/trace_passive.py <log.json> [seat] [hand1 hand2 ...]
默认 seat=1（座位2），若不指定 hand 则列出该座位所有「翻后 to_call==0」的决策点，
并逐层打印出口链轨迹，定位把动作改成 check 的那一层。

★ 不改 bot 代码：全部用运行时 monkey-patch。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "内容"))

import strategy as S            # noqa: E402
import game_state as G          # noqa: E402
import opponent as O            # noqa: E402
import match_ctx as M           # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402
from evaluator import evaluate_5, evaluate_7, CATEGORY_NAMES   # noqa: E402

CHAIN = ["_lock_win_tail_guard", "_bet_cap_guard", "_aggressive_strong_bet",
         "_bluff_cap_guard", "_stability_guard", "_normalize",
         "_endgame_arbitrate", "_big_money_guard", "_cheap_call_guard",
         "_doom_call_upgrade"]

TRACE = []


def _n(a):
    if not isinstance(a, dict):
        return repr(a)[:18]
    return "%s%s" % (a.get("act"), a.get("num") or "")


def install():
    """包裹出口链 10 层 + 入口两个短路函数。"""
    for nm in CHAIN:
        orig = getattr(S, nm)

        def mk(n, f):
            def w(*a, **k):
                b = next((x for x in a if isinstance(x, dict) and "act" in x), None)
                r = f(*a, **k)
                TRACE.append((n, _n(b), _n(r)))
                return r
            return w
        setattr(S, nm, mk(nm, orig))
    for nm in ("_lock_win_unified", "_gamble_plan"):
        orig = getattr(S, nm)

        def mke(n, f):
            def w(*a, **k):
                r = f(*a, **k)
                if isinstance(r, dict) and "act" in r:
                    TRACE.append(("入口:" + n, "", _n(r)))
                return r
            return w
        setattr(S, nm, mke(nm, orig))


def cat_of(hole, board):
    try:
        cards = list(hole) + list(board)
        if len(cards) < 5:
            return "-"
        ev = evaluate_7(cards) if len(cards) >= 6 else evaluate_5(cards)
        return CATEGORY_NAMES.get(ev[0], "?")
    except Exception:
        return "?"


def main():
    log = sys.argv[1]
    seat = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    want = set(int(x) for x in sys.argv[3:])
    install()

    reqs = load_botbattle(log, my_seat=seat) or []
    print("日志=%s  我方座位=%d  决策点总数=%d" % (os.path.basename(log), seat, len(reqs)))
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)

    n_passive = 0
    for req, meta in reqs:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        h = int(meta.get("hand"))
        if want and h not in want:
            continue
        if not want and (st.stage == "preflop" or st.to_call != 0):
            continue
        TRACE.clear()
        act = S.decide(st, m, ctx, debug=False)
        n_passive += 1
        lead = st.total_win_chips[st.my_id] - st.total_win_chips[st.opp_id]
        print("=" * 96)
        hole_s = " ".join(S._fmt_card(c) for c in (st.hole or []))
        board_s = " ".join(S._fmt_card(c) for c in (st.board or [])) or "(无)"
        print("手%-3d %-8s 我=%-9s 公面=%-22s 牌型=%-5s 池=%-6s to_call=%-5s my_left=%s"
              % (h, st.stage, hole_s, board_s, cat_of(st.hole, st.board),
                 st.pot, st.to_call, st.my_left))
        print("      lead=%-7d 剩局=%-3d 追回线=%-5d _match_adjust=%s  出口→ %s"
              % (lead, S._hands_left(st), S._blind_line(st, S._hands_left(st), own=False),
                 S._match_adjust(st), _n(act)))
        if TRACE:
            print("      轨迹:", " | ".join(
                "%s %s→%s" % (t[0], t[1] or "-", t[2]) for t in TRACE))
        else:
            print("      轨迹: (无出口链 = 入口已返回)")
    print()
    print("共检查 %d 个决策点" % n_passive)


main()
