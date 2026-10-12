# 项目长期约定（德扑双人机器人）
> 详情：`项目交接说明.md`/`代码逐行详解.md`/`文献调研_可借鉴方案.md`；逐日 `YYYY-MM-DD.md`；A/B 方法与陷阱见技能 `poker-strategy-ab`。按重要性递减排列。

## 工作流
收尾：`cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`(cmp) → `git commit -F .git/COMMIT_MSG_TMP.txt` → push。交付前 13 测试全量回归 + 同步详解文档。冒烟 history 必须 dict 列表，否则 bot 静默返回 0。

## 平台协议
BotBattle HU 70 手/盲注 50-100/初始 20000/**60s 每步**/按总筹码定胜负（★竞赛平台未定，指南写 Botzone 1s/50 手）。牌号 n=rank*4+suit，**内部编码=平台+8**。response：-1fold/-2allin/0call-check/>0raise-to。history 不含 blind；hand 0-based（`load_botbattle` meta 是 1-based）。**action.amount：raise/allin=本街 raise-to，call=本次增量** ⇒ 尺寸=amount−本街累计；**重建底池用 GameState**。对手弃牌不可见→按 globaldata 增量推断。单挑：翻前 dealer(SB) 先、翻后 BB 先。

## 锁赢/doom（用户硬规则）
lead=我方 net−对手 net；筹码损失让 lead 变 2 倍，×2 只用一次。追回线≈75×剩余手数（固定 SB50/BB100，勿用 `state.big_blind`）⇒ doom 阈值≈落后 150×剩余手数。fold_out：`lead>2×(盲注线+invested)`→fold。doom：`lead−2×敞口≤−2×追回线`（弃牌口径 `_invested`／跟注 `+to_call`），只用原始 lead。
★**10-01 裁决：「doom 成立→无条件 allin」不动，`to_call>0` 无门控=有意设计，勿再提收紧**（异议已被 107 次 allin 数据否定：对手弃 90%、合计 +43,807）。

## 规则清单（生效顺序，除注明外默认开）
1. 规则2 `_lock_win_unified`（入口）：fold_out→fold；doomed/`_profit_lock_allin`→`_doom_plan`。★A 被拒后必须 return None（否则 C 绕过）。
2. `_endgame_arbitrate`：五动作同尺度比 EU（`_win_utility` logistic）。★10-09：`UA_CROSS_CHECK`=「好牌也消极」元凶，已按用户原则修——`_cross_check_exempt` 分街（翻后≥两对 或 `_pair_is_top`；翻前 `_is_super_hand`）；★不可用翻前名单判翻后。回退 `WB_NO_CROSS_STRONG_PASS=1`。
3. 规则10 求稳：lead≥0.70×锁赢线 或剩≤8 手领先→主动 check/被动只跟；强牌例外（★10-01 配对模拟证伪「放行翻前」⇒保持）。
4. 规则16/17：跟全下门槛按剩局/对手频率下调至 ≤0.09；翻后按盈利档 ±。
5. 规则18 搏命区：lead≤−0.95×2×追回线→牌烂 allin、牌好慢打；过 `_shove_fold_ok`(eff_fold≥0.45)。
6. 规则19/学习：小注作废 + 样本≥4 胜率<0.35→raise 降级。
7. 注额上限：翻前≤1000；翻后<三条≤3000（小两对≤2000）；≥三条不限（只约束主动）。
8. 规则20 `_big_money_guard`：to_call>3000 且<三条→fold；主动全押只允许≥三条/翻前 AA·KK·QQ·JJ·AKs（★故意不给 lk 免检口）。★顶两对豁免 `_is_top_two_pair()`（两档都须我方底牌补成）**需同时改 4 处**。
9. `_doom_call_upgrade`：跟注口径 doom→强牌 allin、弱牌 fold。
10. ★规则11 公面同花威胁（只对 3+ 同花 + 对手>3000；★缺陷：不看已成牌/赔率）：全量 895 命中 7 次（5 次对手全下弃对、2 次普通下注，10-11 手5/6 都错）。豁免已实现但**默认关**：`FLUSH_MADE_PASS`/`PAIRED_TRAP_MADE_PASS`/`BIGMONEY_TWOPAIR_PASS`+阈值+非全下门控。只改 2 点。

