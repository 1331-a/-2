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

from evaluator import (TWO_PAIR, ONE_PAIR, STRAIGHT, THREE_OF_A_KIND,
                       FULL_HOUSE, HIGH_CARD, evaluate_7)
from equity import monte_carlo_equity
from ranges import hand_percentile
from opponent import OpponentModel

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

# ---- 翻前全下决策（按累计盈亏动态分档，防止「优势下跟 all-in 比运气」）----
ALLIN_MC = 600             # 全下决策蒙特卡洛抽样数（翻前只需 5 张公共牌，速度快）
ALLIN_TIME_BUDGET = 0.30   # 全下决策软时限（秒）
ALLIN_BAND_PCT = 0.10      # 第四步：极端赔率带宽（必要胜率 ±10% 无条件跟/弃，防反向剥削）
ALLIN_LEAD_BB = 50         # 大幅领先/落后阈值（单位大盲，50BB=+5000）
ALLIN_SMALL_BB = 10        # 小幅领先/落后阈值（10BB=+1000）
# 各盈亏档位的跟注胜率门槛（0~1）：盈利越多越不跟（保收益），落后越多越敢跟（搏翻盘）
ALLIN_THR = {              # key 见 _preflop_allin_decide 档位说明
    "big_lead": 0.75,      # 大幅领先：只跟 AA/KK 级
    "lead": 0.65,          # 小幅领先：TT+、AK 级
    "even": 0.55,          # 均势：77+、AT+、KQ 级
    "behind": 0.50,        # 小幅落后：任何对子、A/K 高张
    "big_behind": 0.40,    # 大幅落后：放宽到任何有潜力的牌
}
ALLIN_ENDGAME_SHIFT = 0.03  # 终局（剩≤15手）修正：领先更严 / 落后更宽

# ---- 钓鱼下注（对跟注型对手缩小价值注，钓更宽跟注范围）----
# 【优化思路】对「爱跟注的对手」（跟注站/低弃牌率），0.65~0.75 池的大注
# 会把他们吓跑，损失价值。这类对手的特点是不看赔率跟注，小注反而能让
# 他们的垃圾牌/中等牌继续跟——利润 = 更宽的跟注范围 × 小注 > 窄范围 × 大注。
# 但「坚果级（顺子+）」例外：跟注型对手对坚果也照跟，应保持大注榨取。
FISH_FOLD_BB = 0.35        # 对手面对下注弃牌率 < 此值 → 视为跟注型（钓鱼目标）
FISH_BET = 0.45            # 跟注型对手的常规价值下注（常规 0.65 → 0.45）
FISH_BET_WET = 0.50        # 湿润面（仍需一定保护，但跟注型不弃小注）
FISH_BET_DRY = 0.38        # 干燥面（求跟，越小越容易钓）
FISH_RAISE = 0.45          # 面对下注加注时对跟注型的克制尺寸（常规 0.75 → 0.45）


# ---- 公对风险规避（弱两对保护）----
RISK_LEAD_CALL_FRAC = 0.50   # 领先时弱两对最多跟注 50% 底池
RISK_ALLIN_EQ_FLOOR = 0.25   # 大幅落后时跟全下的胜率数学底线
RISK_BEHIND_LIMIT = -4000    # 大幅落后阈值（累计净赢）
RISK_HANDS_LEFT = 20         # 落后场景的剩余局数上限

# ---- 河牌公对陷阱（硬性风险规避，不经过数学计算）----
# 【规则】河牌圈：公面≥3个不同点数且无A + 公对存在 + 我方仅一对（对子
# 全部来自公面）+ 踢脚小于 Q → 面对对手全下直接弃牌，不做任何数学计算。
# 【改良】本类牌面下对手任意配对（Q/K/公对牌/口袋对）都是两对或三条，
# Q 踢脚与 K 踢脚几乎无差别——故踢脚 < A 时面对全下要么硬弃（<Q）要么
# 以极高门槛决策（Q/K 踢脚），只有 A 踢脚的裸公对才允许正常数学决策。
RIVER_TRAP_KICKER = 12        # 踢脚 < Q → 硬弃（用户规则，不计算）
RIVER_TRAP_WARN_KICKER = 14   # 踢脚 < A → warning（Q/K 踢脚，高门槛）
RIVER_TRAP_WARN_MARGIN = 0.15 # warning 档跟全下所需的额外胜率门槛

# ---- 全下下限（盈利门槛）----
# 【规则】只有「投入筹码量 > 当前总盈利 + ALLIN_FLOOR_CONST」时才允许
# 跟全下或主动全下；其余情况一律不 allin（跟全下→弃，主动全下→过牌）。
# 效果：盈利越高允许全下的筹码门槛越高（领先保护），落后时门槛为负
# 几乎不限（搏翻盘）。与锁胜弃牌互补：锁胜管「领先到稳赢」，本规则管
# 「领先但未锁胜时的全下保护」。
ALLIN_FLOOR_CONST = 1000      # 全下下限常数（筹码）：投入须 > 总盈利 + 此值

# ---- 优势锁定（LEAD_LOCK）：领先较大时硬性保守 ----
# 【规则】优势（累计盈利差）> LEAD_NO_ALLIN 时：①无论如何不 allin；
# ②单次下注/加注的注码 ≤ LEAD_MAX_BET。领先时只用小注慢慢积累，
# 避免大注送筹码（用户规则，优先级最高——decide 入口即生效）。
LEAD_NO_ALLIN = 2000         # 优势阈值：超过则进入锁定模式
LEAD_MAX_BET = 1000          # 锁定模式下单次注码上限（10BB）

# ---- 总注额上限（用户规则 2026-08-23，取代原增量限制）----
# 原「加注增量 ≤1000」已删除（与总注额 2000 上限冲突），统一为：
#   - 翻前：非超强牌总注额 ≤ PREFLOP_MAX_BET(1000)；超强牌/次强牌(仅落后)
#     可超，但全部 ≤ HIGH_BET_LIMIT(2000)；
#   - 翻后：总注额 ≤ HIGH_BET_LIMIT(2000)，牌面≥三条或抢锁赢(steal)可超。
#   - 单次下注金额（含 allin）以 HIGH_BET_LIMIT 为封顶（例外见
#     _allin_high_bet_allowed），不再有独立的「增量」限制。

# ---- 翻牌前总注额上限（用户规则）----
# 翻牌前下注超过 1000 仅限超强牌（AA/KK/QQ/JJ/AKs）；其他牌翻前
# 总注额不允许超过 PREFLOP_MAX_BET（在 _normalize 统一执行，
# 超强牌可超 1000 但仍受 HIGH_BET_LIMIT(2000) 封顶；次强牌仅落后时豁免）。
PREFLOP_MAX_BET = 1000       # 翻牌前非超强牌总注额上限（10BB）

# ---- 翻后大注牌型门槛（用户规则）----
# 只有牌型 ≥ 三条（THREE_OF_A_KIND）才能下注/加注总注额超过
# HIGH_BET_LIMIT；两对及以下（高牌/一对/两对）总注额上限 2000
#（在 _normalize 统一执行，翻前不受此规则约束——翻前已有
# PREFLOP_MAX_BET 非超强牌 1000 上限，超强牌翻前按增量上限走）。
HIGH_BET_LIMIT = 2000         # 翻后大注总注额上限（20BB）
HIGH_BET_MIN_CAT = THREE_OF_A_KIND  # 允许超限的最低牌型（三条）

# ---- 弃牌亏损线（用户规则）----
# 若本手弃牌会让累计亏损跌破 DESPAIR_ALLIN_LIMIT（弃牌后
# total_win_chips[我方] - 本局已投入 < -3000）→ 无条件全下：
# 弃牌即已无退路，不如全下搏翻盘（深亏时全下反而有最高期望）。
DESPAIR_ALLIN_LIMIT = -3000   # 弃牌后累计亏损超过此值 → 无条件 allin

# ---- 对手突袭大注（单次加注增量 > 此前对手本手总投入的 N 倍）----
# 【规则】当对手一次加注的增量 > 对手之前本手累计投入的 OPP_JUMP_RATIO 倍
# 时，判定为「突袭大注」——往往代表对手强牌（两对+/听牌/全下前奏），
# 慎重量考：跟全下/大注时收紧对手范围估计、抬跟注门槛。
OPP_JUMP_THRESHOLD = 2000      # 对手本手累计已下注超过此值 → 跟注警告（用户规则，无4倍条件）
OPP_JUMP_FAC_MARGIN = 0.10       # 检测到突袭大注时，跟全下阈值额外抬高量
OPP_JUMP_EQ_PENALTY = 0.15     # 突袭大注时 eq 打折（对手范围收紧，顶对级牌力被高估）

# ---- 延迟施压（delayed aggression）----
# 【规则】双方持续过牌后突然加注：对手对「过牌后突然出手」的弃牌率显著
# 高于平均（认为我方有强牌才敢动），故折算为额外 fold_eq 加成。
DELAYED_BONUS_FULL = 0.20      # 当前街双方都 check 过：完整加成（河牌威胁最大）
DELAYED_BONUS_PARTIAL = 0.10   # 上一街双方都 check，当前街我方首次行动（转牌突然出手）
OPP_CHECK_BONUS = 0.30       # 对手最近连续过牌≥2次 → 直接加注（用户规则，优先级最高）
# 【用户规则】对手过牌后立刻加小注：对手本轮 check 过 → 弱牌/听牌/空气
# 不再被动过牌，立刻下小注施压（对手过牌=示弱，小注即可拿下底池）。
OPP_CHECK_BET = 0.40          # 对手 check 后立刻下注（底池比例）

