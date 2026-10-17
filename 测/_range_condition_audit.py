# -*- coding: utf-8 -*-
"""Offline range audit; production modules and decision rules are never patched.

Run from any directory:
    python -X utf8 测/_range_condition_audit.py --output 测/_range_audit.json

Hidden cards are used only for retrospective labels, never range inputs.
Fixed-hole equity and recorded settle deltas do not identify counterfactual EV.
"""
import argparse
import collections
import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
from itertools import combinations
from pathlib import Path
from unittest.mock import patch


BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "\u5185\u5bb9"
sys.path.insert(0, str(CONTENT))

import equity as E
import game_state as G
import match_ctx as M
import opponent as O
import strategy as S
from botbattle_log import card_to_platform, load_botbattle
from evaluator import evaluate_7
from ranges import hand_percentile


TARGETS = {
    ("20261012170738-4895b988", 2, "flop"),
    ("20261012170738-4895b988", 30, "flop"),
    ("20261012170738-4895b988", 32, "flop"),
    ("20261012172157-11de872b", 32, "flop"),
    ("20261012172157-11de872b", 34, "flop"),
    ("20261012172157-11de872b", 40, "flop"),
    ("20261012172157-11de872b", 57, "turn"),
    ("20261012185239-b586268f", 28, "flop"),
    ("20261012185239-b586268f", 29, "turn"),
    ("20260924154120-ea9c99c4", 8, "turn"),
    ("20260924160802-bdd8f0c1", 12, "flop"),
}


def match_id(path):
    name = Path(path).name
    prefix, suffix = "botbattle-holdem-", "-log.json"
    if not name.startswith(prefix) or not name.endswith(suffix):
        raise ValueError("Unexpected log filename: " + name)
    return name[len(prefix):-len(suffix)]


def match_seat(obj):
    match = obj.get("match") or {}
    owners = [str((match.get(key) or {}).get("owner_display", ""))
              for key in ("bot_a", "bot_b")]
    hits = [i for i, value in enumerate(owners) if "j1331" in value]
    return hits[0] if len(hits) == 1 else None


def internal_cards(cards):
    values = [card_to_platform(card) for card in cards]
    if any(value is None for value in values):
        raise ValueError("Invalid card label: %r" % cards)
    result = [value + 8 for value in values]
    if len(set(result)) != len(result):
        raise ValueError("Duplicate cards")
    return result


def hole_map(obj, seat):
    out = {}
    for event in (obj.get("replay") or {}).get("events") or []:
        if event.get("type") != "deal_hole":
            continue
        holes = event["holes"]
        mine = internal_cards(holes[seat])
        opp = internal_cards(holes[1 - seat])
        if len(mine) != 2 or len(opp) != 2 or len(set(mine + opp)) != 4:
            raise ValueError("Invalid hole cards")
        out[int(event["hand"])] = (mine, opp)
    return out


def exact_vs_hole(hole, board, opp_hole):
    cards = list(hole) + list(board) + list(opp_hole)
    if len(hole) != 2 or len(opp_hole) != 2 or not 3 <= len(board) <= 5:
        raise ValueError("Only flop, turn and river labels are supported")
    if len(set(cards)) != len(cards) or any(c not in range(8, 60) for c in cards):
        raise ValueError("Invalid or overlapping cards")
    deck = [c for c in range(8, 60) if c not in set(cards)]
    wins = total = 0.0
    for runout in combinations(deck, 5 - len(board)):
        bd = list(board) + list(runout)
        mine = evaluate_7(list(hole) + bd)
        opp = evaluate_7(list(opp_hole) + bd)
        wins += 1.0 if mine > opp else 0.5 if mine == opp else 0.0
        total += 1.0
    return wins / total


