# 项目长期约定（德扑双人机器人）

> 完整背景见根目录 `项目交接说明.md`、`代码逐行详解.md`；逐日细节见本目录 `YYYY-MM-DD.md`。
> **本文件按「重要性递减」排列** —— 注入被截断时砍掉的是最不关键的尾部。

## 工作流
- 收尾推送：`cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`（`cmp` 校验）→ 长消息写 `.git/COMMIT_MSG_TMP.txt` + `git commit -F` → `git push`。
- 交付前：13 个测试全量回归 → 同步 `代码逐行详解.md` → 更新记忆。
- 冒烟 history **必须是 dict 列表**（player_id/action_type/amount/round）；扁平 list → GameState 抛错、bot 静默返回 0。

## 平台与协议
- BotBattle HU：70 手、按 `total_win_chips` 定胜负；盲注 50/100、初始 20000；**每步 60s**（`holdem_per_decision_60s_v1`）。★ 竞赛平台未定（指南写 Botzone 1s/50 手，实测 BotBattle 60s/70 手）⇒ 未发布前按 60s。详见 `竞赛规则_核查清单.md`。
- 牌号 `n = rank*4 + suit`（T=32..35,J=36..39,Q=40..43,K=44..47,A=48..51），suit 0♠1♥2♦3♣。**内部编码 = 平台 + 8** ⇒ 从原始日志取牌要 +8。response 单整数（-1 fold/-2 allin/0 call·check/>0 raise-to）。
- **history 不含 blind**；`hand` 0-based，但 `load_botbattle` 的 `meta["hand"]` 与平台界面是 **1-based** ⇒ 混用会看错手。`_hands_left = max_hand − hand − 1`；`hand_start.chips` 已扣盲注。
- 只在我方行动时收 request；对手弃牌不可见 ⇒ 按 globaldata 增量推断（+50 对手 SB 弃 / +100 对手 BB 弃）。单挑：翻前 dealer(SB) 先、翻后非 dealer(BB) 先。
- **原始 replay 字段**：action 用 `player`/`action`/`amount`；deal_hole 用 `holes:[[座0],[座1]]`（"7d"）；settle 的 net 是累计；有 `time_used` 事件可拿每步耗时。
- ★ **尺寸重建口径**：`hand_start.sb/.bb` 是**座位号**（盲注固定 50/100）；`action.amount` 对 raise/allin 是**本街 raise-to**、对 call 是**本次增量** ⇒ 尺寸 = `amount − 本街累计`（**不是**整手累计）。

## 锁赢 / doom 数学（用户硬规则）
- `lead = 我方net − 对手net`；**筹码损失让 lead 变化 2 倍**，`×2` 只用一次。
- 追回线 `_blind_line(hands_left, own=False)` 固定 SB=50/BB=100，**勿用 `state.big_blind`**。**追回线 ≈ 75×剩余手数** ⇒ **doom 阈值 ≈ 落后 150×剩余手数**。
- fold_out 锁胜：`lead > 2×(盲注线 + invested)` → fold。doom：`lead − 2×敞口 ≤ −2×追回线`；弃牌口径 `_invested`、跟注口径 `_invested + to_call`。只用**原始 lead**（match_ctx 偏移只作用于软阈值）。
- **★ 10-01 裁决：「doom 成立 → 无条件 allin」不动；`to_call>0` 无 `_shove_fold_ok` 门控 = 有意设计。勿再提收紧 doom。** 我的异议已被数据否定（全量 **107 次 allin**：对手弃 96 次 90% 累计 +23,807、被跟 11 次 +20,000 ⇒ **合计 +43,807，均 +409/次**）⇒ **已撤回**（错因：n=4 过度概括）。
- 仍待用户定：`to_call==0` 且未见翻牌时先过牌看翻牌（手58）。候选（未验证）：我方可能**「全下不足」**；需按画像分臂 A/B。

