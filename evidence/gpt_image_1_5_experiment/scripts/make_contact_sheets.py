#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import (
    EXPERIMENT_ROOT,
    atomic_save_png,
    atomic_write_json,
    load_config,
    load_pairs_manifest,
    read_jsonl,
    resolve_experiment_path,
)
from PIL import Image, ImageDraw


def fit(image: Image.Image, side: int) -> Image.Image:
    copy = image.convert("RGB")
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (side, side), "white")
    x = (side - copy.width) // 2
    y = (side - copy.height) // 2
    canvas.paste(copy, (x, y))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--side", type=int, default=384)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "manifest.jsonl"
    records = [
        record
        for record in read_jsonl(manifest_path)
        if record.get("status") in {"success", "skipped_existing"}
    ]
    if not records:
        raise ValueError(f"No successful records in {manifest_path}")
    config = load_config()
    pairs = {pair["k"]: pair for pair in load_pairs_manifest(config)["pairs"]}
    data_root = resolve_experiment_path(config["data"]["root"])
    output_root = run_dir / "contact_sheets"
    paths = []
    for record in records:
        pair = pairs[record["k"]]
        with Image.open(data_root / pair["path_A"]) as a_image:
            a = fit(a_image, args.side)
        with Image.open(resolve_experiment_path(record["output_path"])) as m_image:
            m = fit(m_image, args.side)
        with Image.open(data_root / pair["path_B"]) as b_image:
            b = fit(b_image, args.side)
        header = 58
        footer = 28
        gutter = 8
        width = args.side * 3 + gutter * 2
        canvas = Image.new("RGB", (width, header + args.side + footer), "white")
        draw = ImageDraw.Draw(canvas)
        title = (
            f"pair {record['k']} | {record['prompt_id']} | "
            f"{record['series_id']} | {record['quality']}"
        )
        draw.text((8, 8), title, fill="black")
        draw.text((8, 30), f"A: {pair['category_A']}    B: {pair['category_B']}", fill="black")
        for index, (label, image) in enumerate(
            (("A (untouched)", a), ("M", m), ("B (untouched)", b))
        ):
            x = index * (args.side + gutter)
            canvas.paste(image, (x, header))
            draw.text((x + 4, header + args.side + 6), label, fill="black")
        coordinate = f"_t{record['t']:.2f}" if record.get("t") is not None else ""
        filename = (
            f"{record['k']}_{record['input_order']}{coordinate}_r{record['replicate']:02d}.png"
        )
        output = output_root / record["series_id"] / record["prompt_id"] / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_png(output, canvas)
        paths.append(str(output.relative_to(EXPERIMENT_ROOT)))
    index_path = output_root / "index.json"
    atomic_write_json(index_path, paths)
    print(f"Wrote {len(paths)} offline A-M-B contact sheets under {output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
