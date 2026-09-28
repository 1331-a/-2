# v50（纯数值型）vs 当前版 对比分析

> 生成时间：2026-09-28
> v50 来源：`测/poker_botv50`（ELF 7,363,560 字节，BuildID `59f7026d...`，Python 3.11）
> 提取方式：PyInstaller CArchive 解包 → `poker_bot` 条目（zlib）→ marshal 装载 → 结构/常量/docstring 还原
> 注意：本文所有 v50 参数均从字节码常量表**直接读出**，非猜测。

---

## 一、核心结论（一句话）

**v50 是「一个 decide 主干 + 三个决策函数」的数值型策略；当前版是「主干 + 十几层补丁函数」的规则堆叠型策略。**
v50 用**统一的百分比阈值和胜率分档**决策；当前版用**一条条用户硬规则（锁赢/doom/搏命区/大额闸门…）依次拦截**。
用户感觉 v50 更强，最可能的原因不是某个参数更好，而是**当前版的规则层之间存在互相绕过、优先级打架的空间**——这正是这两周反复修 bug（A 分支绕过三道门控、C 分支同式后门、第 43 手连环送 20,000）的根源。

---

## 二、结构对比

| 维度 | v50 | 当前版 |
|---|---|---|
| 形态 | 单文件（bundle 前就是单文件） | 6 模块 + `bundle.py` 打包 |
| 顶层函数/类 | **91 个** | **110 个**（strategy.py 单文件） |
| 全部 code 对象 | 213 | — |
| `strategy.py` 行数 | ≈2,600（估算） | **5,032** |
| 打包后行数 | ≈3,400 | **6,855** |
| 决策主链路 | `decide → _preflop_decide / _postflop_decide → _face_bet / _check_side` | `decide → _lock_win_unified → _decide_impl → _endgame_arbitrate → _big_money_guard → _normalize`（**5 层出口拦截**） |
| 规则表达 | 阈值 + 分档（数值） | 命名规则（规则2/10/16/17/18/19/20…） |

### v50 的决策函数清单（全部 91 个中的决策相关部分）

```
decide                          # 唯一入口
├─ _preflop_decide              # 翻前总调度
│  ├─ _preflop_allin_decide     # 面对全下：4 步（胜率/必要胜率/盈亏分档/极端赔率）
│  ├─ _button_open              # 庄家位开池
│  ├─ _button_vs_3bet           # 面对 3-bet
│  ├─ _bb_option                # 大盲平跟后的选择
│  └─ _bb_defend                # 大盲防守（底池赔率推导范围 + 极化 3-bet）
└─ _postflop_decide             # 翻后总调度
   ├─ _check_side               # 无需跟注时（主动侧）
   │  └─ _check_side_stable     # 求稳分支
   └─ _face_bet                 # 需要跟注时（被动侧）
      └─ _risk_avoid_route      # 公对弱两对保守路线
```

**关键：v50 的出口只有一个 `_normalize`（纯合法性夹紧），没有任何「决策改写层」。**
当前版在 `decide` 出口串了 5 道改写：`_lock_win_unified`（3 分支）→ `_endgame_arbitrate`（4 护栏）→ `_big_money_guard`（2 规则）→ `_allin_floor_guard` → `_normalize`。

---

## 三、v50 的关键数值参数（从常量表实读）

### 3.1 赛制状态机 `_match_adjust`（v50）
```python
nums = [2, -2, 15, 30, 0.7, -30]
strs = ['doomed', 'pressure', 'protect', 'desperate', 'normal']
```
- 领先/落后按 **BB 数** 分档（±2 / ±15 / ±30 BB）
- `protect` 触发：大幅领先 + 剩手数近终局
- `doomed`：确定性 doom 公式（与当前版同源）
- **`steal` 状态在 v50 里已经存在**（见 docstring），当前版也保留了

### 3.2 求稳模式 `_stability_mode`（v50）
```python
nums = [1, 0.2, 0, 0.8]
```
- 对手全押手数占比 ≥ **20%**（`0.2`）
- 或 lead ≥ **0.8** × 绝对安全线
- 当前版：`STABILITY_LINE_FACTOR=0.60`，v50 是 **0.80**（更晚求稳 → 更敢打）

