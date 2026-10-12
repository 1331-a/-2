# -*- coding: utf-8 -*-
"""【2026-10-12】定位：面对下注、eq 余量 ≥0 却最终 fold 的点 —— 是哪一层改的？

逐层 monkey-patch 出口链，记录 before→after，只登记"改写"的层。
"""
import io, os, sys, json, glob, collections
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"

CHAIN = ["_lock_win_tail_guard", "_bet_cap_guard", "_aggressive_strong_bet",
         "_bluff_cap_guard", "_stability_guard", "_normalize", "_endgame_arbitrate",
         "_big_money_guard", "_cheap_call_guard", "_doom_call_upgrade"]


def norm(a):
    if not isinstance(a, dict) or "act" not in a:
        return None
    return "%s%s" % (a.get("act"), a.get("num") or "")


_ORDER = {"fold": 0, "check": 1, "call": 2, "raise": 3, "allin": 4}
_REC = []

orig = {n: getattr(S, n, None) for n in CHAIN}
orig["_face_bet"] = S._face_bet


def mk(name, fn):
    def w(*a, **kw):
        before = None
        for x in list(a) + list(kw.values()):
            if isinstance(x, dict) and "act" in x:
                before = x
                break
        out = fn(*a, **kw)
        b, af = norm(before), norm(out)
        if b is not None and b != af:
            _REC.append((name, b, af))
        return out
    w.__name__ = name
    return w


for n in CHAIN:
    if orig[n] is not None:
        setattr(S, n, mk(n, orig[n]))
S._face_bet = mk("_face_bet", orig["_face_bet"])

logs = sorted(glob.glob(os.path.join(BASE, "内容", "记录", "*log.json"))
              + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json"))


def seat_of(p):
    o = json.load(io.open(p, encoding="utf-8"))
    m0 = o.get("match") or {}
    for i, k in ((0, "bot_a"), (1, "bot_b")):
        if "j1331" in str((m0.get(k) or {}).get("owner_display", "")):
            return i
    return 0


cases = []
layer_count = collections.Counter()
for p in logs:
    seat = seat_of(p)
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    tag = os.path.basename(p)[17:25]
    for req, meta in load_botbattle(p, my_seat=seat):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._LAST_REQ_INFO = None
        _REC.clear()
        a = S.decide(st, m, ctx, debug=False)
        ri = S._LAST_REQ_INFO
        if not ri or int(st.to_call) <= 0:
            continue
        eq, eff_req, margin = map(float, ri)
        slack = eq - (eff_req + margin)
        if a.get("act") == "fold" and slack >= 0:
            cases.append({"tag": tag, "hand": req.get("hand"), "stage": st.stage,
                          "to_call": int(st.to_call), "pot": int(st.pot),
                          "eq": eq, "req": eff_req, "margin": margin, "slack": slack,
                          "trace": list(_REC)})
            for (nm, b, af) in _REC:
                layer_count[nm] += 1

print("「面对下注 & eq 够(slack>=0) & 最终 fold」= %d 个点" % len(cases))
print()
print("=== 改写发生的层（计数）===")
for k, v in layer_count.most_common():
    print("  %-26s %3d" % (k, v))
print()
print("=== 逐点改写链（前 30）===")
print("  %-9s %4s %-8s %7s %7s %8s  %s" % ("日志", "手", "街", "to_call", "eq", "slack", "改写链"))
for c in sorted(cases, key=lambda x: -x["slack"])[:30]:
    chain = " > ".join("%s:%s→%s" % t for t in c["trace"]) if c["trace"] else "（无层改写）"
    print("  %-9s %4d %-8s %7d %7.3f %8.3f  %s" % (
        c["tag"], c["hand"], c["stage"], c["to_call"], c["eq"], c["slack"], chain[:96]))

# 还原
for n in CHAIN:
    if orig[n] is not None:
        setattr(S, n, orig[n])
S._face_bet = orig["_face_bet"]
