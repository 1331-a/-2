# BotBattle 提交版构建说明

把德州扑克 bot 冻结为 **Linux x86_64 ELF 可执行文件**，用于 BotBattle 平台提交。

## 文件清单

| 文件 | 作用 |
|------|------|
| `poker_bot.py` | 构建源（= `内容/botzone_submit.py` 的字节副本，原始文件保留不动） |
| `Dockerfile` | Docker 构建镜像（python:3.11-slim-bullseye + PyInstaller） |
| `build.sh` | Docker 方式一键构建（推荐） |
| `build_local.sh` | 原生 Linux 方式构建（无 Docker 时用） |

仓库根另有 `.github/workflows/build-elf.yml`，可在 GitHub Actions 上构建并下载 ELF。

## ⚠️ 为什么这里没有现成的 ELF

PyInstaller **不支持跨平台编译**——要产出 Linux x86_64 ELF，必须在 Linux x86_64 环境上运行 PyInstaller。本机是 Windows，且**没有** Docker / podman / WSL 发行版，所以无法在此沙箱里直接生成 ELF。下面的脚本会在任何 Linux/Docker 环境一键产出。

## 三种构建方式（任选其一）

### 方式 A：Docker（推荐，最省事）
前置：装好 Docker（Windows 用 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，Linux 用原生 docker）。

```bash
cd botbattle
bash build.sh
```
产物：`botbattle/dist/poker_bot`

### 方式 B：原生 Linux（服务器 / WSL2 Ubuntu / 云主机）
前置：有 `python3`（≥3.8）。

```bash
cd botbattle
bash build_local.sh
```

### 方式 C：GitHub Actions（连服务器都没有时）
把仓库推到 GitHub，手动触发 `build-elf` 工作流（Actions 页 → Run workflow），
构建完成后从 Artifacts 下载 `poker_bot-linux-x86_64`。

## 校验产物

```bash
file dist/poker_bot
# 期望输出：ELF 64-bit LSB executable, x86-64, ..., dynamically linked ...

./dist/poker_bot < input.json   # 直接运行（无需 python）
```

`poker_bot.py` 仅用标准库（json/sys/time/random/math/itertools），无第三方依赖，
PyInstaller 不会漏抓 hidden imports，构建稳定、产物约 10–15 MB。

## 移植性说明

Dockerfile 故意选 `python:3.11-slim-bullseye`（Debian 11，glibc 2.31）而非最新版，
是为了让产物在较旧的裁判环境（如 Ubuntu 20.04）也能运行：
**用旧 glibc 构建的 ELF 能在新旧 glibc 上都跑；反之则会出现 `GLIBC_2.36 not found`**。
若确认 BotBattle 裁判是较新系统（Ubuntu 22.04+），可改用 `python:3.11-slim` 提速。

## 与 BotZone 版的关系

- 行为完全相同（同一份代码），协议解析、决策、安全兜底一字未改；
- 仅入口由 `python botzone_submit.py` 变为直接 `./poker_bot`；
- 原始 `内容/botzone_submit.py` 保留不动，BotZone 提交继续用它。
