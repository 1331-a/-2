# 项目长期约定（德扑双人机器人）

## 工作流约定（重要）
- **改动完成后默认推送 GitHub**（用户已确认，不必每轮再问）：
  1. `cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`（`cmp` 校验字节一致）
  2. 提交：消息含引号/长文时写 `.git/COMMIT_MSG_TMP.txt` + `git commit -F`（勿直接 `-m`）→ `git push`
  3. 查 Actions 是否 success（GitHub API；未认证会限流，限流就只确认 push 成功并让用户瞄一眼）
- 交付前固定动作：11 个测试文件全量回归（2~3 轮）→ 同步文档（`代码逐行详解.md`、`程序运行逻辑图.html`）→ 更新记忆。

## 项目关键事实
- 平台：BotBattle / BotZone 德州扑克；HU 双人、70 手、按 `total_win_chips` 总盈亏定胜负、盲注 50/100、初始 20000。
- 协议：牌号 0-51（`n//4+2` 点数，`n%4` 花色 0=♠1=♥2=♦3=♣）；request：num_players/dealer_id/my_id/my_chips/my_cards/public_cards/history/hand/max_hand/total_win_chips/total_win_games；response 单整数（-1 fold / -2 allin / 0 call·check / >0 raise）；JSON 带 requests/response/data/globaldata 包装；每步 1 秒限时。
- `hand` 是 **0-based**（界面显示 hand+1）；`_hands_left = max_hand − hand − 1`。
- history 里 `amount` 是**本街累计总额**（raise-to 语义）；`hand_start.chips` 已扣盲注。
- 只在我方行动时收 request；对手弃牌不可见 → globaldata 持久化我方净赢，按增量推断（+50 = 对手 SB 弃、+100 = 对手 BB 弃）。

## 构建发布
- 单文件提交版 `内容/botzone_submit.py`（`bundle.py` 打包 8+1 模块）；ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow build-elf）构建，artifact `poker_bot-linux-x86-64`（约 7MB）。
- 本地产不出 Linux ELF（无 Docker/WSL）→ Actions 是唯一发布路径。`测/学习升级版/poker_bot` 是用户下载的 ELF，不要动。

## 模块分工
strategy.py（决策+安全网）/ game_state.py（协议解析+合法性推导）/ opponent.py（画像 + 尺寸分桶反应统计）/ equity.py（MC 胜率）/ ranges.py（169 组合百分位）/ match_ctx.py（赛制三模块 + 规则账本）。

## 锁赢 / doom 数学（第一层硬约束，用户规则）
- lead = 我方 net − 对手 net；**筹码损失 → lead 变化是 2 倍**（我 −X、对手 +X → 差 −2X）。比较时两边口径必须一致（都用筹码或都用 lead），`×2` 只能用一次。
- 追回线 `_blind_line(hands_left, own=False)`：按位置轮换精确算落后方能捡回的盲注（固定 SB=50/BB=100，勿用 `state.big_blind`——翻前会被推导污染）。
- **fold_out 锁胜**：`lead > 2×(盲注线 + invested)` → fold。
- **doom**：`lead − 2×敞口 ≤ −2×追回线`；敞口按口径取 `_invested`（弃牌口径 → `_match_adjust` / 盈利锁胜）或 `_exposure = invested + to_call`（跟注口径 → `_doom_call_upgrade`）。
- **doom 判定只用原始 lead**（`lead_raw`）：match_ctx 阈值偏移只作用于 protect/pressure/desperate 软阈值（ff7509d，因第66手把「弃牌只亏 100」误判成 doomed）。

