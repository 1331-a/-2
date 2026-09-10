# -*- coding: utf-8 -*-
"""view_log.py — 决策日志查看工具（本地）

三种用法：
  1) 看内置演示（无需任何输入，直接跑）：
       python view_log.py --demo
  2) 重放一个 botzone 对局（把对局详情里的 request 存成 JSON 文件）：
       python view_log.py payload.json
     支持的 JSON 格式：
       a) {"requests": ["{...}", ...]}            # botzone 完整包装
       b) {"request": {...}}                       # 单个 request
       c) {...}                                    # 裸 request（含 my_cards/history）
  3) 只看某几手（配合 --hand 过滤）：
       python view_log.py payload.json --hand 12 15 30
  4) payload 自检（确认 id 基准/字段完整性，换新对局后先跑这个）：
       python view_log.py payload.json --check
  5) **BotBattle 对局日志**（记录/botbattle-*.json，事件流格式，自动识别）：
       python view_log.py botbattle-holdem-20260910200423-052a67b5-log.json
       python view_log.py <日志名> --seat 0        # 指定我方座位（默认 0）
       python view_log.py <日志名> --hand 61       # 只看第 61 手
     文件名可只写名字，工具会在 ./记录/ 等目录自动查找。

输出：每行 [DECISION] JSON —— hand(手数) / street(街) / pot(底池) /
      rule(命中的规则) / action(动作) / detail(牌型+赛制档+注额)
也可加 --json out.json 把日志落盘便于统计。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state import parse_request          # noqa: E402
from strategy import decide, DecisionLogger   # noqa: E402
from opponent import OpponentModel            # noqa: E402
from match_ctx import MatchContext            # noqa: E402


DEMO_REQUESTS = [
    # 翻前：无历史（会被 _preflop_decide 处理）
    {"num_players": 2, "dealer_id": 0, "my_id": 0, "my_chips": 19900,
     "my_cards": [48, 51], "public_cards": [], "history": [],
     "hand": 1, "max_hand": 70,
     "total_win_chips": [0, 0], "total_win_games": [0, 0]},
    # 翻牌：对手过牌（触发规则12）
    {"num_players": 2, "dealer_id": 1, "my_id": 0, "my_chips": 19500,
     "my_cards": [40, 43], "public_cards": [8, 16, 24],
     "history": [{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 1, "player_id": 1, "action": 0, "action_type": "check"}],
     "hand": 12, "max_hand": 70,
     "total_win_chips": [300, -300], "total_win_games": [0, 0]},
    # 河牌：公面 4 张同花 + 对手大注（触发规则11 弃牌）
    {"num_players": 2, "dealer_id": 0, "my_id": 1, "my_chips": 18000,
     "my_cards": [34, 17], "public_cards": [13, 49, 29, 33, 8],
     "history": [{"round": 0, "player_id": 0, "action": 500, "action_type": "raise"},
                 {"round": 0, "player_id": 1, "action": 0, "action_type": "call"},
                 {"round": 3, "player_id": 1, "action": 500, "action_type": "raise"},
                 {"round": 3, "player_id": 0, "action": 9000, "action_type": "raise"}],
     "hand": 50, "max_hand": 70,
     "total_win_chips": [200, -200], "total_win_games": [0, 0]},
]


def _resolve_path(name):
    """路径解析：支持只写文件名（自动在 ./ 和 ./记录/ 等目录查找）。"""
    import glob
    if os.path.isfile(name):
        return name
    cands = [name]
    for d in ("记录", "logs", ".", os.path.join("内容", "记录")):
        cands.append(os.path.join(d, name))
    cands.append(name)                    # 再按原样试一次
    for c in cands:
        if os.path.isfile(c):
            return c
    hits = glob.glob(os.path.join("**", name), recursive=True)
    if hits:
        return hits[0]
    return None


def _load_requests(path, seat=0, hand=None):
    """从 JSON 文件提取 request 列表。

    支持三种格式：
      A) BotBattle 事件流（format == "botbattle.match.log"）——自动转换
      B) botzone 包装 {"requests":[...]} / {"request":{...}}
      C) 裸 request
    返回 (requests, metas)；metas 为 BotBattle 的辅助信息（可为等长 None 列表）。
    """
    # A) BotBattle 事件流
    try:
        from botbattle_log import load_botbattle
        bb = load_botbattle(path, my_seat=seat, use_hand=hand)
        if bb:
            reqs = [r for r, _m in bb]
            metas = [m for _r, m in bb]
            return reqs, metas
    except Exception:
        pass

    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    out = []
    if isinstance(obj, dict) and "requests" in obj:
        for r in obj["requests"]:
            out.append(json.loads(r) if isinstance(r, str) else r)
    elif isinstance(obj, dict) and "request" in obj:
        r = obj["request"]
        out.append(json.loads(r) if isinstance(r, str) else r)
    elif isinstance(obj, dict):
        out.append(obj)
    elif isinstance(obj, list):
        out.extend(obj)
    return out, [None] * len(out)


def main():
    ap = argparse.ArgumentParser(description="决策日志查看工具")
    ap.add_argument("payload", nargs="?", help="request JSON 文件（省略则用 --demo）")
    ap.add_argument("--demo", action="store_true", help="跑内置演示")
    ap.add_argument("--hand", nargs="*", type=int, help="只看这些手数")
    ap.add_argument("--json", dest="json_out", help="日志落盘路径")
    ap.add_argument("--check", action="store_true",
                    help="只做 payload 自检（id 基准/字段完整性），不跑决策")
    ap.add_argument("--seat", type=int, default=0,
                    help="BotBattle 日志：我方座位号（0/1，默认 0）")
    args = ap.parse_args()

    metas = [None] * len(DEMO_REQUESTS)
    if args.demo or not args.payload:
        requests = DEMO_REQUESTS
        print("（演示模式：3 个典型场景）", file=sys.stderr)
    else:
        path = _resolve_path(args.payload)
        if path is None:
            print("找不到文件：%s" % args.payload, file=sys.stderr)
            print("提示：可只写文件名，工具会在 ./记录/ 等目录自动查找；"
                  "或写完整路径。", file=sys.stderr)
            return 1
        if path != args.payload:
            print("（已定位到 %s）" % path, file=sys.stderr)
        requests, metas = _load_requests(path, seat=args.seat, hand=None)
        if not requests:
            print("没有解析到决策点。若是 BotBattle 日志，请用 --seat 0/1 指定"
                  "我方座位；或检查文件格式。", file=sys.stderr)
            return 1

    if args.check:
        print("=" * 72)
        print("payload 自检（确认识别到的字段与 id 基准）")
        print("=" * 72)
        for i, req in enumerate(requests):
            try:
                st = parse_request(req)
                lead = (st.total_win_chips[st.my_id]
                        - st.total_win_chips[st.opp_id])
                print("第%d个: hand=%s my_id=%s dealer_id=%s id_base=%s(%s) "
                      "my_chips=%s lead=%s max_hand=%s" % (
                          i + 1, st.hand_num, st.my_id, st.dealer_id,
                          st.id_base, "1-based已归一化" if st.id_base else "0-based",
                          st.my_chips, lead, st.max_hand))
                if st.id_base:
                    print("   ⚠ 检测到 1-based id，已自动 -1 归一化（回放显示座位1/2 时正常）")
                if not st.total_win_chips:
                    print("   ⚠ total_win_chips 缺失")
                if not st.my_cards:
                    print("   ⚠ my_cards 缺失（翻前也没有牌？）")
            except Exception as e:
                print("第%d个: 解析失败 %s" % (i + 1, e))
        return 0

    DecisionLogger.enable(True)     # 打开日志
    print("=" * 72)
    print("决策日志（rule=命中规则, action=最终动作, detail=牌型/赛制档/注额）")
    print("=" * 72)

    for i, req in enumerate(requests):
        try:
            state = parse_request(req)
            if args.hand and state.hand_num not in args.hand:
                continue
            model = OpponentModel()
            ctx = MatchContext.from_dict(model.ctx_dict)
            try:
                ctx.update(state)
                ctx.sync_baseline(state)
            except Exception:
                pass
            action = decide(state, model, ctx, debug=True)
            _m = metas[i] if (metas and i < len(metas) and metas[i]) else {}
            print("→ 第%d手 %s 底池=%d 动作=%s%s" %
                  (state.hand_num, state.stage, state.pot, action,
                   ("  [日志: 街=%s 座位=%s chips=%s]" % (
                       _m.get("street"), _m.get("dealer"), _m.get("chips")))
                   if _m else ""))
        except Exception as e:
            print("!! 第%s手处理失败: %s" % (req.get("hand"), e))

    print("=" * 72)
    recs = DecisionLogger.records()
    print("共 %d 条日志" % len(recs))
    if args.json_out:
        ok = DecisionLogger.dump(args.json_out)
        print("已写入 %s: %s" % (args.json_out, ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
