#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from common import atomic_write_json, utc_now


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--bootstrap", type=int, default=10000)
    args = parser.parse_args()
    rows = []
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = [
            "k",
            "stratum",
            "space",
            "d_between_orders",
            "d_repeat_AB",
            "d_repeat_BA",
        ]
        if reader.fieldnames != expected:
            raise ValueError(f"Expected exact columns {expected}")
        for row in reader:
            rows.append(
                {
                    "k": row["k"],
                    "stratum": row["stratum"],
                    "space": row["space"],
                    "d_between_orders": float(row["d_between_orders"]),
                    "d_repeat_AB": float(row["d_repeat_AB"]),
                    "d_repeat_BA": float(row["d_repeat_BA"]),
                }
            )
    by_space = defaultdict(list)
    for row in rows:
        by_space[row["space"]].append(row)
    results = []
    rng = np.random.default_rng(args.seed)
    for space, values in sorted(by_space.items()):
        between = np.array([row["d_between_orders"] for row in values])
        within = np.array([(row["d_repeat_AB"] + row["d_repeat_BA"]) / 2 for row in values])
        denominator = float(within.mean())
        valid_pair_ratios = between[within > 0] / within[within > 0]
        strata = np.array([row["stratum"] for row in values])
        groups = [np.flatnonzero(strata == stratum) for stratum in sorted(set(strata))]
        bootstrap_ratios = []
        for _ in range(args.bootstrap):
            sampled = np.concatenate(
                [rng.choice(group, size=len(group), replace=True) for group in groups]
            )
            sampled_denominator = float(within[sampled].mean())
            bootstrap_ratios.append(
                float(between[sampled].mean() / sampled_denominator)
                if sampled_denominator > 0
                else np.nan
            )
        valid_bootstrap = np.array(bootstrap_ratios)[np.isfinite(bootstrap_ratios)]
        results.append(
            {
                "space": space,
                "n_pairs": len(values),
                "mean_between_order_distance": float(between.mean()),
                "mean_within_order_repeat_distance": denominator,
                "preregistered_ratio": float(between.mean() / denominator)
                if denominator > 0
                else None,
                "pairwise_ratio_median": float(np.median(valid_pair_ratios))
                if len(valid_pair_ratios)
                else None,
                "stratified_bootstrap_95_ci": [
                    float(np.percentile(valid_bootstrap, 2.5)),
                    float(np.percentile(valid_bootstrap, 97.5)),
                ]
                if len(valid_bootstrap)
                else None,
            }
        )
    atomic_write_json(
        args.output,
        {
            "schema_version": 1,
            "created_utc": utc_now(),
            "seed": args.seed,
            "bootstrap_replicates": args.bootstrap,
            "results": results,
        },
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
