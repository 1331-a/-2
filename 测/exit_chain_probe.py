# -*- coding: utf-8 -*-
"""量化出口链的「翻转率」与「层间打架率」——任务 #37。

【为什么】`decide` 的出口是一条 10 层的顺序改写链（每层可覆盖前一层）。
每层单独看都有理由，但叠起来可能互相抵消 —— 真实日志里反复出现
`我加注 → 对方加注 → 我再加注 → 我弃牌` 这种「两头不靠」的动作，
形态上很像层间打架（见 `复盘_20261001_两场vsCodeA.md` §3）。

【怎么做】**不改 bot 代码**：在运行时把出口链的每个函数包一层记录器
（monkey-patch 模块全局名），重放真实日志，逐决策点记录
「第 k 层把动作从 A 改成了 B」。

【指标定义】
  翻转(flip)   ：某层的输出 != 输入（这一层确实改写了动作）
  打架(fight)  ：层 i 把 A→B，之后某层 j 又把 B→A（把上一次的改动画回去了）
  净翻转       ：最终动作 != 决策层输出（整条链对结果有影响）

用法:
    python 测/exit_chain_probe.py                      # 扫 内容/记录 + Downloads
    python 测/exit_chain_probe.py <a.json> <b.json>     # 只测指定日志
    LIMIT=70 python 测/exit_chain_probe.py ...          # 每份最多重放多少决策点
"""
import glob
import io
import json
import os
import sys
import collections

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

import strategy as S           # noqa: E402
import game_state as G         # noqa: E402
import opponent as O           # noqa: E402
import match_ctx as M          # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

LIMIT = int(os.environ.get("LIMIT", "60"))
SEAT = int(os.environ.get("SEAT", "0"))

# 出口链顺序（与 _decide_impl 尾部一致）
CHAIN = ["_lock_win_tail_guard", "_bet_cap_guard", "_aggressive_strong_bet",
         "_bluff_cap_guard", "_stability_guard", "_normalize",
         "_endgame_arbitrate", "_big_money_guard", "_cheap_call_guard",
         "_doom_call_upgrade"]
# 入口短路（不经出口链，直接 return _normalize(...)）
ENTRY = ["_lock_win_unified", "_gamble_plan", "_profit_lock_allin"]


def _norm(a):
    """把动作 dict 归一成可比较的元组。"""
    if a is None:
        return None
    if not isinstance(a, dict):
        return ("?", str(a))
    return (str(a.get("act")), int(a.get("num") or 0), bool(a.get("lk")))


def _find_action(args):
    """从调用参数里找出动作 dict（各层签名不同）。"""
    for a in args:
        if isinstance(a, dict) and "act" in a:
            return a
    return None


_TRACE = []          # 当前决策点的层轨迹 [(层名, before_tuple, after_tuple)]
_CALLS = {}          # 每层被调用次数
_FINAL = [None]      # 决策层输出（出口链第一个输入）


def install():
    for name in CHAIN:
        orig = getattr(S, name, None)
        if orig is None:
            print("⚠️ 找不到层函数:", name)
            continue

        def make(nm, fn):
            def wrapper(*args, **kw):
                before = _find_action(args)
                out = fn(*args, **kw)
                after = _find_action((out,))
                _TRACE.append((nm, _norm(before), _norm(after)))
                _CALLS[nm] = _CALLS.get(nm, 0) + 1
                return out
            wrapper.__name__ = nm
            return wrapper
        setattr(S, name, make(name, orig))
    # 入口短路也要探针化（否则它们的决策点只有一次 _normalize 调用，
    # 会被误当成"出口链只跑了 1 层"）
    for name in ENTRY:
        orig = getattr(S, name, None)
        if orig is None:
            continue

        def make_e(nm, fn):
            def wrapper(*args, **kw):
                out = fn(*args, **kw)
                # 只有**返回动作 dict** 的才是真短路（`_profit_lock_allin`
                # 返回 bool，只是 `_lock_win_unified` 的一个判据，不是短路）
                if isinstance(out, dict) and "act" in out:
                    _TRACE.append(("入口短路:" + nm, None, _norm(out)))
                    _CALLS["入口:" + nm] = _CALLS.get("入口:" + nm, 0) + 1
                return out
            wrapper.__name__ = nm
            return wrapper
        setattr(S, name, make_e(name, orig))


def replay(path):
    """重放一份日志，返回每个决策点的 (trace, final_action)。"""
    m = O.OpponentModel()
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    reqs = load_botbattle(path, my_seat=SEAT)
    out = []
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
        _TRACE.clear()
        try:
            fin = S.decide(st, m, ctx, debug=False)
            ok = True
        except Exception as e:
            fin = "ERR:" + repr(e)
            ok = False
        out.append((meta.get("hand"), st.stage, len(st.board), list(_TRACE),
                    _norm(fin), ok))
    return out


