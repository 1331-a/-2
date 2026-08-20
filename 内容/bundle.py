# -*- coding: utf-8 -*-
"""
bundle.py — 生成 BotZone 单文件提交版本。

把多个模块按依赖顺序合并为一个自包含的 botzone_submit.py：
  - 去掉项目内部模块的 import（合并后共享同一命名空间）；
  - 保留标准库 import；
  - 去掉各模块的 if __name__ 入口块；
  - 末尾追加统一入口 run()。

运行：python bundle.py
输出：botzone_submit.py
"""

INTERNAL = {"cards", "evaluator", "ranges", "game_state",
            "equity", "opponent", "strategy", "bot"}
# 依赖顺序（被依赖者在前）
ORDER = ["cards", "evaluator", "ranges", "game_state",
         "equity", "opponent", "strategy", "bot"]


def _strip_module(src):
    """去掉内部 import 与 if __name__ 块，返回保留的行。"""
    out = []
    in_main_block = False
    for ln in src.split("\n"):
        stripped = ln.strip()
        # 检测 if __name__ 块（跳过整块）
        if in_main_block:
            if ln and not ln[0].isspace():
                in_main_block = False
            else:
                continue
        if stripped.startswith("if __name__"):
            in_main_block = True
            continue
        # 去掉内部模块 import
        if stripped.startswith("import ") or stripped.startswith("from "):
            parts = stripped.split()
            mod = parts[1].split(".")[0]
            if mod in INTERNAL:
                continue
        out.append(ln)
    return "\n".join(out)


def bundle():
    parts = []
    parts.append("# -*- coding: utf-8 -*-")
    parts.append("# 由 bundle.py 自动生成的单文件提交版本（BotZone 用）。")
    parts.append("")
    for m in ORDER:
        with open(m + ".py", encoding="utf-8") as f:
            parts.append(_strip_module(f.read()))
    parts.append("")
    parts.append("if __name__ == '__main__':")
    parts.append("    run()")
    parts.append("")
    content = "\n".join(parts)
    with open("botzone_submit.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("已生成 botzone_submit.py，共 %d 行" % content.count("\n"))


if __name__ == "__main__":
    bundle()
