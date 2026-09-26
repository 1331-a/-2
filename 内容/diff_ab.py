# -*- coding: utf-8 -*-
"""diff_ab.py — A/B 对比：同一份日志在「改动前 / 改动后」两套策略下的决策差异。

用法（在 内容/ 目录下）：
    python diff_ab.py <日志.json> [--seat 0] [--hand 9 11 21]

做法：把 strategy 的两个版本分别 import 成独立模块（旧版用环境变量
WB_NO_FUTURE_COST=1 关闭 A 的口径），逐决策点比较动作。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request
from botbattle_log import load_botbattle


def _run(path, seat, off):
    """在一个干净的子进程语义里跑（通过重新 import 保证全局不串）。"""
    import importlib
    for m in list(sys.modules):
        if m in ("strategy",):
            del sys.modules[m]
    os.environ["WB_NO_FUTURE_COST"] = "1" if off else "0"
    S = importlib.import_module("strategy")
    from opponent import OpponentModel, build_model_from_history
    from match_ctx import MatchContext
    reqs = load_botbattle(path, my_seat=seat)
    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)
    out = []
    for req, meta in reqs:
        try:
            st = parse_request(req)
            try:
                build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
                ctx.sync_baseline(st)
            except Exception:
                pass
            a = S.decide(st, model, ctx, debug=False)
            out.append((meta.get("hand"), meta.get("street"),
                        str(a.get("act")), a.get("num"),
                        meta.get("actual"), st.to_call, st.pot))
        except Exception as e:
            out.append((meta.get("hand"), meta.get("street"), "ERR", str(e),
                        meta.get("actual"), 0, 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--hand", nargs="*", type=int)
    a = ap.parse_args()
    # 两个版本必须分进程跑（模块级全局）
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    res = {}
    for tag, off in (("旧(逐街独立)", "1"), ("新(计入后续投入)", "0")):
        p = subprocess.run(
            [sys.executable, "-c",
             "import sys,json,os;sys.path.insert(0,%r);"
             "import diff_ab as D;print(json.dumps(D._run(%r,%d,%s)))"
             % (here, a.log, a.seat, off)],
            capture_output=True, text=True, cwd=here,
            env=dict(os.environ, WB_NO_FUTURE_COST=off))
        try:
            res[tag] = json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            print("跑失败:", tag, p.stdout[-500:], p.stderr[-800:])
            return 1
    old, new = res["旧(逐街独立)"], res["新(计入后续投入)"]
    n = min(len(old), len(new))
    diff = 0
    print("=" * 84)
    print("%-4s %-8s %-18s %-18s %s" % ("手", "街", "旧", "新", "真实"))
    for i in range(n):
        h, s, ao, no, act, tc, pot = old[i]
        _, _, an, nn, _, _, _ = new[i]
        if a.hand if False else (a.hand and h not in a.hand):
            pass
        if a.hand and h not in a.hand:
            continue
        mark = ""
        if (ao, no) != (an, nn):
            mark = "  <== 变化"
            diff += 1
        print("H%-3s %-8s %-18s %-18s %-12s%s"
              % (h, s,
                 "%s %s" % (ao, no if ao in ("raise", "allin") else ""),
                 "%s %s" % (an, nn if an in ("raise", "allin") else ""),
                 act or "-", mark))
    print("=" * 84)
    print("共 %d 点，变化 %d 点 (%.0f%%)" % (n, diff, 100.0 * diff / max(n, 1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
