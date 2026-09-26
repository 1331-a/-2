# -*- coding: utf-8 -*-
"""sim_early.py — 【A/B 验收】前 20 手累积亏损的配对模拟对照。

为什么需要它：
  · 真实日志只有 4 局、对手风格各异 → 噪声大；
  · 日志回放**不能**衡量胜负（对手动作是既定历史，不会对我方新尺寸反应）；
  · 所以用本地引擎做**同 seed 配对**：同一副牌序分别跑「旧口径」与
    「新口径」，差异只来自策略 → 可归因。

引擎与协议（严格照 BotZone 规则）：
  HU、盲注 50/100、初始 20000、70 手、按钮位交替、每步 1 秒限时（不模拟）。
  request 用平台 0-51 牌号（内部编码 = 平台 + 8），history 用 raise-to 语义。

对手模型 CloudStyle：复刻 0924 日志里观察到的输局模式 ——
  翻前 2.5~3BB 小开池 → 翻牌 40% 池小注 → 转牌 75% 池大注；
  弱牌遇阻即弃（这正是「跟一手再被赶走」的另一半）。

用法：
    python sim_early.py 8                  # 8 组配对（每组 70 手）
    python sim_early.py 8 cloudturn        # 指定对手
    python sim_early.py 8 quiet 70         # 安静对手，70 手
"""
import os
import random
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

