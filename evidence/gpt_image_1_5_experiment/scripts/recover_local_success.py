#!/usr/bin/env python3
"""Recover a paid image saved before a local terminal-record serialization failure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    append_jsonl,
    atomic_write_text,
    read_jsonl,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)
from diagnose_outputs import diagnose_image
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--request-signature", required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "manifest.jsonl"
    records = read_jsonl(manifest_path)
    matches = [
        (index, record)
        for index, record in enumerate(records)
        if record.get("request_signature") == args.request_signature
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one manifest record, got {len(matches)}")
    index, record = matches[0]
    if record.get("status") != "failed" or record.get("http_status") is not None:
        raise ValueError("Recovery is limited to a local post-response failure")
    output = resolve_experiment_path(record["output_path"])
    if not output.is_file():
        raise FileNotFoundError(output)
    with Image.open(output) as image:
        image.verify()
    with Image.open(output) as image:
        image.load()
        image_format = image.format
        dimensions = list(image.size)
        mode = image.mode
    if image_format != "PNG" or dimensions != [1024, 1024]:
        raise ValueError(f"Recovered output is not the required PNG: {image_format}, {dimensions}")
    diagnostics = diagnose_image(output)
    if not diagnostics["decodable"]:
        raise ValueError("Recovered output failed decoding")
    original_failure = {
        "status": record["status"],
        "error_code": record.get("error_code"),
        "error_message": record.get("error_message"),
        "attempts": record.get("attempts"),
    }
    record.update(
        {
            "status": "success",
            "attempts": [
                {
                    "attempt": 1,
                    "status": "service_success_local_record_recovered",
                }
            ],
            "error_code": None,
            "error_message": None,
            "output_exists": True,
            "output_dimensions": dimensions,
            "output_mode": mode,
            "output_byte_count": output.stat().st_size,
            "output_sha256": sha256_file(output),
            "diagnostics": diagnostics,
            "materialized_aliases": [],
            "usage": None,
            "recovery": {
                "recovered_utc": utc_now(),
                "reason": (
                    "Azure response and PNG succeeded before local NumPy-bool "
                    "JSON serialization failure"
                ),
                "usage_unavailable": True,
                "original_failure": original_failure,
            },
        }
    )
    records[index] = record
    atomic_write_text(
        manifest_path,
        "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in records),
    )
    append_jsonl(
        run_dir / "logs" / "events.jsonl",
        {
            "utc": utc_now(),
            "event": "local_manifest_recovery",
            "request_signature": args.request_signature,
            "k": record["k"],
            "output_sha256": record["output_sha256"],
            "new_paid_call": False,
        },
    )
    print(
        json.dumps(
            {
                "status": "recovered",
                "k": record["k"],
                "request_signature": args.request_signature,
                "output_sha256": record["output_sha256"],
                "usage": None,
                "new_paid_call": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"RECOVERY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
