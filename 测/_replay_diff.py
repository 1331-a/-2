# -*- coding: utf-8 -*-
"""重放一致性检查：逐决策点比较「模型动作」与「日志动作」，统计不一致率。

用法: python 测/_replay_diff.py <log.json>
"""
import collections
import io
import json
import os
import sys
import time

sys.path.insert(0, os.environ.get("WB_STRAT_ROOT")
                or r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402


def main():
    path = sys.argv[1]
    _warm = int(os.environ.get("WB_WARM_HANDS", "0") or 0)
    if _warm:
        print("[热启动：hands_seen 起点 = %d]" % _warm)
    if os.environ.get("WB_NO_SMALL_BET_FUTILE") == "1":
        S._small_bet_futile = lambda st, mm: False
        print("[已关闭 _small_bet_futile（规则19）]")
    _minn = os.environ.get("WB_SMALL_BET_MIN_N")
    if _minn:
        S.SMALL_BET_MIN_N = int(_minn)
        print("[SMALL_BET_MIN_N = %s]" % _minn)
    _off = int(os.environ.get("WB_SEED_OFF", "0") or 0)
    if _off:
        _orig_seed = S._decision_seed
        S._decision_seed = lambda st, _o=_orig_seed, _d=_off: _o(st) + _d
        print("[seed offset = %d]" % _off)
    o = json.load(io.open(path, encoding="utf-8"))
    m0 = o["match"]
    seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            seat = i
    m = O.OpponentModel()
    if _warm:
        m.hands_seen = _warm
    ctx = M.MatchContext.from_dict(m.ctx_dict)
    n = 0
    bad = []
    pair = collections.Counter()
    for req, meta in load_botbattle(path, my_seat=seat):
        st = G.parse_request(req)
        try:
            O.build_model_from_history(m, req, st)
        except Exception:
            pass
        try:
            ctx.update(st)
        except Exception:
            pass
        S._DECISION_STARTED_WALL = time.time()
        a = S.decide(st, m, ctx, debug=False)
        act = str(a.get("act"))
        raw = str(meta.get("actual") or "")
        log_act = raw.split()[0] if raw else "?"
        n += 1
        pair[(log_act, act)] += 1
        if log_act != act:
            bad.append((meta.get("hand"), st.stage, st.to_call, st.pot, raw, "%s%s" % (act, a.get("num") or "")))
    print("决策点总数 =", n, " 不一致 =", len(bad), "（%.1f%%）" % (100.0 * len(bad) / max(1, n)))
    print()
    print("=== 混淆 (日志动作, 模型动作) ===")
    for k, v in pair.most_common(12):
        print("   %-22s %4d" % (str(k), v))
    print()
    print("=== 不一致明细（前 25）===")
    for h, stg, tc, pot, raw, got in bad[:25]:
        print("   手%-3s %-8s tc%-6s pot%-6s 日志=%-14s 模型=%s" % (h, stg, tc, pot, raw, got))


if __name__ == "__main__":
    main()
