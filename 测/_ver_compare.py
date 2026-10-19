# -*- coding: utf-8 -*-
"""新旧版本自对局对比（botbattle-holdem-20261019220054-2f88430c）。

座位 0 = 最新版（与当前代码重放一致度 79.2%），座位 1 = 上一版（58.8%）。
输出：逐手净额、大池分布、全押/小注行为差异、关键手明细。

用法: python 测/_ver_compare.py
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

from botbattle_log import card_to_platform       # noqa: E402
from evaluator import evaluate_7                 # noqa: E402

LOG = Path.home() / "Downloads" / "botbattle-holdem-20261019220054-2f88430c-log.json"
NAMES = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子",
         5: "同花", 6: "葫芦", 7: "四条", 8: "同花顺"}
STREET = {0: "翻前", 3: "翻牌", 4: "转牌", 5: "河牌"}


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


obj = json.loads(LOG.read_bytes())
ev = obj["replay"]["events"]

H = {}
cur = None
for e in ev:
    t = e.get("type")
    if t == "hand_start":
        cur = dict(h=e["hand"], sb=e.get("sb"), board=[], acts=[],
                   holes=None, settle=None)
        H[e["hand"]] = cur
    elif t == "deal_hole" and cur is not None:
        cur["holes"] = e["holes"]
    elif t == "deal_board" and cur is not None:
        cur["board"] = list(e["board"])
    elif t == "action" and cur is not None:
        cur["acts"].append(dict(e, _nb=len(cur["board"])))
    elif t == "settle" and cur is not None:
        cur["settle"] = e
        cur = None

NEW, OLD = 0, 1
rows = []
for h in sorted(H):
    x = H[h]
    if not x["settle"]:
        continue
    d0 = int(x["settle"]["deltas"][0])
    pot = int(x["settle"].get("pot") or 0)
    board_i = internal(x["board"]) if x["holes"] else []
    c0 = c1 = -1
    if x["holes"] and len(x["board"]) >= 3:
        try:
            c0 = evaluate_7(internal(x["holes"][0]) + board_i)[0]
            c1 = evaluate_7(internal(x["holes"][1]) + board_i)[0]
        except Exception:
            pass
    # 双方动作序列（带街）
    seq = {0: [], 1: []}
    for a in x["acts"]:
        seq[int(a["player"])].append((STREET.get(a["_nb"], "?"),
                                      str(a["action"]).lower(),
                                      int(a.get("amount") or 0)))
    rows.append(dict(h=h + 1, d0=d0, pot=pot, c0=c0, c1=c1,
                     holes=x["holes"], acts=x["acts"],
                     board=x["board"], seq=seq))

print("手数 %d；新版(座0) 净 %+d，旧版(座1) 净 %+d"
      % (len(rows), sum(r["d0"] for r in rows), -sum(r["d0"] for r in rows)))
big = [r for r in rows if abs(r["d0"]) >= 1000]
print("|净额|>=1000 的手：%d，其中新版赢 %d、输 %d"
      % (len(big), sum(1 for r in big if r["d0"] > 0),
         sum(1 for r in big if r["d0"] < 0)))
print("大池净额合计：新版 %+d" % sum(r["d0"] for r in big))
print()

print("=== 逐手 ===")
print("%-4s %8s %8s %-6s %-6s %s" % ("手", "新版净", "累计", "新版牌", "旧版牌", "动作"))
cum = 0
for r in rows:
    cum += r["d0"]
    s0 = " ".join("%s%d" % (a[1][:2], a[2]) if a[1] in ("raise", "bet", "allin")
                  else a[1][:4] for a in r["seq"][0]) or "-"
    s1 = " ".join("%s%d" % (a[1][:2], a[2]) if a[1] in ("raise", "bet", "allin")
                  else a[1][:4] for a in r["seq"][1]) or "-"
    print("%-4d %+8d %+8d %-6s %-6s 新[%s] 旧[%s]"
          % (r["h"], r["d0"], cum, NAMES.get(r["c0"], "-"), NAMES.get(r["c1"], "-"),
             s0[:46], s1[:46]))