## 规则清单（生效顺序）
1. **规则2 `_lock_win_unified`**（入口）：B fold_out→fold（`to_call==0` 用 check）；A doomed / C `_profit_lock_allin` → 同为 `_doom_plan`。`_doom_plan` = 「弃牌是否立死」+ 牌力分流：`line≤0`→allin；`to_call>0`→**一律 allin**；`to_call≤0` 牌烂→allin（过 `_shove_fold_ok`）、牌好→None、牌好且河牌→allin。★ **A 被拒后必须 return None**（否则 C 会绕过：局2 #43 推出 19,500）。
2. **`_endgame_arbitrate`**（09-24）：五动作同尺度比 EU（`_win_utility` logistic，锚点 ±2×追回线）。护栏 `UA_CROSS_CHECK` / `UA_SEALED_ALLIN`(0.15) / 只往保守修正 / 硬性弃牌不翻案。
   ★★ **10-09 定位 `UA_CROSS_CHECK` = 「好牌也消极」元凶**（L1236 生效，EU 比较**之前**硬 return check；判据 `_doom_risk(extra=add)` 是**最坏情况**，不看 f/eq/规模）。实测座位2 被改 11/107 点、座位1 2/122 点，**能比 EU 的 10/10 次都偏好下注**。机制：越贴 doom 线越禁下注 ⇒ 落后方无法追回（赢家被拦 2 vs 输家 11）。
   ★★ **10-09 已按用户原则修复并设为默认**：「看牌的目的是为了确保优势，我都确保优势了还不跟留着干嘛」⇒ `_cross_check_exempt`（**分街**）：翻后 = 有效牌型 ≥ 两对 **或** `_pair_is_top`（顶对/超对）；翻前 = `_is_super_hand`。★ **不可用「翻前超强牌名单」判翻后优势**（AKs 翻后打空会被误判）。实测命中 11 次 → **5 放行 / 6 仍拦**。开关 `WB_NO_CROSS_STRONG_PASS=1`（回旧「一律拦」）/ `WB_NO_CROSS_CHECK=1`（整体旁路）。
3. **规则10 求稳**：`lead ≥ 0.70×锁赢线` 或剩 ≤8 手且领先 → 主动侧 check、被动只跟；强牌（翻后 ≥两对 / 翻前 AA·KK·QQ·JJ·AKs）例外。开关 `STABILITY_PREFLOP_ON`（默认 True）。
4. **规则16/17**：跟全下门槛按剩局/对手 allin 频率下调（≤0.09）；翻后按盈利档叠加（>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08）。
5. **规则18 搏命区**：`lead ≤ −0.95×2×追回线` → 牌烂 allin、牌好慢打；推前过 `_shove_fold_ok`（`eff_fold_to_bet ≥ 0.45`，样本 ≥6 才门控）。
6. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本 ≥4）→ 停用小注线。**规则学习**：样本 ≥4 且胜率 <0.35 → raise 降级为跟/过；>0.60 优先复用。
7. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束主动下注/shove**。
8. **规则20 `_big_money_guard`**：R1 `to_call>3000` 且 <三条 → fold；R2 主动全押只允许 ≥三条 / 翻前 AA·KK·QQ·JJ·AKs。★**故意不给 lk 开免检口**（改则 test_log_v2 FAIL）。
   ★ **10-01「顶两对」豁免**：`_is_top_two_pair()` = 两对 + 两个对子正好是场上最大两档 + **两档都必须由我方底牌补成**（§手44 反例：T 对纯公共牌时对手是同花）。**需同时改 4 处**（只改规则20 无效，实测「变化 0 点」）：`_normalize` 的 `_over_limit` 分支 **和** `to_call>_bet_limit` 分支、`_big_money_guard` 的 `act=="allin"` 分支（降级 call）、`_doom_call_upgrade`。开关 `BIG_MONEY_TOPTWO_ON` / `DOOM_TOPTWO_CALL_ON`。
   ★ 死代码：`_over_limit` 内部翻前看 1000、**翻后看 `_bet_limit`** ⇒ `_normalize` 里那条只判 `stage!="preflop"` 的重复闸门**永远走不到**。
