#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from common import EXPERIMENT_ROOT, read_jsonl, resolve_experiment_path, sha256_file

REQUIRED = {
    "run_id",
    "series_id",
    "prompt_id",
    "prompt_hash",
    "request_signature",
    "k",
    "sha256_A",
    "sha256_B",
    "input_order",
    "endpoint",
    "api_version",
    "deployment",
    "sdk_version",
    "size",
    "quality",
    "input_fidelity",
    "output_format",
    "replicate",
    "started_utc",
    "ended_utc",
    "latency_seconds",
    "attempt_count",
    "status",
    "git_commit",
    "dirty_worktree",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.run_dir.resolve() / "manifest.jsonl"
    records = read_jsonl(manifest)
    errors = []
    signatures = Counter(record.get("request_signature") for record in records)
    duplicates = sorted(signature for signature, count in signatures.items() if count > 1)
    if duplicates:
        errors.append(f"duplicate terminal request signatures: {duplicates}")
    for line, record in enumerate(records, 1):
        missing = sorted(REQUIRED - set(record))
        if missing:
            errors.append(f"line {line}: missing {missing}")
        if record.get("status") in {"success", "skipped_existing"}:
            output = resolve_experiment_path(record["output_path"])
            if not output.is_file():
                errors.append(f"line {line}: missing output {output}")
            elif sha256_file(output) != record.get("output_sha256"):
                errors.append(f"line {line}: output hash mismatch {output}")
        for alias in record.get("materialized_aliases", []):
            alias_path = resolve_experiment_path(alias["output_path"])
            if not alias_path.is_file():
                errors.append(f"line {line}: missing alias output {alias_path}")
            elif sha256_file(alias_path) != alias.get("sha256"):
                errors.append(f"line {line}: alias hash mismatch {alias_path}")
    ledger = read_jsonl(EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl")
    run_ids = {record.get("run_id") for record in records}
    dispatches = [record for record in ledger if record.get("run_id") in run_ids]
    result = {
        "records": len(records),
        "successes": sum(record.get("status") == "success" for record in records),
        "failures": sum(record.get("status") == "failed" for record in records),
        "paid_dispatches": len(dispatches),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