# ---- 规则1：对手锁胜时的激进调整（最高优先级）----
# 【规则】对手最近20局弃牌率>65% 且 全下频率<10%（match_ctx.opponent_locking）
# → 判定对手明显收紧（疑似锁胜），主动偷盲追分：
#   BTN 任意两张牌 2.5BB 开池（100% 频率）→ 翻后 C-Bet 85% 频率、50~60% 池
#   → 被加注/全下立即弃牌不纠缠。本规则触发时不受规则2/规则3 限制。
STEAL_OPEN_BB = 2.5           # 偷盲开池尺寸（2.5BB）
STEAL_CBET_FRAC = 0.55        # 偷盲档 C-Bet 下注额（底池 55%，落在 50%~60% 区间）
STEAL_FOLD_MIN_CAT = 4        # 被加注/全下时唯一例外：顺子及以上（STRAIGHT=4）仍正常决策

# ---- 规则2：盈利锁胜全下（第二优先级）----
# 【规则】当前累计总盈亏 > 0 且 本局已累计下注（含当前轮）> 总盈亏 + 2000
# 且 手牌对抗随机牌胜率 > 30% → 立即全下锁胜，防止利润回吐。
# 与 LEAD_LOCK 关系（用户确认）：LEAD_LOCK 优先——领先>2000 时注码受限，
# 不可能出现「已投 > 盈利+2000」的深投入场景，本规则自然不触发。
PROFIT_LOCK_CONST = 2000      # 已投须超过 总盈亏 + 此值
PROFIT_LOCK_EQ = 0.30         # 对抗随机牌的胜率底线（防纯垃圾牌推）

# ---- 规则3：下注额限制（第三优先级）----
# 【规则】手牌不属于超强牌（AA/KK/QQ/JJ/AKs）时，主动下注/加注的总注额
# > 1000 → 自动降级：底池≤2000 下注底池 50%；否则过牌/跟注。
# 仅在规则1（偷盲档）与规则2 均未触发时生效。
BET_CAP = 1000                # 非超强牌主动下注总注额上限
BET_CAP_POT = 2000            # 底池超过此值时完全放弃主动下注（过牌/跟注）
BET_CAP_FRAC = 0.50           # 降级后的下注额（底池 50%）

# ---- 必须赢下（MUST-WIN）：本次下注落败即致对手锁胜 → 无条件全下 ----
# 【用户规则】牌面有利于自己（两对+非弱两对，或胜率≥MUSTWIN_EQ）且
# 本次下注（跟注额 或 0.65 池的主动注）后若落败将导致对手锁胜：
#   落败后 lead_new = lead - 2×本手投入（我 -2倍投入，对手 +同额，差 -2倍）；
#   对手锁胜需 对手领先 > 1.5×大盲×(剩余手数-1)（与 _fold_out_active 同口径）
#   ⇒ 当 2×投入后 > 我方领先 + 2.5×大盲×(剩余手数-1) 时，本手即生死局。
# → 无条件全下：输了反正对手锁胜，赢面大就该全力搏——allin 兼具弃牌权益
#   与最大价值（若对手弃牌则直接赢下底池）。优先级高于规则2 与 LEAD_LOCK
#   的注码限制（这些场景下保守小注与全下面对同样的失败后果）；
# ---------------- 对外入口 ----------------
_CTX = None  # 当前请求的赛制上下文（MatchContext，由 decide 入口设置）
_OPP_JUMPED = False  # 当前手牌对手是否「突袭大注」（decide 入口设置）
_LEAD_LOCK = False    # 优势锁定模式：领先>LEAD_NO_ALLIN 时不 allin、注码≤LEAD_MAX_BET


def _opp_bet_jumped(state):
    """对手「突袭大注」检测：最近一次主动加注的增量 > 对手之前本手累计投入的
    OPP_JUMP_RATIO 倍。

    【业务逻辑】对手若一直小跟（例累计 1100），突然 raise 8000（增量 6900
    > 4×1100=4400）→ 这种「突袭」往往是强牌信号（两对+、听牌/半诈唬/全下
    前奏），收紧跟注门槛；正常节奏的下注（增量与之前累计相当或更小）不触发。

    重放 state.request["history"]：按轮跟踪双方已投（raise-to 语义），
    累计对手本手全部投入（call 也算），计算最近一次主动加注的增量。
    """
    request = getattr(state, "request", None) or {}
    hist = request.get("history") or []
    opp = state.opp_id
    opp_cum = 0          # 对手本手累计投入（call+raise 增量之和）
    cur_round = None
    rb = {0: 0, 1: 0}    # 本轮双方已投（按轮重置）
    for r in hist:
        rnd = int(r.get("round", 0))
        if rnd != cur_round:
            cur_round = rnd
            rb = {0: 0, 1: 0}
        p = r.get("player_id")
        if p not in (0, 1):
            continue
        at = r.get("action_type", "")
        a = r.get("action", 0)
        is_raise = at in ("raise", "allin") or (
            isinstance(a, int) and not isinstance(a, bool) and a > 0)
        if is_raise:
            incr = int(a) - rb[p]      # raise-to：a=该轮总注额 → 增量
            if incr < 0:
                incr = 0
            rb[p] = int(a)
            if p == opp:
                opp_cum += incr
        elif at == "call":
            cur_max = max(rb.values())
            incr = cur_max - rb[p]     # 跟平到当前最大注
            if incr < 0:
                incr = 0
            rb[p] = cur_max
            if p == opp:
                opp_cum += incr
        # check/fold/allin(金额未知) 不累计
    # 【用户规则】跟注警告：对方已下注 > OPP_JUMP_THRESHOLD(2000) 即触发，
    # 不设置 4 倍增量条件——对手累计投入超过 2000 后，跟注需慎重。
    return opp_cum > OPP_JUMP_THRESHOLD


def _allin_floor_guard(state, action):
    """全下下限（盈利门槛）——用户规则的最后一道闸。

    【业务逻辑】只有「累计投入 > 当前总盈利 + ALLIN_FLOOR_CONST」才
    允许跟全下或主动全下：
      - 跟全下：累计投入 = 已投（INIT - my_chips）+ 跟注额
                = INIT - (my_chips - min(my_left, to_call))
      - 主动全下：invest = my_left（我方主动把剩余全下，新投量）
    门槛 = total_win_chips[我方] + 1000：盈利越高门槛越高（领先
    保护，防止「小优势 allin 输光」）；落后时门槛为负 → 几乎不限
    （搏翻盘）。
    【第 19 手修正】用「累计投入」而非只算本次新投——我方已大量投入
    后（小底池 or 大底池），即便剩余 to_call 不大，累计也远超门槛，
    应允许继续跟全下榨价值。
    不满足时：跟全下 → 弃牌；主动全下 → 过牌（能过则过，否则弃）。
    """
    if action.get("act") != "allin":
        return action
    # 【优势锁定】领先>LEAD_NO_ALLIN：无论如何不 allin（最高优先级硬规则）
    if _LEAD_LOCK:
        if state.to_call <= 0:
            return {"act": "check"}
        return {"act": "fold"}
    try:
        from game_state import INIT_CHIPS
        floor = state.total_win_chips[state.my_id] + ALLIN_FLOOR_CONST
        if state.to_call > 0:
            # 跟全下：累计投入 = 已投 + 跟注额（受 my_left 约束）
            invest = INIT_CHIPS - (state.my_chips - min(state.my_left, state.to_call))
        else:
            # 主动全下：我方主动投入 = my_left
            invest = state.my_left
        if invest > floor:
            return action          # 累计投入超门槛 → 允许全下
    except Exception:
        return action              # 状态异常时不额外拦截
    # 被锁：能过牌就过牌（不主动 allin），否则弃牌
    if state.to_call <= 0:
        return {"act": "check"}
    return {"act": "fold"}