### 3.3 盈利锁胜 `_profit_lock_allin`（v50）
```python
nums = [0, 600, 1.0, 0.25]
```
- 条件：`总盈亏 > 0` 且 `累计投入 > 总盈亏 + 600` 且 `eq vs 随机牌 > 25%`
- 当前版：`PROFIT_LOCK_CONST` 与 `PROFIT_LOCK_EQ` 同源，但**现在被 `_doom_plan(allow_free=True)` 包装**
- **注意 v50 的门槛是 600，比当前版记忆里的 2000 更低**——v50 更早触发锁胜

### 3.4 翻前面对全下 `_preflop_allin_decide`（v50）
```python
nums = [0.9, 0.7, 0.6, 0.35, 0.02, 1.0, 0, 15]
strs = ['big_lead', 'lead', 'even', 'behind', 'big_behind']
```
四步法：
1. 胜率 = 我方手牌 vs **对手 all-in 范围**（按原型收紧：rock≈AA/KK，maniac≈宽）
2. 必要胜率 = 跟注额 / (跟注后总底池)
3. **按累计盈亏分 5 档**（big_lead / lead / even / behind / big_behind）调门槛
4. **极端赔率优先（防反向剥削）**：`eq ≥ 必要+10%` 无条件跟、`eq ≤ 必要-10%` 无条件弃

> 当前版对应的是 `_endgame_arbitrate` 里的 EU 比较 + `UA_CALL_DAMP`。v50 的「±10% 无条件」比当前版的 logistic 效用更**可预测**。

### 3.5 doom 相关（v50）
`_bet_limit` 中：
```python
nums = [1152921504606846976]   # 2^60，表示「不限」
strs = ['doomed', 'preflop']
```
- **v50 的 doomed 是 `_bet_limit` 里「不限注额」的一个分支**，不是独立的出口改写层
- 也就是说：**v50 的 doomed 只放大注额上限，不会强制改写动作**——这与当前版「doomed → 无条件 allin」有本质区别
- 这正是 45a8fb4 修掉的那个病灶：当前版把 doomed 变成了一条**能覆盖其他所有决策的硬指令**

---

## 四、v50 的「纯数值」体现在哪

| 机制 | v50 做法 | 当前版做法 |
|---|---|---|
| 手牌强度 | `hand_percentile` 百分位 + `chen_score` | 同源（继承自 v50） |
| 范围估计 | `_opp_range_pct`：`vpip` → 0.22/0.7/0.55/0.8/0.6 → clamp[0.08, 0.95] | 增加了本街加注收窄（45a8fb4 新增） |
| 开池尺寸 | `OPEN_SIZE_*` + `bucket_to_frac` 学习 | 相同，但额外乘 `_open_weight` 条件化 |
| 翻后下注 | `_bet_fraction` × `_board_texture` 湿润度 | 同源 + 多道金额上限（`_bet_limit` / `_big_money_guard`） |
| 全下决策 | 胜率 vs 必要胜率，**单一公式** | EU 比较 + 4 护栏 + 3 门控 |

**共同点比想象的多**：v50 的牌力评估、MC 胜率、对手画像、开池/防守范围表**都被当前版继承了**。
**差异集中在「出口」**：v50 的出口是纯数值判定；当前版是规则拦截网。

---

## 五、当前版相对 v50 的「新增复杂度」清单

按 `strategy.py` 函数逐个核对，**v50 没有、当前版新增的决策函数**：

