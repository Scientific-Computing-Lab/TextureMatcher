#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import (
    EXPERIMENT_ROOT,
    atomic_write_json,
    atomic_write_text,
    load_config,
    read_jsonl,
    utc_now,
)
from compute_perceptual_metrics import load_regimes


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def usage_totals(records: list[dict[str, Any]]) -> dict[str, int]:
    totals = Counter()
    for record in records:
        usage = record.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        totals["input_text"] += int(input_details.get("text_tokens", 0))
        totals["input_image"] += int(input_details.get("image_tokens", 0))
        totals["output_text"] += int(output_details.get("text_tokens", 0))
        totals["output_image"] += int(output_details.get("image_tokens", 0))
        totals["total"] += int(usage.get("total_tokens", 0))
    return dict(totals)


def impute_missing_usage(records: list[dict[str, Any]]) -> dict[str, int]:
    fields = {
        "input_text": ("input_tokens_details", "text_tokens"),
        "input_image": ("input_tokens_details", "image_tokens"),
        "output_text": ("output_tokens_details", "text_tokens"),
        "output_image": ("output_tokens_details", "image_tokens"),
    }
    observed: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in records:
        usage = record.get("usage")
        if not usage:
            continue
        for field, (detail_key, token_key) in fields.items():
            observed[(record["prompt_id"], field)].append(
                int((usage.get(detail_key) or {}).get(token_key, 0))
            )
    imputed = Counter()
    for record in records:
        if record.get("usage") is not None:
            continue
        missing_total = 0
        for field in fields:
            values = observed[(record["prompt_id"], field)]
            if not values:
                raise ValueError(f"Cannot impute {field} for prompt {record['prompt_id']}")
            value = round(statistics.median(values))
            imputed[field] += value
            missing_total += value
        imputed["total"] += missing_total
    return dict(imputed)


def cost_usd(tokens: dict[str, int], rates: dict[str, float]) -> float:
    return sum(tokens.get(kind, 0) * rates[kind] for kind in rates) / 1_000_000


def combined_usage(records: list[dict[str, Any]]) -> tuple[dict[str, int], int, dict[str, int]]:
    observed = usage_totals(records)
    missing = sum(record.get("usage") is None for record in records)
    imputed = impute_missing_usage(records)
    combined = {
        key: observed.get(key, 0) + imputed.get(key, 0)
        for key in {"input_text", "input_image", "output_text", "output_image", "total"}
    }
    return combined, missing, imputed


def logical_series_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for record in records:
        if record.get("status") not in {"success", "skipped_existing"}:
            continue
        counts[record["series_id"]] += 1
        for alias in record.get("materialized_aliases", []):
            counts[alias["series_id"]] += 1
    return dict(sorted(counts.items()))


def endpoint_summary(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["space"], row["stratum"])].append(row)
        groups[(row["method"], row["space"], "all")].append(row)
    result = []
    for (method, space, stratum), values in sorted(groups.items()):
        coordinates = [float(row["midpoint_coordinate"]) for row in values]
        balances = [float(row["midpoint_balance"]) for row in values]
        result.append(
            {
                "method": method,
                "space": space,
                "stratum": stratum,
                "n": len(values),
                "mean_midpoint_coordinate": statistics.mean(coordinates),
                "mean_absolute_balance_error": statistics.mean(balances),
                "median_absolute_balance_error": statistics.median(balances),
            }
        )
    return result


def prompt_ablation_summary(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["space"]].append(row)
    fields = ("d_P0_P1", "d_P0_P2", "d_P1_P2")
    return [
        {
            "space": space,
            "n": len(values),
            **{field: statistics.mean(float(row[field]) for row in values) for field in fields},
        }
        for space, values in sorted(groups.items())
    ]


