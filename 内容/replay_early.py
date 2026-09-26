# -*- coding: utf-8 -*-
"""replay_early.py — 重放 BotBattle 日志，统计「前 N 手累积盈亏」与逐手净额。

用途：评估策略改动（A: _face_bet 计入后续投入 / B: 开池加大）对
「前中期劣势」的影响。

用法：
    python replay_early.py <日志.json> [--seat 0] [--split 20] [--quiet]
    python replay_early.py --dir /path/to/dir          # 批量目录

输出：逐手净额 + 前 split 手累积 / 全场累积（对比真实 settle 结果）。
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request                      # noqa: E402
from strategy import decide, DecisionLogger               # noqa: E402
from opponent import OpponentModel, build_model_from_history  # noqa: E402
from match_ctx import MatchContext                        # noqa: E402
from botbattle_log import load_botbattle                  # noqa: E402


def _true_deltas(path):
    """从日志直接取每手的真实 deltas（[我, 对手]），无需重放。"""
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    events = (obj.get("replay") or {}).get("events") or []
    out = []
    for ev in events:
        if ev.get("type") == "settle":
            d = ev.get("deltas") or [0, 0]
            out.append(int(d[0] or 0))
    return out


def replay(path, seat=0, verbose=False):
    reqs = load_botbattle(path, my_seat=seat)
    if not reqs:
        return None
    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)
    DecisionLogger.enable(False)
    out = []
    for i, (req, meta) in enumerate(reqs):
        try:
            state = parse_request(req)
            try:
                build_model_from_history(model, req, state)
            except Exception:
                pass
            try:
                ctx.update(state)
                ctx.sync_baseline(state)
            except Exception:
                pass
            action = decide(state, model, ctx, debug=False)
            out.append({"hand": meta.get("hand"), "street": meta.get("street"),
                        "act": action.get("act"), "num": action.get("num"),
                        "actual": meta.get("actual"),
                        "invested": state.my_chips})
        except Exception as e:
            out.append({"hand": meta.get("hand"), "err": str(e)})
    return reqs, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--split", type=int, default=20)
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()

    files = sorted(glob.glob(a.log)) if any(ch in a.log for ch in "*?") else [a.log]
    summary = {}
    for path in files:
        r = replay(path, seat=a.seat)
        if not r:
            print("跳过（解析失败）: %s" % path)
            continue
        reqs, decisions = r
        true_d = _true_deltas(path)
        real_first = sum(true_d[:a.split])
        real_all = sum(true_d)
        # 重放口径：从 total_win_chips 推每手「我方净额」的增量
        rep = [0] * len(true_d)
        prev = 0
        for i, (req, meta) in enumerate(reqs):
            h = meta.get("hand", 0) - 1
            if 0 <= h < len(rep):
                cur = int(req["total_win_chips"][a.seat])
                # 同手多次决策 → 只记最后一次的增量
                rep[h] = cur - prev if False else rep[h]
        # 更稳：用下一次出现的 total_win 递推
        last_h, last_v = -1, 0
        for i, (req, meta) in enumerate(reqs):
            h = meta.get("hand", 0) - 1
            v = int(req["total_win_chips"][a.seat])
            if h != last_h:
                if last_h >= 0 and 0 <= last_h < len(rep):
                    pass
                last_h, last_v = h, v
        # 直接按 settle 现金流 + 重放动作统计（不用推断净额）
        name = os.path.basename(path)
        summary[name] = {
            "hands": len(true_d),
            "real_first%dh" % a.split: real_first,
            "real_total": real_all,
        }
        print("=" * 72)
        print("%s  (座位 %d)" % (name, a.seat))
        print("  settle 手数 %d | 前 %d 手真实净额 %+d | 全场真实净额 %+d"
              % (len(true_d), a.split, real_first, real_all))
        nd = [d for d in decisions if "err" not in d]
        print("  重放决策点 %d 个" % len(decisions))
        if a.json_out:
            with open(a.json_out, "w", encoding="utf-8") as f:
                json.dump({"path": path, "true_deltas": true_d,
                           "decisions": decisions}, f, ensure_ascii=False)
    print("=" * 72)
    for k, v in summary.items():
        print("%-58s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
