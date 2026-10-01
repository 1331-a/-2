# 项目长期约定（德扑双人机器人）

> 完整背景见根目录 `项目交接说明.md` 与 `代码逐行详解.md`。本文件只放**速查**。

## 工作流
- 收尾默认推送 GitHub：`cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`（`cmp` 校验）→ 长消息写 `.git/COMMIT_MSG_TMP.txt` + `git commit -F` → `git push`。
- 交付前：13 个测试全量回归 → 同步 `代码逐行详解.md` + `内容/程序运行逻辑图.html` → 更新记忆。
- 冒烟 history **必须是 dict 列表**（player_id/action_type/amount/round）；扁平 list 会让 GameState 抛错、bot 静默返回 0。

## 平台与协议
- BotBattle HU 德州：70 手、按 `total_win_chips` 定胜负；盲注 50/100、初始 20000；**每步 60s**（`holdem_per_decision_60s_v1`）。
- **★ 竞赛平台未定**：指南写 Botzone（1s/步、raise 为**增量**、50 手），实测日志是 BotBattle（60s/步、raise-to 累计、70 手）。正式规则未发布前按 60s 口径。详见 `竞赛规则_核查清单.md`。
- 牌号 `n = rank*4 + suit`，rank 2..14（T=32..35, J=36..39, Q=40..43, K=44..47, A=48..51）；suit 0♠1♥2♦3♣。
  **★ 内部编码 = 平台编码 + 8**（`game_state` 统一转换），分析脚本取原始日志牌号后要 +8 才能喂给模型。
- response 单整数（-1 fold / -2 allin / 0 call·check / >0 raise-to）。
- **history 不含 blind 条目**；`hand` 0-based（`botbattle_log.load_botbattle` 的 `meta["hand"]` 是 **1-based**，平台界面也 1-based）→ **混用会看错手**。
- `_hands_left = max_hand − hand − 1`；`hand_start.chips` 已扣盲注。
- 只在我方行动时收 request；对手弃牌不可见 → 按 globaldata 增量推断（+50 对手 SB 弃 / +100 对手 BB 弃）。
- 单挑：翻前 dealer(SB) 先、翻后非 dealer(BB) 先。
- 原始 replay 字段与 request 不同：action 用 `player`/`action`/`amount`；deal_hole 用 `holes:[[座0],[座1]]`（"7d"）；settle 的 `net` 是累计。

## 构建发布
- 单文件 `内容/botzone_submit.py`（bundle 打包 equity/opponent/match_ctx/strategy/bot）；Linux ELF 由 GitHub Actions（仓库 `1331-a/-2`，workflow `build-elf`）产出，artifact `poker_bot-linux-x86-64`（~7MB）。本地无 Docker/WSL → Actions 是唯一发布路径。
- PyInstaller 锁 `<6.22`；【陷阱】artifact 常下成 **22 字节空 zip** → 解压后核对字节数。
- **★ 平台资源**：1 核 / 512MiB 内存 / `/tmp` 256MiB / 无网络 / 60s 每步 ⇒ **保持纯 Python，不引 numpy**（onefile 会膨胀 30~40MB）。
- `测/学习升级版/poker_bot` 是用户下载的 ELF，**不要动**。

## 模块分工
strategy（决策+安全网）/ game_state（协议解析）/ opponent（画像+尺寸分桶）/ equity（胜率）/ ranges（169 组合百分位）/ match_ctx（赛制三模块+规则账本）/ evaluator（牌型）/ bot（I/O）。

## 出口链（★ 最大结构问题）
`decide` → 入口短路 `_lock_win_unified`(规则2 A/B/C) 与 `_gamble_plan`(规则18) → 决策层 → **出口多层改写**（`_lock_win_tail_guard`→`_bet_cap_guard`→`_aggressive_strong_bet`→`_bluff_cap_guard`→`_stability_guard`→`_normalize`→`_endgame_arbitrate`→`_big_money_guard`→`_cheap_call_guard`→`_doom_call_upgrade`）。每层可覆盖前层 → 反复出 bug。v50 出口只有 `_normalize`。**建议收敛为 2 层**。

## 锁赢 / doom 数学（用户硬规则）
- `lead = 我方net − 对手net`；**筹码损失让 lead 变化 2 倍**，`×2` 只用一次。
- 追回线 `_blind_line(hands_left, own=False)`：固定 SB=50/BB=100，**勿用 `state.big_blind`**（翻前会被推导污染）。
- fold_out 锁胜：`lead > 2×(盲注线 + invested)` → fold。
- doom：`lead − 2×敞口 ≤ −2×追回线`；弃牌口径取 `_invested`，跟注口径取 `_invested + to_call`。只用**原始 lead**（match_ctx 偏移只作用于软阈值）。

