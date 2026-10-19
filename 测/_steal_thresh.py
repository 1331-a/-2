# -*- coding: utf-8 -*-
"""阈值扫描：按「模型加注率 >= 阈值」抑制小注时，被抑制的点是否本来就在亏。

对每个「我方翻后小注（≤0.5 池）+ 我方≤一对」的点，用真值算：
  EV_check = e × pot
  EV_bet   = 日志里对手真实反应的结算（fold +pot / call e(pot+2b)-b / raise -b）
若某阈值下 **sum(EV_bet) < sum(EV_check)**，说明抑制这些点是省钱的；
反之抑制会亏钱。

用法: python 测/_steal_thresh.py
"""
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

import game_state as G                     # noqa: E402
import opponent as O                       # noqa: E402
import strategy as S                       # noqa: E402
from botbattle_log import load_botbattle, card_to_platform  # noqa: E402
from _range_condition_audit import match_seat               # noqa: E402
from evaluator import evaluate_7                            # noqa: E402
from _fold_truth import eq_postflop                         # noqa: E402


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def bot_seat(obj):
    s = match_seat(obj)
    if s is not None:
        return s
    hs = (obj.get("match") or {}).get("human_seat")
    return None if hs is None else 1 - int(hs)


def small_bets(obj, seat):
    """{(hand, nboard): (size, pot, react)}"""
    H = {}
    cur = None
    for e in obj["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = dict(h=e["hand"], sb=e.get("sb"), board=[], acts=[], holes=None)
            H[e["hand"]] = cur
        elif t == "deal_hole" and cur is not None:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur is not None:
            cur["board"] = list(e["board"])
        elif t == "action" and cur is not None:
            cur["acts"].append(dict(e, _nb=len(cur["board"])))
        elif t == "settle":
            cur = None
    out = {}
    for h, x in H.items():
        if not x["holes"]:
            continue
        sc = [0, 0]
        sc[x["sb"]] = 50
        sc[1 - x["sb"]] = 100
        pot = 150
        pnb = 0
        for i, a in enumerate(x["acts"]):
            nb = a["_nb"]
            if nb != pnb:
                sc = [0, 0]
                pnb = nb
            pl = int(a["player"])
            act = str(a["action"]).lower()
            amt = int(a.get("amount") or 0)
            if pl == seat and act in ("bet", "raise") and nb >= 3:
                size = amt - sc[pl]
                if 0 < size <= 0.5 * pot and (h, nb) not in out:
                    nxt = next((z for z in x["acts"][i + 1:]
                                if int(z["player"]) == 1 - seat and z["_nb"] == nb), None)
                    react = str(nxt["action"]).lower() if nxt else "none"
                    out[(h, nb)] = (size, pot, react, list(x["board"][:nb]))
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)
    return out, H


pts = []
paths = sorted(set(glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
                   + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
for p in paths:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    sb, H = small_bets(obj, seat)
    model = O.OpponentModel()
    try:
        stream = list(load_botbattle(str(p), my_seat=seat))
    except Exception:
        continue
    for req, meta in stream:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(model, req, st)
        except Exception:
            pass
        key = (int(st.hand_num), len(st.board))
        if key not in sb or st.to_call != 0:
            continue
        size, pot, react, bd = sb[key]
        if int(S._effective_category(st)) > 1:
            continue          # 只统计弱牌小注（≤一对）
        hole = list(st.hole)
        board = internal(bd)
        try:
            e = eq_postflop(hole, board,
                            internal(H[int(st.hand_num)]["holes"][1 - seat]))
        except Exception:
            continue
        if react == "fold":
            ev_bet = pot
        elif react == "call":
            ev_bet = e * (pot + 2 * size) - size
        elif react in ("raise", "allin"):
            ev_bet = -size
        else:
            continue
        info = S._opp_raise_vs_bet(model, st)
        pts.append(dict(m=Path(p).name[18:32], hand=int(st.hand_num) + 1,
                        rate=(info[0] if info else None),
                        n=(info[1] if info else 0),
                        ev_bet=ev_bet, ev_check=e * pot, react=react))

print("可评估点：%d" % len(pts))
print("全量：下注 %+d / 过牌 %+d / 差 %+d"
      % (sum(x["ev_bet"] for x in pts), sum(x["ev_check"] for x in pts),
         sum(x["ev_bet"] - x["ev_check"] for x in pts)))
print()
print("%-8s %6s %10s %10s %10s %8s" % ("阈值", "命中", "下注EV", "过牌EV", "净差", "误杀"))
for th in (0.30, 0.45, 0.60, 0.75, 0.90):
    sub = [x for x in pts if x["rate"] is not None and x["rate"] >= th]
    if not sub:
        print("%-8.2f %6d" % (th, 0))
        continue
    d = sum(x["ev_bet"] - x["ev_check"] for x in sub)
    print("%-8.2f %6d %+10d %+10d %+10d %8d"
          % (th, len(sub), sum(x["ev_bet"] for x in sub),
             sum(x["ev_check"] for x in sub), d,
             sum(1 for x in sub if x["ev_bet"] > x["ev_check"])))
print()
print("=== 阈值 0.60 命中明细 ===")
for x in sorted([q for q in pts if q["rate"] and q["rate"] >= 0.60],
                key=lambda z: z["ev_bet"] - z["ev_check"]):
    print("  %-16s 手%-3d 加注率%.2f/n=%d 反应%-5s 下注EV%+7d 过牌EV%+7d"
          % (x["m"], x["hand"], x["rate"], x["n"], x["react"],
             x["ev_bet"], x["ev_check"]))
