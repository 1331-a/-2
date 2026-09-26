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
- 【翻前尺寸·2026-09-25 方案B】`OPEN_SIZE_BB=3.5`（2.5→3.5）/ `OPEN_SIZE_VS_STATION=3.0`
  / `ISO_SIZE_BB=4.0`（必须 ≥ 开池）/ `STEAL_OPEN_BB=3.0`；**学习模块代表值
  `opponent.bucket_to_frac` 翻前 = 2.5/3.5/4.5**（原 2.2/3.0/4.0）。
  ★**只改 `OPEN_SIZE_BB` 无效**——`_learned_size`（学习优先）会用 `bucket_to_frac`
  **覆盖**它（线上开池 300 = 学习选了 pf_m 的 3.0BB，不是 OPEN_SIZE_BB）。
  分桶边界（pf small≤2.5 / med≤4）不变，3.5 仍落 med 桶。
- 【条件化·2026-09-26 **已上线** 48914c0】开池尺寸**再乘对手权重**：
  `_open_weight` = clamp((0.80−eff_vpip)/0.25, 0, 1)，再乘**样本门控**
  `min(1, hands_seen/OPEN_SAMPLE_HANDS(8))` → `_open_size_bb` 在
  `[OPEN_SIZE_HARD_CALL_BB(2.5) .. OPEN_SIZE_BB(3.5)]` 间插值；
  **学习尺寸一并折减** `preB + w×(learned−preB)`，`_B_PRE_FRAC={2.5:2.2,3.5:3.0,4.5:4.0}`。
  效果：对手硬跟→回退 2.5BB；爱弃→3.5BB；**前 8 手不生效**（开局不凭先验多送钱）。
- 【A 条件化·2026-09-26 已上线】`_future_cost(state, to_call, model)` 折算额按
  `_future_aggr_factor(model)` 缩放（`avg_bets_per_hand` 映射到 [0.15,1.0]）：
  被动对手（不连街开火）→≈0；持续施压→满额。
- 【听牌缺口修正·2026-09-26 已上线】原 `future_cost` 只在 `not big_draw` 计入、
  而 `implied=1.4` 只给 `big_draw` → **作用集合不相交**，听牌（最容易被赶走的牌）
  从未被 A 触及。现听牌也计入折算并取消隐含赔率加成（`FUTURE_DRAW_IMPLIED_CAP=1.0`）。
- 【A 感知硬规则·2026-09-26 **默认关闭**】`BIG_BET_FOLD_A_ON=False` ——
  「大注+无坚果→弃」仍是原样 `to_call > 0.6×池` 一刀切。
  **隔离检验未通过**：连街开火型 +1917（p=0.734 不显著）/ 中等尺度型 −862
  （p=0.036 显著为负）；加门控 0.60 后收益被砍 35% 而亏损未减 → 收益与亏损
  **同源**，无法按对手激进度分离。代码/门控/测试保留，`WB_FORCE_BIGBET_A=1` 可再启用。

