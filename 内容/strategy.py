# -*- coding: utf-8 -*-
"""
strategy.py — AI 决策引擎（升级版）。

【升级总览】
  翻前：Chen 阈值 → 百分位范围体系
      - 庄家开池范围按对手原型动态调整（偷岩石盲 / 收紧打站点）；
      - 大盲防守由底池赔率推导 + 3-bet 范围按对手弃牌率极化/线性化；
      - 面对反加注按赔率+原型决定 4-bet/跟注/弃牌。
  翻后：新增三大模块
      1. 牌面纹理（湿润度）：决定下注尺寸与诈唬频率；
      2. 听牌 outs 计数：同花/两头顺/卡顺，支撑半诈唬与隐含赔率；
      3. EV 决策框架：跟注看底池赔率（隐含赔率修正），
         诈唬看弃牌权益是否超过盈亏平衡点，而非拍脑袋阈值。
  剥削：对手原型（station/maniac/rock/tag）驱动策略偏移——
      跟注站多薄价值少诈唬，疯子宽跟注，岩石的下注直接弃。
  风控：SPR 分层决策 + 对局状态调整（领先保收益、落后追分）。

对外仍只暴露 decide(state, model) -> action dict，
合法性安全程序 _normalize 保持不变（永远输出合法动作）。
"""

import time

from evaluator import (TWO_PAIR, ONE_PAIR, STRAIGHT, evaluate_7)
from equity import monte_carlo_equity
from ranges import hand_percentile

# ============ 可调参数（单位见注释） ============
# ---- 翻前范围（百分位，0~1，越小越紧） ----
BTN_OPEN_PCT = 0.80        # 庄家开池基准：前 80% 的起手牌（HU 标准宽度）
OPEN_SIZE_BB = 2.5         # 开池尺寸（raise-to，单位大盲；最小加注为 2BB）
OPEN_SIZE_VS_STATION = 2.2  # 对跟注站小尺寸开池（其反正不弃）
BB_3BET_PCT = 0.13         # 大盲 3-bet 基准范围
BB_3BET_BLUFFY = 0.20      # 对手高弃牌率时的诈唬性 3-bet 范围
ISO_SIZE_BB = 3.2          # 大盲对溜入者的隔离加注尺寸
SB_4BET_VALUE_PCT = 0.035  # 面对反加注的价值 4-bet 范围（JJ+/AK）
SB_4BET_MULT = 2.3        # 4-bet 尺寸 = 对手 3-bet 额度 × 此倍数

# ---- 翻后下注尺寸（底池比例） ----
VALUE_BET = 0.65           # 常规价值下注
VALUE_BET_WET = 0.75       # 湿润牌面：大注锁听牌
THIN_VALUE = 0.55          # 薄价值 / 中强牌
OVERBET = 1.30             # 河牌坚果超池下注（榨取最大价值）
BLOCKER_BET = 0.33         # 干燥面不利位置小注保护
CBET = 0.55                # 持续下注 / 半诈唬
BLUFF = 0.55               # 纯诈唬
BLOCKER = 0.45             # 中等牌有位置的小注施压

# ---- 计算预算 ----
MC_ITERATIONS = 1000       # 蒙特卡洛最大抽样数
TIME_BUDGET = 0.5          # 决策软时限（秒），平台预检超时 8s，预留充足余量


# ---------------- 对外入口 ----------------
def decide(state, model):
    """根据当前状态与对手模型返回动作 dict（经 _normalize 合法化）。"""
    if state.stage == "preflop":
        action = _preflop_decide(state, model)
    else:
        action = _postflop_decide(state, model)
    return _normalize(state, action)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------- 对局状态调整（风控·宏观层） ----------------
def _match_adjust(state):
    """
    50 手定胜负的比赛中，根据领先量与剩余手数调整风险偏好：
      protect  —— 大幅领先且临近终局：降波动（少诈唬、跟注更严）；
      pressure —— 领先且对手短码：ICM 压力下放宽全下/加注（对手弃牌率高）；
      catchup  —— 大幅落后且临近终局：加波动（多诈唬、宽跟注）；
      normal   —— 常规。
    """
    try:
        hands_left = state.max_hand - state.hand_num
        lead = (state.total_win_chips[state.my_id]
                - state.total_win_chips[state.opp_id])
        if hands_left <= 15:
            # 领先且对手是短码：我的全下带来淘汰压力，弃牌权益高于理论值
            if lead >= 30 * state.big_blind and state.opp_chips <= 0.7 * state.my_chips:
                return "pressure"
            if lead >= 30 * state.big_blind:
                return "protect"
            if lead <= -30 * state.big_blind:
                return "catchup"
    except Exception:
        pass
    return "normal"


