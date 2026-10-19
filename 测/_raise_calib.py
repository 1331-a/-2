# -*- coding: utf-8 -*-
"""标定：模型说的「对手加注率」与真实加注率是否一致。

只取**尺寸桶样本足够**（bet_resp_stats 非 None）的点，避免 check_raise 口径混入。
如果模型说 >=0.45 的点里真实加注率也高，这个统计才能用来门控小注；
否则接进决策只会误伤。

用法: python 测/_raise_calib.py
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
from botbattle_log import load_botbattle    # noqa: E402
from _range_condition_audit import match_seat  # noqa: E402


def bot_seat(obj):
    s = match_seat(obj)
    if s is not None:
        return s
    hs = (obj.get("match") or {}).get("human_seat")
    return None if hs is None else 1 - int(hs)


def reactions(obj, seat):
    """{(hand, nboard): 对手对我方该次小注的即时反应}"""
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
                    out[(h, nb)] = str(nxt["action"]).lower() if nxt else "none"
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
                pot += amt
            elif act in ("raise", "allin"):
                d = amt - sc[pl]
                sc[pl] = amt
                pot += max(0, d)
    return out


rows = []
paths = sorted(set(glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
                   + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))
for p in paths:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    react = reactions(obj, seat)
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
        if key not in react or st.to_call != 0:
            continue
        try:
            probe = int(st.curbet[st.my_id] + max(st.pot, 1) * 0.35)
            b = model._bet_size_bucket(False, probe, st.big_blind, st.pot)
            sbd = model.bet_resp_stats(b, cur_hand=st.hand_num, min_samples=4)
        except Exception:
            sbd = None
        if sbd is None:
            continue
        rows.append((ident, sbd["raise_rate"], sbd["n"], react[key]))

print("尺寸桶样本足够的点：%d" % len(rows))
BUCKETS = [("0~0.15", lambda v: v < 0.15),
           ("0.15~0.30", lambda v: 0.15 <= v < 0.30),
           ("0.30~0.45", lambda v: 0.30 <= v < 0.45),
           (">=0.45", lambda v: v >= 0.45)]
print("%-10s %5s %10s %10s" % ("模型说", "n", "真实加注率", "真实弃牌率"))
for name, f in BUCKETS:
    sub = [r for r in rows if f(r[1])]
    if not sub:
        continue
    ra = sum(1 for r in sub if r[3] in ("raise", "allin")) / len(sub)
    fo = sum(1 for r in sub if r[3] == "fold") / len(sub)
    print("%-10s %5d %9.0f%% %9.0f%%" % (name, len(sub), 100 * ra, 100 * fo))

print()
print("=== 人机对局（19171101）逐点 ===")
for r in rows:
    if r[0] == "0261019171101-":
        print("  raise_rate=%.2f n=%d → 真实 %s" % (r[1], r[2], r[3]))
