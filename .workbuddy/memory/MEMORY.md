# 项目长期约定（德扑双人机器人）
> 详情：`项目交接说明.md`/`代码逐行详解.md`/`文献调研_可借鉴方案.md`；逐日 `YYYY-MM-DD.md`；A/B 方法与陷阱见技能 `poker-strategy-ab`。按重要性递减。

## 工作流
收尾：`cd 内容 && python bundle.py` → `cp 内容/botzone_submit.py botbattle/poker_bot.py`(cmp) → `git commit -F .git/COMMIT_MSG_TMP.txt` → push。交付前 13 测试全量回归。冒烟 history 必须 dict 列表，否则 bot 静默返回 0。
★本机 `refs/remotes/origin/*` 写不进去（`status -sb` 恒显 `[gone]`）⇒ **判断是否真推上去用 `git ls-remote --heads origin main` 对比本地 HEAD**。

## 平台协议
BotBattle HU 70 手/盲注 50-100/初始 20000/**60s 每步**/按总筹码定胜负。牌号 n=rank*4+suit，**内部编码=平台+8**。response：-1fold/-2allin/0call-check/>0raise-to。history 不含 blind；hand 0-based（`load_botbattle` meta 是 1-based，**分析用 `req['hand']`**）。**action.amount：raise/allin=本街 raise-to，call=本次增量** ⇒ 尺寸=amount−本街累计；**重建底池用 GameState**。对手弃牌不可见→按 globaldata 增量推断。单挑：翻前 dealer(SB) 先、翻后 BB 先。
★ `state.total_win_chips` 是按座位的净额 ⇒ `lead = twc[我]−twc[敌]` 是单座位值的 2 倍（[−590,590]⇒−1180）。
★ **平台消费的是 `response` 整数（含尺寸）**，比对行为必须用 response 口径，不是动作类型。

## 锁赢/doom（用户硬规则）
lead=我方 net−对手 net；筹码损失让 lead 变 2 倍，×2 只用一次。追回线≈75×剩余手数（固定 SB50/BB100，勿用 `state.big_blind`）⇒ doom 阈值≈落后 150×剩余手数。fold_out：`lead>2×(盲注线+invested)`→fold。doom：`lead−2×敞口≤−2×追回线`（弃牌口径 `_invested`／跟注 `+to_call`），只用原始 lead。★阈值随剩余手数线性缩小 ⇒ **末段小幅落后会自动变"必搏命"**（剩 8 手时线≈1200，自身 `to_call` 翻倍即可压过）。
★**10-01 裁决：「doom 成立→无条件 allin」不动，`to_call>0` 无门控=有意设计**（异议已被 107 次 allin 否定：对手弃 90%、+43,807）。★ **`to_call>0` 分支仍未加"太差"容错**（待用户定）。

## 规则清单（生效顺序，除注明外默认开）
1. 规则2 `_lock_win_unified`（入口）：fold_out→fold；doomed/`_profit_lock_allin`→`_doom_plan`。★A 被拒后必须 return None（否则 C 绕过）。
2. `_endgame_arbitrate`：五动作同尺度比 EU（`_win_utility` logistic）。`_cross_check_exempt` 分街（翻后≥两对 或 `_pair_is_top`；翻前 `_is_super_hand`）；★不可用翻前名单判翻后。回退 `WB_NO_CROSS_STRONG_PASS=1`。
3. 规则10 求稳：lead≥0.70×锁赢线 或剩≤8 手领先→主动 check/被动只跟；强牌例外（10-01 配对模拟证伪「放行翻前」⇒保持）。**只在"我方领先"生效**。
4. 规则16/17：跟全下门槛按剩局/对手频率下调至 ≤0.09；翻后按盈利档 ±。
5. 规则18 搏命区：`lead≤−GAMBLE_LINE_FACTOR(0.80)×2×追回线`→牌烂(非太差) allin、牌好慢打；过 `_shove_fold_ok`(eff_fold≥0.45)。**10-12 用户新规：0.95→0.80 + 太差不推（见下）**。
6. 规则19/学习：小注作废 + 样本≥4 胜率<0.35→raise 降级。★ 门槛极脆（见工具陷阱）；已改 `SMALL_BET_MIN_N=10`。
7. 注额上限：翻前≤1000；翻后<三条≤3000（小两对≤2000）；≥三条不限（只约束主动）。
8. 规则20 `_big_money_guard`：to_call>3000 且<三条→fold；主动全押只允许≥三条/翻前 AA·KK·QQ·JJ·AKs（★故意不给 lk 免检口）。★顶两对豁免 `_is_top_two_pair()` **需同时改 4 处**。
9. `_doom_call_upgrade`：跟注口径 doom→强牌 allin、弱牌 fold。
10. ★规则11 公面同花威胁（只对 3+ 同花 + 对手>3000；★缺陷：不看已成牌/赔率）：全量 895 命中 7 次（10-11 手5/6 都错）。豁免已实现但**默认关**：`FLUSH_MADE_PASS`/`PAIRED_TRAP_MADE_PASS`/`BIGMONEY_TWOPAIR_PASS`。

