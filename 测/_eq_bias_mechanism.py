# -*- coding: utf-8 -*-
"""验证机制：eq 的高估是否来自「范围只按翻前百分位加权、不看翻后牌力」。

对每个已算好的样本（`_range_calibrate.json`），补上「对手在**当时牌面**上的真实牌型」，
按牌型分组看 `pred − truth`。若偏差随对手牌型变强而变大，
说明模型给「对手已成强牌」的组合权重太低。
"""
import glob
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

from botbattle_log import card_to_platform             # noqa: E402
from evaluator import evaluate_7                        # noqa: E402
from ranges import hand_percentile                       # noqa: E402
from _range_condition_audit import hole_map, match_id, match_seat  # noqa: E402

CAT = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子",
       5: "同花", 6: "葫芦", 7: "四条"}


def main():
    rows = json.loads((BASE / "\u6d4b" / "_range_calibrate.json")
                      .read_text(encoding="utf-8"))
    paths = sorted(set(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
                   | set(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
    index = {}
    for p in paths:
        ident = match_id(p)
        obj = json.loads(Path(p).read_bytes())
        seat = match_seat(obj)
        if seat is None:
            continue
        holes = hole_map(obj, seat)
        board = {}
        for ev in obj["replay"]["events"]:
            t = ev.get("type")
            if t == "hand_start":
                board[int(ev["hand"])] = []
            elif t == "deal_board":
                board[int(ev["hand"])] = [card_to_platform(x) + 8 for x in ev["board"]]
            elif t == "action":
                h = int(ev.get("hand", -1))
                b = board.get(h) or []
                if len(b) >= 3:
                    stage = {3: "flop", 4: "turn", 5: "river"}.get(len(b))
                    if stage:
                        index[(ident, h, stage)] = (list(b), holes[h][1])

    out = []
    for r in rows:
        key = (r["m"], r["hand"], r["stage"])
        if key not in index:
            continue
        b, theirs = index[key]
        ev = evaluate_7(list(theirs) + list(b))
        cat = ev[0] if ev else -1
        out.append(dict(bias=r["eqs"]["1.0"] - r["truth"], pred=r["eqs"]["1.0"],
                        truth=r["truth"], cat=cat,
                        opp_pct=hand_percentile(theirs)))

    print("样本 %d\n" % len(out))
    print("%-8s %5s %8s %8s %8s %10s" %
          ("对手牌型", "n", "pred", "truth", "偏差", "对手翻前百分位"))
    g = {}
    for o in out:
        g.setdefault(o["cat"], []).append(o)
    for c in sorted(g):
        v = g[c]
        print("%-8s %5d %8.3f %8.3f %+8.3f %10.3f"
              % (CAT.get(c, "?"), len(v),
                 statistics.mean(x["pred"] for x in v),
                 statistics.mean(x["truth"] for x in v),
                 statistics.mean(x["bias"] for x in v),
                 statistics.mean(x["opp_pct"] for x in v)))

    strong = [o for o in out if o["cat"] >= 2]
    weak = [o for o in out if o["cat"] < 2]
    if strong and weak:
        print("\n对手已成两对+ : n=%2d  偏差 %+.3f" %
              (len(strong), statistics.mean(x["bias"] for x in strong)))
        print("对手仍一对/高牌: n=%2d  偏差 %+.3f" %
              (len(weak), statistics.mean(x["bias"] for x in weak)))
        print("\n★ 若「两对+」组偏差显著更大 ⇒ 模型给强牌组合的权重不足")


if __name__ == "__main__":
    main()
