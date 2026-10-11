# -*- coding: utf-8 -*-
"""【2026-10-11】决策归因探针 —— 「这一步到底是谁说了算？」

【背景】文献 §9.6/§9.7 的敏感度探针证明：`eq` 摆动 16 倍、最终动作只动 ≤1.4%。
⇒ 说明动作**不是 eq 决定的**。本探针回答"那到底是谁"：
  ① 入口短路（规则2/18）
  ② 决策层：翻前 / 主动侧(_check_side) / 面对下注(_face_bet)
     ②a `_face_bet` 在「eq 开始说话之前」就 return 的硬规则（附具体规则名）
     ②b `_face_bet` 走到 eq 门槛比较才决定
  ③ 出口链改写（最终动作 != 决策层输出）

【怎么做】**不改 bot 代码**
  · 把决策层的各个「可返回动作」的函数包一层，记录 (函数名, 返回值)；
    最后一个记录 = 真正下手的那个。
  · 在 `_face_bet` / `_check_side` 内部装**局部行追踪**（`sys.settrace`），
    拿到它最后执行到的那一行 → 映射成规则名。
    ★ 追踪只在决策函数内部开（进出即开关），不进 MC 热循环。
  · 出口链按 `exit_chain_probe.py` 的方式包 10 层，比「第一层输入 vs 最终」。

用法:
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.3 python 测/owner_probe.py
    python 测/owner_probe.py <log1.json> <log2.json>      # 指定日志（绝对路径）
"""
import glob
import io
import json
import os
import sys
import collections

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
CONTENT = os.path.join(BASE, "内容")
sys.path.insert(0, CONTENT)

import strategy as S            # noqa: E402
import game_state as G          # noqa: E402
import opponent as O            # noqa: E402
import match_ctx as M           # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

# ---------------- `_face_bet` 的行 → 规则名 / 类别 ----------------
# 类别：HARD = 硬规则（不咨询 eq）；EQ = 由 eq 门槛决定；TYPE = 牌型/尺寸驱动
# ★★ 行号会随 `strategy.py` 的编辑漂移 —— 每次改完生产代码都要重新核对！
#    生成命令（打印 `_face_bet` 内所有 return 及其条件行）：
#      grep -n "^def _face_bet" 内容/strategy.py
#      awk 'NR>=A && NR<=B {printf "%d\t%s\n",NR,$0}' 内容/strategy.py | grep "return "
#    （2026-10-11 核对版本：`_face_bet` = 5010~5407）
FB_LINES = {
    5039: ("规则11 同花威胁", "HARD"),
    5045: ("规则14 小注诈唬读", "HARD"),
    5092: ("大注+无坚果(>0.6池)", "HARD"),
    5102: ("4倍突袭+wet公面", "HARD"),
    5120: ("4倍突袭+<三条", "HARD"),
    5250: ("偷盲档被加注", "HARD"),
    5282: ("选项B 闸门(eq)", "EQ"),
    5299: ("河牌裸公对陷阱", "HARD"),
    5318: ("全下档: eq vs thr", "EQ"),
    5329: ("强牌全下(顺子+/eq>=.82)", "TYPE"),
    5332: ("强牌全下(追分)", "TYPE"),
    5334: ("强牌全下(浅筹码+eq>=.72)", "TYPE"),
    5338: ("河牌超池(坚果)", "TYPE"),
    5342: ("强牌加注(学习尺寸)", "TYPE"),
    5343: ("强牌加注(常规)", "TYPE"),
    5351: ("好牌加注(学习尺寸)", "TYPE"),
    5352: ("好牌加注(位置+eq>=.68)", "TYPE"),
    5355: ("便宜跟注封顶 → fold", "HARD"),
    5357: ("eq>=eff_req+margin → call", "EQ"),
    5359: ("疯子/追分宽接 → call", "EQ"),
    5360: ("eq 不足 → fold", "EQ"),
    5366: ("强听牌半诈唬 → raise", "TYPE"),
    5368: ("eq>=eff_req → call", "EQ"),
    5370: ("隐含赔率/追分 → call", "EQ"),
    5371: ("强听牌 eq 不足 → fold", "EQ"),
    5377: ("便宜跟注封顶 → fold", "HARD"),
    5379: ("eq>=eff_req+margin+.03 → call", "EQ"),
    5381: ("疯子/追分宽接 → call", "EQ"),
    5382: ("中等牌 eq 不足 → fold", "EQ"),
    5388: ("便宜跟注封顶 → fold", "HARD"),
    5390: ("弱听牌便宜跟 → call", "EQ"),
    5391: ("弱听牌 → fold", "EQ"),
    5404: ("空气反诈唬 → fold", "TYPE"),
    5405: ("空气反诈唬 → raise", "TYPE"),
    5406: ("空气 → fold", "TYPE"),
}

