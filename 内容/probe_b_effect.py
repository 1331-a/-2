# -*- coding: utf-8 -*-
"""probe_b_effect.py — 【方案B 验收】开池尺寸 2.5BB → 3.5BB 的实际影响。

做法（沿用 A 的教训：**必须子进程隔离**，因为 decide() 会就地 mutate
model/ctx，同进程连跑两臂会得到假的差异）：

  对每份日志跑两个臂：
    旧臂 = 旧尺寸常量（OPEN 2.5 / ISO 3.2 / STATION 2.2 / STEAL 2.5 /
           学习代表值 2.2/3.0/4.0）
    新臂 = 当前（B 生效）常量
  逐决策对比动作，并单独统计**我方翻前加注尺寸分布**。

用法：
    python probe_b_effect.py                       # 4 份 0924 日志
    python probe_b_effect.py "记录/*.json"
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

CHILD = r'''
import os, sys, json
sys.path.insert(0, os.getcwd())
import strategy, opponent

OFF = os.environ.get("WB_OLD_OPEN") == "1"
if OFF:
    strategy.OPEN_SIZE_BB = 2.5
    strategy.OPEN_SIZE_VS_STATION = 2.2
    strategy.ISO_SIZE_BB = 3.2
    strategy.STEAL_OPEN_BB = 2.5
    _old = {"pf_s": 2.2, "pf_m": 3.0, "pf_l": 4.0}
    _cur = opponent.OpponentModel.bucket_to_frac
    opponent.OpponentModel.bucket_to_frac = staticmethod(
        lambda b: _old.get(b, _cur(b)))

from game_state import parse_request
from strategy import decide, DecisionLogger
from opponent import OpponentModel, build_model_from_history
from match_ctx import MatchContext
from botbattle_log import load_botbattle

path = sys.argv[1]
seat = int(sys.argv[2]) if len(sys.argv) > 2 else 0
reqs = load_botbattle(path, my_seat=seat) or []
model = OpponentModel()
ctx = MatchContext.from_dict(model.ctx_dict)
DecisionLogger.enable(False)

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
        a = decide(st, model, ctx, debug=False)
        out.append({
            "hand": meta.get("hand"), "street": meta.get("street"),
            "act": a.get("act"), "num": a.get("num"),
            "pot": st.pot, "bb": st.big_blind, "to_call": st.to_call,
        })
    except Exception as e:
        out.append({"hand": meta.get("hand"), "err": str(e)})
print("@@@" + json.dumps(out))
'''


def run(path, seat, old):
    env = dict(os.environ)
    if old:
        env["WB_OLD_OPEN"] = "1"
    else:
        env.pop("WB_OLD_OPEN", None)
    r = subprocess.run([PY, "-c", CHILD, path, str(seat)],
                       capture_output=True, text=True, env=env, cwd=HERE)
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise SystemExit("child failed")
    for line in r.stdout.splitlines():
        if line.startswith("@@@"):
            return json.loads(line[3:])
    raise SystemExit("no payload")


def main():
    pats = sys.argv[1:] or ["记录/botbattle-holdem-20260924*.json"]
    files = []
    for p in pats:
        files += sorted(glob.glob(p)) if any(c in p for c in "*?") else [p]

    tot_pts = tot_chg = 0
    pre_sizes_old, pre_sizes_new = [], []
    for path in files:
        o = run(path, 0, old=True)
        n = run(path, 0, old=False)
        m = min(len(o), len(n))
        chg = []
        for i in range(m):
            if o[i].get("act") != n[i].get("act"):
                chg.append((i, o[i], n[i]))
            elif o[i].get("act") == "raise" and \
                    abs((o[i].get("num") or 0) - (n[i].get("num") or 0)) > 1:
                chg.append((i, o[i], n[i]))
        for r in o:
            if r.get("street") == "preflop" and r.get("act") == "raise":
                pre_sizes_old.append(r.get("num"))
        for r in n:
            if r.get("street") == "preflop" and r.get("act") == "raise":
                pre_sizes_new.append(r.get("num"))

        name = os.path.basename(path)
        print("=" * 78)
        print("%s   决策点 %d  改动 %d" % (name, m, len(chg)))
        for i, a, b in chg[:12]:
            print("  #%-3d H%-3s %-8s 旧 %s %-6s → 新 %s %-6s  (pot=%s bb=%s)" % (
                i, a.get("hand"), a.get("street"),
                a.get("act"), a.get("num"), b.get("act"), b.get("num"),
                a.get("pot"), a.get("bb")))
        tot_pts += m
        tot_chg += len(chg)

    print("=" * 78)
    print("总计：%d 决策点，改动 %d（%.1f%%）" % (
        tot_pts, tot_chg, (tot_chg / tot_pts * 100) if tot_pts else 0))


def _sum(s):
    return ("n=%d 中位=%s 均值=%.0f 范围 %s~%s" % (
        len(s), sorted(s)[len(s) // 2] if s else "-",
        (sum(s) / len(s)) if s else 0,
        min(s) if s else "-", max(s) if s else "-")) if s else "无"


if __name__ == "__main__":
    main()