def collect_postflop_rows(obj, seat):
    """One row per hand/street; not independent hands or observed raise nodes."""
    opp = 1 - seat
    holes = hole_map(obj, seat)
    hand, street = -1, "preflop"
    pre_actions = collections.defaultdict(list)
    post_actions = collections.defaultdict(list)
    for event in (obj.get("replay") or {}).get("events") or []:
        kind = event.get("type")
        if kind == "hand_start":
            hand, street = int(event["hand"]), "preflop"
        elif kind == "deal_board":
            street = str(event["street"])
        elif kind == "action" and int(event["player"]) == opp:
            action = str(event["action"]).lower()
            if street == "preflop":
                pre_actions[hand].append(action)
            else:
                post_actions[(hand, street)].append(action)
    rows = []
    for (hand, street), actions in post_actions.items():
        cards = holes[hand]
        rows.append({
            "hand": hand,
            "street": street,
            "pct": float(hand_percentile(cards[1])),
            "has_raise": any(x in ("raise", "bet", "allin") for x in actions),
            "pre_raise": any(x in ("raise", "bet", "allin")
                             for x in pre_actions.get(hand, ())),
        })
    return rows


def summary(rows):
    if not rows:
        return None
    values = sorted(x["pct"] for x in rows)
    return {
        "n": len(values), "mean": statistics.mean(values),
        "median": statistics.median(values),
        "pct_le_025": 100.0 * sum(x <= 0.25 for x in values) / len(values),
        "pct_le_050": 100.0 * sum(x <= 0.50 for x in values) / len(values),
    }


def condition_key(row):
    return "%s_%s" % (
        "pre_raise" if row["pre_raise"] else "no_pre_raise",
        "raise" if row["has_raise"] else "no_raise",
    )


def frozen_equity(state, range_pct, seed, iterations):
    if len(state.board) >= 4:
        return E.exact_equity(state.hole, state.board,
                              opp_range_pct=range_pct, deadline=None)
    return E.monte_carlo_equity(
        state.hole, state.board, iterations=iterations,
        opp_range_pct=range_pct, rng=random.Random(seed), deadline=None)


