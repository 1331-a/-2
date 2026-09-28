# 项目长期约定（德扑双人机器人）

## 工作流约定（重要）
- **改动完成后默认推送 GitHub**（用户已确认）：
  1. `cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`（`cmp` 校验字节一致）
  2. 提交：长文消息写 `.git/COMMIT_MSG_TMP.txt` + `git commit -F`（勿直接 `-m`）→ `git push`
  3. 查 Actions 是否 success（GitHub API 未认证会限流；限流就只确认 push 成功并让用户瞄一眼）
- 交付前固定动作：12 个测试文件全量回归 → 同步 `代码逐行详解.md` + `内容/程序运行逻辑图.html` → 更新记忆。
- 冒烟必须用**正确 history 格式**（dict 含 player_id/action_type/amount/round）；扁平 list 会让 GameState 抛错、bot 静默返回 0，看起来像回归。

## 平台与协议
- BotBattle/BotZone HU 德州：70 手、按 `total_win_chips` 总盈亏定胜负、盲注 50/100、初始 20000、每步 1 秒。
- 牌号 0-51（`n//4+2` 点数，`n%4` 花色 0=♠1=♥2=♦3=♣）；response 单整数（-1 fold / -2 allin / 0 call·check / >0 raise）；JSON 带 requests/response/data/globaldata 包装。
- `hand` 是 **0-based**（界面显示 hand+1）；`_hands_left = max_hand − hand − 1`。
- history 里 `amount` 是**本街累计总额**（raise-to 语义）；`hand_start.chips` 已扣盲注。
- 只在我方行动时收 request；对手弃牌不可见 → globaldata 持久化我方净赢，按增量推断（+50 = 对手 SB 弃、+100 = 对手 BB 弃）。

## 构建发布
- 单文件 `内容/botzone_submit.py`（`bundle.py` 打包 8+1 模块）；Linux ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow build-elf）产出，artifact `poker_bot-linux-x86-64`（~7MB）。本地无 Docker/WSL → Actions 是唯一发布路径。
- PyInstaller **锁 `<6.22`**（6.22.x 的 onefile 引导器加了父进程校验，产物在受限沙箱秒退）；构建含冒烟自检 + glibc 兼容报告。
- 【陷阱】artifact 常下成 **22 字节空 zip**（`PK\x05\x06`）→ 上传前解压核对字节数。
- `测/学习升级版/poker_bot` 是用户下载的 ELF，不要动。

## 模块分工
strategy.py（决策+安全网）/ game_state.py（协议解析+合法性推导）/ opponent.py（画像+尺寸分桶反应）/ equity.py（MC 胜率）/ ranges.py（169 组合百分位）/ match_ctx.py（赛制三模块+规则账本）/ evaluator.py（牌型）。

## 锁赢 / doom 数学（第一层硬约束，用户规则）
- lead = 我方 net − 对手 net；**筹码损失 → lead 变化是 2 倍**（我 −X 对手 +X → 差 −2X）。比较时两边口径必须一致，`×2` 只能用一次。
- 追回线 `_blind_line(hands_left, own=False)`：按位置轮换算落后方可捡回的盲注（固定 SB=50/BB=100，**勿用 `state.big_blind`**，翻前会被推导污染）。
- **fold_out 锁胜**：`lead > 2×(盲注线 + invested)` → fold。
- **doom**：`lead − 2×敞口 ≤ −2×追回线`。敞口按口径取 `_invested`（弃牌口径 → `_match_adjust`/规则2-A·C）或 `_exposure = invested + to_call`（跟注口径 → `_doom_call_upgrade`）。
- **doom 判定只用原始 lead**（`lead_raw`）：match_ctx 偏移只作用于 protect/pressure/desperate 软阈值（ff7509d）。

