#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from common import atomic_write_text, sha256_file, utc_now
from PIL import Image


def diagnose_image(path: Path, expected_size: tuple[int, int] = (1024, 1024)) -> dict:
    result = {
        "path": str(path),
        "sha256": None,
        "byte_count": None,
        "format": None,
        "dimensions": None,
        "mode": None,
        "decodable": False,
        "exact_dimensions": False,
        "blank": None,
        "near_uniform": None,
        "suspicious_border": None,
        "suspicious_panel_layout": None,
        "flags": [],
    }
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            result["format"] = image.format
            result["dimensions"] = list(image.size)
            result["mode"] = image.mode
            rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
        result["decodable"] = True
        result["exact_dimensions"] = tuple(result["dimensions"]) == expected_size
        result["sha256"] = sha256_file(path)
        result["byte_count"] = path.stat().st_size

        gray = rgb.mean(axis=2)
        std = float(gray.std())
        dynamic_range = float(np.percentile(gray, 99) - np.percentile(gray, 1))
        result["grayscale_std"] = std
        result["p01_p99_range"] = dynamic_range
        result["blank"] = std < 1.0
        result["near_uniform"] = std < 3.0 or dynamic_range < 8.0

        height, width = gray.shape
        band = max(4, min(height, width) // 32)
        edge_pixels = np.concatenate(
            [
                gray[:band].ravel(),
                gray[-band:].ravel(),
                gray[:, :band].ravel(),
                gray[:, -band:].ravel(),
            ]
        )
        inner = gray[band:-band, band:-band]
        edge_inner_mean_gap = abs(float(edge_pixels.mean()) - float(inner.mean()))
        edge_std_ratio = float(edge_pixels.std() / max(inner.std(), 1e-6))
        result["edge_inner_mean_gap"] = edge_inner_mean_gap
        result["edge_inner_std_ratio"] = edge_std_ratio
        result["suspicious_border"] = edge_inner_mean_gap > 45 and edge_std_ratio < 0.35

        vertical = np.abs(np.diff(gray, axis=1)).mean(axis=0)
        horizontal = np.abs(np.diff(gray, axis=0)).mean(axis=1)
        v_mid = vertical[width // 3 : 2 * width // 3]
        h_mid = horizontal[height // 3 : 2 * height // 3]
        v_ratio = float(v_mid.max() / max(np.median(vertical), 1e-6))
        h_ratio = float(h_mid.max() / max(np.median(horizontal), 1e-6))
        result["central_vertical_seam_ratio"] = v_ratio
        result["central_horizontal_seam_ratio"] = h_ratio
        result["suspicious_panel_layout"] = bool(
            (v_ratio > 10 and v_mid.max() > 18) or (h_ratio > 10 and h_mid.max() > 18)
        )

        if result["format"] != "PNG":
            result["flags"].append("not_png")
        if not result["exact_dimensions"]:
            result["flags"].append("wrong_dimensions")
        for key in ("blank", "near_uniform", "suspicious_border", "suspicious_panel_layout"):
            if result[key]:
                result["flags"].append(key)
        if result["byte_count"] < 4096:
            result["flags"].append("implausibly_small_file")
    except Exception as exc:
        result["flags"].append("unreadable")
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = []
    for path in args.paths:
        files.extend(sorted(path.rglob("*.png")) if path.is_dir() else [path])
    diagnostics = [diagnose_image(path) for path in files]
    by_hash: dict[str, list[str]] = defaultdict(list)
    for record in diagnostics:
        if record["sha256"]:
            by_hash[record["sha256"]].append(record["path"])
    duplicates = {digest: paths for digest, paths in by_hash.items() if len(paths) > 1}
    summary = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "image_count": len(diagnostics),
        "flagged_count": sum(bool(record["flags"]) for record in diagnostics),
        "duplicate_groups": duplicates,
    }
    payload = [json.dumps({"type": "summary", **summary}, sort_keys=True)]
    payload.extend(
        json.dumps({"type": "image", **record}, sort_keys=True) for record in diagnostics
    )
    atomic_write_text(args.output, "\n".join(payload) + "\n")
    print(json.dumps(summary, indent=2))
    return 1 if summary["flagged_count"] or duplicates else 0


if __name__ == "__main__":
    sys.exit(main())
