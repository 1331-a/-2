# -*- coding: utf-8 -*-
"""audit_lock.py — 锁赢/防锁赢 全量审计工具

用法：
    python audit_lock.py <对局日志.json> [--seat 0]

作用：把整局重放一遍，对每个决策点核算锁赢公式并检查实际决策是否自洽。
输出：
    ① 锁赢点清单（lead / 门槛 / 决策）—— 判定锁赢但没 fold 的会标 ⚠
    ② 可疑决策（免费却弃牌 / 极小注弃牌 / 领先 allin）—— 附判定依据
    ③ 汇总统计

公式回顾（HU 70 手、盲注 50/100、total_win_chips 零和）：
    lead        = twc[我] - twc[对手]          （= 单边显示值 × 2）
    锁赢门槛     = 2 × (_blind_line(剩余手数, own=True) + 本局已投)
    锁赢        ⇔ lead > 门槛               → 应 fold（全程弃牌也赢）
    防锁赢(doom) ⇔ lead - 2×已投 ≤ -2×_blind_line(剩余手数, own=False)
                                          → 应 allin（弃牌即把锁定输掉）
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request, INIT_CHIPS          # noqa: E402
from strategy import (_fold_out_active, _blind_line, _match_adjust,   # noqa: E402
                      decide)
from opponent import OpponentModel                        # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="锁赢/防锁赢审计")
    ap.add_argument("payload", help="对局日志 JSON（botzone 或 BotBattle）")
    ap.add_argument("--seat", type=int, default=0, help="BotBattle: 我方座位")
    args = ap.parse_args()

    for cand in (args.payload, os.path.join("记录", args.payload)):
        if os.path.isfile(cand):
            path = cand
            break
    else:
        print("找不到文件：%s" % args.payload)
        return 1

    from view_log import _load_requests
    reqs, metas = _load_requests(path, seat=args.seat, hand=None)
    if not reqs:
        print("未解析到决策点（BotBattle 日志请确认 --seat）")
        return 1

    lock_pts, lock_bad, odd = [], [], []
    for i, req in enumerate(reqs):
        st = parse_request(req)
        hl = st.max_hand - st.hand_num
        lead = st.total_win_chips[st.my_id] - st.total_win_chips[st.opp_id]
        inv = INIT_CHIPS - st.my_chips
        bl = _blind_line(st, hl, own=True)
        thr = 2 * (bl + inv)
        is_lock = _fold_out_active(st)
        act = decide(st, OpponentModel()).get("act")
        m = metas[i] if (metas and i < len(metas) and metas[i]) else {}
        tag = "第%s手/%s" % (st.hand_num, st.stage)

        if is_lock:
            lock_pts.append((tag, lead, thr, act))
            if act != "fold":
                lock_bad.append((tag, lead, thr, act))

        # 可疑：免费却弃牌 / 极小注(<1BB)弃牌且非锁赢
        if act == "fold" and st.to_call <= 0:
            odd.append(("免费却弃牌", tag, st.to_call, lead, is_lock))
        if act == "fold" and 0 < st.to_call < 100 and not is_lock:
            odd.append(("极小注弃牌", tag, st.to_call, lead, is_lock))
        # 领先 allin：需有 doom/foldout 依据才合理
        if act == "allin" and lead > 0:
            adj = _match_adjust(st)
            _ok = (adj == "doomed") or is_lock
            odd.append(("领先allin%s" % ("(防锁赢OK)" if _ok else "(⚠无依据)"),
                        tag, st.to_call, lead, is_lock))

    print("=" * 74)
    print("决策点总数: %d" % len(reqs))
    print("-" * 74)
    print("【锁赢点】共 %d 个（判定锁赢 → 应 fold）" % len(lock_pts))
    for t, lead, thr, act in lock_pts:
        flag = "✓" if act == "fold" else "⚠ 未弃牌"
        print("  %s lead=%d > 门槛=%d → 决策=%s %s" % (t, lead, thr, act, flag))
    print("  锁赢判定正确率: %d/%d" % (len(lock_pts) - len(lock_bad), len(lock_pts)))
    print("-" * 74)
    print("【可疑决策】共 %d 条（多为弱牌正常弃 / 防锁赢正确触发）" % len(odd))
    for kind, t, tc, lead, lock in odd:
        print("  %s: %s to_call=%s lead=%d 锁赢=%s" % (kind, t, tc, lead, lock))
    print("=" * 74)
    if lock_bad:
        print("⚠ 发现 %d 个锁赢未弃牌异常！" % len(lock_bad))
        return 2
    print("锁赢判定全部自洽 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
