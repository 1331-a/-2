# 项目长期约定（德扑双人机器人）

> 详细背景见根目录 `项目交接说明.md`（自包含交接文档）与 `代码逐行详解.md`。本文件只放**速查**。

## 工作流约定（重要）
- **改动完成后默认推送 GitHub**：
  1. `cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`（`cmp` 校验字节一致）
  2. 长文消息写 `.git/COMMIT_MSG_TMP.txt` + `git commit -F`（勿直接 `-m`）→ `git push`
  3. 查 Actions（未认证 API 会 403 限流；限流就只确认 push 成功）
- 交付前：13 个测试文件全量回归 → 同步 `代码逐行详解.md` + `内容/程序运行逻辑图.html` → 更新记忆。
- 冒烟 history **必须是 dict 列表**（含 player_id/action_type/amount/round）；扁平 list 会让 GameState 抛错、bot 静默返回 0（像回归）。

## 平台与协议
- BotBattle HU 德州：70 手、按 `total_win_chips` 定胜负；盲注 50/100、初始 20000；**每步时限 60s**（`holdem_per_decision_60s_v1`，早期笔记的"1 秒"已过时）。
- 牌号 `n = rank*4 + suit`，rank 2..14（T=32..35, J=36..39, Q=40..43, **K=44..47**, A=48..51）；suit 0=♠1=♥2=♦3=♣。
- response 单整数（-1 fold / -2 allin / 0 call·check / >0 raise-to）；JSON 带 requests/response/data/globaldata。
- **history 不含 blind 条目**（盲注由 GameState 从 `my_chips` 推导）。
- `hand` 0-based；`_hands_left = max_hand − hand − 1`；`hand_start.chips` 已扣盲注。
- 只在**我方行动时**收 request；对手弃牌不可见 → globaldata 按增量推断（+50 对手 SB 弃 / +100 对手 BB 弃）。
- 单挑：**翻前 dealer(SB) 先、翻后非 dealer(BB) 先**。
- 【★ 手号 0-based vs 1-based 陷阱】`hand_start.hand` 是 **0-based**；`botbattle_log.load_botbattle` 的 `meta["hand"]` 是 **1-based**；平台界面也是 1-based。**两套混用会「看错手」**（我第一轮扫描因此把 55/59/62 对到了相邻的手）。分析前先确认用哪套。
- 原始 replay 事件字段与 request 不同：action 是 `player`/`action`/`amount`；deal_hole 是 `holes:[[座0],[座1]]`（"7d" 字符串）；settle 的 `net`=累计（平台计分口径）。

## 构建发布
- 单文件 `内容/botzone_submit.py`（`bundle.py` 打包 equity/opponent/match_ctx/strategy/bot）；Linux ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow `build-elf`）产出，artifact `poker_bot-linux-x86-64`（~7MB）。本地无 Docker/WSL → Actions 是唯一发布路径。
- PyInstaller **锁 `<6.22`**（6.22.x onefile 引导器有父进程校验，产物在受限沙箱秒退）。
- 【陷阱】artifact 常下成 **22 字节空 zip**（`PK\x05\x06`）→ 部署前解压核对字节数。
- 【★ 平台资源约束（09-30 ChatGPT 侧确认，此前未知）】**1 核 CPU / 512 MiB 内存 / `/tmp` 256 MiB / 无网络 / 单步 60s**；允许约 200MB ELF，但「能打包」≠「适合运行」（onefile 每次启动解压到 `/tmp`）。
  ⇒ **撤回「numpy 加速评估器」的想法**：512MiB + 256MiB `/tmp` 下 numpy 让 onefile 膨胀 30~40MB、启动变慢。**保持纯 Python，靠抬高 MC 抽样数（内存零开销）拿精度更稳**。
- `测/学习升级版/poker_bot` 是用户下载的 ELF，**不要动**（有一处历史未提交改动）。

