# -*- coding: utf-8 -*-
"""P1 诊断：翻牌无人下注（to_call==0）时，为什么过牌而不是小注偷池。

逐点记录：是否翻前加注者、对手本手是否表现过强度、公面危险度、
`_small_bet_futile`（规则19）、`_check_bet_weight`（规则12 权重）、
以及最终动作 —— 把「规则拦下」和「随机过牌」分开。

用法: python 测/_cbet_audit.py
"""
import glob
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "内容"))
import strategy as S                      # noqa: E402
import game_state as G                    # noqa: E402
import opponent as O                      # noqa: E402
import match_ctx as M                     # noqa: E402
from botbattle_log import load_botbattle  # noqa: E402

PATHS = sorted(set(
    glob.glob(str(BASE / "内容" / "记录" / "*log.json"))
    + glob.glob(str(Path.home() / "Downloads" / "botbattle*log.json"))))


def preflop_raiser(state):
    """翻前最后一个主动加注者是不是我方（只看 history 的 round 0）。"""
    last = None
    for h in (state.request.get("history") or []):
        if int(h.get("round", -1)) != 0:
            continue
        t = str(h.get("action_type", ""))
        if t in ("raise", "allin"):
            last = int(h.get("player_id", -1))
    return last == state.my_id


def opp_showed_strength(state):
    """对手本手是否有过 raise/allin（翻前或翻后）。"""
    for h in (state.request.get("history") or []):
        if int(h.get("player_id", -1)) == state.opp_id and \
                str(h.get("action_type", "")) in ("raise", "allin"):
            return True
    return False


def board_dry(state):
    """公面是否"干燥"：无 3 张同花、无 3 连、无高张(A/K)。"""
    br = [(c - 8) >> 2 for c in state.board]
    if not br:
        return False
    suits = {}
    for c in state.board:
        suits[c & 3] = suits.get(c & 3, 0) + 1
    if max(suits.values()) >= 3:
        return False
    rs = sorted(set(br))
    run = best = 1
    for i in range(1, len(rs)):
        run = run + 1 if rs[i] == rs[i - 1] + 1 else 1
        best = max(best, run)
    if best >= 3:
        return False
    if max(br) >= 11:            # 公面有 A/K
        return False
    return True


rows = []
for p in PATHS:
    obj = json.loads(Path(p).read_bytes())
    m0 = obj.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display", ""))
    db = str((m0.get("bot_b") or {}).get("owner_display", ""))
    if "j1331" in da and "j1331" in db:
        continue
    seat = 0 if "j1331" in da else 1
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    ident = Path(p).name[18:32]
    try:
        for req, meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            try:
                O.build_model_from_history(model, req, st)
            except Exception:
                pass
            try:
                ctx.update(st)
            except Exception:
                pass
            S._DECISION_STARTED_WALL = time.time()
            a = S.decide(st, model, ctx, debug=False)
            if st.stage != "flop" or int(st.to_call) != 0:
                continue
            rows.append(dict(
                m=ident, h=int(st.hand_num) + 1, pot=int(st.pot),
                act=a.get("act"), num=a.get("num"),
                pfr=preflop_raiser(st), opp_str=opp_showed_strength(st),
                dry=board_dry(st),
                futile=S._small_bet_futile(st, model),
                w=round(float(S._check_bet_weight(st, model)), 2),
                cat=S._effective_category(st),
                opp_chk=S._opp_checked_this_round(st),
                real=str(meta.get("actual")),
            ))
    except Exception as e:
        print("  skip %s %r" % (ident, e))

print("翻牌无人下注的决策点：%d" % len(rows))
print()
nchk = sum(1 for r in rows if r["act"] == "check")
nbet = sum(1 for r in rows if r["act"] in ("raise", "allin"))
print("过牌 %d / 下注 %d" % (nchk, nbet))
print()
print("按「是否翻前加注者 × 面是否干燥」拆：")
for k in [(True, True), (True, False), (False, True), (False, False)]:
    sub = [r for r in rows if r["pfr"] == k[0] and r["dry"] == k[1]]
    if not sub:
        continue
    c = sum(1 for r in sub if r["act"] == "check")
    print("  PFR=%-5s dry=%-5s n=%-3d 过牌%-3d 下注%-3d" % (k[0], k[1], len(sub), c, len(sub) - c))
print()
print("过牌点归因（规则19 拦下 / 权重 <1 / 其他）：")
fut = [r for r in rows if r["act"] == "check" and r["futile"]]
low = [r for r in rows if r["act"] == "check" and not r["futile"] and r["w"] < 1.0]
oth = [r for r in rows if r["act"] == "check" and not r["futile"] and r["w"] >= 1.0]
print("  规则19 _small_bet_futile 拦下 : %d" % len(fut))
print("  权重 <1（概率性过牌/降频）    : %d" % len(low))
print("  权重=1 仍过牌（其他分支接管） : %d" % len(oth))
print()
print("--- 权重=1 仍过牌的明细（这些才是「该下注却过牌」的候选）---")
for r in oth[:20]:
    print("  %-14s 手%-3d pot%-5d PFR=%-5s 干=%-5s opp_str=%-5s cat=%-2d 对手已过牌=%-5s → %s"
          % (r["m"], r["h"], r["pot"], r["pfr"], r["dry"], r["opp_str"],
             r["cat"], r["opp_chk"], r["act"]))
print()
print("--- 权重 <1 的明细 ---")
for r in low[:20]:
    print("  %-14s 手%-3d pot%-5d w=%-4s PFR=%-5s 干=%-5s cat=%-2d → %s"
          % (r["m"], r["h"], r["pot"], r["w"], r["pfr"], r["dry"], r["cat"], r["act"]))