CHILD = r'''
# -*- coding: utf-8 -*-
import os, sys, random, json
sys.path.insert(0, os.getcwd())
import cards, evaluator, game_state, opponent, ranges, strategy, equity

OPP = sys.argv[1]; HANDS = int(sys.argv[2])
SB, BB, STACK = 50, 100, 20000

# ---- 旧口径开关（对照臂）：可分别关掉方案A / 方案B，用于拆分归因 ----
# 【2026-09-25 条件化后】关 B 必须把**条件化也一起中性化**：把上下限都压到
# 2.5（`OPEN_SIZE_HARD_CALL_BB` 是条件化的下限），否则 w 的作用仍在、只是
# 在 2.5~2.5 之间插值 —— 结果正确，但显式写清楚更不易误解。
_off_a = os.environ.get("WB_DISABLE_A") == "1" or os.environ.get("WB_OLD_ALL") == "1"
_off_b = os.environ.get("WB_DISABLE_B") == "1" or os.environ.get("WB_OLD_ALL") == "1"
if _off_a:
    strategy.FUTURE_COST_ON = False
    strategy.FUTURE_COST_CAP_ON = False
if _off_b:
    strategy.OPEN_SIZE_BB = 2.5
    strategy.OPEN_SIZE_HARD_CALL_BB = 2.5   # 条件化中性化（下=上=2.5）
    strategy.OPEN_SIZE_VS_STATION = 2.2
    strategy.ISO_SIZE_BB = 3.2
    strategy.STEAL_OPEN_BB = 2.5
    strategy._B_PRE_FRAC = {2.2: 2.2, 3.0: 3.0, 4.0: 4.0}
    _old = {"pf_s": 2.2, "pf_m": 3.0, "pf_l": 4.0}
    _c = opponent.OpponentModel.bucket_to_frac
    opponent.OpponentModel.bucket_to_frac = staticmethod(
        lambda b: _old.get(b, _c(b)))

# ---- 候选联动：开池范围随尺寸收紧（BTN_OPEN_PCT 覆盖）----
_p = os.environ.get("WB_OPEN_PCT")
if _p:
    strategy.BTN_OPEN_PCT = float(_p)

random.seed(0)   # 占位；每局在 run_match 里按 seed 重新播种


class CloudStyle:
    """翻前小开池 → 翻牌小注 → 弱牌遇阻即弃。"""
    def __init__(self):
        self.model = opponent.OpponentModel()

    def act(self, st):
        pct = ranges.hand_percentile(st.hole)
        pot = max(st.pot, 1); tc = st.to_call
        if tc == 0:
            if st.stage == "preflop":
                if pct <= 0.45:
                    return {"act": "raise", "num": st.curbet[st.my_id] + int(2.5 * BB)}
                return {"act": "check"}
            if pct <= 0.30:
                return {"act": "raise", "num": st.curbet[st.my_id] + int(0.40 * pot)}
            return {"act": "check"}
        if tc >= st.my_left:
            return {"act": "call"}
        if pct <= 0.25:
            return {"act": "call"}
        if tc <= 0.33 * pot:
            return {"act": "call"}
        return {"act": "fold"}


class CloudTurn(CloudStyle):
    """转牌主动打 75% 池 —— 制造「转牌被赶走」。"""
    def act(self, st):
        pct = ranges.hand_percentile(st.hole)
        pot = max(st.pot, 1); tc = st.to_call
        if tc == 0:
            if st.stage == "preflop":
                if pct <= 0.45:
                    return {"act": "raise", "num": st.curbet[st.my_id] + int(3.0 * BB)}
                return {"act": "check"}
            if st.stage == "turn" and pct <= 0.55:
                return {"act": "raise", "num": st.curbet[st.my_id] + int(0.75 * pot)}
            if st.stage == "flop" and pct <= 0.30:
                return {"act": "raise", "num": st.curbet[st.my_id] + int(0.40 * pot)}
            return {"act": "check"}
        if tc >= st.my_left:
            return {"act": "call"}
        if pct <= 0.25:
            return {"act": "call"}
        if tc <= 0.33 * pot:
            return {"act": "call"}
        return {"act": "fold"}


class Quiet(CloudTurn):
    """只在有牌力时继续 —— 低噪声对照。"""
    def act(self, st):
        pct = ranges.hand_percentile(st.hole)
        pot = max(st.pot, 1); tc = st.to_call
        if tc == 0:
            if st.stage == "preflop":
                if pct <= 0.40:
                    return {"act": "raise", "num": st.curbet[st.my_id] + int(2.5 * BB)}
                return {"act": "check"}
            if pct <= 0.22:
                return {"act": "raise", "num": st.curbet[st.my_id] + int(0.50 * pot)}
            return {"act": "check"}
        if tc >= st.my_left:
            return {"act": "call"}
        if pct <= 0.20:
            return {"act": "call"}
        if tc <= 0.25 * pot and pct <= 0.45:
            return {"act": "call"}
        return {"act": "fold"}


class Aggro(CloudStyle):
    """【2026-09-25 新增】持续施压型：宽开池 + 连街开火。

    这是「跟一手再被赶走」的**来源**——翻牌小注把你留下，转牌/河牌重锤赶走。
    用户假设：A（future_cost）应当在这类对手上有正收益。
    """
    def act(self, st):
        pct = ranges.hand_percentile(st.hole)
        pot = max(st.pot, 1)
        tc = st.to_call
        if tc == 0:
            if st.stage == "preflop":
                if pct <= 0.60:
                    return {"act": "raise", "num": st.curbet[st.my_id] + int(3.0 * BB)}
                return {"act": "check"}
            # 翻后：宽范围连街开火（转牌/河牌加重）
            if pct <= 0.65:
                frac = 0.80 if st.stage in ("turn", "river") else 0.55
                return {"act": "raise", "num": st.curbet[st.my_id] + int(frac * pot)}
            return {"act": "check"}
        if tc >= st.my_left:
            return {"act": "call"}
        # 面对下注：很少弃，常用加注继续施压
        if pct <= 0.40:
            return {"act": "raise",
                    "num": max(int(st.opp_round_bet or 0), tc) + int(0.8 * pot)}
        if pct <= 0.75 or tc <= 0.45 * pot:
            return {"act": "call"}
        return {"act": "fold"}


class Station(CloudStyle):
    """【2026-09-25 新增】一直硬跟型：几乎不弃、极少加注。

    用户假设：B（开池加大）在这类对手上**最没用**——没有弃牌权益，开大
    只是用更宽的范围在更大底池里打 → 应当降低 B 的权重（条件化后应被回退）。
    """
    def act(self, st):
        pct = ranges.hand_percentile(st.hole)
        pot = max(st.pot, 1)
        tc = st.to_call
        if tc == 0:
            if st.stage == "preflop":
                if pct <= 0.08:          # 极少主动加注
                    return {"act": "raise", "num": st.curbet[st.my_id] + int(3.0 * BB)}
                return {"act": "check"}
            if pct <= 0.06:
                return {"act": "raise", "num": st.curbet[st.my_id] + int(0.6 * pot)}
            return {"act": "check"}
        if tc >= st.my_left:
            return {"act": "call"}
        # 硬跟：只要不是把自己打光的大注就跟，基本不看牌力
        if tc <= st.my_chips * 0.55 or pct <= 0.45:
            return {"act": "call"}
        return {"act": "fold"}


_DIAG = os.environ.get("WB_DIAG") == "1"


class MyBot:
    def __init__(self):
        self.model = opponent.OpponentModel()

    def act(self, st):
        n0 = len(strategy.WB_FACE_LOG)
        a = strategy.decide(st, self.model)
        # 把「本次决策的最终动作」回填到决策过程中记录的跟注点全景上 ——
        # 否则无法区分「eq 已过门槛却仍弃牌」（硬规则先返回）与「被门槛挡住」。
        new = strategy.WB_FACE_LOG[n0:]
        if new:
            for r in new:
                r["action"] = a.get("act")
                r["num"] = a.get("num")
            if _DIAG:
                for r in new:
                    sys.stderr.write("FACE %s\n"
                                     % json.dumps(r, ensure_ascii=False))
            del strategy.WB_FACE_LOG[n0:]
        return a


FACT = {"cloud": CloudStyle, "cloudturn": CloudTurn, "quiet": Quiet,
        "aggro": Aggro, "station": Station}[OPP]


def play_hand(hand_no, dealer, bot0, bot1, twc, holes, board_cards):
    chips = [STACK - SB, STACK - BB]
    committed = [SB, BB]
    folded = [False, False]
    hist = []; board = []; stage_no = [0]

    def apply_action(p, action, rb):
        act = action.get("act", "call")
        tc = max(rb) - rb[p]
        if act == "fold":
            folded[p] = True
            hist.append({"round": stage_no[0], "player_id": p, "action": -1,
                         "action_type": "fold"})
            return "fold"
        if act == "check" or (act == "call" and tc <= 0):
            hist.append({"round": stage_no[0], "player_id": p, "action": 0,
                         "action_type": "check"})
            return "check"
        if act == "call":
            pay = min(tc, chips[p])
            chips[p] -= pay; committed[p] += pay; rb[p] += pay
            hist.append({"round": stage_no[0], "player_id": p, "action": 0,
                         "action_type": "call"})
            return "call"
        if act == "allin":
            pay = chips[p]; chips[p] = 0; committed[p] += pay; rb[p] += pay
            hist.append({"round": stage_no[0], "player_id": p, "action": pay,
                         "action_type": "raise"})
            return "raise"
        tgt = max(int(action.get("num", rb[p])), rb[p] + 1)
        pay = min(tgt - rb[p], chips[p])
        chips[p] -= pay; committed[p] += pay; rb[p] += pay
        hist.append({"round": stage_no[0], "player_id": p, "action": rb[p],
                     "action_type": "raise"})
        return "raise"

    def street(first):
        nonlocal board
        rb = [0, 0]; to_act = first; last_agg = None; acted = [False, False]
        while True:
            if sum(1 for f in folded if not f) <= 1:
                return
            if chips[0] == 0 and chips[1] == 0:
                return
            p = to_act
            if chips[p] == 0:
                to_act = 1 - to_act; continue
            if rb[0] == rb[1]:
                if last_agg is None:
                    if acted[0] and acted[1]:
                        return
                elif chips[last_agg] == 0 or p == last_agg:
                    return
            req = {"num_players": 2, "dealer_id": dealer, "my_id": p,
                   "my_chips": chips[p],
                   "my_cards": [c - 8 for c in holes[p]],
                   "public_cards": [c - 8 for c in board],
                   "history": list(hist), "hand": hand_no, "max_hand": 70,
                   "total_win_chips": list(twc), "total_win_games": [0, 0]}
            st = game_state.parse_request(req)
            act_out = (bot0 if p == 0 else bot1).act(st)
            kind = apply_action(p, act_out, rb)
            # ★【2026-09-25 修复·关键保真度】对手模型必须照**真实 bot 的方式**
            # 驱动：bot.py 每收一个 request 就调 `build_model_from_history`，
            # **从不调 `model.update`**。之前用 update 只写了动作计数，而
            # ① `hand_bet_counts`（bets/hand 的滑动窗口）只在
            #    `build_model_from_history` 的**换手分支**入队 → 窗口恒空
            #    → `avg_bets_per_hand()` 永远等于先验 0.9
            #    → A 的条件化无法区分激进/被动手（实测 aggro 上 A 空转 150/150）；
            # ② `bet_resp_events` 也从不入队 → `_learned_size` 学习路径全程失效。
            #
            # 更新对象：**另一个 bot 的模型**（它要学的是刚行动这个人）。
            # 而 `build_model_from_history` 统计的是 `1 - state.my_id` 的动作，
            # 所以必须把 my_id **翻到另一个座位**，它才会去数 player p 的动作。
            ob = 1 - p
            obot = bot1 if ob == 0 else bot0
            req_ob = {"num_players": 2, "dealer_id": dealer, "my_id": ob,
                      "my_chips": chips[ob],
                      "my_cards": [c - 8 for c in holes[ob]],
                      "public_cards": [c - 8 for c in board],
                      "history": list(hist), "hand": hand_no, "max_hand": 70,
                      "total_win_chips": list(twc), "total_win_games": [0, 0]}
            try:
                st_ob = game_state.parse_request(req_ob)
                opponent.build_model_from_history(obot.model, req_ob, st_ob)
            except Exception:
                pass
            acted[p] = True
            if kind == "raise":
                last_agg = p
            to_act = 1 - p

    def settle():
        pot = committed[0] + committed[1]
        if folded[0]:
            chips[1] += pot
        elif folded[1]:
            chips[0] += pot
        return [chips[0] - STACK, chips[1] - STACK]

    street(dealer)
    if sum(1 for f in folded if not f) <= 1:
        return settle()
    for idx, n in enumerate((3, 4, 5), start=1):
        board = board_cards[:n]; stage_no[0] = idx
        street(1 - dealer)
        if sum(1 for f in folded if not f) <= 1:
            return settle()
    p0 = committed[0] + committed[1]
    s0 = evaluator.evaluate_7(list(holes[0]) + board)
    s1 = evaluator.evaluate_7(list(holes[1]) + board)
    if s0 > s1:
        chips[0] += p0
    elif s1 > s0:
        chips[1] += p0
    else:
        chips[0] += p0 // 2; chips[1] += p0 - p0 // 2
    return settle()


def run_match(seed, hands):
    """跑一整局（70 手），返回 (前20手累积, 全场, 赢率)。每局用全新的
    bot/model —— 进程复用只省启动开销，不共享任何对局状态。

    【配对的关键】发牌用**专用 RNG**，与策略自身的随机数消耗彻底解耦
    （尺寸抖动 / 诈唬频率 / MC 抽样都用全局 random）。否则两臂一旦在某步
    做出不同动作，全局 RNG 流就错位、后续牌序分叉，「同 seed 配对」失效
    —— 差异里会混进牌运噪声，把 B 的真实效果淹没。
    """
    rng = random.Random(seed)      # 发牌专用：两臂完全一致
    random.seed(seed)              # 策略用：起点一致（MC 抽样噪声仍属固有）
    equity._rng.seed(seed + 7)     # MC 抽样专用流：让整局**可复现**
    # （equity._rng 默认是未播种的 random.Random() → 每次进程启动都不同，
    #   导致同 seed 重跑结果漂移、实测结论无法复核。必须显式播种。）
    my_bot = MyBot(); opp = FACT()
    curves = []; tot = 0; wins = 0; twc = [0, 0]
    for i in range(hands):
        dealer = i % 2
        deck = cards.full_deck(); rng.shuffle(deck)
        holes = [deck[0:2], deck[2:4]]
        board_cards = deck[4:9]
        profit = play_hand(i, dealer, my_bot, opp, twc, holes, board_cards)
        my_id = dealer
        my = profit[my_id]
        twc[my_id] += my; twc[1 - my_id] -= my
        tot += my
        if my > 0:
            wins += 1
        curves.append(tot)
    early = curves[19] if len(curves) >= 20 else curves[-1]
    return early, tot, wins / hands * 100.0


for sd in [int(x) for x in sys.argv[3:]]:
    e, t, w = run_match(sd, HANDS)
    print("%d|%d|%d|%.1f" % (sd, e, t, w))
'''

