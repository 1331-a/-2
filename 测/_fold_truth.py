# -*- coding: utf-8 -*-
"""弃牌真值审计：每一次「我方弃牌」当时该不该弃。

用日志里**对手的真实底牌**做离线标签（只做评估，不进任何预测）：
  需要胜率 required = to_call / (pot + to_call)
  真实胜率 true_eq  = 对该手牌的精确胜率（翻后完整枚举；翻前 2 万次抽样）
  弃错 = true_eq > required  ⇒ 放弃了一个正 EV 的跟注
  弃对 = true_eq <= required

按「我方在本手是否主动投入过」分组，对照 `_leak_audit.py` 的 A/B 分类。
"""
import argparse
import collections
import glob
import json
import random
import sys
from itertools import combinations
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

from botbattle_log import card_to_platform            # noqa: E402
from evaluator import evaluate_7                      # noqa: E402
from _range_condition_audit import match_id, match_seat  # noqa: E402
import strategy as S                                  # noqa: E402
from types import SimpleNamespace                     # noqa: E402

INIT = 20000
SB, BB = 50, 100
_rng = random.Random(20261017)


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def eq_postflop(hole, board, opp):
    cards = set(list(hole) + list(board) + list(opp))
    deck = [c for c in range(8, 60) if c not in cards]
    wins = tot = 0.0
    for runout in combinations(deck, 5 - len(board)):
        bd = list(board) + list(runout)
        m = evaluate_7(list(hole) + bd)
        o = evaluate_7(list(opp) + bd)
        wins += 1.0 if m > o else 0.5 if m == o else 0.0
        tot += 1.0
    return wins / tot if tot else 0.5


def eq_preflop(hole, opp, n=6000):
    cards = set(list(hole) + list(opp))
    deck = [c for c in range(8, 60) if c not in cards]
    wins = 0.0
    for _ in range(n):
        bd = _rng.sample(deck, 5)
        m = evaluate_7(list(hole) + bd)
        o = evaluate_7(list(opp) + bd)
        wins += 1.0 if m > o else 0.5 if m == o else 0.0
    return wins / n


def _flush_threat(board, to_call):
    """复刻 strategy._flush_threat：公面 ≥3 张同花色 且 to_call > 3000。"""
    if len(board) < 3:
        return False
    from collections import Counter
    suits = Counter(c & 3 for c in board)
    if max(suits.values(), default=0) < 3:
        return False
    return to_call > 3000


def _cat(hole, board):
    try:
        return S._effective_category(SimpleNamespace(hole=hole, board=board))
    except Exception:
        return -1


def scan_hand(h, seat):
    """回放一只手，返回我方每一次弃牌点的明细。"""
    holes = h["holes"]
    if not holes:
        return []
    hole = internal(holes[seat])
    opp_hole = internal(holes[1 - seat])
    board = []
    pot = SB + BB
    sc = [0, 0]                 # 本街已投入（street commit）
    sb_seat = h["sb_seat"]
    sc[sb_seat] = SB
    sc[1 - sb_seat] = BB
    our_aggr = False            # 我方是否主动下注/加注过
    out = []
    for a in h["acts"]:
        _raw = a.get("_board") or []
        if len(_raw) != len(board):
            sc = [0, 0]         # 新街：本街投入清零
        board = internal(_raw) if _raw else []
        act = a.get("action")
        p = int(a.get("player", -1))
        amt = int(a.get("amount") or 0)
        if act == "fold":
            if p == seat:
                to_call = max(0, sc[1 - seat] - sc[seat])
                if to_call > 0 and (len(board) >= 3 or to_call >= 200):
                    req = to_call / float(pot + to_call)
                    eq = (eq_postflop(hole, board, opp_hole) if len(board) >= 3
                          else eq_preflop(hole, opp_hole))
                    out.append({
                        "street": ("preflop" if not board else
                                   ["flop", "turn", "river"][len(board) - 3]),
                        "pot": pot, "to_call": to_call, "required": req,
                        "true_eq": eq, "board": " ".join(_raw),
                        "hole": "%s%s" % (holes[seat][0], holes[seat][1]),
                        "aggr": our_aggr,
                        "over_fold": eq > req,
                        "gap": eq - req,
                        "flush_threat": _flush_threat(board, to_call),
                        "cat": _cat(hole, board),
                    })
            continue
        if act == "call":
            sc[p] += amt
            pot += amt
        elif act in ("bet", "raise", "allin"):
            delta = amt - sc[p]
            sc[p] = amt
            pot += max(0, delta)
            if p == seat:
                our_aggr = True
        # check: 0
    return out