# ---------------- 规则2/规则3（用户规则，优先级 2/3） ----------------
def _is_super_hand(hole):
    """超强牌（最严格版，用户规则 2026-08-23）：AA/KK/QQ/JJ（对子点数≥J=11）
    或 AKs（同花 AK）。唯一获得翻前 1000 上限豁免的牌（可超 1000 但 ≤2000）。
    """
    r = sorted(c // 4 for c in hole)
    hi, lo = r[1], r[0]
    if hi == lo and hi >= 11:            # JJ+（口袋对 J 及以上）
        return True
    suited = (hole[0] % 4) == (hole[1] % 4)
    return hi == 14 and lo == 13 and suited   # AKs（同花 AK）


def _is_sub_strong(hole):
    """次强牌：AQ/AK/KQ（含同花与不同花；AKo 属次强，AKs 是超强）。
    仅大幅落后（desperate/doomed）时豁免翻前 1000 上限（用户规则），
    其余时段与普通牌一样受 PREFLOP_MAX_BET 约束。
    """
    r = sorted(c // 4 for c in hole)
    hi, lo = r[1], r[0]
    if hi == lo and hi >= 11:
        return False                      # 超强对子不在此列
    suited = (hole[0] % 4) == (hole[1] % 4)
    if hi == 14 and lo == 13 and suited:
        return False                      # AKs 是超强牌
    if hi == 14 and lo >= 12:             # AQ / AK（含 AQs/AQo/AKo）
        return True
    return hi == 13 and lo == 12          # KQ（含 KQs/KQo）


def _profit_lock_allin(state):
    """规则2：盈利锁胜全下检查。

    【业务逻辑】当前累计总盈亏 > 0（盈利状态）且本局已累计下注金额（含
    盲注与当前轮，= INIT_CHIPS - my_chips）> 总盈亏 + 2000，且手牌对抗
    随机牌胜率 > 30%（防纯垃圾牌推）→ 立即全下锁胜，防止利润回吐
    （投入已深、牌力有底线，直接推掉避免后街被对手反超）。
    与 LEAD_LOCK 关系（用户确认）：LEAD_LOCK 优先——领先>2000 时注码
    受限（≤1000），不可能出现「已投 > 盈利+2000」的深投入场景，
    故本函数只在 LEAD_LOCK 未触发时被调用。
    """
    try:
        from game_state import INIT_CHIPS
        pnl = state.total_win_chips[state.my_id]
        if pnl <= 0:
            return False
        invested = INIT_CHIPS - state.my_chips   # 本局已累计投入（含当前轮）
        if invested <= pnl + PROFIT_LOCK_CONST:
            return False
        # 胜率底线：对抗随机牌（opp_range_pct=1.0）快速蒙特卡洛
        eq = monte_carlo_equity(state.hole, state.board, iterations=600,
                                opp_range_pct=1.0,
                                deadline=time.time() + 0.25)
        return eq > PROFIT_LOCK_EQ
    except Exception:
        return False


def _allin_high_bet_allowed(state):
    """allin 金额超过 HIGH_BET_LIMIT(2000) 是否允许（用户规则例外集）。

    【业务逻辑】「只有 ≥ 三条的牌型才投入超过 2000」——allin 也是投入，
    金额 = 我方剩余筹码。允许超 2000 的唯一例外：
      1. 本局输即对手锁胜（doomed：弃牌=认输，必须全下搏，第一优先级）；
      2. 翻后有效牌型 ≥ 三条（经 _effective_category 净化——纯公共牌拼的
         三条/顺子/同花/葫芦/四条/同花顺降级为高牌，不豁免）。
    【2026-08-23 严格化】steal（抢锁赢偷盲）不再是例外：>2000 限制
    处于第二优先级，仅 doomed（防锁赢 allin）可豁免。其余场景一律 ≤2000。
    """
    try:
        adj = _match_adjust(state)
        if adj == "doomed":
            return True
        if state.stage != "preflop" and \
                _effective_category(state) >= HIGH_BET_MIN_CAT:
            return True
    except Exception:
        pass
    return False


def _bet_cap_guard(state, action):
    """规则3：下注额限制（第三优先级）。

    【业务逻辑】手牌不属于超强牌（AA/KK/QQ/JJ/AKs）时，主动下注/加注的
    总注额 > BET_CAP(1000) → 自动降级：
      - 底池 ≤ 2000 → 只下注底池 50%（BET_CAP_FRAC）；
      - 底池 > 2000 → 放弃主动下注（能跟就跟、否则过牌）。
    目的：避免边缘牌投入过多筹码（用户规则）。仅在规则1（偷盲档）与
    规则2 均未触发时生效。
    """
    if action.get("act") != "raise":
        return action
    if state.stage == "preflop":
        # 翻前总注额限制由 _normalize 统一执行（超强牌豁免 + min_raise 边界
        # 与降级逻辑集中一处，避免此处 _bet_fraction 在翻前产生歧义）
        return action
    if _is_super_hand(state.hole):
        return action
    # 【用户规则】牌型 ≥ 三条（顺子/同花/葫芦/四条/同花顺）同样豁免：
    # 只有牌型 ≥ 三条才能下注超过 HIGH_BET_LIMIT(2000)，故此类牌力
    # 不受本规则 1000 上限约束（由 _normalize 的牌型门槛放行/压限）。
    # 注：经 _effective_category 净化——公共牌拼的强牌型不豁免。
    if _effective_category(state) >= HIGH_BET_MIN_CAT:
        return action
    num = int(action.get("num", 0))
    if num <= BET_CAP:
        return action
    # 降级：底池 ≤ 2000 → 下注底池 50%；否则过牌/跟注
    if state.pot <= BET_CAP_POT:
        return _bet_fraction(state, BET_CAP_FRAC)
    if state.to_call > 0:
        return {"act": "call"}
    return {"act": "check"}


def decide(state, model, ctx=None):
    """根据当前状态与对手模型返回动作 dict（经 _normalize 合法化）。

    ctx: 可选 MatchContext（bot 层从 globaldata 恢复）。三个赛制模块
    （对手弃牌推断/激进等级/回撤保护）通过它只调整状态机阈值偏移。
    """
    global _CTX, _OPP_JUMPED, _LEAD_LOCK
    _CTX = ctx
    # 【对手突袭大注】全局标志：翻前/翻后所有决策共享（优先级最高——
    # 领先较大时不 allin、面对突袭大注收紧防守，都在决策一开始生效）
    _OPP_JUMPED = _opp_bet_jumped(state)
    # 【优势锁定】领先 > LEAD_NO_ALLIN → 不 allin + 注码≤LEAD_MAX_BET
    # （用户规则，优先级最高：决策一开始就进入锁定模式）
    try:
        _LEAD_LOCK = (state.total_win_chips[state.my_id]
                      - state.total_win_chips[state.opp_id]) > LEAD_NO_ALLIN
    except Exception:
        _LEAD_LOCK = False
    # 【用户规则·最高优先级】对手将要锁赢（doomed：本局失败后对手即可
    # 用剩余手数全程弃牌锁胜）→ 无条件全下，置于所有其他限制之上：
    # 不查 2000 上限、不查牌型≥三条、不查公对陷阱/公对风险、不看牌力——
    # 弃牌=直接认输，任何其他动作都拖慢翻盘，必须全下搏。
    # （与锁胜弃牌 fold_out 互斥：doomed 是大幅落后，fold_out 是大幅领先）
    if _match_adjust(state) == "doomed":
        return {"act": "allin"}
    # 锁胜弃牌：领先足够大时直接弃牌拖到终局（零方差锁定胜局）
    if _fold_out_active(state):
        return {"act": "fold"}
    # 【规则2】盈利锁胜全下（第二优先级）：LEAD_LOCK 优先——未锁定时，
    # 盈利且本局已投 > 盈利+2000 且牌力≥30% → 直接全下锁胜（用户规则）
    if not _LEAD_LOCK and _profit_lock_allin(state):
        return {"act": "allin"}

    # 公对风险规避：弱两对走保守路线（规则3 与累计盈亏联动）
    if should_avoid_risk(state):
        action = _risk_avoid_route(state, model)
    elif state.stage == "preflop":
        action = _preflop_decide(state, model)
    else:
        action = _postflop_decide(state, model)
    # 全下下限：投入须超过「当前总盈利 + 1000」才允许 allin（用户规则）
    action = _allin_floor_guard(state, action)
    # 【规则3】下注额限制（第三优先级）：规则1（偷盲档）触发时不生效——
    # 偷盲 C-Bet 允许超过 1000（对手弃牌率高，高频 C-Bet 是主动收益策略）
    if _match_adjust(state) != "steal":
        action = _bet_cap_guard(state, action)
    return _normalize(state, action)


# ================================================================
#  公对风险规避（弱两对保护）
# ================================================================
def _find_board_pair(board):
    """返回公共牌面最大公对点数（无对返回 0）。"""
    counts = {}
    for c in board:
        r = c // 4
        counts[r] = counts.get(r, 0) + 1
    for r in range(14, 1, -1):
        if counts.get(r, 0) >= 2:
            return r
    return 0


def should_avoid_risk(state):
    """
    公对风险规避前置检查：公共牌有对子且我的手牌构成「底部两对」时
    返回 True，提示本手应走保守路线。

    【业务说明（供算法文档）】
    规则1 公对风险识别：公对面上（如 Q-8-2-8），若我的两对中「较小的一对」
      由手牌配对公共牌单张构成（如手牌 2-7 → 2 与公 2 配成 22），这是经典的
      底部两对（bottom two pair）——对手任意一张 8/Q 配对即成三条或更高两对，
      我的牌实际处于被统治地位。顶两对（手牌配成高对）不在此列。
    规则2 踢脚被压制：两对中高对是公对（我手里没有公对牌），且我的踢脚
      （第五张牌）小于公共牌面存在的任何高张（Q/K/A）→ 标记「弱两对」。
    规则3 见 _risk_avoid_route（与累计盈亏联动）。
    """
    board = state.board
    if len(board) < 3 or len(board) >= 5:
        return False                      # 只有翻牌/转牌（3~4 张）才可能判定公对
    pair_rank = _find_board_pair(board)   # 规则1：公对点数
    if pair_rank == 0:
        return False
    hr = sorted((c // 4 for c in state.hole), reverse=True)
    # 手牌配成的对：手牌某张 = 公共牌非公对点数（构成两对中的「手牌对」）
    board_other = [c // 4 for c in board if c // 4 != pair_rank]
    hand_pair = None
    for h in hr:
        if h in board_other:
            hand_pair = h
            break
    if hand_pair is None:
        return False                      # 没有第二对 → 不是两对结构
    if hand_pair >= pair_rank:
        return False                      # 手牌对 ≥ 公对 = 顶两对（强牌，不触发）
    # 规则2：踢脚 = 我手牌中除配对牌外最大的一张（反映我的真实牌力；
    # 公共牌高张双方都能用，真正威胁是「对手更高两对/三条」）。
    # 若我的踢脚小于公面高张（Q/K/A），说明极易被更高两对统治 → 弱两对
    hand_kickers = [r for r in hr if r != hand_pair]
    kicker = max(hand_kickers, default=0)
    high_board = max(board_other, default=0)   # 公面可能压制踢脚的高张（Q/K/A）
    if kicker < high_board:
        return True                       # 弱两对：踢脚被压制
    return False


def _effective_category(state):
    """有效牌型等级（用户规则 2026-08-23）：纯公共牌组成的牌型降级。

    公共牌自身已构成三条/顺子/同花/葫芦/四条/同花顺（5 张公共牌全用上、
    未用到任何一张手牌）时，对手必然同样拥有该牌型（最多平分），且对手仅需
    一张升级牌即可击败我们：
      - board 三条（K K K 9 7）→ 对手有 K 即四条，有 9 即葫芦；
      - board 顺子（9 8 7 6 5）→ 对手有 T 即更高顺子；
      - board 同花 → 对手有同花牌即更高踢脚；
      - board 葫芦/四条 → 对手有对应牌即升级。
    这种「假强牌」不能作为个人牌力 → 降级为 HIGH_CARD 处理，避免据此
    价值下注 / 超池 / 跟大注 / 豁免注额上限 / 豁免河牌公对弃牌。

    仅当 5 张公共牌且最强牌型 ≥ 三条时检查（翻牌/转牌阶段 3~4 张公共牌
    组合必然用到手牌，无需净化）。
    """
    if len(state.board) != 5:
        return evaluate_7(state.hole + state.board)[0]
    full = evaluate_7(state.hole + state.board)
    if full[0] < THREE_OF_A_KIND:
        return full[0]                    # 只有「≥ 三条」才需要检查（纯公共牌降级）
    if full == evaluate_7(state.board):
        return HIGH_CARD                  # 最强 5 张全为公共牌 → 假强牌
    return full[0]


def _river_paired_trap(state):
    """【合并规则 2026-08-23】河牌圈公对存在 + 我方非(葫芦/三条/较大对≥Q 的
    顶两对) → 面对对手全下直接弃牌（结构性风险，不做数学计算）。

    合并了原「河牌裸公对硬弃」与「领先弱两对弃牌」两条规则：
      - 豁免：葫芦/四条/同花顺（FULL_HOUSE+）、三条、两对且较大对 ≥ Q(12)
        （Q 高顶两对是强牌，可继续对抗）；
      - 其余（裸公对一对/低两对/公对+踢脚等）遇对手全下 → 弃牌。
    第 49 手（K♣8♥ 对公对9+公面Q）即命中：一对且非豁免 → 弃。
    """
    if state.current_round < 3 or len(state.board) != 5:
        return False                      # 仅河牌圈
    rc = {}
    for r in (c // 4 for c in state.board):
        rc[r] = rc.get(r, 0) + 1
    if max(rc.values()) < 2:
        return False                      # 无公对
    eff = _effective_category(state)      # 净化：公共牌拼的强牌型降级为高牌
    if eff >= THREE_OF_A_KIND:
        return False                      # 真强牌（三条/顺子/同花/葫芦等）→ 豁免
    e = evaluate_7(state.hole + state.board)
    cat = e[0]
    if cat == TWO_PAIR and e[1] >= 12:    # 较大对 ≥ Q → 顶两对豁免（两对不受净化影响）
        return False
    return True


def _risk_avoid_route(state, model):
    """
    公对弱两对的保守路线（规则3：与累计盈亏联动）。
    领先时保护筹码、落后时按数学底线拼、中间档降级为普通一对评估。
    """
    pnl = state.total_win_chips[state.my_id]
    hands_left = state.max_hand - state.hand_num
    to_call = state.to_call

    if pnl > 0:
        # 领先状态：屏蔽 allin/raise，仅过牌或跟注小注（≤50% 底池）；
        # 对手全下 → 直接弃牌（弱两对没必要拿领先去赌）
        if to_call <= 0:
            return {"act": "check"}
        if state.opp_is_allin or to_call >= state.my_left:
            return {"act": "fold"}
        if to_call <= RISK_LEAD_CALL_FRAC * state.pot:
            return {"act": "call"}
        return {"act": "fold"}

    if pnl < RISK_BEHIND_LIMIT and hands_left < RISK_HANDS_LEFT:
        # 大幅落后且剩余局数少：允许跟全下，但胜率必须 > 25%（纯数学底线）
        eq = monte_carlo_equity(
            state.hole, state.board, iterations=MC_ITERATIONS,
            opp_range_pct=_opp_range_pct(model, _opp_raised_preflop(state)),
            deadline=time.time() + TIME_BUDGET)
        if to_call <= 0:
            return {"act": "check"}
        if eq > RISK_ALLIN_EQ_FLOOR:
            return {"act": "call"}
        return {"act": "fold"}

    # 正常/小幅落后（0 ~ -4000）：按「普通一对」评估 ——
    # 走正常路径，但 _postflop_decide 的 strong 判定已排除弱两对，
    # 该手最多按 good/medium 处理，不会因「两对」触发全下/大注
    if state.stage == "preflop":
        return _preflop_decide(state, model)
    return _postflop_decide(state, model)


def _fold_out_active(state):
    """
    锁胜弃牌（fold-out）判定：领先优势能否靠全程弃牌保证最终获胜。

    【数学推导】比赛按 total_win_chips（累计净赢）定胜负，盲注 50/100：
      - 我 SB 弃牌：我净 -50，对手净 +50 → 领先差 -100
      - 我 BB 弃牌：我净 -100，对手净 +100 → 领先差 -200
      即每手弃牌最多消耗 2×大盲 的领先优势（BB 弃牌时）。
    剩余 R 手 → 最坏消耗 2×大盲×R。
    当 领先 > 2.5×大盲×R（2.5 倍余量覆盖盲注估计偏差/平局判负等边界）
    时，全程弃牌后领先仍为正 → 稳赢。此模式自动只会在后期大领先时触发。
    """
    try:
        lead = (state.total_win_chips[state.my_id]
                - state.total_win_chips[state.opp_id])
        hands_left = state.max_hand - state.hand_num
        return lead > 1.5 * state.big_blind * hands_left
    except Exception:
        return False


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------- 对局状态调整（风控·宏观层） ----------------
def _match_adjust(state):
    """
    max_hand 手定胜负的比赛中，根据领先量与剩余手数调整风险偏好：
      protect   —— 大幅领先且临近终局：降波动（少诈唬、跟注更严）；
      pressure  —— 领先且对手短码：ICM 压力下放宽全下/加注（对手弃牌率高）；
      desperate —— 大幅落后且临近终局：极限激进追分，阻止对手锁胜；
      doomed    —— 落后到数学上不可追（对手同款锁胜逻辑已成立）：放开一切豪赌；
      steal     —— 对手疑似锁胜（弃牌率飙升）：关闭诈唬、高频小额偷盲；
      normal    —— 常规。

    赛制上下文（match_ctx）只在此处调整阈值：
      - opponent_locking → 直接返回 steal 档；
      - 激进等级 → 对 lead 做 ±LEVEL_SHIFT_BB 偏移（激进=负偏移早追分，
        保守=正偏移早保收益），即「调整触发阈值」而非新增决策路径。
    """
    try:
        hands_left = state.max_hand - state.hand_num
        lead = (state.total_win_chips[state.my_id]
                - state.total_win_chips[state.opp_id])
        bb = state.big_blind

        # 模块一：疑似锁胜 → 偷盲档（关闭诈唬 + 高频小额偷盲）
        if _CTX is not None and _CTX.opponent_locking:
            return "steal"
        # 模块二/三：激进等级 → 阈值偏移（大盲单位）
        if _CTX is not None:
            lead += _CTX.threshold_offset(state) * bb

        # 劣势冲刺（doomed）——随时计算，不设「剩 15 手」闸门：
        # 若本局失败（lead 再降 2×大盲，弃牌级最坏损失）后，对手用剩余
        # hands_left-1 手全程弃牌即可锁胜（对手每手弃牌净赚 2×大盲领先差，
        # 2.5 倍余量兜底），则立即转入「放开一切豪赌」的冲刺模式。
        # 数学上比「最后十几把」的拍脑袋闸门更早、更准——只要对手锁胜
        # 条件在本局失败后成立，就该放弃稳健、全力搏翻盘。
        if lead - 2 * bb <= -1.5 * bb * max(hands_left - 1, 1):
            return "doomed"

        if hands_left <= 15:
            if lead >= 30 * bb and state.opp_chips <= 0.7 * state.my_chips:
                return "pressure"
            if lead >= 30 * bb:
                return "protect"
            if lead <= -30 * bb:
                return "desperate"
    except Exception:
        pass
    return "normal"


# ================================================================
#  翻牌前：百分位范围决策
# ================================================================
def _preflop_allin_decide(state, model):
    """翻前对手全下（或需跟注额 ≥ 我方筹码，跟注即全下）时的独立决策。

    【业务逻辑——按用户方案三要素 + 第四步防反向剥削】
      第一步 胜率：我方手牌 vs 对手「all-in 范围」的胜率。
             对手敢全下说明牌力更强，范围比随机牌紧（按对手原型收紧：
             岩石 all-in≈AA/KK 级，疯子≈宽范围），比固定映射更准。
      第二步 必要胜率：跟注额 / (跟注后总底池)，跟注额 = min(我方筹码, 对手下注量)。
      第三步 按累计盈亏分档（核心）：盈利越多跟注门槛越高（保收益），
             落后越多门槛越低（搏翻盘）——避免「优势下跟 all-in 比运气」。
      第四步 极端赔率优先（防反向剥削）：eq ≥ 必要+10% 无条件跟、
             eq ≤ 必要-10% 无条件弃，中间地带才由第三步分档决定——
             防对手用「极小全下白嫖领先者」（好赔率不能弃）、
             或「超大全下诱杀落后者」（差赔率不能接）。
    注：有人全下后平台规则只允许 -1/-2，本函数只返回 fold / allin。
    """
    # ---- 第一步：胜率（对手 all-in 范围收紧）----
    arch = model.archetype()
    base_rp = _opp_range_pct(model, True)      # 对手翻前主动加注的基准范围
    factor = {"maniac": 0.90, "station": 0.70, "tag": 0.60, "rock": 0.35}.get(arch, 0.60)
    rp = _clamp(base_rp * factor, 0.02, 1.0)   # all-in 宣告 → 范围再收紧
    eq = monte_carlo_equity(
        state.hole, [], iterations=ALLIN_MC, opp_range_pct=rp,
        deadline=time.time() + ALLIN_TIME_BUDGET)

    # ---- 第二步：必要胜率（底池赔率）----
    call_amt = min(state.my_left, state.to_call)
    total_pot = state.pot + call_amt
    required = call_amt / total_pot if total_pot > 0 else 1.0

    # ---- 第四步：极端赔率优先（防反向剥削）----
    if eq >= required + ALLIN_BAND_PCT:
        return {"act": "allin"}    # 赔率极好：任何状态都跟（弃掉才是 -EV）
    if eq <= required - ALLIN_BAND_PCT:
        return {"act": "fold"}     # 赔率极差：任何状态都不接

    # ---- 第三步：按累计盈亏分档（核心）----
    lead = (state.total_win_chips[state.my_id]
            - state.total_win_chips[state.opp_id])
    bb = state.big_blind
    big_bb = ALLIN_LEAD_BB * bb      # 50BB = +5000
    small_bb = ALLIN_SMALL_BB * bb   # 10BB = +1000
    if lead > big_bb:
        thr = ALLIN_THR["big_lead"]       # 大幅领先：只跟 AA/KK 级
    elif lead > small_bb:
        thr = ALLIN_THR["lead"]           # 小幅领先：TT+、AK 级
    elif lead > -small_bb:
        thr = ALLIN_THR["even"]           # 均势：77+、AT+、KQ 级
    elif lead > -big_bb:
        thr = ALLIN_THR["behind"]         # 小幅落后：任何对子、A/K 高张
    else:
        thr = ALLIN_THR["big_behind"]     # 大幅落后：放宽到任何有潜力的牌

    # 终局修正：剩 ≤15 手时，领先保护更严、落后搏命更凶（对手没时间翻盘）
    hands_left = state.max_hand - state.hand_num
    if hands_left <= 15:
        thr = thr + ALLIN_ENDGAME_SHIFT if lead > 0 else thr - ALLIN_ENDGAME_SHIFT

    # 【突袭大注】对手翻前突然大幅加注（增量 > 4×此前累计）→ 范围收紧，
    # 跟全下阈值抬高（与翻后 jumped 同款保护）
    if _OPP_JUMPED:
        thr = min(0.90, thr + OPP_JUMP_FAC_MARGIN)

    # 领先者至少要过赔率底线（防止 -EV 的接注）；落后者允许 -EV 搏翻盘
    if lead > 0:
        thr = max(thr, required)

    if eq >= thr:
        return {"act": "allin"}
    return {"act": "fold"}


def _preflop_decide(state, model):
    pct = hand_percentile(state.hole)   # 起手牌百分位（越小越强）
    arch = model.archetype()
    adj = _match_adjust(state)

    # 翻前对手全下 / 跟注即全下：走「累计盈亏动态分档」专用决策
    # （原逻辑只按底池赔率 + protect 减 5%，缺少「领先收紧到 75%+」的硬保护，
    #   这正是「优势下也跟 all-in 比运气」的直接来源）
    if state.opp_is_allin or state.to_call >= state.my_left:
        return _preflop_allin_decide(state, model)

    if state.is_button:
        if state.to_call <= state.blind:      # 面对大盲（含无人加注）
            return _button_open(state, model, pct, arch, adj)
        return _button_vs_3bet(state, model, pct, arch, adj)
    else:
        if state.to_call <= 0:                # 庄家溜入，我有选项
            return _bb_option(state, model, pct, arch, adj)
        return _bb_defend(state, model, pct, arch, adj)


def _button_open(state, model, pct, arch, adj):
    """庄家位开池：范围随对手原型伸缩；开池尺寸学习优先。"""
    # 偷盲档：对手疑似锁胜 → 任意两张牌 2.5BB 开池，频率 100%（规则1）
    if adj == "steal":
        return _raise_to(state, STEAL_OPEN_BB * state.big_blind)
    # 【学习优先】对手对翻前下注的反应数据充分时，选「弃牌率最低」的开池
    # 尺寸（实证覆盖原型假设）——比如对手对大注弃牌率远低，说明他爱跟，
    # 用大注开池也能被跟；反之对手对小注弃牌率最低，用小注钓更宽范围。
    lf, learned = _learned_size(model, state, None, is_preflop=True)
    open_pct = BTN_OPEN_PCT
    if arch == "rock":
        open_pct = 0.92     # 岩石不惩罚宽开池 → 更激进偷盲
    elif arch == "station":
        open_pct = 0.85     # 站点翻后乱跟 → 价值牌多打
    elif arch == "maniac":
        open_pct = 0.75     # 疯子爱反加 → 略收紧避免被掀翻
    if adj == "protect":
        open_pct = min(open_pct, 0.85)
    elif adj in ("desperate", "doomed"):
        # 劣势追分：所有牌全开池（含垃圾牌），最大化底池波动博翻盘
        open_pct = 1.0

    if pct <= open_pct:
        if learned:
            # lf 翻前为「大盲倍数」（2.2/3.0/4.0）
            return _raise_to(state, lf * state.big_blind)
        size = OPEN_SIZE_VS_STATION if arch == "station" else OPEN_SIZE_BB
        return _raise_to(state, size * state.big_blind)

    # 垃圾牌：对手极少主动加注时补齐溜入看翻牌；劣势追分时绝不弃庄家位
    limp_max = 1.0 if adj in ("desperate", "doomed") else 0.96
    if pct <= limp_max and (model.eff_pfr() < 0.25 or adj in ("desperate", "doomed")):
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
    elif adj in ("desperate", "doomed"):
        value_pct = min(0.20, value_pct + 0.12)  # 劣势追分：4-bet 价值范围大幅放宽
    if pct <= value_pct:
        return _raise_to(state, SB_4BET_MULT * state.curbet[state.opp_id])

    # 诈唬 4-bet：Axs 阻挡牌，仅在对手有一定弃牌率或 ICM 压力下使用
    opp_fold = model.eff_fold_to_bet()
    if _is_4bet_bluff(state.hole) and (
            opp_fold >= 0.40 or adj in ("pressure", "desperate", "doomed")):
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
    elif adj in ("desperate", "doomed"):
        # 劣势追分：反加注也几乎全接（要翻盘必须先留在局里）
        call_pct = min(0.90, call_pct + 0.30)
    # 【突袭大注】对手突然大幅加注（如 799→5300）→ 跟注所需胜率门槛提高
    # 10%（可量化：跟注范围百分位门槛收紧 0.10，等效胜率要求 +10%）
    if _OPP_JUMPED:
        call_pct = max(0.05, call_pct - 0.10)
    if pct <= call_pct:
        return {"act": "call"}
    return {"act": "fold"}


def _bb_option(state, model, pct, arch, adj):
    """大盲面对溜入：强牌隔离加注，其余免费看牌。"""
    iso_pct = 0.40
    if arch == "station":
        iso_pct = 0.30     # 对站点隔离靠价值范围
    elif arch == "rock":
        iso_pct = 0.55     # 多惩罚岩石的溜入
    if adj == "steal":
        iso_pct = 0.90     # 偷盲档：对手弃牌率高 → 几乎任何牌都隔离抢池
    elif adj in ("desperate", "doomed"):
        iso_pct = 0.80     # 劣势追分：隔离加注范围翻倍（抢底池搏翻盘）
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
    if adj == "steal":
        # 偷盲档：对手弃牌率高 → 不做诈唬性 3-bet，按赔率防守即可
        threebet_pct = 0.0
        defend_pct = max(defend_pct, 0.60)
    else:
        threebet_pct = BB_3BET_PCT
        if model.eff_fold_to_bet() >= 0.50:
            threebet_pct = BB_3BET_BLUFFY
        if arch == "station":
            threebet_pct = 0.10
        if adj in ("desperate", "doomed"):
            threebet_pct = 0.35  # 劣势追分：3-bet 范围大幅加宽（含大量诈唬）
        if adj in ("desperate", "doomed"):
            defend_pct = 1.0   # 劣势追分：任何牌都防守（含垃圾牌），留在局里搏翻盘

    # 【突袭大注】对手突然大幅加注 → 防守所需胜率门槛提高 10%
    # （可量化：防守范围百分位门槛收紧 0.10，等效胜率要求 +10%）
    if _OPP_JUMPED:
        defend_pct = max(0.10, defend_pct - 0.10)

    if pct <= threebet_pct:
        return _raise_to(state, 3.0 * state.curbet[state.opp_id])
    if pct <= defend_pct:
        # 很贵的跟注只防守范围上半区（反向隐含赔率保护）；劣势追分时放弃该保护
        if required > 0.45 and pct > defend_pct * 0.7 and adj not in ("desperate", "doomed"):
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



def _opp_checked_this_round(state):
    """对手本轮（当前街）是否 check 过。重放 state.request.history 检查
    当前 round 的 check 记录（玩家=对手）。

    【业务逻辑】对手 check = 示弱/无强牌 → 我方应立刻下小注施压
    （用户规则：对手过牌后立刻加小注），而不是被动跟 check 拖到下一街。
    """
    request = getattr(state, "request", None) or {}
    hist = request.get("history") or []
    cur_round = state.current_round
    for r in hist:
        if int(r.get("round", 0)) == cur_round and \
                r.get("player_id") == state.opp_id and \
                r.get("action_type") == "check":
            return True
    return False


def _opp_check_bet(state, opp_checked):
    """对手 check 后立刻下小注（用户规则）：min(0.40×底池, 1000)；否则过牌。
    （深底池时 0.40 池可能超 1000，受 PREFLOP/翻后注码上限约束取 min。）"""
    if opp_checked:
        frac = min(OPP_CHECK_BET, 1000.0 / max(state.pot, 1))
        return _bet_fraction(state, frac)
    return {"act": "check"}


def _delayed_aggression_bonus(state):
    """延迟施压加成：双方持续过牌后突然加注的额外弃牌率加成。

    【业务逻辑】用户规则：双方持续过牌时，可以突然无视牌型加注来欺骗对手。
    对手对「过牌后突然出手」的弃牌率显著高于平均，故此场景下诈唬的
    fold_eq 需额外加成：
      - 当前街双方都 check 过 → +DELAYED_BONUS_FULL（0.20，河牌威胁最大）
      - 上一街双方都 check，当前街我方首次行动（转牌突然出手）
        → +DELAYED_BONUS_PARTIAL（0.10）
    返回 fold_eq 加成（0~0.20）。"""
    request = getattr(state, "request", None) or {}
    hist = request.get("history") or []
    cur_round = state.current_round
    if cur_round < 1:
        return 0.0
    opp = state.opp_id
    my = state.my_id

    # 【对手连续过牌≥2 次 → 直接加注】用户规则：对手连续两次过牌就直接加注。
    # 对手连续 check 说明其牌力弱/示弱，此时突然出手弃牌率极高——不要求
    # 我方也过牌（我方下注后对手连续 check 同样适用）。
    streak = 0
    for r in reversed(hist):
        if r.get("player_id") != opp:
            continue
        if r.get("action_type") == "check":
            streak += 1
        else:
            break
    if streak >= 2:
        return OPP_CHECK_BONUS

    def _street_checked(round_no):
        return [r for r in hist if int(r.get("round", 0)) == round_no and r.get("action_type") == "check"]

    # 上一街双方都 check，当前街我方首次行动（典型「翻牌 check-check → 转牌加注」）
    if cur_round >= 2:
        prev = _street_checked(cur_round - 1)
        prev_opp_check = any(r.get("player_id") == opp for r in prev)
        prev_my_check = any(r.get("player_id") == my for r in prev)
        cur_my_acted = any(r.get("player_id") == my for r in hist
                            if int(r.get("round", 0)) == cur_round)
        if prev_opp_check and prev_my_check and not cur_my_acted:
            # 上两街（cur_round-1 和 cur_round-2）都 check-check →
            # 持续三街过牌后突然出手：弃牌率加成更大（FULL）
            if cur_round >= 3:
                prev2 = _street_checked(cur_round - 2)
                if all(any(r.get("player_id") == p for r in prev2) for p in (opp, my)):
                    return DELAYED_BONUS_FULL
            return DELAYED_BONUS_PARTIAL
    return 0.0


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

    category = _effective_category(state)   # 净化：公共牌拼的 >三条 牌型降级为高牌
    outs = _count_outs(state.hole, state.board)

    # ---- 强度分层（牌型 × 胜率 双口径）----
    # 【修复】公对底部两对（should_avoid_risk）即使 category=TWO_PAIR 也
    # 不算 strong——否则会在小优势下全下被对手三条/葫芦/更高两对统治，
    # 这正是「AI 喜欢小优势 allin 输得很惨」的主要根因之一。
    weak_pair = should_avoid_risk(state)
    strong = ((category >= TWO_PAIR and not weak_pair) or eq >= 0.78)   # 两对及以上（非弱两对）/ 压制性胜率
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
def _fold_equity(model, adj):
    """有效弃牌权益（诈唬收益的核心输入），按对局状态打折/加成。"""
    fe = model.eff_fold_to_bet()
    if adj == "protect":
        fe *= 0.5      # 领先保收益：诈唬大幅压缩
    elif adj in ("desperate", "doomed"):
        fe *= 1.6      # 劣势追分：把弃牌权益打到顶（激进诈唬搏翻盘）
    return _clamp(fe, 0.0, 0.9)


def _fishy(model):
    """跟注型对手（钓鱼目标）：跟注站原型，或面对下注弃牌率很低（爱跟）。

    对这类对手，价值注应该用小注「钓」更宽的跟注范围，
    而不是大注把他们吓跑（用户反馈：优势加注太多钓不上鱼）。
    """
    return model.archetype() == "station" or model.eff_fold_to_bet() < FISH_FOLD_BB


def _learned_size(model, state, default_frac, is_preflop=False):
    """对手响应学习的下注尺寸（学习优先于常规打法）。

    【优化思路】对手行为学习模块记录「我下注 X 后对手的反应」（最近 20 手、
    按尺寸分桶）。只要样本 ≥ 3，就用「对手弃牌率最低的桶」的代表尺寸
    覆盖常规策略（原型假设/固定阈值）——实证永远优先于先验猜测。
    翻前返回大盲倍数（2.2/3.0/4.0），翻后返回底池比例（0.35/0.55/0.80）。
    样本不足时返回 (default_frac, False) 回退现有逻辑。
    """
    res = model.learned_value_bucket(is_preflop, cur_hand=state.hand_num)
    if res is None:
        return default_frac, False
    bucket, _ = res
    return OpponentModel.bucket_to_frac(bucket), True


def _check_side(state, model, eq, category, strong, good, medium, big_draw,
                draw, tex, arch, adj, is_river, i_aggressor):
    """主动下注侧：价值 / 诱敌深入 / 保护 / 半诈唬 / 纯诈唬（EV 门控+阻挡牌）。"""
    fold_eq = _fold_equity(model, adj)
    spr = state.effective_stack / max(state.pot, 1)
    # 有利位置 + 翻前主动方 = 标准 C-Bet 场景，诈唬门槛下调
    cbet_spot = i_aggressor and state.is_button
    # 【用户规则】对手本轮 check 过 → 立刻小注（弱牌不再被动过牌）
    opp_checked = _opp_checked_this_round(state)

    # 【规则1】偷盲档（对手锁胜）：高频 C-Bet（85% 频率，50~60% 池）——
    # 强牌（strong/good）走下方价值分支，其余（中等/听牌/空气）一律
    # 下注底池 55%：对手弃牌率高，任何牌 C-Bet 都有利可图。
    if adj == "steal" and not strong and not good:
        return _bet_fraction(state, STEAL_CBET_FRAC)

    if strong:
        # 诱敌深入：OOP 强牌 + 对手激进（爱下注）→ 过牌让其下注，
        # 其出手后由 _face_bet 做大额加注（check-raise 陷阱），
        # 专门反制「翻后自动持续下注」的激进对手
        if (not state.is_button) and (not is_river) and \
                (category >= TWO_PAIR or eq >= 0.85) and \
                model.eff_bet_freq() >= 0.45:
            return {"act": "check"}
        # 河牌坚果优势 + 对手非岩石：超池下注榨取最大价值（跟注型对手也照跟）
        if is_river and (category >= STRAIGHT or eq >= 0.80) and arch != "rock":
            return _bet_fraction(state, OVERBET)
        # 坚果级（顺子+）即使对跟注型也大注榨取——跟注型对手对坚果照跟
        if category >= STRAIGHT:
            frac = VALUE_BET_WET if tex["wet"] >= 0.5 else VALUE_BET
            if is_river:
                frac = VALUE_BET
            return _bet_fraction(state, frac)
        # 【响应学习】价值注尺寸：样本充分时选对手弃牌率最低的桶（实证优先）
        lf, learned = _learned_size(model, state, None)
        if learned:
            return _bet_fraction(state, lf)
        # 【用户规则】前几步（翻牌/转牌）非坚果强牌 → 小注钓鱼：
        # 早期用小注维持对手宽范围跟注、渐进构建底池，避免大注吓跑；
        # 河牌才放大注/超池榨取（对手此时牌力已定型，小注钓不动）。
        if (not is_river) and category < STRAIGHT:
            frac = FISH_BET_WET if tex["wet"] >= 0.5 else FISH_BET_DRY
            return _bet_fraction(state, frac)
        # 非坚果强牌（顶对/两对/三条）对跟注型：钓鱼小注，钓垃圾牌跟注
        if _fishy(model):
            frac = FISH_BET_WET if tex["wet"] >= 0.5 else FISH_BET_DRY
            if is_river:
                frac = FISH_BET
            return _bet_fraction(state, frac)
        # 常规对手：湿面大注拒绝给听牌好赔率，干面稍小求跟注
        frac = VALUE_BET_WET if tex["wet"] >= 0.5 else VALUE_BET
        if is_river:
            frac = VALUE_BET
        return _bet_fraction(state, frac)

    if good:
        # SPR 很低：大注把后街筹码在有利时打光（0.6 池而非 0.8，防一次打光）
        if spr <= 2.5:
            return _bet_fraction(state, 0.60)
        # 【响应学习】价值注尺寸：实证弃牌率最低的桶优先
        lf, learned = _learned_size(model, state, None)
        if learned:
            return _bet_fraction(state, lf)
        # 【用户规则】前几步（翻牌/转牌）非坚果强牌 → 小注钓鱼
        # （与 strong 分支同规则：顶对级成牌在早期用小注维持对手宽跟注范围）
        if (not is_river) and category < STRAIGHT:
            frac = FISH_BET_WET if tex["wet"] >= 0.5 else FISH_BET_DRY
            return _bet_fraction(state, frac)
        # 跟注型对手：钓鱼小注（其会用差牌跟注，小注钓更宽范围）
        if _fishy(model):
            frac = FISH_BET_WET if tex["wet"] >= 0.5 else FISH_BET_DRY
            if is_river:
                frac = FISH_BET
            return _bet_fraction(state, frac)
        frac = VALUE_BET if tex["wet"] >= 0.5 else THIN_VALUE
        # 河牌对跟注站做薄价值（其会用差牌跟注）
        if is_river and arch == "station":
            frac = 0.60
        return _bet_fraction(state, frac)

    if big_draw:
        # 半诈唬优先级高于控池：强听牌即使当前胜率中等，
        # 也要么积累底池要么直接赢下（弃牌权益 + 成牌双重收益）
        if fold_eq >= 0.30 or state.is_button or adj in ("desperate", "doomed"):
            return _bet_fraction(state, CBET)
        return _opp_check_bet(state, opp_checked)   # 对手check过 → 立刻小注

    if medium:
        # 有利位置 C-Bet 频率目标 ≥70%：湿面或主动方都下注施压/保护
        if state.is_button and (tex["wet"] >= 0.4 or cbet_spot):
            return _bet_fraction(state, BLOCKER)
        # 不利位置 + 极干面 + 中强牌：1/3 池小注保护（低成本纠缠+节省筹码）
        if not state.is_button and tex["wet"] < 0.2 and eq >= 0.55:
            return _bet_fraction(state, BLOCKER_BET)
        return _opp_check_bet(state, opp_checked)   # 对手check过 → 立刻小注

    if draw:
        return _opp_check_bet(state, opp_checked)   # 对手check过 → 立刻小注（原免费看牌）

    # 空气：纯诈唬，EV 门控 + 阻挡牌效应
    breakeven = BLUFF / (1.0 + BLUFF)        # ≈ 0.355
    buffer = _bluff_buffer(state)            # A=0.03 / K=0.06 / 小废牌=0.12
    if cbet_spot:
        buffer = max(0.0, buffer - 0.05)     # 有利位置 C-Bet 诈唬门槛下调
    if adj == "protect":
        buffer += 0.15                       # 领先保收益：少诈唬
    elif adj in ("desperate", "doomed"):
        buffer = max(0.0, buffer - 0.12)     # 劣势追分：诈唬门槛大幅放宽
    # 【延迟施压】双方持续过牌后突然加注 / 对手连续过牌≥2次直接加注：
    # 弃牌率额外加成（所有档位生效，normal 也适用）。
    # 【前置条件 2026-08-23】累计盈亏 > -3000（非深亏）且 对手面对下注弃牌率
    # > 40% 才生效——落后时滥用延迟施压会白送筹码。
    _pnl_now = 0
    try:
        _pnl_now = state.total_win_chips[state.my_id]
    except Exception:
        pass
    if _pnl_now > -3000 and model.eff_fold_to_bet() > 0.40:
        fold_eq = min(0.95, fold_eq + _delayed_aggression_bonus(state))
    # 【响应学习】诈唬用「该尺寸实测弃牌率」替代全局弃牌率（更准）：
    # 计划下注 BLUFF(0.55 池) → 查对手对 medium 桶的真实反应，
    # 比如「我下注 550 后对手 8 次弃 6 次」→ 用 0.75 而非全局估计。
    my_bet_total = state.curbet[state.my_id] + int(BLUFF * state.pot)
    lf = model.learned_fold_rate(False, my_bet_total, state.big_blind,
                                 state.pot, cur_hand=state.hand_num)
    if lf is not None:
        fold_eq = lf
    if fold_eq >= breakeven + buffer:
        # 无位置时只诈唬非激进对手（避免被 check-raise 掀翻）
        if state.is_button or model.eff_bet_freq() < 0.45 or \
                adj in ("desperate", "doomed"):
            # 河牌诈唬额外要求：对手在河牌有弃牌倾向（避免诈唬被站点抓死）
            if (not is_river) or (fold_eq >= 0.45 and
                                  model.river_fold_rate() >= 0.35):
                return _bet_fraction(state, BLUFF)
    return _opp_check_bet(state, opp_checked)   # 对手check过 → 立刻小注（原过牌）


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
    elif adj in ("desperate", "doomed"):
        margin -= 0.06       # 劣势追分：跟注门槛大幅放宽（多看牌搏翻盘）

    # 【规则1】偷盲档被加注/全下：立即弃牌不纠缠（规则1 执行动作 3）。
    # 对手平时在弃牌，突然加注/全下 = 拿到强牌或识破偷盲 → 止损离场；
    # 唯一例外：顺子及以上（STEAL_FOLD_MIN_CAT=STRAIGHT）的极强牌
    # 仍正常决策（避免真坚果被白白弃掉）。
    if adj == "steal" and to_call > 0:
        if category < STEAL_FOLD_MIN_CAT:
            return {"act": "fold"}

    # 【对手突袭大注】最近一次加注增量 > 此前累计 4 倍 → 强牌信号，跟注门槛
    # 整体抬高（覆盖大注跟注与全下；压力/追分档不重复抬高）。第 36 手教训：
    # 对手翻 10 倍大注（非全下）时也要收紧跟注——K10 顶对面对突袭应弃。
    if adj not in ("pressure", "desperate", "doomed") and _OPP_JUMPED:
        eff_req += OPP_JUMP_FAC_MARGIN
        eq -= OPP_JUMP_EQ_PENALTY   # 突袭大注=对手范围大幅收紧，eq 高估需打折
    # ---- 对手全下 / 需跟注额 ≥ 剩余筹码：纯赔率决策 ----
    # 【硬性风险规避】河牌裸公对陷阱：直接弃牌，不做任何数学计算——
    # 对手全下 range 里两对/三条占比极高，裸公对几乎必输（第 49 手教训）。
    if is_river and _river_paired_trap(state):
        return {"act": "fold"}
    if state.opp_is_allin or to_call >= state.my_left:
        # ICM 压力/劣势追分：放宽跟注（对手范围更紧或我们需要赌博）
        if adj == "pressure":
            thr = eff_req - 0.05
        elif adj in ("desperate", "doomed"):
            thr = eff_req - 0.08
        else:
            # 常规档跟全下需要胜率 > 赔率要求的边际（margin≥0.02），
            # 避免「小优势就接全下」的高方差打法
            thr = eff_req + margin
            return {"act": "allin"}
        return {"act": "fold"}

    # ---- 强牌：加注求价值；全下门槛按牌力分层 ----
    if strong:
        spr = state.effective_stack / max(pot, 1)
        # 【修复】全下分层：坚果/超高胜率（顺子+ 或 eq≥0.82）才可在
        # 浅筹码/追分时全下；两对/顶对只允许极浅筹码+高胜率或追分时全下，
        # 其余情况一律克制加注——避免「小优势上大筹码一次输光」
        if category >= STRAIGHT or eq >= 0.82:
            if spr <= 3.0 or adj in ("pressure", "desperate", "doomed"):
                return {"act": "allin"}
        else:
            if adj in ("desperate", "doomed"):
                return {"act": "allin"}
            if spr <= 1.2 and eq >= 0.72:
                return {"act": "allin"}
        # 河牌坚果 + 有位置：超池加注榨取
        if is_river and (category >= STRAIGHT or eq >= 0.80) and \
                state.is_button and arch != "rock":
            return _bet_fraction(state, OVERBET)
        # 【学习优先】对手反应数据充分时用学习尺寸加注（实证覆盖 fishy 原型）
        lf, learned = _learned_size(model, state, None)
        if learned:
            return _raise_pot(state, category, adj, frac=lf)
        return _raise_pot(state, category, adj, fish=_fishy(model))

    # ---- 良好成牌：价值加注或赔率跟注 ----
    if good:
        if state.is_button and eq >= 0.68 and arch != "rock":
            # 【学习优先】同上：学习尺寸优先于原型假设
            lf, learned = _learned_size(model, state, None)
            if learned:
                return _raise_pot(state, category, adj, frac=lf)
            return _raise_pot(state, category, adj, fish=_fishy(model))  # 位置+明显领先 → 克制加注
        if eq >= eff_req + margin:
            return {"act": "call"}
        if eq >= eff_req and (arch == "maniac" or adj in ("desperate", "doomed")):
            return {"act": "call"}            # 疯子下注不可信/劣势追分宽接
        return {"act": "fold"}

    # ---- 强听牌：半诈唬加注或按（隐含）赔率抽牌（优先于中等成牌：
    #      强听牌有隐含赔率加成，按成牌口径评估会低估其价值）----
    if big_draw:
        if model.eff_fold_to_bet() >= 0.45 and required <= 0.40:
            return _raise_pot(state, None, adj)  # 半诈唬：克制尺寸（0.75 池）
        if eq >= eff_req:
            return {"act": "call"}
        if eq >= required * 0.75 or adj in ("desperate", "doomed"):
            return {"act": "call"}            # 隐含赔率勉强支撑 / 劣势追分硬接
        return {"act": "fold"}

    # ---- 中等成牌：只打好赔率 ----
    if medium:
        if eq >= eff_req + margin + 0.03:
            return {"act": "call"}
        if eq >= eff_req and (arch == "maniac" or adj in ("desperate", "doomed")):
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 弱听牌：只在很便宜时跟；劣势追分时便宜就抽 ----
    if draw:
        if required <= 0.20 and (eq >= required * 0.9 or adj in ("desperate", "doomed")):
            return {"act": "call"}
        return {"act": "fold"}

    # ---- 空气：罕见反诈唬（对手高弃牌 + 我有位置 + 便宜；劣势追分时也尝试）----
    if (model.eff_fold_to_bet() >= 0.60 and required <= 0.30 and state.is_button) \
            or adj in ("desperate", "doomed"):
        # 偷盲档不在此列：关闭反诈唬（对手弃牌率已高，反诈唬无收益）
        return _raise_pot(state, None, adj)
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


def _raise_pot(state, category=None, adj=None, fish=False, frac=None):
    """
    面对下注的加注（克制版）。
    【修复】原实现做「底池大小加注」——深筹码时一次加注会把 60~70% 筹码
    打进去，两对/顶对这类「强牌」也被迫全下量级，一旦被对手统治（三条/
    顺子/更高两对）就单局输光。默认只加注到 0.75 底池（跟注后）；
    仅坚果级（顺子+）或劣势追分（desperate/doomed）才满池加注。
    【钓鱼】fish=True（跟注型对手）时只加注到 0.45 底池——大加注会把
    他们的差牌吓跑，小加注钓更宽跟注范围（坚果仍满池，站点对坚果照跟）。
    【学习优先】frac 显式传入（对手响应学习的尺寸）时完全覆盖 fish 默认——
    实证数据优先于原型假设。
    """
    to_call = state.to_call
    if (category is not None and category >= STRAIGHT) or \
            adj in ("desperate", "doomed"):
        base = state.curbet[state.my_id] + to_call + (state.pot + to_call)
    else:
        f = frac if frac is not None else (FISH_RAISE if fish else 0.75)
        base = state.curbet[state.my_id] + to_call + int(f * (state.pot + to_call))
    return _raise_to(state, base)


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
        if _LEAD_LOCK:
            return {"act": "fold"}   # LEAD_LOCK 时对手全下也弃（不 allin）
        # 【doomed 禁弃】本局失败后对手即可锁胜 → 弃牌=直接认输，全下搏翻盘
        # （doomed 已在 decide 入口无条件 allin，此处为兜底——决策层若漏判）
        if act == "fold" and _match_adjust(state) == "doomed":
            return {"act": "allin"} if my_left > 0 else {"act": "fold"}
        if act == "fold":
            return {"act": "fold"}
        # 【用户规则 2026-08-24】翻前跟全下金额 > 1000 且非 doomed → 弃。
        # 「翻前投入不能大于 1000」沿用到翻前：翻前无公共牌、手牌最多一对
        # （< 三条），任何大额投入都无法由牌型支撑 → 一律 1000 封顶。
        if state.stage == "preflop" and my_left > PREFLOP_MAX_BET and \
                not _allin_high_bet_allowed(state):
            return {"act": "fold"}
        # 【用户规则】allin 金额 ≤2000（仅翻后；例外见 _allin_high_bet_allowed）：
        # 对手全押下我方全下金额超限且无例外 → 弃牌（规则5 内只允许弃/全押）。
        if state.stage != "preflop" and my_left > HIGH_BET_LIMIT and \
                not _allin_high_bet_allowed(state):
            return {"act": "fold"}
        return {"act": "allin"} if my_left > 0 else {"act": "fold"}

    if act == "fold":
        # 【doomed 禁弃】本局失败后对手即可锁胜（_match_adjust==doomed）→
        # 弃牌=直接认输，任何弃牌一律升级为全下搏翻盘（doomed 已在 decide
        # 入口无条件 allin，此处为兜底）。LEAD_LOCK 领先锁定优先（不可能 doomed）。
        if not _LEAD_LOCK and _match_adjust(state) == "doomed":
            return {"act": "allin"} if my_left > 0 else {"act": "fold"}
        return {"act": "fold"}

    if act == "check":
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "allin":
        if my_left > 0:
            # 【用户规则 2026-08-24】翻前全下金额 > 1000 且非 doomed → 降级：
            #   跟全下 → 弃；主动全下 → 降级为 1000 上限加注（保持游戏进行）。
            if state.stage == "preflop" and my_left > PREFLOP_MAX_BET and \
                    not _allin_high_bet_allowed(state):
                if to_call > 0:
                    return {"act": "fold"}
                num = PREFLOP_MAX_BET
                min_r = state.min_raise()
                if _LEAD_LOCK:
                    num = min(num, LEAD_MAX_BET)
                if num < min_r:
                    return {"act": "check"}
                return {"act": "raise", "num": num}
            # 【用户规则】allin 金额 ≤2000（仅翻后；例外见 _allin_high_bet_allowed）
            if state.stage != "preflop" and my_left > HIGH_BET_LIMIT and \
                    not _allin_high_bet_allowed(state):
                if to_call > 0:
                    return {"act": "fold"}   # 跟全下超限 → 弃
                # 主动全下超限 → 降级为 2000 上限的普通加注（保持游戏进行）
                num = HIGH_BET_LIMIT
                min_r = state.min_raise()
                if _LEAD_LOCK:
                    num = min(num, LEAD_MAX_BET)
                if num < min_r:
                    return {"act": "check"}
                return {"act": "raise", "num": num}
            return {"act": "allin"}
        return {"act": "check"} if to_call == 0 else {"act": "fold"}

    if act == "call":
        if to_call <= 0:
            return {"act": "check"}
        if to_call >= my_left:      # 需严格 my_left > to_call 才能跟注
            # 【用户规则 2026-08-24】翻前跟注即全下且金额 > 1000 非 doomed → 弃
            if state.stage == "preflop" and my_left > PREFLOP_MAX_BET and \
                    not _allin_high_bet_allowed(state):
                return {"act": "fold"}
            # 【用户规则】跟注即全下且金额超 2000 无例外 → 弃（仅翻后）
            if state.stage != "preflop" and my_left > HIGH_BET_LIMIT and \
                    not _allin_high_bet_allowed(state):
                return {"act": "fold"}
            return {"act": "allin"}
        # 【用户规则 2026-08-24】翻前跟注额 > 1000 且非 doomed → 弃。
        # 翻前手牌最多一对（< 三条），无法支撑大额跟注（与翻后 >2000 同逻辑）。
        if state.stage == "preflop" and to_call > PREFLOP_MAX_BET and \
                not _allin_high_bet_allowed(state):
            return {"act": "fold"}
        # 【用户规则 2026-08-23 严格执行】翻后跟注额 > 2000 即「投入超过 2000」，
        # 与 raise/allin 同口径受第二优先级限制：非 ≥ 三条 且非 doomed → 弃。
        # 第 12 手教训：A 一对弱踢脚 call 3223 是假投入——假强牌不应跟大注。
        if state.stage != "preflop" and to_call > HIGH_BET_LIMIT and \
                not _allin_high_bet_allowed(state):
            return {"act": "fold"}
        return {"act": "call"}

    if act == "raise":
        try:
            num = int(round(float(action.get("num", 0))))
        except (TypeError, ValueError):
            num = 0
        min_r = state.min_raise()
        max_r = state.max_raise()
        # 【用户规则 2026-08-23】原「加注增量≤1000」已删除，统一由
        # 下方 HIGH_BET_LIMIT(2000) 总注额封顶管控（无独立增量限制）。
        if _LEAD_LOCK:
            # 优势锁定：单次注码 ≤ LEAD_MAX_BET；若最小加注已超上限
            # （对手注已很大），则无法合法加注 → 降级 call/check
            num = min(num, LEAD_MAX_BET)
            if num < min_r:
                return {"act": "call"} if to_call > 0 else {"act": "check"}
        # 【用户规则 2026-08-24】翻牌前总注额 ≤ PREFLOP_MAX_BET(1000)：
        #   所有手牌一律 1000 封顶（超强牌/次强牌不再豁免——翻前手牌最多
        #   一对，任何牌都无法支撑「投入 > 1000」；doomed 防锁赢第一优先级
        #   例外，已在 decide 入口无条件 allin）。
        #   面对大反加（min_raise 已超上限）→ 无法合法加注 → 降级 call/check；
        #   降级 call 也受翻前 ≤1000 约束（to_call > 1000 且非 doomed → 弃）。
        if state.stage == "preflop":
            num = min(num, PREFLOP_MAX_BET)
            if num < min_r:
                if to_call > PREFLOP_MAX_BET and \
                        not _allin_high_bet_allowed(state):
                    return {"act": "fold"}
                return {"act": "call"} if to_call > 0 else {"act": "check"}
        # 【用户规则 2026-08-23 严格化】投入 > HIGH_BET_LIMIT(2000) 仅限：
        #   ①翻后有效牌型 ≥ 三条（经 _effective_category 净化——纯公共牌拼的
        #     三条/顺子/同花/葫芦/四条/同花顺降级为高牌，不豁免）；
        #   ②doomed（防锁赢 allin，第一优先级，在 decide 入口已返回）。
        # 其余一律 2000 封顶（含 steal——>2000 限制处于第二优先级，仅
        # doomed 例外；翻前无牌面 → 一律 ≤2000）。
        # 若对手注已大到最小加注超上限 → 无法合法加注 → 降级 call/check。
        if num > HIGH_BET_LIMIT:
            if state.stage == "preflop" or \
                    _effective_category(state) < HIGH_BET_MIN_CAT:
                num = HIGH_BET_LIMIT
                if num < min_r:
                    return {"act": "call"} if to_call > 0 else {"act": "check"}
        if num < min_r:
            num = min_r
        if num >= max_r or num >= my_left:
            return {"act": "allin"}
        return {"act": "raise", "num": num}

    return {"act": "fold"}
