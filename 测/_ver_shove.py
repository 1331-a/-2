# -*- coding: utf-8 -*-
"""新版面对旧版「连续 open shove」时的 29 次弃牌，逐手核真值。

对手（旧版）从手 42 起每手翻前 allin 20000；新版每手都弃。
用对手**真实底牌**算新版该不该跟：required = to_call/(pot+to_call)，
真实胜率 = 两张牌对两牌的全下胜率（精确枚举，翻前）。

用法: python 测/_ver_shove.py
"""
import itertools
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

from botbattle_log import card_to_platform       # noqa: E402
from evaluator import evaluate_7                 # noqa: E402
from ranges import hand_percentile               # noqa: E402

LOG = Path.home() / "Downloads" / "botbattle-holdem-20261019220054-2f88430c-log.json"


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def eq_preflop(hole, opp, n_sample=None):
    """对给定两手牌的翻前胜率（枚举 5 张公共牌，C(48,5)=1712304 太多 ⇒ 抽样）。"""
    import random
    deck = [c for c in range(52) if c not in hole and c not in opp]
    rng = random.Random(7)
    win = tie = tot = 0
    for _ in range(20000):
        bd = rng.sample(deck, 5)
        a = evaluate_7(list(hole) + bd)[0]
        b = evaluate_7(list(opp) + bd)[0]
        tot += 1
        if a > b:
            win += 1
        elif a == b:
            tie += 1
    return (win + tie / 2.0) / tot


obj = json.loads(LOG.read_bytes())
ev = obj["replay"]["events"]
H = {}
cur = None
for e in ev:
    t = e.get("type")
    if t == "hand_start":
        cur = dict(h=e["hand"], sb=e.get("sb"), acts=[], holes=None, settle=None)
        H[e["hand"]] = cur
    elif t == "deal_hole" and cur is not None:
        cur["holes"] = e["holes"]
    elif t == "action" and cur is not None:
        cur["acts"].append(dict(e))
    elif t == "settle" and cur is not None:
        cur["settle"] = e
        cur = None

print("%-4s %-7s %-8s %-8s %-7s %-7s %-6s %-6s %s"
      % ("手", "位置", "新版牌", "旧版牌", "新pct", "旧pct", "需要", "真实", "判定"))
bad = []
n = 0
for h in sorted(H):
    x = H[h]
    if not x["holes"] or not x["settle"]:
        continue
    acts = x["acts"]
    # 旧版(座1)翻前 allin，新版(座0)随后 fold
    old_allin = any(int(a["player"]) == 1 and str(a["action"]).lower() == "allin"
                    and int(a.get("amount") or 0) >= 15000 for a in acts)
    new_fold = any(int(a["player"]) == 0 and str(a["action"]).lower() == "fold"
                   for a in acts)
    if not (old_allin and new_fold):
        continue
    n += 1
    me = internal(x["holes"][0])
    op = internal(x["holes"][1])
    pct_me, pct_op = hand_percentile(me), hand_percentile(op)
    # 需要的胜率：翻前 SB/BB 投入 + 对手 allin 后我跟注
    sb = x["sb"]
    mine_blind = 50 if sb == 0 else 100
    pot = 150 + 20000 - 100          # 双方盲注 + 对手 allin（扣回自己那 100 的重复）
    to_call = 20000 - mine_blind
    req = to_call / float(pot + to_call)
    eq = eq_preflop(me, op)
    verdict = "该跟" if eq > req else "弃对"
    if eq > req:
        bad.append((h + 1, eq, req))
    print("%-4d %-7s %-8s %-8s %-7.3f %-7.3f %-6.2f %-6.3f %s"
          % (h + 1, "SB" if sb == 0 else "BB",
             " ".join(str(c) for c in x["holes"][0]),
             " ".join(str(c) for c in x["holes"][1]),
             pct_me, pct_op, req, eq, verdict))

print()
print("共 %d 手「对手 open shove → 新版弃牌」；其中**真实胜率够跟却没跟**：%d 手"
      % (n, len(bad)))
if bad:
    print("  明细：", ", ".join("手%d(%.2f vs 需要%.2f)" % b for b in bad))
