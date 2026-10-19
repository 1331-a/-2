# 项目长期约定（德扑双人机器人）
> 详情：`项目交接说明.md`/`代码逐行详解.md`/`文献调研_可借鉴方案.md`；逐日 `YYYY-MM-DD.md`；A/B 方法与陷阱见技能 `poker-strategy-ab`。按重要性递减。

## 工作流
收尾：`cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`(cmp) → `git commit -F .git/COMMIT_MSG_TMP.txt` → push。交付前**全量回归**（2026-10-16 起是 16 个测试文件，约 11 分钟，最慢 `test_strategy.py` ≈370s）。冒烟 history 必须 dict 列表，否则 bot 静默返回 0。
★本机 `refs/remotes/origin/*` 写不进去（`status -sb` 恒显 `[gone]`）⇒ **判断是否真推上去用 `git ls-remote --heads origin main` 对比本地 HEAD**。

## 平台协议
BotBattle HU 70 手/盲注 50-100/初始 20000/**60s 每步**/按总筹码定胜负。牌号 n=rank*4+suit，**内部编码=平台+8**。response：-1fold/-2allin/0call-check/>0raise-to。history 不含 blind；hand 0-based（`load_botbattle` meta 是 1-based，**分析用 `req['hand']`**）。**action.amount：raise/allin=本街 raise-to，call=本次增量** ⇒ 尺寸=amount−本街累计；**重建底池用 GameState**。对手弃牌不可见→按 globaldata 增量推断。单挑：翻前 dealer(SB) 先、翻后 BB 先。
★ `state.total_win_chips` 是按座位的净额 ⇒ `lead = twc[我]−twc[敌]` 是单座位值的 2 倍。
★ **twc 是「上一手结算后」口径，不是 live**（10-17 实测 8 份日志 389 手、本手内变化 **0** 手）
  ⇒ `lead − 2×invested` **没有重复扣减**，doom 公式口径正确（头号 bug 嫌疑已排除）。
★ **平台消费的是 `response` 整数（含尺寸）**，比对行为必须用 response 口径，不是动作类型。

## 锁赢/doom（用户硬规则）
lead=我方 net−对手 net。追回线≈75×剩余手数（固定 SB50/BB100，勿用 `state.big_blind`）⇒ doom 阈值≈落后 150×剩余手数。fold_out：`lead>2×(盲注线+invested)`→fold/check。doom：`lead−2×敞口≤−2×追回线`（弃牌口径 `_invested`／跟注 `+to_call`）。★阈值随剩余手数线性缩小 ⇒ **末段小幅落后会自动变"必搏命"**。
★**10-01 裁决：「doom 成立→无条件 allin」不动，`to_call>0` 无门控=有意设计**（异议已被 107 次 allin 否定：对手弃 90%、+43,807）。
★ `_lock_win_unified` 三支：A doomed(`_match_adjust=="doomed"`) / B fold_out / C `_profit_lock_allin`；**A、C 被门控拒绝时必须 return None**（否则互相绕过）。C 已覆盖「我领先但输掉这手就锁输」⇒ **08-23 加的 MUST-WIN 规则在 `3ccd629` 被删（与 doom 重叠致 allin 泄漏）**，无需另设。

## 规则清单（生效顺序，除注明外默认开）
1. 规则2 `_lock_win_unified`（入口，短路 33.9%）→ `_doom_plan`。
2. 规则18 搏命区 `_gamble_plan`：`lead≤−0.80×2×追回线`→牌烂(非太差) allin、牌好慢打；过 `_shove_fold_ok`。`GAMBLE_TRASH_PCT=0.80`，剩 ≤8 手不允许跳过。
   ★ **10-18 P2：`to_call≤0`（无人下注）一律 `check` 埋伏**，全押只在对手已投入后发生
   （`DOOM_WAIT_RAISE_ON`，回退 `WB_NO_DOOM_WAIT=1`）。`_doom_plan` 同样。
   依据：open shove 只赢盲注（+300/次）vs 对手下注后再推（+398/次）；缺口 3 万量级
   ⇒ 「大劣开局就全压一辈子出不去」（用户原话）。**`to_call>0` 的「一律 allin」逐字不变**。
   ★★ **10-19 P2b：「开局」= `to_call≤0` **或** 翻前 `to_call≤BB`**（补盲注不算对手投入）。
   P2 只判 `to_call≤0` ⇒ **在 SB 位置完全失效**（翻前 SB 的 to_call=50=BB），
   实测人机对局 10 次 open shove 全在 SB（+750 vs 坑 20,289）。命中后翻前返回 **`call`（limp）**。
   修后本场全押 10→2 次；A/B 净 **72** 点（对照 1）。契约变更 4 项。
