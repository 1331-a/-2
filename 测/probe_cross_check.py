# -*- coding: utf-8 -*-
"""【2026-10-09】量化 `UA_CROSS_CHECK`（09-15 方案B：有免费过牌、但投入即 doom → 过牌）。

★ 关键做法：直接包装 `_endgame_arbitrate` 本体，拿到它**真正看到的** `chip_action`
  （决策层输出会被 `_aggressive_strong_bet` 等层放大，用「决策层金额」会漏判）。
  同时对每个触发点额外算一次 `_endgame_eu`，回答：
  **这条硬规则是否在否决它自己的 EU 模型认为更好的动作？**

用法：python 测/probe_cross_check.py <log.json> [seat]
不带 seat 则两个座位都跑。
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

import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle              # noqa: E402
from evaluator import evaluate_5, evaluate_7, CATEGORY_NAMES   # noqa: E402

REC = []          # 当前决策点的 (chip_action, state, model, eq, adj)
_orig_arb = S._endgame_arbitrate


def _wrap_arb(*args, **kw):
    """record 参数后原样转发（顺序不固定，按类型识别）。"""
    st = next((x for x in args if hasattr(x, "to_call") and hasattr(x, "stage")), None)
    ca = next((x for x in args if isinstance(x, dict) and "act" in x), None)
    md = next((x for x in args if hasattr(x, "archetype")), None)
    eq = next((x for x in args if isinstance(x, float)), None)
    adj = None
    for x in args:
        if isinstance(x, str) and x in ("doomed", "normal", "desperate",
                                        "protect", "pressure", "steal"):
            adj = x
    if st is not None and ca is not None:
        REC.append((st, ca, md, eq, adj))
    return _orig_arb(*args, **kw)


S._endgame_arbitrate = _wrap_arb


def cat_of(hole, board):
    try:
        cards = list(hole) + list(board)
        if len(cards) < 5:
            return "-"
        ev = evaluate_7(cards) if len(cards) >= 6 else evaluate_5(cards)
        return CATEGORY_NAMES.get(ev[0], "?")
    except Exception:
        return "?"


def outcomes(log):
    obj = json.load(io.open(log, encoding="utf-8"))
    out, cur = {}, None
    for e in obj["replay"]["events"]:
        if e.get("type") == "hand_start":
            cur = e["hand"]
        elif e.get("type") == "settle":
            out[cur] = (e.get("deltas"), e.get("reason"), e.get("pot"))
    return out


def run(log, seat, oc):
    reqs = load_botbattle(log, my_seat=seat) or []
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    rows = []
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
        REC.clear()
        act = S.decide(st, m, ctx, debug=False)
        for st2, ca, md, eq, adj in REC:
            if int(st2.to_call) > 0 or int(st2.my_left) <= 0:
                continue
            if ca.get("act") not in ("raise", "allin"):
                continue
            my_round = max(0, int(getattr(st2, "my_round_bet", 0) or 0))
            add = (max(0, int(ca.get("num", 0) or 0) - my_round)
                   if ca.get("act") == "raise" else max(0, int(st2.my_left)))
            if add <= 0:
                continue
            doom = S._doom_risk(st2, extra=add)
            eu = {}
            try:
                if md is not None and eq is not None:
                    eu = S._endgame_eu(st2, md, eq, ca, adj) or {}
            except Exception:
                eu = {}
            rows.append((meta.get("hand"), st2.stage, st2, ca, add, doom, act, eu))

    print("=" * 108)
    print("座位 %d：`_endgame_arbitrate` 收到「to_call<=0 且动作是 raise/allin」的调用 = %d 次"
          % (seat + 1, len(rows)))
    fire = [r for r in rows if r[5]]
    print("  ★ 其中 `_doom_risk(extra=add)` 成立 → 被 UA_CROSS_CHECK 强行改成 check = %d 次" % len(fire))
    if fire:
        print()
        print("  手 街      我底牌     公面                  牌型  想下注 池     lead    追回线  EU(check) EU(raise) 规则否决了EU?")
        for h, stg, st2, ca, add, doom, act, eu in fire:
            hole_s = " ".join(S._fmt_card(c) for c in (st2.hole or []))
            board_s = " ".join(S._fmt_card(c) for c in (st2.board or []))
            lead = st2.total_win_chips[st2.my_id] - st2.total_win_chips[st2.opp_id]
            line = S._blind_line(st2, S._hands_left(st2), own=False)
            ec = eu.get("check")
            er = eu.get("raise")
            veto = ""
            if ec is not None and er is not None:
                veto = "★是（EU 偏好 raise）" if er > ec else "否"
            print("  %-3d %-8s %-10s %-21s %-5s %-6d %-5s %-7d %-6d %-9s %-9s %s"
                  % (h, stg, hole_s, board_s, cat_of(st2.hole, st2.board), add,
                     st2.pot, lead, line,
                     "%.4f" % ec if ec is not None else "-",
                     "%.4f" % er if er is not None else "-", veto))
        nv = sum(1 for r in fire if r[7].get("check") is not None
                 and r[7].get("raise") is not None
                 and r[7]["raise"] > r[7]["check"])
        nn = sum(1 for r in fire if r[7].get("check") is not None
                 and r[7].get("raise") is not None)
        print()
        print("  ★ 在能比较 EU 的 %d 次里，有 %d 次 **EU 其实偏好 raise**（被硬规则否决）" % (nn, nv))
    print()
    print("  全部调用明细（doom=否的也会列出，便于对比）：")
    print("  手 街      我底牌     公面                  牌型  想下注 池     lead  投入即doom  实际")
    for h, stg, st2, ca, add, doom, act, eu in rows:
        hole_s = " ".join(S._fmt_card(c) for c in (st2.hole or []))
        board_s = " ".join(S._fmt_card(c) for c in (st2.board or []))
        lead = st2.total_win_chips[st2.my_id] - st2.total_win_chips[st2.opp_id]
        print("  %-3d %-8s %-10s %-21s %-5s %-6d %-5s %-6d %-10s %s"
              % (h, stg, hole_s, board_s, cat_of(st2.hole, st2.board), add, st2.pot,
                 lead, "★是" if doom else "否",
                 "%s%s" % (act.get("act"), act.get("num") or "")))


def main():
    log = sys.argv[1]
    oc = outcomes(log)
    for s in ([int(sys.argv[2])] if len(sys.argv) > 2 else [0, 1]):
        run(log, s, oc)


main()
