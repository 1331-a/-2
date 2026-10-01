# -*- coding: utf-8 -*-
"""验证「决策可复现 + 单步耗时」——自动扫描全部可用真实对局日志。

用法:
    python check_repro.py                # 扫 内容/记录/*.json + Downloads/botbattle*.json
    python check_repro.py <某个.json>    # 只测这一个
环境变量:
    LIMIT  每份日志最多重放多少个决策点（默认 60）
    SEAT   我方座位（默认 0；可用 --seat N 覆盖）
"""
import glob
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True,
                              write_through=True)
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

import strategy as S           # noqa: E402
import game_state as G         # noqa: E402
import opponent as O           # noqa: E402
import match_ctx as M          # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

LIMIT = int(os.environ.get("LIMIT", "60"))
SEAT = int(os.environ.get("SEAT", "0"))

_args = [a for a in sys.argv[1:] if not a.startswith("--")]
for a in sys.argv[1:]:
    if a.startswith("--seat="):
        SEAT = int(a.split("=", 1)[1])

if _args:
    LOGS = _args
else:
    LOGS = sorted(set(
        glob.glob(os.path.join(BASE, "内容", "记录", "*botbattle*log.json"))
        + glob.glob("C:/Users/HP/Downloads/botbattle*log.json")
    ))


def replay(path, probe=None):
    """重放一份日志前 LIMIT 个决策点，返回 (动作序列, 每步耗时)。

    probe : 若给出，只在**该索引**的决策点记录耗时明细（诊断用）。
    """
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    reqs = load_botbattle(path, my_seat=SEAT)
    acts, times = [], []
    for i, (req, meta) in enumerate(reqs[:LIMIT]):
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        if probe is not None and i == probe:
            _profile(st, m, ctx, i)
        t0 = time.perf_counter()
        try:
            a = S.decide(st, m, ctx, debug=False)
            s = json.dumps(a, ensure_ascii=False, sort_keys=True) \
                if isinstance(a, dict) else str(a)
        except Exception as e:
            s = "ERR:" + repr(e)
        times.append(time.perf_counter() - t0)
        acts.append("h%s:%s" % (meta.get("hand"), s))
    return acts, times


def _profile(st, m, ctx, idx):
    """打印第 idx 个决策点的输入形态 + 逐段耗时，用于定位超时。"""
    print("\n===== 诊断第 %d 个决策点 =====" % idx)
    try:
        print("  hand=%s stage=%s board=%d hole=%s my_chips=%s to_call=%s "
              "pot=%s my_left=%s" % (st.hand_num, st.stage, len(st.board),
                                     st.hole, st.my_chips, st.to_call,
                                     st.pot, st.my_left))
        print("  curbet=%s  round=%s  dealer=%s" % (st.curbet, st.current_round,
                                                    st.dealer))
        print("  hist_len=%d" % len(st.history or []))
        print("  last_preflop_raiser=%s  street_raises=%s"
              % (S._last_preflop_raiser(st), S._opp_street_raises(st)))
    except Exception as e:
        print("  状态打印失败:", e)
    # 逐段计时：把 decide 的关键阶段单独跑
    segs = []
    def _t(name, fn):
        t = time.perf_counter()
        try:
            r = fn()
            segs.append((name, time.perf_counter() - t, repr(r)[:40]))
        except Exception as e:
            segs.append((name, time.perf_counter() - t, "ERR:" + repr(e)[:60]))
    _t("_opp_range_pct", lambda: S._opp_range_pct(
        m, S._opp_raised_preflop(st), S._opp_street_raises(st)))
    _t("monte_carlo_equity", lambda: S.monte_carlo_equity(
        st.hole, st.board, iterations=S.MC_ITERATIONS,
        opp_range_pct=S._opp_range_pct(m, S._opp_raised_preflop(st),
                                       S._opp_street_raises(st)),
        deadline=S._eq_deadline()))
    _t("equity_best", lambda: S.equity_best(
        st.hole, st.board, iterations=S.MC_ITERATIONS,
        opp_range_pct=S._opp_range_pct(m, S._opp_raised_preflop(st),
                                       S._opp_street_raises(st)),
        deadline=S._eq_deadline()))
    for nm, dt, r in segs:
        print("  %-22s %8.2fs  %s" % (nm, dt, r))
    # 最后一次决定性的决定
    t = time.perf_counter()
    S.decide(st, m, ctx, debug=False)
    print("  %-22s %8.2fs" % ("decide 整轮", time.perf_counter() - t))
    print("==============================\n")


print("配置: MC_ITERATIONS=%s  TIME_BUDGET=%.1fs  ALLIN_MC=%s  EQ_TOTAL=%.1fs  "
      "DECISION_TIMEOUT=%.0fs" % (S.MC_ITERATIONS, S.TIME_BUDGET, S.ALLIN_MC,
                                  S.EQ_TOTAL_BUDGET, S.DECISION_TIMEOUT))
print("座位 = %d   每份日志最多 %d 个决策点   共 %d 份日志\n" % (SEAT, LIMIT, len(LOGS)))
if not LOGS:
    print("没有找到对局日志 —— 把 json 放到 内容/记录/ 或 Downloads/ 即可")
    raise SystemExit(1)

tot_same = tot_n = 0
all_time = []
worst_step = (0.0, "")
for path in LOGS:
    try:
        t0 = time.perf_counter()
        a1, t1 = replay(path)
        wall1 = time.perf_counter() - t0
        a2, _t2 = replay(path)
    except Exception as e:
        print("%-46s  ✗ 跳过（%r）" % (os.path.basename(path)[:46], e))
        continue
    if not a1:
        print("%-46s  (无决策点)" % os.path.basename(path)[:46])
        continue
    same = sum(1 for x, y in zip(a1, a2) if x == y)
    tot_same += same
    tot_n += len(a1)
    all_time.extend(t1)
    mx = max(range(len(t1)), key=lambda i: t1[i])
    if t1[mx] > worst_step[0]:
        worst_step = (t1[mx], os.path.basename(path)[:28] + " / " + a1[mx][:40])
    print("%-46s  一致 %3d/%3d   总 %5.1fs  均 %4.2fs  最慢 %5.2fs"
          % (os.path.basename(path)[:46], same, len(a1), wall1, wall1 / len(a1), t1[mx]))
    for x, y in zip(a1, a2):
        if x != y:
            print("      ✗ 不一致: %s  vs  %s" % (x, y))

print()
print("=== ① 可复现性 ===")
print("  两次重放动作一致: %d / %d" % (tot_same, tot_n))
print("  " + ("✅ 完全一致（抽样已播种，决策确定性）" if tot_same == tot_n
              else "⚠️ 存在不一致，见上"))

print()
print("=== ② 耗时 ===")
if all_time:
    st = sorted(all_time)
    print("  决策点总数: %d" % len(all_time))
    print("  单步: 中位 %.2fs  90分位 %.2fs  最慢 %.2fs  (= 预算的 %.1f%%)"
          % (st[len(st) // 2], st[int(len(st) * 0.9)], st[-1], st[-1] / 60.0 * 100))
    print("  最慢一步: %s" % worst_step[1])
    over = sum(1 for d in all_time if d > 20.0)
    print("  超过 20 秒的步数: %d / %d" % (over, len(all_time)))
else:
    print("  (无数据)")
