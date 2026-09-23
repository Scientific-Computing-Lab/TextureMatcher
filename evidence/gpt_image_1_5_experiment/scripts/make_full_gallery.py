#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    EXPERIMENT_ROOT,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    load_config,
    load_pairs_manifest,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)
from compute_perceptual_metrics import load_regimes, logical_outputs, required_output
from PIL import Image, ImageDraw


def tile(path: Path, side: int) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        rgb = image.convert("RGB")
    rgb.thumbnail((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2))
    return canvas


def save_jpeg(path: Path, image: Image.Image) -> None:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True, progressive=True)
    atomic_write_bytes(path, buffer.getvalue())


def render_rows(
    path: Path,
    title: str,
    headers: list[str],
    rows: list[tuple[str, str, list[Path]]],
    side: int,
) -> None:
    label_width, gutter, title_height, header_height, row_gap = 230, 6, 44, 30, 28
    width = label_width + len(headers) * side + (len(headers) - 1) * gutter
    row_height = side + row_gap
    height = title_height + header_height + len(rows) * row_height
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 10), title, fill="black")
    for index, header in enumerate(headers):
        x = label_width + index * (side + gutter)
        draw.text((x + 4, title_height + 7), header, fill="black")
    for row_index, (pair_label, categories, image_paths) in enumerate(rows):
        y = title_height + header_height + row_index * row_height
        draw.text((8, y + 8), pair_label, fill="black")
        draw.text((8, y + 27), categories, fill="black")
        for column, image_path in enumerate(image_paths):
            x = label_width + column * (side + gutter)
            canvas.paste(tile(image_path, side), (x, y))
    save_jpeg(path, canvas)


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output_dir = (args.output_dir or (run_dir / "gallery")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config()
    pairs = {pair["k"]: pair for pair in load_pairs_manifest(config)["pairs"]}
    regimes = load_regimes(config)
    data_root = resolve_experiment_path(config["data"]["root"])
    outputs = logical_outputs(run_dir)
    subsets = json.loads(
        resolve_experiment_path(config["data"]["subsets"]).read_text(encoding="utf-8")
    )["subsets"]

    pages: dict[str, list[str]] = {"main": [], "s3": [], "s4": [], "s5": []}
    all_ids = sorted(pairs)
    for page_number, pair_ids in enumerate(chunks(all_ids, 10), 1):
        rows = []
        for k in pair_ids:
            pair = pairs[k]
            rows.append(
                (
                    f"{k} | {regimes[k]}",
                    f"{pair['category_A']} -> {pair['category_B']}",
                    [
                        data_root / pair["path_A"],
                        required_output(outputs, "S1", k),
                        required_output(outputs, "S2", k),
                        data_root / pair["path_B"],
                    ],
                )
            )
        path = output_dir / f"main_{page_number:02d}.jpg"
        render_rows(
            path, "S1/S2 full 120-pair comparison", ["A", "S1 / P2", "S2 / P1", "B"], rows, 192
        )
        pages["main"].append(str(path.relative_to(EXPERIMENT_ROOT)))

    s3_ids = [item["k"] for item in subsets["s3_24"]]
    for page_number, pair_ids in enumerate(chunks(s3_ids, 6), 1):
        rows = []
        for k in pair_ids:
            pair = pairs[k]
            rows.append(
                (
                    f"{k} | {regimes[k]}",
                    f"{pair['category_A']} -> {pair['category_B']}",
                    [
                        data_root / pair["path_A"],
                        required_output(outputs, "S3", k, "P0_MINIMAL"),
                        required_output(outputs, "S3", k, "P1_PERCEPTUAL_SYMMETRIC"),
                        required_output(outputs, "S3", k, "P2_SOURCE_LAYOUT"),
                        data_root / pair["path_B"],
                    ],
                )
            )
        path = output_dir / f"s3_{page_number:02d}.jpg"
        render_rows(path, "S3 prompt-dependence ablation", ["A", "P0", "P1", "P2", "B"], rows, 176)
        pages["s3"].append(str(path.relative_to(EXPERIMENT_ROOT)))

    for page_number, pair_ids in enumerate(chunks(s3_ids, 4), 1):
        rows = []
        for k in pair_ids:
            pair = pairs[k]
            rows.append(
                (
                    f"{k} | {regimes[k]}",
                    f"{pair['category_A']} -> {pair['category_B']}",
                    [
                        data_root / pair["path_A"],
                        required_output(outputs, "S4", k, order="AB", replicate=1),
                        required_output(outputs, "S4", k, order="AB", replicate=2),
                        required_output(outputs, "S4", k, order="BA", replicate=1),
                        required_output(outputs, "S4", k, order="BA", replicate=2),
                        data_root / pair["path_B"],
                    ],
                )
            )
        path = output_dir / f"s4_{page_number:02d}.jpg"
        render_rows(
            path,
            "S4 order sensitivity versus repeat variability",
            ["A", "AB-1", "AB-2", "BA-1", "BA-2", "B"],
            rows,
            156,
        )
        pages["s4"].append(str(path.relative_to(EXPERIMENT_ROOT)))

    s5_ids = [item["k"] for item in subsets["s5_12"]]
    for page_number, pair_ids in enumerate(chunks(s5_ids, 4), 1):
        rows = []
        for k in pair_ids:
            pair = pairs[k]
            frames = (
                [data_root / pair["path_A"]]
                + [
                    required_output(outputs, "S5", k, t=float(t))
                    for t in config["series"]["S5"]["t_values"]
                ]
                + [data_root / pair["path_B"]]
            )
            rows.append(
                (
                    f"{k} | {regimes[k]}",
                    f"{pair['category_A']} -> {pair['category_B']}",
                    frames,
                )
            )
        path = output_dir / f"s5_{page_number:02d}.jpg"
        render_rows(
            path,
            "S5 independently prompted path",
            [f"t={index / 10:.1f}" for index in range(11)],
            rows,
            112,
        )
        pages["s5"].append(str(path.relative_to(EXPERIMENT_ROOT)))

    index = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "run_id": run_dir.name,
        "pages": {
            section: [
                {
                    "path": page,
                    "bytes": resolve_experiment_path(page).stat().st_size,
                    "sha256": sha256_file(resolve_experiment_path(page)),
                }
                for page in section_pages
            ]
            for section, section_pages in pages.items()
        },
    }
    atomic_write_json(output_dir / "index.json", index)
    markdown = [
        "# Full GPT Image 1.5 gallery",
        "",
        "Derived review sheets only; endpoints are untouched and model outputs "
        "are not selected or beautified.",
        "",
        "| Section | Scope | Columns |",
        "|---|---:|---|",
        "| S1/S2 | 120 pairs | A, directed P2, symmetric P1, B |",
        "| S3 | 24 pairs | A, minimal P0, symmetric P1, directed P2, B |",
        "| S4 | 24 pairs | A, two A→B repeats, two B→A repeats, B |",
        "| S5 | 12 pairs | untouched t=0 and t=1 plus nine independent prompts |",
        "",
        "P1 is the natural symmetric-midpoint task; P2 is the paper-aligned "
        "directed source-layout task. GPT Image is a comparator, not ground truth. "
        "See [`../../reports/FULL_RUN_REPORT.md`](../../reports/FULL_RUN_REPORT.md) "
        "for metrics, cost, and limitations.",
        "",
    ]
    for key, heading in (
        ("main", "S1 and S2: all 120 pairs"),
        ("s3", "S3: prompt-dependence ablation"),
        ("s4", "S4: symmetry versus repeat floor"),
        ("s5", "S5: full-path controllability"),
    ):
        markdown.extend([f"## {heading}", ""])
        for page in pages[key]:
            relative = Path(page).relative_to(run_dir.relative_to(EXPERIMENT_ROOT))
            markdown.extend([f"![{heading}]({relative.as_posix()})", ""])
    atomic_write_text(run_dir / "FULL_GALLERY.md", "\n".join(markdown).rstrip() + "\n")
    print(json.dumps({key: len(value) for key, value in pages.items()}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FULL GALLERY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
