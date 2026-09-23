#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import sys
from pathlib import Path

from common import (
    EXPERIMENT_ROOT,
    atomic_write_json,
    atomic_write_text,
    load_config,
    load_pairs_manifest,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)

DIRECTED_METHODS = {"AAT", "Gaussian", "GPT_P2", "Position"}


def parse_method(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("method must be NAME=PATH")
    name, path = value.split("=", 1)
    return name, Path(path).resolve()


def digest_rank(seed: int, *parts: str) -> str:
    return hashlib.sha256(":".join((str(seed), *parts)).encode()).hexdigest()


def copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", type=parse_method, required=True)
    parser.add_argument("--output-dir", type=Path, default=EXPERIMENT_ROOT / "human_study")
    args = parser.parse_args()
    config = load_config()
    required_methods = config["human_study"]["methods"]
    methods = dict(args.method)
    if set(methods) != set(required_methods):
        raise ValueError(f"Expected methods {required_methods}, got {sorted(methods)}")
    pairs = {pair["k"]: pair for pair in load_pairs_manifest(config)["pairs"]}
    subsets_path = resolve_experiment_path(config["data"]["subsets"])
    subsets = json.loads(subsets_path.read_text(encoding="utf-8"))
    selected = subsets["subsets"]["human_42"]
    if len(selected) != int(config["human_study"]["endpoint_pairs"]):
        raise RuntimeError("Human-study subset size differs from config")
    data_root = resolve_experiment_path(config["data"]["root"])
    output_dir = args.output_dir.resolve()
    assets = output_dir / "assets"
    seed = int(config["human_study"]["seed"])

    candidate_paths: dict[tuple[str, str], Path] = {}
    for method, directory in methods.items():
        for item in selected:
            path = directory / f"{item['k']}_mid.png"
            if not path.is_file():
                raise FileNotFoundError(f"Missing {method} candidate for k={item['k']}: {path}")
            candidate_paths[(method, item["k"])] = path

    private_trials = []
    public_trials = []
    for item in selected:
        k = item["k"]
        pair = pairs[k]
        endpoint_a = data_root / pair["path_A"]
        endpoint_b = data_root / pair["path_B"]
        endpoint_a_name = f"endpoint_{k}_a{endpoint_a.suffix.lower()}"
        endpoint_b_name = f"endpoint_{k}_b{endpoint_b.suffix.lower()}"
        copy_atomic(endpoint_a, assets / endpoint_a_name)
        copy_atomic(endpoint_b, assets / endpoint_b_name)
        for method_a, method_b in itertools.combinations(required_methods, 2):
            trial_key = digest_rank(seed, "trial", k, method_a, method_b)
            left, right = (
                (method_a, method_b) if int(trial_key[0], 16) % 2 == 0 else (method_b, method_a)
            )
            directed = left in DIRECTED_METHODS or right in DIRECTED_METHODS
            endpoint_order = "AB" if directed or int(trial_key[1], 16) % 2 == 0 else "BA"
            blind_left = f"cand_{trial_key[:16]}_l.png"
            blind_right = f"cand_{trial_key[:16]}_r.png"
            copy_atomic(candidate_paths[(left, k)], assets / blind_left)
            copy_atomic(candidate_paths[(right, k)], assets / blind_right)
            hashes = {
                "endpoint_A": sha256_file(endpoint_a),
                "endpoint_B": sha256_file(endpoint_b),
                "candidate_left": sha256_file(candidate_paths[(left, k)]),
                "candidate_right": sha256_file(candidate_paths[(right, k)]),
            }
            public = {
                "trial_id": trial_key[:24],
                "k_blind": digest_rank(seed, "pair", k)[:12],
                "regime": item["regime"],
                "directed": directed,
                "endpoint_order": endpoint_order,
                "endpoint_A": f"assets/{endpoint_a_name}",
                "endpoint_B": f"assets/{endpoint_b_name}",
                "candidate_left": f"assets/{blind_left}",
                "candidate_right": f"assets/{blind_right}",
                "question_ids": ["pair_midpoint", "self_consistent_texture"],
                "hashes": hashes,
            }
            private = {**public, "k": k, "method_left": left, "method_right": right}
            public_trials.append(public)
            private_trials.append(private)

    public_trials.sort(key=lambda row: digest_rank(seed, "order", row["trial_id"]))
    private_by_id = {row["trial_id"]: row for row in private_trials}
    private_trials = [private_by_id[row["trial_id"]] for row in public_trials]
    public_path = output_dir / "trial_manifest.public.jsonl"
    private_path = output_dir / "trial_manifest.private.jsonl"
    atomic_write_text(
        public_path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in public_trials)
    )
    atomic_write_text(
        private_path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in private_trials)
    )

    participant_count = int(config["human_study"]["target_participants"])
    per_participant = int(config["human_study"]["scored_trials_per_participant"])
    primary_per_participant = int(config["human_study"]["primary_trials_per_participant"])
    primary_pair = frozenset(("AAT", "GPT_P2"))
    private_lookup = {row["trial_id"]: row for row in private_trials}
    primary_trials = [
        row
        for row in public_trials
        if frozenset(
            (
                private_lookup[row["trial_id"]]["method_left"],
                private_lookup[row["trial_id"]]["method_right"],
            )
        )
        == primary_pair
    ]
    secondary_trials = [row for row in public_trials if row not in primary_trials]
    exposures = {row["trial_id"]: 0 for row in public_trials}
    assignments = []
    for participant in range(participant_count):
        chosen = []
        seen_pairs = set()
        for pool, quota in (
            (primary_trials, primary_per_participant),
            (secondary_trials, per_participant - primary_per_participant),
        ):
            regime_targets = {regime: quota // 3 for regime in ("ordinary", "periodic", "semantic")}
            for regime in list(regime_targets)[: quota % 3]:
                regime_targets[regime] += 1
            for regime, target in regime_targets.items():
                ordered = sorted(
                    (row for row in pool if row["regime"] == regime),
                    key=lambda row: (
                        exposures[row["trial_id"]],
                        digest_rank(seed, "participant", str(participant), row["trial_id"]),
                    ),
                )
                taken = 0
                for row in ordered:
                    if row["k_blind"] in seen_pairs:
                        continue
                    chosen.append(row["trial_id"])
                    seen_pairs.add(row["k_blind"])
                    exposures[row["trial_id"]] += 1
                    taken += 1
                    if taken == target:
                        break
                if taken != target:
                    raise RuntimeError("Could not build balanced participant assignment")
        assignments.append({"participant_slot": participant + 1, "trial_ids": chosen})
    atomic_write_json(output_dir / "participant_assignments.json", assignments)

    html = """<!doctype html>
<meta charset="utf-8"><title>Blinded midpoint study — local preview only</title>
<style>body{font:16px sans-serif;max-width:1200px;margin:auto} .row{display:flex;gap:12px}
img{width:46%;height:auto;object-fit:contain;background:#eee}.label{text-align:center;font-weight:bold}
button{margin:8px;padding:10px}.notice{color:#900;font-weight:bold}</style>
<p class="notice">LOCAL PREVIEW ONLY — not deployed and not collecting responses.</p>
<div id="root"></div><script>
fetch('trial_manifest.public.jsonl').then(r=>r.text()).then(text=>{
 const rows=text.trim().split(/\n/).map(JSON.parse);
 let i=0; const root=document.querySelector('#root');
 function show(){const t=rows[i];
 const e=t.endpoint_order==='AB'?[t.endpoint_A,t.endpoint_B]:[t.endpoint_B,t.endpoint_A];
 root.innerHTML=`<p>Trial ${i+1}/${rows.length} — ${t.trial_id}</p><h2>Endpoints</h2>
 <div class=row><img src="${e[0]}"><img src="${e[1]}"></div><h2>Candidates</h2>
 <div class=row><img src="${t.candidate_left}"><img src="${t.candidate_right}"></div>
 <p>1. Which is the better coherent midpoint for this pair? Left / Right / Tie</p>
 <p>2. Which is more like one realistic self-consistent texture? Left / Right / Tie</p>
 <button id=prev>Previous</button><button id=next>Next</button>`;
 document.querySelector('#prev').onclick=()=>{i=Math.max(0,i-1);show()};
 document.querySelector('#next').onclick=()=>{i=Math.min(rows.length-1,i+1);show()};}
 show();});</script>
"""
    atomic_write_text(output_dir / "index.html", html)
    freeze = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "seed": seed,
        "trial_count": len(public_trials),
        "endpoint_pair_count": len(selected),
        "methods": required_methods,
        "public_manifest_sha256": sha256_file(public_path),
        "private_manifest_sha256": sha256_file(private_path),
        "deployed": False,
        "collection_authorized": False,
    }
    atomic_write_json(output_dir / "FREEZE.json", freeze)
    print(f"Prepared {len(public_trials)} blinded trial blocks at {output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"HUMAN STUDY BUILD FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
