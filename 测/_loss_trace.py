# -*- coding: utf-8 -*-
"""输局溯源：三场输掉的比赛，lead 是在哪几手被累积掉的。

对每场输出逐手：lead（区间）、本手净额、类别、底牌、牌面。
并标出「最大单手亏损」和「doom 首次成立」的位置。
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

from _range_condition_audit import match_id, match_seat  # noqa: E402

sys.path.insert(0, str(CONTENT))
import strategy as S                                      # noqa: E402


def build(events):
    hands, cur = {}, None
    for e in events:
        t = e.get("type")
        if t == "hand_start":
            cur = {"hand": e["hand"], "sb": e.get("sb"), "board": [],
                   "acts": [], "holes": None, "settle": None}
            hands[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _nb=len(cur["board"])))
        elif t == "settle" and cur is not None:
            cur["settle"] = e
            cur = None
    return hands


def tag(h, seat):
    st = h["settle"]
    delta = int(st["deltas"][seat])
    won = seat in (st.get("winners") or [])
    acts = [a for a in h["acts"] if int(a.get("player", -1)) == seat]
    fold = any(a.get("action") == "fold" for a in acts)
    aggr_post = any(a.get("action") in ("raise", "allin")
                    and a.get("_nb", 0) >= 3 for a in acts)
    allin = any(a.get("action") == "allin" for a in acts)
    if won:
        return "W"
    if fold and aggr_post:
        return "A 投入后弃"
    if fold:
        return "F 弃"
    if allin:
        return "C 全押被跟"
    return "E 摊牌"


paths = sorted(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
paths += sorted(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json")))

for p in paths:
    obj = json.loads(Path(p).read_bytes())
    seat = match_seat(obj)
    if seat is None:
        continue
    hands = build(obj["replay"]["events"])
    total = sum(int(h["settle"]["deltas"][seat])
                for h in hands.values() if h["settle"])
    if total >= 0:
        continue                     # 只看输掉的场次
    print("=" * 92)
    print("%s  净 %+d" % (match_id(p), total))
    lead = 0
    rows = []
    for hn in sorted(hands):
        h = hands[hn]
        if not h["settle"]:
            continue
        d = int(h["settle"]["deltas"][seat])
        rows.append((hn, lead, d, lead + d, tag(h, seat),
                     "".join(h["holes"][seat]) if h["holes"] else "-",
                     " ".join(h["board"])))
        lead += d
    # 最大单手亏损
    worst = sorted(rows, key=lambda x: x[2])[:4]
    worst_hn = {r[0] for r in worst}
    for hn, l0, d, l1, tg, hole, board in rows:
        mark = "  ★" if hn in worst_hn else ""
        # 打印 lead 跌破 [-1000, -3000, -6000, -10000] 的首次
        print("  手%-3d lead %+7d → %+7d (%+7d)  %-10s %-6s %s%s"
              % (hn + 1, l0, l1, d, tg, hole, board, mark))
    print("  ---- 最大 4 个亏损手 ----")
    for hn, l0, d, l1, tg, hole, board in worst:
        print("    手%-3d %+7d  %-10s %-6s %s" % (hn + 1, d, tg, hole, board))