## ★ 搏命区新规（10-12 用户指令，已实装默认开，提交 0288ce7）
- `GAMBLE_LINE_FACTOR` **0.95→0.80**（回退 `WB_GAMBLE_LINE=0.95`）。
- 新增 `_gamble_hand_trash`（翻前 百分位 >`GAMBLE_TRASH_PCT`=0.80；翻后 无对子+无听牌+**连一张高张都没有**）+ `_gamble_trash_pass`（**剩 ≤`GAMBLE_SHOVE_FORCE_HANDS`(8) 时不允许跳过**）。落点 `_gamble_plan` + `_doom_plan` 的 `to_call<=0` 分支。回退 `WB_NO_GAMBLE_TRASH=1` / `WB_GAMBLE_TRASH_PCT=`。
- 依据（大注复查 125 笔）：`allin`+**高牌 77 笔 −32,100（均 −417）** vs `allin`+口袋对 7 笔 +20,600；翻前 allin 按百分位 **0.80~1.00 的 19 笔 −18,200**（亏损全在最烂 20%）⇒ 门槛取 0.80。**弃牌权益(+100)只有被跟代价(−20,000)的 1/200 ⇒ 对手跟注率 >1.6% 即负 EV（实测 2.6%）**。
- A/B 86/1360=6.32%、对照 0、净增 42 次 allin。★ 与三条用户旧规则冲突（18b/18/1）⇒ **改了 7 条断言**，保留 K8o(0.36) 等"烂但不太差"样本。
- ★教训：**"这次先不做、等下次"的规则必须加"还有下次吗"的门控**（`test_strategy` 报"剩2手"才发现）。

## 出口链（★最大结构问题）
入口短路 `_lock_win_unified`/`_gamble_plan` **实测 33.9%（几乎全是 `_fold_out_active` 锁赢弃牌）**→决策层→出口 10 层：`_lock_win_tail_guard`→`_bet_cap_guard`→`_aggressive_strong_bet`→`_bluff_cap_guard`→`_stability_guard`→`_normalize`→`_endgame_arbitrate`→`_big_money_guard`→`_cheap_call_guard`→`_doom_call_upgrade`（v50 只有 `_normalize`）。
★逐层实测（948 点，改写 116 次/98 点）：**更保守 77 : 更激进 5 = 单向保守机器**。`_stability_guard` **39**（36 翻前）/ `_bet_cap_guard` 32 / `_aggressive_strong_bet` 12 / `_doom_call_upgrade` 11 / `_cheap_call_guard` 7 / `_endgame_arbitrate` 6（唯一主要"更激进"）/ `_normalize` 5 / `_big_money_guard` 3 / `_bluff_cap_guard` 1 / **`_lock_win_tail_guard` 0（627 调用 0 改写；冗余但**不建议删**——锁赢安全网）**。层间打架仅 1 次。
★归因：翻前 35.2% / 入口短路 33.9% / 主动侧 17.8% / 面对下注·牌型尺寸 5.7% / 硬规则 5.4% / **eq 门槛仅 2.0%**；出口链净改写 10.3%，**eq 门槛结论 36.8% 被出口链盖掉** ⇒ `eq` 权重低是规则堆出来的。
★★「好牌也消极」证据：77 次保守改写里 **26 次（33.8%）落在 `eq 超门槛 ≥+0.10`**（中间地带 0~+0.10 为 0，两极分布）——`eq0.901→allin→call→fold`、`eq0.896→raise→call→fold`。
⇒ **`eq` 权重天花板低**（选项B 试点净 0/948）。★ 唯一越过出口链的办法 = `EQ_VETO`（见下）。

