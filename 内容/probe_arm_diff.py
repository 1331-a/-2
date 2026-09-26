# -*- coding: utf-8 -*-
"""probe_arm_diff.py — 直接比较各臂在**同一批 seeds** 下的决策轨迹，
回答「该方案到底有没有改变任何决策」（与「结果有没有变」是两件事）。

输入：`WB_DIAG=1 WB_FACE_DEBUG=1 python sim_early.py --decomp <opp> <hands> <n>`
      的 stdout（含 `@@@ARM <label>` 分隔线与 `FACE {...}` 行）。

用法：python probe_arm_diff.py adiff.txt
"""
import json
import sys


def parse(path):
    base, arms = [], []
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("@@@ARM"):
            cur = []
            arms.append((line[len("@@@ARM"):].strip(), cur))
            continue
        if not line.startswith("FACE "):
            continue
        r = json.loads(line[5:])
        rec = (r.get("stage"), r.get("action"), r.get("eq"),
               r.get("eff_req"), r.get("fc"), r.get("implied"))
        (cur if cur is not None else base).append(rec)
    return base, arms


def main():
    base, arms = parse(sys.argv[1])
    print("基线决策点 %d 个；对照臂 %d 个：%s" % (
        len(base), len(arms), [a[0] for a in arms]))
    print("=" * 92)
    for name, recs in arms:
        n = min(len(base), len(recs))
        diff = [k for k in range(n) if base[k][1] != recs[k][1]]
        print("%-30s 前 %d 点：动作不同 %d 个" % (name, n, len(diff)))
        for k in diff[:3]:
            b, a = base[k], recs[k]
            print("    #%-3d %-6s 旧 %-6s(eq %.3f thr %.3f fc %.0f imply %.2f)"
                  " → 新 %-6s(eq %.3f thr %.3f fc %.0f imply %.2f)" % (
                      k, b[0], b[1], b[2], b[3], b[4], b[5],
                      a[1], a[2], a[3], a[4], a[5]))
        if not diff:
            # 即使动作相同，门槛是否被抬高了？
            lifted = sum(1 for k in range(n)
                         if recs[k][4] and (recs[k][4] or 0) > 0
                         and abs(recs[k][3] - base[k][3]) > 1e-6)
            print("    （动作零差异；但门槛被折算抬高的点有 %d 个 → 折算生效"
                  "却不够翻盘）" % lifted)


if __name__ == "__main__":
    main()
