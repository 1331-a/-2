# -*- coding: utf-8 -*-
"""test_e2e.py — 端到端多回合测试：直接调用 bot.run()，模拟平台多轮交互。"""
import io
import json
import sys
import time

sys.path.insert(0, ".")

import bot  # noqa: E402


def run_turn(stdin_text):
    """喂一段 stdin，捕获 stdout，返回解析后的输出 dict。"""
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(stdin_text)
    sys.stdout = io.StringIO()
    try:
        bot.run()
        out = sys.stdout.getvalue().strip()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return json.loads(out) if out else None


def wrap(request, globaldata=""):
    return json.dumps({"requests": [json.dumps(request)],
                       "responses": [], "data": "", "globaldata": globaldata})


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 1, "my_chips": 19800,
            "my_cards": [48, 51], "public_cards": [], "history": [],
            "hand": 0, "max_hand": 50, "total_win_chips": [0, 0],
            "total_win_games": [0, 0]}
    base.update(kw)
    return base


fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print("[%s] %s -> %s (期望 %s)" % ("PASS" if ok else "FAIL", name, got, want))


# ---- 回合1：BB AA 面对加注 400，应 3-bet（2026-08-24 新规：翻前投入≤1000）----
r1 = req(history=[{"round": 0, "player_id": 0, "action": 400, "action_type": "raise"}])
o1 = run_turn(wrap(r1))
check("回合1 response", o1["response"], 1000)
gd = o1["globaldata"]
m = json.loads(gd)
check("回合1 对手翻前加注计数", m["preflop_raise"], 1)

# ---- 回合2：同一手牌，对手 call 后翻牌 check，回传 globaldata，不应重复计数 ----
r2 = req(my_chips=18200, public_cards=[46, 6, 1], history=[
    {"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 1000, "action_type": "raise"},
    {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
])
o2 = run_turn(wrap(r2, gd))
m2 = json.loads(o2["globaldata"])
check("回合2 不重复计数 preflop_raise", m2["preflop_raise"], 1)
check("回合2 新增 preflop_call", m2["preflop_call"], 1)
check("回合2 新增 postflop_check", m2["postflop_check"], 1)
# 我方 AA 翻牌顶SET/顶对，可自由下注（response>0 或 0 都行，检查合法性）
resp2 = o2["response"]
ok2 = resp2 == 0 or (isinstance(resp2, int) and resp2 >= 200)
check("回合2 动作合法性(过牌或>=200下注)", ok2, True)

# ---- 回合3：新手牌 hand=1，计数器应清零并重新统计 ----
r3 = req(hand=1, my_chips=19800, my_cards=[23, 2],
         history=[{"round": 0, "player_id": 0, "action": 0, "action_type": "call"}])
o3 = run_turn(wrap(r3, o2["globaldata"]))
m3 = json.loads(o3["globaldata"])
check("回合3 新手牌重新计数(preflop_call总2)", m3["preflop_call"], 2)
check("回合3 72o 过牌选项 response", o3["response"], 0)

# ---- 损坏输入：不合法 JSON 字符串的 request 元素 ----
o4 = run_turn('{"requests":["not-a-json"],"responses":[],"data":"","globaldata":""}')
check("损坏输入兜底 response=0", o4["response"], 0)

# ---- 空 requests ----
o5 = run_turn('{"requests":[],"responses":[],"data":"","globaldata":""}')
check("空 requests 兜底 response=0", o5["response"], 0)

# ---- 计时：最重场景（翻牌后需蒙特卡洛）----
worst = req(my_chips=18200, public_cards=[46, 6, 1], history=[
    {"round": 0, "player_id": 0, "action": 400, "action_type": "raise"},
    {"round": 0, "player_id": 1, "action": 1000, "action_type": "raise"},
    {"round": 0, "player_id": 0, "action": 0, "action_type": "call"},
    {"round": 1, "player_id": 0, "action": 0, "action_type": "check"},
])
t0 = time.time()
for _ in range(20):
    run_turn(wrap(worst))
dt = (time.time() - t0) / 20
check("平均单步耗时<0.5s", dt < 0.5, True)
print("实际平均耗时: %.0f ms" % (dt * 1000))

print("\n%s" % ("全部通过 ✅" if fails == 0 else "有 %d 项失败 ❌" % fails))
sys.exit(1 if fails else 0)
