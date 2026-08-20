#!/usr/bin/env bash
# 一键构建 Linux x86_64 ELF —— 原生 Linux 方式（无 Docker，需本机有 python3）
#
# 适用：任意 Linux 服务器 / WSL2 Ubuntu / GitHub Codespaces / 云主机。
# 用法：cd botbattle && bash build_local.sh
# 产物：botbattle/dist/poker_bot
set -euo pipefail
cd "$(dirname "$0")"

# 检查 python3
command -v python3 >/dev/null || { echo "未找到 python3，请先安装"; exit 1; }

echo "[1/3] 安装 PyInstaller ..."
python3 -m pip install --user --upgrade "pyinstaller>=6.10,<7"

echo "[2/3] 构建单文件 ELF ..."
python3 -m PyInstaller --onefile --strip --clean --name poker_bot poker_bot.py

echo "[3/3] 校验 ..."
chmod +x dist/poker_bot
file dist/poker_bot || true
ls -lh dist/poker_bot

echo ""
echo "✅ 完成：dist/poker_bot 即 BotBattle 提交用 ELF"
echo "   本地测试：echo '{\"requests\":[...]}' | ./dist/poker_bot"