def main():
    # 只在作为 CLI 运行时替换 stdout（放在 main 里，模块可被 import 复用）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True,
                                  write_through=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--seat="):
            SEAT = int(a.split("=", 1)[1])
    if args:
        logs = args
    else:
        logs = sorted(set(
            glob.glob(os.path.join(BASE, "内容", "记录", "*botbattle*log.json"))
            + glob.glob("C:/Users/HP/Downloads/botbattle*log.json")))

    install()
    print("出口链: %s" % " → ".join(CHAIN))
    print("共 %d 份日志，每份最多 %d 个决策点\n" % (len(logs), LIMIT))

    flip = collections.Counter()      # 每层翻转次数
    flip_when = collections.Counter()  # 每层翻转发生在哪个街
    pair = collections.Counter()      # 打架对 (i, j)
    ENTRY_N = collections.Counter()   # 入口短路按规则计数
    entry_act = collections.Counter()  # 入口短路的最终动作
    n_dec = 0
    n_entry = 0                       # 入口短路
    n_net = 0                         # 净翻转（最终 != 决策层输出）
    n_multi = 0                       # 被改写了 ≥2 次的决策点
    net_examples = []
    fight_examples = []

    for path in logs:
        try:
            recs = replay(path)
        except Exception as e:
            print("%-52s ✗ 跳过（%r）" % (os.path.basename(path)[:52], e))
            continue
        if not recs:
            continue
        f_this = 0
        for hand, stage, nb, trace, fin, ok in recs:
            n_dec += 1
            if not trace:
                n_entry += 1
                continue
            entry = [t for t in trace if t[0].startswith("入口短路:")]
            if entry:
                n_entry += 1
                ENTRY_N[entry[0][0]] += 1
                entry_act[entry[0][2]] += 1
                continue          # 短路时决策层没跑，"净翻转"无意义
            # 决策层输出 = 出口链第一层的输入
            d0 = trace[0][1]
            flips = []
            for i, (nm, b, a) in enumerate(trace):
                if nm.startswith("入口短路:"):
                    continue
                if a is not None and b is not None and a != b:
                    flip[nm] += 1
                    flip_when[(nm, stage)] += 1
                    flips.append((i, nm, b, a))
                    f_this += 1
            if len(flips) >= 2:
                n_multi += 1
            if d0 is not None and fin is not None and d0 != fin:
                n_net += 1
                if len(net_examples) < 12:
                    net_examples.append((os.path.basename(path)[:22], hand, stage,
                                         d0, fin,
                                         " > ".join("%s:%s" % (t[1], t[3][0])
                                                    for t in flips)))
            # 打架：把之前某次改动的结果改回去
            for x in range(len(flips)):
                for y in range(x + 1, len(flips)):
                    i, ni, b1, a1 = flips[x]
                    j, nj, b2, a2 = flips[y]
                    if a1 == b2 and a2 == b1 and b1 != a1:
                        pair[(ni, nj)] += 1
                        if len(fight_examples) < 12:
                            fight_examples.append(
                                (os.path.basename(path)[:22], hand, stage,
                                 ni, nj, b1, a1))
        print("%-52s 决策点 %3d  翻转 %3d  均 %.2f 层/点"
              % (os.path.basename(path)[:52], len(recs), f_this,
                 f_this / max(1, len(recs))))

    print()
    print("=" * 84)
    print("=== ① 各层「被调用」与「翻转」次数（决策点总数 %d）===" % n_dec)
    tot = sum(flip.values())
    print("  %-24s %8s %8s %8s" % ("层", "被调用", "翻转", "占比"))
    for nm in CHAIN:
        v = flip.get(nm, 0)
        c = _CALLS.get(nm, 0)
        bar = "#" * int(round(v / max(1, tot) * 40)) if tot else ""
        print("  %-24s %8d %8d %7.1f%%  %s" % (nm, c, v, v / max(1, tot) * 100, bar))
    print("  %-24s %8s %8d" % ("合计", "", tot))
    print()
    print("=== ①b 入口短路（规则2/18，不经出口链）===")
    print("  短路决策点数: %d / %d（%.1f%%）" % (n_entry, n_dec, n_entry / max(1, n_dec) * 100))
    for k, v in ENTRY_N.most_common():
        print("    %-30s %4d" % (k, v))
    for k, v in entry_act.most_common(6):
        print("    最终动作 %-22s %4d" % (str(k), v))
    print()
    print("=== ② 翻转发生在哪些街 ===")
    stages = ["preflop", "flop", "turn", "river"]
    print("  %-24s %s" % ("层", "".join("%9s" % s for s in stages)))
    for nm in CHAIN:
        row = [flip_when.get((nm, s), 0) for s in stages]
        if sum(row):
            print("  %-24s %s" % (nm, "".join("%9d" % v for v in row)))
    print()
    print("=== ③ 层间「打架」（A 改成 B，后面某层又把 B 改回 A）===")
    tot_fight = sum(pair.values())
    print("  打架事件合计: %d" % tot_fight)
    for (ni, nj), v in pair.most_common(15):
        print("    %-24s → %-24s %4d 次" % (ni, nj, v))
    print()
    print("=== ④ 净翻转（最终动作 != 决策层输出）===")
    print("  %d / %d 个决策点（%.1f%%）被出口链改变了最终动作"
          % (n_net, n_dec, n_net / max(1, n_dec) * 100))
    print("  被改写 ≥2 次的决策点: %d / %d（%.1f%%）"
          % (n_multi, n_dec, n_multi / max(1, n_dec) * 100))
    print()
    if net_examples:
        print("=== ⑤ 净翻转样例（决策层 → 最终；中间链条）===")
        for f, h, sg, d0, fin, chain in net_examples:
            print("  %-22s 手%-3s %-8s %s → %s" % (f, h, sg, d0, fin))
            print("        %s" % chain)
    if fight_examples:
        print()
        print("=== ⑥ 打架样例 ===")
        for f, h, sg, ni, nj, b1, a1 in fight_examples:
            print("  %-22s 手%-3s %-8s %s: %s→%s   随后 %s 又改回 %s"
                  % (f, h, sg, ni, b1, a1, nj, b1))


if __name__ == "__main__":
    main()
