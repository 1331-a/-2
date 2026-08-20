# 德州扑克（Heads-Up）双人机器人 —— BotZone 适配

一套完整的双人无限注德州扑克（No-Limit Texas Hold'em, heads-up）机器人，
核心游戏逻辑与平台交互逻辑完全分离，可直接提交到 BotZone 平台对战。

## 一、目录结构

```
├── cards.py          # 扑克牌表示与解析（整数编码 + BotZone 牌字符串）
├── evaluator.py      # 牌型评估器（高牌 → 皇家同花顺，7 选 5 最佳组合）
├── game_state.py     # 游戏状态建模 + BotZone 状态 JSON 解析 + 合法动作边界
├── ranges.py         # 翻前起手牌强度（Chen 公式）与范围管理
├── equity.py         # 蒙特卡洛胜率估算
├── opponent.py       # 对手建模（行为画像，跨回合/跨手牌记忆）
├── strategy.py       # AI 决策引擎（手牌强度 + 底池赔率 + 位置 + 对手画像）
├── bot.py            # BotZone 平台交互层（stdin/stdout）
├── main.py           # 程序入口
├── simulate.py       # 本地单挑对局模拟器（调试/验证）
├── test_evaluator.py # 牌型评估单元测试
├── bundle.py         # 生成单文件提交版本
└── README.md         # 本说明
```

## 二、BotZone 交互协议

### 输入（stdin，单行 JSON）

平台通过标准输入下发完整历史，格式如下：

```json
{
  "requests": ["<状态1>", "<状态2>", ...],   // 每次我方决策点的状态 JSON 字符串
  "responses": ["<动作1>", ...],             // 我方历史输出
  "data": "...",                             // 上回合持久化备注（手牌内有效）
  "globaldata": "..."                        // 上局持久化备注（跨手牌有效）
}
```

其中每个状态 JSON 字段：

| 字段 | 含义 |
|------|------|
| `blind` | 小盲注额（大盲 = 2 × blind） |
| `myID` | 当前决策玩家编号（0 或 1；0 = 庄家/小盲，1 = 大盲） |
| `pot` | 底池（所有玩家已投入筹码之和，含本轮 `curbet`） |
| `hand` | 我的两张底牌，如 `["SA", "HT"]` |
| `publiccard` | 公共牌数组 |
| `curbet` | 本轮各玩家已投入，如 `[10, 20]` |
| `leftbet` | 各玩家剩余筹码，如 `[990, 980]` |

**牌编码**：花色（`S`♠ / `H`♥ / `D`♦ / `C`♣）+ 点数（`2`~`9`、`T`=10、`J`、`Q`、`K`、`A`）。

### 输出（stdout，单行 JSON）

```json
{"response": "{\"act\": \"raise\", \"num\": 50}", "data": "...", "globaldata": "..."}
```

`response` 为动作 JSON 字符串，动作取值：

| 动作 | 含义 |
|------|------|
| `{"act":"fold"}` | 弃牌 |
| `{"act":"check"}` | 过牌 |
| `{"act":"call"}` | 跟注 |
| `{"act":"raise","num":X}` | 加注，使本轮总注额达到 X |
| `{"act":"allin"}` | 全下 |

## 三、快速开始

```bash
# 1) 运行牌型评估单元测试
python test_evaluator.py

# 2) 本地模拟对局（对抗跟注站 / 随机对手）
python simulate.py 500            # 500 手，对抗跟注站
python simulate.py 500 random     # 500 手，对抗随机对手

# 3) 本地模拟平台交互（手动喂一个状态）
echo '{"requests":["{\"blind\":10,\"myID\":0,\"pot\":30,\"hand\":[\"SA\",\"HA\"],\"publiccard\":[],\"curbet\":[10,20],\"leftbet\":[990,980]}"],"responses":[],"data":"","globaldata":""}' | python main.py

# 4) 生成 BotZone 单文件提交版本
python bundle.py   # 产出 botzone_submit.py，上传该文件即可
```

## 四、策略概述

1. **翻牌前（范围管理）**：用 Chen 公式给起手牌打分；
   - 庄家位（小盲）：开池加注（默认 Chen ≥ 2.5，对手越被动越宽）；
   - 大盲位：宽范围防守，顶级牌 3-bet；
   - 面对 3-bet：按牌力分档 + 底池赔率决定 4-bet / 跟注 / 弃牌。
2. **翻牌后（手牌强度 + 赔率 + 位置）**：
   - 成牌牌型（`evaluator`）判强度，蒙特卡洛估胜率；
   - 底池赔率 `required = to_call / (pot + to_call)` 决定跟注；
   - 庄家位（翻后有位置）更多下注 / 诈唬 / 薄价值；大盲位（无位置）更谨慎；
   - 识别同花 / 顺子听牌用于半诈唬；
   - SPR 较低时强牌直接全下。
3. **对手建模**：通过比较相邻状态推断对手动作，累计「激进程度 / 松紧程度 /
   面对下注弃牌率」，据此调整范围与诈唬频率，并经 `data`/`globaldata` 持久化。

## 五、可调参数

集中在 `strategy.py` 顶部常量，可针对不同对手风格快速调优：

```python
OPEN_SIZE_BB   = 2.5   # 庄家开池加注（BB）
THREE_BET_MULT = 3.0   # 3-bet/4-bet 倍数
CBET_SIZE      = 0.6   # 持续下注（底池比例）
VALUE_BET_SIZE = 0.7   # 价值下注
BIG_VALUE_BET  = 1.0   # 强牌大价值下注
BLUFF_SIZE     = 0.6   # 诈唬下注
OPEN_CHEN      = 2.5   # 庄家开池最低 Chen
MC_ITERATIONS  = 500   # 蒙特卡洛抽样次数
```

## 六、设计要点

- **核心 / 交互分离**：`cards`、`evaluator`、`game_state`、`ranges`、
  `equity`、`opponent`、`strategy` 为纯逻辑，不碰 stdin/stdout；仅 `bot.py`
  负责平台 I/O，便于单独单元测试与迭代。
- **牌型评估正确性**：`evaluator` 对 7 张牌做 C(7,5)=21 组合全枚举取最优，
  逻辑直观、可验证，`test_evaluator.py` 覆盖所有牌型与 A-2-3-4-5 轮子顺。
- **动作合法性兜底**：决策层统一 `_normalize` 夹紧动作，保证任何局面下
  输出的 fold/check/call/raise/allin 均合法。