## 模块分工
strategy.py（决策+安全网，5052 行/110 函数）/ game_state.py（协议解析+合法性推导）/ opponent.py（画像+尺寸分桶）/ equity.py（MC 胜率）/ ranges.py（169 组合百分位）/ match_ctx.py（赛制三模块+规则账本）/ evaluator.py（牌型）/ bot.py（I/O）。

## 出口链（★ 最大结构问题）
`decide` → 入口短路 `_lock_win_unified`(规则2 A/B/C) 与 `_gamble_plan`(规则18) → 决策层 → **出口 9 层改写**：
`_lock_win_tail_guard` → `_bet_cap_guard` → `_aggressive_strong_bet` → `_bluff_cap_guard` → `_stability_guard` → `_normalize` → `_endgame_arbitrate` → `_big_money_guard` → `_cheap_call_guard` → `_doom_call_upgrade`。
每层可覆盖前层 → 反复出 bug（A/C 互为绕过通道、规则20 与 lk 冲突、第32手顺序冲突）。v50 出口**只有 `_normalize`**，doomed 只是 `_bet_limit` 的放宽分支（参数而非指令）。**建议收敛为 2 层**（详见交接文档 P0-1）。

## 锁赢 / doom 数学（第一层硬约束，用户规则）
- `lead = 我方net − 对手net`；**筹码损失 → lead 变化是 2 倍**（我 −X 对手 +X → 差 −2X）；比较时口径一致，`×2` 只用一次。
- 追回线 `_blind_line(hands_left, own=False)`：固定 SB=50/BB=100，**勿用 `state.big_blind`**（翻前会被推导污染）。
- fold_out 锁胜：`lead > 2×(盲注线 + invested)` → fold。
- doom：`lead − 2×敞口 ≤ −2×追回线`；弃牌口径取 `_invested`，跟注口径取 `_invested + to_call`。判定只用**原始 lead**（match_ctx 偏移只作用于软阈值）。

## 当前规则清单（按生效顺序）
1. **规则2 `_lock_win_unified(state, model)`**（入口）：B fold_out→fold（`to_call==0` 用 check）；A doomed→`_doom_plan`；C `_profit_lock_allin`→`_doom_plan`（**与 A 同一函数**）。
   ★ `_doom_plan` = **「弃牌是否立死」+ 牌力分流**（不做越线幅度判断——用户 09-28 指出该变量逻辑错误）：
   · `line≤0`（最后一手）→ allin；· `to_call>0`（弃牌立死）→ **一律 allin**；· `to_call≤0` 牌烂 → allin（过 `_shove_fold_ok`）；· `to_call≤0` 牌好 → None「再看看」；牌好且**河牌** → 收网 allin。
   · 开关 `DOOM_ALLIN_ON` / `DBG_NO_DOOM_ALLIN=1`（回退无条件全押）。
   ★ A 被拒后**必须 return None**：C 用同一个 `_doom_risk` 不等式，继续走会绕过（局2 #43 由此推出 19,500）。
