"""Isolated full-response replay for the paired-board/draw candidates.

Fixed histories are not counterfactual games. Observed deltas are not uplift.
Each arm starts a new process and persists the full bot data between requests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import _range_condition_audit as audit
from _range_replay_ab import compare


def worker(paths, arm, iterations):
    import bot as B
    import equity as E
    import game_state as G
    import strategy as S

    S.BOTTOM_POCKET_RISK_ON = arm == "bottom"
    S.MC_ITERATIONS = iterations
    S.ALLIN_MC = iterations
    counts = {"best": 0, "mc": 0, "face": 0, "bottom_risk": 0}
    original_face = S._face_bet

    def best(*args, **kwargs):
        counts["best"] += 1
        kwargs["deadline"] = None
        return E.equity_best(*args, **kwargs)

    def mc(*args, **kwargs):
        counts["mc"] += 1
        kwargs["deadline"] = None
        return E.monte_carlo_equity(*args, **kwargs)

    def face(*args, **kwargs):
        counts["face"] += 1
        return original_face(*args, **kwargs)

    S.equity_best = best
    S.monte_carlo_equity = mc
    S._face_bet = face
    rows = []
    for path in paths:
        obj = json.loads(path.read_bytes())
        seat = audit.match_seat(obj)
        ident = audit.match_id(path)
        holes = audit.hole_map(obj, seat)
        deltas = {int(e["hand"]): int(e["deltas"][seat])
                  for e in obj["replay"]["events"] if e.get("type") == "settle"}
        data = ""
        for index, (request, _) in enumerate(
                audit.load_botbattle(path, my_seat=seat)):
            st = G.parse_request(request)
            before = dict(counts)
            response, data, mode = B._handle_line({
                "requests": [request], "data": data, "globaldata": data})
            if not mode or not isinstance(response, int) or not data:
                raise ValueError("Invalid bot response")
            rows.append({
                "match_id": ident, "request_index": index,
                "hand": int(st.hand_num), "stage": st.stage,
                "response": response, "pot": st.pot, "to_call": st.to_call,
                "hole": st.hole, "board": st.board,
                "opponent_hole_label_only": holes[int(st.hand_num)][1],
                "opponent_allin": bool(st.any_allin),
                "face_reached": counts["face"] > before["face"],
                "risk": S.should_avoid_risk(st),
                "settle_delta_observed_only": deltas.get(int(st.hand_num)),
            })
    return {"arm": arm, "counts": counts, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1500)
    parser.add_argument("--worker", choices=("baseline", "bottom", "draw", "both"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("iterations must be positive")
    paths = sorted(
        set((audit.CONTENT / "\u8bb0\u5f55").glob("*log.json")) |
        set((Path.home() / "Downloads").glob("botbattle*log.json")))
    unique = {}
    for p in paths:
        if audit.match_seat(json.loads(p.read_bytes())) is None:
            continue
        ident = audit.match_id(p)
        if ident in unique and unique[ident].read_bytes() != p.read_bytes():
            raise ValueError("Conflicting log copies: " + ident)
        unique[ident] = p
    paths = list(unique.values())
    if args.worker:
        print(json.dumps(worker(paths, args.worker, args.iterations)))
        return
    if not paths:
        raise ValueError("No unambiguous logs")
    arms = {}
    for name, arm in (("baseline", "baseline"), ("bottom", "bottom"),
                      ("control", "baseline")):
        print("Running " + name, flush=True)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("WB_", "DBG_"))}
        env["WB_POKER_DEBUG"] = "0"
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
             "--worker", arm, "--iterations", str(args.iterations)],
            cwd=audit.CONTENT, env=env, text=True, encoding="utf-8",
            capture_output=True, timeout=2400)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-5000:])
        arms[name] = json.loads(proc.stdout)
    comparisons = {}
    for name in ("bottom", "control"):
        diff = compare(arms["baseline"]["rows"], arms[name]["rows"])
        for change in diff["changes"]:
            row = change["baseline"]
            if len(row["board"]) >= 3:
                change["fixed_hole_eq_label_only"] = audit.exact_vs_hole(
                    row["hole"], row["board"], row["opponent_hole_label_only"])
        comparisons[name] = diff
    result = {
        "scope": "Cold-start fixed-history replay; NOT causal EV or platform parity",
        "equity_deadline": None, "iterations": args.iterations,
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=audit.BASE, text=True).strip(),
        "modules": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (audit.CONTENT / "strategy.py",
                              audit.CONTENT / "equity.py")},
        "sources": {audit.match_id(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in paths},
        "arms": arms, "comparisons": comparisons,
    }
    if args.output:
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8")
    print(json.dumps({name: {k: v for k, v in diff.items() if k != "changes"}
                      for name, diff in comparisons.items()}, indent=2))
    if comparisons["control"]["changed_decisions"]:
        raise SystemExit("Nonzero control noise")


if __name__ == "__main__":
    main()