## ★★ EQ_VETO（10-11 用户拍板选项②，已实装默认开，提交 6ec4374）
逐层否决 `_bet_cap_guard`/`_normalize`/`_big_money_guard`/`_cheap_call_guard` 的"更保守"改写（判据 `eq ≥ eff_req+margin+EQ_VETO_DELTA(0.10)`，数据来自 `_face_bet` 曝露的 `_LAST_REQ_INFO`，落点与 `WB_FACE_LOG` 一致）。
`EQ_VETO_MAX_RANK`（fold0/check1/call2/raise3/allin4）：**3 = 可恢复加注、不可恢复全押** ⇒ 保住"好牌敢加注"、去掉"弱牌 lk 主动推光"。三档（对照臂均 0）：MAX=4→18 点/11回归；**MAX=3→16 点/12回归**；MAX=2→5 点/13回归。回退 `WB_NO_EQ_VETO=1`。★会**越过规则20 的 3000 上限**（用户批准，`test_preflop_cap` C2 断言已放宽到 ≤3000）。
★更正：`_cheap_call_guard` 是**【方案A·2026-09-24 用户规则】**，此前误标"我方、不碰用户规则"。

## 对手/胜率
算力 MC=30000/预算 5.0s/全下 20000·4.0s/EQ_TOTAL 12.0s；播种 `equity._rng`+全局 random 两处。`equity_best()` 河/转牌精确枚举。对手范围系统性偏窄 2 倍→`RANGE_SOFT_TAIL`（★全下禁用）。★`_eq_deadline` 兜底不能无界（曾致单步 277s 判负）。翻前尺寸 `OPEN_SIZE_BB`（只改它无效，前 8 手不生效；`hands_seen=0→250` vs ≥8→298）。对手 code A：eff_vpip 0.89 / 翻前松翻后 fit-or-fold、VPIP 0.87 弃牌率 0.34 的**跟注站**。**内置对手强于本 bot；打不过 v50 是首要问题**。

