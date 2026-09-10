# 项目长期约定（德扑双人机器人）

## 工作流约定（重要）
- **改动完成后默认推送 GitHub**：用户已确认——每次代码/策略改动完成并测试通过后，默认执行：
  1. `cp 内容/botzone_submit.py botbattle/poker_bot.py`（同步构建源，需 cmp 校验字节一致）
  2. `git add -A && git commit -m "<改动说明>" && git push`
  3. 确认 Actions 自动重建成功（curl API 查 conclusion=success）
  不再需要每次询问用户是否推送。

## 项目关键事实
- 平台：BotZone 德州扑克（bot.tjdfxt.top / BotBattle），双人 HU、70 手赛制、按 total_win_chips 总盈亏定胜负、盲注 50/100、初始筹码 20000。
- 官方协议：牌号 0-51 整数（n//4+2 点数，n%4 花色）；request 字段 num_players/dealer_id/my_id/my_chips/my_cards/public_cards/history/hand/max_hand/total_win_chips/total_win_games；response 为单个整数：-1 fold / -2 allin / 0 call/check / >0 raise（加注量）。只支持 JSON 交互，输入输出均带 requests/response/data/globaldata 包装。每步 1 秒限时。
- raise 语义：纯加注量（跟平之外额外下注）。最小加注：首注≥大盲，再注≥2倍本轮最大加注。有人全押后只能 -1/-2。
- 平台只在轮到我行动时发 request；对手弃牌的手牌不可见 → 需用 globaldata 持久化我方累计净赢按增量推断对手弃牌（+50=对手SB弃、+100=对手BB弃）。

## 构建发布
- 单文件提交版：`内容/botzone_submit.py`（bundle.py 从 8+1 模块打包，含 match_ctx）。
- BotBattle ELF：GitHub Actions（仓库 1331-a/-2，workflow build-elf）自动构建，Ubuntu 22.04 runner，PyInstaller onefile，产物约 7MB，artifact 名 poker_bot-linux-x86-64。
- 本地无法产 Linux ELF（无 Docker/WSL）；GitHub Actions 是标准发布路径。

## 关键决策历史摘要
- 状态机：normal / protect / pressure / desperate / doomed / steal（偷盲，对手疑似锁胜时）。**2026-08-23 已删除 despair，统一用 doomed 公式**。
- 核心策略文件：strategy.py（决策+安全网）、opponent.py（对手画像）、equity.py（MC）、ranges.py（169组合百分位）、match_ctx.py（赛制三模块）、game_state.py（协议解析+合法性推导）。
- 已实现：锁胜弃牌（fold-out）、劣势极限激进、诱敌深入 check-raise、公对风险规避（弱两对）、防输光（加注克制化+全下分层）、逐行读取（防预检超时）。

## 2026-08-28 2倍系数修复（commit 232592a，用户反馈驱动）
- **重大 bug**：lead（我-对手累计净赢差）变化是筹码损失的 **2 倍**（每局弃牌我-X/对手+X→差-2X）；
  `_blind_line` 只返回筹码损失（SB/BB），c6ddf01 精确公式化时直接当 lead 阈值用，少算 2 倍
  （旧 1.5×BB≈2×平均盲注已含系数）。后果：fold_out 剩余1局 lead=60 误弃牌直接输掉。
- **修复**：fold_out `lead > 2×(盲注线+invested)`；doom `lead - 2×invested <= -2×追回线`。

## 2026-08-27/28 锁胜/doom 公式精确化（commit c6ddf01，用户规则·第一层数学硬约束）
- **fold_out**：`lead > 2×(盲注线 + 本局已投入(invested))`（invested=INIT_CHIPS-my_chips；×2 见 232592a）。
- **doom**：`lead - 2×invested <= -2×追回线`（即 lead+2×追回线 ≤ 2×invested）——
  **注意**：用户原式 `lead+追平线+invested ≤ 2×BB` 有误（invested 放错边），已修正。
- 行为：深投入局=生死局（确定锁死→无条件 allin）；规则3 深 pot 降级被 doom 覆盖。
- 影响：约 15 个测试场景改浅投入隔离 doom；全量回归×3、Actions success。

## 2026-08-26 三项规则改动（commit 1a55147，用户规则）
- **注额分级**：HIGH_BET_LIMIT 2000→3000（<三条 总注额≤3000）；新增小两对≤2000
  （`_is_small_two_pair`：两对最大对≤9 或公对弱两对）；≥三条（净化后）/doomed 不限；
  `_bet_limit(state)` 统一上限，`_over_limit` 按 stage 分流（翻前 1000）。
