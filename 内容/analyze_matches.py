# -*- coding: utf-8 -*-
"""analyze_matches.py — 实战对局复盘分析器（只读，不改策略）。

对每局日志输出：
  ① 结果概览（我方净胜 / 领先曲线极值）
  ② 亏损最大 + 盈利最大的若干手（含逐街动作、本手净胜、每步的 eq/牌型/采纳规则）
  ③ 决策扫描：把可疑决策归类（锁赢类 / 大额投入 / 薄跟注 / 听牌跟大注 / 河牌乱接）

用法：python analyze_matches.py <log.json> [<log.json> ...]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategy as S                                          # noqa: E402
from game_state import parse_request, INIT_CHIPS               # noqa: E402
from opponent import OpponentModel, build_model_from_history    # noqa: E402
from match_ctx import MatchContext                             # noqa: E402
from botbattle_log import load_botbattle                       # noqa: E402

STREET_CN = {"preflop": "翻前", "flop": "翻牌", "turn": "转牌", "river": "河牌"}
ACT_CN = {"raise": "加注到", "call": "跟", "check": "过牌",
          "fold": "弃牌", "allin": "全押"}


def detect_seat(obj):
    """我方座位：优先 owner 含 j1331 且名字不是对手的那个。"""
    m = obj.get("match") or {}
    for idx, key in ((0, "bot_a"), (1, "bot_b")):
        b = m.get(key) or {}
        if "j1331" in str(b.get("owner_display", "")) and \
                "fffmvp5" not in str(b.get("display_name", "")) and \
                "cloud" not in str(b.get("display_name", "")):
            return idx
    for idx, key in ((0, "bot_a"), (1, "bot_b")):
        b = m.get(key) or {}
        if "j1331" in str(b.get("owner_display", "")):
            return idx
    return 0


def parse_hands(obj):
    """→ {hand: dict(holes_all, board, acts=[(street,pid,act,amt)], reason, pot)}"""
    hands, cur, street = {}, None, 0
    for e in (obj.get("replay") or {}).get("events") or []:
        t = e.get("type")
        if t == "hand_start":
            cur = {"holes_all": None, "board": [], "acts": [], "reason": "",
                   "pot": 0}
            hands[e.get("hand")] = cur
            street = 0
        elif cur is None:
            continue
        elif t == "deal_hole":
            cur["holes_all"] = e.get("holes")
        elif t == "deal_board":
            street = {"flop": 1, "turn": 2, "river": 3}.get(e.get("street"),
                                                             street)
            cur["board"] = list(e.get("board") or [])
        elif t == "action":
            cur["acts"].append((street, e.get("player"), e.get("action"),
                                e.get("amount")))
        elif t == "settle":
            cur["reason"] = e.get("reason", "")
            cur["pot"] = e.get("pot", 0)
            cur["board"] = list(e.get("board") or cur["board"])
    return hands


def per_hand_delta(obj, seat):
    out = {}
    for e in (obj.get("replay") or {}).get("events") or []:
        if e.get("type") == "settle":
            d = e.get("deltas") or [0, 0]
            out[e.get("hand")] = int(d[seat])
    return out


def replay_decisions(path, seat):
    """用决策逻辑重放（安静模式），返回决策记录列表。

    注意：`decide(debug=...)` 内部会调用 `DecisionLogger.enable(debug ...)`，
    会把外部的手动 enable 覆盖掉 → 必须传 debug=True；再用 `_quiet=True`
    抑制 stderr 打印（`log()` 里 `if not block or cls._quiet: return`）。
    """
    reqs = load_botbattle(path, my_seat=seat) or []
    S.DecisionLogger._quiet = True
    S.DecisionLogger.reset()
    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)
    states = []
    for req, meta in reqs:
        try:
            st = parse_request(req)
            build_model_from_history(model, req, st)
            ctx.update(st)
            ctx.sync_baseline(st)
            S.decide(st, model, ctx, debug=True)
            states.append((meta, st))
        except Exception:
            pass
    recs = list(S.DecisionLogger._records)
    S.DecisionLogger.enable(False)
    S.DecisionLogger._quiet = False
    return recs, states


def fmt(h, seat):
    ha = h.get("holes_all")
    hole = " ".join(ha[seat]) if ha and len(ha) > seat else "?"
    board = " ".join(h.get("board") or []) or "-"
    seq = []
    for _st, pid, act, amt in h.get("acts") or []:
        who = "我" if pid == seat else "敌"
        a = ACT_CN.get(act, act)
        if act in ("raise", "allin"):
            a += str(amt)
        elif act == "call" and amt:
            a += "(到%s)" % amt
        seq.append(who + a)
    return hole, board, " ".join(seq)


def scan(recs):
    """可疑决策归类（全部信息取自决策记录自身，避免与 states 错位配对）。

    注意：一次决策可能写多条记录（锁赢入口 / 决策层 / 出口各一条）
    → 用 (hand, street, action, to_call) 去重。
    """
    hits = {"① 锁赢类（跟注即锁赢）": [], "② 大额投入 (>3000)": [],
            "③ 薄跟注（余量 <0.05）": [], "④ 河牌接大注 (>0.5池)": [],
            "⑤ 主动全押": [], "⑥ 超池加注 (>1.5池)": []}
    seen = set()
    for r in recs:
        info = r.get("info") or {}
        lk = info.get("lock") or {}
        hm = info.get("hand") or {}
        act = r.get("action")
        tc = int(hm.get("to_call") or 0)
        pot = int(r.get("pot") or 0)
        key = (r.get("hand"), r.get("street"), act, tc)
        if key in seen:
            continue
        seen.add(key)
        try:
            eq = float(hm.get("eq")) if hm.get("eq") is not None else None
        except Exception:
            eq = None
        lead = lk.get("lead")
        inv = int(lk.get("invested") or 0)
        exp = int(lk.get("exposure") or 0)
        line = int(lk.get("line") or 0)
        tag = "手%-3s %-3s %-10s" % (r.get("hand"),
                                    STREET_CN.get(r.get("street"), ""),
                                    act)
        # ① 跟注即锁赢（doom 跟注口径，本地重算，不依赖 state）
        if act == "call" and line > 0 and lead is not None:
            if lead - 2 * exp <= -2 * line:
                hits["① 锁赢类（跟注即锁赢）"].append(
                    (tag, "跟注即锁赢 tc=%d 已投=%d 敞口=%d 领先=%+d 追回线=%d"
                     % (tc, inv, exp, lead, line)))
        # ② 单笔大额投入
        if inv > 3000 and act in ("call", "allin"):
            hits["② 大额投入 (>3000)"].append(
                (tag, "已投=%d tc=%d eq=%s 规则=%s" % (inv, tc, eq,
                                                       r.get("rule"))))
        # ③ 薄跟注
        if act == "call" and eq is not None and pot > 0:
            req = tc / float(pot + tc)
            if 0 < eq - req < 0.05:
                hits["③ 薄跟注（余量 <0.05）"].append(
                    (tag, "eq=%.3f 需=%.3f 余量=%+.3f tc=%d 池=%d"
                     % (eq, req, eq - req, tc, pot)))
        # ④ 河牌接大注
        if act == "call" and r.get("street") == "river" and tc > 0.5 * pot > 0:
            hits["④ 河牌接大注 (>0.5池)"].append(
                (tag, "tc=%d 池=%d eq=%s 规则=%s" % (tc, pot, eq,
                                                     r.get("rule"))))
        # ⑤ 主动全押
        if act == "allin":
            ratio = (tc / float(pot)) if pot > 0 else 0
            hits["⑤ 主动全押"].append(
                (tag, "tc=%d 池=%d (%.1f×池) eq=%s 规则=%s"
                 % (tc, pot, ratio, eq, r.get("rule"))))
        # ⑥ 超池加注
        if act == "raise" and pot > 0:
            try:
                num = int((r.get("detail") or "0").strip() or 0)
            except Exception:
                num = 0
            if num > 1.5 * pot > 0:
                hits["⑥ 超池加注 (>1.5池)"].append(
                    (tag, "加注到%s 池=%d eq=%s 规则=%s" % (num, pot, eq,
                                                           r.get("rule"))))
    return hits


def main():
    for path in sys.argv[1:]:
        obj = json.load(open(path, encoding="utf-8"))
        seat = detect_seat(obj)
        m = obj.get("match") or {}
        bots = (m.get("bot_a"), m.get("bot_b"))
        me, opp = bots[seat], bots[1 - seat]

        hands = parse_hands(obj)
        ph = per_hand_delta(obj, seat)
        final = sum(ph.values())
        cum, mx, mn = 0, 0, 0
        for h in sorted(ph):
            cum += ph[h]
            mx, mn = max(mx, cum), min(mn, cum)

        print("=" * 98)
        print("【%s】" % os.path.basename(path))
        print("我们=%s(座位%d) vs %s" % (me.get("display_name"), seat,
                                        opp.get("display_name")))
        print("=" * 98)
        print("结果：我们 {:,}（{:.2f} BB）　对手 {:,}　→ {}".format(
            final, final / 100.0, -final, "胜" if final > 0 else "负"))
        print("领先曲线：最低 {:,} / 最高 {:,}".format(mn, mx))

        recs, states = replay_decisions(path, seat)
        by_hand = {}
        for r in recs:
            by_hand.setdefault(r.get("hand"), []).append(r)

        order = sorted(ph, key=lambda h: ph[h])
        print("-" * 98)
        print("▼ 亏损最大的 6 手")
        for h in order[:6]:
            hh, hole, board, seq = hands.get(h) or {}, "", "", ""
            hole, board, seq = fmt(hh, seat)
            print("  手%-3s %-7s 公面 %-20s 净%+7s 池%-6s %s" % (
                h, hole, board, format(ph[h], "+,"), hh.get("pot"),
                hh.get("reason")))
            print("       %s" % seq)
            for r in by_hand.get(h, []):
                hm = (r.get("info") or {}).get("hand") or {}
                print("       · %-2s 池%-6s %-16s eq=%-6s %-8s 规则=%s" % (
                    STREET_CN.get(r.get("street"), "?"), r.get("pot"),
                    "%s%s" % (r.get("action"), r.get("detail") or ""),
                    hm.get("eq"), hm.get("cat_name"), r.get("rule")))
        print("-" * 98)
        print("▲ 盈利最大的 4 手")
        for h in order[::-1][:4]:
            hh = hands.get(h) or {}
            hole, board, seq = fmt(hh, seat)
            print("  手%-3s %-7s 公面 %-20s 净%+7s 池%-6s %s" % (
                h, hole, board, format(ph[h], "+,"), hh.get("pot"),
                hh.get("reason")))
            print("       %s" % seq)
        print("-" * 98)
        print("⚠ 决策扫描")
        hits = scan(recs)
        for k, v in hits.items():
            print("  %s：%d 个" % (k, len(v)))
            for tag, why in v[:8]:
                print("     - %-22s %s" % (tag, why))
        print()


if __name__ == "__main__":
    main()
