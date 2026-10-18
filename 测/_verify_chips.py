# -*- coding: utf-8 -*-
"""校验 load_botbattle 重建的 my_chips 是否等于平台真值。

独立口径：从日志动作直接算「我方在该动作**之前**的本手累计投入」，
真值 my_chips = 20000 − 累计投入。不看 my_chips 本身，避免自证。
"""
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "\u5185\u5bb9"))
import game_state as G          # noqa: E402
from botbattle_log import load_botbattle  # noqa: E402


def truth_before(obj, seat=0):
    """{(hand, 第几次我方动作): 该动作之前的本手累计投入}"""
    out = {}
    cur = None
    sb = None
    closed = 0          # 已结束各街的累计（含盲注）
    sc = [0, 0]
    cnt = 0
    for e in obj["replay"]["events"]:
        t = e.get("type")
        if t == "hand_start":
            cur = e["hand"]
            sb = e.get("sb")
            closed = 0
            sc = [0, 0]
            sc[sb] = 50
            sc[1 - sb] = 100
            cnt = 0
        elif t == "deal_board":
            closed += sc[seat]
            sc = [0, 0]
        elif t == "action":
            pl = int(e["player"])
            act = e["action"]
            amt = int(e.get("amount") or 0)
            if pl == seat:
                out[(cur, cnt)] = closed + sc[seat]
                cnt += 1
            if act == "fold":
                continue
            if act == "call":
                sc[pl] += amt
            elif act in ("raise", "allin"):
                sc[pl] = amt
    return out


def main():
    paths = []
    for pat in (str(Path.home() / "Downloads" / "botbattle*log.json"),
                str(BASE / "\u5185\u5bb9" / "\u8bb0\u5f55" / "*log.json")):
        paths += sorted(glob.glob(pat))
    tot = bad = 0
    shown = 0
    for p in paths:
        obj = json.loads(Path(p).read_bytes())
        m = obj.get("match") or {}
        da = str((m.get("bot_a") or {}).get("owner_display", ""))
        db = str((m.get("bot_b") or {}).get("owner_display", ""))
        if "j1331" in da and "j1331" in db:
            continue
        seat = 0 if "j1331" in da else 1
        tb = truth_before(obj, seat)
        idx = {}
        for req, meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            h = int(st.hand_num)
            k = idx.get(h, 0)
            idx[h] = k + 1
            exp = 20000 - tb.get((h, k), 0)
            tot += 1
            if st.my_chips != exp:
                bad += 1
                if shown < 10:
                    shown += 1
                    print("  MISMATCH %s 手%-3d %-6s my_chips=%-6d 真值%-6d (此前投入%d) act=%s"
                          % (Path(p).name[18:32], h + 1, st.stage, st.my_chips,
                             exp, tb.get((h, k), 0), meta.get("actual")))
    print("\n比对 %d 个请求，不一致 %d 个 (%.1f%%)"
          % (tot, bad, 100.0 * bad / max(1, tot)))


if __name__ == "__main__":
    main()
