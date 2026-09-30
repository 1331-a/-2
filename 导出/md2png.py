# -*- coding: utf-8 -*-
"""把 项目交接说明.md 渲染成一张长图 PNG。

方法：markdown -> HTML（内嵌打印样式） -> Edge 无头模式截图。
先用 --dump-dom 读取真实页面高度，再按该高度截图，避免内容被裁切。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import markdown

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
MD = os.path.join(BASE, "项目交接说明.md")
OUT_DIR = os.path.join(BASE, "导出")
HTML = os.path.join(OUT_DIR, "_渲染.html")
PNG = os.path.join(OUT_DIR, "项目交接说明.png")

WIDTH = 1240          # 正文宽度（含 padding）
SCALE = 1             # 由 --force-device-scale-factor 控制

CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ffffff; }
body {
  width: %(w)dpx;
  padding: 56px 64px 72px 64px;
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
  font-size: 15px; line-height: 1.75; color: #1f2328;
  -webkit-font-smoothing: antialiased;
}
h1 { font-size: 30px; line-height: 1.35; margin: 0 0 10px 0; color: #111827;
     padding-bottom: 14px; border-bottom: 3px solid #4f46e5; }
h2 { font-size: 23px; margin: 46px 0 14px 0; color: #1e293b;
     padding: 6px 0 6px 14px; border-left: 5px solid #4f46e5; background: #f5f5ff; }
h3 { font-size: 18.5px; margin: 30px 0 10px 0; color: #334155; }
h4 { font-size: 16px; margin: 22px 0 8px 0; color: #475569; }
p { margin: 10px 0; }
a { color: #4f46e5; text-decoration: none; }
strong { color: #0f172a; font-weight: 600; }
ul, ol { margin: 10px 0; padding-left: 26px; }
li { margin: 5px 0; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 34px 0; }
blockquote { margin: 14px 0; padding: 12px 18px; background: #f8fafc;
  border-left: 4px solid #94a3b8; color: #475569; border-radius: 0 6px 6px 0; }
blockquote p { margin: 5px 0; }
code { font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: 13px; background: #f1f5f9; color: #b91c1c;
  padding: 1.5px 5px; border-radius: 4px; border: 1px solid #e2e8f0; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 14px 16px; overflow-x: auto; margin: 14px 0; }
pre code { background: none; border: 0; padding: 0; color: #1f2328;
  font-size: 12.5px; line-height: 1.6; }
table { border-collapse: collapse; width: 100%%; margin: 16px 0;
  font-size: 14px; border: 1px solid #e2e8f0; }
th { background: #eef2ff; color: #312e81; font-weight: 600; text-align: left;
  padding: 9px 12px; border: 1px solid #e2e8f0; }
td { padding: 8px 12px; border: 1px solid #e8ecf1; vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafbfc; }
""" % {"w": WIDTH}

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>项目交接说明</title>
<style>%(css)s</style></head>
<body>
%(body)s
<div id="__H" style="height:0;overflow:hidden"></div>
<script>
window.addEventListener('load', function(){
  var h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  document.getElementById('__H').textContent = 'HEIGHT_MARK:' + h + ':END';
  document.title = 'H' + h;
});
</script>
</body></html>"""

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("找不到 Edge/Chrome")


def run(args, timeout=180):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    src = io.open(MD, encoding="utf-8").read()
    body = markdown.markdown(
        src,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )
    io.open(HTML, "w", encoding="utf-8").write(
        TEMPLATE % {"css": CSS, "body": body})
    print("① HTML 生成完成:", HTML)

    browser = find_browser()
    print("   浏览器:", browser)
    url = "file:///" + HTML.replace("\\", "/")

    # ② 量高度
    prof = os.path.join(OUT_DIR, "_profile")
    dom = run([browser, "--headless=new", "--disable-gpu", "--no-first-run",
               "--user-data-dir=" + prof, "--virtual-time-budget=8000",
               "--window-size=%d,1200" % WIDTH, "--dump-dom", url])
    dom_text = dom.stdout or ""
    m = re.search(r"HEIGHT_MARK:(\d+):END", dom_text)
    if not m:
        print("   [警告] dump-dom 未取到高度，改用 1200 起步试探")
        print("   stderr 摘要:", (dom.stderr or "")[-400:])
        height = 1200
    else:
        height = int(m.group(1))
        print("② 页面真实高度: %d px" % height)

    # ③ 截图（高度 +32 余量，防最后一像素被裁）
    shot_h = height + 32
    for f in (PNG,):
        if os.path.exists(f):
            os.remove(f)
    r = run([browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--user-data-dir=" + prof, "--hide-scrollbars",
             "--force-device-scale-factor=%d" % SCALE,
             "--window-size=%d,%d" % (WIDTH, shot_h),
             "--screenshot=" + PNG, url], timeout=300)
    print("③ 截图返回码:", r.returncode)
    if not os.path.exists(PNG):
        print("   [失败] 未生成 PNG")
        print("   stderr:", (r.stderr or "")[-600:])
        raise SystemExit(1)

    from PIL import Image
    im = Image.open(PNG)
    print("④ 成品: %s  %d × %d  %.2f MB" % (
        PNG, im.width, im.height,
        os.path.getsize(PNG) / 1024.0 / 1024.0))


if __name__ == "__main__":
    main()
