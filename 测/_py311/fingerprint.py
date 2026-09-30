# -*- coding: utf-8 -*-
"""用「行为指纹」判定日志里哪个座位是哪个版本。

方法：把同一批真实决策点分别喂给 v50 和当前版，统计各自与日志实际动作的
一致率。一致率高的那个版本，就是该座位实际运行的版本。

为什么需要：BotBattle 日志里双方 display_name / id / name 可能完全相同
（同一账号上传两份 ELF），无法从元数据判断座位归属 —— 只能靠行为指纹。

用法：  python fingerprint.py <log.json>
"""
import io
import json
import marshal
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

# ---- 加载 v50（Python 3.11 字节码）----
with open(os.path.join(BASE, "测", "_v50_body.bin"), "rb") as f:
    V50 = {"__name__": "v50mod", "__file__": "poker_bot.py"}
    exec(marshal.loads(f.read()), V50)

import strategy as NOW          # noqa: E402
import game_state as G          # noqa: E402
import opponent as O            # noqa: E402
import match_ctx as M           # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

# 播种，降低 MC 噪声对判定的干扰
try:
    import equity as EQ
    EQ._rng.seed(20260930)
except Exception:
    pass


def act_type(a):
    """把 decide 的返回值归一到动作类型。"""
    if a is None:
        return "none"
    if isinstance(a, dict):
        t = str(a.get("act", "")).lower()
    else:
        t = {**{-1: "fold", -2: "allin", 0: "check"}}.get(a, "raise")
    if t in ("allin", "all_in", "shove"):
        return "allin"
    if t in ("raise", "bet"):
        return "raise"
    return t


def actual_type(s):
    return str(s).split()[0].lower() if s else ""


def run_seat(path, seat, model_v50_cls, parse_v50, decide_v50,
             NowS, G, O, M, verbose=False):
    """返回 (一致数, 总数) 对每个版本。"""
    reqs = load_botbattle(path, my_seat=seat)
    if not reqs:
        return None

    m50 = model_v50_cls()
    mnow = O.OpponentModel()
    cnow = M.MatchContext.from_dict(mnow.ctx_dict)

    tally = {"v50": [0, 0], "now": [0, 0]}
    rows = []

    for req, meta in reqs:
        hist = req.get("history") or []
        # ---- v50 ----
        try:
            st50 = parse_v50(req)
            a50 = decide_v50(st50, m50, None)
            t50 = act_type(a50)
        except Exception as e:
            t50 = "err:%s" % type(e).__name__
        # ---- 当前版 ----
        try:
            stnow = G.parse_request(req)
            try:
                O.build_model_from_history(mnow, req, stnow)
            except Exception:
                pass
            try:
                cnow.update(stnow)
            except Exception:
                pass
            anow = NowS.decide(stnow, mnow, cnow, debug=False)
            tnow = act_type(anow)
        except Exception as e:
            tnow = "err:%s" % type(e).__name__

        real = actual_type(meta.get("actual"))
        for tag, t in (("v50", t50), ("now", tnow)):
            tally[tag][1] += 1
            if t == real or (real == "call" and t == "check"):
                tally[tag][0] += 1
        rows.append((meta.get("hand"), meta.get("street"), meta.get("hole"),
                     meta.get("actual"), t50, tnow))

    if verbose:
        print("  手  街      底牌        实际            v50预测        当前版预测")
        for r in rows[:40]:
            mark = lambda t, real: ("=" if (t == real or (real == "call" and t == "check")) else " ")
            print("  %-4s %-8s %-10s %-14s %s%-13s %s%-13s"
                  % (r[0], r[1], "/".join(map(str, r[2] or [])), r[3],
                     mark(r[4], r[3]), r[4], mark(r[5], r[3]), r[5]))
    return tally, rows


def main():
    path = sys.argv[1]
    print("日志:", os.path.basename(path))
    print("=" * 78)
    summary = {}
    for seat in (0, 1):
        print("\n### 座位 %d" % seat)
        res = run_seat(path, seat,
                       V50["OpponentModel"], V50["parse_request"], V50["decide"],
                       NOW, G, O, M, verbose=True)
        if res is None:
            print("  (无决策点)")
            continue
        tally, rows = res
        summary[seat] = tally
        for tag, label in (("v50", "v50"), ("now", "当前版")):
            ok, tot = tally[tag]
            print("  → %-6s 一致 %3d / %3d  =  %5.1f%%" % (label, ok, tot, 100.0 * ok / max(tot, 1)))

    print("\n" + "=" * 78)
    print("判定：对每个座位，取一致率更高的版本为其实际运行版本")
    for seat in sorted(summary):
        t = summary[seat]
        r50 = t["v50"][0] / max(t["v50"][1], 1)
        rnow = t["now"][0] / max(t["now"][1], 1)
        who = "v50" if r50 > rnow else "当前版"
        print("  座位 %d → %-6s   (v50 %.1f%% vs 当前版 %.1f%%, 差 %.1f 个百分点)"
              % (seat, who, r50 * 100, rnow * 100, abs(r50 - rnow) * 100))


if __name__ == "__main__":
    main()
