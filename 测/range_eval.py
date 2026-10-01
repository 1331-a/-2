# -*- coding: utf-8 -*-
"""range_eval.py — 对手范围模型的**无偏校准**测量（只测量，不改策略）。

背景：`_opp_range_pct` 把对手范围建模成「按百分位等权的 top-X%」。
若真实分布并非等权，模型就会系统性高/低估我方胜率。

★ 取样设计（关键，避免选择偏差）：
  对**每一手**都取样 —— 包括我方翻前就弃牌的手。
  对手的翻前动作在日志里必然可见（deal_hole 在该手开始时就有），
  因此「条件于对手翻前加注，其底牌分布」是**无偏**的。
  （若只在「进入翻牌」的手上取样，会因为「对手牌强→下注大→我方弃牌」
    而把强牌剔出样本 —— 这正是第一版测量的偏差来源。）

指标：
  覆盖率 = P(真实底牌 percentile ≤ 模型给的 range_pct)
     · 等权 top-X% 模型下，理想覆盖率应接近 100%（真实范围就是 top-X% 时）
     · 明显 <100% → 模型范围**过窄/过强** → 低估我方胜率
     · 覆盖率 > 100% 不可能；若远高于 rp 的等权预期，说明范围偏宽
  mean(p)/mean(rp)
     · 等权假设下应 ≈ 0.50（真实底牌均匀铺在 [0, rp] 内）
     · <0.50 → 真实范围比模型更靠前（模型过宽 → 高估胜率）
     · >0.50 → 真实范围更靠后（模型过窄 → 低估胜率）

用法:
    python range_eval.py [--seat=N] [日志路径...]
"""
import collections
import glob
import io
import json
import os
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True,
                              write_through=True)
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
sys.path.insert(0, os.path.join(BASE, "内容"))

import strategy as S            # noqa: E402
import game_state as G          # noqa: E402
import opponent as O            # noqa: E402
import match_ctx as M           # noqa: E402
from ranges import hand_percentile                          # noqa: E402
from botbattle_log import load_botbattle, card_to_platform   # noqa: E402

_args = [a for a in sys.argv[1:] if not a.startswith("--")]
LOGS = _args or sorted(set(
    glob.glob(os.path.join(BASE, "内容", "记录", "*botbattle*log.json"))
    + glob.glob("C:/Users/HP/Downloads/botbattle*log.json")))


def detect_seat(obj):
    """我方座位。注意：自对弈日志双方都是自己 → 返回 0，样本需单独标注。"""
    m = obj.get("match") or {}
    for idx, key in ((0, "bot_a"), (1, "bot_b")):
        b = m.get(key) or {}
        if "j1331" in str(b.get("owner_display", "")):
            return idx
    return 0


def is_selfplay(obj):
    m = obj.get("match") or {}
    a, b = m.get("bot_a") or {}, m.get("bot_b") or {}
    return a.get("id") == b.get("id") or (
        a.get("owner_display") == b.get("owner_display"))


