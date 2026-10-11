# -*- coding: utf-8 -*-
"""【2026-10-11】量化「to_call 刚好压过 3000」这条悬崖。

口径：**用 `GameState` 直接解析我方每个「面对下注」的决策点**（权威，且不需要跑 MC）。
      不自己重建底池 —— 手工重建踩过两次坑：
      · 按街清零底池 ⇒ 漏掉前面街的筹码，会把满池下注判成「1.00 倍池」的假象；
      · `hand_start.sb/.bb` 是座位号不是金额；`action.amount` 对 raise 是「本街 raise-to」。

用法：python 测/cliff_3000.py
"""
import glob
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

import game_state as G                      # noqa: E402
import strategy as S                        # noqa: E402
from botbattle_log import load_botbattle    # noqa: E402
from evaluator import CATEGORY_NAMES        # noqa: E402

ALL = sorted(set(glob.glob(os.path.join(BASE, "内容", "记录", "*botbattle*log.json"))
                 + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))

rows = []   # (日志, 手, 街, to_call, 决策时底池, 下注前底池, 我方剩余, any_allin, 牌型)
for p in ALL:
    try:
        obj = json.load(io.open(p, encoding="utf-8"))
    except Exception:
        continue
    m0 = obj.get("match") or {}
    mine = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            mine = i
    for req, meta in load_botbattle(p, my_seat=mine):
        try:
            st = G.parse_request(req)
        except Exception:
            continue
        tc = int(st.to_call)
        if tc <= 0:
            continue
        rows.append((os.path.basename(p)[17:31], int(meta.get("hand")), st.stage, tc,
                     int(st.pot), int(st.pot) - tc, int(st.my_left), bool(st.any_allin),
                     CATEGORY_NAMES.get(S._effective_category(st), "?")))

print("日志 %d 份 | 我方「面对下注」决策点 %d" % (len(ALL), len(rows)))
print()

BUCKETS = [(0, 500), (500, 1000), (1000, 2000), (2000, 2900), (2900, 3001),
           (3001, 4000), (4000, 6000), (6000, 8000), (8000, 10 ** 9)]
print("=== to_call 分布 ===")
print("  %-18s %6s %10s" % ("区间", "样本", "占全部"))
for lo, hi in BUCKETS:
    sub = [r for r in rows if lo <= r[3] < hi]
    if not sub:
        continue
    tag = "   <-- 悬崖后第一档" if lo == 3001 else ""
    print("  %5d ~ %-11s %6d %9.1f%%%s"
          % (lo, hi if hi < 10 ** 9 else "inf", len(sub), 100.0 * len(sub) / len(rows), tag))

big = [r for r in rows if r[3] > 3000]


def is_shove(r):
    return r[7] or r[3] >= r[6] * 0.95


A = [r for r in big if is_shove(r)]
B = [r for r in big if not is_shove(r)]

print()
print("★ to_call > 3000: %d / %d = %.1f%%" % (len(big), len(rows), 100.0 * len(big) / len(rows)))
print("   A 对手推光 / 需跟 >= 我方剩余 : %d 次" % len(A))
print("   B 普通下注（身后还有筹码）   : %d 次   <-- 只有这部分才是「被压住」的问题" % len(B))

print()
print("=== B 类全部明细（GameState 口径）===")
print("   %-9s %-5s %-7s %8s %9s %8s %8s  %s"
      % ("日志", "手", "街", "to_call", "下注前池", "倍池", "占剩余", "牌型"))
for r in B:
    print("   %-9s 手%-3d %-7s %8d %9d %7.2fx %7.0f%%  %s"
          % (r[0], r[1], r[2], r[3], r[5], r[3] / max(1, r[5]),
             100.0 * r[3] / max(1, r[6]), r[8]))

print()
print("=== A 类（推光）里 to_call 在 (3000, 10000] 的 —— 压线式推光 ===")
sub = [x for x in A if x[3] <= 10000]
if not sub:
    print("   （无）")
for r in sub:
    print("   %-9s 手%-3d %-7s to_call=%-6d 剩余=%-6d 池前=%-6d"
          % (r[0], r[1], r[2], r[3], r[6], r[5]))

print()
print("=== 对照：悬崖两侧（2900~3000 vs 3001~4000）===")
for lo, hi in ((2900, 3001), (3001, 4000)):
    s = [r for r in rows if lo <= r[3] < hi]
    print("   %d~%d: n=%d" % (lo, hi, len(s)))
    for r in s:
        print("       %-9s 手%-3d %-7s to_call=%-6d 牌型=%-5s"
              % (r[0], r[1], r[2], r[3], r[8]))