## 当前规则清单（按生效顺序）
1. **规则2 `_lock_win_unified(state, model)`**（decide 入口，先于胜率计算）：
   B. fold_out 锁胜 → fold（`to_call==0` 用 check，平台不允许弃牌）；
   A. doomed → `_doom_plan(state, model)`；
   C. `_profit_lock_allin` → `_doom_plan(state, model)`（**与 A 完全同一个函数**，`allow_free` 参数已删）。
   ★【2026-09-28 v3】`_doom_plan` 的分界 = **「弃牌是否立死」+ 牌力分流**（用户当天推翻 v2 的越线幅度门控：
     「既然已经越线了还投入就应该 allin，因为如果输了也是全局的」——doom 成立即「输了全局输」，与越线 2.8% 还是 28% 无关）：
     · `to_call > 0`（必须再投入）→ **一律 allin**，无论牌多烂。唯一例外：牌好且翻前只需补大盲 → call（溜入慢打）。
     · `to_call ≤ 0`（能免费过牌）→ **看牌质量**（用户原话「质量不好就直接 allin，质量好就再看看」）：
       牌烂 → 直接 allin（仍过 `_shove_fold_ok`）；牌好 → **None「再看看」**；**牌好且河牌 → 收网 allin**（最后一街没得等）。
     · `line≤0`（最后一手）→ 直接 allin；`DOOM_ALLIN_ON=False` / `DBG_NO_DOOM_ALLIN=1` → 回退旧无条件全押。
     · v2 的 `DOOM_ALLIN_MIN_MARGIN/FOLD/FOLD_SAMPLES` 已**全部删除**。
   ★ A 被拒后**必须 return None**：`_profit_lock_allin` 用的是同一个 `_doom_risk` 不等式，继续往下走 C 会原样绕过（局2 #43 由此后门推出 19,500）。
   ★ 异常兜底 `_safe_fallback_action` 仍是无条件 allin（只在决策层抛异常时走）。
   ★【2026-09-28 复核】`_big_money_guard` **故意不给 `lk` 开免检口**——规则20（弱牌不许主动推光）从 2026-09-24 起就压过 `UA_SEALED_ALLIN`（见 test_log_v2「0924第21/32手」）。规则2/18 都在出口链**之前**短路返回（`_decide_impl` 里 `_gamble_plan` 命中即 `return _normalize(...)`），不会流到 guard。
2. **终局效用仲裁 `_endgame_arbitrate`（2026-09-24）**：出口把弃/过/跟/加/全押放同一尺度比较 EU（`_win_utility`：lead→最终胜率 U，logistic 平滑无悬崖；锚点 ±2×_blind_line），取最优。
   · EU：fold/check = `lead−2×已投`；跟注 = eq×U(收池)+(1−eq)×U(输敞口)；加注/全押 = f×U(收池)+(1−f)(eq_c×U(赢大池)+(1−eq_c)×U(输更多))，`f=弃牌权益`，`eq_c=eq^(1+UA_CALL_DAMP×n/底池)`（幂次保证坚果不受罚）；对手已全押时 f=0。
   · 护栏顺序：① `UA_CROSS_CHECK`（免费过牌且投入即越线 → 过牌）；② `UA_SEALED_ALLIN`（越线幅度 ≥ `UA_SEALED_MARGIN(0.15)` → 全押）；③ 只往更保守方向修正（`UA_RISK_RANK`，不制造新加注/全押）；④ 硬性弃牌（河牌公对陷阱/突袭大注/公对规避）不翻案。
   · 触发面 `_endgame_matters`：敞口 doom / 投入即锁赢 / 搏命区。
   · 调参：`UA_ON` / `UA_SLOPE(1.6)` / `UA_CALL_DAMP(0.6)` / `UA_CROSS_CHECK` / `UA_SEALED_ALLIN` / `UA_SEALED_MARGIN(0.15)`。链路文档：`内容/端到端策略链.md`。
3. **规则10 求稳 `_stability_mode`**（`STABILITY_LINE_FACTOR=0.70`［2026-09-28 由 0.60 回调，v50 是 0.80，取折中：更晚求稳、领先时更敢打；改回 0.60 即恢复「更早求稳」］或剩 ≤8 手且领先）→ 主动侧 check、被动只跟；强牌例外。
4. **规则16/17**：剩局少或对手爱 all-in → 跟全下门槛 −（上限 0.09）；翻后跟 all-in 按盈利档叠加（>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08）。
5. **规则18 搏命区**：`lead ≤ −0.95×2×追回线` → 整手在区内；牌烂 → allin（带 lk）；牌好 → 能过牌就 check、翻前补大盲 call、遇下注或河牌免费则 allin。
   ★【2026-09-28】牌烂推之前先过 `_shove_fold_ok(state, model)`：**`eff_fold_to_bet ≥ 0.45`**（样本 ≥6 才门控）才推；被逼全下 / 无画像 / 剩 ≤`GAMBLE_SHOVE_FORCE_HANDS(8)` 手豁免（末段逃生口）。
6. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本≥4）→ 停用 `_opp_check_bet`/`_blocking_bet_proxy`/`_lead_bet_proxy`/`_probe_bet_proxy`；价值注不受影响。
7. **规则学习**（`match_ctx.rule_stats` 跨手持久化）：样本≥4 且胜率 <0.35 的输规则 → 只把 raise 降级为跟/过；胜率 >0.60 优先复用；fold/check/call/allin 及硬规则不参与。
8. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束我方主动下注/shove**，跟注与应对对手 all-in 豁免。开池 3.5BB 后 3-bet 更早撞 1000（对手开 350 → 目标 1050 被夹到 1000；对手 800 → 无法合法加注，降级 call）。1000 是用户规则，未擅改。
9. **规则20 大额闸门 `_big_money_guard`**（出口最后一步，在仲裁之后）：R1 `to_call > BIG_CALL_LIMIT(3000)` 且牌型 <三条 → fold；R2 **主动**全押只在 [≥三条 / 翻前 AA·KK·QQ·JJ·AKs] 允许，否则降级。豁免：应对对手全下（`any_allin` 或 `to_call ≥ my_left`）。防锁赢/搏命区在入口 return，不受影响。
10. **规则2 补漏 `_doom_call_upgrade`**（出口最后一步，2026-09-28 ef67a93）：跟注口径 doom 成立 → 不许便宜跟注；只改写 call，强牌 → allin(lk)、弱牌 → fold。开关 `DOOM_CALL_UPGRADE_ON`（`DBG_NO_DOOM_UPGRADE=1` 关）。搏命区与规则2-A 在入口 return，不经过它。
11. 安全网 `_normalize`（合法性夹紧）+ `_allin_floor_guard`（仅主动 shove：累计投入 ≤ 盈利+1000 → fold）。

## 牌型与强度判定
- `_effective_category`：**≥三条不能只由公共牌组成**（board 独自拼出的三条/顺/花/葫芦降级 HIGH_CARD）。
- `_is_super_hand` = AA/KK/QQ/JJ/AKs（＝`_strong_for_big_money` 的翻前口径）；`_is_sub_strong` = AQ/AK/KQ。
- 公对风险：`should_avoid_risk`（弱两对走保守）+ `_river_paired_trap`；**≥三条不算弱两对**（葫芦 222JJ 曾误判弃牌）。
- 状态机：normal / protect / pressure / desperate / doomed / steal（despair、`opponent_locking` 已删）。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。

## 对手画像与胜率
- 【翻前尺寸·2026-09-25 方案B】`OPEN_SIZE_BB=3.5` / `OPEN_SIZE_VS_STATION=3.0` / `ISO_SIZE_BB=4.0` / `STEAL_OPEN_BB=3.0`；**学习代表值 `opponent.bucket_to_frac` 翻前 = 2.5/3.5/4.5**。
  ★**只改 `OPEN_SIZE_BB` 无效**——`_learned_size`（学习优先）会用 `bucket_to_frac` 覆盖它。
- 【条件化·2026-09-26 48914c0】开池再乘对手权重 `clamp((0.80−eff_vpip)/0.25,0,1)` × 样本门控 `min(1, hands_seen/8)` → `_open_size_bb ∈ [2.5, 3.5]` 插值；学习尺寸一并折减。对手硬跟→2.5BB，爱弃→3.5BB，**前 8 手不生效**。
- 【A 条件化·2026-09-26】`_future_cost` 折算额按 `_future_aggr_factor(model)` 缩放（`avg_bets_per_hand` → [0.15,1.0]）；听牌也计入折算，隐含赔率加成取消（`FUTURE_DRAW_IMPLIED_CAP=1.0`）——原实现两套条件作用集合不相交，听牌从未被 A 触及。
- 【A 感知硬规则·2026-09-26 **默认关闭**】`BIG_BET_FOLD_A_ON=False`：隔离检验未通过（连街开火型 +1917 p=0.734 不显著 / 中等尺度型 −862 p=0.036 显著为负；加门控收益砍 35% 而亏损未减 → 收益与亏损同源）。`WB_FORCE_BIGBET_A=1` 可再启用。
- 【2026-09-28】`_opp_range_pct(model, raised_pf, street_raises)` **计入本街加注**：`_opp_street_raises(state)` 统计当前街对手 raise/allin/bet 次数（上限 3），每次按 `per=0.45−0.30×agg`（clamp 0.20~0.40）收窄，总收窄 `base×(1−per)^n`。修掉「对手连开三枪仍按宽松范围算 eq」的高估（三局 162 个翻后点中 40 个=25% 受影响，收窄约 35%，关键手 eq 下修 0.06~0.10）。
- 对手模型叠加后跟注门槛可从 0.39 压到 ~0.20（maniac −0.08、规则16 −0.09、被动 −0.02）。