## 构建发布
- 单文件提交版 `内容/botzone_submit.py`（`bundle.py` 打包 8+1 模块）；ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow build-elf）构建，artifact `poker_bot-linux-x86-64`（约 7MB）。
- 本地产不出 Linux ELF（无 Docker/WSL）→ Actions 是唯一发布路径。`测/学习升级版/poker_bot` 是用户下载的 ELF，不要动。
- 【2026-09-24 起】PyInstaller **锁定 `<6.22`**（原 `>=6.10,<7` 浮动 → 6.22.x 给 onefile 引导器加了「父进程安全校验」，产物在受限沙箱里会秒退/exec 失败）；构建新增**冒烟自检**（真跑 ELF 断言能应答；失败即构建失败）+ 兼容性报告（glibc/ldd/所需最高 GLIBC 符号版本）。
- 【下载陷阱】Actions artifact 常下成 **22 字节空 zip**（`PK\x05\x06`）——上传前必须解压核对 `poker_bot` 字节数，别直接传 zip。

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
2. **终局效用仲裁 `_endgame_arbitrate`（2026-09-24，取代两个旧补丁）**：决策出口把
   **弃牌 / 过牌 / 跟注 / 加注 / 全押**放在同一尺度（`_win_utility`：lead → 最终胜率 U，
   logistic 平滑、无「线上1线下0」悬崖；锚点 = ±2×_blind_line）比较 EU，取最优。
   · EU 分支：fold/check = `lead−2×已投`；跟注 = eq×U(收池) + (1−eq)×U(输敞口)；
     加注/全押 = f×U(收池) + (1−f)(eq_c×U(赢大池) + (1−eq_c)×U(输更多))，
     `f=弃牌权益`，**`eq_c = eq^(1+UA_CALL_DAMP×n/底池)`**（超池全押被跟 = 已输；
     用幂次保证 eq=1 的坚果不受惩罚）；对手已全押时 f=0。
   · 四条护栏（按执行顺序）：① `UA_CROSS_CHECK`（有免费过牌且投进去就越线 → 过牌，09-15 方案B）；
     ② **`UA_SEALED_ALLIN` 防锁赢：越线 → 无条件全押** —— `_sealed_by_call` 要求越线幅度
     ≥ `UA_SEALED_MARGIN(0.15)`×2×追回线 才算「明显被锁」（第32手越线 61% → 全押 ✓；
     第51手越线 3.9% = 擦线 → 不触发）；设 0 = 只要越线就全押；
     ③ 效用比较只往「更保守」方向修正（UA_RISK_RANK，不制造新加注/全押）；
     ④ 硬性弃牌（河牌公对陷阱/突袭大注/公对风险规避）不被翻案。
   · **顺序**（用户 2026-09-24 强调）：先判「弃牌会不会被锁赢」（入口规则2-A）→ 再判
     「继续投入会不会越线」（②）→ 都非硬约束才轮到效用比较。
   · 触发面 `_endgame_matters`：敞口 doom / 投入即锁赢 / 搏命区；不触发则完全不动常规策略。
   · 已删除的旧补丁：`_doom_call_upgrade`（call/raise→allin，单向更激进、弃牌从不参与）、
     `_doom_bet_downgrade`（raise→check）。
   · 第51手实测 EU：弃牌 0.190 / 跟注 0.286(0.412 收池) / 加注576 0.322 / **全押 0.188（最差）**
     → 12 次决策 0 次全押。
   · 调参：`UA_ON` / `UA_SLOPE(1.6)` / `UA_CALL_DAMP(0.6)` / `UA_CROSS_CHECK` /
     `UA_SEALED_ALLIN` / `UA_SEALED_MARGIN(0.15)`。
   · 端到端链路文档：`内容/端到端策略链.md`（平台输入 → bot.py → game_state → decide → 输出）。
3. **方案B `_doom_bet_downgrade`**：已并入 `_endgame_arbitrate` 的 `UA_CROSS_CHECK`
   硬规则（`to_call == 0` 且本次投入会让 `_doom_risk(extra=add)` 成立 → check）。
4. **规则10 求稳 `_stability_mode`**（`STABILITY_LINE_FACTOR=0.60` 或剩 ≤8 手且领先）→ `_stability_guard`：主动侧 check、被动只跟；强牌例外。
5. **规则16 放宽**：剩局少 / 对手爱 all-in → 跟全下门槛 −，上限 0.09。
6. **规则17 盈利收紧 `_lead_allin_shift`**（翻后跟 all-in 叠加）：>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08。
7. **规则18/18b 搏命区**：`lead < 0 且 ≤ −0.95 × 2×追回线` → 整手在区内；牌烂 → 立即 allin（带 lk）；牌好 → 能过牌就 check、翻前补大盲 call、遇下注或河牌免费则 allin。
8. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本≥4）→ 停用四条小注路线（`_opp_check_bet` / `_blocking_bet_proxy` / `_lead_bet_proxy` / `_probe_bet_proxy`）；价值注不受影响。
9. **规则学习**（`match_ctx.rule_stats` 跨手持久化）：样本≥4 且胜率 <0.35 的「输的规则」→ 只把 raise 降级为跟/过；胜率 >0.60 的规则优先复用；fold/check/call/allin 及硬规则、兜底标签不参与。
10. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束我方主动下注/shove**——跟注与应对对手 all-in 一律豁免（2026-09-14 用户规则：定向决策替换所有旧限制）。
    · 【2026-09-25 方案B 起需注意】开池升到 3.5BB(350) 后，**我方 3-bet 更早撞 1000**：
      对手开池 250→3bet 750（不撞）；350→目标 1050 **被夹到 1000**；800→**无法合法加注→降级 call**。
      4-bet（2.3×对手3bet）在对手 3-bet ≥435 时即无法合法加注。1000 是用户规则，未擅改。