# 动作「激进度」序（用于判断出口链把动作改向哪边）：
#   fold < check < call < raise < allin
_ORDER = {"fold": 0, "check": 1, "call": 2, "raise": 3, "allin": 4}


def _dir_of(b, a):
    """出口链改写方向：更保守 / 更激进 / 同向。"""
    try:
        x, y = _ORDER.get(b[0]), _ORDER.get(a[0])
    except Exception:
        return "?"
    if x is None or y is None:
        return "?"
    if y < x:
        return "更保守"
    if y > x:
        return "更激进"
    return "同向(仅尺寸)"

# 决策层「可返回动作」的函数（最后一个记录 = 真正下手的）
DECIDERS = ["_preflop_decide", "_preflop_allin_decide", "_risk_avoid_route",
            "_check_side", "_check_side_stable", "_face_bet", "_flush_made_guard"]
# 入口短路（返回动作 dict 才算）
ENTRY = ["_lock_win_unified", "_gamble_plan"]
# 出口链
CHAIN = ["_lock_win_tail_guard", "_bet_cap_guard", "_aggressive_strong_bet",
         "_bluff_cap_guard", "_stability_guard", "_normalize",
         "_endgame_arbitrate", "_big_money_guard", "_cheap_call_guard",
         "_doom_call_upgrade"]

_REC = []          # 本决策点的 [(函数名, 动作, 行号)]
_TRACE = []        # 本决策点出口链的翻转记录 [(层名, before, after)]
_CALLS = {}        # 出口链各层「被调用」总次数（跨全部决策点累计）
_first_in = [None]  # 出口链第一层的输入（= 决策层输出）
_eq_called = [False]


def _norm(a):
    if a is None:
        return None
    if not isinstance(a, dict):
        return ("?", str(a))
    return (str(a.get("act")), int(a.get("num") or 0))


def _find_action(args):
    for a in args:
        if isinstance(a, dict) and "act" in a:
            return a
    return None


_lastline = {}


def _local(frame, event, arg):
    if event == "line":
        _lastline[frame.f_code.co_name] = frame.f_lineno
    return _local


def _global(frame, event, arg):
    if event == "call" and frame.f_code.co_name in ("_face_bet", "_check_side"):
        return _local
    return None