3. `should_avoid_risk`→`_risk_avoid_route`（公对弱两对；pnl>0 时**不看 eq**：check/小注 call/否则 fold）。
4. `_preflop_decide` / `_postflop_decide`（含 `_face_bet`）。
5. 出口链 10 层：`_lock_win_tail_guard`→`_bet_cap_guard`→`_aggressive_strong_bet`→`_bluff_cap_guard`→`_stability_guard`(规则10)→`_normalize`→`_endgame_arbitrate`→`_big_money_guard`(规则20)→`_cheap_call_guard`→`_doom_call_upgrade`。
6. 注额上限：翻前≤1000（**主动**；跟注有 `_preflop_big_call_ok` 豁免，百分位≤0.08）；翻后<三条≤3000；≥三条不限。
★默认关的开关：`ADV_PASS_ON`/`ADV_ODDS_FALLBACK_ON`/`BIGBET_THRESH_ON`/`DOOM_LOCK_ON`/`BIG_BET_FOLD_A_ON`；
默认开：`FLUSH_REAL_PASS`/`ADV_TIER_ON`/`EQ_VETO_ON`(MAX_RANK=3)/`FUTURE_COST_ON`/`BOTTOM_POCKET_RISK_ON`
/ **`FLUSH_MADE_PASS`/`PAIRED_TRAP_MADE_PASS`/`BIGMONEY_TWOPAIR_PASS`（10-17 拍板）**
/ **`OVERP_VS_BIGBET_ON`（10-18 P0-2）** / **`DOOM_WAIT_RAISE_ON`（10-18 P2）**
/ `PREFLOP_BIG_CALL_ON` / `SHOVE_BY_ODDS_ON`。
7. **P0-2 超对豁免**（10-18）：`_face_bet` 三道「大注 / 4 倍突袭」锁命中时，若
   `_overpair_bigbet_pass` 放行则改走 `_bb_gate`（**只 call/fold**）。分层：clean 直接豁免 /
   wet（3 同花 或 公面 Q-K）门槛 +0.06 / 公面 3 连·≥4 同花·三条 **不豁免** /
   对手弃牌率<0.25 且样本≥6 **不豁免**。★ **公面成对仍算超对**（QQ on 334 = 两对 QQ33）；
   ★ **公面有 A 不可能与超对共存** ⇒ 中危只按 Q/K 判。`_endgame_arbitrate` 入口对豁免点的
   call/fold 直接返回（否则 `UA_SEALED_ALLIN` 会改回 allin）。回退 `WB_NO_OVERP=1`。
★ **P0-1 全押弃牌权益按赔率算**（10-18）：`_shove_fold_ok(odds=True)`，
   `f*=(R−e(P+2R))/(R+P−e(P+2R))`，`to_call≤0` 再加 0.10，封顶 0.95，样本不足用先验 0.35；
   **只用于 `_doom_plan` 的 to_call≤0 分支**（规则18 与 to_call>0 的 doom 不动）。回退 `WB_NO_SHOVE_BY_ODDS=1`。

