#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from common import (
    atomic_write_json,
    atomic_write_text,
    load_config,
    load_pairs_manifest,
    read_jsonl,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)
from PIL import Image


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, buffer.getvalue())


def load_regimes(config: dict[str, Any]) -> dict[str, str]:
    path = resolve_experiment_path(config["data"]["strata_annotations"])
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    regimes = {row["k"]: row["regime"] for row in rows}
    if len(regimes) != 120:
        raise ValueError(f"Expected 120 frozen regime labels, got {len(regimes)}")
    return regimes


def logical_outputs(
    run_dir: Path,
) -> dict[tuple[str, str, str, str, int, float | None], Path]:
    records = read_jsonl(run_dir / "manifest.jsonl")
    terminal = {"success", "skipped_existing"}
    outputs: dict[tuple[str, str, str, str, int, float | None], Path] = {}
    for record in records:
        if record.get("status") not in terminal:
            continue
        primary = resolve_experiment_path(record["output_path"])
        if not primary.is_file() or sha256_file(primary) != record["output_sha256"]:
            raise RuntimeError(f"Invalid manifest output for {record['request_signature']}")
        key = (
            record["series_id"],
            record["k"],
            record["prompt_id"],
            record["input_order"],
            int(record["replicate"]),
            record.get("t"),
        )
        outputs[key] = primary
        for alias in record.get("materialized_aliases", []):
            path = resolve_experiment_path(alias["output_path"])
            if not path.is_file() or sha256_file(path) != alias["sha256"]:
                raise RuntimeError(f"Invalid alias output for {record['request_signature']}")
            alias_key = (
                alias["series_id"],
                record["k"],
                record["prompt_id"],
                record["input_order"],
                int(record["replicate"]),
                record.get("t"),
            )
            outputs[alias_key] = path
    return outputs


def required_output(
    outputs: dict[tuple[str, str, str, str, int, float | None], Path],
    series: str,
    k: str,
    prompt_id: str | None = None,
    order: str = "AB",
    replicate: int = 1,
    t: float | None = None,
) -> Path:
    matches = [
        path
        for key, path in outputs.items()
        if key[0] == series
        and key[1] == k
        and (prompt_id is None or key[2] == prompt_id)
        and key[3] == order
        and key[4] == replicate
        and key[5] == t
    ]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one completed logical output for "
            f"{(series, k, prompt_id, order, replicate, t)}, got {len(matches)}"
        )
    return matches[0]


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return image.convert("RGB")