9. **`_doom_call_upgrade`**（最后一层）：跟注口径 doom → 强牌 allin、弱牌 fold。安全网 `_normalize` + `_allin_floor_guard`。
10. **★ 10-11 规则11「公面同花威胁」**（用户 09-07：公面 3+ 同花 + 对手 >3000 → 视作对手有坚果同花）。★ **缺陷：只看牌面纹理，不看已成牌也不看赔率**（实测把百老汇顺子、三条也判"该弃"）；`my_best>=11` 把「阻断牌」和「我的同花够不够大」混为一谈。
    **全量 895 点命中 7 次：5 次是对手全下（弃对）、只有 2 次是普通下注（10-11 手5/手6，两次都错）。**
    ⇒ **已实现豁免（默认关闭）**：`FLUSH_MADE_PASS`(env `WB_FLUSH_MADE=1`) / `PAIRED_TRAP_MADE_PASS`(`WB_PAIRED_MADE=1`) / `BIGMONEY_TWOPAIR_PASS`(`WB_BIGMONEY_TWOPAIR=1`) + 阈值 `FLUSH_MADE_MIN_CAT`(`WB_FLUSH_MADE_CAT=3`) + **★非全下门控 `FLUSH_MADE_NO_ALLIN`**(`WB_FLUSH_MADE_ALLIN=1` 放开) + 护栏 `_flush_made_guard`（已成牌时**只跟不推**）。
    **共 7 处落点**；实测最终方案 895 点**只改 2 点**（只有手5/手6 fold→call）。详见 `复盘_20261011_同花威胁连弃.md`。

## ★ 「3000 悬崖」（10-11 全量普查，`测/cliff_3000.py`）
**口径：必须用 `GameState` 直接解析决策点，不要手工重建底池**（按街清零会漏前面街筹码 ⇒ 把满池注错判成 1.00 倍池；`sb/.bb` 是座位号；`action.amount` 对 raise 是本街 raise-to）。
668 个「面对下注」决策点：`to_call>3000` 共 **41 次(6.1%)** = **36 次对手推光**（定向决策，弃对）+ **仅 5 次普通下注**。
这 5 次全在 **0.98×~1.30× 池**（满池/超池），**没有一次是刻意压线**（2900~3000 样本 0 次）。
★ **其中 手21(20260924154120, 一对, 6318, 1.14×池) 正是规则20 的原始案例** ⇒ 真正的问题是**牌力**，不是金额。
⇒ 现行语义 = 「**底池 >3000 后，对手下满池我们只能拿三条+去接**」；而底池过 3000 是**常规场景**；
且是**悬崖**（3000→eq≥0.33；3001→必须≥三条）⇒ **对手多下 1 个筹码即可压死我们**（主动侧有 `_dynamic_cap` 防 read，**跟注侧没有**）。
**建议（未实施）**：① 把 4 处金额闸门收敛成 `_big_call_gate()`（纯工程、行为不变）；② 主判据换成「对手是否推光」；③ **闸门从「筛牌力」改成「抬门槛」**（连续加价，由 `eq` 决定）⇒ 消悬崖、弱牌仍被挡；④ `opp_threshold_bets` 防 read。**这 5 个样本不足以做统计 A/B**（±1 点=20%）。

