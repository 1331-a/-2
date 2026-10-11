# -*- coding: utf-8 -*-
"""【2026-10-11】文献 §9.6 第 1 步：量化 —— 把 range_pct 换成 N 个对手原型后，最终动作会变多少次？

【背景】`文献调研_可借鉴方案.md` §九（NeurIPS 2018 Depth-Limited Solving）：
论文指出「叶子只填一个值」= 假设对手打法固定 ⇒ 精修打不过蓝图。
我们的决策层正是一个单值：`eq = f(底牌, 公牌, range_pct标量)`。
§9.4① / §9.6 第 1 步：**先不接线，只量化**——把 `range_pct` 乘上不同倍率
（模拟"对手是另一种类型"），看「最终动作」变了多少。

【怎么做】**不改 bot 代码**：只 monkey-patch `S._opp_range_pct`（乘倍率）与
`S.equity_best`（顺便记录每次 eq）。每份日志重放 K 遍（每遍一个新模型），
对比同一决策点在不同倍率下的 (最终动作, eq)。

【指标】
  ① eq 变化幅度（证明旋钮真的拧动了 —— 触发计数器）
  ② **最终动作改变**的决策点数（核心指标）
  ③ 对照臂：同一倍率跑两遍，应逐点一致（噪声底）

【重要口径说明】
  · 倍率作用在 `_opp_range_pct` 的**返回值**上，再 clamp 回 [0.05, 0.95]（与函数内一致）。
  · 河牌/转牌走精确枚举 ⇒ 该部分**无抽样误差**；翻牌及以前是 MC（有 ~1% 误差）。
  · 状态演化（模型/ctx）只依赖 request，与我们选什么动作无关 ⇒ 各遍可逐点对齐。

用法:
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/range_meta_probe.py
    python 测/range_meta_probe.py <a.json> <b.json>     # 只测指定日志
"""
import glob
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True, write_through=True)

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
CONTENT = os.path.join(BASE, "内容")

# 【对手原型菜单】倍率作用在 range_pct 上：
#   0.50 = 偏弃（nit/rock：继续入池的牌更紧）
#   1.00 = 现状（基线）
#   1.60 = 偏跟（station：继续入池的牌更宽）
#   2.50 = 偏加（maniac/LAG：大量用边缘牌开火）
#   0.25 / 4.00 = 极端臂（诊断用：确认"没变化"不是因为倍率太温和）
# ★ 最后一个 1.0 是**对照臂**（与第一个同值，用来确认噪声底）
MULTS = [1.0, 0.50, 1.60, 2.50, 0.25, 4.00, 1.0]
LABELS = {1.0: "现状", 0.50: "偏弃", 1.60: "偏跟", 2.50: "偏加",
          0.25: "极紧", 4.00: "极宽"}

CHILD = r'''
import sys, io, json, os
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle

path = sys.argv[1]; seat = int(sys.argv[2]); mults = json.loads(sys.argv[3])

_ORIG_RANGE = S._opp_range_pct
_ORIG_EQ = S.equity_best
_ORIG_MC = S.monte_carlo_equity
CUR = [1.0]
_eq = []

def _range(model, raised, sr=0):
    v = _ORIG_RANGE(model, raised, sr)
    return max(0.05, min(0.95, v * CUR[0]))

def _eqwrap(*a, **kw):
    out = _ORIG_EQ(*a, **kw)
    _eq.append((kw.get("opp_range_pct"), float(out)))
    return out

def _mcwrap(*a, **kw):
    out = _ORIG_MC(*a, **kw)
    _eq.append((kw.get("opp_range_pct"), float(out)))
    return out

S._opp_range_pct = _range
S.equity_best = _eqwrap
S.monte_carlo_equity = _mcwrap

reqs = load_botbattle(path, my_seat=seat)
res = {}
for mt in mults:
    CUR[0] = mt
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    rows = []
    for req, meta in reqs:
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        _eq.clear()
        try:
            a = S.decide(st, m, ctx, debug=False)
            at = str(a.get("act"))
            num = int(a.get("num") or 0)
        except Exception:
            at, num = "ERR", 0
        eq = round(_eq[0][1], 4) if _eq else None
        rp = round(_eq[0][0], 4) if _eq and _eq[0][0] is not None else None
        rows.append(["h%s|%s|nb%d|tc%s" % (meta.get("hand"), st.stage,
                                           len(st.board), st.to_call),
                     at, num, eq, rp])
    res[str(mt)] = rows
print(json.dumps(res))
'''


def run(path, seat):
    e = dict(os.environ)
    e.setdefault("WB_MC_ITERS", "1500")
    e.setdefault("WB_MC_BUDGET", "0.3")
    r = subprocess.run([sys.executable, "-c", CHILD, path, str(seat),
                        json.dumps(MULTS)],
                       capture_output=True, text=True, env=e, cwd=CONTENT)
    if r.returncode != 0:
        return None, r.stderr[-500:]
    return json.loads(r.stdout.strip().splitlines()[-1]), None