def dino_embeddings(
    paths: list[Path], model_id: str, revision: str, batch_size: int, device: str
) -> tuple[dict[Path, np.ndarray], dict[str, Any]]:
    import torch
    import transformers
    from transformers import AutoImageProcessor, AutoModel

    processor = AutoImageProcessor.from_pretrained(model_id, revision=revision, use_fast=False)
    model = AutoModel.from_pretrained(model_id, revision=revision).eval().to(device)
    embeddings: dict[Path, np.ndarray] = {}
    with torch.inference_mode():
        for start in range(0, len(paths), batch_size):
            batch_paths = paths[start : start + batch_size]
            inputs = processor(images=[load_rgb(path) for path in batch_paths], return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            features = model(**inputs).last_hidden_state[:, 0]
            features = torch.nn.functional.normalize(features.float(), dim=1)
            for path, vector in zip(batch_paths, features.cpu().numpy(), strict=True):
                embeddings[path] = vector
    metadata = {
        "model": model_id,
        "requested_revision": revision,
        "resolved_revision": getattr(model.config, "_commit_hash", None),
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
    }
    return embeddings, metadata


def lpips_tensors(paths: list[Path], size: tuple[int, int]) -> dict[Path, Any]:
    from torchvision.transforms.functional import pil_to_tensor

    tensors = {}
    for path in paths:
        image = load_rgb(path).resize(size, Image.Resampling.BICUBIC)
        tensors[path] = pil_to_tensor(image).float().div(127.5).sub(1.0)
    return tensors


def main() -> int:
    started_utc = utc_now()
    start_clock = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    import lpips
    import torch

    config = load_config()
    metric_config = config["evaluation"]["perceptual_metrics"]
    device = (
        ("cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else args.device
    )
    run_dir = args.run_dir.resolve()
    output_dir = (args.output_dir or (run_dir / "evaluation" / "perceptual")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = logical_outputs(run_dir)
    pairs = {pair["k"]: pair for pair in load_pairs_manifest(config)["pairs"]}
    regimes = load_regimes(config)
    data_root = resolve_experiment_path(config["data"]["root"])

    endpoints = {
        (k, endpoint): data_root / pair[f"path_{endpoint}"]
        for k, pair in pairs.items()
        for endpoint in ("A", "B")
    }
    paths: set[Path] = set(endpoints.values())
    for k in pairs:
        paths.add(required_output(outputs, "S1", k))
        paths.add(required_output(outputs, "S2", k))
    s3_ids = [
        item["k"]
        for item in json.loads(
            resolve_experiment_path(config["data"]["subsets"]).read_text(encoding="utf-8")
        )["subsets"]["s3_24"]
    ]
    s5_ids = [
        item["k"]
        for item in json.loads(
            resolve_experiment_path(config["data"]["subsets"]).read_text(encoding="utf-8")
        )["subsets"]["s5_12"]
    ]
    for k in s3_ids:
        for prompt_id in ("P0_MINIMAL", "P1_PERCEPTUAL_SYMMETRIC", "P2_SOURCE_LAYOUT"):
            paths.add(required_output(outputs, "S3", k, prompt_id=prompt_id))
    for k in s3_ids:
        for order in ("AB", "BA"):
            for replicate in (1, 2):
                paths.add(required_output(outputs, "S4", k, order=order, replicate=replicate))
    for k in s5_ids:
        for t in config["series"]["S5"]["t_values"]:
            paths.add(required_output(outputs, "S5", k, t=float(t)))
    ordered_paths = sorted(paths, key=str)

    dino, dino_metadata = dino_embeddings(
        ordered_paths,
        metric_config["dinov2_model"],
        metric_config["dinov2_revision"],
        args.batch_size,
        device,
    )
    lpips_size = tuple(metric_config["lpips_input_size"])
    lpips_inputs = lpips_tensors(ordered_paths, lpips_size)
    lpips_model = (
        lpips.LPIPS(net=metric_config["lpips_network"], version=metric_config["lpips_version"])
        .eval()
        .to(device)
    )
    lpips_checkpoint = (
        Path(lpips.__file__).resolve().parent
        / "weights"
        / f"v{metric_config['lpips_version'].removeprefix('v')}"
        / f"{metric_config['lpips_network']}.pth"
    )
    distance_cache: dict[tuple[str, Path, Path], float] = {}

    def distance(space: str, first: Path, second: Path) -> float:
        ordered = tuple(sorted((first, second), key=str))
        key = (space, ordered[0], ordered[1])
        if key in distance_cache:
            return distance_cache[key]
        if space == "DINOv2":
            value = float(1.0 - np.dot(dino[first], dino[second]))
        elif space == "LPIPS":
            with torch.inference_mode():
                value = float(
                    lpips_model(
                        lpips_inputs[first].unsqueeze(0).to(device),
                        lpips_inputs[second].unsqueeze(0).to(device),
                    ).item()
                )
        else:
            raise ValueError(space)
        distance_cache[key] = value
        return value

    endpoint_rows = []
    for series, method in (("S1", "GPT_P2"), ("S2", "GPT_P1")):
        for k in sorted(pairs):
            midpoint = required_output(outputs, series, k)
            for space in ("DINOv2", "LPIPS"):
                d_a = distance(space, midpoint, endpoints[(k, "A")])
                d_b = distance(space, midpoint, endpoints[(k, "B")])
                coordinate = d_a / max(d_a + d_b, 1e-12)
                endpoint_rows.append(
                    {
                        "k": k,
                        "stratum": regimes[k],
                        "method": method,
                        "space": space,
                        "d_to_A": d_a,
                        "d_to_B": d_b,
                        "midpoint_coordinate": coordinate,
                        "midpoint_balance": abs(coordinate - 0.5),
                    }
                )
    for k in s3_ids:
        midpoint = required_output(outputs, "S3", k, prompt_id="P0_MINIMAL")
        for space in ("DINOv2", "LPIPS"):
            d_a = distance(space, midpoint, endpoints[(k, "A")])
            d_b = distance(space, midpoint, endpoints[(k, "B")])
            coordinate = d_a / max(d_a + d_b, 1e-12)
            endpoint_rows.append(
                {
                    "k": k,
                    "stratum": regimes[k],
                    "method": "GPT_P0",
                    "space": space,
                    "d_to_A": d_a,
                    "d_to_B": d_b,
                    "midpoint_coordinate": coordinate,
                    "midpoint_balance": abs(coordinate - 0.5),
                }
            )

    prompt_rows = []
    for k in s3_ids:
        p0 = required_output(outputs, "S3", k, prompt_id="P0_MINIMAL")
        p1 = required_output(outputs, "S3", k, prompt_id="P1_PERCEPTUAL_SYMMETRIC")
        p2 = required_output(outputs, "S3", k, prompt_id="P2_SOURCE_LAYOUT")
        for space in ("DINOv2", "LPIPS"):
            prompt_rows.append(
                {
                    "k": k,
                    "stratum": regimes[k],
                    "space": space,
                    "d_P0_P1": distance(space, p0, p1),
                    "d_P0_P2": distance(space, p0, p2),
                    "d_P1_P2": distance(space, p1, p2),
                }
            )

    symmetry_rows = []
    for k in s3_ids:
        ab1 = required_output(outputs, "S4", k, order="AB", replicate=1)
        ab2 = required_output(outputs, "S4", k, order="AB", replicate=2)
        ba1 = required_output(outputs, "S4", k, order="BA", replicate=1)
        ba2 = required_output(outputs, "S4", k, order="BA", replicate=2)
        for space in ("DINOv2", "LPIPS"):
            between = np.mean([distance(space, ab, ba) for ab in (ab1, ab2) for ba in (ba1, ba2)])
            symmetry_rows.append(
                {
                    "k": k,
                    "stratum": regimes[k],
                    "space": space,
                    "d_between_orders": float(between),
                    "d_repeat_AB": distance(space, ab1, ab2),
                    "d_repeat_BA": distance(space, ba1, ba2),
                }
            )

    path_rows = []
    for k in s5_ids:
        frames = (
            [endpoints[(k, "A")]]
            + [
                required_output(outputs, "S5", k, t=float(t))
                for t in config["series"]["S5"]["t_values"]
            ]
            + [endpoints[(k, "B")]]
        )
        coordinates = [index / 10 for index in range(11)]
        for space in ("DINOv2", "LPIPS"):
            for index, (t, frame) in enumerate(zip(coordinates, frames, strict=True)):
                path_rows.append(
                    {
                        "k": k,
                        "space": space,
                        "t": t,
                        "d_to_A": distance(space, frame, frames[0]),
                        "d_to_B": distance(space, frame, frames[-1]),
                        "step_from_previous": 0.0
                        if index == 0
                        else distance(space, frames[index - 1], frame),
                    }
                )

    write_csv(
        output_dir / "endpoint_metrics.csv",
        [
            "k",
            "stratum",
            "method",
            "space",
            "d_to_A",
            "d_to_B",
            "midpoint_coordinate",
            "midpoint_balance",
        ],
        endpoint_rows,
    )
    paired_rows = [
        {
            "k": row["k"],
            "stratum": row["stratum"],
            "method": row["method"],
            "metric": f"{row['space']}_midpoint_balance",
            "value": row["midpoint_balance"],
        }
        for row in endpoint_rows
    ]
    write_csv(
        output_dir / "paired_metrics.csv",
        ["k", "stratum", "method", "metric", "value"],
        paired_rows,
    )
    write_csv(
        output_dir / "prompt_ablation_distances.csv",
        ["k", "stratum", "space", "d_P0_P1", "d_P0_P2", "d_P1_P2"],
        prompt_rows,
    )
    write_csv(
        output_dir / "symmetry_distances.csv",
        ["k", "stratum", "space", "d_between_orders", "d_repeat_AB", "d_repeat_BA"],
        symmetry_rows,
    )
    write_csv(
        output_dir / "path_distances.csv",
        ["k", "space", "t", "d_to_A", "d_to_B", "step_from_previous"],
        path_rows,
    )
    metadata = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "started_utc": started_utc,
        "elapsed_seconds": time.perf_counter() - start_clock,
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device.startswith("cuda") else None,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pillow_version": Image.__version__,
        "dino": dino_metadata,
        "lpips": {
            "package_version": getattr(lpips, "__version__", "0.1.4"),
            "network": metric_config["lpips_network"],
            "version": metric_config["lpips_version"],
            "input_size": list(lpips_size),
            "resampling": metric_config["lpips_resampling"],
            "checkpoint_sha256": sha256_file(lpips_checkpoint)
            if lpips_checkpoint.is_file()
            else None,
        },
        "counts": {
            "unique_images": len(ordered_paths),
            "endpoint_rows": len(endpoint_rows),
            "paired_rows": len(paired_rows),
            "prompt_ablation_rows": len(prompt_rows),
            "symmetry_rows": len(symmetry_rows),
            "path_rows": len(path_rows),
            "unique_distances": len(distance_cache),
        },
    }
    atomic_write_json(output_dir / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PERCEPTUAL METRICS FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
