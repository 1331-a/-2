# -*- coding: utf-8 -*-
"""
main.py — 程序入口。

本地运行（模拟平台交互）：
    echo '{"requests":["{\\"blind\\":10,\\"myID\\":0,\\"pot\\":30,\\"hand\\":[\\"SA\\",\\"HA\\"],\\"publiccard\\":[],\\"curbet\\":[10,20],\\"leftbet\\":[990,980]}"],"responses":[],"data":"","globaldata":""}' | python main.py

提交到 BotZone 时，请用 bundle.py 生成单文件 botzone_submit.py 后上传。
"""

import bot

if __name__ == "__main__":
    bot.run()
