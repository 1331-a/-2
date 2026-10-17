# -*- coding: utf-8 -*-
"""「当前代码 vs 历史日志」的分歧账本。

动机：`_leak_audit.py` 的漏损账本横跨 9-24 ~ 10-15 共 8 份日志，而策略改了几十次。
账本只能说明「历史上钱丢在哪类手上」，**不能代表当前版本的行为**。
本工具用**当前代码重放**，逐决策点与日志里的真实动作对照，找出：
  · 当前版本已经不再犯的错（= 账本里那些点已作废）
  · 当前版本仍然照犯的错（= 真正的待办）

★ 只做**行为级**对照：不声称"改了就能赚 X"（固定历史重放不是反事实对局）。
"""
import glob
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))

import strategy as S                                    # noqa: E402
import game_state as G                                  # noqa: E402
import opponent as O                                    # noqa: E402
import match_ctx as M                                   # noqa: E402
from botbattle_log import load_botbattle                # noqa: E402

sys.path.insert(0, str(BASE / "\u6d4b"))
from _range_condition_audit import match_id, match_seat  # noqa: E402


def norm(act, num):
    """归一化为 4 类，避免把 raise 尺寸抖动算成分歧。"""
    if act in ("fold", "f", -1):
        return "fold"
    if act in ("allin", "a", -2):
        return "allin"
    if act in ("check", "c", "call", 0):
        return "call/check"
    return "raise"


def our_actions(obj, seat):
    out = []
    for e in obj["replay"]["events"]:
        if e.get("type") == "action" and int(e.get("player", -1)) == seat:
            out.append((e.get("action"), int(e.get("amount") or 0),
                        int(e.get("hand", -1))))
    return out


def main():
    paths = sorted(glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
    paths += sorted(glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json")))
    tot_req = tot_same = tot_amt = 0
    per_match = []
    hand_div = []      # (match, hand, 日志动作, 当前动作, 本手净额)
    for p in paths:
        obj = json.loads(Path(p).read_bytes())
        seat = match_seat(obj)
        if seat is None:
            continue
        ident = match_id(p)
        deltas = {int(e["hand"]): int(e["deltas"][seat])
                  for e in obj["replay"]["events"] if e.get("type") == "settle"}
        acts = our_actions(obj, seat)
        model = O.OpponentModel()
        ctx = M.MatchContext.from_dict(model.ctx_dict)
        # ★★ 必须「边更新模型边决策」：早期版本先把整场的 model/ctx 更新完、
        #    再用最终状态回头决策前面的请求 ⇒ **未来信息泄漏**，保真度被虚高，
        #    且派生的「当前版本仍照做多少」全部不可信（2026-10-17 修正）。
        decisions = []
        n_req = 0
        for req, _meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            try:
                O.build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
            except Exception:
                pass
            S._DECISION_STARTED_WALL = time.time()
            try:
                a = S.decide(st, model, ctx)
            except Exception:
                a = {"act": "fold"}
            decisions.append((st, a))
            n_req += 1
        if len(decisions) != len(acts):
            print("  [warn] %s 请求数 %d ≠ 我方动作数 %d（跳过）"
                  % (ident, len(decisions), len(acts)))
            continue
        same = 0
        for (st, a), (lact, lnum, lhand) in zip(decisions, acts):
            S._DECISION_STARTED_WALL = time.time()
            try:
                a = S.decide(st, model, ctx)
            except Exception:
                a = {"act": "fold"}
            cand = norm(a.get("act"), a.get("num"))
            real = norm(lact, lnum)
            # ★ 除动作类别外，还要比**尺寸**：GPT 指出只比类别会把
            #   「raise 300 vs raise 900」算成一致。容差取底池的 2%（至少 1）。
            amt_ok = True
            if cand == "raise" and real == "raise":
                tol = max(1.0, 0.02 * max(1, int(st.pot)))
                amt_ok = abs(int(a.get("num") or 0) - int(lnum or 0)) <= tol
            tot_req += 1
            tot_amt += 1 if amt_ok else 0
            if cand == real:
                same += 1
                tot_same += 1
            else:
                hand_div.append(dict(m=ident, hand=int(st.hand_num),
                                     ui=int(st.hand_num) + 1, stage=st.stage,
                                     log=real, cur=cand,
                                     delta=deltas.get(int(st.hand_num))))
        per_match.append((ident, len(decisions), same, deltas))

    print("\n" + "=" * 86)
    print("重放保真度（当前代码 vs 日志真实动作）")
    print("  仅动作类别一致：%d/%d = %.1f%%"
          % (tot_same, tot_req, 100.0 * tot_same / max(1, tot_req)))
    print("  类别+金额一致  ：%d/%d = %.1f%%（raise 容差 = 底池 2%%）"
          % (tot_amt, tot_req, 100.0 * tot_amt / max(1, tot_req)))
    print("\n%-30s %6s %8s %8s" % ("对局", "决策点", "一致", "净额"))
    for ident, n, same, deltas in per_match:
        print("%-30s %6d %7.1f%% %+8d"
              % (ident, n, 100.0 * same / max(1, n), sum(deltas.values())))

    # 分歧点里，日志当时是「亏钱手」的比例
    print("\n" + "=" * 86)
    print("分歧点按「本手净额」分组：")
    neg = [d for d in hand_div if (d["delta"] or 0) < 0]
    pos = [d for d in hand_div if (d["delta"] or 0) > 0]
    zero = [d for d in hand_div if (d["delta"] or 0) == 0]
    print("  亏钱手 %3d 点  赚钱手 %3d 点  零额 %3d 点" % (len(neg), len(pos), len(zero)))

    print("\n---- 分歧点（本手亏钱，前 40）----")
    for d in sorted(neg, key=lambda x: (x["delta"] or 0))[:40]:
        print("  %-14s 手%-3d %-7s 日志=%-10s 当前=%-10s 本手净=%+7d"
              % (d["m"][-13:], d["ui"], d["stage"], d["log"], d["cur"], d["delta"]))

    out = BASE / "\u6d4b" / "_divergence.json"
    out.write_text(json.dumps(hand_div, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("\n分岐明细已写 %s" % out)


if __name__ == "__main__":
    main()