## 工具 / 测试陷阱
- history 里对手 all-in 必须写**真实金额**；写 `-2` 会让 `to_call` 塌缩（金额未知 → 按「对手推光、需跟全部筹码」保守口径）。
- 翻后场景公牌张数要对（3/4/5 = flop/turn/river），否则 stage 不符、规则不触发。
- 复盘：`botbattle_log.load_botbattle` 逐决策点重放，投入**按街累加**；界面「底池」常是结果态（all-in 后）→ 必须回到决策前。
- `DecisionLogger`：`decide(debug=False)` 会**关掉**日志并覆盖手动 enable；分析器需 `enable(True) + _quiet=True`。
- 日志里的「规则1/4 大注弃牌」是 `_winning_rule()` 的兜底标签，不是真规则。
- MC 600 次抽样会让贴门槛断言偶发翻转 → 加大迭代或直测底层函数/极端值。
- 验证某规则是否提前 return，不能拿最终动作当判据（别的规则也会导致同样动作），要看 `WB_FACE_LOG` 有无记录。
- 盘上行为与代码不符时先穷举输入形态（金额缺失 / my_id 反转 / 字段类型），再怀疑规则。
- 旧 ELF 指纹：`PyInstaller.archive.readers.CArchiveReader(path).extract('poker_bot')` 取主脚本后 grep 变量名（比回放命中率可靠，回放受 MC 噪声影响）。已定位 v50 = `547e4a6`。
- 【复盘工具】`内容/analyze_matches.py`：`load_botbattle(path, my_seat)` / `detect_seat(obj)` / `replay_decisions(path, seat)`；座位需动态检测（三局分别是 1/0/0）。
- 【原始 replay 事件字段（与 request 不同！）】action 事件是 `player`/`action`/`amount`（**不是** player_id/action_type，写错会静默匹配 0 条）；deal_hole 是 `holes:[[座0],[座1]]`（卡面字符串如 "7d"）；hand_start 带 `sb`/`bb`/`chips`；settle 的 `net`=累计 total_win_chips（平台计分口径）、`deltas`=本手、`winners`。我方=owner 含 j1331 的一侧（测01），fffmvp5/hhhmvp 是对手。

## 调参入口
`UA_ON`·`UA_SLOPE`·`UA_CALL_DAMP`·`UA_CROSS_CHECK`·`UA_SEALED_ALLIN`·`UA_SEALED_MARGIN` / `BIG_CALL_LIMIT`·`BIG_MONEY_GUARD_ON` / `DOOM_ALLIN_ON` / `GAMBLE_SHOVE_FOLD_MIN(0.45)`·`GAMBLE_SHOVE_FORCE_HANDS(8)` / `RANGE_NARROW_*` / `GAMBLE_LINE_FACTOR`·`GAMBLE_GOOD_PCT` / `STABILITY_LINE_FACTOR` / `LEAD_ALLIN_SHIFT` / `SMALL_BET_FOLD_MIN` / `RULE_MIN_SAMPLES`·`RULE_BAD_WR`·`RULE_GOOD_WR`·`RULE_LEARN_ON`。

## 待办 / 已知瑕疵
- 2026-09-25 方案 A（future_cost）与方案 B（开池 3.5BB）配对模拟**均未证明**能降低前 20 手累积亏损（A 改动面 2~6% 方向混杂；B 改动面 18.9% 中位略差、95%CI 横跨 0）。未推送，等用户决定去留。
- `测/学习升级版/poker_bot` 有一处非本轮改动未提交，需用户确认。
- 2026-08 旧日志按维护规则应蒸馏后删除，但用户常用它们做「当时版本行为」取证 → 暂保留。
