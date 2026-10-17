# -*- coding: utf-8 -*-
"""漏损账本：按「我方动作模式」给每一手分类，看 doom 之前的分是从哪丢的。

数据源：`内容/记录/*log.json` 的 `replay.events`（含 action / deal_hole /
deal_board / settle），**不依赖重放**，所以口径就是平台真实行为。

每手的「我方投入」用 settle 反推（避免自己重建下注序列出错）：
  · 我方在 winners 里 → 投入 = pot − delta
  · 否则              → 投入 = −delta
（settle.deltas 是座位净额，已含盲注。）

分类（按我方动作模式 + 结果）：
  A 主动投入后弃牌   ：翻后我方有 bet/raise，最终我方弃牌
  B 跟注后弃牌       ：翻后我方只 call（无 bet/raise），最终我方弃牌
  C 我方全押被跟输   ：我方 allin、对手也 allin、我方输
  D 跟对手全押输     ：对手 allin，我方 call（非 allin），输
  E 摊牌输（未全押） ：走到 showdown，我方输
  F 翻前弃牌         ：一手没打，只丢盲注
  G 其他
"""
import argparse
import collections
import glob
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"

INIT = 20000
STREETS = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}


def parse_match(path):
    obj = json.loads(Path(path).read_bytes())
    events = obj["replay"]["events"]
    # ---- 定座位：owner_display 不能用于自对弈；这里用「我方 = 有 hole 且
    #      action 数量较多」不可靠，改由外部传入 seat ----
    return obj, events


def build_hands(events, seat):
    hands = {}
    cur = None
    for e in events:
        t = e.get("type")
        if t == "hand_start":
            cur = {
                "hand": e["hand"], "chips0": list(e["chips"]),
                "sb_seat": e.get("sb"), "board": [], "holes": None,
                "acts": [], "settle": None,
            }
            hands[e["hand"]] = cur
        elif t == "deal_hole":
            if cur is not None:
                cur["holes"] = e["holes"]
        elif t == "deal_board":
            if cur is not None:
                cur["board"] = list(e["board"])
                cur["street"] = e.get("street")
        elif t == "action":
            if cur is not None:
                # ★ 必须记录**动作当时**的牌面：用整手最终牌面判「翻后」会把
                #   纯翻前加注 + 翻后过牌/弃牌 的手也算成「翻后有 bet/raise」。
                cur["acts"].append(dict(e, _nboard=len(cur["board"])))
        elif t == "settle":
            if cur is not None:
                cur["settle"] = dict(e)
                cur = None
    return hands


def classify(h, seat):
    """返回 (类别, 我方投入, 净额, 说明)"""
    st = h["settle"]
    if st is None:
        return "?", 0, 0, "no settle"
    pot = int(st.get("pot") or 0)
    delta = int(st["deltas"][seat])
    won = seat in (st.get("winners") or [])
    contrib = (pot - delta) if won else (-delta)

    acts = [a for a in h["acts"] if int(a.get("player", -1)) == seat]
    opp = [a for a in h["acts"] if int(a.get("player", -1)) != seat]
    our_fold = any(a.get("action") == "fold" for a in acts)
    our_allin = any(a.get("action") == "allin" for a in acts)
    opp_allin = any(a.get("action") == "allin" for a in opp)
    # 我方主动 bet/raise 的街（排除 call / check / fold）；牌面按**动作当时**
    aggr = [a for a in acts
            if a.get("action") in ("bet", "raise") and int(a.get("amount") or 0) > 0]
    aggr_post = [a for a in aggr if int(a.get("_nboard") or 0) >= 3]
    fell = [a for a in acts if a.get("action") == "call"]

    reason = st.get("reason")
    if our_fold:
        if aggr_post:
            return "A 主动投入后弃牌", contrib, delta, "翻后有 bet/raise 再弃"
        if any(a for a in fell if int(a.get("_nboard") or 0) >= 3):
            return "B 跟注后弃牌", contrib, delta, "翻后只跟再弃"
        if aggr:
            return "A 主动投入后弃牌", contrib, delta, "仅翻前加注后弃"
        return "F 翻前弃牌", contrib, delta, "只丢盲注"
    if won:
        return "W 赢", contrib, delta, reason or ""
    if our_allin and opp_allin:
        return "C 我方全押被跟输", contrib, delta, reason or ""
    if opp_allin:
        return "D 跟对手全押输", contrib, delta, reason or ""
    if reason == "showdown" or not h["board"]:
        return "E 摊牌输(未全押)", contrib, delta, reason or ""
    return "E 摊牌输(未全押)", contrib, delta, reason or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*", type=Path)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    paths = list(a.logs) or sorted(
        Path(p) for p in glob.glob(str(CONTENT / "\u8bb0\u5f55" / "*log.json")))
    paths += sorted(Path(p) for p in glob.glob(
        str(Path.home() / "Downloads" / "botbattle*log.json")))

    import sys
    sys.path.insert(0, str(BASE / "\u6d4b"))
    from _range_condition_audit import match_id, match_seat

    agg = collections.defaultdict(lambda: [0, 0])   # 类别 -> [手数, 净额]
    all_rows = []
    for p in paths:
        obj, events = parse_match(p)
        seat = match_seat(obj)
        if seat is None:
            continue
        ident = match_id(p)
        hands = build_hands(events, seat)
        lead = 0
        for hn in sorted(hands):
            h = hands[hn]
            if h["settle"] is None:
                continue
            cat, contrib, delta, note = classify(h, seat)
            agg[cat][0] += 1
            agg[cat][1] += delta
            all_rows.append({
                "match": ident, "hand": hn, "ui": hn + 1, "cat": cat,
                "hole": " ".join(h["holes"][seat]) if h["holes"] else "-",
                "board": " ".join(h["board"]), "contrib": contrib,
                "delta": delta, "lead_before": lead, "note": note,
                "pot": int(h["settle"].get("pot") or 0),
                "n_act": len([x for x in h["acts"]
                              if int(x.get("player", -1)) == seat]),
            })
            lead += delta

    print("=" * 96)
    print("%-22s %6s %12s %10s" % ("类别", "手数", "净筹码", "均值/手"))
    for cat in sorted(agg):
        n, s = agg[cat]
        print("%-22s %6d %12d %10.1f" % (cat, n, s, s / max(n, 1)))
    tot = [sum(v[0] for v in agg.values()), sum(v[1] for v in agg.values())]
    print("-" * 96)
    print("%-22s %6d %12d %10.1f" % ("合计", tot[0], tot[1], tot[1] / max(tot[0], 1)))

    print("\n---- 单场净额 ----")
    per = collections.defaultdict(int)
    for r in all_rows:
        per[r["match"]] += r["delta"]
    for k, v in sorted(per.items(), key=lambda x: x[1]):
        print("  %s  %+8d" % (k, v))

    print("\n---- 最大亏损手 TOP %d ----" % a.top)
    for r in sorted(all_rows, key=lambda x: x["delta"])[:a.top]:
        print("  %-26s 手%-3d %-20s %-14s %-13s 投入%-6d 净%-7d 底池%-6d %s"
              % (r["match"], r["ui"], r["cat"], r["hole"], r["board"] or "-",
                 r["contrib"], r["delta"], r["pot"], r["note"]))

    out = BASE / "\u6d4b" / "_leak_audit.json"
    out.write_text(json.dumps(all_rows, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("\n明细已写 %s" % out)


if __name__ == "__main__":
    main()