def run_batch(seeds, opp, hands, old, pct=None, off_a=None, off_b=None,
              no_bigbet_a=None):
    """一次子进程跑一批 seed（省启动开销），返回 {seed: (early, total, wr)}。

    old=True  → 关 A + 关 B（旧基准）
    off_a/off_b  → 单独关掉其中一项，用于**拆分归因**（是谁把结果拉差）。
    """
    env = dict(os.environ)
    if old:
        env["WB_OLD_ALL"] = "1"
    else:
        env.pop("WB_OLD_ALL", None)
    env.pop("WB_NO_FUTURE_COST", None)
    for k, v in (("WB_DISABLE_A", off_a), ("WB_DISABLE_B", off_b),
                 ("WB_NO_BIGBET_A", no_bigbet_a)):
        if v:
            env[k] = "1"
        else:
            env.pop(k, None)
    if pct:
        env["WB_OPEN_PCT"] = str(pct)
    else:
        env.pop("WB_OPEN_PCT", None)
    cmd = [PY, "-c", CHILD, opp, str(hands)] + [str(s) for s in seeds]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=HERE)
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise SystemExit("child failed")
    if os.environ.get("WB_DIAG") == "1" and r.stderr.strip():
        # 不限长度：诊断用（FACE 全景可能很多行）
        print(r.stderr.strip())
    out = {}
    for line in r.stdout.strip().splitlines():
        p = line.split("|")
        if len(p) != 4:
            continue
        sd = int(p[0])
        out[sd] = (int(p[1]), int(p[2]), float(p[3]))
    missing = [s for s in seeds if s not in out]
    if missing:
        print("!! 子进程缺少 %d 个 seed: %s" % (len(missing), missing))
        print(r.stdout[-800:])
    return out


