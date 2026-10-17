# -*- coding: utf-8 -*-
"""Controlled offline response replay; never a counterfactual profit estimator.

Three independent processes: baseline, half-range diagnostic, baseline control.
Full request history and bot data/globaldata are replayed, including preflop.
Timing cutoffs are removed from equity calls; iteration caps are diagnostic.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import _range_condition_audit as audit


def worker(paths, multiplier, iterations):
    import bot as B
    import equity as E
    import game_state as G
    import strategy as S

    os.environ["WB_POKER_DEBUG"] = "0"
    os.environ.pop("WB_NO_SEED", None)
    S.MC_ITERATIONS = iterations
    S.ALLIN_MC = iterations
    original_range = S._opp_range_pct
    current = [None]
    counts = collections.Counter()

    def diagnostic_range(model, raised, street_raises=0):
        value = original_range(model, raised, street_raises)
        state = current[0]
        if state.stage != "preflop" and street_raises > 0:
            counts["eligible_range_calls"] += 1
            return max(.05, min(.95, value * multiplier))
        return value

    def no_deadline_best(*args, **kwargs):
        counts["equity_best_calls"] += 1
        kwargs["deadline"] = None
        return E.equity_best(*args, **kwargs)

    def no_deadline_mc(*args, **kwargs):
        counts["mc_calls"] += 1
        kwargs["deadline"] = None
        return E.monte_carlo_equity(*args, **kwargs)

    S._opp_range_pct = diagnostic_range
    S.equity_best = no_deadline_best
    S.monte_carlo_equity = no_deadline_mc
    rows = []
    for path in paths:
        obj = json.loads(path.read_bytes())
        seat = audit.match_seat(obj)
        if seat is None:
            continue
        ident = audit.match_id(path)
        deltas = {int(e["hand"]): int(e["deltas"][seat])
                  for e in obj["replay"]["events"] if e.get("type") == "settle"}
        data = ""
        for index, (request, meta) in enumerate(
                audit.load_botbattle(path, my_seat=seat)):
            state = G.parse_request(request)
            current[0] = state
            before = dict(counts)
            response, data, json_mode = B._handle_line({
                "requests": [request], "data": data, "globaldata": data})
            if not json_mode or not isinstance(response, int) or not data:
                raise ValueError("Replay failed at %s request %d" % (ident, index))
            rows.append({
                "match_id": ident, "request_index": index,
                "hand": int(state.hand_num), "ui_hand": int(state.hand_num) + 1,
                "stage": state.stage, "response": response,
                "opponent_allin": bool(state.any_allin),
                "range_calls": counts["eligible_range_calls"] -
                               before.get("eligible_range_calls", 0),
                "settle_delta_observed_only": deltas.get(int(state.hand_num)),
            })
    return {"multiplier": multiplier, "iterations": iterations,
            "counts": dict(counts), "rows": rows}


def key(row):
    return row["match_id"], row["request_index"]


def compare(baseline, variant):
    base = {key(row): row for row in baseline}
    other = {key(row): row for row in variant}
    if len(base) != len(baseline) or len(other) != len(variant):
        raise ValueError("Duplicate decision keys")
    if set(base) != set(other):
        raise ValueError("Mismatched decision keys")
    changed = []
    hands = {}
    migrations = collections.Counter()
    for ident, row in base.items():
        next_row = other[ident]
        if row["response"] == next_row["response"]:
            continue
        changed.append({"baseline": row, "variant": next_row})
        hand_key = (row["match_id"], row["hand"])
        hands[hand_key] = row["settle_delta_observed_only"]
        migrations[(row["response"], next_row["response"])] += 1
    return {
        "decisions": len(base), "changed_decisions": len(changed),
        "changed_hands": len(hands),
        "observed_changed_hand_deltas_not_improvement": sum(
            value for value in hands.values() if value is not None),
        "response_migrations": [
            {"before": pair[0], "after": pair[1], "n": n}
            for pair, n in sorted(migrations.items())],
        "changes": changed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path)
    parser.add_argument("--iterations", type=int, default=1500)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=float)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")
    paths = args.logs or sorted(
        set((audit.CONTENT / "\u8bb0\u5f55").glob("*log.json")) |
        set((Path.home() / "Downloads").glob("botbattle*log.json")))
    # Reject conflicting copies, then keep one source per full match id.
    unique = {}
    for path in paths:
        obj = json.loads(path.read_bytes())
        if audit.match_seat(obj) is None:
            continue
        ident = audit.match_id(path)
        if ident in unique and unique[ident].read_bytes() != path.read_bytes():
            raise ValueError("Conflicting log copies: " + ident)
        unique[ident] = path.resolve()
    paths = list(unique.values())
    if args.worker is not None:
        print(json.dumps(worker(paths, args.worker, args.iterations)))
        return
    if not paths:
        raise SystemExit("No unambiguous logs")
    arms = {}
    for name, multiplier in (("baseline", 1.0), ("half_range", .5), ("control", 1.0)):
        print("Running %s" % name, flush=True)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("WB_", "DBG_"))}
        command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                   "--worker", str(multiplier), "--iterations", str(args.iterations)]
        proc = subprocess.run(
            command + [str(path) for path in paths], env=env,
            text=True, encoding="utf-8", capture_output=True, timeout=1200,
            check=True, cwd=audit.CONTENT)
        arms[name] = json.loads(proc.stdout)
    changed = compare(arms["baseline"]["rows"], arms["half_range"]["rows"])
    control = compare(arms["baseline"]["rows"], arms["control"]["rows"])
    result = {
        "scope": "Offline full bot response replay, not platform or causal EV.",
        "equity_deadline": None, "iterations": args.iterations,
        "sources": [{"match_id": audit.match_id(p),
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in paths],
        "arms": arms, "half_range_vs_baseline": changed,
        "control_vs_baseline": control,
    }
    if args.output:
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "half_range_vs_baseline": {k: v for k, v in changed.items() if k != "changes"},
        "control_vs_baseline": {k: v for k, v in control.items() if k != "changes"},
    }, indent=2))
    if control["changed_decisions"]:
        raise SystemExit("Nonzero baseline control differences")


if __name__ == "__main__":
    main()