def build(events):
    hands, cur = {}, None
    for e in events:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "sb_seat": e.get("sb"), "holes": None,
                   "board": [], "acts": [], "settle": None}
            hands[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _board=list(cur["board"])))
        elif t == "settle" and cur is not None:
            cur["settle"] = e
            cur = None
    return hands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*", type=Path)
    a = ap.parse_args()
    paths = list(a.logs) or sorted(
        Path(p) for p in glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
    paths += sorted(Path(p) for p in glob.glob(
        str(Path.home() / "Downloads" / "botbattle*log.json")))

    rows = []
    for p in paths:
        obj = json.loads(Path(p).read_bytes())
        seat = match_seat(obj)
        if seat is None:
            continue
        ident = match_id(p)
        holes_by_hand = {}
        for ev in obj["replay"]["events"]:
            if ev.get("type") == "deal_hole":
                holes_by_hand[ev["hand"]] = ev["holes"]
        for hn, h in sorted(build(obj["replay"]["events"]).items()):
            h["holes"] = holes_by_hand.get(hn)
            for r in scan_hand(h, seat):
                r.update({"match": ident, "hand": hn, "ui": hn + 1})
                rows.append(r)

    def report(sub, title):
        n = len(sub)
        if not n:
            print("%s: 无" % title)
            return
        bad = [r for r in sub if r["over_fold"]]
        lost = sum(r["to_call"] * (r["true_eq"] - r["required"]) / max(1e-9, 1 - r["required"])
                   for r in bad)
        print("%-28s 弃牌 %3d 次 | 弃错 %3d (%.0f%%) | 平均需要 %.2f vs 真实 %.2f | 弃错的理论代价 ≈ %+d"
              % (title, n, len(bad), 100.0 * len(bad) / n,
                 sum(r["required"] for r in sub) / n,
                 sum(r["true_eq"] for r in sub) / n, -lost))

    print("=" * 100)
    report(rows, "全部弃牌")
    report([r for r in rows if r["street"] != "preflop"], "其中翻后")
    report([r for r in rows if r["street"] == "preflop"], "其中翻前")
    report([r for r in rows if r["aggr"]], "★ 我方主动投入过")
    report([r for r in rows if not r["aggr"]], "我方未主动投入")
    print("-" * 100)
    ft = [r for r in rows if r.get("flush_threat")]
    print("★ 规则11（公面同花威胁 + to_call>3000）触发点：%d 次" % len(ft))
    if ft:
        bad = [r for r in ft if r["over_fold"]]
        print("   其中弃错 %d (%.0f%%)，真强牌(≥0.75)被弃 %d，cat<两对 %d"
              % (len(bad), 100.0 * len(bad) / len(ft),
                 sum(1 for r in ft if r["true_eq"] >= 0.75),
                 sum(1 for r in ft if r.get("cat", -1) < 2)))
        for r in ft:
            print("   %-26s 手%-3d %-7s 需要%.2f 真实%.2f cat=%-2s %s %s"
                  % (r["match"], r["ui"], r["street"], r["required"],
                     r["true_eq"], r.get("cat"), "弃错" if r["over_fold"] else "弃对",
                     r["board"]))
    print("-" * 100)
    print("按需胜率分档（翻后，我方主动投入过）：")
    sub = [r for r in rows if r["aggr"] and r["street"] != "preflop"]
    bins = collections.defaultdict(list)
    for r in sub:
        bins[min(3, int(r["required"] * 10))].append(r)
    for k in sorted(bins):
        v = bins[k]
        bad = [r for r in v if r["over_fold"]]
        print("  required %.1f~%.1f : n=%3d 弃错 %3d (%.0f%%) 真实eq均值 %.2f"
              % (k / 10.0, (k + 1) / 10.0, len(v), len(bad),
                 100.0 * len(bad) / max(1, len(v)),
                 sum(r["true_eq"] for r in v) / len(v)))

    print("\n---- 弃得最错的手 TOP 12（我方主动投入过） ----")
    for r in sorted([x for x in rows if x["aggr"]],
                    key=lambda x: -x["gap"])[:12]:
        print("  %-26s 手%-3d %-7s 牌面 %-14s 底池%-6d 跟%-6d 需要%.2f 真实%.2f 差%+.2f"
              % (r["match"], r["ui"], r["street"], r["board"] or "-",
                 r["pot"], r["to_call"], r["required"], r["true_eq"], r["gap"]))

    out = BASE / "\u6d4b" / "_fold_truth.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n明细已写 %s" % out)


if __name__ == "__main__":
    main()
