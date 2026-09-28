# -*- coding: utf-8 -*-
"""专项测试：规则2-A doom 的分界 = 「弃牌是否立死」+ 牌力分流。

用户规则（2026-09-28）：
  ① 「既然已经越线了还投入就应该 allin，因为如果输了也是全局的」
     → doom 成立 + to_call > 0（必须再投入才继续）= 弃牌立死 → **一律 allin**，
       无论牌多烂（拿整副筹码赌一把，严格优于确定性地输掉全局）。
  ② 「看牌质量，质量不好就直接 allin，质量好就再看看」
     → doom 成立 + to_call <= 0（能免费过牌）时按牌力分流：
         · 牌烂 → 直接 allin（过牌赢不下足够大的底池）
         · 牌好 → 再看看（交给常规策略；河牌除外——最后一街没得等，收网）

不再使用「越线幅度门控」（用户指出用错了变量：doom 成立即「输了就全局输」，
与越线 2.8% 还是 28% 无关）。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import strategy as S                                          # noqa: E402
from game_state import parse_request                          # noqa: E402
from opponent import OpponentModel                            # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print("[%s] %s %s" % (mark, name, detail))


def req(hist, cards, pub=(), my=20000, hand=43, twc=(0, 0)):
    return {"num_players": 2, "dealer_id": 0, "my_id": 0, "my_chips": my,
            "my_cards": list(cards), "public_cards": list(pub),
            "history": hist, "hand": hand, "max_hand": 70,
            "total_win_chips": list(twc), "total_win_games": [0, 0]}


# 牌号 = rank * 4 + suit（rank 2..14）
A_S, A_H, A_D = 48, 49, 50          # A♠ A♥ A♦
K_S, K_H = 44, 45                   # K♠ K♥
Q_S, Q_H = 40, 41                   # Q♠ Q♥
T_S, T_H = 40 - 0, 41               # T♠ T♥
SEVEN_S, TWO_S = 20, 0              # 7♠ 2♠

BL = [{"player_id": 0, "action": -4, "action_type": "blind", "amount": 50, "round": 0},
      {"player_id": 1, "action": -4, "action_type": "blind", "amount": 100, "round": 0}]
# 对手加注到 500 → 我需再投 450（弃牌立死）
H_RAISE = BL + [{"player_id": 1, "action": 500, "action_type": "raise",
                 "amount": 500, "round": 0}]
# 对手平跟 → to_call = 0（能免费过牌）
H_LIMP = BL + [{"player_id": 1, "action": 0, "action_type": "call",
                "amount": 100, "round": 0}]

# 深度 doom：lead = -9000 - 9000 = -18000，远越 2×追回线（手43/70 → line≈1950）
DOOM_TWC = (-9000, 9000)

print("=" * 78)
print("① doom + to_call>0（弃牌立死）→ 一律 allin（无论牌多烂）")
print("=" * 78)
for name, cards in [("Q5o 垃圾", (12, 1)), ("72o 最烂", (22, 0)),
                    ("AA 超强", (A_S, A_H)), ("23o 最烂", (3, 7))]:
    st = parse_request(req(H_RAISE, cards, my=19950, twc=DOOM_TWC))
    a = S.decide(st, OpponentModel(), None, debug=False)
    check("doom+投入:%s → allin" % name, a.get("act") == "allin",
          "to_call=%s act=%s" % (st.to_call, a))

print()
print("=" * 78)
print("② doom + to_call==0（免费过牌）→ 看牌质量")
print("=" * 78)
# 翻前：好牌 = 百分位 ≤ GAMBLE_GOOD_PCT（约 top20%）
for name, cards, good in [("72o 烂", (22, 0), False), ("Q5o 烂", (12, 1), False),
                          ("AA 好", (A_S, A_H), True), ("KK 好", (K_S, K_H), True)]:
    st = parse_request(req(H_LIMP, cards, my=19900, twc=DOOM_TWC))
    is_good = S._gamble_hand_good(st)
    a = S.decide(st, OpponentModel(), None, debug=False)
    want_allin = not good
    ok = (a.get("act") == "allin") if want_allin else (a.get("act") != "allin")
    check("doom免费:(%s牌) %s" % ("好" if good else "烂", name), ok,
          "判定good=%s act=%s" % (is_good, a))

# 翻后彩虹面 T♠ 8♥ 4♦（无听牌）：高牌 = 烂；顶对/三条 = 好
PUB_DRY = [40, 33, 18]
for name, cards, good in [("23o 高牌", (3, 7), False),
                          ("KTo 顶对", (T_H, K_S), True),
                          ("TT 三条", (T_H, 41 + 1), True)]:
    st = parse_request(req(H_LIMP, cards, pub=PUB_DRY, my=19900, twc=DOOM_TWC))
    a = S.decide(st, OpponentModel(), None, debug=False)
    ok = (a.get("act") == "allin") if not good else (a.get("act") != "allin")
    check("doom免费翻后:(%s牌) %s" % ("好" if good else "烂", name), ok,
          "cat=%s good=%s act=%s" % (S._effective_category(st),
                                     S._gamble_hand_good(st), a))

# 河牌例外：最后一街没得「再看」→ 好牌也要收网
H_RIVER = BL + [{"player_id": 1, "action": 0, "action_type": "call", "amount": 100, "round": 0}] + \
    [{"player_id": 1, "action": 0, "action_type": "check", "round": r} for r in (1, 2, 3)] + \
    [{"player_id": 0, "action": 0, "action_type": "check", "round": r} for r in (1, 2)]
st = parse_request(req(H_RIVER, (T_H, K_S), pub=PUB_DRY + [30, 22], my=19900, twc=DOOM_TWC))
a = S.decide(st, OpponentModel(), None, debug=False)
check("doom免费河牌:顶对 → 收网 allin", a.get("act") == "allin",
      "stage=%s to_call=%s act=%s" % (st.stage, st.to_call, a))

print()
print("=" * 78)
print("③ 保护性断言：非 doom 时不接管（均势照常）")
print("=" * 78)
st = parse_request(req(H_LIMP, (22, 0), my=19900, twc=(0, 0)))
a = S.decide(st, OpponentModel(), None, debug=False)
check("均势 72o 免费过牌 → 不是 allin", a.get("act") != "allin", str(a))
st = parse_request(req(H_LIMP, (A_S, A_H), my=19900, twc=(0, 0)))
a = S.decide(st, OpponentModel(), None, debug=False)
check("均势 AA → 正常开池(raise)", a.get("act") == "raise", str(a))

print()
if FAILED:
    print("FAILED %d: %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过 ✅")