10b. **规则20 大额投入闸门 `_big_money_guard`**（2026-09-24，出口最后一步，在 `_endgame_arbitrate` 之后）：R1 `to_call > BIG_CALL_LIMIT(3000)` 且有效牌型 < 三条 → **fold**；R2 **主动**全押只在 [≥三条 / 翻前 AA·KK·QQ·JJ·AKs] 才允许，否则降级（免费→check，否则按 R1）。豁免：应对对手全下（`any_allin` 或 `to_call ≥ my_left`）。防锁赢/搏命区在入口 return，不受影响。背景：第21手一对6 因「模型压低门槛 → 决策层想跟 → `UA_SEALED_ALLIN` 升级全押」而推光 17,226。
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
- 【旧 ELF 版本指纹（2026-09-24）】用户给的旧 ELF（如 `测/poker_botv50`）可用
  `PyInstaller.archive.readers.CArchiveReader(path).extract('poker_bot')` 取出主脚本
  （zlib 自动解压），再 grep **特征字符串**（函数名/co_varnames 变量名）与 git 历史对照；
  回放命中率受 MC 抽样噪声影响（差 1~2 点不算证据），变量名指纹更可靠。
  已定位：v50 = `547e4a6`（2026-09-07 22:03）。
- 【教训】确定性硬规则（doom/锁赢）的输入必须用客观原始值；「赛制/风格偏移」只能改软阈值。
- 【标签】日志里的「规则1/4 大注弃牌」是 `_winning_rule()` 的兜底标签，不是真规则。
- 【A 感知硬规则·2026-09-26】「大注 + 无坚果 → 弃」（用户 2026-08-30 规则）原先
  `to_call > 0.6×池` **一刀切、从不咨询门槛**，是 A 唯一够不到的大块
  （实测 aggro 上 20 个 fold 里 **12 个＝60%** 由它决定）。现改为
  `commit = to_call + BIG_BET_FOLD_FUTURE_W × _future_cost(...)`，
  `commit > BIG_BET_FOLD_FRAC(0.60) × 池` → 弃。
  对手爱连街开火 → commit 抬高 → **更早弃**；对手被动 / 河牌（fc=0）→
  **逐字等价原规则**（不会反向过度弃牌）；关 A 时也等价原规则（A/B 可隔离）。
  【踩坑】验证时不能拿「最终动作」当判据（被动档也会因**别的**规则弃牌）；
  要拿 `WB_FACE_LOG` 有无记录判断该规则是否**提前 return**。
- 【翻后跟 all-in 判定顺序】规则2 → 河牌裸公对陷阱 → 公面同花威胁 → 突袭大注（eq 打折 0.15、牌型<三条直接弃）→ `thr = eff_req + margin ± 档位 + 规则17 − 规则16`。
- 【调参入口】`UA_ON`·`UA_SLOPE`·`UA_CALL_DAMP`·`UA_CROSS_CHECK`（终局效用仲裁）/ `BIG_CALL_LIMIT`·`BIG_MONEY_GUARD_ON`（规则20）/ `GAMBLE_LINE_FACTOR`·`GAMBLE_GOOD_PCT` / `STABILITY_LINE_FACTOR` / `LEAD_ALLIN_SHIFT` / `SMALL_BET_FOLD_MIN` / `RULE_MIN_SAMPLES`·`RULE_BAD_WR`·`RULE_GOOD_WR`·`RULE_LEARN_ON`。
- 【对手模型对门槛的叠加影响】`arch=="maniac" → eff_req −0.08`、规则16 最多 −0.09、被动型 −0.02 → 跟注门槛可从 0.39 压到 ~0.20；`_opp_range_pct` 只看「翻前是否加注者 + vpip」，**不看当前街加注**（范围可能被估宽：一对 6 对 67% 范围 eq 0.49、对 35% 只 0.37）——这是「学习导致偏差过大」的来源，规则20 是它的兜底。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。
- 【测试稳定性】MC 600 次抽样会让贴门槛的断言偶发翻转（>=10/20 → >=20/40 或改直测底层函数/极端值）。

## 待办 / 已知瑕疵
- `_profit_lock_allin`（C 分支）等价于 A 分支 → 死代码，可清理。
- 2026-08 的旧日志（08-17 ~ 08-24）按维护规则应蒸馏后删除，但用户常用它们做「当时版本行为」取证 → 暂保留。
- 【2026-09-25】方案 A（future_cost）与方案 B（开池 3.5BB）均已实现+全量回归通过，
  但**配对模拟均未证明能降低「前 20 手累积亏损」**（A：改动面 2~6% 且方向混杂；
  B：改动面 18.9% 但中位略差、均值 95%CI 横跨 0）。**未推送 GitHub**，等用户决定去留。
- 【2026-09-25】`测/学习升级版/poker_bot` 有一处非本轮的改动（未提交），需用户确认。
