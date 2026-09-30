# -*- coding: utf-8 -*-
"""把 导出/项目交接说明.png 长图按「空白行」切成多张可上传的分页图。

为什么要切：17845px 高的长图上传到 ChatGPT / 多数平台后会被等比缩到
长边 ~2048px，文字直接糊掉不可读。按空白行切段后每张 ~2400px，清晰可读。

切点算法：先用 point+resize(BOX) 得到「每一行是否有墨迹」的一维序列，
再在目标高度附近搜索最近的空白行作为切点，保证不切断文字/表格。
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\导出"
SRC = os.path.join(BASE, "项目交接说明.png")
OUT = os.path.join(BASE, "分页")
TARGET = 2400          # 每页目标高度
SEARCH = 600           # 在目标点 ±SEARCH 范围内找空白行
HEADER = 44            # 每页顶部加的标签条高度

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def load_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def ink_rows(im):
    """返回长度 = 高度的一维序列：0 = 该行完全空白，>0 = 有内容。"""
    g = im.convert("L")
    # 阈值化：深色像素（文字/边框）-> 255，背景 -> 0
    g = g.point(lambda v: 255 if v < 245 else 0)
    # 横向 BOX 缩到 1px：每个输出像素 = 整行的墨迹比例
    col = g.resize((1, im.height), Image.BOX)
    return list(col.getdata())


def pick_splits(vals, target, search):
    H = len(vals)
    cuts = [0]
    y = target
    while y < H - 300:
        found = None
        for d in range(0, search):
            for cand in (y - d, y + d):
                if 40 < cand < H - 40 and int(vals[cand]) == 0:
                    found = cand
                    break
            if found is not None:
                break
        if found is None:
            found = y                      # 附近没有空白行，硬切
        cuts.append(found)
        y = found + target
    cuts.append(H)
    return cuts


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))

    im = Image.open(SRC).convert("RGB")
    W, H = im.size
    vals = ink_rows(im)
    cuts = pick_splits(vals, TARGET, SEARCH)
    n = len(cuts) - 1
    print("源图 %d × %d，共切 %d 页" % (W, H, n))

    font = load_font(17)
    for i in range(n):
        top, bot = cuts[i], cuts[i + 1]
        page = im.crop((0, top, W, bot))
        canvas = Image.new("RGB", (W, page.height + HEADER), "#ffffff")
        canvas.paste(page, (0, HEADER))
        d = ImageDraw.Draw(canvas)
        d.text((64, 14), "项目交接说明   ·   第 %d / %d 页   (总高 %d px, 本页 %d px)"
               % (i + 1, n, H, page.height), font=font, fill="#94a3b8")
        d.line([(64, HEADER - 8), (W - 64, HEADER - 8)], fill="#e5e7eb", width=1)
        name = os.path.join(OUT, "项目交接说明_第%02d页_共%d页.png" % (i + 1, n))
        canvas.save(name, "PNG", optimize=True)
        print("  %-46s %d × %d  %.2f MB" % (
            os.path.basename(name), canvas.width, canvas.height,
            os.path.getsize(name) / 1024.0 / 1024.0))


if __name__ == "__main__":
    main()