2. **`_endgame_arbitrate`**（09-24）：弃/过/跟/加/全押同尺度比 EU（`_win_utility` logistic 无悬崖，锚点 ±2×追回线）。护栏：① `UA_CROSS_CHECK` ② `UA_SEALED_ALLIN`（`UA_SEALED_MARGIN=0.15`）③ 只往保守修正 ④ 硬性弃牌不翻案。调参 `UA_ON/UA_SLOPE(1.6)/UA_CALL_DAMP(0.6)`。
3. **规则10 求稳**：`lead ≥ STABILITY_LINE_FACTOR(0.70) × 锁赢线` 或剩 ≤8 手且领先 → 主动侧 check、被动只跟；强牌例外。★0.70 是 09-28 从用户 09-14 定的 0.60 调来的（v50 是 0.80），**待用户确认**。
4. **规则16/17**：剩局少/对手爱 all-in → 跟全下门槛 −（上限 0.09）；翻后按盈利档叠加（>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08）。
5. **规则18 搏命区**：`lead ≤ −0.95×2×追回线` → 整手在区内；牌烂 allin、牌好慢打。牌烂推前过 `_shove_fold_ok`（`eff_fold_to_bet ≥ GAMBLE_SHOVE_FOLD_MIN(0.45)`，样本 ≥6 才门控；被逼全下/无画像/剩 ≤8 手豁免）。
6. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本≥4）→ 停用四种小注线。
7. **规则学习**（`match_ctx.rule_stats` 跨手持久化）：样本≥4 且胜率 <0.35 → 只把 raise 降级为跟/过；>0.60 优先复用。
8. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束我方主动下注/shove**，跟注与应对对手全下豁免。（1000 是用户规则，勿擅改。）
9. **规则20 `_big_money_guard`**（出口，仲裁之后）：R1 `to_call>BIG_CALL_LIMIT(3000)` 且 <三条 → fold；R2 主动全押只在 [≥三条 / 翻前 AA·KK·QQ·JJ·AKs] 允许。豁免：应对对手全下。★**故意不给 `lk` 开免检口**（弱牌不许主动推光，自 09-24 起压过 `UA_SEALED_ALLIN`，改则 test_log_v2 FAIL）。
10. **`_doom_call_upgrade`**（出口最后一步）：跟注口径 doom → 不许便宜跟注；强牌 allin(lk)、弱牌 fold。
11. 安全网 `_normalize` + `_allin_floor_guard`（主动 shove 累计投入 ≤ 盈利+1000 → fold）。

## 牌型与强度判定
- `_effective_category`：**≥三条不能只由公共牌组成**（board 独自拼出的三条/顺/花/葫芦降级 HIGH_CARD）。
- `_is_super_hand` = AA/KK/QQ/JJ/AKs（＝`_strong_for_big_money` 翻前口径）；`_is_sub_strong` = AQ/AK/KQ。
- 公对风险：`should_avoid_risk`（弱两对保守）+ `_river_paired_trap`；**≥三条不算弱两对**（葫芦 222JJ 曾误判弃牌）。
- 状态机：normal / protect / pressure / desperate / doomed / steal。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。

## 对手画像与胜率
- 【翻前尺寸 09-25】`OPEN_SIZE_BB=3.5` / `OPEN_SIZE_VS_STATION=3.0` / `ISO_SIZE_BB=4.0` / `STEAL_OPEN_BB=3.0`；学习代表值 `bucket_to_frac` 翻前 = 2.5/3.5/4.5。★**只改 `OPEN_SIZE_BB` 无效**——`_learned_size` 会用 `bucket_to_frac` 覆盖它。
- 【条件化 09-26】开池再乘 `clamp((0.80−eff_vpip)/0.25,0,1)` × 样本门控 `min(1, hands_seen/8)` → `_open_size_bb ∈ [2.5, 3.5]`，**前 8 手不生效**（故冒烟常见 raise 250 而非 350）。`_future_cost` 按 `_future_aggr_factor` 缩放。
- 【09-28】`_opp_range_pct(model, raised_pf, street_raises)` **计入本街加注**：`_opp_street_raises(state)` 数当前街对手 raise/allin/bet（上限 3），每次按 `per = 0.45 − 0.30×agg`（clamp 0.20~0.40）收窄，总 `base×(1−per)^n`。修掉"对手连开三枪仍按宽松范围算 eq"（162 个翻后点中 40 个受影响，收窄约 35%）。
- 【**默认关闭**】`BIG_BET_FOLD_A_ON=False`（隔离检验未通过，收益与亏损同源）；`WB_FORCE_BIGBET_A=1` 可启用。

