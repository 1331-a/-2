# -*- coding: utf-8 -*-
"""对 `_call_leak.py` 找出的「跟错点」逐个重放，看**模型自己的 eq** 与真实值差多少。

用途：区分两种跟错
  A 型 模型 eq 已经 ≥ 门槛 ⇒ 是 **eq 高估** 造成的（P0-1 的直接后果）
  B 型 模型 eq < 门槛但仍跟 ⇒ 是 **某条规则越过门槛**（需要定位是哪一层）

输出每个点：模型 eq / 门槛（eff_req+margin）/ 真实 eq / 实际所需 / 动作 / 本手净额。

用法: python 测/_call_bias.py
"""
import glob
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))

import strategy as S                       # noqa: E402
import game_state as G                     # noqa: E402
import opponent as O                       # noqa: E402
import match_ctx as M                      # noqa: E402
from botbattle_log import load_botbattle, card_to_platform  # noqa: E402
from _range_condition_audit import match_seat               # noqa: E402
from evaluator import evaluate_7                            # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))

STREETS = {0: "翻前", 3: "翻牌", 4: "转牌", 5: "河牌"}

# 从 _call_leak.json 关注的「跟错且亏得多」的点（对局标识, 手号[平台1-based]）
TARGETS = {
    ("0261018104218-", 54), ("0261019171101-", 50), ("0260924154120-", 21),
    ("0261015175104-", 29), ("0261012172157-", 1), ("0261012170738-", 11),
    ("0261019171101-", 36), ("0261012172157-", 31), ("0261018104218-", 38),
    ("0261012170738-", 20), ("0260924154120-", 9),
}


def internal(cards):
    return [card_to_platform(c) + 8 for c in cards]


def bot_seat(obj):
    s0 = match_seat(obj)
    if s0 is not None:
        return s0
    hs = (obj.get("match") or {}).get("human_seat")
    if hs is not None:
        return 1 - int(hs)
    return None


def true_eq(obj, hand, seat, stage_nb):
    """对手真实底牌下我方在「该街结束前」的精确胜率（离线标签）。"""
    holes = None
    board = []
    for e in obj["replay"]["events"]:
        if e.get("type") == "deal_hole" and e.get("hand") == hand:
            holes = e["holes"]
        elif e.get("type") == "deal_board" and e.get("hand") == hand:
            board = list(e["board"])
        elif e.get("type") == "settle" and e.get("hand") == hand:
            break
    if not holes:
        return None
    try:
        from _fold_truth import eq_postflop, eq_preflop
        me = internal(holes[seat])
        th = internal(holes[1 - seat])
        if stage_nb >= 3:
            return eq_postflop(me, internal(board[:stage_nb]), th)
        return eq_preflop(me, th)
    except Exception:
        return None


def main():
    print("%-16s %-5s %-5s %-7s %-7s %-8s %-8s %-8s %-6s"
          % ("对局", "手", "街", "所需", "真实", "模型eq", "门槛req", "动作", "本手净"))
    agg = {"A": 0, "B": 0}
    for p in PATHS:
        obj = json.loads(Path(p).read_bytes())
        seat = bot_seat(obj)
        if seat is None:
            continue
        ident = Path(p).name[18:32]
        if not any(k[0] == ident for k in TARGETS):
            continue
        hands = {h for k, h in TARGETS if k == ident}
        deltas = {}
        for e in obj["replay"]["events"]:
            if e.get("type") == "settle":
                deltas[e["hand"]] = int(e["deltas"][seat])
        model = O.OpponentModel()
        ctx = M.MatchContext.from_dict(model.ctx_dict)
        for req, meta in load_botbattle(str(p), my_seat=seat):
            st = G.parse_request(req)
            try:
                O.build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
            except Exception:
                pass
            h = int(st.hand_num)
            if (h + 1) not in hands or st.to_call <= 0:
                continue
            S._DECISION_STARTED_WALL = time.time()
            S._LAST_REQ_INFO = None
            act = S.decide(st, model, ctx, debug=False)
            info = getattr(S, "_LAST_REQ_INFO", None)
            req_ratio = st.to_call / float(st.pot + st.to_call)
            teq = true_eq(obj, h, seat, len(st.board))
            if teq is None:
                continue
            eq_m = info[0] if info else -1.0
            thr = (info[1] + info[2]) if info else -1.0
            kind = "A" if eq_m >= thr else "B"
            agg[kind] += 1
            print("%-16s 手%-3d %-5s %-7.2f %-7.3f %-8.3f %-8.3f %-6s %+7d  [%s型]"
                  % (ident, h + 1, STREETS.get(len(st.board), "?"), req_ratio, teq,
                     eq_m, thr, act.get("act"), deltas.get(h, 0), kind))
    print()
    print("A 型（模型 eq 已过门槛 ⇒ eq 高估所致）：%d 点" % agg["A"])
    print("B 型（模型 eq 未过门槛仍跟 ⇒ 规则越过）：%d 点" % agg["B"])


if __name__ == "__main__":
    main()