## 出口链（★ 最大结构问题）
`decide` → 入口短路 `_lock_win_unified`(规则2 A/B/C，≈7%) 与 `_gamble_plan`(规则18) → 决策层 → **出口 10 层**（`_lock_win_tail_guard`→`_bet_cap_guard`→`_aggressive_strong_bet`→`_bluff_cap_guard`→`_stability_guard`→`_normalize`→`_endgame_arbitrate`→`_big_money_guard`→`_cheap_call_guard`→`_doom_call_upgrade`）。v50 出口只有 `_normalize`。
**实测（10-01 `测/exit_chain_probe.py`，315 真实点）**：`_stability_guard` **26/49=53%（22/26 在翻前，全把 raise 降 call/check）**；`_bet_cap_guard` 9；`_aggressive_strong_bet` 7（全放大）；其余各 1~2；**`_lock_win_tail_guard`/`_bluff_cap_guard` 各调用 292 次、0 翻转**。净翻转 13.3%、被改写 ≥2 次仅 1.9%、打架仅 1 次。
⇒ ① **「层间打架」不是主要风险**（原假设被否定）——`我加注→对加注→我再加注→我弃牌` 来自**决策层自身**（同街每次轮到我都是独立决策点），**别再用它当出口链证据**；② 收敛收益调低预期（只 2 个死层）；③ `_stability_guard` 翻前压制是唯一大项（A/B 已结案，见下）；④ **`LIMIT` 会静默截断** ⇒ **重放前先确认决策点总数**。
★ **规律（两次踩到）**：**同一条「金额/阈值」规则通常在出口链上有 3~5 个实现点**（10-01 顶两对 4 处、10-11 规则11 4 处）⇒ **只改一处 = diff 报 0 变化**。

## 对手画像与胜率
- 【算力 09-30】`MC_ITERATIONS=30000`/`TIME_BUDGET=5.0`/`ALLIN_MC=20000`/`ALLIN_TIME_BUDGET=4.0`/`DECISION_TIMEOUT=40.0`/`EQ_TOTAL_BUDGET=12.0`（各路共用 `_eq_deadline()`）。**播种两处**：`equity._rng` **和全局 `random`**（只播前者一致率 52/60）。env `WB_MC_ITERS`/`WB_MC_BUDGET`。
- 【精确枚举 09-30】`equity.equity_best()`：河牌/转牌走 `exact_equity`（误差 0）、翻牌及以前回退 MC。河牌 990 组合 **0.05s**；转牌 ≈4.4 万 ≈2.6s；翻牌 ≈214 万超预算。
- 【★ 软尾巴 09-30】无偏校准发现模型范围**系统性偏窄约 2 倍**（覆盖率 50~67%）→ eq 低估 0.0589；`RANGE_SOFT_TAIL` 修正后与真实底牌差距 **+0.0012**。★ **全下禁用** `ALLIN_SOFT_TAIL=0.0`。工具 `测/range_eval.py`·`tail_impact.py`·`tail_actions.py`。
- 【★ 软时限陷阱 09-30 修复】`_eq_deadline` 兜底下限**不能无界**（原 `max(limit, now+0.05)` ⇒ 永不主动停 ⇒ 单步 **277.46s** 判负）。已封顶 `决策起点 + EQ_TOTAL_BUDGET + EQ_GRACE`。
- 【规则12 已接线 09-30】`_check_bet_weight()` 融合 `check_fold_rate`（贝叶斯 `w=n/(n+6)`，n ≥ 6）+ `check_raise_rate ≥ 0.20` → 频率 ×0.6。
- 【翻前尺寸】`OPEN_SIZE_BB=3.5`/`VS_STATION=3.0`/`ISO=4.0`/`STEAL=3.0`；★**只改 `OPEN_SIZE_BB` 无效**（`_learned_size` 用 `bucket_to_frac` 覆盖）。条件化乘 `clamp((0.80−eff_vpip)/0.25,0,1)` × `min(1,hands_seen/8)` ⇒ 实际 [2.5,3.5]，**前 8 手不生效**。
- 【默认关闭】`BIG_BET_FOLD_A_ON=False`；`WB_FORCE_BIGBET_A=1` 启用。条件化 A（`_future_aggr_factor`）/B（`_open_size_bb`）**早已实现**；实测对 code A 自动退化为中性 ⇒「看不出变化」是预期行为。
- combo 级 1326 权重**暂缓**（70 手 ≈130 翻后点，识别 1326 参数严重欠定）；`opp_weights` 接口已建好，体积仅 ≈**5KB**。
- 【★ 10-01 尺寸结论】「对手过牌→我方下注」全量 85 次：**25~45%（现用）与 45~70% 两档均值完全相同（+243/手）** ⇒ **加大尺寸不是杠杆，不改**。（原「纯诈唬盈亏平衡尺寸 f/(1−f)」推理**错误**。）
- 【★ 10-01 模拟算力】生产口径 **70 手/场 ≈4 分钟**（不可行；20 手短局触发数 0）。**两臂同口径降抽样** `WB_MC_ITERS=1500 WB_MC_BUDGET=0.3` → **≈7 秒/场（~35×）**。**必须加「触发计数器」**（`sim_early.py` CHILD 第 5 字段）才能区分「无效果」与「没触发」；触发率对齐真实日志可当**保真度校验**。
- 【★ 10-01 求稳翻前 A/B 终验（#39）】240 组配对 × 2 对手：**观察性估计 +3,450/场 被证伪**（cloud 全场 **+422**，95%CI −556~+1467，符号 36:36；station **−468**，符号 65:43 但均值负 = 重尾）⇒ **无一致证据支持改 `STABILITY_PREFLOP_ON`；待裁决 ① 结案 = 保持现状**。功效边界 CI ≈ ±1,000（+500 量级排除不了）。
- 【★ 对手 code A 画像 10-01】`eff_vpip` 0.70→**0.89**（翻前几乎不弃）、`bets/hand` 0→1.08~1.17 ⇒ **「翻前松、翻后 fit-or-fold」**。可剥削点在**翻后弃牌多**（靠逼弃收 20,256 / 63 手）。全量：靠逼对手弃牌是主要收入（过牌线 +24k、全下线 +24k），摊牌是方差来源。