## 工具 / 测试陷阱
- 对手 all-in 在 history 里必须写**真实金额**；写 `-2` 会让 `to_call` 塌缩（按"推光需跟全部筹码"保守口径）。
- 翻后场景公牌张数要对（3/4/5 = flop/turn/river），否则 stage 不符、规则不触发。
- 复盘：`botbattle_log.load_botbattle` 逐决策点重放，投入**按街累加**；界面「底池」常是结果态（all-in 后）→ 必须回到决策前。座位需动态检测（我方 = owner 含 `j1331` / 显示名"测01"）。
- `DecisionLogger`：`decide(debug=False)` 会**关掉**日志并覆盖手动 enable；分析器需 `enable(True) + _quiet=True`。
- 日志里的「规则1/4 大注弃牌」是 `_winning_rule()` 兜底标签，不是真规则。
- MC 600 次抽样会让贴门槛断言偶发翻转 → 加大迭代或直测底层函数。
- 【★ 算力余量 09-30 实测·全书最重要的一条】`equity.py` 文件头仍写「平台每步限 1 秒」（**过时**，实际 60s），
  `TIME_BUDGET=0.5s` / `MC_ITERATIONS=1000` / `ALLIN_MC=600` → 实测 600 次只用 **0.073s**，
  **真正的约束是 iterations 上限，不是时间**。平台 60s/步 ⇒ **只用了 0.12% 的时间预算（120 倍余量）**。
  实测 `evaluate_7` 吞吐 **16,884 次/秒**（59.2µs）。
  标准误 `SE=0.5/√N`：N=600→2.04%、N=1000→1.58%、**N=50,000→0.22%**（约 6s）、N=80,000→0.18%（约 10s）。
  精确枚举成本（含双方各一次评估）：**河牌 1,980 次 = 0.12s（可完全精确）**、
  **转牌 87,120 次 = 5.2s（可完全精确）**、翻牌 3,920,400 次 = **232s（超时 4 倍，只能 MC）**。
  ⇒ **首选改动**：抬高 iterations 上限 + 软时限，并给 `equity._rng` 播种（当前未播种 → 不可复现）。
  **不需要预计算表**（曾误判为 +25MB 方案，已修正）。
- 【★ 位置偏差校正】`TIME_BUDGET` 注释写「平台预检超时 8s」，与日志的 per_decision 60s 关系**未确认** → 上预算前先核实，建议从 3~5s 起步。
- 验证某规则是否提前 return，不能拿最终动作当判据，要看 `WB_FACE_LOG`。
- 构造测试场景前先跑「状态自检」（两版 to_call/pot/stage 一致）再比较结论——协议校准错一次结论就反了。
- 盘上行为与代码不符时先穷举输入形态（金额缺失 / `my_id` 反转 / 字段类型），再怀疑规则。
- 旧 ELF 指纹：`CArchiveReader(path).extract('poker_bot')` 后 grep 变量名（比回放可靠）。v50 = `547e4a6`。
- 复盘工具：`内容/analyze_matches.py`（`load_botbattle` / `detect_seat` / `replay_decisions`）。

## ★ 行为指纹判座位（09-30 新增，重要）
BotBattle 日志双方元数据可能**完全相同**（同账号上传两份 ELF：`display_name/id/name/owner` 全同）→ **无法从元数据判座位**。
解法：把同一批真实决策点分别喂给两版，统计动作一致率，高者为该座位的实际版本。
工具 `测/_py311/fingerprint.py`（Python 3.11 运行）。实测 20260930201238：**座位0=当前版 93.8%**（v50 79.4%）、**座位1=v50 98.1%**（当前版 80.0%），分离度 14~18 个百分点。配套 `verify_hands.py`（逐手两版对照 + 累计比分）、`diag_shove.py`（按规则归因）。

## ★ 让 v50 真跑起来（09-30，可复现）
v50 pyc 是 **Python 3.11** → 3.13 marshal 读不了、decompyle3 不支持。路径：
1. 下载 **python-3.11.9-embed-amd64.zip**（`registry.npmmirror.com/-/binary/python/3.11.9/`，python.org 直连超时）→ 解压 `测/_py311/`。
2. 从 ELF 取 pyc：`CArchiveReader('测/poker_botv50')` → `toc['poker_bot']` → 绝对偏移 `_start_offset + dpos` 取 `dlen` 字节 → **`zlib.decompressobj(15)`（wbits=+15，不是 −15）** → `marshal.loads`。（`extract()` 返回未解压段，别直接用。）产物 `测/_v50_body.bin`。
3. `exec(marshal.loads(body), ns)` → 91 个可调用对象。当前版纯标准库 → **同一 3.11 进程可同时 import 两版** → 对拍。
工具：`测/_py311/{cmp2.py, diag2.py, duel.py}`。

