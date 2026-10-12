# -*- coding: utf-8 -*-
"""【2026-10-12】量化：「c-bet → 被加注 → 跟注」这条链上，钱是在哪一步之后丢的。

对每手找出「我方主动下注 → 对手加注 → 我方跟注/再加注」的第一次，
统计此后我方继续投入的总额 = 若在此处放弃本可省下的钱（上界）。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
PLAT = "23456789TJQKA"; SUIT = "cdhs"
RANKN = {c: i for i, c in enumerate(PLAT)}


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))

rows = []
for p in logs:
    o = json.load(io.open(p, encoding="utf-8"))
    m = o["match"]; seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            seat = i
    opp = 1 - seat
    tag = os.path.basename(p)[17:25]
    cur = None
    for e in o["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "street": "preflop", "acts": [], "folded": False,
                   "pf_open": None, "first_raise_call": None, "spent_after": 0}
        elif t == "deal_board" and cur is not None:
            cur["street"] = e.get("street", cur["street"])
        elif t == "action" and cur is not None:
            pl, at = e.get("player"), e.get("action")
            amt = int(e.get("amount", 0) or 0)
            st = cur["street"]
            cur["acts"].append((st, pl, at, amt))
            if pl == seat and at == "raise" and st == "preflop" and cur["pf_open"] is None:
                cur["pf_open"] = amt
            if pl == seat and at == "fold":
                cur["folded"] = True
        elif t == "settle" and cur is not None:
            if cur["pf_open"] and cur["folded"]:
                # 找第一次「我方下注 → 对手加注 → 我方跟注/再加注」
                A = cur["acts"]
                idx = None
                for i in range(len(A) - 2):
                    s1, p1, a1, m1 = A[i]
                    if p1 == seat and a1 in ("raise", "allin") and s1 != "preflop":
                        # 看同街之后对手是否加注、我方是否又投入
                        for j in range(i + 1, len(A)):
                            s2, p2, a2, m2 = A[j]
                            if s2 != s1:
                                break
                            if p2 == opp and a2 in ("raise", "allin"):
                                for k2 in range(j + 1, len(A)):
                                    s3, p3, a3, m3 = A[k2]
                                    if s3 != s1:
                                        break
                                    if p3 == seat and a3 in ("call", "raise", "allin"):
                                        idx = k2
                                        break
                                break
                        if idx is not None:
                            break
                if idx is not None:
                    after = sum(m for (s, pl, a, m) in A[idx + 1:]
                                if pl == seat and a in ("call", "raise", "allin"))
                    rows.append((tag, cur["hand"], A[idx][0], A[idx][3], after, e["deltas"][seat],
                                 cur["folded"]))
            cur = None

print("符合「翻前开池 + 我方翻后下注→对手加注→我方又投入」的手：%d" % len(rows))
tot_after = sum(r[4] for r in rows)
tot_net = sum(r[5] for r in rows)
print("  此后我方继续投入合计 = %d（均 %.0f）" % (tot_after, tot_after / max(1, len(rows))))
print("  这些手真实净变合计 = %d（均 %.0f）" % (tot_net, tot_net / max(1, len(rows))))
print()
byfirst = collections.defaultdict(lambda: [0, 0, 0])
for r in rows:
    g = byfirst[r[2]]
    g[0] += 1; g[1] += r[4]; g[2] += r[5]
print("  按首次被加注的街：")
for k in sorted(byfirst, key=lambda x: -byfirst[x][0]):
    n, a, d = byfirst[k]
    print("    %-8s %3d 手 | 此后投入 %6d | 净变 %+8d | 均 %+7.0f" % (k, n, a, d, d / max(1, n)))
print()
print("=== 明细（此后投入最大的 20 手）===")
print("  %-9s %4s %-8s %8s %8s" % ("日志", "手", "首被加注街", "此后投入", "净变"))
for r in sorted(rows, key=lambda x: -x[4])[:20]:
    print("  %-9s %4d %-8s %8d %8d" % (r[0], r[1], r[2], r[4], r[5]))
