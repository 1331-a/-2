# -*- coding: utf-8 -*-
"""eq 偏差的**条件分桶**：找出「可以精确下手」的高偏差桶。

对每个「翻后面对下注」的决策点，记录：
  模型 eq（重放得到）、真实 eq（对手真实底牌，离线标签）、required、
  我方牌型 cat、**对手本手已下注/加注次数**、我方本街是否已跟过、街道、对局。

然后按桶统计 bias = model_eq − true_eq 与 MAE，找出 n 足够大且偏差稳定的桶。
用途：为「条件化收窄范围」提供靶点，而不是再找全局常数（10-17 已证伪）。

用法: WB_MC_ITERS=1200 WB_MC_BUDGET=0.2 python 测/_eq_bias_cond.py
输出: 测/_eq_bias_cond.json
"""
import glob
import json
import statistics
import sys
import time
from collections import defaultdict
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
from _fold_truth import eq_postflop                         # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))

NAMES = {0: "高牌", 1: "一对", 2: "两对", 3: "三条", 4: "顺子", 5: "同花", 6: "葫芦"}


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


def hand_meta(obj):
    """每手：真实底牌、最终牌面、对手本手累计「下注/加注」次数（到各街为止）。"""
    out = {}
    cur = None
    for e in obj["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = dict(h=e["hand"], holes=None, board=[], aggr_by_street=defaultdict(int))
            out[e["hand"]] = cur
        elif t == "deal_hole" and cur:
            cur["holes"] = e["holes"]
        elif t == "deal_board" and cur:
            cur["board"] = list(e["board"])
        elif t == "action" and cur:
            cur["board"] = cur["board"]  # no-op
        elif t == "settle":
            cur = None
    return out


def _opp_hole(obj, hand, seat):
    for e in obj["replay"]["events"]:
        if e.get("type") == "deal_hole" and e.get("hand") == hand:
            return e["holes"][seat]
    raise KeyError("no hole")


rows = []
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    seat = bot_seat(obj)
    if seat is None:
        continue
    ident = Path(p).name[18:32]
    opp = 1 - seat
    deltas = {}
    for e in obj["replay"]["events"]:
        if e.get("type") == "settle":
            deltas[e["hand"]] = int(e["deltas"][seat])
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
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
        try:
            ctx.update(st)
        except Exception:
            pass
        if st.to_call <= 0 or len(st.board) < 3:
            continue
        S._DECISION_STARTED_WALL = time.time()
        S._LAST_REQ_INFO = None
        act = S.decide(st, model, ctx, debug=False)
        info = getattr(S, "_LAST_REQ_INFO", None)
        if info is None:
            continue
        # 对手本手截至本街的下注/加注次数
        hist = req.get("history") or []
        n_aggr = 0
        for h in hist:
            if int(h.get("player_id", -1)) == opp and str(h.get("action_type")) in ("bet", "raise", "allin"):
                n_aggr += 1
        try:
            # ★ `st.hole` / `st.board` 已是**内部编码**（= 平台 + 8），不能再转一次；
            #   只有日志里的底牌是平台编码，需要 `internal()`。
            teq = eq_postflop(list(st.hole), list(st.board),
                              internal(_opp_hole(obj, st.hand_num, opp)))
        except Exception:
            continue
        rows.append(dict(
            m=ident, hand=int(st.hand_num), stage=st.stage,
            street=len(st.board), req=round(st.to_call / float(st.pot + st.to_call), 3),
            eq=round(float(info[0]), 4), thr=round(float(info[1] + info[2]), 4),
            truth=round(float(teq), 4), cat=int(S._effective_category(st)),
            n_aggr=n_aggr, act=act.get("act"), delta=deltas.get(int(st.hand_num), 0)))



Path(str(BASE / "测" / "_eq_bias_cond.json")).write_text(
    json.dumps(rows, ensure_ascii=False), encoding="utf-8")

print("翻后面对下注、可算真值的决策点：%d（%d 手）"
      % (len(rows), len({(r["m"], r["hand"]) for r in rows})))
print("全体 bias = %+.3f  MAE = %.3f"
      % (statistics.mean(r["eq"] - r["truth"] for r in rows),
         statistics.mean(abs(r["eq"] - r["truth"]) for r in rows)))
print()


def table(keyfn, title, minn=8):
    print("=== %s ===" % title)
    print("%-26s %5s %8s %8s %8s" % ("桶", "n", "bias", "MAE", "truth均值"))
    g = defaultdict(list)
    for r in rows:
        g[keyfn(r)].append(r)
    for k in sorted(g, key=lambda x: -len(g[x])):
        v = g[k]
        if len(v) < minn:
            continue
        b = [x["eq"] - x["truth"] for x in v]
        print("%-26s %5d %+8.3f %8.3f %8.3f"
              % (str(k), len(v), statistics.mean(b),
                 statistics.mean(abs(x) for x in b),
                 statistics.mean(x["truth"] for x in v)))
    print()


table(lambda r: "全体", "总量")
table(lambda r: "%s / 对手加注%d次" % (
    {"flop": "翻牌", "turn": "转牌", "river": "河牌"}.get(r["stage"], r["stage"]),
    min(r["n_aggr"], 3)), "按街 × 对手加注次数")
table(lambda r: "%s / cat=%s" % (
    {"flop": "翻牌", "turn": "转牌", "river": "河牌"}.get(r["stage"], r["stage"]),
    NAMES.get(r["cat"], r["cat"])), "按街 × 我方牌型")
table(lambda r: "cat=%s / 对手加注%d次" % (NAMES.get(r["cat"], r["cat"]),
                                          min(r["n_aggr"], 3)), "按牌型 × 对手加注次数")
table(lambda r: "对手加注%d次 / cat%s三条" % (min(r["n_aggr"], 3),
                                           "≥" if r["cat"] >= 3 else "<"),
      "对手加注次数 × 我方是否三条+")