## v50 对拍基线（09-30，39 场景）
- 翻前开池 / BB 防守两版 **0 差异**；翻后主动仅**尺寸**有别；**翻后面对下注本版反而更激进**（听牌/空气加注 vs v50 弃）。
- 真正保守处：① `_doom_plan` 的「翻前好牌补大盲→call 溜入」（**已删**，1d2fd1e）；② `_stability_guard` 翻前也压制主动加注（v50 只管翻后，但这是用户 09-14 规则，**保留待决**）。
- 强牌面对下注加注尺寸偏小（本版 280 vs v50 500）→ 属"少赢"。
- **对弈引擎 `duel.py` 不可用**：同进程双实例对照实验不通过（v50 vs v50 出现 6:0），推定模块级全局/RNG 无法隔离。要量化只能**子进程隔离**或**真实日志回放**。逐场景对拍不受影响。

## 技术判负（09-28 fbfdfaa4）
- 43 秒 / 7 手、第7手翻牌后零响应。★**`ended_at` 只记最后事件时间，60s 超时等待不计入** → 真故障 = 最后一步没响应。判据：per_decision 60s + 前几步 used 仅 0.1~0.3s。
- 已加固 `run()`（bot.py）：① stdin/stdout reconfigure(utf-8, errors=replace)；② `_handle_line`+序列化全包 try/except；③ 异常也输出合法响应、写出失败吞掉，**循环永不中断**；异常写 stderr `[FATAL]`。**进程退出＝立即判负，比回保守动作严重得多。**
- 排查通过：输出全路径合法 int；stdout 无污染；MC 有上限+软时限；400 场景最慢 0.26s；`ast.parse(feature_version=(3,11))` 全过。
- **未定位根因**，需用户提供：ELF 版本 / 平台 stderr / 完整 json。

## 调参入口
`UA_ON`·`UA_SLOPE`·`UA_CALL_DAMP`·`UA_CROSS_CHECK`·`UA_SEALED_ALLIN`·`UA_SEALED_MARGIN` / `BIG_CALL_LIMIT`·`BIG_MONEY_GUARD_ON` / `DOOM_ALLIN_ON` / `GAMBLE_SHOVE_FOLD_MIN(0.45)`·`GAMBLE_SHOVE_FORCE_HANDS(8)`·`GAMBLE_LINE_FACTOR(0.95)`·`GAMBLE_GOOD_PCT` / `RANGE_NARROW_*` / `STABILITY_LINE_FACTOR(0.70)`·`STABILITY_ENDGAME_HANDS(8)` / `LEAD_ALLIN_SHIFT` / `SMALL_BET_FOLD_MIN` / `RULE_MIN_SAMPLES`·`RULE_BAD_WR`·`RULE_GOOD_WR`·`RULE_LEARN_ON` / `OPEN_SIZE_BB(3.5)`。

## 待办 / 已知瑕疵
- **待用户裁决**：① 求稳是否放宽到只作用翻后（改法：`_stability_guard` 加 `if state.stage=="preflop": return action` + 改 2 条断言）；② `STABILITY_LINE_FACTOR` 保持 0.70 还是回 0.60；③ 强牌加注尺寸是否调大；④ 09-25 方案 A/B 去留（配对模拟未证明有效，未推送）。
- **打不过 v50** 是当前首要问题，唯一可信验证方式 = 用户提供一场 vs v50 的真实日志做回放。
- `测/学习升级版/poker_bot` 有一处非本轮改动未提交，需用户确认。
- 2026-08 旧日志按维护规则应蒸馏删除，但用户常用它们做「当时版本行为」取证 → 暂保留。
- 交付文档：`项目交接说明.md`（根目录，自包含交接说明，用户已转用 ChatGPT 写代码）。
