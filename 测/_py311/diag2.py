# -*- coding: utf-8 -*-
"""诊断：落后时该推不推 / 领先时该攻不攻 的根因。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"
sys.path.insert(0, BASE + "/内容")
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as MC        # noqa: E402


def req(cards, my_chips=19950, twc=(0, 0), hand=10, dealer=0, hist=None):
    return {"num_players": 2, "dealer_id": dealer, "my_id": 0,
            "my_chips": my_chips, "my_cards": list(cards),
            "public_cards": [], "history": list(hist or []),
            "hand": hand, "max_hand": 70,
            "total_win_chips": list(twc), "total_win_games": [0, 0]}


def probe(tag, r):
    st = G.parse_request(r)
    m = O.OpponentModel()
    ctx = MC.MatchContext.from_dict(m.ctx_dict)
    lead = st.total_win_chips[0] - st.total_win_chips[1]
    hl = S._hands_left(st)
    ln = S._blind_line(st, hl, own=False)
    print("=" * 88)
    print("【%s】lead=%s to_call=%s invested=%s hands_left=%s 追回线=%s" % (
        tag, lead, st.to_call, S._invested(st), hl, ln))
    print("  doom不等式 lead-2*inv=%-8s  vs  -2*line=%-8s → doom=%s" % (
        lead - 2 * S._invested(st), -2 * ln, S._doom_risk(st)))
    print("  _match_adjust = %s" % S._match_adjust(st))
    print("  _doom_plan    = %s" % (S._doom_plan(st, m),))
    print("  _gamble_hand_good = %s  (翻前 AKo 百分位=%.3f, 门槛=%s)" % (
        S._gamble_hand_good(st),
        (lambda: __import__("ranges").hand_percentile(list(st.hole)))()
        if hasattr(__import__("ranges"), "hand_percentile") else -1,
        getattr(S, "GAMBLE_GOOD_PCT", "?")))
    print("  _gamble_zone  = %s   _gamble_plan = %s" % (
        S._gamble_zone(st), S._gamble_plan(st, m)))
    print("  _stability_mode = %s" % S._stability_mode(st, m))
    S.DecisionLogger._quiet = True
    S.DecisionLogger.reset()
    a = S.decide(st, m, ctx, debug=True)
    print("  → decide = %s" % (a,))
    for rec in S.DecisionLogger._records[-4:]:
        print("     [log] %-6s rule=%s" % (rec.get("action"), rec.get("rule")))
    print()


probe("落后9000 AKo（应 allin，实为 call）", req((48, 45), twc=(-9000, 9000)))
probe("落后15000 AKo", req((48, 45), twc=(-15000, 15000)))
probe("领先4000 AKo（v50 raise / 现 call）", req((48, 45), twc=(4000, -4000)))
probe("领先8000 AKo", req((48, 45), twc=(8000, -8000)))