## 规则清单（生效顺序）
1. **规则2 `_lock_win_unified`**（入口）：B fold_out→fold（`to_call==0` 用 check）；A doomed / C `_profit_lock_allin` → 同为 `_doom_plan`。
   ★ `_doom_plan` = 「弃牌是否立死」+ 牌力分流：`line≤0`→allin；`to_call>0`→**一律 allin**；`to_call≤0` 牌烂→allin（过 `_shove_fold_ok`）、牌好→None「再看看」、牌好且河牌→收网 allin。开关 `DOOM_ALLIN_ON` / `DBG_NO_DOOM_ALLIN=1`。
   ★ **A 被拒后必须 return None**：C 用同一不等式，继续走会绕过（局2 #43 因此推出 19,500）。
2. **`_endgame_arbitrate`**（09-24）：五动作同尺度比 EU（`_win_utility` logistic，锚点 ±2×追回线）。护栏：`UA_CROSS_CHECK` / `UA_SEALED_ALLIN`(0.15) / 只往保守修正 / 硬性弃牌不翻案。
3. **规则10 求稳**：`lead ≥ 0.70×锁赢线` 或剩 ≤8 手且领先 → 主动侧 check、被动只跟；强牌例外。（0.70 待用户确认，v50 是 0.80。）
4. **规则16/17**：跟全下门槛按剩局/对手 allin 频率下调（≤0.09），翻后按盈利档叠加（>+50BB +0.12 / >+10BB +0.07 / ±10BB +0.02 / <−10BB −0.03 / <−50BB −0.08）。
5. **规则18 搏命区**：`lead ≤ −0.95×2×追回线` → 牌烂 allin、牌好慢打；推前过 `_shove_fold_ok`（`eff_fold_to_bet ≥ 0.45`，样本≥6才门控）。
6. **规则19 小注作废**：对手面对 ≤40% 池小注弃牌率 <0.35（样本≥4）→ 停用小注线。
7. **规则学习**（跨手持久化）：样本≥4 且胜率 <0.35 → raise 降级为跟/过；>0.60 优先复用。
8. **注额上限**：翻前 ≤1000；翻后 <三条 ≤3000（小两对 ≤2000）；≥三条不限。**只约束主动下注/shove**。（1000 是用户规则。）
9. **规则20 `_big_money_guard`**：R1 `to_call>3000` 且 <三条 → fold；R2 主动全押只允许 ≥三条 / 翻前 AA·KK·QQ·JJ·AKs。★**故意不给 lk 开免检口**（改则 test_log_v2 FAIL）。
10. **`_doom_call_upgrade`**：跟注口径 doom → 强牌 allin、弱牌 fold。
11. 安全网 `_normalize` + `_allin_floor_guard`。

## 牌型判定
- `_effective_category`：**≥三条不能只由公共牌组成**。
- `_is_super_hand` = AA/KK/QQ/JJ/AKs；`_is_sub_strong` = AQ/AK/KQ。
- `hand_percentile`：AA 0.015 / 77 0.151 / 66 0.210 / KQs 0.275 / AKo 0.121。
- 状态机：normal / protect / pressure / desperate / doomed / steal。

## 对手画像与胜率（★ 本轮重点）
- 【算力 09-30 落地】`MC_ITERATIONS=30000`、`TIME_BUDGET=5.0`、`ALLIN_MC=20000`、`ALLIN_TIME_BUDGET=4.0`、`DECISION_TIMEOUT=40.0`、`EQ_TOTAL_BUDGET=12.0`（各路共用截止时刻 `_eq_deadline()`）。
  **播种两处**：`equity._rng` **和全局 `random`**（只播前者一致率 52/60）。环境变量 `WB_MC_ITERS`/`WB_MC_BUDGET`/`WB_NO_SEED`。
- 【精确枚举 09-30】`equity.exact_equity`：河牌 C(45,2)=990 组合 **0.05s**、转牌 87k 组合约 5s；误差归零。翻牌仍用 MC（精确需 ~232s）。
- 【软尾巴 09-30，有数据支撑】实测模型范围**一律偏窄约 2 倍** → eq 被系统性低估 0.059。加 `RANGE_SOFT_TAIL`（核心不变、只补衰减尾）后与真实底牌差距 **+0.0012**。
  校准工具：`测/range_eval.py`（覆盖率/反推真实宽度）、`测/tail_impact.py`、`测/tail_actions.py`。
