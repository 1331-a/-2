# -*- coding: utf-8 -*-
"""P0-2（2026-10-18）：超对在大注 / 4 倍突袭下的硬弃豁免 —— 按牌面危险度分层。

背景：10-18 场1 手56，QQ 在 `3 3 4` 面对 27o 全押被硬弃（需要 0.45 / 真实 0.96）。
真凶是「4 倍突袭 + 牌型 < 三条 → 硬弃」把「超对」当弱牌。但「超对永不弃牌」是错的：
公面成三条 / 4 张同花 / 3 连时必须继续硬弃。

本测试只断言分层判据本身（`_overpair_bigbet_pass`），不依赖 MC，
避免把「门槛是否够」和「该不该豁免」两件事混在一起。
"""
import os
import strategy as S
from game_state import parse_request

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("[PASS] %s" % name)
    else:
        print("[FAIL] %s %s" % (name, detail))
        FAILS.append(name)


def req(**kw):
    base = {"num_players": 2, "dealer_id": 0, "my_id": 0,
            "my_chips": 15000, "my_cards": [48, 50], "public_cards": [],
            "history": [], "hand": 20, "max_hand": 70,
            "total_win_chips": [0, 0], "total_win_games": [0, 0]}
    base.update(kw)
    return base


def st(my_cards, public_cards, **kw):
    return parse_request(req(my_cards=my_cards, public_cards=public_cards, **kw))


# 平台编码：n = rank*4 + suit（rank 0=2 … 12=A）
# AA=[48,50]  KK=[44,45]  KQ=[44,41]  QQ=[40,42]
# 公面干燥 7 6 2 = [22, 18, 1]（rank 5/4/0，无 Q/K、无 3 连、无 3 同花）
# 公面 K 7 3 = [46, 22, 5]（有 K ⇒ 超对的中危"高张面"）
# 公面 3 张同花 K 7 3 (全 s2) = [46, 22, 6]
# 公面 4 张同花 K 7 3 2 (全 s2) = [46, 22, 6, 2]
# 公面 3 连 K Q J = [46, 41, 36]
# 公面三条 KKK = [46, 47, 45]

# ---------- 1. 干燥面：超对豁免 ----------
s = st([48, 50], [22, 18, 1])
ok, tier = S._overpair_bigbet_pass(s, None)
check("干燥面(762):AA 超对 → 豁免，档位 clean", ok and tier == "clean", "%s/%s" % (ok, tier))
check("干燥面(762):_overpair_rank = A(12)", S._overpair_rank(s) == 12, str(S._overpair_rank(s)))

# ---------- 2. 公面成对（低于我方口袋对）：仍算超对 ----------
# `3 3 4` = [6, 7, 10]（3 两张 + 4）
s = st([40, 42], [6, 7, 10])
check("公面对(334):QQ 仍算超对（两对 QQ33）", S._overpair_rank(s) == 10, str(S._overpair_rank(s)))
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面对(334):QQ → 豁免，clean", ok and tier == "clean", "%s/%s" % (ok, tier))

# ---------- 3. 公面三条：不豁免 ----------
s = st([40, 42], [46, 47, 45])
check("公面三条(KKK):QQ → 不豁免", S._overpair_rank(s) is None, str(S._overpair_rank(s)))

# ---------- 4. 公面 3 连：不豁免 ----------
s = st([48, 50], [46, 41, 36])
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面3连(KQJ):AA → 不豁免", not ok and tier == "straight_board", "%s/%s" % (ok, tier))

# ---------- 5. 公面 4 张同花：不豁免 ----------
s = st([48, 50], [46, 22, 6, 2])
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面4同花:AA → 不豁免", not ok and tier == "flush_made", "%s/%s" % (ok, tier))

# ---------- 6. 公面 3 张同花：豁免但升为中危 ----------
s = st([48, 50], [46, 22, 6])
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面3同花:AA → 豁免，档位 wet", ok and tier == "wet", "%s/%s" % (ok, tier))

# ---------- 7. 公面出现 K（高张面）：中危 ----------
# ★ 公面的 A 不可能与超对共存（超对必须高于公面所有牌），故只测 K/Q 两档。
s = st([48, 50], [46, 22, 5])          # AA on K 7 3
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面有K:AA 超对 → 豁免，档位 wet", ok and tier == "wet", "%s/%s" % (ok, tier))
s = st([48, 50], [41, 22, 5])          # AA on Q 7 3
ok, tier = S._overpair_bigbet_pass(s, None)
check("公面有Q:AA 超对 → 豁免，档位 wet", ok and tier == "wet", "%s/%s" % (ok, tier))

# ---------- 8. 非超对（顶对 / 两张非对子）：不豁免 ----------
s = st([44, 41], [22, 18, 1])
ok, tier = S._overpair_bigbet_pass(s, None)
check("顶对(KQ on 762) → 不豁免", not ok and tier == "not_overpair", "%s/%s" % (ok, tier))
s = st([40, 42], [46, 22, 5])
check("低口袋对(QQ on K73, 被盖过) → 不豁免", S._overpair_rank(s) is None, str(S._overpair_rank(s)))

# ---------- 9. 翻前（公面 < 3 张）：不豁免 ----------
s = st([48, 50], [])
ok, tier = S._overpair_bigbet_pass(s, None)
check("翻前 → 不豁免", not ok and tier == "not_overpair", "%s/%s" % (ok, tier))

# ---------- 10. 回退开关 ----------
_saved = S.OVERP_VS_BIGBET_ON
try:
    S.OVERP_VS_BIGBET_ON = False
    s = st([48, 50], [22, 18, 1])
    ok, tier = S._overpair_bigbet_pass(s, None)
    check("回退开关关闭 → 一律不豁免", (not ok) and tier == "off", "%s/%s" % (ok, tier))
finally:
    S.OVERP_VS_BIGBET_ON = _saved

# ---------- 11. 对手极度不弃牌（样本足）→ 不豁免 ----------
class _StrongOpp(object):
    faces_bet = S.OVERP_OPP_MIN_SAMPLES

    def eff_fold_to_bet(self):
        return 0.10


class _WeakOpp(object):
    faces_bet = S.OVERP_OPP_MIN_SAMPLES

    def eff_fold_to_bet(self):
        return 0.70


s = st([48, 50], [22, 18, 1])
ok, tier = S._overpair_bigbet_pass(s, _StrongOpp())
check("对手弃牌率 0.10(<0.25) → 不豁免", (not ok) and tier == "opp_strong", "%s/%s" % (ok, tier))
ok, tier = S._overpair_bigbet_pass(s, _WeakOpp())
check("对手弃牌率 0.70 → 豁免", ok and tier == "clean", "%s/%s" % (ok, tier))

# ---------- 12. 环境变量回退 ----------
print()
if FAILS:
    print("有 %d 项失败 ❌" % len(FAILS))
    raise SystemExit(1)
print("全部通过 ✅")
