# -*- coding: utf-8 -*-
"""【临时】把 open_pct A/B 的 21 个变化点，映射到真实对局结果。

读 测/_openpct_ab.txt 里 "reqNN|hMM|..." 的标签，回到日志查该手的净变。
"""
import io, os, re, json, glob, collections

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
txt = io.open(os.path.join(BASE, "测", "_openpct_ab.txt"), encoding="utf-8").read()

# 解析变化行： tag(只有前 8 位) ... reqNN|hMM|...
rows = []
for line in txt.splitlines():
    m = re.match(r"\s+(\d{8})\S*\s+req(\d+)\|h(\d+)\|(\w+)\|.*?hole\[([\d, ]+)\]\s+(\S+)\s+->\s+(\S+)", line)
    if m:
        rows.append((m.group(1), int(m.group(2)), int(m.group(3)), m.group(6), m.group(7),
                     m.group(5)))
print("解析到变化点 %d 个" % len(rows))

# 日志索引：8 位前缀 -> 文件
logs = {}
for p in sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
                + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")):
    key = os.path.basename(p)[17:25]
    logs[key] = p

PLAT = "23456789TJQKA"
SUIT = "cdhs"


def c2s(n):
    return PLAT[(n - 8) // 4] + SUIT[(n - 8) % 4]


# 逐份日志建 hand -> net 映射
def hand_nets(path):
    o = json.load(io.open(path, encoding="utf-8"))
    m = o["match"]
    seat = 0
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m.get(k) or {}).get("owner_display", "")):
            seat = i
    d = {}
    for e in o["replay"]["events"]:
        if e.get("type") == "settle":
            d[e["hand"]] = (e["deltas"][seat], e.get("reason"))
    return d


print()
print("%-10s %-4s %-16s %-22s %-16s %8s %s" % ("日志", "手", "底牌", "原动作→新动作", "", "该手净变", "结算"))
tot_old, tot_new = 0, 0
cache = {}
for key, reqh, hand, a_old, a_new, hole in rows:
    if key not in cache:
        p = None
        for k, v in logs.items():
            if k.startswith(key[:8]):
                p = v
                break
        cache[key] = hand_nets(p) if p else {}
    net = cache[key].get(reqh) or cache[key].get(hand)
    cards = ' '.join(c2s(int(x)) for x in hole.split(','))
    print("%-10s %-4d %-10s %-24s %9s %s" % (key, reqh, cards, a_old + "->" + a_new,
                                             net[0] if net else "?", net[1] if net else ""))
    if net:
        tot_old += net[0]

vals = [cache[k].get(rh) or cache[k].get(hd) for k, rh, hd, ao, an, ho in rows]
vals = [v[0] for v in vals if v]
print()
print("这 %d 手实际净变合计 = %+d（均 %+.0f）" % (len(vals), sum(vals), sum(vals) / max(1, len(vals))))
neg = [v for v in vals if v < 0]
print("  其中亏损 %d 手（合计 %+d），盈利/持平 %d 手" % (len(neg), sum(neg), len(vals) - len(neg)))
