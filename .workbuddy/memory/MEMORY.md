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

## 2026-09-14 面对对手 all-in 的定向决策优先级（commit ccaf8ae，用户规则）
- **核心原则**：凡是「面对对手 all-in」的定向决策（规则2 锁赢/防锁赢、规则16+`_preflop_allin_decide` 跟全下、翻后全下分支）→ **替换此前所有针对 allin 的限制**（翻前 1000 上限、翻后 `_bet_limit` 牌型上限），`_normalize` 不再二次降级。
- **锁赢 allin 免检标记 lk**：`_lock_win_legal` 给锁赢 allin 打 `lk=1`，`_normalize` 见标记直接放行——修「ctx 保守偏移 → `_match_adjust` 非 doomed → doom 的 allin 被降级成 fold」。
- **仍保留限制的是我方主动 shove**（无人全押、to_call < my_left → 仍按 1000/牌型上限降级）。
- **盈利锁胜 C 分支 = 死代码**：`_profit_lock_allin(state)` 就是 `_doom_risk(state)`；自 ff7509d 起 A 分支（`_match_adjust=='doomed'`）也改用原始 lead → 两者完全等价，C 永不单独生效（以后可清理）。
- 【测试陷阱】history 里 allin 必须写**真实金额**（写 -2 会让 to_call 塌缩为 1，赔率失真 → 弱牌也判跟注）。

## 2026-09-14 补充修复（commit ff7509d）
- **doom 判定只用原始 lead**（`lead_raw`）：`_match_adjust` 里 ctx 偏移只作用于 protect/pressure/desperate 阈值，**不再参与 doomed 判定**。原因（截图第 66 手）：ctx 激进偏移 -6BB 把「弃牌只损失 100、完全安全」的局面压成 doomed → 拿 10 高牌（两头顺听牌）无条件 allin 19900。
- **规则10 强化**：`STABILITY_LINE_FACTOR=0.60`（原硬编码 0.8）+ 新增「剩 ≤8 手且领先」也求稳；求稳时主动侧一律 check（取消「对手过牌 → 强制小注」）；新增 `_stability_guard` 禁止主动加注/主动全下，被动侧只跟（强牌例外：翻后有效牌型 ≥ 两对 / 翻前 AA·KK·QQ·JJ·AKs）。

## 2026-09-14 全下下限豁免 + 弱两对判定修复（commit dd24755）
- **`_allin_floor_guard` 只约束主动 shove**：「跟对手全下」（`any_allin` 或 `to_call ≥ my_left`）直接放行——否则四条/葫芦这类必胜牌会因「累计投入 ≤ 盈利+1000」被降级成 fold（实测四条弃于 3000 注）。
- **`should_avoid_risk` 增加 ≥三条 豁免**：手牌 22 + 公面 JJ2 = 葫芦(222JJ) 原被判「弱两对」→ 走 `_risk_avoid_route` 弃牌；现在有效牌型 ≥ 三条一律不算弱两对。
- 保留：两对面对「突袭大注」（`_OPP_JUMPED` + 牌型 < 三条）仍 fold（用户 2026-09-04 规则）。

## 2026-09-15 规则17：盈利越多，跟 all-in 条件越严格（commit d03d60b）
- 翻后「跟 all-in」新增 `_lead_allin_shift(state)` 增量（叠加在底池赔率要求之上）：
  `thr = eff_req ± 档位修正 + shift − 规则16放宽`
  · lead > +50BB → **+0.12**（只跟坚果级）· lead > +10BB → **+0.07**
  · |lead| ≤ 10BB → **+0.02** · lead < −10BB → **−0.03** · lead < −50BB → **−0.08**
- 档位边界复用翻前 `ALLIN_THR` 的 50BB/10BB；**翻前不叠加**（本身已是绝对门槛分档 0.75/0.65/0.55/0.50/0.40）。
- 与规则16（剩局少/对手爱 allin → 放宽，上限 0.09）独立叠加，终局时部分抵消。

## 2026-09-15 规则2 扩展·方案B：主动下注若「投进去就锁赢」→ 过牌（commit afc63de）
- 新增 `_doom_bet_downgrade`：`to_call == 0`（有免费过牌）+ 决策层要 raise/allin + `_doom_risk(state, extra=本次额外投入)` 成立 → **check**（不投入就不过线）。
- `_doom_call_upgrade`（已有）负责另一半：`to_call > 0`（对手已加注、过不了牌）且跟注即锁赢 → **allin**；它只升级 call/raise，决策层判 fold 时不动（弃牌只损失已投部分）。
- `_doom_risk` 新增 `extra` 参数（敞口 += extra），复用同一不等式。
- **转换器 bug 修复**（影响所有复盘）：`botbattle_log` 原把「本街累计注额」当本手投入（跨街不累加）→ 改为按街累加；第9手重放 invested 由 328 → **906** 正确。
- 【测试陷阱】日志 `action.amount` 是**本街**累计总额；`hand_start.chips` 已扣盲注。
- 实测（截图第23手三条8，对手突袭全押，eq 打折 0.15）：大领先 → fold；均势/落后 → allin。

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
3. **>2000 投入限制**（4466168）：仅有效牌型≥三条可投入>2000；例外 = doomed / steal。（**2026-09-14 起仅约束「主动下注/shove」**——跟注或应对对手 all-in 已豁免，见上节）
4. **翻前投入 ≤1000**（8124067）：翻前 raise/call 一律 ≤1000（含超强牌；raise-to 总注额口径），doomed 例外。（**2026-09-14 起不再约束「跟对手全下」**）
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
