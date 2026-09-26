# -*- coding: utf-8 -*-
"""ab_effect.py — 用真实日志的「历史真实结果」评估 A 的动作变化是否划算。

思路（诚实评估，不做假回放）：
  A 只改变「我方动作」，而对手动作在日志里是**既定历史**。因此对每个变化的
  决策点，检视「我方原本的跟注/加注是否在同一条付费链上导致了后续亏损」：
   · 若变化点是「同一条街里我们早些的动作」→ 用该手真实净额衡量；
   · 汇总：变化点的所属手净额之和 vs 未变化点所属手净额之和。

更直接的做法：统计「A 把哪些手的决策从 call 改成 fold」，并按这些手真实净额
分组 —— 如果 A 主要改的是「真实亏钱的手」，方向就是对的。
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(path, seat, off):
    p = subprocess.run(
        [sys.executable, "-c",
         "import sys,json,os;sys.path.insert(0,%r);"
         "import diff_ab as D;print(json.dumps(D._run(%r,%d,%s)))"
         % (HERE, path, seat, off)],
        capture_output=True, text=True, cwd=HERE,
        env=dict(os.environ, WB_NO_FUTURE_COST=off))
    return json.loads(p.stdout.strip().splitlines()[-1])


def true_deltas(path, seat=0):
    o = json.load(open(path, encoding="utf-8"))
    ev = (o.get("replay") or {}).get("events") or []
    return [int((e.get("deltas") or [0, 0])[seat] or 0)
            for e in ev if e.get("type") == "settle"]


def main():
    pats = sys.argv[1:] or ["记录/botbattle-holdem-20260924*.json"]
    files = []
    for p in pats:
        files += sorted(glob.glob(p)) if any(c in p for c in "*?") else [p]
    print("%-26s %-12s %-12s" % ("日志", "A 改掉的手", "这些手真实净额合计"))
    print("-" * 60)
    tot_changed, tot_net, tot_all = 0, 0, 0
    for f in files:
        old = run(f, 0, "1")
        new = run(f, 0, "0")
        d = true_deltas(f)
        # 按手归并：只看**动作类型**变化（raise 的尺寸带 ±15% 随机抖动，
        # 尺寸差异不是策略变化，必须排除，否则会把赢局误判成「被改动」）。
        hands_old, hands_new = {}, {}
        for row in old:
            h, s, act, num, actual, tc, pot = row
            hands_old.setdefault(h, []).append((s, act))
        for row in new:
            h, s, act, num, actual, tc, pot = row
            hands_new.setdefault(h, []).append((s, act))
        changed = []
        for h in hands_old:
            if hands_old.get(h) != hands_new.get(h):
                changed.append(h)
        net = sum(d[h - 1] for h in changed if 1 <= h <= len(d))
        name = os.path.basename(f).replace("botbattle-holdem-20260924", "")
        print("%-26s %-12s %+12d" % (name, ",".join("H%d" % h for h in changed), net))
        for h in changed:
            if 1 <= h <= len(d):
                print("      H%-3d 真实净额 %+7d" % (h, d[h - 1]))
        tot_changed += len(changed)
        tot_net += net
        tot_all += sum(d)
    print("-" * 60)
    print("A 共改动 %d 手；这些手真实净额合计 %+d（4 局总计 %+d）"
          % (tot_changed, tot_net, tot_all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
