# BotBattle 提交版构建 —— 把 Python 单文件 bot 冻结为 Linux x86_64 ELF
#
# 选 bullseye（Debian 11, glibc 2.31）而非最新 bookworm，是为了让产物
# 在裁判环境（可能较旧，如 Ubuntu 20.04）也能运行：用旧 glibc 构建的
# ELF 能在新旧 glibc 上都跑，反之则不行（"GLIBC_2.36 not found"）。
FROM python:3.11-slim-bullseye

# PyInstaller：把 .py + Python 解释器打包成单文件 ELF
#   --onefile : 单个可执行文件（真 ELF，非 .pyz）
#   --strip   : 去符号表，减小约 30% 体积
#   --clean   : 清理 PyInstaller 缓存，保证干净构建
RUN pip install --no-cache-dir "pyinstaller>=6.10,<7"

WORKDIR /src
COPY poker_bot.py /src/poker_bot.py

RUN pyinstaller --onefile --strip --clean --name poker_bot poker_bot.py

# 产物路径：/dist/poker_bot
