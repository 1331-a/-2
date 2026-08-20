# -*- coding: utf-8 -*-
"""
bot.py — BotZone 平台交互层（只支持 JSON 交互，每步限时 1 秒）。

BotZone JSON 交互协议：
  输入（stdin，一个 JSON 对象）：
    {"requests": [...], "responses": [...], "data": "...", "globaldata": "..."}
    requests 数组的最后一个元素是本轮的 request（可能是 JSON 字符串或对象）。
  输出（stdout，一个 JSON 对象）：
    {"response": <整数>, "data": "...", "globaldata": "..."}

response 整数语义：
  -1 弃牌(fold)  -2 全押(allin)  0 跟注/过牌(call/check)
  >0 加注（raise-to：加注后本轮我的总下注额）

安全设计：
  - 任何解析/决策异常都有兜底，保证永远输出一个合法 response；
  - _final_guard 在整数层面做最后一道合法性校验。
"""

import json
import sys

from game_state import parse_request
from match_ctx import MatchContext
from opponent import OpponentModel, build_model_from_history
from strategy import decide

_ACT_TO_RESPONSE = {"fold": -1, "allin": -2, "call": 0, "check": 0}


def _to_response(action):
    """把内部动作 dict 转为 response 整数。"""
    act = action.get("act", "fold")
    if act == "raise":
        try:
            num = int(action.get("num", 0))
        except (TypeError, ValueError):
            return -1
        return num if num > 0 else -1
    return _ACT_TO_RESPONSE.get(act, -1)


def _final_guard(state, resp):
    """整数 response 层面的最后一道安全网，绝对保证合法。"""
    try:
        to_call = state.to_call
        my_left = state.my_left

        if resp == -1:
            return -1  # 弃牌永远合法
        if resp == -2:
            if my_left > 0:
                return -2  # 全押合法
            return -1 if to_call > 0 else 0

        # 规则5：本局有人全押 → 只能弃牌(-1)/全押(-2)
        if state.any_allin:
            return -2 if my_left > 0 else -1

        if resp == 0:
            if to_call <= 0:
                return 0          # 过牌，合法
            if my_left > to_call:
                return 0          # 跟注（需严格大于才合法）
            return -2             # 筹码不足完整跟注 → 全押

        # resp > 0：加注（raise-to 语义）
        num = int(resp)
        if num <= 0:
            return -1
        min_r = state.min_raise()
        max_r = state.max_raise()
        if num < min_r:
            num = min_r
        if num >= max_r or num >= my_left:
            return -2             # 加注空间不足 → 全押
        return num
    except Exception:
        return -1


def _fallback_resp(state):
    """决策层异常时的保守动作：能过牌就过牌，能跟就跟，否则弃牌。"""
    try:
        if state.any_allin:
            return -1
        if state.to_call <= 0:
            return 0
        if state.my_left > state.to_call:
            return 0
        return -1
    except Exception:
        return -1


def _extract_request(obj):
    """从 BotZone JSON 交互输入中取出本轮 request dict（可能为 None）。"""
    reqs = obj.get("requests") or []
    for item in reversed(reqs):
        cand = item
        if isinstance(cand, str):
            try:
                cand = json.loads(cand)
            except Exception:
                continue
        if isinstance(cand, dict) and ("my_cards" in cand or "history" in cand):
            return cand
    return None


def _persisted_str(v):
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    try:
        return json.dumps(v)
    except Exception:
        return ""


def _handle_line(obj):
    """处理一行 JSON 输入，返回 (resp, data_out, json_mode)。"""
    json_mode = False
    data_str = gdata_str = ""
    request = None

    if isinstance(obj, dict) and "requests" in obj:
        # BotZone JSON 交互：包装结构
        json_mode = True
        data_str = _persisted_str(obj.get("data"))
        gdata_str = _persisted_str(obj.get("globaldata"))
        request = _extract_request(obj)
    elif isinstance(obj, dict) and ("my_cards" in obj or "history" in obj):
        # 本地调试：裸 request
        request = obj

    resp = 0
    data_out = ""
    try:
        if request is None:
            resp = 0  # 拿不到状态时的最保守输出（非法时裁判仅按弃牌处理）
        else:
            state = parse_request(request)
            try:
                # 对手建模：优先跨手牌的 globaldata，其次 data
                model = OpponentModel.from_json(gdata_str or data_str)
                build_model_from_history(model, request, state)
                # 赛制上下文：从模型容器恢复 → 结算上一手 → 同步激进档
                ctx = MatchContext.from_dict(model.ctx_dict)
                ctx.update(state)
                ctx.sync_baseline(state)
                action = decide(state, model, ctx)
                resp = _to_response(action)
                resp = _final_guard(state, resp)
                model.ctx_dict = ctx.to_dict()
                data_out = model.to_json()
            except Exception:
                resp = _fallback_resp(state)
    except Exception:
        resp = 0
    return resp, data_out, json_mode


def run():
    """
    逐行读取 stdin：平台发一行 request 就回一行 response。

    【修复】原实现用 sys.stdin.read() 等 EOF 才输出；若平台发完 request
    后保持 stdin 打开（常驻模式），bot 会一直阻塞在 read() 上，8 秒内
    无任何输出 → 预检判定「Bot 未响应」。逐行模式两种情形都兼容：
      - 每轮重启：平台关 stdin → EOF → 循环结束，进程自然退出；
      - 常驻模式：继续循环等待下一行 request。
    """
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue  # 非 JSON 输入（如预热握手）直接忽略，避免崩溃
        resp, data_out, json_mode = _handle_line(obj)
        if json_mode:
            out = {"response": resp, "data": data_out, "globaldata": data_out}
            sys.stdout.write(json.dumps(out) + "\n")
        else:
            sys.stdout.write(str(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run()
