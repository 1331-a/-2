# -*- coding: utf-8 -*-
"""① 大注复查：把所有真实对局里「我方下的大注」捞出来，看它们的真实结果。

  大注定义（两种取并集）：
    · 绝对尺寸 raise-to ≥ BIG_ABS（默认 2000）
    · 相对尺寸 ≥ BIG_FRAC（默认 1.0 = 下注额 ≥ 当时底池）
  记录：街头、尺寸、当时的底池与倍池、我方牌型、对手的即时反应、整手真实净变。

用法: BIG_ABS=2000 BIG_FRAC=1.0 python 测/_bigbet_lost.py
"""
import glob
import io
import json
import os
import collections
import sys

sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
from evaluator import evaluate_7, CATEGORY_NAMES   # noqa: E402

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = '23456789TJQKA'
SUIT = 'cdhs'
RANKN = {c: i for i, c in enumerate(PLAT)}
BIG_ABS = int(os.environ.get("BIG_ABS", "2000"))
BIG_FRAC = float(os.environ.get("BIG_FRAC", "1.0"))


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


def cards_str(cs):
    return ' '.join(PLAT[(c - 8) // 4] + SUIT[(c - 8) % 4] for c in cs)


def cat_of(hole, board):
    if len(board) >= 3:
        try:
            return CATEGORY_NAMES.get(evaluate_7(hole + board)[0], '?')
        except Exception:
            return '?'
    r = sorted((c - 8) // 4 for c in hole)
    return '口袋对' if r[0] == r[1] else '高牌'


def main():
    paths = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                   + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))
    rows = []
    for p in paths:
        o = json.load(io.open(p, encoding="utf-8"))
        m0 = o["match"]
        a, b = (m0.get("bot_a") or {}), (m0.get("bot_b") or {})
        if "j1331" in str(a.get("owner_display", "")) and "j1331" in str(b.get("owner_display", "")):
            continue                       # 自对弈：座位不可定
        seat = 0 if "j1331" in str(a.get("owner_display", "")) else 1
        tag = os.path.basename(p)[18:32]
        hand = None
        street = "preflop"
        board = []
        hole = None
        pot = 0                # 近似底池（双方本街累计 + 之前各街）
        committed = [0, 0]     # 各街已并入的投入
        cur = [0, 0]           # 本街累计
        big = None
        for e in o["replay"]["events"]:
            t = e.get("type")
            if t == "hand_start":
                hand = e["hand"]
                street = "preflop"
                board = []
                hole = None
                pot = 0
                committed = [0, 0]
                cur = [0, 0]
                big = None
            elif t == "deal_hole":
                hole = [p2i(c) for c in e["holes"][seat]]
            elif t == "deal_board":
                committed = [committed[i] + cur[i] for i in (0, 1)]
                cur = [0, 0]
                board = [p2i(c) for c in (e.get("board") or [])]
                street = e.get("street", street)
                pot = committed[0] + committed[1]
            elif t == "action":
                pl = e.get("player")
                at = e.get("action")
                amt = int(e.get("amount", 0) or 0)
                if pl == seat and at in ("raise", "allin") and big is None:
                    call_amt = max(0, amt - cur[seat])
                    size = call_amt                      # 本街主动加注的增量
                    if size >= BIG_ABS or (pot > 0 and size >= BIG_FRAC * pot):
                        big = dict(street=street, size=size, pot=pot, act=at,
                                   ratio=(size / pot if pot else 0),
                                   cat=cat_of(hole, board), react=None,
                                   hole=list(hole or []), board=list(board))
                elif pl == seat and at == "call":
                    cur[seat] += amt
                    pot = committed[0] + committed[1] + cur[0] + cur[1]
                elif pl == seat and at in ("raise", "allin"):
                    cur[seat] = amt
                    pot = committed[0] + committed[1] + cur[0] + cur[1]
                if big is not None and pl != seat and big["react"] is None \
                        and at in ("fold", "call", "raise", "allin"):
                    big["react"] = at
            elif t == "settle":
                if big is not None:
                    big.update(hand=hand, delta=e["deltas"][seat], tag=tag)
                    rows.append(big)
                big = None
    print("大注样本（BIG_ABS=%d 或 ≥%.2f×池）: %d 笔" % (BIG_ABS, BIG_FRAC, len(rows)))
    print()
    g = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        k = "%.2f~%.2f×池" % (min(int(r["ratio"]), 3), min(int(r["ratio"]) + 1, 3)) \
            if r["ratio"] < 3 else "≥3×池"
        g[k][0] += 1
        g[k][1] += r["delta"]
    print("=== 按倍池 ===")
    for k in sorted(g):
        n, net = g[k]
        print("   %-12s %3d 笔 | 净变 %+8d | 均 %+7.0f" % (k, n, net, net / max(1, n)))
    print()
    g2 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        g2[r["street"]][0] += 1
        g2[r["street"]][1] += r["delta"]
    print("=== 按街 ===")
    for k in ("preflop", "flop", "turn", "river"):
        if k in g2:
            n, net = g2[k]
            print("   %-9s %3d 笔 | 净变 %+8d | 均 %+7.0f" % (k, n, net, net / max(1, n)))
    print()
    g3 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        g3[(r["cat"], r["react"])][0] += 1
        g3[(r["cat"], r["react"])][1] += r["delta"]
    print("=== 按「我方牌型 × 对手即时反应」（笔数≥2）===")
    for k in sorted(g3, key=lambda x: -g3[x][0]):
        n, net = g3[k]
        if n >= 2:
            print("   %-12s 对手%-7s %3d 笔 | 净变 %+8d | 均 %+7.0f" % (k[0], k[1], n, net, net / n))
    print()
    print("=== ★ 按「是 allin 还是常规大注」 × 我方牌型 ===")
    g4 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        g4[(r["act"], r["cat"])][0] += 1
        g4[(r["act"], r["cat"])][1] += r["delta"]
    for k in sorted(g4, key=lambda x: (x[0], -g4[x][1])):
        n, net = g4[k]
        print("   %-7s %-10s %3d 笔 | 净变 %+8d | 均 %+7.0f" % (k[0], k[1], n, net, net / n))
    print()
    print("=== 常规大注(非 allin) 按街×牌型 ===")
    g5 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r["act"] == "allin":
            continue
        g5[(r["street"], r["cat"])][0] += 1
        g5[(r["street"], r["cat"])][1] += r["delta"]
    for k in sorted(g5, key=lambda x: -g5[x][0]):
        n, net = g5[k]
        if n >= 2:
            print("   %-9s %-10s %3d 笔 | 净变 %+8d | 均 %+7.0f" % (k[0], k[1], n, net, net / n))
    print()
    print("=== 亏得最多的 20 笔 ===")
    print("  %-10s %4s %-8s %7s %7s %6s %-8s %-7s %8s" % (
        "日志", "手", "街", "尺寸", "底池", "倍池", "牌型", "对手", "整手净变"))
    for r in sorted(rows, key=lambda x: x["delta"])[:20]:
        print("  %-10s %4s %-8s %7d %7d %6.2f %-8s %-7s %8d  [%s | %s]" % (
            r["tag"], r["hand"], r["street"], r["size"], r["pot"], r["ratio"],
            r["cat"], str(r["react"]), r["delta"],
            cards_str(r["hole"]), cards_str(r["board"])))
    tot = sum(r["delta"] for r in rows)
    print()
    print("大注总体：%d 笔，整手净变合计 %+d（均 %+.0f）" % (len(rows), tot, tot / max(1, len(rows))))


if __name__ == "__main__":
    main()
