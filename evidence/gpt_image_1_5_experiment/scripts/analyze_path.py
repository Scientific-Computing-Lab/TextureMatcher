#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from common import atomic_write_json, utc_now


def r_squared(x: np.ndarray, y: np.ndarray) -> float:
    prediction = np.polyval(np.polyfit(x, y, 1), x)
    residual = float(np.square(y - prediction).sum())
    total = float(np.square(y - y.mean()).sum())
    return 1.0 - residual / total if total > 0 else 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    groups = defaultdict(list)
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = ["k", "space", "t", "d_to_A", "d_to_B", "step_from_previous"]
        if reader.fieldnames != expected:
            raise ValueError(f"Expected exact columns {expected}")
        for row in reader:
            groups[(row["k"], row["space"])].append({key: float(row[key]) for key in expected[2:]})
    results = []
    expected_t = np.linspace(0, 1, 11)
    for (k, space), rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["t"])
        t = np.array([row["t"] for row in rows])
        if len(rows) != 11 or not np.allclose(t, expected_t, atol=1e-8):
            raise ValueError(f"k={k}, space={space}: expected t=0.0,...,1.0")
        d_a = np.array([row["d_to_A"] for row in rows])
        d_b = np.array([row["d_to_B"] for row in rows])
        coordinate = d_a / np.maximum(d_a + d_b, 1e-12)
        steps = np.array([row["step_from_previous"] for row in rows[1:]])
        results.append(
            {
                "k": k,
                "space": space,
                "midpoint_ratio": float(coordinate[5]),
                "midpoint_balance": float(abs(coordinate[5] - 0.5)),
                "coordinate_monotonic_fraction": float(np.mean(np.diff(coordinate) >= 0)),
                "distance_to_A_monotonic_fraction": float(np.mean(np.diff(d_a) >= 0)),
                "distance_to_B_monotonic_fraction": float(np.mean(np.diff(d_b) <= 0)),
                "path_linearity_r2": r_squared(t, coordinate),
                "mean_step_size": float(steps.mean()),
                "step_size_cv": float(steps.std(ddof=1) / steps.mean())
                if steps.mean() > 0
                else None,
                "max_to_median_step_ratio": float(steps.max() / np.median(steps))
                if np.median(steps) > 0
                else None,
            }
        )
    atomic_write_json(
        args.output,
        {"schema_version": 1, "created_utc": utc_now(), "results": results},
    )
    print(f"Computed path diagnostics for {len(results)} pair/space groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