## 牌型判定
- `_effective_category`：**≥三条不能只由公共牌组成**。`_is_super_hand` = AA/KK/QQ/JJ/AKs；`_is_sub_strong` = AQ/AK/KQ。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。状态机：normal/protect/pressure/desperate/doomed/steal。
- 类别序：高牌<一对<两对<三条<顺子<同花<葫芦<四条<同花顺（★ **顺子 > 三条** —— 影响阈值取值）。

## 工具 / 测试陷阱
> 完整版（含 11 条血泪陷阱与判读顺序）见技能 `~/.workbuddy/skills/poker-strategy-ab/SKILL.md`。
- ★ **`diff_ab.py --off-env <VAR>` 的列方向**：它把 VAR 设为 1 = **关掉改动** ⇒ 输出**第一列（"旧"）其实是候选臂**。对 `WB_NO_XXX` 这类变量 `--labels` 必须反着命名。
- ★★ **「只在被逼到落后时才生效」的规则，用内置对手做配对模拟必然假阴性**（`UA_CROSS_CHECK` 对 cloud 跑 3 局**触发 0 次**）⇒ 用 `sim_early.py --selfab`（自对弈镜像配对）。
- ★★ **跨进程重放自带 ~0.5~1% 噪声下限**（`测/repro_noise.py`）：两臂配置**完全相同**、只换进程，140 点日志差异 1/0/1 点，固定 `PYTHONHASHSEED=0` 无效 ⇒ **凡报「幅度」必须配对照组臂**（净效应 = 实验 − 对照）；**≤1 点不可判读**。「同 seed 连跑两次逐字节一致」**只在同进程内成立**。
- ★ **`_winning_rule()`/`_candidate_rules` 的规则标签只是「会命中」的分类，不等于真正返回的那一行** —— 定位必须关掉候选规则重跑、或直接行级 `sys.settrace`。
- 对手 all-in 在 history 里写**真实金额**（写 `-2` 会让 `to_call` 塌缩）；翻后公牌张数要对（3/4/5）。
- 花色标号**只用于相等比较** ⇒ 任意重标号不影响决策；3 处 docstring 口径不一致（以 `botbattle_log._SUIT` 为唯一权威，属文档瑕疵）。
- 复盘：界面「底池」常是结果态 → 回到决策前；座位需动态检测。`DecisionLogger`：`decide(debug=False)` 会关日志，分析器需 `enable(True) + _quiet=True`。
- **★ 行为指纹判座位**（09-30）：日志双方元数据可能完全相同 ⇒ 把同一批决策点喂给两版，一致率高者为该座位版本。工具 `测/_py311/{fingerprint,verify_hands,diag_shove}.py`。
- **`duel.py` 不可用**（模块级全局/RNG 无法隔离）⇒ 量化只能子进程隔离或真实日志回放。
- **v50 对拍基线（39 场景）**：翻前 0 差异；翻后主动仅尺寸有别。本版更保守：① `_stability_guard` 翻前也压制（已结案保留）；② 强牌加注偏小（280 vs 500）。v50 ELF 指纹 `547e4a6`；pyc 提取流程见 `代码逐行详解.md`。