- 【09-28】`_opp_range_pct` 计入**本街加注**：`_opp_street_raises` 数当前街对手 raise/allin/bet（≤3），每次按 `per=0.45−0.30×agg`（clamp 0.20~0.40）收窄。
- 【翻前尺寸】`OPEN_SIZE_BB=3.5`/`VS_STATION=3.0`/`ISO=4.0`/`STEAL=3.0`；★**只改 `OPEN_SIZE_BB` 无效**——`_learned_size` 用 `bucket_to_frac`(2.5/3.5/4.5) 覆盖。条件化再乘 `clamp((0.80−eff_vpip)/0.25,0,1)` × `min(1,hands_seen/8)` → 实际 [2.5,3.5]，**前 8 手不生效**。
- 【默认关闭】`BIG_BET_FOLD_A_ON=False`（隔离检验未通过）；`WB_FORCE_BIGBET_A=1` 可启用。

## 工具 / 测试陷阱
- 对手 all-in 在 history 里写**真实金额**；写 `-2` 会让 `to_call` 塌缩。
- 翻后公牌张数要对（3/4/5）。
- 复盘：界面「底池」常是结果态 → 必须回到决策前。座位需动态检测。
- `DecisionLogger`：`decide(debug=False)` 会关日志；分析器需 `enable(True) + _quiet=True`。
- 日志「规则1/4 大注弃牌」是 `_winning_rule()` 兜底标签，不是真规则。
- **★ 行为指纹判座位**（09-30）：日志双方元数据可能完全相同 → 无法从元数据判座位。解法：把同一批决策点喂给两版，动作一致率高者为该座位版本。工具 `测/_py311/fingerprint.py` + `verify_hands.py` + `diag_shove.py`。
- **★ v50 对拍**（可复现）：v50 pyc 是 Python 3.11 → 需 embed 版解压到 `测/_py311/`。取 pyc：`CArchiveReader` → toc → `_start_offset+dpos` 取 `dlen` → **`zlib.decompressobj(15)`（wbits=+15）** → `marshal.loads`。产物 `测/_v50_body.bin`。工具 `测/_py311/{cmp2.py,diag2.py,duel.py}`。
- **对弈引擎 `duel.py` 不可用**：模块级全局/RNG 无法隔离（v50 vs v50 出现 6:0）→ 要量化只能子进程隔离或真实日志回放。
- **v50 对拍基线（39 场景）**：翻前 0 差异；翻后主动仅尺寸有别；翻后面对下注本版更激进。保守处：① `_stability_guard` 翻前也压制主动加注（用户 09-14 规则，保留待决）；② 强牌加注偏小（280 vs 500）→「少赢」。
- 验证规则是否提前 return，看 `WB_FACE_LOG`，不能只看最终动作。
- 旧 ELF 指纹：`CArchiveReader(path).extract('poker_bot')` 后 grep 变量名。v50 = `547e4a6`。

## 技术判负（09-28）
- 43 秒 / 7 手、第 7 手零响应。**`ended_at` 只记最后事件时间，60s 超时不计入** → 真故障 = 最后一步没响应。
- 已加固 `bot.py`：utf-8 reconfigure、`_handle_line` 全包 try/except、异常也输出合法响应、**循环永不中断**（进程退出＝立即判负，比回保守动作严重得多）。**根因未定位**。

## 调参入口
`UA_ON`·`UA_SLOPE`·`UA_CALL_DAMP`·`UA_CROSS_CHECK`·`UA_SEALED_ALLIN`·`UA_SEALED_MARGIN` / `BIG_CALL_LIMIT`·`BIG_MONEY_GUARD_ON` / `DOOM_ALLIN_ON` / `GAMBLE_SHOVE_FOLD_MIN(0.45)`·`GAMBLE_SHOVE_FORCE_HANDS(8)`·`GAMBLE_LINE_FACTOR(0.95)` / `RANGE_NARROW_*`·`RANGE_SOFT_TAIL` / `STABILITY_LINE_FACTOR(0.70)`·`STABILITY_ENDGAME_HANDS(8)` / `LEAD_ALLIN_SHIFT` / `SMALL_BET_FOLD_MIN` / `RULE_MIN_SAMPLES`·`RULE_BAD_WR`·`RULE_GOOD_WR`·`RULE_LEARN_ON` / `OPEN_SIZE_BB(3.5)`。

## 待办 / 已知瑕疵
- **待用户裁决**：① 求稳是否只作用翻后（改法：`_stability_guard` 加 `if state.stage=="preflop": return action` + 改 2 条断言）；② `STABILITY_LINE_FACTOR` 0.70 / 0.60；③ 强牌加注尺寸是否调大。
- **打不过 v50** 是首要问题，唯一可信验证 = 用户提供 vs v50 的真实日志。
- `测/学习升级版/poker_bot` 有一处非本轮改动未提交。
- 交付文档：`项目交接说明.md`（用户已转用 ChatGPT 写代码）。