## ★★ 当前第一瓶颈：eq（对手范围）系统性高估
- 10-15 旧口径：我方 eq 平均 0.459 / 真实 0.175 ⇒ 高估 0.284（n=11）。
- 10-16 修正口径（`测/_range_condition_audit.py`，固定计算量、完整前序更新、8 份真实日志 98 点）：**全体 +0.150 / MAE 0.245**；历史 11 点 +0.223。**不是同口径，不能说成已改善。**
- **凡是"把硬弃改成信 eq"的改动，必须先过这个判据**（`测/_advpass_truth.py` / `_range_condition_audit.py`）。
★★ **10-17 找到机制、但两个修法都被留出验证否掉**：
  · **机制**（`测/_eq_bias_mechanism.py`）：偏差集中在「对手已成强牌」——高牌 **−0.147**、一对 +0.144、
    两对 +0.185、三条 **+0.400**、顺子 **+0.552**；两对+ 偏差 +0.296 vs 一对/高牌 +0.106。
    根因：`_build_range` 权重只来自**翻前** `hand_percentile`，**不看"对手下注"与翻后牌力的相关性**
    （典型 `b1a82568 手16`：对手 22 翻前百分位 0.447，河牌成三条 2，真实 0.000、模型给 0.754）。
  · **修法1 缩范围 k**：LOOCV 0.2406→0.2088（−13.2%）、8/8 折选 k=0.25，但 **k 落在网格边界 + 3/8 场变差** ⇒ 否。
  · **修法2 按翻后牌力加权**（`opp_weights` 钩子）：LOOCV 0.2618→0.2409（−8.0%），但 **4/8 场变差** ⇒ 否。
  · **根因**：偏差是**对局特定**的（8 场 +0.032~+0.341，差 10 倍；MAE 差 2.4 倍）⇒ **任何全局常数都修不好**。
  ⇒ **不要再找全局常数校准 eq**；方向改为「限制 eq 的话语权」（只在极端确信区越过硬规则 = `EQ_VETO`）
    或「场内自适应」。工具：`测/_range_calibrate.py`、`_range_empirical.py`、`_eq_strength_weight.py`。
- 范围减半诊断：全体 MAE 0.2445→0.2204（11 点 0.2228→0.1695），但 2 份日志变差、无留出验证 ⇒ **只是假设筛选，未校准完成**。完整重放 B/A 仅 5/786 变化（MC 300 次，仅敏感度）。
- 转牌截断偏差已修：`_exact_turn` 原按 `full_deck()` 固定牌序枚举+超时截断 ⇒ 只取前缀（hand57 报 0.8188 = 前 4 张；完整 0.195、真实 0.182）。现限时转牌改 MC（**未提交、建议换改法**）：实测（`测/_turn_cost.py`）完整枚举 **2.45s/误差0** vs MC30000 **4.36s/误差0.32%** ⇒ MC 评估次数更多（6万 vs 4.35万）、**又慢又准不了=净亏**；且单次转牌占用 2.45→4.44s，更易撞破 `EQ_TOTAL_BUDGET=12s` ⇒ 后续胜率落到 **0.5 兜底**（0.5 恰是 `medium` 门槛）。触达面 94/786 转牌点（12%）。**更好改法：保留精确枚举、只把河牌枚举序换成确定性洗牌序**。★**该改动无法 A/B**（两个重放工具都强制 `deadline=None`，走不到新分支；带真实时钟不可复现）⇒ 验收口径待用户拍板。

## 出口链（★最大结构问题）
★逐层实测（948 点，改写 116 次）：**更保守 77 : 更激进 5 = 单向保守机器**。`_stability_guard` 39 / `_bet_cap_guard` 32 / `_aggressive_strong_bet` 12 / `_doom_call_upgrade` 11 / `_cheap_call_guard` 7 / `_endgame_arbitrate` 6 / `_normalize` 5 / `_big_money_guard` 3 / `_bluff_cap_guard` 1 / `_lock_win_tail_guard` 0。层间打架仅 1 次。
★归因：翻前 35.2% / 入口短路 33.9% / 主动侧 17.8% / 面对下注 5.7% / 硬规则 5.4% / **eq 门槛仅 2.0%**；出口链净改写 10.3%。
★★「好牌也消极」：77 次保守改写里 **26 次（33.8%）落在 `eq 超门槛 ≥+0.10`**（`eq0.901→allin→call→fold`）。
⇒ **`eq` 权重天花板低**；唯一越过出口链的办法 = `EQ_VETO`（判据 `eq ≥ eff_req+margin+0.10`，`EQ_VETO_MAX_RANK=3` 可恢复加注、不可恢复全押；会越过规则20 的 3000 上限，用户已批准）。
★ `_face_bet` 兜底空洞：`eq∈[~0.40,0.50)` 且无听牌 ⇒ strong/good/medium/draw 全 False ⇒ **L5945 兜底 fold、不看赔率**（10-12 实测 18 点，to_call≈1/4 池、eq 0.23~0.49）。补丁 `ADV_ODDS_FALLBACK_ON` 已写好但**默认关**——因为 eq 高估下"信 eq"大概率是负 EV。