## ★3000 悬崖（10-11）
668 个面对下注点：to_call>3000 仅 41 次=36 次对手推光+5 次普通下注（全 0.98~1.30×池，无压线）。手21（一对 6318=1.14×池）正是规则20 原始案例 ⇒ **真问题是牌力非金额**。悬崖：3000→eq≥0.33；3001→须≥三条 ⇒ 对手多下 1 筹码即可压死。
★建议3 已默认启用：`BIG_CALL_RAMP_ON`，`_big_call_ramp()` 加价=BASE+(MAX−BASE)×max((to_call−3000)/3000, to_call/剩余)（0.06→0.20），`_big_call_ramp_applies()` 唯一判据（开关+to_call>3000+牌型≥两对）；落点 `_face_bet`/`_normalize`×2/`_big_money_guard` call。回退 `WB_NO_BIGCALL_RAMP=1`。
★①ramp 单独=0/895（手5/6 在 `_face_bet` 前已被规则11 弃）⇒ 与 §5 规则11 豁免配套；②「弱牌交给 eq 挡」不成立（手21 一对 eq 被抬到 0.46）⇒ 必须设牌型下限。

## 出口链（★最大结构问题）
入口短路 `_lock_win_unified`/`_gamble_plan`——★**实测 33.9%（几乎全是 `_fold_out_active` 锁赢弃牌），不是旧记的 ~7%**（`测/owner_probe.py`，948 点）→决策层→出口 10 层：`_lock_win_tail_guard`→`_bet_cap_guard`→`_aggressive_strong_bet`→`_bluff_cap_guard`→`_stability_guard`→`_normalize`→`_endgame_arbitrate`→`_big_money_guard`→`_cheap_call_guard`→`_doom_call_upgrade`（v50 只有 `_normalize`）。
实测 315 点：`_stability_guard` 占 53%（多为翻前降 raise）；`_lock_win_tail_guard`/`_bluff_cap_guard` 292 次 0 翻转；打架仅 1 次。
⇒①层间打架不是主要风险（"我加注→对加注→我再弃"来自决策层自身）；②LIMIT 静默截断，重放前确认决策点数；③★**同一金额/阈值规则在出口链常有多达 3~5 个实现点，只改一处=diff 报 0**。
★ **归因实测（948 点）**：翻前 35.2% / 入口短路 33.9% / 主动侧 17.8% / 面对下注·牌型尺寸 5.7% / 面对下注·硬规则 5.4% / **面对下注·eq 门槛仅 2.0%**；出口链净改写 10.3%，其中 **eq 门槛的结论 36.8% 被出口链盖掉**。⇒ **`eq` 权重低是规则堆出来的**，不是 bug。详见 `复盘_20261011_决策归因与eq话语权.md`。
★ **出口链逐层实测（948 点，改写 116 次 / 98 点）**：**更保守 77 : 更激进 5 = 单向保守机器**。逐层改写：`_stability_guard` **39**（36 在翻前）/ `_bet_cap_guard` **32** / `_aggressive_strong_bet` 12 / `_doom_call_upgrade` 11 / `_cheap_call_guard` 7 / `_endgame_arbitrate` 6（唯一主要"更激进"）/ `_normalize` 5 / `_big_money_guard` 3 / `_bluff_cap_guard` 1 / **`_lock_win_tail_guard` 0（627 调用 0 改写；冗余候选但**不建议删**——锁赢安全网）**。
★★ **「好牌也消极」的量化证据**：77 次保守改写里 **26 次（33.8%）落在 `eq 超门槛 ≥ +0.10`** 的点上（中间地带 0~+0.10 **为 0**，分布两极）——最刺眼 `eq0.901 → allin→call→fold`、`eq0.896 → raise→call→fold`。按层：`_bet_cap_guard` 11 / `_cheap_call_guard` 7 / `_doom_call_upgrade` 3 / `_normalize` 2 / `_endgame_arbitrate` 2 / `_big_money_guard` 1。详见 `复盘_20261011_出口链普查与eq否决权.md`。

## 对手/胜率
算力 MC=30000/预算 5.0s/全下 20000·4.0s/EQ_TOTAL 12.0s；播种 `equity._rng`+全局 random 两处。`equity_best()` 河/转牌精确枚举。对手范围系统性偏窄 2 倍→`RANGE_SOFT_TAIL` 修正（★全下禁用）。★`_eq_deadline` 兜底不能无界（曾致单步 277s 判负）。翻前尺寸 `OPEN_SIZE_BB`（只改它无效，前 8 手不生效）。对手 code A：eff_vpip 0.89、翻前松翻后 fit-or-fold。**内置对手强于本 bot；打不过 v50 是首要问题**。