# ================================================================
#  翻牌前：百分位范围决策
# ================================================================
def _preflop_decide(state, model):
    pct = hand_percentile(state.hole)   # 起手牌百分位（越小越强）
    arch = model.archetype()
    adj = _match_adjust(state)

    if state.is_button:
        if state.to_call <= state.blind:      # 面对大盲（含无人加注）
            return _button_open(state, model, pct, arch, adj)
        return _button_vs_3bet(state, model, pct, arch, adj)
    else:
        if state.to_call <= 0:                # 庄家溜入，我有选项
            return _bb_option(state, model, pct, arch)
        return _bb_defend(state, model, pct, arch, adj)


def _button_open(state, model, pct, arch, adj):
    """庄家位开池：范围随对手原型伸缩。"""
    open_pct = BTN_OPEN_PCT
    if arch == "rock":
        open_pct = 0.92     # 岩石不惩罚宽开池 → 更激进偷盲
    elif arch == "station":
        open_pct = 0.85     # 站点翻后乱跟 → 价值牌多打
    elif arch == "maniac":
        open_pct = 0.75     # 疯子爱反加 → 略收紧避免被掀翻
    if adj == "protect":
        open_pct = min(open_pct, 0.85)
    elif adj == "catchup":
        open_pct = min(0.97, open_pct + 0.15)  # 落后追分：大幅加宽开池

    if pct <= open_pct:
        size = OPEN_SIZE_VS_STATION if arch == "station" else OPEN_SIZE_BB
        return _raise_to(state, size * state.big_blind)

    # 垃圾牌：对手极少主动加注时补齐溜入看翻牌；落后追分时绝不弃庄家位
    limp_max = 1.0 if adj == "catchup" else 0.96
    if pct <= limp_max and (model.eff_pfr() < 0.25 or adj == "catchup"):
        return {"act": "call"}
    return {"act": "fold"}


