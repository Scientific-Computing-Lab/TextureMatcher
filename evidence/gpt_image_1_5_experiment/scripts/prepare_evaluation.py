#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    atomic_save_png,
    atomic_write_json,
    load_config,
    load_pairs_manifest,
    sha256_file,
    utc_now,
)
from PIL import Image

RESAMPLING = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


def parse_method(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("method must be NAME=PATH")
    name, path = value.split("=", 1)
    return name, Path(path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", type=parse_method, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    resize_method = config["evaluation"]["resize_method"]
    if resize_method not in RESAMPLING:
        raise RuntimeError(
            "Evaluation resize method is unresolved. Recover the paper evaluator or make "
            "an explicit prospective choice in config.yaml before deriving metric inputs."
        )
    pairs = load_pairs_manifest(config)["pairs"]
    expected = {pair["k"] for pair in pairs}
    size = tuple(config["evaluation"]["output_size"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    methods = dict(args.method)
    joined = []
    for name, directory in methods.items():
        found = {path.stem.removesuffix("_mid"): path for path in directory.glob("*_mid.png")}
        missing = sorted(expected - set(found))
        extra = sorted(set(found) - expected)
        if missing or extra:
            raise ValueError(
                f"{name}: missing {missing[:10]} ({len(missing)}); "
                f"extra {extra[:10]} ({len(extra)})"
            )
        for pair in pairs:
            source = found[pair["k"]]
            with Image.open(source) as image:
                image.load()
                rgb = image.convert("RGB")
                derived = rgb.resize(size, RESAMPLING[resize_method])
            output = args.output_dir / name / f"{pair['k']}_mid.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            atomic_save_png(output, derived)
            joined.append(
                {
                    "k": pair["k"],
                    "method": name,
                    "source_path": str(source),
                    "source_sha256": sha256_file(source),
                    "derived_path": str(output),
                    "derived_sha256": sha256_file(output),
                    "transform": {"mode": "RGB", "size": list(size), "resampling": resize_method},
                }
            )
    if not args.reference_manifest.is_file():
        raise FileNotFoundError("Fixed DTD reference manifest is missing")
    references = json.loads(args.reference_manifest.read_text(encoding="utf-8"))
    if not references:
        raise ValueError("Reference manifest is empty")
    result = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "pair_count": len(pairs),
        "methods": sorted(methods),
        "resize": {"size": list(size), "resampling": resize_method, "mode": "RGB"},
        "reference_manifest": str(args.reference_manifest.resolve()),
        "reference_manifest_sha256": sha256_file(args.reference_manifest),
        "items": joined,
    }
    atomic_write_json(args.output_dir / "evaluation_inputs_manifest.json", result)
    print(f"Prepared {len(joined)} method images on the same {len(pairs)} pair IDs")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"EVALUATION PREP FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