## ★★「一直输」的结构诊断（10-12，11 场 770 手，净 −10,479）
三条独立线索同一根因：**价值/诈唬倒挂（弱牌乱进攻、强牌加注不足）**。
1. 实战：最大失血 = **「投入后弃牌」335 手 −73,052**（主动加注后弃 72 手 −48,052）。拆街全押：`preflop/allin` −27,500、`flop/allin` −16,400、`river/allin` −11,540、`turn/allin` +41,397（仅 3 次=方差）。
2. v50 静态对拍：面对 70% 池，**v50 强牌加注 500 / 本版 280**；v50 对听牌·空气 fold / 本版 call·raise。
3. v50 结构：`doomed` 只放宽注额上限、不强制 allin；求稳门槛 0.80 且只作用翻后。
★ **胜负机制**：翻前全押 138 次，对手弃 130 次（94%，每次只赚 100~300 追不回落后），仅 8 次被跟 = ±20,000 ⇒ **每场约 1 次被跟决定胜负**。10-15 四场复核：28 次全押→弃 24/跟 4 ⇒ 全押手净 −37,600，**每次全押 ≈ −1,343**；打平需弃牌率 ≥99%，实测 86%。
★ 已排除：开池范围收紧（A/B 证有害）、纯诈唬门槛（0/1058）、规则12 路径（0 次）、`_stability_guard`、`OPEN_PCT_VS_STATION`（21 手真实 +650 ⇒ 撤回）。
★ **10-17 全押位置核查**（`测/_allin_lock_audit.py`，8 份日志 794 请求 **79 次全押**）：
  **0 次落在 `fold_out`（弃牌即锁赢）** ⇒ 不是 bug 且**结构上不可能**（`_lock_win_unified` 的 B 分支排第一，命中即 return，A/C 走不到）；**68/79 落在 doomed** ⇒ 符合设计。
  11 次非 doom：9 次 = 规则18 搏命区 0.80（**用户规则**，全擦线、离线差 106~470）；2 次 = 常规策略（n=2，不动）。
  按来源拆账：`lock_win` 68 次**净 −14,050**（59 次只赢 +100、2 次 −20,000）⇒ **doom 触发时这局已实质输掉，全押只是续命**（追回 ≈300/手 vs 坑 3.5 万）。
  ⇒ P0-1 的准确表述不是「全押输钱」，而是「**已经输了之后才全押**」；要治的是**为什么会掉进 doom**（P1-1/P1-2）。

★ **10-17 漏损账本**（`测/_leak_audit.py`，560 手、不依赖重放）：A 主动投入后弃 **49 手 −33,759**、
  B 跟注后弃 8 手 −9,987、C 全押被跟输 3 手 **−60,000**、F 翻前弃 205 手 −15,462、W 赢 291 手 +130,329。
  ⇒ **投入后弃 57 手 −43,746 = 最大结构漏损**；单场胜负仍由「1 次全押被跟」决定。
★ **10-17 弃牌真值**（`测/_fold_truth.py`，对手真实底牌只作离线标签）：102 次弃牌弃错 29（28%），
  翻后 21% / **翻前 41%**。★口径：`true_eq` 是「对那一手具体底牌」的胜率，**不是对范围的期望**，只能当下界。
★ **10-17 已撤回的假设**：「`OPP_JUMP_RATIO=4.0` 把正常再加注误判成突袭」——A 类 26 手里
  突袭组弃错率 **7%(1/14)** vs 非突袭组 **25%(3/12)**，突袭组弃得反而更准 ⇒ **不动该规则**。
★ **规则11 硬弃两对**：全场只触发 4 次、弃错 3 次；扣掉已修的真同花，剩 **2 次**（`b1a82568 手5/手6`，
  公面 3 张同花 + 两对 + 对手 >3000，需要 0.33 / 真实 1.00）。**四道串联锁**：规则11 `_flush_threat` →
  `_river_paired_trap` → 规则20 `_big_money_guard`+`_normalize` → 出口 `_doom_call_upgrade`。
  ⇒ 必须 `FLUSH_MADE_PASS`+`PAIRED_TRAP_MADE_PASS`+`BIGMONEY_TWOPAIR_PASS` **三个一起开**；
  **只开 `WB_FLUSH_MADE=1` 是 0 净效应**（10-17 四臂实测：B1=1 噪声、B2=3 含 1 噪声、对照臂噪声 2）。
  A/B 工具 `测/flushmade_ab.py`。**默认值仍关，等用户拍板**（动规则11/规则20 属硬规则）。