## ★★「一直输」的结构诊断（10-12，11 场 770 手，净 −10,479）
**三条独立线索同一根因：价值/诈唬倒挂（弱牌乱进攻、强牌加注不足）**
1. **实战统计**：最大失血 = **「投入后弃牌」335 手 −73,052**（其中**主动加注后弃 72 手 −48,052**）；`allin` +28,464、`raise` +31,188。唯一大盈利 = **`flop/raise` +29,515**。★别混算各街全押：拆开后 `preflop/allin` −27,500、`flop/allin` −16,400、`river/allin` −11,540，`turn/allin` +41,397 **仅 3 次=纯方差**。
2. **v50 静态对拍（09-28）**：面对 70% 池，**v50 强牌加注 500 / 本版 280**；**v50 对听牌·空气 fold / 本版 call·raise**。原文"本版并不保守，反而更爱用听牌/空气留在池里。"
3. **v50 结构差异**：`doomed` **只放宽注额上限、不强制 allin**（原文"强制 allin 是这两个月最大的亏损源"）；求稳门槛 **0.80 且只作用翻后**。
★ **胜负机制**：翻前全押 138 次，对手弃牌 130 次（94%，每次只赚 100~300 **追不回落后**），仅 8 次被跟 = ±20,000 ⇒ **每场约 1 次被跟决定胜负**；输的场次全押 10~25 次、赢的 1~5 次。
★ **B 类 72 手归因**：**翻前开池 61 手（−36,027，75%）** vs c-bet 11 手；"对手过牌→规则12"路径 **0 次**。`BLUFF_BUFFER_EXTRA` A/B=0/1058 ⇒ 诈唬分支非主路径。弃于 river 的 9 手均 −1,367 最大。典型案例手10：翻前开池300→flop 跟390→turn 跟1035→river 弃 −1725 ⇒ **问题在"翻后跟注门槛"不在"弃牌"**。
★ **`_face_bet` 有「牌型空洞」**：分类 `strong(≥两对 或 eq≥0.78)/good(eq≥0.60)/medium(eq≥0.50)/big_draw(outs≥8)/draw(outs≥4)`，到底部是 **L5534 兜底 `return fold`**；`eq∈[~0.40,0.50)` 且无听牌 ⇒ 全 False ⇒ 兜底弃、**完全不看赔率**。实测 28 点里 18 点落兜底（画像 to_call≈1/4 池、eq 0.233~0.490、slack 全正）。★`medium` 入口 eq≥0.50 + 分支要求 +0.03 ⇒ `eq∈[赔率门槛,0.50)` 连 medium 都进不去。
★ **复核后亏损结构（仅 5 份真实对抗）**：fold 31 手 **−19,682**；按牌型 **一对 21 手 −24,638(均 −1,173) 最大**、高牌 −940、三条 +40,628；投入档 **500~1500 的 27 手 −19,086** 唯一亏钱。
★ 文献（`文献调研` §9，NeurIPS 2018）：`eq`+`range_pct` 双标量="叶子只有一个值" ⇒ 单值精修天花板低；**§9.4① 解法：单值→4 元策略 {现状/偏弃/偏跟(station)/偏加} 取最坏**（§9.7 曾因"低敏感 1.4%"暂缓，**但可能是出口链压制的假象**）。
★ **已排除**：开池范围收紧（A/B 证有害）、纯诈唬门槛（0/1058）、规则12 路径（0 次）、出口链（28 点仅 8 点改）、`_stability_guard`（只作用领先）、"代码缺对手条件化"（误判）、版本回退（两版只差 1.7%）。
**做法方向（未落地）**：① 收紧跟注链（占可省 70%）② 尺寸回归 2.5~3BB ③ 底对不在高张面加注 ④ 末段阈值缩放（**用户硬规则必先问**）⑤ `_face_bet` 空洞补"赔率优先"分支（影响面大）。详见 `复盘_20261012_归因总表.md` / `复盘_20261012_搏命前漏损账本.md` / `复盘_20261012_大注复查与搏命区新规.md`。

## ★★ 重放保真度（重放 ≠ 平台，确定性差异）
**本地重放与平台真实决策只有 80~86% 一致**（response 口径 40.9%），与代码版本×6/种子×5/MC 算力/deltas 口径全无关。
**主因**：`_opp_check_bet` 被 **规则19 `_small_bet_futile`** 拦下（依赖对手模型小样本表）。关规则19 → 新日志 31→17。**凡依赖小样本学习表的规则，重放都可能整类判错**（`_check_bet_weight`/`_learned_size`/`learned_fold_rate`/`_small_bet_bluff_read`/`_delayed_aggression_bonus`）。
★**判读**：✅ A/B **相对**比较仍有效（共享偏差）；❌ **单点归因失效**（"手X走第N行"只对重放成立）。
★ **落地**：`SMALL_BET_MIN_N` **4→10**（提交 1f899e2；A/B 39/1306=2.99%、对照 1/1306、34 点映射 +6,436、保真度 20.1%→11.0%）；`bot.py` 新增 `[MODEL]` stderr 自检行（`seen/vpip/arch/sfs_n/sfs_fold/resp_ev`）。★ 尺寸差异成因：**平台开局是"热"的**（模型经 globaldata 跨对局延续）；但 `_replay_seq.py` 连着重放**并未改善** ⇒ **仍有未解释项，别宣称已解决**。
★ 保真度**随局数漂移**：前 11 手 ≈96% 一致 vs 全场 11~14% ⇒ 独立支持"热启动/状态漂移"。
★ 战报：18:52 赢 +19,280、17:21 输 −19,990、21:55 输 −19,782（均 vs code A）⇒ **单场 70 手不足以评价一次改动**。

