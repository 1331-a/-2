# -*- coding: utf-8 -*-
"""翻前「同一赔率档」里的弃/跟一致性检查。

问题：如果 required 相同、手牌百分位相近，动作却一个是 fold、一个是 call，
那说明门槛不是按赔率来的，而是被别的条件（位置/加注次数/百分位硬截断）切开。
"""
import collections
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

from botbattle_log import card_to_platform            # noqa: E402
from ranges import hand_percentile                    # noqa: E402
from _range_condition_audit import match_id, match_seat  # noqa: E402

SB, BB = 50, 100


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def parse_hands(events):
    hands, cur = {}, None
    for e in events:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "sb": e.get("sb"), "holes": None,
                   "board": [], "acts": []}
            hands[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _nboard=len(cur["board"])))
        elif t == "settle":
            cur = None
    return hands


rows = []
paths = sorted(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
paths += sorted(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json")))
for p in paths:
    obj = json.loads(Path(p).read_bytes())
    seat = match_seat(obj)
    if seat is None:
        continue
    for hn, h in parse_hands(obj["replay"]["events"]).items():
        if not h["holes"]:
            continue
        hole = internal(h["holes"][seat])
        pct = hand_percentile(hole)
        sc = [0, 0]
        sc[h["sb"]] = SB
        sc[1 - h["sb"]] = BB
        pot = SB + BB
        raises = 0
        for a in h["acts"]:
            if a["_nboard"] > 0:
                break
            act = a.get("action")
            pl = int(a.get("player", -1))
            amt = int(a.get("amount") or 0)
            to_call = max(0, sc[1 - pl] - sc[pl])
            if pl == seat and act in ("fold", "call", "raise", "allin") and to_call > 0:
                rows.append(dict(
                    m=match_id(p), h=hn + 1, hole="".join(h["holes"][seat]),
                    pct=pct, pot=pot, to_call=to_call, raises=raises,
                    req=round(to_call / float(pot + to_call), 2),
                    iam_dealer=(seat == h["sb"]),
                    act="fold" if act == "fold" else act))
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)
                if pl != seat:
                    raises += 1

print("样本 %d 个翻前面对下注的决策点\n" % len(rows))

# 1) 一致性矩阵：赔率档 × 手牌百分位档 → 弃/跟
print("=== 弃/跟分布（行=required，列=手牌百分位；×表示该格没样本） ===")
grid = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    rq = int(r["req"] * 10) / 10.0
    pc = min(0.9, int(r["pct"] * 10) / 10.0)
    grid[rq][pc].append(r["act"])
hdr = "%-12s" % "req\\pct"
cols = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
for c in cols:
    hdr += " %5.1f" % c
print(hdr)
for rq in sorted(grid):
    line = "%-12.2f" % rq
    for c in cols:
        v = grid[rq].get(c)
        if not v:
            line += "     ·"
        else:
            f = sum(1 for x in v if x == "fold")
            k = len(v) - f
            line += "  %d/%d" % (k, f)      # 跟+K / 弃 F
    print(line)
print("（格子=跟或加注数 / 弃牌数）")

# 2) 同档里「更弱的手被跟、更强的手被弃」——真矛盾
print("\n=== 同 required 档、更弱的手被跟 / 更强的手被弃 ===")
by_req = collections.defaultdict(list)
for r in rows:
    by_req[round(r["req"], 2)].append(r)
bad = 0
for rq in sorted(by_req):
    v = [x for x in by_req[rq] if x["raises"] == 0]
    cont = [x for x in v if x["act"] != "fold"]
    fold = [x for x in v if x["act"] == "fold"]
    if not cont or not fold:
        continue
    weakest_cont = max(cont, key=lambda x: x["pct"])
    strongest_fold = min(fold, key=lambda x: x["pct"])
    if strongest_fold["pct"] < weakest_cont["pct"]:
        bad += 1
        print("  req=%.2f 档：跟注里最弱 %s(%.3f)  vs  弃牌里最强 %s(%.3f)  ⇒ 反序 %.3f"
              % (rq, weakest_cont["hole"], weakest_cont["pct"],
                 strongest_fold["hole"], strongest_fold["pct"],
                 weakest_cont["pct"] - strongest_fold["pct"]))
print("反序档数 %d" % bad)

# 3) 三种典型位置的弃/跟百分位
print("\n=== 按「对手已加注次数」分组，弃/跟的手牌百分位中位数 ===")
for rz in sorted(set(r["raises"] for r in rows)):
    v = [r for r in rows if r["raises"] == rz]
    f = sorted(x["pct"] for x in v if x["act"] == "fold")
    c = sorted(x["pct"] for x in v if x["act"] != "fold")
    med = lambda a: a[len(a) // 2] if a else float("nan")
    print("  对手加注 %d 次：n=%-3d  弃 n=%-3d 中位 %.3f | 跟/加 n=%-3d 中位 %.3f"
          % (rz, len(v), len(f), med(f), len(c), med(c)))