## 重放保真度（重放 ≠ 平台）
**本地重放与平台真实决策只有 80~86% 一致**。主因：`_opp_check_bet` 被规则19 `_small_bet_futile` 拦下（依赖小样本表）⇒ 关规则19 后 31→17。**凡依赖小样本学习表的规则，重放都可能整类判错**。保真度随局数漂移（前 11 手 ≈96% vs 全场 11~14%）⇒ 平台开局是"热"的；但 `_replay_seq.py` 连着重放**并未改善** ⇒ **仍有未解释项，别宣称已解决**。
★判读：✅ A/B **相对**比较有效（共享偏差）；★ **10-18 更正**：同一版本下决策是**确定的**
（见下「复现率 99.8%」）⇒ **单点归因其实有效**，只要同版本 + 同输入重建 + 固定计算预算。
★落地：`SMALL_BET_MIN_N` 4→10（提交 1f899e2）；`bot.py` 新增 `[MODEL]` stderr 自检行。
★★ **10-18 起一律用严格整数口径**（`测/_replay_protocol.py`，走完整 `bot._handle_line`、
  模型 `to_json` 跨请求恢复、比较整数 response）：10 份日志 **1043 点**
  —— **历史一致率 严格整数 806/1043 = 77.3%**、类别 948/1043 = 90.9%
  —— **同版本复现率 整数 1041/1043 = 99.8%**（类别 99.9%）
  ⇒ ①旧口径「81.4%（类别+金额±2%容差）」**作废**；②**随机性不是低保真度的原因**，
     差异可逐个追溯；③按日志拆 63.6%~90.8%，与代码演进吻合（10-12 / 10-18 晚差异最大）。
  ★ 类别转移矩阵最大一类是 **`raise → call` 31 点** ⇒ 出口链确实在把主动加注降级。
★★ `_divergence.py` 曾把整场 `build_model_from_history`/`ctx.update` 跑完再回头 `decide`
  （**未来信息泄漏**，已修）；修后数字未变，但**先修再结论**。
★★ **任何「漏损账本」类分析必须先过 `_divergence.py` 过滤**：8 份日志横跨 9-24~10-15 多个代码版本，
  账本是历史行为。实测 A 类 49 手只有 31% 有分歧（= 69% 当前版本仍照做），C 类 3 手里 2 手已作废。
★★ **`true_eq`（对具体底牌）不能用于范围决策**：翻前「41% 弃错」是伪影；正确口径是手牌百分位
  （翻前弃牌中位 0.80~0.86，弃的多是垃圾牌 ⇒ 翻前没有可修的结构性 bug）。
★★ 遍历 `action` 事件必须判 `pl == seat`，否则对手弃牌被算成我方（曾造出「AA 面对全押弃牌」假 bug）。
★★ **`load_botbattle` 筹码重建三坑（10-18 已修，`_verify_chips.py` 0/1043）**：
  `street_bet` 要恒为「本街累计总注额含盲注」⇒ ①call 的 amount 是**增量**要 `+=`；
  ②翻前要用盲注初始化（raise 的 amount 是 raise-to）；③**check/fold 不能写 0**（会把累计清零）。
  偏差 1 个盲注就会让 doom/锁赢在临界点翻面。
★ **doom 全押的弃牌权益必须按赔率算**：`f* = (R−e(P+2R))/(R+P−e(P+2R))`；
  旧实现固定 0.45 且样本不足默认放行 ⇒ 10-18 手60 推 19,608 进 584 的池（需 97% 弃牌率）被跟输光。
  已加 `_shove_fold_ok(odds=True)`，**只用于 `_doom_plan` 的 to_call<=0 分支**
  （规则18 与 to_call>0 的 doom 不动）。回退 `WB_NO_SHOVE_BY_ODDS=1`。
★★ 三个 −20,000 输局手：`ea9c99c4 手21`(转牌 call→fold)、`4895b988 手45`(allin→fold) 当前已不同；
  **只剩 `11de872b 手62`**（BB T6o 对手 open 250 → doom 擦线 180/1200 → allin 20000），属硬规则未动。
★战报：18:52 赢 +19,280、17:21 输 −19,990、21:55 输 −19,782（vs code A）⇒ **单场 70 手不足以评价一次改动**。

