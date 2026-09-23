#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from common import (
    load_config,
    load_pairs_manifest,
    read_jsonl,
    resolve_experiment_path,
    sha256_file,
)


def copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--series", default="S1")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    expected = {pair["k"] for pair in load_pairs_manifest(config)["pairs"]}
    records = [
        record
        for record in read_jsonl(args.run_dir.resolve() / "manifest.jsonl")
        if record.get("status") in {"success", "skipped_existing"}
    ]
    by_k: dict[str, tuple[dict, Path]] = {}
    for record in records:
        if record.get("series_id") == args.series:
            by_k[record["k"]] = (record, resolve_experiment_path(record["output_path"]))
        for alias in record.get("materialized_aliases", []):
            if alias.get("series_id") == args.series:
                by_k[record["k"]] = (record, resolve_experiment_path(alias["output_path"]))
    if set(by_k) != expected:
        raise ValueError(
            f"Series {args.series} is incomplete: missing {len(expected - set(by_k))}, "
            f"extra {len(set(by_k) - expected)}"
        )
    for k in sorted(expected):
        record, source = by_k[k]
        if sha256_file(source) != record["output_sha256"]:
            raise RuntimeError(f"Manifest/output hash mismatch for k={k}")
        copy_atomic(source, args.output_dir.resolve() / f"{k}_mid.png")
    print(f"Exported exactly {len(expected)} verified files to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"EXPORT FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
