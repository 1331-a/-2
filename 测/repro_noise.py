# -*- coding: utf-8 -*-
"""【2026-10-01】重放确定性体检：生产 MC 口径下，同一配置跑两遍是否逐点一致？

背景：`diff_ab.py` 在 21:51 那局报「变化 2 点」（H35 与 H53），但把 MC 降到 1500
后只剩 H35 一点，且与规则学习无关。必须查清 H53 是**真二阶效应**还是**重放噪声**
—— 若是噪声，则所有基于 diff 的幅度结论都带误差。

做法：三个独立子进程，同一份日志、同一套生产口径：
  A/B = 完全相同配置（对照组，测纯噪声）
  C   = 关掉顶两对豁免（WB_NO_BIGMONEY_TOPTWO=1）
输出逐决策点动作序列并求差。
"""
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTENT = os.path.join(ROOT, "内容")

CHILD = r'''
import sys, io, json, os
sys.path.insert(0, r"__CONTENT__")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True, write_through=True)
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
p = sys.argv[1]
reqs = load_botbattle(p, my_seat=0)
m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
out = []
for req, meta in reqs:
    st = G.parse_request(req)
    try: O.build_model_from_history(m, req, st)
    except Exception: pass
    try: ctx.update(st)
    except Exception: pass
    a = S.decide(st, m, ctx, debug=False)
    out.append("h%s/%s:%s%s" % (meta.get("hand"), st.stage,
                                a.get("act"), a.get("num") or ""))
print(json.dumps(out))
'''.replace("__CONTENT__", CONTENT)


def run(log, extra_env, mc_iters="30000", mc_budget="5.0"):
    env = dict(os.environ, WB_MC_ITERS=mc_iters, WB_MC_BUDGET=mc_budget)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, "-c", CHILD, log],
                       capture_output=True, text=True, env=env, cwd=CONTENT)
    if r.returncode != 0:
        print("!! 子进程失败:", r.stderr[-600:])
        return None
    line = r.stdout.strip().splitlines()[-1]
    return json.loads(line)


def diff(a, b, tag):
    d = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    print("  %-40s 差异 %d / %d 点" % (tag, len(d), min(len(a), len(b))))
    for i, x, y in d[:10]:
        print("      #%-3d  %-24s | %-24s" % (i, x, y))
    return d


def main():
    logs = sys.argv[1:] or [
        os.path.join(os.path.expanduser("~"), "Downloads",
                     "botbattle-holdem-20261001215122-70205a71-log.json")]
    mc = os.environ.get("MC", "30000")
    budget = os.environ.get("BUDGET", "5.0")
    for log in logs:
        print("=" * 100)
        print("日志:", os.path.basename(log), " MC_ITERS=%s BUDGET=%s" % (mc, budget))
        a = run(log, None, mc, budget)
        b = run(log, None, mc, budget)
        c = run(log, {"WB_NO_BIGMONEY_TOPTWO": "1"}, mc, budget)
        if a is None or b is None or c is None:
            continue
        print("  （决策点总数 %d）" % len(a))
        d_ctl = diff(a, b, "对照组：同配置跑两遍（测纯噪声）")
        d_arm = diff(a, c, "实验组：豁免ON vs OFF")
        print()
        if not d_ctl:
            print("  ⇒ 对照组 0 差异：重放在此行口径下**确定性**，H53 那种差异属真实效应。")
        else:
            print("  ⇒ ★ 对照组**不为 0**：重放带噪声！所有 diff 幅度结论需按此噪声下限解读。")
        print("  ⇒ 实验组净效应 = %d 点；扣除噪声 ≈ %d 点"
              % (len(d_arm), max(0, len(d_arm) - len(d_ctl))))


main()