def path_summary_by_space(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in (payload or {}).get("results", []):
        groups[row["space"]].append(row)
    fields = (
        "midpoint_balance",
        "coordinate_monotonic_fraction",
        "path_linearity_r2",
        "step_size_cv",
    )
    return [
        {
            "space": space,
            "n": len(values),
            **{field: statistics.mean(float(row[field]) for row in values) for field in fields},
        }
        for space, values in sorted(groups.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    config = load_config()
    records = read_jsonl(run_dir / "manifest.jsonl")
    if len(records) != 444:
        raise ValueError(f"Expected 444 terminal full-plan records, got {len(records)}")
    failures = [record for record in records if record.get("status") == "failed"]
    if failures:
        raise RuntimeError(f"Full run contains {len(failures)} failed logical requests")
    successes = [record for record in records if record.get("status") == "success"]
    reused = [record for record in records if record.get("status") == "skipped_existing"]
    ledger = read_jsonl(EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl")
    dispatches = [record for record in ledger if record.get("run_id") == run_dir.name]
    regimes = load_regimes(config)
    latencies = [float(record["latency_seconds"]) for record in successes]
    sizes = [int(record["output_byte_count"]) for record in successes]
    tokens = usage_totals(successes)
    billable_tokens, usage_missing, imputed_tokens = combined_usage(successes)
    rates = config["azure"]["pricing"]["usd_per_million_tokens"]
    data_zone_cost = cost_usd(billable_tokens, rates)
    global_cost = data_zone_cost * float(config["azure"]["pricing"]["global_standard_multiplier"])
    service_by_series = []
    for series in sorted({record["series_id"] for record in records}):
        generated = [record for record in successes if record["series_id"] == series]
        series_tokens, series_missing, _ = combined_usage(generated)
        service_by_series.append(
            {
                "series": series,
                "paid_successes": len(generated),
                "signature_reuses": sum(record["series_id"] == series for record in reused),
                "serial_seconds": sum(float(record["latency_seconds"]) for record in generated),
                "billable_tokens_estimate": series_tokens,
                "missing_usage_responses": series_missing,
                "data_zone_cost_usd": cost_usd(series_tokens, rates),
            }
        )
    hashes = Counter(record["output_sha256"] for record in records)
    duplicate_primary_hashes = sorted(digest for digest, count in hashes.items() if count > 1)

    diagnostic_by_series_regime: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for record in records:
        logical_series = [record["series_id"]] + [
            alias["series_id"] for alias in record.get("materialized_aliases", [])
        ]
        flags = record.get("diagnostics", {}).get("flags", [])
        for series in logical_series:
            key = (series, regimes[record["k"]])
            diagnostic_by_series_regime[key]["outputs"] += 1
            diagnostic_by_series_regime[key]["flagged"] += bool(flags)
            for flag in flags:
                diagnostic_by_series_regime[key][flag] += 1
    diagnostic_summary = [
        {"series": series, "stratum": stratum, **dict(counts)}
        for (series, stratum), counts in sorted(diagnostic_by_series_regime.items())
    ]

    metric_dir = run_dir / "evaluation" / "perceptual"
    metadata_path = metric_dir / "metadata.json"
    metric_metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else None
    )
    endpoint = endpoint_summary(load_csv(metric_dir / "endpoint_metrics.csv"))
    prompt_ablation = prompt_ablation_summary(
        load_csv(metric_dir / "prompt_ablation_distances.csv")
    )
    symmetry_path = metric_dir / "symmetry_summary.json"
    path_path = metric_dir / "path_summary.json"
    paired_path = metric_dir / "paired_summary.json"
    symmetry = (
        json.loads(symmetry_path.read_text(encoding="utf-8")) if symmetry_path.exists() else None
    )
    path_metrics = json.loads(path_path.read_text(encoding="utf-8")) if path_path.exists() else None
    paired = json.loads(paired_path.read_text(encoding="utf-8")) if paired_path.exists() else None
    payload = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "run_id": run_dir.name,
        "planned_unique_requests": 444,
        "nominal_cells": 516,
        "new_successes": len(successes),
        "signature_reuses": len(reused),
        "failures": len(failures),
        "paid_dispatches": len(dispatches),
        "logical_series_counts": logical_series_counts(records),
        "latency_seconds": {
            "sum": sum(latencies),
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p90": quantile(latencies, 0.9),
            "max": max(latencies),
        },
        "output_bytes": {"sum": sum(sizes), "median": statistics.median(sizes)},
        "usage": tokens,
        "usage_missing_successes": usage_missing,
        "imputed_usage_for_missing_successes": imputed_tokens,
        "billable_usage_estimate": billable_tokens,
        "estimated_azure_cost_usd": {
            "data_zone_retail": data_zone_cost,
            "global_standard_retail": global_cost,
            "rates": rates,
            "source": config["azure"]["pricing"]["source"],
            "retrieved_utc": config["azure"]["pricing"]["retrieved_utc"],
        },
        "service_by_primary_series": service_by_series,
        "duplicate_primary_hashes": duplicate_primary_hashes,
        "diagnostics_by_series_and_stratum": diagnostic_summary,
        "endpoint_metrics": endpoint,
        "prompt_ablation": prompt_ablation,
        "symmetry": symmetry,
        "path": path_metrics,
        "paired_endpoint_statistics": paired,
        "path_summary_by_space": path_summary_by_space(path_metrics),
        "local_perceptual_evaluation": metric_metadata,
        "blocked_evaluation_assets": [
            "AAT midpoint outputs for all 120 pair IDs",
            "Gaussian midpoint outputs for all 120 pair IDs",
            "Texture Mixer midpoint outputs for all 120 pair IDs",
            "position baseline outputs for all 120 pair IDs",
            "fixed DTD reference-pool manifest",
            "the original 128x128 evaluator resize/color protocol",
        ],
    }
    report_json = EXPERIMENT_ROOT / "reports" / "FULL_RUN_REPORT.json"
    atomic_write_json(report_json, payload)

    series_rows = "\n".join(
        f"| {series} | {count} |" for series, count in payload["logical_series_counts"].items()
    )
    endpoint_rows = (
        "\n".join(
            f"| {row['method']} | {row['space']} | {row['stratum']} | {row['n']} | "
            f"{row['mean_midpoint_coordinate']:.4f} | {row['mean_absolute_balance_error']:.4f} |"
            for row in endpoint
        )
        or "| Not computed | — | — | 0 | — | — |"
    )
    service_rows = "\n".join(
        f"| {row['series']} | {row['paid_successes']} | {row['signature_reuses']} | "
        f"{row['serial_seconds'] / 60:.1f} min | {row['billable_tokens_estimate']['total']:,} | "
        f"${row['data_zone_cost_usd']:.2f} |"
        for row in service_by_series
    )
    paired_rows = (
        "\n".join(
            f"| {row['metric']} | {row['n_pairs']} | "
            f"{row['mean_paired_difference_a_minus_b']:.4f} | "
            f"[{row['bootstrap_95_ci'][0]:.4f}, {row['bootstrap_95_ci'][1]:.4f}] | "
            f"{row['paired_effect_dz']:.4f} | {row['permutation_p_holm']:.4g} |"
            for row in (paired or {}).get("results", [])
        )
        or "| Not computed | 0 | — | — | — | — |"
    )
    prompt_rows = (
        "\n".join(
            f"| {row['space']} | {row['n']} | {row['d_P0_P1']:.4f} | "
            f"{row['d_P0_P2']:.4f} | {row['d_P1_P2']:.4f} |"
            for row in prompt_ablation
        )
        or "| Not computed | 0 | — | — | — |"
    )
    symmetry_rows = (
        "\n".join(
            f"| {row['space']} | {row['n_pairs']} | "
            f"{row['mean_between_order_distance']:.4f} | "
            f"{row['mean_within_order_repeat_distance']:.4f} | "
            f"{row['preregistered_ratio']:.4f} | "
            f"[{row['stratified_bootstrap_95_ci'][0]:.4f}, "
            f"{row['stratified_bootstrap_95_ci'][1]:.4f}] |"
            for row in (symmetry or {}).get("results", [])
        )
        or "| Not computed | 0 | — | — | — | — |"
    )
    path_rows = (
        "\n".join(
            f"| {row['space']} | {row['n']} | {row['midpoint_balance']:.4f} | "
            f"{row['coordinate_monotonic_fraction']:.4f} | "
            f"{row['path_linearity_r2']:.4f} | {row['step_size_cv']:.4f} |"
            for row in path_summary_by_space(path_metrics)
        )
        or "| Not computed | 0 | — | — | — | — |"
    )
    diagnostic_rows = "\n".join(
        f"| {row['series']} | {row['stratum']} | {row.get('outputs', 0)} | "
        f"{row.get('flagged', 0)} | {row.get('blank', 0)} | "
        f"{row.get('near_uniform', 0)} | {row.get('suspicious_border', 0)} | "
        f"{row.get('suspicious_panel_layout', 0)} |"
        for row in diagnostic_summary
    )
    report = f"""# Full GPT Image 1.5 run report

Generated: {payload["created_utc"]}. Run: `{run_dir.name}`.

## Completion

- Nominal S1–S5 cells: **516**.
- Unique request signatures: **444**.
- Reused exact high-quality preview signatures: **{len(reused)}**.
- New successful paid requests: **{len(successes)}**.
- Paid dispatches including retries: **{len(dispatches)}**.
- Failed logical requests: **{len(failures)}**.
- Missing usage payloads among new successes: **{usage_missing}**.
- Unexpected duplicate primary-output hashes: **{len(duplicate_primary_hashes)}**.

| Series | Completed logical cells |
|---|---:|
{series_rows}

## Service measurements and cost

| Series | Paid | Reused | Serial time | Billable tokens | Data Zone cost |
|---|---:|---:|---:|---:|---:|
{service_rows}

- Serial API time: **{sum(latencies) / 3600:.2f} hours**; median
  **{statistics.median(latencies):.2f}s**, p90 **{quantile(latencies, 0.9):.2f}s**,
  maximum **{max(latencies):.2f}s**.
- New output bytes: **{sum(sizes) / (1024**3):.2f} GiB**.
- Billable token estimate: **{billable_tokens.get("total", 0):,} total**;
  {billable_tokens.get("input_image", 0):,} input-image,
  {billable_tokens.get("input_text", 0):,} input-text,
  {billable_tokens.get("output_image", 0):,} output-image, and
  {billable_tokens.get("output_text", 0):,} output-text. This uses actual
  service usage except for {usage_missing} locally recovered response(s),
  imputed component-wise from the median for the same frozen prompt.
- Azure Data Zone retail estimate: **${data_zone_cost:.2f} USD**.
- Azure Global Standard retail equivalent: **${global_cost:.2f} USD**.
- Local DINOv2/LPIPS evaluation: **{metric_metadata["elapsed_seconds"]:.2f}s** on
  **{metric_metadata["gpu"]}**; this is reported separately from API latency and
  is not comparable to the paper's local A100 method runtime.

These estimates use the frozen Azure retail meters in `config.yaml`; private
discounts, taxes, and local evaluation compute are excluded.

## Endpoint-conditioned metrics

The midpoint coordinate is `d(M,A)/(d(M,A)+d(M,B))`; 0.5 is balanced. Balance
error is its absolute deviation from 0.5. These are descriptive distances, not
ground-truth correctness scores.

| Method | Space | Stratum | n | Mean coordinate | Mean balance error |
|---|---|---|---:|---:|---:|
{endpoint_rows}

Paired values below are P2 minus P1 absolute balance error, so negative favors
P2 only for this descriptive balance criterion. They do not establish
perceptual correctness.

| Metric | n | Mean paired difference | Stratified bootstrap 95% CI | dz | Holm p |
|---|---:|---:|---:|---:|---:|
{paired_rows}

Both observed differences are positive: P1 is closer to symmetric endpoint
balance in these feature spaces. P2's stronger source bias is consistent with
its different directed source-layout contract, so this is not a method ranking.

## Prompt, symmetry, and path diagnostics

S3 distances are means over the frozen 24-pair subset. Larger values mean the
prompt variants produced more perceptually separated samples.

| Space | n | P0–P1 | P0–P2 | P1–P2 |
|---|---:|---:|---:|---:|
{prompt_rows}

The preregistered S4 ratio is mean between-order distance divided by mean
within-order repeat distance. A value near one means order effects are no
larger than the stochastic repeat floor.

| Space | n | Between order | Within repeat | Ratio | Bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|
{symmetry_rows}

S5 values below are means over the frozen 12-pair path subset. Monotonicity and
R² are descriptive prompt-control measures, not evidence of a latent geodesic.

| Space | n | Midpoint balance | Coordinate monotonicity | Linearity R² | Step CV |
|---|---:|---:|---:|---:|---:|
{path_rows}

All pair-level values are stored beside the raw metric CSVs under
`runs/{run_dir.name}/evaluation/perceptual/`.

## S6 scope and blockers

The source-only frozen strata are used below; flags are conservative automated
review cues and flagged outputs remain in every analysis.

| Series | Stratum | n | Any flag | Blank | Uniform | Border | Panel-like |
|---|---|---:|---:|---:|---:|---:|---:|
{diagnostic_rows}

Automated output diagnostics are stratified by the frozen source-only regime
labels in `FULL_RUN_REPORT.json`. The post-hoc disposition of all six flags is
recorded in `reports/VISUAL_QC.md`; every flagged output remains included.
KID/FID, cross-method paired tests, and the
complete blinded human-study trial build were not fabricated because the
repository does not contain the required baseline outputs, fixed DTD reference
manifest, or recovered 128x128 evaluator transform. The human-study protocol
and power analysis remain ready but undeployed.
"""
    atomic_write_text(EXPERIMENT_ROOT / "reports" / "FULL_RUN_REPORT.md", report)
    print(json.dumps({"report": str(report_json), "cost_usd": data_zone_cost}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FULL REPORT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
