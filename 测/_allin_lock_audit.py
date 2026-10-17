# -*- coding: utf-8 -*-
"""审计：每一次「全押」是否真的发生在「弃牌即锁输（对手锁赢）」的点上。

判据（全部用决策当时的真实 state 计算，不做事后推断）：
  lead        = twc[我] - twc[敌]        （平台给的累计净额，lead 单位是筹码的 2 倍）
  invested    = INIT_CHIPS - my_chips    （本手已投入，弃牌沉没）
  弃牌后的 lead = lead - 2*invested
  剩余可追回   = 2*_blind_line(hands_left, own=False)
  doomed      = 弃牌后 lead + 剩余可追回 <= 0      ← 规则2 的公式
  fold_out    = lead > 2*(blind_line(own=True) + invested)  ← 规则2-B

同时回答一个前置事实问题：**twc 在本手进行中是否会变化**（live 还是 settled）。
若 twc 是 live 的（已含本手投入），则 `lead - 2*invested` 是重复扣减 → 假 doom。
"""
import argparse
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))
sys.path.insert(0, str(BASE / "\u6d4b"))

import equity as E  # noqa: F401
import game_state as G
import match_ctx as M
import opponent as O
import strategy as S
from botbattle_log import load_botbattle
from _range_condition_audit import match_id, match_seat

sys.path.insert(0, str(CONTENT))
from bot import _to_response, _final_guard  # noqa: E402

INIT = G.INIT_CHIPS


def blind_line(state, hands, own):
    return S._blind_line(state, hands, own)


def scan(path, seat, verbose=True):
    ident = match_id(path)
    obj = json.loads(Path(path).read_bytes())
    deltas = {int(e["hand"]): int(e["deltas"][seat])
              for e in obj["replay"]["events"] if e.get("type") == "settle"}
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    rows = []
    twc_within = {}   # hand -> set(twc tuple) 是否本手内变化
    for index, (request, meta) in enumerate(load_botbattle(path, my_seat=seat)):
        state = G.parse_request(request)
        O.build_model_from_history(model, request, state)
        ctx.update(state)
        ctx.sync_baseline(state)
        twc = tuple(int(x) for x in state.total_win_chips)
        twc_within.setdefault(int(state.hand_num), set()).add(twc)

        lead = state.total_win_chips[state.my_id] - state.total_win_chips[state.opp_id]
        invested = INIT - int(state.my_chips)
        hl = S._hands_left(state)
        cap = 2 * blind_line(state, hl, own=False)
        own_line = blind_line(state, hl, own=True)
        after_fold = lead - 2 * invested
        doomed = after_fold + cap <= 0
        fold_out = lead > 2 * (own_line + invested)
        adj = S._match_adjust(state)
        gamb = S._gamble_zone(state)

        action = S.decide(state, model, ctx)
        resp = _final_guard(state, _to_response(action))
        # ---- 归因：这次全押是哪条规则推出来的 ----
        try:
            _lw = S._lock_win_unified(state, model)
            src = ("lock_win:%s" % (_lw.get("act") if _lw else "none"))
        except Exception:
            src = "lock_win:err"
        if src == "lock_win:none":
            try:
                _gp = S._gamble_plan(state, model)
                if _gp is not None:
                    src = "rule18:%s" % _gp.get("act")
            except Exception:
                pass
        rows.append({
            "idx": index, "hand": int(state.hand_num), "stage": state.stage,
            "act": action.get("act"), "resp": resp, "src": src,
            "lead": lead, "invested": invested, "hands_left": hl,
            "cap": cap, "own_line": own_line,
            "after_fold": after_fold, "doomed": doomed, "fold_out": fold_out,
            "adj": adj, "gamble": gamb,
            "my_left": int(state.my_left), "to_call": int(state.to_call),
            "pot": int(state.pot),
            "delta": deltas.get(int(state.hand_num)),
        })
    return ident, rows, twc_within, deltas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*", type=Path)
    a = ap.parse_args()
    paths = list(a.logs)
    if not paths:
        paths = sorted(Path(p) for p in glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
        paths += sorted(Path(p) for p in glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json")))

    all_allin = []
    live_flag = {}
    for p in paths:
        try:
            obj = json.loads(Path(p).read_bytes())
            seat = match_seat(obj)
        except Exception as exc:
            print("skip", p, exc)
            continue
        if seat is None:
            print("skip (no seat)", match_id(p))
            continue
        ident, rows, twc_within, deltas = scan(p, seat)
        n_live = sum(1 for h, s in twc_within.items() if len(s) > 1)
        live_flag[ident] = (n_live, len(twc_within))
        al = [r for r in rows if r["resp"] == -2]
        final = rows[-1]["lead"] if rows else 0
        print("=" * 78)
        print("%s  seat=%s  reqs=%d  allin=%d  twc本手内变化的手数=%d/%d  final_lead=%d"
              % (ident, seat, len(rows), len(al), n_live, len(twc_within), final))
        for r in al:
            all_allin.append((ident, r, final))
            print("  h%-3d %-6s resp=-2 act=%-6s | lead=%+7d inv=%-6d hl=%-3d "
                  "cap=%-6d | 弃牌后=%+7d doomed=%-5s fold_out=%-5s | adj=%-9s gamble=%-5s "
                  "| to_call=%-6d pot=%-6d 本手净=%s | src=%s"
                  % (r["hand"], r["stage"], r["act"], r["lead"], r["invested"],
                     r["hands_left"], r["cap"], r["after_fold"],
                     r["doomed"], r["fold_out"], r["adj"], r["gamble"],
                     r["to_call"], r["pot"], r["delta"], r.get("src", "?")))

    print("=" * 78)
    print("全押总数 %d" % len(all_allin))
    if all_allin:
        ok = sum(1 for _, r, _ in all_allin if r["doomed"])
        fo = sum(1 for _, r, _ in all_allin if r["fold_out"])
        print("  其中 doomed(弃牌即锁输)=%d  fold_out(弃牌即锁赢)=%d" % (ok, fo))
        win = sum(1 for _, r, _ in all_allin if (r["delta"] or 0) > 0)
        lose = sum(1 for _, r, _ in all_allin if (r["delta"] or 0) < 0)
        tot = sum((r["delta"] or 0) for _, r, _ in all_allin)
        print("  全押手：赢 %d / 输 %d / 净 %+d" % (win, lose, tot))
    print("\ntwc 是否 live（本手内变化的手数 / 总手数）：")
    for k, v in live_flag.items():
        print("  %s  %d/%d" % (k, v[0], v[1]))

    print("\n---- 不在 doom 点的全押（重点核查） ----")
    for ident, r, _f in all_allin:
        if not r["doomed"]:
            print("  %s h%-3d %-7s lead=%+7d 弃牌后=%+7d cap=%-6d 差=%+6d "
                  "| src=%-18s adj=%-8s gamble=%-5s inv=%-5d to_call=%-6d pot=%-6d 净=%s"
                  % (ident, r["hand"], r["stage"], r["lead"], r["after_fold"],
                     r["cap"], r["after_fold"] + r["cap"], r.get("src", "?"),
                     r["adj"], r["gamble"], r["invested"], r["to_call"],
                     r["pot"], r["delta"]))

    out = BASE / "\u6d4b" / "_allin_lock_audit.json"
    out.write_text(json.dumps(
        [dict(r, match_id=i) for i, r, _f in all_allin],
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n全押明细已写 %s" % out)


if __name__ == "__main__":
    main()