def _is_4bet_bluff(hole):
    """诈唬 4-bet 候选：同花 A2s~A6s —— A 阻断对手 AA/AK，同花保留后手。"""
    r = sorted(c // 4 for c in hole)
    hi, lo = r[1], r[0]
    suited = (hole[0] % 4) == (hole[1] % 4)
    return hi == 14 and suited and 2 <= lo <= 6


def _button_vs_3bet(state, model, pct, arch, adj):
    """庄家面对反加注：极化 4-bet（价值+诈唬） / 跟注 / 弃牌。"""
    to_call = state.to_call
    pot = state.pot
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 价值 4-bet：JJ+/AK（前 ~3.5%）；对疯子放宽（其反加范围极宽）
    value_pct = SB_4BET_VALUE_PCT if arch != "maniac" else 0.08
    if adj == "pressure":              # ICM 压力：价值 4-bet 放宽
        value_pct = min(0.15, value_pct + 0.06)
    if pct <= value_pct:
        return _raise_to(state, SB_4BET_MULT * state.curbet[state.opp_id])

    # 诈唬 4-bet：Axs 阻挡牌，仅在对手有一定弃牌率或 ICM 压力下使用
    opp_fold = model.eff_fold_to_bet()
    if _is_4bet_bluff(state.hole) and (opp_fold >= 0.40 or adj == "pressure"):
        return _raise_to(state, SB_4BET_MULT * state.curbet[state.opp_id])

    # 跟注范围：赔率越好越宽；原型修正
    # 保证整体防守频率不低于底池赔率要求（即 call_pct >= required 的折算）
    call_pct = _clamp(1.0 - 2.0 * required, 0.10, 0.60)
    call_pct = max(call_pct, required)   # 防守底线：至少满足赔率
    if arch == "maniac":
        call_pct = min(0.75, call_pct + 0.15)   # 疯子反加不可信
    elif arch == "rock":
        call_pct = max(0.08, call_pct - 0.12)   # 岩石反加=大牌，弃
    if adj == "protect":
        call_pct -= 0.05
    elif adj == "catchup":
        call_pct += 0.05
    if pct <= call_pct:
        return {"act": "call"}
    return {"act": "fold"}


def _bb_option(state, model, pct, arch):
    """大盲面对溜入：强牌隔离加注，其余免费看牌。"""
    iso_pct = 0.40
    if arch == "station":
        iso_pct = 0.30     # 对站点隔离靠价值范围
    elif arch == "rock":
        iso_pct = 0.55     # 多惩罚岩石的溜入
    if pct <= iso_pct:
        return _raise_to(state, ISO_SIZE_BB * state.big_blind)
    return {"act": "check"}


def _bb_defend(state, model, pct, arch, adj):
    """大盲防守：底池赔率推导防守范围 + 极化 3-bet。"""
    to_call = state.to_call
    pot = state.pot
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 防守总范围：跟注需求越低防得越宽（HU vs 2.5x ≈ 55%）
    defend_pct = _clamp(1.15 - 1.8 * required, 0.22, 0.90)
    if arch == "maniac":
        defend_pct = min(0.95, defend_pct + 0.12)
    if adj == "catchup":
        defend_pct += 0.05

    # 3-bet 范围：对手面对加注弃牌率高 → 宽（诈唬）；
    #             跟注站 → 窄（纯价值，线性化）
    threebet_pct = BB_3BET_PCT
    if model.eff_fold_to_bet() >= 0.50:
        threebet_pct = BB_3BET_BLUFFY
    if arch == "station":
        threebet_pct = 0.10
    if adj == "catchup":
        threebet_pct += 0.05

    if pct <= threebet_pct:
        return _raise_to(state, 3.0 * state.curbet[state.opp_id])
    if pct <= defend_pct:
        # 很贵的跟注只防守范围上半区（反向隐含赔率保护）
        if required > 0.45 and pct > defend_pct * 0.7:
            return {"act": "fold"}
        return {"act": "call"}
    return {"act": "fold"}


# ================================================================
#  翻牌后：纹理 + 胜率 + EV + 剥削 + 风控
# ================================================================
def _board_texture(board):
    """
    牌面纹理评估：
      wet  湿润度 0~1（同花/顺子连通/对子面，听牌越多越湿）；
      high 高牌程度 0~1（A 高面=1，低面=0）。
    用途：湿面下注更大（拒绝给听牌好赔率），干面适合小注/诈唬。
    """
    n = len(board)
    if n == 0:
        return {"wet": 0.0, "high": 0.0}
    ranks = sorted((c // 4 for c in board), reverse=True)
    suits = {}
    for c in board:
        suits[c % 4] = suits.get(c % 4, 0) + 1
    max_suit = max(suits.values())

    wet = 0.0
    if max_suit >= 3:
        wet += 0.35            # 成花面（含三同花）
    elif max_suit == 2 and n >= 3:
        wet += 0.15            # 双色面
    rs = set(ranks)
    if 14 in rs:
        rs.add(1)
    cluster = 0
    for h in range(5, 15):
        window = {h, h - 1, h - 2, h - 3, h - 4}
        cluster = max(cluster, len(window & rs))
    if cluster >= 3:
        wet += 0.25            # 连通面
    if cluster >= 4:
        wet += 0.15            # 极湿（四连/已成顺）
    if len(set(ranks)) < n:
        wet += 0.10            # 对子面（葫芦可能）
    if n == 4:
        wet += 0.05
    return {"wet": min(wet, 1.0), "high": (ranks[0] - 2) / 12.0}


def _count_outs(hole, board):
    """
    统计改进型听牌张数（同花听 9、顺子听每缺一档 4 张）。
    两头顺会产生两个缺档（8 outs），卡顺一个缺档（4 outs）。
    用于半诈唬判定与隐含赔率折算。
    """
    if len(board) < 3 or len(board) >= 5:
        return 0
    outs = 0
    suits = {}
    for c in hole + board:
        suits[c % 4] = suits.get(c % 4, 0) + 1
    if any(v == 4 for v in suits.values()):
        outs += 9              # 同花听牌

    all_ranks = set(c // 4 for c in hole + board)
    if 14 in all_ranks:
        all_ranks.add(1)
    hole_ranks = set(c // 4 for c in hole)
    missing_ranks = set()
    for h in range(5, 15):
        window = {h, h - 1, h - 2, h - 3, h - 4}
        miss = window - all_ranks
        if len(miss) == 1 and (window & hole_ranks):
            missing_ranks |= miss
    outs += 4 * len(missing_ranks)
    return min(outs, 17)


def _last_preflop_raiser(state):
    """最后一位在翻前主动加注的玩家 ID（None 表示无人加注）。
    一次扫描同时得到「我是不是翻前主动方」与「对手是不是」。"""
    last = None
    for r in state.history:
        if int(r.get("round", 0)) != 0:
            continue
        a = r.get("action", 0)
        at = r.get("action_type", "")
        if at in ("raise", "allin") or (isinstance(a, int) and a > 0):
            last = r.get("player_id")
    return last


def _opp_raised_preflop(state):
    """对手翻前是否主动加注（判断其范围宽度与激进度）。"""
    return _last_preflop_raiser(state) == state.opp_id


def _bluff_buffer(state):
    """诈唬缓冲按阻挡牌效应调整（手握 A 阻断对手 Ax 强牌/坚果同花）。
    A→0.03，K→0.06，小废牌→0.12。"""
    ranks = {c // 4 for c in state.hole}
    if 14 in ranks:
        return 0.03
    if 13 in ranks:
        return 0.06
    return 0.12


def _opp_range_pct(model, opp_raised_preflop):
    """对手当前范围宽度估计（0~1），驱动蒙特卡洛对手抽样。"""
    vpip = model.eff_vpip()
    if opp_raised_preflop:
        base = 0.22 * (0.7 + vpip)      # 主动加注者：范围收紧
    else:
        base = 0.55 * (0.8 + 0.6 * vpip)  # 平跟入池：范围较宽
    return _clamp(base, 0.08, 0.95)


def _postflop_decide(state, model):
    adj = _match_adjust(state)
    arch = model.archetype()
    tex = _board_texture(state.board)
    is_river = state.current_round >= 3

    # 对手范围感知的胜率估算（对手越松范围越宽）
    last_raiser = _last_preflop_raiser(state)
    opp_raised = (last_raiser == state.opp_id)
    i_aggressor = (last_raiser == state.my_id)
    range_pct = _opp_range_pct(model, opp_raised)
    eq = monte_carlo_equity(
        state.hole, state.board, iterations=MC_ITERATIONS,
        opp_range_pct=range_pct,
        deadline=time.time() + TIME_BUDGET)

    category = evaluate_7(state.hole + state.board)[0]
    outs = _count_outs(state.hole, state.board)

    # ---- 强度分层（牌型 × 胜率 双口径）----
    strong = category >= TWO_PAIR or eq >= 0.75   # 两对及以上 / 压制性胜率
    good = (not strong) and eq >= 0.60            # 顶对好踢脚级别
    medium = (not good) and eq >= 0.50            # 中等成牌
    big_draw = (not is_river) and outs >= 8       # 同花/两头顺
    draw = (not is_river) and outs >= 4           # 卡顺级

    if state.to_call <= 0:
        return _check_side(state, model, eq, category, strong, good, medium,
                           big_draw, draw, tex, arch, adj, is_river,
                           i_aggressor)
    return _face_bet(state, model, eq, category, strong, good, medium,
                     big_draw, draw, arch, adj, is_river, i_aggressor)


def _fold_equity(model, adj):
    """有效弃牌权益（诈唬收益的核心输入），按对局状态打折/加成。"""
    fe = model.eff_fold_to_bet()
    if adj == "protect":
        fe *= 0.5      # 领先保收益：诈唬大幅压缩
    elif adj == "catchup":
        fe *= 1.3      # 落后追分：诈唬加码
    return _clamp(fe, 0.0, 0.9)


# ---------------- 无人下注（可过牌）----------------
def _check_side(state, model, eq, category, strong, good, medium, big_draw,
                draw, tex, arch, adj, is_river, i_aggressor):
    """主动下注侧：价值 / 保护 / 半诈唬 / 纯诈唬（EV 门控 + 阻挡牌）。"""
    fold_eq = _fold_equity(model, adj)
    spr = state.effective_stack / max(state.pot, 1)
    # 有利位置 + 翻前主动方 = 标准 C-Bet 场景，诈唬门槛下调
    cbet_spot = i_aggressor and state.is_button
    fold_eq = _fold_equity(model, adj)
    spr = state.effective_stack / max(state.pot, 1)

    if strong:
        # 河牌坚果优势 + 对手非岩石：超池下注榨取最大价值
        if is_river and (category >= STRAIGHT or eq >= 0.80) and arch != "rock":
            return _bet_fraction(state, OVERBET)
        # 湿面大注拒绝给听牌好赔率，干面稍小求跟注
        frac = VALUE_BET_WET if tex["wet"] >= 0.5 else VALUE_BET
        if is_river:
            frac = VALUE_BET
        return _bet_fraction(state, frac)

    if good:
        # SPR 很低：直接大注把后街筹码在有利时打光
        if spr <= 2.5:
            return _bet_fraction(state, 0.80)
        frac = VALUE_BET if tex["wet"] >= 0.5 else THIN_VALUE
        # 河牌对跟注站做薄价值（其会用差牌跟注）
        if is_river and arch == "station":
            frac = 0.60
        return _bet_fraction(state, frac)

    if big_draw:
        # 半诈唬优先级高于控池：强听牌即使当前胜率中等，
        # 也要么积累底池要么直接赢下（弃牌权益 + 成牌双重收益）
        if fold_eq >= 0.30 or state.is_button:
            return _bet_fraction(state, CBET)
        return {"act": "check"}

    if medium:
        # 有利位置 C-Bet 频率目标 ≥70%：湿面或主动方都下注施压/保护
        if state.is_button and (tex["wet"] >= 0.4 or cbet_spot):
            return _bet_fraction(state, BLOCKER)
        # 不利位置 + 极干面 + 中强牌：1/3 池小注保护（低成本纠缠+节省筹码）
        if not state.is_button and tex["wet"] < 0.2 and eq >= 0.55:
            return _bet_fraction(state, BLOCKER_BET)
        return {"act": "check"}

    if draw:
        return {"act": "check"}     # 弱听牌免费看牌

    # 空气：纯诈唬，EV 门控 + 阻挡牌效应
    breakeven = BLUFF / (1.0 + BLUFF)        # ≈ 0.355
    buffer = _bluff_buffer(state)            # A=0.03 / K=0.06 / 小废牌=0.12
    if cbet_spot:
        buffer = max(0.0, buffer - 0.05)     # 有利位置 C-Bet 诈唬门槛下调
    if adj == "protect":
        buffer += 0.15                       # 领先保收益：少诈唬
    elif adj == "catchup":
        buffer = max(0.0, buffer - 0.06)     # 落后追分：放宽诈唬
    if fold_eq >= breakeven + buffer:
        # 无位置时只诈唬非激进对手（避免被 check-raise 掀翻）
        if state.is_button or model.eff_bet_freq() < 0.45:
            # 河牌诈唬额外要求：对手在河牌有弃牌倾向（避免诈唬被站点抓死）
            if (not is_river) or (fold_eq >= 0.45 and
                                  model.river_fold_rate() >= 0.35):
                return _bet_fraction(state, BLUFF)
    return {"act": "check"}


# ---------------- 面对下注 ----------------
def _face_bet(state, model, eq, category, strong, good, medium, big_draw, draw,
              arch, adj, is_river, i_aggressor):
    """面对下注：底池赔率（隐含修正）+ 原型/街级修正 + 加注/跟注/弃牌。"""
    pot = state.pot
    to_call = state.to_call
    required = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

    # 隐含赔率：强听牌 + 深筹码时，有效跟注需求降低
    implied = 1.0
    if big_draw and state.effective_stack > 4 * pot and not is_river:
        implied = 1.4
    eff_req = required / implied

    # 跟注安全边际：默认 2%；岩石的下注≈价值 → 抬门槛；疯子乱打 → 放宽
    margin = 0.02
    if arch == "rock":
        eff_req += 0.10
    elif arch == "maniac":
        eff_req -= 0.08
    # 街级修正：对手转牌加注率飙升 → 河牌下注更可能是真强牌，跟注更严
    if is_river and model.turn_aggr() >= 0.45:
        eff_req += 0.05
    if adj == "protect":
        margin += 0.06       # 领先时只打好赔率
    elif adj == "catchup":
        margin -= 0.03       # 落后时多看几张牌

    # ---- 对手全下 / 需跟注额 ≥ 剩余筹码：纯赔率决策 ----
    if state.opp_is_allin or to_call >= state.my_left:
        # ICM 压力：领先且对手短码，放宽跟注（对手全下范围更紧）
        thr = eff_req - 0.05 if adj == "pressure" else eff_req + 0.02
        if strong or eq >= thr or (big_draw and eq >= eff_req):
            return {"act": "allin"}
        return {"act": "fold"}

    # ---- 强牌：加注求价值；浅筹码或 ICM 压力直接全下 ----
    if strong:
        spr = state.effective_stack / max(pot, 1)
        if spr <= 2.0 or adj == "pressure":
            return {"act": "allin"}
        # 河牌坚果 + 有位置：超池加注榨取
        if is_river and (category >= STRAIGHT or eq >= 0.80) and \
                state.is_button and arch != "rock":
            return _bet_fraction(state, OVERBET)
        return _raise_pot(state)

    # ---- 良好成牌：价值加注或赔率跟注 ----
    if good:
        if state.is_button and eq >= 0.68 and arch != "rock":
            return _raise_pot(state)          # 位置+明显领先 → 加注
        if eq >= eff_req + margin:
            return {"act": "call"}
        if eq >= eff_req and arch == "maniac":
            return {"act": "call"}            # 疯子的下注不可全信
        return {"act": "fold"}

    # ---- 强听牌：半诈唬加注或按（隐含）赔率抽牌（优先于中等成牌：
    #      强听牌有隐含赔率加成，按成牌口径评估会低估其价值）----
    if big_draw:
        if model.eff_fold_to_bet() >= 0.45 and required <= 0.40:
            return _raise_pot(state)          # 半诈唬加注（弃牌权益+成牌双收益）
        if eq >= eff_req:
            return {"act": "call"}
        if eq >= required * 0.75:
            return {"act": "call"}            # 隐含赔率勉强支撑
        return {"act": "fold"}

    # ---- 中等成牌：只打好赔率 ----
    if medium:
        if eq >= eff_req + margin + 0.03:
            return {"act": "call"}
        if eq >= eff_req and arch == "maniac":
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 弱听牌：只在很便宜时跟 ----
    if draw:
        if required <= 0.20 and eq >= required * 0.9:
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 空气：罕见反诈唬（对手高弃牌 + 我有位置 + 便宜）----
    if model.eff_fold_to_bet() >= 0.60 and required <= 0.30 and state.is_button:
        return _raise_pot(state)
    return {"act": "fold"}


# ---------------- 动作构造辅助（raise-to 语义） ----------------
def _raise_to(state, target_total):
    """加注到本轮总注额 target_total；越界转全下。"""
    target_total = int(round(target_total))
    if target_total < state.min_raise():
        target_total = state.min_raise()
    if target_total >= state.max_raise() or target_total >= state.my_left:
        return {"act": "allin"}
    return {"act": "raise", "num": target_total}


def _bet_fraction(state, fraction):
    """当可以过牌时，下注底池的 fraction 倍。"""
    target = state.curbet[state.my_id] + int(fraction * state.pot)
    return _raise_to(state, target)


def _raise_pot(state):
    """面对下注时，做约一个底池大小的加注。"""
    to_call = state.to_call
    target = state.curbet[state.my_id] + to_call + (state.pot + to_call)
    return _raise_to(state, target)


# ---------------- 合法性安全程序（不变，最后防线） ----------------
def _normalize(state, action):
    """
    防止非法操作触发的最终安全程序。
    - 规则5：本局有人全押 → 只能弃牌/全押；
    - check 仅当无需跟注；call 需筹码严格大于跟注额；
    - raise 夹紧到 [最小加注, 筹码上界)，越界转全下；
    - 未知动作一律退化为最安全合法动作。
    """
    act = action.get("act", "fold")
    to_call = state.to_call
    my_left = state.my_left

    # 规则5：本局有人全押 → 只允许弃牌(-1)/全押(-2)
    if state.any_allin:
        if act == "fold":
            return {"act": "fold"}
        return {"act": "allin"} if my_left > 0 else {"act": "fold"}

    if act == "fold":
        return {"act": "fold"}

    if act == "check":
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "allin":
        if my_left > 0:
            return {"act": "allin"}
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "call":
        if to_call <= 0:
            return {"act": "check"}
        if to_call >= my_left:      # 需严格 my_left > to_call 才能跟注
            return {"act": "allin"}
        return {"act": "call"}

    if act == "raise":
        try:
            num = int(round(float(action.get("num", 0))))
        except (TypeError, ValueError):
            num = 0
        min_r = state.min_raise()
        max_r = state.max_raise()
        if num < min_r:
            num = min_r
        if num >= max_r or num >= my_left:
            return {"act": "allin"}
        return {"act": "raise", "num": num}

    return {"act": "fold"}