## 工具陷阱
★规则标签≠真凶（逐层 monkey-patch 看 before→after）。★★报「变化 N 点」必须重跑+对照臂（跨进程噪声 0.5~1%）。★`diff_ab.py --off-env` 列方向反。★自对弈双方 owner 同一 id，先确认座位；`duel.py` 不可用。
★★ **按街分类绝不能用「整手最终牌面」**：`len(hand["board"])` 是最后一街的牌面 ⇒ 纯翻前加注会被算成"翻后有 bet/raise"
  （`_leak_audit` 初版把 A 类虚报 53 手，修正为 49）。必须记录**动作当时**的牌面快照（`deal_board` 逐条更新）。
★★ **日志必须同时扫 `~/Downloads/botbattle*log.json`**：`内容/记录` 只有 8 份里 5 份可定座位；
  漏扫会让样本从 560 手掉到 300 手（`_a_class_shape` 初版 A 类报 4 手 vs 实际 26 手）。
★★「只落后才生效」的规则用内置对手配对必然假阴性 ⇒ 用 `sim_early.py --selfab`。
★★ 改一条硬规则后 diff 报 0：①加触发计数器 → ②找"下一个接走者"（同人群常被多条**串联**规则覆盖）→ ③查出口链。★「大注/突袭」族 15 点里 14 点 `_OPP_JUMPED=True`。
★★ **`load_botbattle` 双口��**：`req['hand']` 0-based，`meta['hand']` +1。★★ 自对弈日志（`owner_display` 都是 j1331）**无法确定我方座位**；11 份里 6 份是自对弈。
★ 牌型归因必须用 `_effective_category`（`evaluate_7` 会把"公面三条"标成"三条"）。
★★ **测试时钟污染**：`_DECISION_STARTED_WALL` 只在 `_decide_impl` 入口刷新；测试直接调子函数跑够 12s 后 deadline 恒过期 ⇒ MC 0 抽样 ⇒ `equity.py` 兜底 0.5 ⇒ 阈值失效。**修法在测试侧**：断言前 `strategy._DECISION_STARTED_WALL = time.time()`。
★★ **动作面变化 ≠ 收益改善**：必须用 `req['hand']` 把变化点映射回真实 `settle.deltas` 再下结论（`测/_openpct_impact.py`）。
★★ 固定历史重放不是反事实对局：日志原手 deltas **不是改动收益**。

## 构建/平台
单文件 `内容/botzone_submit.py`（≈8.5k 行）；Linux ELF 由 GitHub Actions（仓库 1331-a/-2，workflow build-elf）产出；artifact 常下成 22 字节空 zip。★平台 1 核/512MiB/无网络/60s ⇒ **纯 Python 不引 numpy**。`测/学习升级版/poker_bot` 是用户 ELF，勿动。★技术判负(09-28)根因未定位。
★ 识别任意 `poker_bot` ELF 版本：遍历常量表读 git hash。三个"升级版"ELF：`学习升级版` f34f565、`参考升级版` a9bc958、`参考升级版2(v80以后)` 6ec4374。

## 待办（按优先级）
0. ★**交付决策（未提交）**：本地 HEAD `5a9a69f` 未推送（远端 `61fbcfe`）；工作区还压着 10-16 两处改动——`BOTTOM_POCKET_RISK_ON`（A/B 2/786、对照 0，**可交**）与 `equity.py` 限时转牌改 MC（**建议改成洗牌序精确枚举再交**）；bundle 已重建（8484 行、与 `botbattle/poker_bot.py` SHA 一致）；16/16 测试全绿。详见 `复盘_20261016_状态核查与转牌估计器代价.md`。
1. **eq 校准**（放开硬规则的前置条件）—— 先做 combo 权重诊断，真实底牌只做离线标签；按对局/对手分组留出验证。
2. **收紧跟注链** / 强牌加注尺寸回归 2.5~3BB / 底对不在高张面加注。
3. `_doom_plan` 的 `to_call>0` 分支是否加"太差"容错（用户 09-28 裁决过，未定）。
4. `ADV_ODDS_FALLBACK_ON`（`_face_bet` 兜底赔率）—— 只在 eq 校准后才考虑开。
5. 复核文献 §9.7"低敏感"是否出口链假象；拉翻前 Nash 蓝图。
★ 教训：**"门槛比原规则更高"的补丁，要问一句"它推迟的是不是本该发生的事"**（锁定门被否）；**"这次先不做、等下次"的规则必须加"还有下次吗"门控**；**"金额上限"类规则常有作用域溢出**（管下注的上限被复用去管跟注）。
