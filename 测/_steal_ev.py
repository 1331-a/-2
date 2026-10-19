# -*- coding: utf-8 -*-
"""小注偷的 EV 对比：下注 vs 过牌（用对手真实底牌 + 日志里真实反应）。

对每个「我方翻后小注（≤0.5 池）+ 我方≤一对」的点：
  EV_check ≈ e × pot                      （摊牌价值，忽略后续下注）
  EV_bet   ≈ 用日志里对手的**真实反应**结算：
              fold  → +pot
              call  → e×(pot+2b) − b        （单街近似）
              raise → −b                    （按现有规则，被加注后基本弃牌）

然后按「模型当时的加注率」分档，看高加注率那档的下注 EV 是否为负
—— 这正是 `_steal_guard` 的判据。

用法: python 测/_steal_ev.py
"""
import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

import game_state as G                     # noqa: E402
import opponent as O                       # noqa: E402
from botbattle_log import load_botbattle, card_to_platform  # noqa: E402
from _range_condition_audit import match_seat               # noqa: E402
from evaluator import evaluate_7                            # noqa: E402
from _fold_truth import eq_postflop                         # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def bot_seat(obj):
    s0 = match_seat(obj)
    if s0 is not None:
        return s0
    hs = (obj.get("match") or {}).get("human_seat")
    return None if hs is None else 1 - int(hs)


def build(obj):
    H = {}
    cur = None
    for e in obj["replay"]["events"]:
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
    return H


rows = []
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    opp = 1 - seat
    H = build(obj)
    # 逐请求重放，拿「当时的加注率」
    model = O.OpponentModel()
    try:
        stream = list(load_botbattle(str(p), my_seat=seat))
    except Exception:
        continue
    rate_at = {}
    for req, meta in stream:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(model, req, st)
        except Exception:
            pass
        try:
            info = None
            if model is not None:
                probe = int(st.curbet[st.my_id] + max(st.pot, 1) * 0.35)
                b = model._bet_size_bucket(False, probe, st.big_blind, st.pot)
                sbd = model.bet_resp_stats(b, cur_hand=st.hand_num, min_samples=4)
                if sbd is not None and sbd.get("n", 0) >= 4:
                    info = (float(sbd["raise_rate"]), int(sbd["n"]))
                else:
                    n = int(getattr(model, "check_faces", 0) or 0)
                    if n >= 5:
                        info = (float(model.check_raise_rate()), n)
            rate_at[(int(st.hand_num), len(st.board))] = info
        except Exception:
            rate_at[(int(st.hand_num), len(st.board))] = None

    for h in sorted(H):
        x = H[h]
        if not x["settle"] or not x["holes"]:
            continue
        sb = x["sb"]
        sc = [0, 0]
        sc[sb] = 50
        sc[1 - sb] = 100
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
                if 0 < size <= 0.5 * pot:
                    hole = internal(x["holes"][seat])
                    bd = internal(x["board"][:nb])
                    if evaluate_7(hole + bd)[0] <= 1:      # ≤ 一对
                        nxt = next((z for z in x["acts"][i + 1:]
                                    if int(z["player"]) == opp and z["_nb"] == nb), None)
                        react = str(nxt["action"]).lower() if nxt else "none"
                        try:
                            e = eq_postflop(hole, bd, internal(x["holes"][opp]))
                        except Exception:
                            e = None
                        if e is not None and react in ("fold", "call", "raise", "allin"):
                            ev_check = e * pot
                            if react == "fold":
                                ev_bet = pot
                            elif react == "call":
                                ev_bet = e * (pot + 2 * size) - size
                            else:
                                ev_bet = -size
                            rows.append(dict(m=ident, hand=h + 1, street=nb,
                                             pot=pot, size=size, eq=e,
                                             react=react, rate=rate_at.get((h, nb)),
                                             ev_check=ev_check, ev_bet=ev_bet))
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)

print("可评估的「弱牌小注」点：%d（%d 手）" % (len(rows), len({(r["m"], r["hand"]) for r in rows})))
if not rows:
    raise SystemExit(0)
print("下注 EV %+d / 过牌 EV %+d / 差 %+d"
      % (sum(r["ev_bet"] for r in rows), sum(r["ev_check"] for r in rows),
         sum(r["ev_bet"] - r["ev_check"] for r in rows)))
print()

buckets = [("加注率<0.20", lambda v: v < 0.20),
           ("0.20~0.30", lambda v: 0.20 <= v < 0.30),
           ("0.30~0.45", lambda v: 0.30 <= v < 0.45),
           ("≥0.45", lambda v: v >= 0.45),
           ("无样本", None)]
print("%-12s %5s %8s %10s %10s %9s" % ("档", "n", "被加注", "下注EV", "过牌EV", "净差"))
for name, f in buckets:
    if f is None:
        sub = [r for r in rows if r["rate"] is None]
    else:
        sub = [r for r in rows if r["rate"] is not None and f(r["rate"][0])]
    if not sub:
        continue
    nraise = sum(1 for r in sub if r["react"] in ("raise", "allin"))
    print("%-12s %5d %7.0f%% %+10d %+10d %+9d"
          % (name, len(sub), 100.0 * nraise / len(sub),
             sum(r["ev_bet"] for r in sub), sum(r["ev_check"] for r in sub),
             sum(r["ev_bet"] - r["ev_check"] for r in sub)))
print()
print("=== 高加注率(≥0.30)逐条 ===")
for r in sorted([q for q in rows if q["rate"] and q["rate"][0] >= 0.30],
                key=lambda z: z["ev_bet"] - z["ev_check"]):
    print("  %-16s 手%-3d %-5s 池%-6d 注%-5d eq%.2f 加注率%.2f/n=%d 反应%-5s 下注EV%+7d 过牌EV%+7d"
          % (r["m"], r["hand"], {3: "翻牌", 4: "转牌", 5: "河牌"}.get(r["street"], "?"),
             r["pot"], r["size"], r["eq"], r["rate"][0], r["rate"][1],
             r["react"], r["ev_bet"], r["ev_check"]))