| 新增函数 | 作用 | 风险 |
|---|---|---|
| `_lock_win_unified` | 规则2 统一锁赢（A/B/C 三支） | 高：分支间可互相绕过（已修） |
| `_doom_plan` | doom 三道门控 | 高：需配合 A 分支 `return None` 才生效 |
| `_endgame_arbitrate` | 终局 EU 仲裁 + 4 护栏 | 中：逻辑最复杂，`UA_*` 参数多 |
| `_endgame_eu` / `_endgame_matters` | EU 计算与触发面 | 中 |
| `_gamble_zone` / `_gamble_hand_good` / `_gamble_plan` | 搏命区（规则18） | 中 |
| `_shove_fold_ok` | 搏命全押弃牌率门控（45a8fb4） | 低：新增，已验证 |
| `_big_money_guard` | 规则20 大额闸门 | 中 |
| `_stability_guard` | 规则10 求稳执行 | 低 |
| `_doom_call_upgrade` | 规则2 补漏（暴露） | **已废弃**（注释保留） |
| `_lead_allin_shift` | 规则17 盈利收紧 | 低 |
| `_lock_win_tail_guard` / `_lock_win_engaged` / `_lock_win_legal` | 锁赢辅助 | 中：耦合深 |
| `_profit_lock_allin` | 规则2 C 分支 | 中：曾被 A 分支绕过 |

**v50 里对应位置的实现**：
- 没有 `_lock_win_unified` → 锁赢逻辑分散在 `_fold_out_active` + `_bet_limit` + `_profite_lock_allin`（**三个独立函数，互不覆盖**）
- 没有 `_endgame_arbitrate` → 翻后直接 `_face_bet` 里用胜率判断
- 没有 `_gamble_zone` → 搏命由 `_match_adjust` 的 `doomed/desperate` 状态 + `_bet_limit` 放宽表达

---

## 六、为什么 v50 可能「打得更稳」

1. **决策路径短**：v50 从入口到出口最多 3 层；当前版最多 5 层改写 + 十几条命名规则。
2. **规则之间不互相覆盖**：v50 的 doomed 只改「注额上限」，不强制改动作 → 不可能出现「A 分支绕过 B 分支」这类 bug。
3. **阈值统一**：v50 用 BB 数（±2/±15/±30）和胜率百分比（±10%）表达风险，当前版用「规则编号」表达，规则的交互需要人工推演。
4. **求稳门槛更高（0.80 vs 0.60）**：v50 更晚进入保守模式 → 领先时仍保持进攻性。

但同时要注意：**v50 也有明确弱项**（从它自己的 docstring 和上周失败局看）：
- 锁赢判定用 `_fold_out_active` 独立函数，缺少当前版的「弃牌会不会被锁赢」正向验证
- 没有当前的「对手本街加注收窄范围」（v50 的 `_opp_range_pct` 只看 vpip）→ **eq 会高估，薄跟注偏多**
- 没有 `_shove_fold_ok` 这类弃牌率门控 → 垃圾牌推光的问题 v50 同样可能有

---

## 七、建议

**不建议直接回退到 v50**（会丢掉 45a8fb4 修的三个真 bug）。建议**借鉴 v50 的结构**，做一次减法：

1. **把出口改写层收敛成一层**：`_lock_win_unified` + `_endgame_arbitrate` + `_big_money_guard` 合并为一个「终局仲裁器」，内部用统一尺度（EU 或数值门槛）判定，避免分支绕过。
2. **doomed 降级为「放宽注额上限」**（学 v50），不再强制改写成 allin —— 强制 allin 是这两个月最大的亏损源。
3. **求稳门槛 0.60 → 0.70~0.80**（对齐 v50），领先时更敢打。
4. **给当前版补上 v50 没有的两项**（这两个是真改进）：本街加注收窄范围、搏命全押弃牌率门控。

---

## 附：还原方法与复现命令

```bash
cd 测
pip install pyinstaller xdis
# 1) 解包 CArchive
python -c "from PyInstaller.archive.readers import CArchiveReader as C; r=C('poker_botv50'); print(r.toc['poker_bot'])"
# 2) 按 _start_offset + dpos 取原始段，zlib 解压（wbits=15）→ marshal.loads
# 3) 结构/常量/docstring 见本目录：_v50_body.bin / v50_structure.txt / _v50_docs.txt / _v50_asm_out.txt
```

**产出文件**：
- `测/_v50_body.bin` — 解压后的 marshal 字节码（164,424 字节，对应 .pyc body）
- `测/v50_structure.txt` — 函数树 + 每函数常量表
- `测/_v50_docs.txt` — 全部函数 docstring（中文业务说明，可直接读）
- `测/_v50_asm_out.txt` — 关键函数字节码反汇编（5,869 行）
