# -*- coding: utf-8 -*-
"""诊断：为什么当前版比 v50 保守（翻后弃牌过多 / 落后不推）。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"C:/Users/HP/WorkBuddy/德扑双人机器人测试"
sys.path.insert(0, BASE + "/内容")
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as MC        # noqa: E402

BL = [{"player_id": 0, "action": -4, "action_type": "blind", "amount": 50, "round": 0},
      {"player_id": 1, "action": -4, "action_type": "blind", "amount": 100, "round": 0}]


def req(cards, board=(), my_chips=19950, twc=(0, 0), hand=10, dealer=0, hist=None):
    return {"num_players": 2, "dealer_id": dealer, "my_id": 0,
            "my_chips": my_chips, "my_cards": list(cards),
            "public_cards": list(board), "history": list(hist or BL),
            "hand": hand, "max_hand": 70,
            "total_win_chips": list(twc), "total_win_games": [0, 0]}


def probe(tag, r):
    st = G.parse_request(r)
    m = O.OpponentModel()
    ctx = MC.MatchContext.from_dict(m.ctx_dict)
    print("=" * 88)
    print("【%s】stage=%s to_call=%s pot=%s 底池=%s" % (tag, st.stage, st.to_call, st.pot, st.pot))
    print("  lead=%s invested=%s hands_left=%s line=%s" % (
        st.total_win_chips[0] - st.total_win_chips[1], S._invested(st),
        S._hands_left(st), S._blind_line(st, S._hands_left(st), own=False)))
    for fn, call in (
        ("_match_adjust", lambda: S._match_adjust(st)),
        ("_fold_out_active", lambda: S._fold_out_active(st)),
        ("_doom_risk", lambda: S._doom_risk(st)),
        ("_lock_win_unified", lambda: S._lock_win_unified(st, m)),
        ("_doom_plan", lambda: S._doom_plan(st, m)),
        ("_gamble_zone", lambda: S._gamble_zone(st)),
        ("_gamble_hand_good", lambda: S._gamble_hand_good(st)),
        ("_gamble_plan", lambda: S._gamble_plan(st, m)),
        ("_effective_category", lambda: S._effective_category(st)),
        ("should_avoid_risk", lambda: S.should_avoid_risk(st)),
        ("_stability_mode", lambda: S._stability_mode(st, m)),
        ("_strong_for_big_money", lambda: S._strong_for_big_money(st)),
        ("_opp_range_pct", lambda: S._opp_range_pct(m, False, 0)),
        ("_opp_street_raises", lambda: S._opp_street_raises(st)),
        ("faces_bet", lambda: getattr(m, "faces_bet", "?")),
        ("eff_fold_to_bet", lambda: m.eff_fold_to_bet()),
    ):
        try:
            print("  %-22s = %s" % (fn, call()))
        except Exception as e:
            print("  %-22s !! %r" % (fn, e))
    # 决策日志
    S.DecisionLogger._quiet = True
    S.DecisionLogger.reset()
    a = S.decide(st, m, ctx, debug=True)
    print("  → decide = %s" % (a,))
    for rec in S.DecisionLogger._records[-3:]:
        info = rec.get("info") or {}
        hm = info.get("hand") or {}
        print("     [log] act=%-6s rule=%-18s eq=%-6s cat=%s to_call=%s" % (
            rec.get("action"), rec.get("rule"), hm.get("eq"),
            hm.get("cat_name"), hm.get("to_call")))
    print()


# ---- A. 落后 16000 + AKo（翻前，to_call=50）----
probe("A 落后16000 AKo 翻前", req((48, 45), hist=BL, twc=(-8000, 8000)))

# ---- B. 顶对 KQ 面对 2/3 池下注 ----
BOARD_DRY = [52, 21, 2]      # K♠ 7♥ 2♦
FLOP_BET = BL + [{"player_id": 0, "action": 0, "action_type": "check", "round": 0},
                 {"player_id": 1, "action": 0, "action_type": "check", "round": 0},
                 {"player_id": 1, "action": 400, "action_type": "raise", "amount": 400, "round": 1}]
probe("B 顶对KQ 面对400下注", req((44, 40), board=BOARD_DRY, hist=FLOP_BET, my_chips=19400))

# ---- C. 中一对 88 面对同样下注 ----
probe("C 中对88 面对400下注", req((24, 25), board=BOARD_DRY, hist=FLOP_BET, my_chips=19400))

# ---- D. 听牌 A5s 面对同样下注 ----
probe("D 听牌A5s 面对400下注", req((48, 12), board=BOARD_DRY, hist=FLOP_BET, my_chips=19400))
