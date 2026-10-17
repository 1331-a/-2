# -*- coding: utf-8 -*-
"""翻前漏损：面对「需要胜率 ≥ 阈值」的跟注时，我方各动作的**手牌百分位分布**。

不用「真实胜率 vs 具体底牌」这种事后标签（对范围无效），改看范围层面的问题：
同一赔率档里，弃掉的牌有多强？跟/加的牌有多强？中间有没有断层？
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
            # ★ 必须只记**我方**的动作：漏了 pl==seat 会把对手的弃牌算成我方，
            #   实测直接造出「AA 面对全押弃牌」这种假 bug（实际那手是我方 allin AA、
            #   对手弃牌）。
            if pl == seat and act in ("fold", "call", "raise", "allin"):
                if to_call > 0:
                    rows.append(dict(
                        m=match_id(p), h=hn + 1, hole="".join(h["holes"][seat]),
                        pct=pct, pot=pot, to_call=to_call, raises=raises,
                        req=to_call / float(pot + to_call),
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

print("翻前「面对下注」的决策点：%d 个" % len(rows))
for th in (0.30, 0.35, 0.40, 0.45):
    sub = [r for r in rows if r["req"] >= th]
    if not sub:
        continue
    print("\n=== required ≥ %.2f（n=%d）===" % (th, len(sub)))
    agg = collections.defaultdict(list)
    for r in sub:
        agg[r["act"]].append(r["pct"])
    for k in ("call", "raise", "allin", "fold"):
        v = agg.get(k)
        if not v:
            continue
        v = sorted(v)
        print("  %-6s n=%-3d 百分位 中位 %.3f  最强 %.3f  最弱 %.3f"
              % (k, len(v), v[len(v) // 2], v[0], v[-1]))
    f = sorted(agg.get("fold", []))
    if f:
        print("  ★ 弃掉的最强 8 手：", ["%.3f" % x for x in f[:8]])

print("\n---- required ≥0.38 的弃牌，按手牌强度排序（前 25） ----")
for r in sorted([x for x in rows if x["act"] == "fold" and x["req"] >= 0.38],
                key=lambda x: x["pct"])[:25]:
    print("  %-14s 手%-3d %-8s 百分位 %.3f  底池%-6d 跟%-6d 需要 %.2f  对手已加注%d次"
          % (r["m"][-13:], r["h"], r["hole"], r["pct"], r["pot"],
             r["to_call"], r["req"], r["raises"]))

print("\n---- required ≥0.38 的跟注/加注，按手牌强度排序（前 20） ----")
for r in sorted([x for x in rows if x["act"] in ("call", "raise", "allin")
                 and x["req"] >= 0.38], key=lambda x: x["pct"])[:20]:
    print("  %-14s 手%-3d %-8s 百分位 %.3f  底池%-6d 跟%-6d 需要 %.2f  %s"
          % (r["m"][-13:], r["h"], r["hole"], r["pct"], r["pot"],
             r["to_call"], r["req"], r["act"]))
