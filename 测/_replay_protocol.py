# -*- coding: utf-8 -*-
"""阶段一：可信重放基线（走完整 Bot 协议，比较整数 response）。

与既有 `_divergence.py` 的区别：
  1. **逐请求经过 `bot._handle_line`** —— 包含模型序列化/恢复
     （`data_out` → 下一次的 `globaldata`）、`_final_guard` 合法性检查；
  2. **比较最终整数 response**（含加注金额），不再只比动作类别；
  3. **分离两个口径**：
       · `同版本复现率`：同一版本跑两遍，测随机性（MC / jitter）造成的不可避免差异
       · `历史一致率`：当前版本 vs 日志真实动作（含版本差异）
     两者不再混称「保真度」。

用法:
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/_replay_protocol.py
    WB_MC_ITERS=1500 WB_MC_BUDGET=0.25 python 测/_replay_protocol.py --passes 1   # 跳过复现率
"""
import glob
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
sys.path.insert(0, str(BASE / "测"))
os.environ.setdefault("WB_POKER_DEBUG", "0")

import bot                                    # noqa: E402
from botbattle_log import load_botbattle      # noqa: E402
from _range_condition_audit import match_seat  # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))


def actual_to_resp(s):
    """把日志里的 `actual`（"call 638" / "raise 1000" / "fold"）还原成 response 整数。"""
    parts = str(s).split()
    if not parts:
        return None
    act = parts[0].lower()
    amt = int(parts[1]) if len(parts) > 1 else 0
    if act == "fold":
        return -1
    if act == "allin":
        return -2
    if act in ("call", "check"):
        return 0
    return amt


def cat(r):
    """动作类别：fold / allin / call-check / raise。"""
    if r is None:
        return "?"
    if r == -1:
        return "fold"
    if r == -2:
        return "allin"
    if r == 0:
        return "call"
    return "raise"


def run_pass(path, seat):
    """跑一遍，返回 [(ident, hand, stage, resp, actual_resp)]。"""
    ident = Path(path).name[18:32]
    gdata = ""
    out = []
    try:
        for req, meta in load_botbattle(path, my_seat=seat):
            obj = {"requests": [req], "responses": [], "data": "", "globaldata": gdata}
            resp, data_out, _ = bot._handle_line(obj)
            gdata = data_out or ""
            out.append((ident, meta.get("hand"), meta.get("street"),
                        int(resp), actual_to_resp(meta.get("actual"))))
    except Exception as e:
        print("  [skip] %s %r" % (ident, e))
    return out


def collect(passes=2):
    runs = []
    for k in range(passes):
        rows = []
        for p in PATHS:
            obj = json.loads(Path(p).read_bytes())
            seat = match_seat(obj)
            if seat is None:
                continue
            rows += run_pass(p, seat)
        runs.append(rows)
        print("  pass %d 完成：%d 个决策点" % (k + 1, len(rows)))
    return runs


def pct(a, b):
    return 100.0 * a / max(1, b)


def main():
    passes = 2
    if "--passes" in sys.argv:
        try:
            passes = int(sys.argv[sys.argv.index("--passes") + 1])
        except Exception:
            passes = 1
    print("日志 %d 份（含 ~/Downloads），passes=%d" % (len(PATHS), passes))
    runs = collect(passes)
    base = runs[0]
    n = len(base)

    # ---------- 1) 同版本复现率（随机性下限） ----------
    if len(runs) > 1:
        same_int = sum(1 for a, b in zip(runs[0], runs[1]) if a[3] == b[3])
        same_cat = sum(1 for a, b in zip(runs[0], runs[1])
                       if cat(a[3]) == cat(b[3]))
        print()
        print("【同版本复现率】（同一版本跑两遍，测 MC / jitter 随机性）")
        print("  整数 response 一致：%d/%d = %.1f%%" % (same_int, n, pct(same_int, n)))
        print("  动作类别一致    ：%d/%d = %.1f%%" % (same_cat, n, pct(same_cat, n)))
        print("  ⇒ 这是「历史一致率」的噪声上限：超过它的部分才可能归因于版本差异")

    # ---------- 2) 历史一致率（当前版本 vs 日志） ----------
    print()
    print("【历史一致率】（当前版本 vs 日志真实动作，含跨版本差异）")
    same_int = sum(1 for a in base if a[3] == a[4])
    same_cat = sum(1 for a in base if cat(a[3]) == cat(a[4]))
    print("  整数 response 一致：%d/%d = %.1f%%" % (same_int, n, pct(same_int, n)))
    print("  动作类别一致    ：%d/%d = %.1f%%" % (same_cat, n, pct(same_cat, n)))

    # 分「同类别但金额不同」与「类别不同」
    amt_only = [a for a in base
                if cat(a[3]) == cat(a[4]) and a[3] != a[4]]
    cat_diff = [a for a in base if cat(a[3]) != cat(a[4])]
    print("  其中：同类别但金额不同 %d 点；类别不同 %d 点" % (len(amt_only), len(cat_diff)))

    # ---------- 3) 类别不一致的分布 ----------
    print()
    print("【类别不一致的转移矩阵】（日志 → 当前版本）")
    from collections import Counter
    c = Counter((cat(a[4]), cat(a[3])) for a in cat_diff)
    for (src, dst), k in c.most_common(12):
        print("  %-10s → %-10s %d" % (src, dst, k))

    # ---------- 4) 明细（按金额差排序） ----------
    print()
    print("【类别不一致明细（前 25 条）】")
    for a in cat_diff[:25]:
        print("  %-14s 手%-3s %-7s 日志=%-12s 当前=%-12s"
              % (a[0], a[1], a[2], "%s/%s" % (cat(a[4]), a[4]),
                 "%s/%s" % (cat(a[3]), a[3])))

    # ---------- 5) 落盘 ----------
    outp = BASE / "测" / "_replay_protocol.json"
    payload = {
        "n": n,
        "repro": None,
        "hist_int": same_int,
        "hist_cat": same_cat,
        "rows": [dict(m=a[0], hand=a[1], stage=a[2], cur=a[3], real=a[4])
                 for a in base],
    }
    if len(runs) > 1:
        payload["repro"] = {
            "int": sum(1 for a, b in zip(runs[0], runs[1]) if a[3] == b[3]),
            "cat": sum(1 for a, b in zip(runs[0], runs[1]) if cat(a[3]) == cat(b[3])),
        }
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写入 %s" % outp.name)


if __name__ == "__main__":
    main()
