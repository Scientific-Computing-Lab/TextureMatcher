#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from common import atomic_write_json, utc_now


def holm(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = [0.0] * len(p_values)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        value = min(1.0, (count - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def stratified_bootstrap(
    differences: np.ndarray, strata: np.ndarray, n: int, rng: np.random.Generator
) -> np.ndarray:
    unique = sorted(set(strata.tolist()))
    indices = [np.flatnonzero(strata == stratum) for stratum in unique]
    result = np.empty(n, dtype=np.float64)
    for iteration in range(n):
        sampled = np.concatenate(
            [rng.choice(group, size=len(group), replace=True) for group in indices]
        )
        result[iteration] = differences[sampled].mean()
    return result


def permutation_p(differences: np.ndarray, n: int, rng: np.random.Generator) -> float:
    observed = abs(float(differences.mean()))
    exceed = 0
    for _ in range(n):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(differences))
        exceed += abs(float((differences * signs).mean())) >= observed
    return (exceed + 1) / (n + 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, required=True, help="CSV: k,stratum,method,metric,value"
    )
    parser.add_argument("--compare", action="append", required=True, help="METHOD_A,METHOD_B")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--permutations", type=int, default=100000)
    args = parser.parse_args()
    values: dict[tuple[str, str, str], tuple[str, float]] = {}
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["k", "stratum", "method", "metric", "value"]:
            raise ValueError("Expected exact columns k,stratum,method,metric,value")
        for row in reader:
            key = (row["k"], row["method"], row["metric"])
            if key in values:
                raise ValueError(f"Duplicate observation: {key}")
            values[key] = (row["stratum"], float(row["value"]))

    metrics = sorted({key[2] for key in values})
    results = []
    rng = np.random.default_rng(args.seed)
    for comparison in args.compare:
        method_a, method_b = comparison.split(",", 1)
        for metric in metrics:
            pair_ids = sorted(
                {
                    k
                    for k, method, candidate_metric in values
                    if method == method_a and candidate_metric == metric
                }
                & {
                    k
                    for k, method, candidate_metric in values
                    if method == method_b and candidate_metric == metric
                }
            )
            if len(pair_ids) < 2:
                continue
            strata = np.array([values[(k, method_a, metric)][0] for k in pair_ids])
            for k in pair_ids:
                if values[(k, method_a, metric)][0] != values[(k, method_b, metric)][0]:
                    raise ValueError(f"Stratum mismatch for k={k}")
            differences = np.array(
                [
                    values[(k, method_a, metric)][1] - values[(k, method_b, metric)][1]
                    for k in pair_ids
                ],
                dtype=np.float64,
            )
            bootstrap = stratified_bootstrap(differences, strata, args.bootstrap, rng)
            std = float(differences.std(ddof=1))
            results.append(
                {
                    "method_a": method_a,
                    "method_b": method_b,
                    "metric": metric,
                    "n_pairs": len(pair_ids),
                    "mean_paired_difference_a_minus_b": float(differences.mean()),
                    "median_paired_difference_a_minus_b": float(np.median(differences)),
                    "bootstrap_95_ci": [
                        float(np.percentile(bootstrap, 2.5)),
                        float(np.percentile(bootstrap, 97.5)),
                    ],
                    "paired_effect_dz": float(differences.mean() / std) if std > 0 else math.nan,
                    "permutation_p_unadjusted": permutation_p(differences, args.permutations, rng),
                    "stratified_bootstrap": True,
                }
            )
    adjusted = holm([result["permutation_p_unadjusted"] for result in results])
    for result, value in zip(results, adjusted, strict=True):
        result["permutation_p_holm"] = value
    payload = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "seed": args.seed,
        "bootstrap_replicates": args.bootstrap,
        "permutation_replicates": args.permutations,
        "results": results,
    }
    atomic_write_json(args.output, payload)
    print(json.dumps({"comparisons": len(results), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PAIRED STATISTICS FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