def sign_test(better, worse):
    """符号检验的近似单侧 p 值（正态近似，n≥20 够用）。"""
    import math
    n = better + worse
    if n == 0:
        return 1.0
    z = (better - n / 2.0) / math.sqrt(n / 4.0)
    # 单侧：越小越说明「新臂更差」
    return 0.5 * math.erfc(-z / math.sqrt(2))


def summarize(label, diffs, base_vals, new_vals):
    """重尾分布下必须同时报「中位数 / 更好更差组数 / 符号检验 / 均值自助 CI」。

    单看均值会得出与事实相反的结论（少数大赢能把均值拉正，而多数组更差）。
    """
    better = sum(1 for d in diffs if d > 0)
    worse = sum(1 for d in diffs if d < 0)
    n = len(diffs)
    mean = statistics.mean(diffs)
    med = statistics.median(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    se = sd / (n ** 0.5) if n else 0.0
    p = sign_test(better, worse)
    lo, hi = bootstrap_ci(diffs)
    ci = ("95%%CI %+7d~%+7d" % (int(lo), int(hi))
          if lo == lo and hi == hi else "95%%CI     n/a   ")   # n<5 → NaN
    print("%-30s n=%-4d 更好 %-4d 更差 %-4d 持平 %-3d | 中位 %+7d | 均值 %+8d "
          "(%s) | 符号 p=%.3f" % (
              label, n, better, worse, n - better - worse, int(med),
              int(mean), ci, p))
    print("%-30s 水平：旧 %s → 新 %s" % (
        "", format(int(statistics.mean(base_vals)), ","),
        format(int(statistics.mean(new_vals)), ",")))


def bootstrap_ci(vals, iters=4000, alpha=0.05):
    """均值的百分位自助置信区间（重尾样本比正态近似可靠）。"""
    n = len(vals)
    if n < 5:
        return (float("nan"), float("nan"))
    rnd = random.Random(12345)
    means = []
    for _ in range(iters):
        s = 0
        for _ in range(n):
            s += vals[rnd.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(iters * alpha / 2)]
    hi = means[int(iters * (1 - alpha / 2))]
    return lo, hi


def decomp():
    """拆分归因：A 单独 / B 单独 / A+B 各自相对「旧基准」的效果。

    调用：`python sim_early.py --decomp [对手] [手数] [组数]`
    """
    opp = sys.argv[1] if len(sys.argv) > 1 else "cloudturn"
    hands = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    groups = int(sys.argv[3]) if len(sys.argv) > 3 else 250
    seeds = [20260924 + g * 977 for g in range(groups)]

    print("=" * 108)
    print("拆分归因：谁把「前 20 手累积」拉差？  对手=%s  %d手/组  %d组" % (
        opp, hands, groups))
    print("基准 = 关 A + 关 B（旧：开池 2.5BB，无 future_cost）")
    print("=" * 108)

    base = run_batch(seeds, opp, hands, old=True)
    base_v = [base[s][0] for s in seeds]
    print("%-30s 水平：旧 %s" % ("", format(int(statistics.mean(base_v)), ",")))

    arms = [
        ("仅 A（future_cost，尺寸不变）", dict(off_b=True)),
        ("仅 A·旧口径（硬规则不感知 A）", dict(off_b=True, no_bigbet_a=True)),
        ("仅 B（开池 3.5BB，无 A）", dict(off_a=True)),
        ("A + B（当前线上配置）", dict()),
    ]
    got = {}
    for label, kw in arms:
        if os.environ.get("WB_DIAG") == "1":
            print("@@@ARM %s" % label)     # 仅在诊断模式打分隔线（probe_arm_diff 依赖）
        arm = run_batch(seeds, opp, hands, old=False, **kw)
        got[label] = [arm[s][0] for s in seeds]
        d = [arm[s][0] - base[s][0] for s in seeds]
        summarize(label, d, base_v, got[label])

    # ★隔离项：「A 感知硬规则」自己的净效果（同 seeds 直接配对，不经过基准臂）
    k_new = "仅 A（future_cost，尺寸不变）"
    k_old = "仅 A·旧口径（硬规则不感知 A）"
    if k_new in got and k_old in got:
        print("-" * 108)
        print("隔离检验：只把「大注弃牌口径是否含后续投入」换掉（其余全同），同 seeds 配对")
        d = [x - y for x, y in zip(got[k_new], got[k_old])]
        summarize("A 感知硬规则 vs 旧口径", d, got[k_old], got[k_new])


def sweep():
    """对照多组候选（开池尺寸 × 开池范围），量化 B 的正确联动方向。

    调用：`python sim_early.py --sweep [对手] [手数] [组数]`
    main() 已把 `--sweep` 摘掉 → 此处 argv = [prog, 对手, 手数, 组数]。
    """
    opp = sys.argv[1] if len(sys.argv) > 1 else "cloudturn"
    hands = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    groups = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    seeds = [20260924 + g * 977 for g in range(groups)]

    print("=" * 108)
    print("B 联动搜索：开池 3.5BB × 开池范围(BTN_OPEN_PCT)   对手=%s  %d手/组  %d组" % (
        opp, hands, groups))
    print("基准臂 = 关 A + 关 B（旧：开池 2.5BB / 范围 0.80）")
    print("=" * 108)

    base = run_batch(seeds, opp, hands, old=True)
    base_v = [base[s][0] for s in seeds]

    cands = [("B 原样 (pct=0.80)", None), ("B+收范围 (pct=0.70)", "0.70"),
             ("B+收范围 (pct=0.60)", "0.60"), ("B+收范围 (pct=0.50)", "0.50"),
             ("仅收范围 (pct=0.60, 尺寸不变)", "0.60X")]
    for label, pct in cands:
        if pct and pct.endswith("X"):
            # 只收紧范围、尺寸保持旧值 → 用 OLD_ALL 再覆盖 pct
            arm = run_batch(seeds, opp, hands, old=True, pct=pct[:-1])
        else:
            arm = run_batch(seeds, opp, hands, old=False, pct=pct)
        d = [arm[s][0] - base[s][0] for s in seeds]
        summarize(label, d, base_v, [arm[s][0] for s in seeds])


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--sweep", "--decomp"):
        mode = sys.argv[1]
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        (sweep if mode == "--sweep" else decomp)()
        return
    groups = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    opp = sys.argv[2] if len(sys.argv) > 2 else "cloudturn"
    hands = int(sys.argv[3]) if len(sys.argv) > 3 else 70

    seeds = [20260924 + g * 977 for g in range(groups)]
    old = run_batch(seeds, opp, hands, old=True)
    new = run_batch(seeds, opp, hands, old=False)

    print("=" * 84)
    print("前 20 手累积盈亏配对对照   对手=%s  %d 手/组  %d 组" % (opp, hands, groups))
    print("旧臂 = 关 A(方案A) + 关 B(开池 2.5BB)   新臂 = A+B 全开")
    print("=" * 84)
    print("%6s %15s %15s %11s   %11s %11s" %
          ("seed", "旧·前20h", "新·前20h", "差", "旧·全场", "新·全场"))

    d_early, d_all = [], []
    for sd in seeds:
        oe, ot, _ = old[sd]
        ne, nt, _ = new[sd]
        d_early.append(ne - oe); d_all.append(nt - ot)
        print("%6d %15s %15s %+11s   %11s %11s" %
              (sd, format(oe, ","), format(ne, ","), format(ne - oe, ","),
               format(ot, ","), format(nt, ",")))

    print("-" * 84)
    summarize("A+B 全开 vs 旧", d_early,
              [old[s][0] for s in seeds], [new[s][0] for s in seeds])
    summarize("（全场）A+B vs 旧", d_all,
              [old[s][1] for s in seeds], [new[s][1] for s in seeds])


if __name__ == "__main__":
    main()
