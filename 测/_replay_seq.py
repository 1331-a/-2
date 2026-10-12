# -*- coding: utf-8 -*-
"""★ 按时间顺序连着重放多份日志（共用一个 model + ctx），复现「跨对局延续」。

依据：bot.py 把整个 OpponentModel 序列化进平台的 data/globaldata，而该字段在
**同一选手的所有对局之间持续存在** ⇒ 线上 bot 每局是「热启动」的，模型带着
上一局（甚至好几个对手）的学习数据；而所有本地探针都是「每局全新模型」。

用法:
    python 测/_replay_seq.py <log1> <log2> ... [--warm N]
  · 日志按文件名时间排序（调用方保证顺序）
  · 每份日志结束后打印它与「该局日志实际动作」的不一致率
  · --warm N ：额外先把模型 hands_seen 预置为 N（模拟更早的历史）
"""
import json
import os
import sys
import time

sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import bot as B               # noqa: E402
import strategy as S          # noqa: E402
import game_state as G        # noqa: E402
import opponent as O          # noqa: E402
import match_ctx as M         # noqa: E402
from botbattle_log import load_botbattle   # noqa: E402

_ACT2RESP = {"fold": -1, "call": 0, "check": 0, "allin": -2}


def log_resp(raw):
    p = str(raw or "").split()
    if not p:
        return None
    if p[0] in _ACT2RESP:
        return _ACT2RESP[p[0]]
    if p[0] in ("raise", "bet") and len(p) > 1:
        try:
            return int(p[1])
        except ValueError:
            return None
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    warm = 0
    for a in sys.argv[1:]:
        if a.startswith("--warm"):
            warm = int(a.split("=")[-1]) if "=" in a else 0
    model = O.OpponentModel()
    if warm:
        model.hands_seen = warm
        print("[预置 hands_seen = %d]" % warm)
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    print("%-34s %6s %6s %8s %8s" % ("日志", "决策点", "动作不一致", "resp不一致", "hands_seen"))
    for path in args:
        o = json.load(open(path, encoding="utf-8"))
        m0 = o["match"]
        seat = 0
        for i, k in ((0, "bot_a"), (1, "bot_b")):
            if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
                seat = i
        n = a_mis = r_mis = 0
        gdata = model.to_json()
        for req, meta in load_botbattle(path, my_seat=seat):
            st = G.parse_request(req)
            S._DECISION_STARTED_WALL = time.time()
            # 完全复刻 bot.py 的活路径
            model = O.OpponentModel.from_json(gdata)
            O.build_model_from_history(model, req, st)
            ctx = M.MatchContext.from_dict(model.ctx_dict)
            try:
                ctx.update(st)
            except Exception:
                pass
            try:
                ctx.sync_baseline(st)
            except Exception:
                pass
            act = S.decide(st, model, ctx, debug=False)
            resp = B._final_guard(st, B._to_response(act))
            model.ctx_dict = ctx.to_dict()
            gdata = model.to_json()

            want = log_resp(meta.get("actual"))
            n += 1
            if want is not None:
                if resp != want:
                    r_mis += 1
                if str(act.get("act")) != str(meta.get("actual", "")).split()[0]:
                    a_mis += 1
        print("%-34s %6d %6d(%5.1f%%) %6d(%5.1f%%) %8d" % (
            os.path.basename(path)[18:34], n, a_mis, 100.0 * a_mis / max(1, n),
            r_mis, 100.0 * r_mis / max(1, n), getattr(model, "hands_seen", -1)))


if __name__ == "__main__":
    main()