## 工具陷阱
★规则标签≠真凶（逐层 monkey-patch 看 before→after）。★★报「变化 N 点」必须重跑+对照臂（跨进程噪声 0.5~1%）。★`diff_ab.py --off-env` 列方向反。★自对弈双方 owner 同一 id，先确认座位。★★「只落后才生效」的规则用内置对手配对必然假阴性 ⇒ 用 `sim_early.py --selfab`。`duel.py` 不可用。
★★ **改一条硬规则后 diff 报 0 —— 三步排查**：①加触发计数器 → ②找"下一个接走者"（同人群常被多条**串联**规则覆盖；标记位定位，如「大注/突袭」族 15 点里 14 点 `_OPP_JUMPED=True`） → ③查出口链。★检查作用域诚实：不排除"全下点位"会**绕过规则16/17**。
★★ **`load_botbattle` 双口径**：`req['hand']` 是平台 0-based，`meta['hand']` 是 +1。
★★ **自对弈日志**（`bot_a`/`bot_b` 的 `owner_display` 都是 j1331）**无法确定我方座位** ⇒ 分析任何日志前先查 owner_display；11 份里 6 份是自对弈。
★ **牌型归因必须用 `_effective_category`**（`evaluate_7` 原始值会把"公面三条"标成"三条"）。
★★ **测试时钟污染**：`_eq_deadline = min(now+per, _DECISION_STARTED_WALL + EQ_TOTAL_BUDGET[12s])`，`_DECISION_STARTED_WALL` **只在 `_decide_impl` 入口刷新**。测试若**直接调策略子函数**（不经 `decide`）⇒ 跑够 12s 后 deadline 恒过期 ⇒ `monte_carlo_equity` 0 抽样 ⇒ `equity.py` 返回**兜底 0.5** ⇒ 阈值失效（AA→fold、K6o→allin 的"方向颠倒"，随机器快慢时有时无）。**修法在测试侧**：断言前 `strategy._DECISION_STARTED_WALL = time.time()`。**勿在生产代码自动重置**。
★★ **动作面变化 ≠ 收益改善**：任何"减少某类动作"的改动，**必须**用 `req['hand']` 把变化点映射回真实 `settle.deltas` 再下结论（工具 `测/_openpct_impact.py`）。例：对跟注站收紧开池 0.85→0.65 动作面 21/1058 全符合假设，但**这 21 手真实 +650（均 +31）** ⇒ 撤回（`OPEN_PCT_VS_STATION=0.85` 仅留开关）。

## 构建/平台
单文件 `内容/botzone_submit.py`；Linux ELF 由 GitHub Actions（仓库 1331-a/-2，workflow build-elf）产出；artifact 常下成 22 字节空 zip。★平台 1 核/512MiB/无网络/60s ⇒ **纯 Python 不引 numpy**。`测/学习升级版/poker_bot` 是用户 ELF，勿动。★技术判负(09-28)根因未定位。
★ **识别任意 `poker_bot` ELF 的打包版本**：遍历常量表读 git hash。
★ 三个"升级版"ELF = `学习升级版` f34f565(09-30)、`参考升级版` a9bc958(10-09)、`参考升级版2(v80以后)` 6ec4374(10-12)。

## 待办
① `_doom_plan` 的 `to_call>0` 分支是否也加"太差"容错（本次未动，用户 09-28 裁决过）；② 强牌加注尺寸是否调大（v50 对拍 280→更大）；③ `to_call==0` 未见翻牌是否先过牌（手58）；④ §5 规则11 豁免是否启用（3 开关）；⑤ `_face_bet` 空洞补"赔率优先"分支；⑥ 收紧跟注链/尺寸回归 2.5~3BB/底对不在高张面加注；⑦ 复核 §9.7"低敏感"是否出口链假象；⑧ 拉翻前 Nash 蓝图（文献资产2）。
★ 行为面 6.32%（净增 42 次全押）不算小，**先推上去实跑几场**，盯三个数：每场 all-in 次数 / 全押被跟率 / 每场最大单笔亏损。
