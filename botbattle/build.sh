#!/usr/bin/env bash
# 一键构建 Linux x86_64 ELF —— Docker 方式（推荐，无需本机装 Python/PyInstaller）
#
# 前置：本机已装 Docker（Docker Desktop / Linux 原生 docker 均可）。
# 用法：cd botbattle && bash build.sh
# 产物：botbattle/dist/poker_bot  （一个可执行的 Linux x86_64 ELF）
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/4] 构建 Docker 镜像 pokerbot-builder ..."
docker build -t pokerbot-builder .

echo "[2/4] 准备输出目录 ..."
rm -rf dist
mkdir -p dist

echo "[3/4] 从镜像中拷出 ELF ..."
cid=$(docker create pokerbot-builder)
docker cp "$cid:/dist/poker_bot" dist/poker_bot
docker rm "$cid" >/dev/null

echo "[4/4] 赋予可执行权限并校验 ..."
chmod +x dist/poker_bot
echo "---- file ----"
file dist/poker_bot || true
echo "---- ls -lh ----"
ls -lh dist/poker_bot

echo ""
echo "✅ 完成：dist/poker_bot 即 BotBattle 提交用的 Linux x86_64 ELF"
echo "   本地测试：echo '{\"requests\":[...]}' | ./dist/poker_bot"
