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


def _load_requests(path):
    """从 JSON 文件提取 request 列表（兼容 botzone 包装 / 单个 / 裸）。"""
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
    return out


def main():
    ap = argparse.ArgumentParser(description="决策日志查看工具")
    ap.add_argument("payload", nargs="?", help="request JSON 文件（省略则用 --demo）")
    ap.add_argument("--demo", action="store_true", help="跑内置演示")
    ap.add_argument("--hand", nargs="*", type=int, help="只看这些手数")
    ap.add_argument("--json", dest="json_out", help="日志落盘路径")
    args = ap.parse_args()

    if args.demo or not args.payload:
        requests = DEMO_REQUESTS
        print("（演示模式：3 个典型场景）", file=sys.stderr)
    else:
        requests = _load_requests(args.payload)
    if not requests:
        print("没有可用的 request", file=sys.stderr)
        return 1

    DecisionLogger.enable(True)     # 打开日志
    print("=" * 72)
    print("决策日志（rule=命中规则, action=最终动作, detail=牌型/赛制档/注额）")
    print("=" * 72)

    for req in requests:
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
            print("→ 第%d手 %s 底池=%d 动作=%s" %
                  (state.hand_num, state.stage, state.pot, action))
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
