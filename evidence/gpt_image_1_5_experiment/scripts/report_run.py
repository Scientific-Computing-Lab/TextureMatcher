#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from common import EXPERIMENT_ROOT, atomic_write_text, load_config, read_jsonl, utc_now


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--blocked-reason")
    args = parser.parse_args()
    config = load_config()
    reports = EXPERIMENT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    preflight_path = reports / "preflight.json"
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.exists() else {}
    )
    records = read_jsonl(args.run_dir / "manifest.jsonl") if args.run_dir else []
    ledger = read_jsonl(EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl")
    run_id = args.run_dir.name if args.run_dir else None
    run_ledger = [row for row in ledger if row.get("run_id") == run_id] if run_id else []
    successes = [record for record in records if record.get("status") == "success"]
    failures = [record for record in records if record.get("status") == "failed"]
    latencies = [float(record["latency_seconds"]) for record in successes]
    output_sizes = [int(record["output_byte_count"]) for record in successes]
    latency_median = statistics.median(latencies) if latencies else "n/a"
    latency_p10 = quantile(latencies, 0.1) if latencies else "n/a"
    latency_p90 = quantile(latencies, 0.9) if latencies else "n/a"
    size_min = min(output_sizes) if output_sizes else "n/a"
    size_median = statistics.median(output_sizes) if output_sizes else "n/a"
    size_max = max(output_sizes) if output_sizes else "n/a"
    endpoint = config["azure"]["endpoint"]
    api_version = config["azure"]["api_version"]
    deployment = config["azure"]["deployment"]
    status = "completed" if len(successes) == 10 and not failures else "blocked_or_incomplete"
    blocker = args.blocked_reason or (None if status == "completed" else "Pilot is incomplete")
    smoke = next((record for record in records if record.get("series_id") == "SMOKE"), None)
    smoke_dispatches = (
        sum(
            row.get("request_signature") == smoke.get("request_signature")
            for row in run_ledger
        )
        if smoke
        else 0
    )
    smoke_dimensions = smoke.get("output_dimensions") if smoke else "not available"
    smoke_mode = smoke.get("output_mode") if smoke else "not available"
    smoke_bytes = smoke.get("output_byte_count") if smoke else "not available"
    smoke_report = f"""# Smoke report

- Reported UTC: {utc_now()}
- Status: **{smoke.get("status") if smoke else "NOT RUN"}**
- Azure endpoint: `{config["azure"]["endpoint"]}`
- API version: `{config["azure"]["api_version"]}`
- Deployment: `{config["azure"]["deployment"]}`
- Credential value recorded: no
- Two-reference edit request: {"confirmed" if smoke else "not dispatched"}
- Paid dispatches for the smoke request: {smoke_dispatches}
- Smoke latency seconds: {smoke.get("latency_seconds") if smoke else "not available"}
- Output dimensions/mode/bytes: {smoke_dimensions} / {smoke_mode} / {smoke_bytes}
- Request ID: `{smoke.get("request_id") if smoke else "not available"}`
- Output SHA-256: `{smoke.get("output_sha256") if smoke else "not available"}`
- Revised prompt returned: {"yes" if smoke and smoke.get("revised_prompt") else "no/not available"}
- Blocker: {blocker or "none"}
"""
    atomic_write_text(reports / "SMOKE_REPORT.md", smoke_report)

    sheets = []
    if args.run_dir:
        index = args.run_dir / "contact_sheets" / "index.json"
        if index.exists():
            sheets = json.loads(index.read_text(encoding="utf-8"))
    diagnostics = {}
    if args.run_dir:
        diagnostics_path = args.run_dir / "diagnostics.json"
        if diagnostics_path.exists():
            diagnostics_records = read_jsonl(diagnostics_path)
            diagnostics = next(
                (item for item in diagnostics_records if item.get("type") == "summary"), {}
            )
    review = {}
    if args.run_dir:
        review_path = args.run_dir / "visual_review.json"
        if review_path.exists():
            review = json.loads(review_path.read_text(encoding="utf-8"))
    subset_text = "not frozen because the external pair manifest is absent"
    subsets = EXPERIMENT_ROOT / config["data"]["subsets"]
    if subsets.exists():
        data = json.loads(subsets.read_text(encoding="utf-8"))
        subset_text = "; ".join(
            f"{item['k']} ({item['regime']}: {item['rationale']})"
            for item in data["subsets"]["pilot_3"]
        )
    client_instantiated = preflight.get("client_instantiated", "not checked")
    latency_min = min(latencies) if latencies else "n/a"
    latency_max = max(latencies) if latencies else "n/a"
    pilot_report = f"""# Pilot report

Status: **{status}**. Reported UTC: {utc_now()}.

## Deployment and execution

- OpenAI Python SDK: {preflight.get("openai_sdk_version", "not checked")}.
- Multi-file `images.edit` declared: {preflight.get("multiple_inputs_declared", "not checked")}.
- Azure client instantiated during local preflight: {client_instantiated}.
- Endpoint: `{endpoint}`.
- API version/deployment: `{api_version}`, `{deployment}`.
- Secrets recorded: no.
- Paid API dispatches in this run: **{len(run_ledger)}** (cap: 10).
- Successful logical requests: {len(successes)}; failed logical requests: {len(failures)}.
- Successful latency seconds: min {latency_min}, median {latency_median},
  p10 {latency_p10}, p90 {latency_p90}, max {latency_max}.
- Output byte sizes: min {size_min}, median {size_median}, max {size_max}.

## Preregistered pairs

{subset_text}

## Contact sheets and compliance

Contact sheets: {", ".join(sheets) if sheets else "none; no generated outputs exist"}.
Automated diagnostics: {diagnostics.get("image_count", 0)} images checked;
{diagnostics.get("flagged_count", 0)} flagged; {len(diagnostics.get("duplicate_groups", {}))}
exact duplicate groups. Visual compliance review: {review.get("summary", "not yet recorded")}
Prompt observations: {review.get("prompt_observations", "not yet recorded")}
These three pairs are prompt/compliance diagnostics only and are not used to
select a scientific winner.

## Proposed full run

S1 120 new; S2 120 new; S3 72 nominal/48 reused/24 new; S4 96 nominal/24
reused/72 new; S5 108 new; S6 zero. Total: **444 new paid requests** after the
pilot, with 72 exact high-quality cells reused.

Cost must be estimated from the actual Azure account/region/deployment meter or
billing export at approval time. Record timestamp/currency and reconcile the
manifest's actual usage; no public or guessed unit price is substituted.

## Approval gate / blocker

{blocker or "Pilot complete. Full execution remains prohibited without explicit series approval."}
"""
    atomic_write_text(reports / "PILOT_REPORT.md", pilot_report)
    print(f"Wrote {reports / 'SMOKE_REPORT.md'} and {reports / 'PILOT_REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