def turn_prefixes(state, range_pct):
    """Deterministic simulated deadlines, not real-time or production patches."""
    out = {}
    # _exact_turn checks the clock before rivers 0, 4, 8, ... .
    for count in (4, 8, 16, 32):
        calls = [0.0] * (count // 4) + [2.0]
        with patch.object(E.time, "time", side_effect=calls):
            value = E.exact_equity(
                state.hole, state.board, opp_range_pct=range_pct, deadline=1.0)
        out[str(count)] = value
    return out


def residual_summary(rows):
    if not rows:
        return None
    errors = [row["baseline_eq"] - row["fixed_hole_eq"] for row in rows]
    return {
        "decisions": len(rows),
        "hands": len({(r["match_id"], r["hand"]) for r in rows}),
        "matches": len({r["match_id"] for r in rows}),
        "mean_signed_error": statistics.mean(errors),
        "mae": statistics.mean(abs(x) for x in errors),
        "rmse": math.sqrt(statistics.mean(x * x for x in errors)),
        "note": "Descriptive fixed-hole residuals; no independent-sample CI.",
    }


def audit_decisions(path, obj, seat, iterations, targets_only=False):
    ident = match_id(path)
    holes = hole_map(obj, seat)
    deltas = {int(e["hand"]): int(e["deltas"][seat])
              for e in obj["replay"]["events"] if e.get("type") == "settle"}
    model = O.OpponentModel()
    ctx = M.MatchContext.from_dict(model.ctx_dict)
    rows = []
    for index, (request, meta) in enumerate(load_botbattle(path, my_seat=seat)):
        state = G.parse_request(request)
        # Fail loudly on malformed state; silently skipping corrupts model history.
        O.build_model_from_history(model, request, state)
        ctx.update(state)
        ctx.sync_baseline(state)
        key = (ident, int(state.hand_num), state.stage)
        if len(state.board) < 3 or state.to_call <= 0:
            continue
        if targets_only and key not in TARGETS:
            continue
        mine, theirs = holes[int(state.hand_num)]
        if mine != state.hole:
            raise ValueError("Replay/label hole-card mismatch: %r" % (key,))
        last = S._last_preflop_raiser(state)
        street_raises = S._opp_street_raises(state)
        range_pct = S._opp_range_pct(model, last == state.opp_id, street_raises)
        seed = S._decision_seed(state)
        baseline = frozen_equity(state, range_pct, seed, iterations)
        control = frozen_equity(state, range_pct, seed, iterations)
        narrow_pct = max(0.05, range_pct * 0.5)
        narrow = frozen_equity(state, narrow_pct, seed, iterations)
        row = {
            "match_id": ident, "request_index": index,
            "hand": int(state.hand_num), "ui_hand": int(state.hand_num) + 1,
            "stage": state.stage, "selected_target": key in TARGETS,
            "hole": mine, "board": list(state.board),
            "opponent_hole_label_only": theirs,
            "pot": int(state.pot), "to_call": int(state.to_call),
            "required": state.to_call / (state.pot + state.to_call),
            "lead": state.total_win_chips[seat] - state.total_win_chips[1-seat],
            "opponent_allin": bool(state.any_allin),
            "range_pct": range_pct, "narrow_range_pct": narrow_pct,
            "baseline_eq": baseline, "control_eq": control, "narrow_eq": narrow,
            "fixed_hole_eq": exact_vs_hole(state.hole, state.board, theirs),
            "seen": int(model.hands_seen), "vpip": float(model.eff_vpip()),
            "bet_freq": float(model.eff_bet_freq()), "street_raises": street_raises,
            "opponent_preflop_raiser": last == state.opp_id,
            "settle_delta_observed_only": deltas.get(int(state.hand_num)),
            "production_equity_reached": "not measured; offline estimator only",
        }
        if key in TARGETS and state.stage == "turn":
            row["fixed_order_turn_prefixes"] = turn_prefixes(state, range_pct)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=4000)
    parser.add_argument("--targets-only", action="store_true")
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")
    paths = args.logs or sorted(
        set((CONTENT / "\u8bb0\u5f55").glob("*log.json")) |
        set((Path.home() / "Downloads").glob("botbattle*log.json")))
    hashes = {}
    rows, post_rows, files, skipped = [], [], [], []
    for path in paths:
        raw = path.read_bytes()
        ident = match_id(path)
        digest = hashlib.sha256(raw).hexdigest()
        if ident in hashes:
            if hashes[ident] != digest:
                raise ValueError("Conflicting copies of " + ident)
            continue
        hashes[ident] = digest
        obj = json.loads(raw)
        seat = match_seat(obj)
        if seat is None:
            skipped.append({"file": str(path), "reason": "Ambiguous/unknown seat"})
            continue
        print("Auditing %s seat=%d" % (ident, seat), flush=True)
        files.append({"match_id": ident, "path": str(path), "sha256": digest,
                      "seat": seat, "opponent": obj["match"].get(
                          "bot_b" if seat == 0 else "bot_a")})
        post_rows.extend(collect_postflop_rows(obj, seat))
        rows.extend(audit_decisions(path, obj, seat, args.iterations,
                                    args.targets_only))
    controls = sum(r["baseline_eq"] != r["control_eq"] for r in rows)
    targets = [r for r in rows if r["selected_target"]]
    target_keys = {(r["match_id"], r["hand"], r["stage"]) for r in targets}
    arm_stats = {}
    for name in ("all", "targets", "non_targets"):
        group = rows if name == "all" else [
            r for r in rows if r["selected_target"] == (name == "targets")]
        arm_stats[name] = residual_summary(group)
    result = {
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BASE, text=True).strip(),
        "module_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (CONTENT / "strategy.py", CONTENT / "equity.py",
                                    CONTENT / "opponent.py", CONTENT / "botbattle_log.py")},
        "scope": "Offline estimator; cold-start reconstructed history; not platform A/B.",
        "iterations": args.iterations, "deadline": None,
        "files": files, "skipped": skipped,
        "control_mismatches": controls, "summaries": arm_stats,
        "target_expected": len(TARGETS), "target_observed": len(target_keys),
        "target_missing": sorted(TARGETS - target_keys),
        "postflop_hand_street_groups": {
            key: summary([r for r in post_rows if condition_key(r) == key])
            for key in sorted({condition_key(r) for r in post_rows})},
        "rows": rows,
    }
    if args.output:
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "control_mismatches", "target_expected", "target_observed", "summaries")},
        indent=2))
    if controls:
        raise SystemExit("Repeated baseline differs from control")


if __name__ == "__main__":
    main()
