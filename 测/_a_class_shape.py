# -*- coding: utf-8 -*-
"""A 类（翻后主动下注/加注后被弃）的形态统计。"""
import collections
import glob
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "\u6d4b"))
sys.path.insert(0, str(BASE / "\u5185\u5bb9"))
from _range_condition_audit import match_id, match_seat  # noqa: E402
import strategy as S                                   # noqa: E402
from botbattle_log import card_to_platform             # noqa: E402
from types import SimpleNamespace                      # noqa: E402


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


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
            cur["acts"].append(dict(e, _board=list(cur["board"])))
        elif t == "settle" and cur is not None:
            cur["settle"] = e
            cur = None
    return hands


rows = []
paths = sorted(glob.glob(str(BASE / "\u5185\u5bb9" / "\u8bb0\u5f55" / "*log.json")))
paths += sorted(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json")))
for p in paths:
    o = json.loads(Path(p).read_bytes())
    seat = match_seat(o)
    if seat is None:
        continue
    for hn, h in build(o["replay"]["events"]).items():
        if not h["settle"]:
            continue
        pot = 150
        sc = [0, 0]
        sc[h["sb"]] = 50
        sc[1 - h["sb"]] = 100
        board = []
        ours = []
        opp = []
        opp_cum = 0
        last_incr = 0
        jump_cum0 = jump_ratio = False
        for a in h["acts"]:
            nb = len(a.get("_board") or [])
            if nb != len(board):
                sc = [0, 0]
            board = a.get("_board") or []
            act = a.get("action")
            pl = int(a.get("player", -1))
            amt = int(a.get("amount") or 0)
            nb = len(board)
            (ours if pl == seat else opp).append((act, amt, nb))
            if pl != seat and act in ("raise", "allin"):
                incr = max(0, amt - sc[pl])
                if opp_cum == 0 and incr > S.OPP_JUMP_THRESHOLD:
                    jump_cum0 = True
                if opp_cum > 0 and incr > S.OPP_JUMP_RATIO * opp_cum:
                    jump_ratio = True
                opp_cum += incr
                last_incr = incr
            elif pl != seat and act == "call":
                incr = max(0, max(sc[0], sc[1]) - sc[pl])
                opp_cum += incr
                last_incr = incr
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("bet", "raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)
        fold = [x for x in ours if x[0] == "fold"]
        if not fold:
            continue
        aggr_post = [x for x in ours if x[0] in ("bet", "raise") and x[2] >= 3]
        if not aggr_post:
            continue
        st = fold[0][2]
        stage = "preflop" if st == 0 else (["flop", "turn", "river"][st - 3]
                                          if st >= 3 else "?")
        to_call = max(0, sc[1 - seat] - sc[seat])
        try:
            cat = S._effective_category(SimpleNamespace(
                hole=internal(h["holes"][seat]) if h["holes"] else [],
                board=internal(board)))
        except Exception:
            cat = -1
        rows.append(dict(m=match_id(p), h=hn + 1, stage=stage, pot=pot,
                         to_call=to_call, ratio=round(to_call / max(1, pot), 2),
                         n_aggr=len(aggr_post),
                         opp_allin=any(x[0] == "allin" for x in opp),
                         n_opp_raise=sum(1 for x in opp
                                         if x[0] in ("bet", "raise", "allin")),
                         jump=(jump_cum0 or jump_ratio), jump_cum0=jump_cum0,
                         jump_ratio=jump_ratio, cat=cat,
                         bigbet=to_call > S.BIG_BET_FOLD_FRAC * pot))

print("A 类（翻后主动下注/加注后弃牌）共 %d 手" % len(rows))
print("弃牌街分布", dict(collections.Counter(r["stage"] for r in rows)))
print("面对 allin 的 %d 手" % sum(1 for r in rows if r["opp_allin"]))
print("to_call/pot 中位数 %.2f" % statistics.median(r["ratio"] for r in rows))
b = collections.Counter()
for r in rows:
    x = r["ratio"]
    b["<=0.25" if x <= 0.25 else "0.25-0.5" if x <= 0.5
      else "0.5-1.0" if x <= 1.0 else ">1.0"] += 1
print("to_call/pot 分档", dict(b))
print()
print("★ 规则归因（在弃牌点上的标志）：")
print("  _OPP_JUMPED=True            %2d / %d" % (sum(1 for r in rows if r["jump"]), len(rows)))
print("    其中 first-raise>2000     %2d" % sum(1 for r in rows if r["jump_cum0"]))
print("    其中 4×此前累计          %2d" % sum(1 for r in rows if r["jump_ratio"]))
print("  cat<三条                    %2d / %d" % (sum(1 for r in rows if 0 <= r["cat"] < 3), len(rows)))
print("  to_call>0.6×池（大注族）    %2d / %d" % (sum(1 for r in rows if r["bigbet"]), len(rows)))
print("  ★ 突袭 & cat<三条（硬弃组合）%2d / %d"
      % (sum(1 for r in rows if r["jump"] and 0 <= r["cat"] < 3), len(rows)))
print()
for r in sorted(rows, key=lambda x: -x["to_call"])[:14]:
    print("  %-26s 手%-3d %-7s 底池%-6d 跟%-6d 比值%-5s 我方主动%d次 对手加注%d次 allin=%s jump=%s cat=%s"
          % (r["m"], r["h"], r["stage"], r["pot"], r["to_call"], r["ratio"],
             r["n_aggr"], r["n_opp_raise"], r["opp_allin"], r["jump"], r["cat"]))

# ---- 与真实底牌结论 JOIN ----
tj = BASE / "\u6d4b" / "_fold_truth.json"
if tj.exists():
    truth = json.loads(tj.read_text(encoding="utf-8"))
    tmap = {(t["match"], t["ui"]): t for t in truth}
    print("\n---- 与 _fold_truth.json 交叉（我方主动投入过的弃牌） ----")
    cats = {"jump": [0, 0], "nojump": [0, 0]}
    for r in rows:
        t = tmap.get((r["m"], r["h"]))
        if not t:
            continue
        k = "jump" if r["jump"] else "nojump"
        cats[k][0] += 1
        if t["true_eq"] > t["required"]:
            cats[k][1] += 1
        if t["true_eq"] >= 0.75:
            print("  ★真强牌被弃 %-26s 手%-3d %-7s 需要%.2f 真实%.2f jump=%s cat=%s 牌面%s"
                  % (r["m"], r["h"], r["stage"], t["required"], t["true_eq"],
                     r["jump"], r["cat"], t["board"] or "-"))
    for k, v in cats.items():
        print("  %-7s n=%2d 弃错 %2d (%.0f%%)" % (k, v[0], v[1],
                                                  100.0 * v[1] / max(1, v[0])))
