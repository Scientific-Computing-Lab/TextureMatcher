#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from common import (
    atomic_write_json,
    canonical_json,
    load_config,
    resolve_experiment_path,
    sha256_file,
    sha256_text,
    utc_now,
)
from PIL import Image

COLUMNS = ["k", "category_A", "category_B", "file_A", "file_B"]


def safe_child(root: Path, filename: str) -> Path:
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes input directory: {filename!r}") from exc
    return candidate


def endpoint_path(data_root: Path, endpoint_dir: Path, filename: str) -> Path:
    relative = Path(filename)
    if relative.parts and relative.parts[0] == endpoint_dir.name:
        candidate = safe_child(data_root, filename)
    else:
        candidate = safe_child(endpoint_dir, filename)
    try:
        candidate.relative_to(endpoint_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Endpoint path is outside {endpoint_dir}: {filename!r}") from exc
    return candidate


def image_metadata(path: Path, expected_size: tuple[int, int], allowed_modes: set[str]) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            mode = image.mode
    except Exception as exc:
        raise ValueError(f"Unreadable image {path}: {exc}") from exc
    if (width, height) != expected_size:
        raise ValueError(f"{path}: expected {expected_size}, got {(width, height)}")
    if mode not in allowed_modes:
        raise ValueError(f"{path}: expected mode in {sorted(allowed_modes)}, got {mode}")
    return {
        "width": width,
        "height": height,
        "mode": mode,
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def validate(config: dict) -> dict:
    data = config["data"]
    pairs_csv = resolve_experiment_path(data["pairs_csv"])
    data_root = resolve_experiment_path(data["root"])
    a_dir = resolve_experiment_path(data["a_dir"])
    b_dir = resolve_experiment_path(data["b_dir"])
    if not pairs_csv.is_file():
        raise FileNotFoundError(f"Frozen pairs CSV is missing: {pairs_csv}")
    if not a_dir.is_dir() or not b_dir.is_dir():
        raise FileNotFoundError(f"Expected endpoint directories: {a_dir} and {b_dir}")

    with pairs_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Expected exact CSV columns/order {COLUMNS}, got {reader.fieldnames}")
        rows = list(reader)

    expected_rows = int(data["expected_rows"])
    if len(rows) != expected_rows:
        raise ValueError(f"Expected exactly {expected_rows} rows, got {len(rows)}")
    keys = [row["k"].strip() for row in rows]
    if len(set(keys)) != len(keys):
        duplicates = sorted(k for k, count in Counter(keys).items() if count > 1)
        raise ValueError(f"Duplicate k values: {duplicates}")

    expected_size = tuple(int(value) for value in data["expected_size"])
    allowed_modes = set(data["allowed_modes"])
    pairs = []
    for row_number, row in enumerate(rows, 2):
        values = {key: value.strip() for key, value in row.items()}
        k = values["k"]
        if len(k) != 4 or not k.isdigit():
            raise ValueError(f"Row {row_number}: k must be four digits, got {k!r}")
        if not all(values.values()):
            raise ValueError(f"Row {row_number}: empty required field")
        if values["category_A"] == values["category_B"]:
            raise ValueError(f"Row {row_number}: expected cross-category pair for k={k}")
        if Path(values["file_A"]).name[:4] != k or Path(values["file_B"]).name[:4] != k:
            raise ValueError(f"Row {row_number}: A/B filenames must share leading four-digit k={k}")

        path_a = endpoint_path(data_root, a_dir, values["file_A"])
        path_b = endpoint_path(data_root, b_dir, values["file_B"])
        meta_a = image_metadata(path_a, expected_size, allowed_modes)
        meta_b = image_metadata(path_b, expected_size, allowed_modes)
        pairs.append(
            {
                **values,
                "path_A": str(path_a.relative_to(data_root)),
                "path_B": str(path_b.relative_to(data_root)),
                "sha256_A": meta_a["sha256"],
                "sha256_B": meta_b["sha256"],
                "bytes_A": meta_a["byte_count"],
                "bytes_B": meta_b["byte_count"],
                "width_A": meta_a["width"],
                "height_A": meta_a["height"],
                "width_B": meta_b["width"],
                "height_B": meta_b["height"],
                "mode_A": meta_a["mode"],
                "mode_B": meta_b["mode"],
            }
        )

    semantic_payload = {
        "pairs_csv_sha256": sha256_file(pairs_csv),
        "row_count": len(pairs),
        "pairs": pairs,
    }
    category_a = Counter(pair["category_A"] for pair in pairs)
    category_b = Counter(pair["category_B"] for pair in pairs)
    unordered = Counter(
        " | ".join(sorted((pair["category_A"], pair["category_B"]))) for pair in pairs
    )
    return {
        "schema_version": 1,
        "frozen_utc": utc_now(),
        "source_url": data.get("source_url"),
        "source_commit": data.get("source_commit"),
        "dataset_digest": sha256_text(canonical_json(semantic_payload)),
        **semantic_payload,
        "category_counts_A": dict(sorted(category_a.items())),
        "category_counts_B": dict(sorted(category_b.items())),
        "category_pair_counts_unordered": dict(sorted(unordered.items())),
        "validation": {
            "unique_k": True,
            "cross_category": True,
            "filename_k_correspondence": True,
            "all_images_readable": True,
            "all_dimensions": list(expected_size),
            "allowed_modes": sorted(allowed_modes),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = load_config()
    output = resolve_experiment_path(config["data"]["pair_manifest"])
    result = validate(config)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("dataset_digest") != result["dataset_digest"]:
            raise RuntimeError(
                "Inputs differ from the frozen pair manifest. Refusing to overwrite the freeze."
            )
        print(f"Validated 120 rows; frozen dataset digest unchanged: {result['dataset_digest']}")
        return 0
    if args.check_only:
        print(f"Validated 120 rows (check only): {result['dataset_digest']}")
        return 0
    atomic_write_json(output, result)
    print(f"Frozen pair manifest: {output}")
    print(f"Dataset digest: {result['dataset_digest']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