def install():
    for name in DECIDERS:
        orig = getattr(S, name, None)
        if orig is None:
            continue

        def make(nm, fn):
            def wrapper(*args, **kw):
                inp = _find_action(args)
                if nm in ("_face_bet", "_check_side"):
                    _lastline.clear()
                    sys.settrace(_global)
                    try:
                        out = fn(*args, **kw)
                    finally:
                        sys.settrace(None)
                else:
                    out = fn(*args, **kw)
                if isinstance(out, dict) and "act" in out:
                    # ★ 护栏类：**没改写就不算它**（否则它会把内层 _face_bet 整个盖住）
                    if nm == "_flush_made_guard" and _norm(inp) == _norm(out):
                        return out
                    _REC.append((nm, _norm(out), _lastline.get(nm)))
                return out
            wrapper.__name__ = nm
            return wrapper
        setattr(S, name, make(name, orig))

    for name in ENTRY:
        orig = getattr(S, name, None)
        if orig is None:
            continue

        def make_e(nm, fn):
            def wrapper(*args, **kw):
                out = fn(*args, **kw)
                if isinstance(out, dict) and "act" in out:
                    _REC.append(("入口:" + nm, _norm(out), None))
                return out
            wrapper.__name__ = nm
            return wrapper
        setattr(S, name, make_e(name, orig))

    for name in CHAIN:
        orig = getattr(S, name, None)
        if orig is None:
            continue

        def make_c(nm, fn):
            def wrapper(*args, **kw):
                before = _find_action(args)
                if _first_in[0] is None and before is not None:
                    _first_in[0] = _norm(before)
                out = fn(*args, **kw)
                _CALLS[nm] = _CALLS.get(nm, 0) + 1
                if isinstance(out, dict) and "act" in out:
                    b, a = _norm(before), _norm(out)
                    if b is not None and b != a:
                        _TRACE.append((nm, b, a))
                return out
            wrapper.__name__ = nm
            return wrapper
        setattr(S, name, make_c(name, orig))

    _orig_eq = S.equity_best

    def _eqw(*a, **kw):
        _eq_called[0] = True
        return _orig_eq(*a, **kw)
    S.equity_best = _eqw

    _orig_mc = S.monte_carlo_equity

    def _mcw(*a, **kw):
        _eq_called[0] = True
        return _orig_mc(*a, **kw)
    S.monte_carlo_equity = _mcw

    # 打开跟注点全景日志（WB_FACE_LOG：eq / eff_req / margin / 牌型 …）
    # 目的是给每个决策点配上「决策层用的 eq 与门槛」，用于测量
    # 「出口链的更保守改写，有多少发生在 eq 明显够的点上」。
    S.WB_FACE_DEBUG = True


def replay(path, seat):
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    reqs = load_botbattle(path, my_seat=seat)
    out = []
    for req, meta in reqs:
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        _REC.clear()
        _TRACE.clear()
        _first_in[0] = None
        _eq_called[0] = False
        _n0 = len(S.WB_FACE_LOG)
        try:
            fin = S.decide(st, m, ctx, debug=False)
            fn = _norm(fin)
        except Exception as e:
            fn = ("ERR", repr(e)[:24])
        _fb = S.WB_FACE_LOG[_n0:]
        out.append({
            "key": "h%s|%s|nb%d|tc%s" % (meta.get("hand"), st.stage,
                                         len(st.board), st.to_call),
            "stage": st.stage,
            "rec": list(_REC),
            "trace": list(_TRACE),
            "dl": _first_in[0],
            "fin": fn,
            "eq": _eq_called[0],
            "face": (_fb[-1] if _fb else None),
        })
    return out


def mine_seat(path):
    try:
        obj = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return 0
    m0 = obj.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