def scan(path, seat):
    """返回 [(hand1, group, rp, pct), ...]，每手一条（含我方弃牌的手）。

    group 按「位置 + 翻前动作」细分 —— 混在一起会被 BB 免费过牌污染
    （BB 过牌 = 任意两张牌，不是「跟注范围」）：
      SB_open   : 小盲（=庄家）开池加注 —— 范围最宽
      SB_limp   : 小盲平跟
      BB_3bet   : 大盲反加 —— 范围最窄
      BB_call   : 大盲跟注加注
      BB_check  : 大盲免费过牌（任意两张牌，仅作对照）
    """
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    opp = 1 - seat
    holes = {}
    ops = collections.defaultdict(list)
    sb_of = {}
    cur = None
    street = "preflop"
    for ev in (obj.get("replay") or {}).get("events") or []:
        t = ev.get("type")
        if t == "hand_start":
            cur = int(ev.get("hand", -1))
            street = "preflop"
            sb_of[cur] = int(ev.get("sb", 0) or 0)
        elif t == "deal_board":
            street = str(ev.get("street", "flop"))
        elif t == "deal_hole":
            holes[cur] = ev.get("holes") or [[], []]
        elif t == "action" and street == "preflop":
            if int(ev.get("player", -1)) == opp:
                ops[cur].append(str(ev.get("action", "")).lower())

    reqs = load_botbattle(path, my_seat=seat) or []
    by_hand = collections.defaultdict(list)
    for req, meta in reqs:
        by_hand[int(req.get("hand", 0))].append(req)

    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    out = []
    for h in sorted(holes):
        hs = holes[h][opp] if len(holes[h]) > opp else []
        oh = [card_to_platform(c) for c in hs]
        if len(oh) != 2 or any(c is None for c in oh):
            continue
        acts = ops.get(h, [])
        if not acts:
            continue
        is_sb = (sb_of.get(h, 0) == opp)
        has_raise = any(a in ("raise", "allin") for a in acts)
        if is_sb:
            grp = "SB_open" if has_raise else "SB_limp"
        else:
            if has_raise:
                grp = "BB_3bet"
            elif any(a == "call" for a in acts):
                grp = "BB_call"
            else:
                grp = "BB_check"
        # 模型侧：用「本手对手动作之后是否加注」这一事实取对应的范围估计
        try:
            rp = float(S._opp_range_pct(model, has_raise))
        except Exception:
            continue
        p = float(hand_percentile([c + 8 for c in oh]))
        out.append((h + 1, grp, rp, p))
        for req in by_hand.get(h, []):
            try:
                st = G.parse_request(req)
                O.build_model_from_history(model, req, st)
                ctx.update(st)
            except Exception:
                pass
    return out


def report(name, rows):
    if not rows:
        print("  %-16s （无样本）" % name)
        return
    n = len(rows)
    rps = [r[2] for r in rows]
    pcts = [r[3] for r in rows]
    inc = sum(1 for r in rows if r[3] <= r[2]) / n
    ratio = statistics.mean(pcts) / statistics.mean(rps) if statistics.mean(rps) else 0
    print("  %-16s n=%-4d  模型 range_pct=%.3f   真实百分位 均=%.3f 中位=%.3f"
          % (name, n, statistics.mean(rps), statistics.mean(pcts),
             statistics.median(pcts)))
    print("  %-16s 覆盖率=%.1f%%   mean(p)/mean(rp)=%.3f  (等权应≈0.50)"
          % ("", inc * 100, ratio))
    # 「若真实范围=top-W%，则均值应为 W/2」→ 反推 W
    implied_w = 2 * statistics.mean(pcts)
    print("  %-16s 由均值反推真实范围宽度 ≈ top-%.0f%%   （模型给的是 top-%.0f%%）"
          % ("", implied_w * 100, statistics.mean(rps) * 100))


print("对手范围模型校准（无偏取样：全部手牌，含我方弃牌的手）")
print("日志 %d 份\n" % len(LOGS))

real, selfp = [], []
for p in LOGS:
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        seat = detect_seat(obj)
        sp = is_selfplay(obj)
        rows = scan(p, seat)
    except Exception as e:
        print("  %-44s ✗ %r" % (os.path.basename(p)[:44], e))
        continue
    (selfp if sp else real).extend(rows)
    print("  %-44s %s 样本 %3d" % (os.path.basename(p)[:44],
                                   "自对弈" if sp else "真实对手", len(rows)))

print()
print("=== A. 真实对手（cloud）—— 按位置+动作细分 ===")
GROUPS = ["SB_open", "SB_limp", "BB_3bet", "BB_call", "BB_check"]
for g in GROUPS:
    report(g, [r for r in real if r[1] == g])
report("小计", real)

print()
print("=== B. 自对弈（对手其实也是本 bot 的旧版）—— 仅供对照 ===")
for g in GROUPS:
    report(g, [r for r in selfp if r[1] == g])
report("小计", selfp)

print()
print("=== 解读 ===")
print("  覆盖率明显 <100%      → 模型范围过窄（把对手想得太强）→ 低估我方胜率 → 过度弃牌")
print("  mean(p)/mean(rp) <0.50 → 真实范围更靠前 → 模型过宽 → 高估胜率 → 跟注过多")
print("  mean(p)/mean(rp) >0.50 → 真实范围更靠后 → 模型过窄 → 低估胜率 → 弃牌过多")
