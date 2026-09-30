# -*- coding: utf-8 -*-
"""验证 P0-A 改动：① 决策可复现（两次重放逐字节一致）② 实际耗时。"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")

import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

LOG = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:/Users/HP/Downloads/botbattle-holdem-20260930201238-94796087-log.json"
SEAT = 0
LIMIT = int(os.environ.get("LIMIT", "60"))


def replay():
    """重放前 LIMIT 个决策点，返回 (动作序列, 每步耗时, 总耗时)。"""
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    reqs = load_botbattle(LOG, my_seat=SEAT)
    acts, times = [], []
    for req, meta in reqs[:LIMIT]:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        t0 = time.perf_counter()
        try:
            a = S.decide(st, m, ctx, debug=False)
        except Exception as e:
            a = {"err": repr(e)}
        dt = time.perf_counter() - t0
        times.append(dt)
        acts.append("%s=%s" % (meta.get("hand"),
                               json.dumps(a, ensure_ascii=False, sort_keys=True)
                               if isinstance(a, dict) else str(a)))
    return acts, times


print("配置: MC_ITERATIONS=%s  TIME_BUDGET=%.1fs  ALLIN_MC=%s  EQ_TOTAL=%.1fs  DECISION_TIMEOUT=%.0fs"
      % (S.MC_ITERATIONS, S.TIME_BUDGET, S.ALLIN_MC, S.EQ_TOTAL_BUDGET, S.DECISION_TIMEOUT))
print("重放 %d 个决策点（座位 %d）\n" % (LIMIT, SEAT))

t0 = time.perf_counter()
a1, t1 = replay()
wall1 = time.perf_counter() - t0
t0 = time.perf_counter()
a2, t2 = replay()
wall2 = time.perf_counter() - t0

print("=== ① 可复现性 ===")
same = sum(1 for x, y in zip(a1, a2) if x == y)
print("  两次重放动作一致: %d / %d" % (same, len(a1)))
if same != len(a1):
    for x, y in zip(a1, a2):
        if x != y:
            print("    ✗ 不一致: %s  vs  %s" % (x, y))
else:
    print("  ✅ 完全一致（抽样已播种，决策确定性）")

print()
print("=== ② 耗时（单进程，本机）===")
allt = sorted(t1)
print("  第 1 轮总耗时: %.1f 秒（%d 步，平均 %.2f 秒/步）" % (wall1, len(t1), wall1 / len(t1)))
print("  第 2 轮总耗时: %.1f 秒" % wall2)
print("  单步耗时: 中位 %.2fs  90分位 %.2fs  最慢 %.2fs" %
      (allt[len(allt) // 2], allt[int(len(allt) * 0.9)], allt[-1]))
print("  平台预算: 60.0 秒/步  →  最慢一步用了 %.1f%% 的预算"
      % (allt[-1] / 60.0 * 100))
over = [i for i, d in enumerate(t1) if d > 20.0]
print("  超过 20 秒的步数: %d" % len(over))

print()
print("=== ③ 动作变化抽样（前 15 步）===")
for i in range(min(15, len(a1))):
    print("  %-40s  %.2fs" % (a1[i], t1[i]))