def mine_seat(path):
    """从日志里判断我方座位（owner_display 含 j1331）。"""
    try:
        obj = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return 0
    m0 = obj.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        logs = args
    else:
        logs = sorted(set(
            glob.glob(os.path.join(CONTENT, "记录", "*botbattle*log.json"))
            + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))

    NA = len(MULTS)
    base_i, ctrl_i = 0, NA - 1

    print("对手原型（倍率作用在 range_pct 上）:")
    for i, m in enumerate(MULTS):
        note = "（基线）" if i == base_i else (
            "（对照，应与基线逐点一致）" if i == ctrl_i else "")
        print("    %-6s ×%.2f  %s" % (LABELS.get(m, "?"), m, note))
    print("抽样口径： WB_MC_ITERS=%s  WB_MC_BUDGET=%s"
          % (os.environ.get("WB_MC_ITERS", "1500"),
             os.environ.get("WB_MC_BUDGET", "0.3")))
    print("日志 %d 份\n" % len(logs))

    n_tot = 0
    n_eq = 0
    diff_act = [0] * NA
    diff_size = [0] * NA
    eq_shift = [0.0] * NA
    stage_of = {}
    trans = {}
    examples = []
    ctrl_bad = 0
    ok_logs = 0

    for p in logs:
        tag = os.path.basename(p)[17:31]
        seat = mine_seat(p)
        got, err = run(p, seat)
        if got is None:
            print("  ✗ %-15s 跳过（%s）" % (tag, (err or "").strip()[-120:]))
            continue
        ok_logs += 1
        arms = [got[str(m)] for m in MULTS]
        L = min(len(a) for a in arms)
        for i in range(L):
            key = arms[base_i][i][0]
            stage = key.split("|")[1]
            at = [a[i][1] for a in arms]
            nm = [a[i][2] for a in arms]
            eqs = [a[i][3] for a in arms]
            n_tot += 1
            if (at[base_i], nm[base_i]) != (at[ctrl_i], nm[ctrl_i]):
                ctrl_bad += 1
            if eqs[base_i] is not None:
                n_eq += 1
                for k in range(NA):
                    if eqs[k] is not None:
                        eq_shift[k] += (eqs[k] - eqs[base_i])
            hit = False
            for k in range(NA):
                if k == base_i:
                    continue
                if at[k] != at[base_i]:
                    diff_act[k] += 1
                    trans[(at[base_i], at[k])] = \
                        trans.get((at[base_i], at[k]), 0) + 1
                    if k != ctrl_i:
                        stage_of[stage] = stage_of.get(stage, 0) + 1
                    hit = True
                elif nm[k] != nm[base_i]:
                    diff_size[k] += 1
            if hit and len(examples) < 20:
                examples.append((tag, key,
                                 ["%s%s" % (at[k], nm[k] or "") for k in range(NA)],
                                 [e if e is not None else -1 for e in eqs]))
        print("  ✓ %-15s 决策点 %3d  座位 %d" % (tag, L, seat))

    print()
    print("=" * 94)
    print("成功日志 %d 份   决策点总数 %d   其中会算胜率的 %d 个（%.1f%%）"
          % (ok_logs, n_tot, n_eq, n_eq / max(1, n_tot) * 100))
    print()
    print("=== ⓿ 对照臂（×1.00 跑两遍，应与基线逐点一致）===")
    print("  不一致数：%d  →  %s"
          % (ctrl_bad, "噪声底 = 0 ✓" if ctrl_bad == 0 else "★ 有噪声，结论需复核"))
    print()
    print("=== ① 敏感度曲线：range_pct 乘倍率后，最终动作变了几点 ===")
    print("  %-6s %7s %9s %12s %10s %13s"
          % ("臂", "倍率", "act变化", "仅尺寸变化", "占全部", "eq平均偏移"))
    for k in range(NA):
        if k == base_i:
            continue
        note = "   ← 对照" if k == ctrl_i else ""
        sh = eq_shift[k] / n_eq if n_eq else 0.0
        print("  %-6s %7.2f %9d %12d %9.1f%% %+13.4f%s"
              % (LABELS.get(MULTS[k], "?"), MULTS[k], diff_act[k], diff_size[k],
                 diff_act[k] / max(1, n_tot) * 100, sh, note))
    print("  基线 = 现状。「act 变化」= 动作类型变了；「仅尺寸变化」= 类型相同、num 不同。")
    print("  ⚠️ raise 的 num 带 ±15% 抖动，尺寸级差异含噪声成分，以「act 变化」为准。")
    print()
    st_order = ["preflop", "flop", "turn", "river"]
    print("=== ② act 变化点落在哪些街（不含对照臂）===")
    print("  " + ("  ".join("%s %d" % (s, stage_of.get(s, 0)) for s in st_order)
                  if stage_of else "（无）"))
    if trans:
        print("  动作迁移（现状 act → 原型 act）：")
        for (b, x), v in sorted(trans.items(), key=lambda kv: -kv[1])[:12]:
            print("     %-12s → %-12s %4d" % (b, x, v))
    print()
    if examples:
        print("=== ③ 变化样例（动作/eq 均按 现状|偏弃|偏跟|偏加|极紧|极宽；eq -1 = 该点不算胜率）===")
        for tag, key, acts, e4 in examples[:20]:
            print("  %-15s %-26s" % (tag, key))
            print("        动作 %s" % " | ".join(acts))
            print("        eq   %s" % " | ".join("%.3f" % e for e in e4))


if __name__ == "__main__":
    main()