- **doom 无条件 allin**：删除主动侧 steal 施压分流（2026-08-25 分流方案取消）；
  确定性 doom 公式成立 → 无条件 allin（无论主动/被动）。
- **策略学习**：对手每局下注数量（`avg_bets_per_hand`，窗口 12 手）→ 跟注门槛微调
  （≥1.5 收紧 3% / ≤0.7 放宽 2%）；我方赢牌策略标签（aggro/cbet/passive 按翻后
  下注次数）+ 胜负统计 → `strategy_shift` 胜率高者 ±1BB 强化。

## 2026-08-25 防锁赢确定性改造（commit 8ee4b0e / 7733586，覆盖旧版疑似判断）
- **删除 opponent_locking 疑似判断**（收盲率统计不再触发 steal）；强制施压只用确定性 doom 公式。
- **按 to_call 分流**：被动（`_passive_side`：翻前 opp_round_bet>大盲 / 翻后>0 / any_allin）→
  doomed 无条件 allin（第一优先级）；主动 → steal 强制施压防锁赢（第二优先级，优先于 fold_out）。
- **默认盲注修复 200→100**（game_state.py `DEFAULT_BIG_BLIND`）：平台 HU 固定 50/100，
  翻前由 my_total_in 动态推导正确 BB，翻后停留默认值 200 曾致 doom 阈值 2 倍漂移。
- **精确锁赢公式（7733586）** `_blind_line(state, hands, own)`：弃用 1.5×BB×手数 极值估算；
  位置逐局翻转，own=True=小盲次×SB+大盲次×BB（领先方绝对安全线）、
  own=False=小盲次×BB+大盲次×SB（落后方追平线）。
  fold_out: `lead > _blind_line(hands_left)`；doom: `lead-2BB <= -_blind_line(hands_left-1, own=False)`。

## 2026-08-23 策略优先级统一重构（最终决策链，覆盖旧版）
0. **牌型净化（贯穿所有翻后牌型判定）** `_effective_category`：≥三条的牌型不能仅由公共牌组成——board 拼的三条/顺子/同花/葫芦/四条/同花顺（未用手牌）降级 HIGH_CARD（对手必有同款+一张升级牌即败）；应用在强度分层/公对豁免/注额豁免（5处）
1. **doomed 无条件 allin**（确定性 doom 公式 + 我方被动，最高，decide 入口最前）
2. **steal 强制施压防锁赢**（确定性 doom 公式 + 我方主动，>2000 豁免；优先于 fold_out）
3. **>2000 投入限制**（4466168）：仅有效牌型≥三条可投入>2000；例外 = doomed / steal
4. **翻前投入 ≤1000**（8124067）：翻前 raise/call/allin 一律 ≤1000（含超强牌；raise-to 总注额口径），doomed 例外
5. **锁胜弃牌 fold_out**（FOLD_OUT_FACTOR=1.5）
6. **规则2**（盈利锁胜全下）
7. **规则1**（弃牌亏损线 fold 升级 allin 兜底）
8. **状态机** protect/pressure/desperate/normal
9. **河牌公对规则** `_river_paired_trap`：非葫芦/三条/大对≥Q两对 → 对手全下弃牌
10. 常规策略（范围/强度分层/EV门控诈唬/响应学习/前几步钓鱼/对手check小注 min(0.40池,1000)）
11. 安全网 _normalize + 平台合法性兜底

### 重构关键参数（2026-08-23 生效）
- 超强牌 `_is_super_hand` = AA/KK/QQ/JJ/AKs；次强 `_is_sub_strong` = AQ/AK/KQ（仅 desperate/doomed 豁免 1000 上限）。
- **MUST-WIN 已删除**（与 doomed 重叠，且是 allin>2000 泄漏源头）。
- 锁胜系数 2.5→1.5；jumped 警告→eff_req+0.10；延迟施压前置 pnl>-3000 且 fold_to_bet>0.40。
- match_ctx 分阶段：<10手 normal；10-20手放宽（fold>70%）；≥20手正常（>65%）。
- **牌型净化 5ac3ec7→4466168 严格化**：`_effective_category(state)` = `len(board)==5 且 full≥三条 且 full==evaluate_7(board)` → HIGH_CARD（**含三条**，用户明确"纯公共牌组成的牌型降级"）。