## 构建发布
- 单文件 `内容/botzone_submit.py`；Linux ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow `build-elf`）产出，artifact `poker_bot-linux-x86-64`（~7MB）。本地无 Docker ⇒ Actions 是唯一发布路径。
- PyInstaller 锁 `<6.22`；【陷阱】artifact 常下成 **22 字节空 zip** ⇒ 解压后核对字节数。
- **★ 平台资源**：1 核 / 512MiB / `/tmp` 256MiB / 无网络 / 60s 每步 ⇒ **保持纯 Python，不引 numpy**。
- `测/学习升级版/poker_bot` 是用户下载的 ELF，**不要动**。

## 模块分工
strategy（决策+安全网）/ game_state（协议）/ opponent（画像+尺寸分桶）/ equity（胜率）/ ranges（169 组合百分位）/ match_ctx（赛制三模块+规则账本）/ evaluator（牌型）/ bot（I/O）。

## 技术判负（09-28）
43 秒 / 7 手、第 7 手零响应。**`ended_at` 只记最后事件时间，60s 超时不计入** ⇒ 真故障 = 最后一步没响应。已加固 `bot.py`（循环永不中断——进程退出＝立即判负）。**根因未定位。**

## 调参入口
`UA_ON`·`UA_SLOPE`·`UA_CALL_DAMP`·`UA_CROSS_CHECK`(`WB_NO_CROSS_CHECK=1`)·`UA_SEALED_ALLIN`·`UA_SEALED_MARGIN` / `CROSS_CHECK_STRONG_PASS`(`WB_NO_CROSS_STRONG_PASS=1`) / `BIG_CALL_LIMIT`·`BIG_MONEY_GUARD_ON`·`BIG_MONEY_TOPTWO_ON` / `DOOM_ALLIN_ON`·`DOOM_TOPTWO_CALL_ON` / **`FLUSH_MADE_PASS`·`PAIRED_TRAP_MADE_PASS`·`BIGMONEY_TWOPAIR_PASS`·`FLUSH_MADE_MIN_CAT`·`FLUSH_MADE_NO_ALLIN`** / `GAMBLE_SHOVE_FOLD_MIN(0.45)`·`GAMBLE_LINE_FACTOR(0.95)` / `RANGE_NARROW_*`·`RANGE_SOFT_TAIL` / `STABILITY_LINE_FACTOR(0.70)`·`STABILITY_PREFLOP_ON` / `LEAD_ALLIN_SHIFT` / `RULE_LEARN_ON` / `OPEN_SIZE_BB(3.5)`。

## 待办 / 已知瑕疵
- **待用户裁决**：① ~~求稳是否只作用翻后~~ **已结案（10-01）**；② 强牌加注尺寸是否调大；③ `to_call==0` 且未见翻牌时是否先过牌看翻牌（手58）；④ **10-11 规则11 豁免是否启用**（推荐开，影响 2/895 点）+ 是否放开「顺子遇全下」与「4/5 张才触发」两条更远改法。
- ★ **内置对手（cloud / station）强于本 bot**（240 组里两臂全场均值都是负的）—— 新暴露的待查项。
- `STABILITY_LINE_FACTOR` 实为 **0.70**（注释陈旧已修）。**打不过 v50** 是首要问题，唯一可信验证 = 用户提供 vs v50 的真实日志。
- `测/学习升级版/poker_bot` 有一处非本轮改动未提交。任务 #38（出口链 KL 锚重构）依据 #37 实测**建议不做**。
