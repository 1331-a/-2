# -*- coding: utf-8 -*-
"""baseline_early.py — 前中期累积曲线（真实数据，逐手）。

只读真实日志（不重放策略），输出：
  · 第 N 手结束时的累积净额（前 20 手重点 / 全场）
  · 前 20 手内亏损最大的 5 手（含牌面/公面/动作序列），用于定位「跟一手再被赶走」
用法：
  python baseline_early.py 记录/botbattle-holdem-20260924*.json [--split 20] [--seat 0]
"""
import argparse
import glob
import json
import os
import sys

_R = "23456789TJQKA"
_SU = "\u2663\u2666\u2665\u2660"


def _card(s):
    try:
        return _R["23456789TJQKA".index(str(s)[0].upper())] + _SU["cdhs".index(str(s)[1].lower())]
    except Exception:
        return str(s)


def analyze(path, seat=0, split=20, verbose=True):
    o = json.load(open(path, encoding="utf-8"))
    m = o.get("match") or {}
    ev = (o.get("replay") or {}).get("events") or []
    cur = None
    hands = []          # [{hand, delta, board, hole, seq}]
    for e in ev:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": int(e.get("hand", 0)), "delta": 0,
                   "hole": None, "board": [], "seq": []}
        elif t == "deal_hole" and cur is not None:
            hs = e.get("holes") or [[], []]
            cur["hole"] = list(hs[seat] if len(hs) > seat else [])
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e.get("board") or [])
        elif t == "action" and cur is not None:
            cur["seq"].append("%s%d:%s%s" % (
                "我" if int(e.get("player", -1)) == seat else "敌",
                int(e.get("amount", 0) or 0), e.get("action"),
                "" if e.get("amount") else ""))
        elif t == "deal_board" and cur is not None:
            pass
        elif t == "settle" and cur is not None:
            d = e.get("deltas") or [0, 0]
            cur["delta"] = int(d[seat] or 0)
            hands.append(cur)
            cur = None
    if not hands:
        return None
    cums = []
    s = 0
    for h in hands:
        s += h["delta"]
        cums.append(s)
    first = cums[split - 1] if len(cums) >= split else cums[-1]
    if verbose:
        print("=" * 78)
        print("%s  (座位 %d)  %s vs %s  结果=%+d"
              % (os.path.basename(path), seat,
                 (m.get("bot_a") or {}).get("name"),
                 (m.get("bot_b") or {}).get("name"),
                 (m.get("result") or {}).get("deltas", [0, 0])[seat]))
        print("  前 %d 手累积 %+d | 全场 %+d" % (split, first, cums[-1]))
        print("  逐手累积（每手）：")
        line, seg = [], []
        for i, c in enumerate(cums):
            seg.append("%+d" % c)
            if len(seg) == 10:
                line.append("H%02d-%02d: %s" % (i - 8, i + 1, " ".join(seg)))
                seg = []
        if seg:
            line.append("H%02d-%02d: %s" % (len(cums) - len(seg) + 1, len(cums), " ".join(seg)))
        print("    " + "\n    ".join(line))
        early = sorted(hands[:split], key=lambda x: x["delta"])[:5]
        print("  前 %d 手最亏的 5 手：" % split)
        for h in early:
            print("    H%-3d 净%+7d 手牌=%s 公面=%s" % (
                h["hand"] + 1, h["delta"],
                " ".join(_card(c) for c in (h["hole"] or [])),
                " ".join(_card(c) for c in h["board"]) or "-"))
            print("          %s" % "  ".join(h["seq"]))
    return {"cums": cums, "first": first, "total": cums[-1], "hands": hands}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--split", type=int, default=20)
    a = ap.parse_args()
    files = []
    for pat in (a.logs or ["记录/botbattle-holdem-20260924*.json"]):
        files += sorted(glob.glob(pat)) if any(c in pat for c in "*?") else [pat]
    tot = []
    for p in files:
        r = analyze(p, a.seat, a.split)
        if r:
            tot.append((os.path.basename(p), r["first"], r["total"]))
    print("=" * 78)
    print("%-52s %12s %12s" % ("日志", "前%dh" % a.split, "全场"))
    for n, f, t in tot:
        print("%-52s %+12d %+12d" % (n[-24:], f, t))
    if tot:
        print("%-52s %+12d %+12d" % ("平均",
              sum(x[1] for x in tot) / len(tot), sum(x[2] for x in tot) / len(tot)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
