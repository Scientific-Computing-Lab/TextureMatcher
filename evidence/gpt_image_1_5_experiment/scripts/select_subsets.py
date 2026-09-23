#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter

from common import (
    atomic_write_json,
    canonical_json,
    load_config,
    load_pairs_manifest,
    resolve_experiment_path,
    sha256_file,
    sha256_text,
    utc_now,
)


def score(seed: int, subset: str, k: str) -> str:
    return hashlib.sha256(f"{seed}:{subset}:{k}".encode()).hexdigest()


def select(
    labels: dict[str, dict], regimes: list[str], seed: int, name: str, quota: int
) -> list[dict]:
    selected = []
    for regime in regimes:
        candidates = [value for value in labels.values() if value["regime"] == regime]
        candidates.sort(key=lambda value: (score(seed, name, value["k"]), value["k"]))
        if len(candidates) < quota:
            raise ValueError(f"Subset {name}: regime {regime} has {len(candidates)}, needs {quota}")
        for value in candidates[:quota]:
            selected.append({**value, "selection_score": score(seed, name, value["k"])})
    return selected


def main() -> int:
    config = load_config()
    manifest = load_pairs_manifest(config)
    path = resolve_experiment_path(config["data"]["strata_annotations"])
    if not path.exists():
        raise FileNotFoundError(f"Missing source-only annotations: {path}; run prepare_strata.py")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = ["k", "regime", "rationale", "annotator", "annotated_utc"]
        if reader.fieldnames != expected:
            raise ValueError(
                f"Expected exact annotation columns {expected}, got {reader.fieldnames}"
            )
        rows = [{key: value.strip() for key, value in row.items()} for row in reader]

    expected_ids = {pair["k"] for pair in manifest["pairs"]}
    ids = [row["k"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise ValueError("Annotations must contain every pair k exactly once")
    regimes = list(config["selection"]["regimes"])
    for row in rows:
        if row["regime"] not in regimes:
            raise ValueError(f"k={row['k']}: invalid/blank regime {row['regime']!r}")
        if not row["rationale"]:
            raise ValueError(f"k={row['k']}: a source-only rationale is required")

    labels = {row["k"]: row for row in rows}
    seed = int(config["seed"])
    subsets = {
        "pilot_3": select(
            labels, regimes, seed, "pilot_3", int(config["selection"]["pilot_per_regime"])
        ),
        "s3_24": select(labels, regimes, seed, "s3_24", int(config["selection"]["s3_per_regime"])),
        "s5_12": select(labels, regimes, seed, "s5_12", int(config["selection"]["s5_per_regime"])),
        "human_42": select(
            labels,
            regimes,
            seed,
            "human_42",
            int(config["human_study"]["endpoint_pairs_per_regime"]),
        ),
    }
    payload = {
        "schema_version": 1,
        "frozen_utc": utc_now(),
        "seed": seed,
        "selection_rule": "ascending sha256('<seed>:<subset>:<k>') independently per regime",
        "source_only_annotation_contract": True,
        "pairs_dataset_digest": manifest["dataset_digest"],
        "annotations_sha256": sha256_file(path),
        "regime_counts": dict(sorted(Counter(row["regime"] for row in rows).items())),
        "subsets": subsets,
    }
    payload["subsets_digest"] = sha256_text(canonical_json(payload["subsets"]))
    output = resolve_experiment_path(config["data"]["subsets"])
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("subsets_digest") != payload["subsets_digest"]:
            raise RuntimeError(
                "Subset selection differs from the frozen selection; refusing overwrite"
            )
        print(f"Frozen subsets verified: {output}")
        return 0
    atomic_write_json(output, payload)
    print(f"Frozen subsets: {output}")
    for name, values in subsets.items():
        print(f"{name}: {','.join(value['k'] for value in values)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"SELECTION FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