## 当前规则清单（按生效顺序）
1. **规则2 锁赢/防锁赢 `_lock_win_unified`**（decide 入口，先于胜率计算）：fold_out 锁胜 → fold（`to_call==0` 用 check）；**A 防锁赢（doomed）→ 无条件 allin**（带 `lk=1` 免检，`_normalize` 直接放行；用户硬规则，不给便宜跟注豁免）；C 盈利锁胜与 A 同式（死代码，可清理）。
2. **规则2-B 便宜跟注封顶 `_doom_exposure_cap`**（2026-09-24）：敞口 doom 成立时，若 `to_call ≤ DOOM_CAP_STACK_FRAC(0.15) × 我方剩余` 且手牌不强（`_doom_hand_strong`：翻后 ≥两对 / 翻前超强）→ **call**（不加注不全押）；强牌 / 跟注本身重投入 / 跟即全下 → allin。作用点 `_doom_call_upgrade`。
3. **方案B `_doom_bet_downgrade`**：`to_call == 0` 且本次投入会让 doom 成立 → check。
4. **规则10 求稳 `_stability_mode`**（`STABILITY_LINE_FACTOR=0.60` 或剩 ≤8 手且领先）→ `_stability_guard`：主动侧 check、被动只跟；强牌例外。
5. **规则16 放宽**：剩局少 / 对手爱 all-in → 跟全下门槛 −，上限 0.09。
6. **规则17 盈利收紧 `_lead_allin_shift`**（翻后跟 all-in 叠加）：>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08。
7. **规则18/18b 搏命区**：`lead < 0 且 ≤ −0.95 × 2×追回线` → 整手在区内；牌烂 → 立即 allin（带 lk）；牌好 → 能过牌就 check、翻前补大盲 call、遇下注或河牌免费则 allin。
8. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本≥4）→ 停用四条小注路线（`_opp_check_bet` / `_blocking_bet_proxy` / `_lead_bet_proxy` / `_probe_bet_proxy`）；价值注不受影响。
9. **规则学习**（`match_ctx.rule_stats` 跨手持久化）：样本≥4 且胜率 <0.35 的「输的规则」→ 只把 raise 降级为跟/过；胜率 >0.60 的规则优先复用；fold/check/call/allin 及硬规则、兜底标签不参与。
10. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束我方主动下注/shove**——跟注与应对对手 all-in 一律豁免（2026-09-14 用户规则：定向决策替换所有旧限制）。
11. 安全网 `_normalize`（合法性夹紧）+ `_allin_floor_guard`（仅主动 shove：累计投入 ≤ 盈利+1000 → fold）。

## 牌型与强度判定
- `_effective_category`：**≥三条的牌型不能只由公共牌组成**（board 独自拼出的三条/顺/花/葫芦降级 HIGH_CARD）。
- `_is_super_hand` = AA/KK/QQ/JJ/AKs；`_is_sub_strong` = AQ/AK/KQ。
- 公对风险：`should_avoid_risk`（弱两对走保守路线）+ 河牌裸公对陷阱 `_river_paired_trap`；**≥三条不算弱两对**（葫芦 222JJ 曾误判弃牌）。
- 状态机：normal / protect / pressure / desperate / doomed / steal（despair 已删）；`opponent_locking` 疑似判断已删（防锁赢只用确定性 doom 公式）。

## 工具 / 测试事实与陷阱
- 【测试陷阱】history 里对手 all-in 必须写**真实金额**；写 `-2` 会让 `to_call` 塌缩（2026-09-16 已修：金额未知 → 按「对手推光、需跟全部筹码」保守口径）。
- 【测试陷阱】翻后场景公牌张数要对（3=flop/4=turn/5=river），否则 stage 不符、规则不触发。
- 【复盘工具】`botbattle_log.load_botbattle` 逐决策点重放；投入**按街累加**（勿用本街最大值）。
- 【复盘口径】界面「底池」常是**结果态**（all-in 之后）→ 必须回到决策前（第51手：界面 20,592，实际 992）。
- 【教训】盘上行为与代码不符时先穷举输入形态（金额缺失 / `my_id` 反转 / 字段类型），再怀疑规则；用 `git archive` 拉历史构建逐个回放可区分「版本问题」与「输入问题」。
- 【教训】确定性硬规则（doom/锁赢）的输入必须用客观原始值；「赛制/风格偏移」只能改软阈值。
- 【标签】日志里的「规则1/4 大注弃牌」是 `_winning_rule()` 的兜底标签，不是真规则。
- 【翻后跟 all-in 判定顺序】规则2 → 河牌裸公对陷阱 → 公面同花威胁 → 突袭大注（eq 打折 0.15、牌型<三条直接弃）→ `thr = eff_req + margin ± 档位 + 规则17 − 规则16`。
- 【调参入口】`DOOM_CAP_STACK_FRAC` / `GAMBLE_LINE_FACTOR`·`GAMBLE_GOOD_PCT` / `STABILITY_LINE_FACTOR` / `LEAD_ALLIN_SHIFT` / `SMALL_BET_FOLD_MIN` / `RULE_MIN_SAMPLES`·`RULE_BAD_WR`·`RULE_GOOD_WR`·`RULE_LEARN_ON`。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。
- 【测试稳定性】MC 600 次抽样会让贴门槛的断言偶发翻转（>=10/20 → >=20/40 或改直测底层函数/极端值）。

## 待办 / 已知瑕疵
- `_profit_lock_allin`（C 分支）等价于 A 分支 → 死代码，可清理。
- 2026-08 的旧日志（08-17 ~ 08-24）按维护规则应蒸馏后删除，但用户常用它们做「当时版本行为」取证 → 暂保留。
