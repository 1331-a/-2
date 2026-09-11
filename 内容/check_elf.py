# -*- coding: utf-8 -*-
"""ELF 一致性自检 —— 判断「场上跑的那颗 ELF」是否为当前代码。

原理
----
对局日志里记录的是**实际动作**（那颗 ELF 打的）；本工具用**当前代码**逐决策点重放，
两者对比：
  · 一致            → 相同
  · 尺寸不同        → 动作相同、金额不同（当前代码有 ±10~15% 抖动 + 规则12 权重
                      随机，属正常随机化，**不代表版本不同**）
  · 动作不同        → 结构性差异（当前代码不会这么做）
特别地，**锁赢点**（数学上已锁定 / 必须防锁赢）是可判定的硬规则：
  锁赢点实际动作 ≠ fold / allin → 说明那颗 ELF 没执行规则2 → **必是旧版**。

用法
----
    python check_elf.py <对局日志.json> [--seat 0] [--txt] [--hand 19 47]

退出码：0 = 一致；2 = 检测到结构性不一致（疑似旧 ELF）。
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request                      # noqa: E402
from opponent import OpponentModel, build_model_from_history  # noqa: E402
from match_ctx import MatchContext                        # noqa: E402
from strategy import (decide, _fold_out_active, _match_adjust,  # noqa: E402
                      _effective_category, DecisionLogger, BOT_VERSION)


def _load(path, seat):
    """复用 view_log 的加载器（自动识别 BotBattle / botzone 两种格式）。"""
    from view_log import _load_requests, _resolve_path
    p = _resolve_path(path)
    if p is None:
        return None, None, None
    requests, metas = _load_requests(p, seat=seat, hand=None)
    return p, requests, metas


def main():
    ap = argparse.ArgumentParser(description="ELF 一致性自检")
    ap.add_argument("payload", help="对局日志路径（可只写文件名，会自动在 记录/ 下找）")
    ap.add_argument("--seat", type=int, default=0, help="我方座位（默认 0）")
    ap.add_argument("--hand", type=int, nargs="*", default=None,
                    help="只看这几手（定位问题用）")
    ap.add_argument("--hand-offset", type=int, default=0,
                    help="调试：把 request 的 hand 减去 N（验证平台 hand 基准）")
    ap.add_argument("--txt", nargs="?", const="__auto__", default=None,
                    help="导出记事本 .txt 到 记录/日志文本/")
    args = ap.parse_args()

    path, requests, metas = _load(args.payload, args.seat)
    if requests is None:
        print("找不到文件: %s" % args.payload, file=sys.stderr)
        return 1

    DecisionLogger.reset()
    DecisionLogger.enable(True)
    DecisionLogger._quiet = True          # 由本工具渲染

    model = OpponentModel()
    ctx = MatchContext.from_dict(model.ctx_dict)

    total = same = size_diff = act_diff = 0
    lock_total = lock_bad = 0
    bad_rows = []
    odd_rows = []

    for i, req in enumerate(requests):
        if args.hand_offset:
            req = dict(req)
            try:
                req["hand"] = int(req.get("hand", 0)) - args.hand_offset
            except Exception:
                pass
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
        try:
            a = decide(st, model, ctx)
        except Exception:
            continue
        _mt = ((metas[i] or {}) if (metas and i < len(metas)) else {}) or {}
        _dh = _mt.get("hand") or (st.hand_num + 1)      # 显示用 1-based
        actual = _mt.get("actual")
        if not actual:
            continue
        total += 1
        a_act = str(a.get("act"))
        a_num = str(a.get("num") or "")
        parts = str(actual).split()
        h_act = parts[0]
        h_num = parts[1] if len(parts) > 1 else ""

        lock = False
        doom = False
        try:
            lock = bool(_fold_out_active(st))
        except Exception:
            pass
        try:
            doom = (_match_adjust(st) == "doomed")
        except Exception:
            pass

        if h_act == a_act:
            if h_act in ("raise", "allin") and h_num and a_num and h_num != a_num:
                size_diff += 1
                if args.hand and _dh in args.hand:
                    odd_rows.append((_dh, st.stage, actual,
                                     "%s %s" % (a_act, a_num), "尺寸不同(随机化范围内)"))
            else:
                same += 1
        else:
            act_diff += 1
            need = ""
            if lock:
                lock_total += 1
                if h_act != "fold":
                    lock_bad += 1
                    need = "锁赢点应 fold"
            if doom:
                lock_total += 1
                if h_act != "allin":
                    lock_bad += 1
                    need = "防锁赢点应 allin"
            if need or (args.hand and _dh in args.hand):
                bad_rows.append((_dh, st.stage, actual,
                                 "%s %s" % (a_act, a_num), need or "结构性不同"))
        # 锁赢点即使"动作相同"也要计入正确数
        if lock or doom:
            if h_act == a_act:
                lock_total += 1
                if (lock and h_act == "fold") or (doom and h_act == "allin"):
                    pass
                else:
                    lock_bad += 1

    lines = []

    def emit(t=""):
        print(t)
        lines.append(t)

    emit("=" * 72)
    emit("ELF 一致性自检 —— %s" % os.path.basename(path or ""))
    emit("本工具版本: BOT_VERSION=%s | 我方座位: %s" % (BOT_VERSION, args.seat))
    emit("=" * 72)
    emit("决策点总数        : %d" % total)
    emit("动作一致          : %d  (%.0f%%)" % (same, 100.0 * same / max(total, 1)))
    emit("尺寸不同(随机化)  : %d  (%.0f%%)  —— 当前代码含抖动/随机权重，属正常"
         % (size_diff, 100.0 * size_diff / max(total, 1)))
    emit("动作不同(结构性)  : %d  (%.0f%%)" % (act_diff, 100.0 * act_diff / max(total, 1)))
    emit("")
    emit("锁赢/防锁赢点     : %d 个，其中实际动作不符 %d 个" % (lock_total, lock_bad))
    emit("-" * 72)

    if bad_rows:
        emit("【结构性不一致清单】")
        emit("%-6s %-9s %-14s %-14s %s" % ("手", "街", "实际(ELF)", "当前代码", "说明"))
        for h, s, act, exp, why in bad_rows:
            emit("%-6s %-9s %-14s %-14s %s" % (h, s, act, exp, why))
        emit("")

    # ---------------- 判定 ----------------
    if total == 0:
        verdict = "无法判定（日志里没有可对比的决策点）"
        code = 1
    elif lock_bad > 0:
        verdict = ("⚠️  本局 ELF 与当前代码【不一致】：%d 个锁赢/防锁赢点未按规则执行。"
                   "锁赢是确定性硬规则，说明场上那颗 ELF 不是最新版 → 请重新下载并上传。"
                   % lock_bad)
        code = 2
    elif act_diff == 0:
        verdict = "✅ 本局 ELF 与当前代码【一致】（无结构性差异）"
        code = 0
    else:
        verdict = ("❓ 存在 %d 处结构性差异但没有锁赢点出错 —— 可能是版本差异，"
                   "也可能是对手/ctx 状态差异导致的正常分歧，建议人工看上面清单。" % act_diff)
        code = 2

    emit("【判定】")
    emit(verdict)
    emit("")
    emit("提示：ELF 版本自证方式 ——")
    emit("  1) 下载的压缩包名形如 poker_bot-linux-x86-64-<短SHA>，短 SHA 即版本；")
    emit("  2) 机器人 stderr 日志首行会打印 [BOT_VERSION] <短SHA>；")
    emit("  3) 与最新 commit 对比：git log --oneline -1")
    emit("=" * 72)

    # ---------------- 导出记事本 ----------------
    if args.txt is not None:
        out_dir = os.path.join("记录", "日志文本")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            pass
        if args.txt == "__auto__":
            base = os.path.splitext(os.path.basename(path or "log"))[0]
            fname = "%s-ELF自检.txt" % base
        else:
            fname = args.txt
        out_path = fname if os.path.isabs(fname) else os.path.join(out_dir, fname)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("ELF 一致性自检 — %s\n" % path)
                f.write("生成时间: %s\n"
                        % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                f.write("\n".join(lines))
                f.write("\n")
            print("已导出记事本: %s" % out_path)
        except Exception as e:
            print("导出失败: %s" % e)

    return code


if __name__ == "__main__":
    sys.exit(main())