def owner_of(rec):
    """判定这个决策点归谁。返回 (大类, 细分名)。"""
    if not rec:
        return ("未捕获", "-")
    name, act, line = rec[-1]
    if name.startswith("入口:"):
        return ("入口短路", name[3:])
    if name == "_face_bet":
        if line in FB_LINES:
            nm, cat = FB_LINES[line]
            return ("面对下注·" + ("硬规则" if cat == "HARD"
                                 else ("eq门槛" if cat == "EQ" else "牌型尺寸")), nm)
        return ("面对下注·未知行", "L%s" % line)
    if name in ("_check_side", "_check_side_stable"):
        return ("主动侧(_check_side)", name)
    if name == "_flush_made_guard":
        return ("同花护栏", name)
    if name in ("_preflop_decide", "_preflop_allin_decide", "_risk_avoid_route"):
        return ("翻前", name)
    return ("其它", name)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True,
                                  write_through=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        logs = args
    else:
        logs = sorted(set(
            glob.glob(os.path.join(CONTENT, "记录", "*botbattle*log.json"))
            + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))

    print("抽样口径： WB_MC_ITERS=%s  WB_MC_BUDGET=%s"
          % (os.environ.get("WB_MC_ITERS", "1500"),
             os.environ.get("WB_MC_BUDGET", "0.3")))
    print("日志 %d 份\n" % len(logs))

    install()

    cat_n = collections.Counter()
    sub_n = collections.Counter()
    stage_cat = collections.Counter()
    flip_n = collections.Counter()      # 各大类里被出口链改写的点数
    eq_cat = collections.Counter()      # 各大类「是否咨询了胜率」
    n_tot = 0
    n_flip = 0
    hard_examples = []
    eq_flips = []
    rows_all = []

    for p in logs:
        tag = os.path.basename(p)[17:31]
        try:
            recs = replay(p, mine_seat(p))
        except Exception as e:
            print("  ✗ %-15s 跳过（%r）" % (tag, e))
            continue
        for r in recs:
            n_tot += 1
            c, s = owner_of(r["rec"])
            rows_all.append((tag, c, r))
            cat_n[c] += 1
            sub_n[(c, s)] += 1
            stage_cat[(r["stage"], c)] += 1
            eq_cat[(c, r["eq"])] += 1
            if r["dl"] is not None and r["fin"] is not None and r["dl"] != r["fin"]:
                n_flip += 1
                flip_n[c] += 1
                if c == "面对下注·eq门槛":
                    eq_flips.append((tag, r))
            if c == "面对下注·硬规则" and len(hard_examples) < 12:
                hard_examples.append((tag, r["key"], s, r["fin"]))
        print("  ✓ %-15s 决策点 %3d" % (tag, len(recs)))

    print()
    print("=" * 90)
    print("决策点总数 %d" % n_tot)
    print()
    print("=== ① 谁说了算（决策层归属）===")
    print("  %-22s %8s %8s %10s" % ("归属", "点数", "占比", "含胜率咨询"))
    for c, v in cat_n.most_common():
        e = eq_cat.get((c, True), 0)
        print("  %-22s %8d %7.1f%% %10d" % (c, v, v / n_tot * 100, e))
    print()
    print("=== ② 细分（Top 20）===")
    for (c, s), v in sub_n.most_common(20):
        print("  %-22s %-28s %5d  %5.1f%%" % (c, s, v, v / n_tot * 100))
    print()
    print("=== ③ 出口链改写率（决策层输出 != 最终动作）===")
    print("  总体 %d / %d（%.1f%%）" % (n_flip, n_tot, n_flip / n_tot * 100))
    for c, v in flip_n.most_common():
        print("     %-22s %5d / %-5d  %5.1f%%"
              % (c, v, cat_n[c], v / max(1, cat_n[c]) * 100))
    print()
    print("=== ④ 归属 × 街 ===")
    stages = ["preflop", "flop", "turn", "river"]
    cats = [c for c, _ in cat_n.most_common()]
    print("  %-22s %s" % ("归属", "".join("%9s" % s for s in stages)))
    for c in cats:
        row = [stage_cat.get((s, c), 0) for s in stages]
        if sum(row):
            print("  %-22s %s" % (c, "".join("%9d" % v for v in row)))
    print()
    print("=== ⑤ 「不看 eq 的硬规则」样例（_face_bet 提前 return）===")
    for tag, key, s, fin in hard_examples:
        print("  %-15s %-26s %-26s → %s" % (tag, key, s, fin))
    print()
    print("=== ⑥ ★ eq 门槛的结论被出口链盖掉的点 ===")
    layer_cnt = collections.Counter()
    for tag, r in eq_flips:
        for nm, b, a in r["trace"]:
            layer_cnt[nm] += 1
    print("  合计 %d 点；改写层分布：" % len(eq_flips))
    for nm, v in layer_cnt.most_common():
        print("     %-24s %3d" % (nm, v))
    for tag, r in eq_flips:
        chain = " > ".join("%s:%s→%s" % (nm, b[0], a[0]) for nm, b, a in r["trace"])
        print("  %-15s %-24s 决策层%s → 最终%s" % (tag, r["key"], r["dl"][0], r["fin"][0]))
        print("        %s" % chain)

    print()
    print("=== ⑦ ★ 出口链逐层改写（全量 %d 点）===" % n_tot)
    lay = collections.Counter()
    lay_dir = collections.Counter()
    called = collections.Counter()
    for tag, c, r in rows_all:
        seen = set()
        for nm, b, a in r["trace"]:
            lay[nm] += 1
            lay_dir[(nm, _dir_of(b, a))] += 1
            seen.add(nm)
        for nm in seen:
            called[nm] += 1
    tot_flip = sum(lay.values())
    print("  改写总次数 %d，涉及 %d 个决策点（%.1f%%）"
          % (tot_flip, n_flip, n_flip / max(1, n_tot) * 100))
    print("  %-24s %8s %8s %8s %8s %8s %8s"
          % ("层", "调用次数", "有改写点", "改写次数", "更保守", "更激进", "仅尺寸"))
    for nm in CHAIN:
        v = lay.get(nm, 0)
        print("  %-24s %8d %8d %8d %8d %8d %8d %s"
              % (nm, _CALLS.get(nm, 0), called.get(nm, 0), v,
                 lay_dir.get((nm, "更保守"), 0), lay_dir.get((nm, "更激进"), 0),
                 lay_dir.get((nm, "同向(仅尺寸)"), 0),
                 "← 从不改写（纯冗余候选）" if v == 0 else ""))
    print()
    print("=== ⑧ 决策层归属 × 被哪层改写 ===")
    cross = collections.Counter()
    own_tot = collections.Counter()
    for tag, c, r in rows_all:
        own_tot[c] += 1
        for nm, b, a in r["trace"]:
            cross[(c, nm)] += 1
    for c, v in own_tot.most_common():
        parts = ["%s:%d" % (nm, cross.get((c, nm), 0)) for nm in CHAIN
                 if cross.get((c, nm), 0)]
        print("  %-24s %8d  %s" % (c, v, "  ".join(parts) if parts else "（无）"))

    print()
    print("=== ⑨ ★ 出口链「更保守」改写 vs 决策层的 eq 确信度 ===")
    print("  （eq/eff_req/margin 取自已开启的 WB_FACE_LOG；仅面对下注的点有）")
    buckets = collections.Counter()
    details = []
    for tag, c, r in rows_all:
        f = r.get("face")
        for nm, b, a in r["trace"]:
            if _dir_of(b, a) != "更保守":
                continue
            if not f:
                buckets["（该点没有 eq 记录）"] += 1
                continue
            eq = float(f.get("eq", 0.0))
            req = float(f.get("eff_req", 1.0))
            mg = float(f.get("margin", 0.0))
            edge = eq - (req + mg)
            if edge >= 0.10:
                k = "eq 超门槛 ≥ +0.10"
            elif edge >= 0.05:
                k = "eq 超门槛 +0.05~0.10"
            elif edge >= 0.0:
                k = "eq 超门槛 0~+0.05"
            else:
                k = "eq 本来就不够（<门槛）"
            buckets[k] += 1
            if edge >= 0.05 and len(details) < 25:
                details.append((tag, r["key"], nm, b[0], a[0], eq, req, mg, edge))
    tot_c = sum(buckets.values())
    print("  「更保守」改写合计 %d 次：" % tot_c)
    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print("     %-24s %4d  %5.1f%%" % (k, v, v / max(1, tot_c) * 100))
    if details:
        print("  ★ eq 明显够（超门槛 ≥ +0.05）却被改保守的点：")
        for tag, key, nm, b, a, eq, req, mg, edge in details:
            print("     %-15s %-24s %-22s %s→%s  eq%.3f req%.3f mg%.3f 超%.3f"
                  % (tag, key, nm, b, a, eq, req, mg, edge))


if __name__ == "__main__":
    main()