## 工具陷阱
★规则标签≠真凶（逐层 monkey-patch 看 before→after）。★★报「变化 N 点」必须重跑+对照臂（跨进程噪声 0.5~1%）。★`diff_ab.py --off-env` 列方向反。★自对弈双方 owner 同一 id，先确认座位。★★「只落后才生效」的规则用内置对手配对必然假阴性 ⇒ 用 `sim_early.py --selfab`。`duel.py` 不可用。
★★ **改一条硬规则后 diff 报 0 —— 三步排查**：①加触发计数器(区分没触发/没翻) → ②找"下一个接走者"(同人群常被多条**串联**规则覆盖；用标记位定位，如「大注/突袭」族 15 点里 14 点 `_OPP_JUMPED=True`) → ③查出口链(决策层判对了也可能被盖回去)。★还要检查作用域诚实：不排除"全下点位"会**绕过规则16/17**。

## 构建/平台
单文件 `内容/botzone_submit.py`；Linux ELF 由 GitHub Actions（仓库 1331-a/-2，workflow build-elf）产出；artifact 常下成 22 字节空 zip。★平台 1 核/512MiB/无网络/60s ⇒ **纯 Python 不引 numpy**。`测/学习升级版/poker_bot` 是用户 ELF，勿动。★技术判负(09-28)根因未定位。

## 待办
①强牌加注尺寸是否调大；②`to_call==0` 未见翻牌是否先过牌（手58）；③§5 规则11 豁免是否启用；④ramp 是否放开到「顺子遇全下」「4/5 张激活」。建议3 需与 §5 三开关配套。
★**「提高 eq 权重」方向已试到尽头**（归因：eq 直接决定仅 2.0%；选项B 试点净 0/948，三重封锁）⇒
**先解出口链再谈 eq**。`BIGBET_THRESH_ON`（选项B，默认关）已实现未打包；`内容/strategy.py` 与
`botbattle/poker_bot.py` 暂不一致。
★★ **`EQ_VETO` 已实装并默认启用**（选项②、δ=0.10、**`MAX_RANK=3`**，提交 `6ec4374` 已 push）：
逐层否决 `_bet_cap_guard`/`_normalize`/`_big_money_guard`/`_cheap_call_guard` 的"更保守"改写
（判据 `eq ≥ eff_req+margin+0.10`，数据来自 `_face_bet` 曝露的 `_LAST_REQ_INFO`）。
`EQ_VETO_MAX_RANK`（fold0/check1/call2/raise3/allin4）：**3 = 可恢复加注、不可恢复全押**
⇒ 保住"好牌敢加注"、去掉"弱牌 lk 主动推光"。三档实测（对照臂均 0）：MAX=4 →18 点；**MAX=3 →16 点**；MAX=2 →5 点。
回退 `WB_NO_EQ_VETO=1`。★含义：会**越过规则20 的 3000 上限**（用户批准，`test_preflop_cap` C2 断言已放宽到 ≤3000）。
★ 更正：`_cheap_call_guard` 是**【方案A·2026-09-24 用户规则】**，我此前误标成"我方、不碰用户规则"。
★★ **撤回**：「EQ_VETO 导致 test_log_v2 2 项失败」**是错误归因**。真因是**测试时钟缺陷**（见下），
开/关两臂失败完全相同 ⇒ 与 EQ_VETO 无关。结论记于 `复盘_20261011_EQ_VETO实现与AB.md` §7。
★★ **测试陷阱·时钟污染**：`_eq_deadline() = min(now+per, _DECISION_STARTED_WALL + EQ_TOTAL_BUDGET[12s])`，
而 `_DECISION_STARTED_WALL` **只在 `_decide_impl` 入口刷新**。测试若**直接调策略子函数**（不经 `decide`），
该值停留旧值 ⇒ 文件跑够 12s 后 deadline 恒过期 ⇒ `monte_carlo_equity` 首次查钟即 break、`total==0`
⇒ **`equity.py` 返回兜底 0.5** ⇒ 阈值比较全失效（表现：AA→fold、K6o→allin 的"方向颠倒"，随机器快慢时有时无）。
**修法在测试侧**：断言前 `strategy._DECISION_STARTED_WALL = time.time()`（`test_log_v2.py` 的 `_reset_decision_clock()`）。
**勿在生产代码里自动重置** —— 会破坏一次决策内多路 eq 共享截止时刻的预算约束。
