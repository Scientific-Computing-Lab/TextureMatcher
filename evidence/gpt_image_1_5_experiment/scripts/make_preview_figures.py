#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    EXPERIMENT_ROOT,
    atomic_save_png,
    atomic_write_json,
    load_config,
    load_pairs_manifest,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)
from PIL import Image, ImageDraw, ImageFont


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def fit(path: Path, side: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def render_row(
    title: str,
    cells: list[tuple[str, Path]],
    output: Path,
    side: int,
) -> None:
    header = 72
    label_height = 38
    gutter = 8
    width = len(cells) * side + (len(cells) - 1) * gutter
    canvas = Image.new("RGB", (width, header + label_height + side), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), title, fill="black", font=font(24))
    for index, (label, path) in enumerate(cells):
        if not path.is_file():
            raise FileNotFoundError(f"Missing preview cell: {path}")
        x = index * (side + gutter)
        draw.text((x + 5, header + 6), label, fill="black", font=font(17))
        canvas.paste(fit(path, side), (x, header + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_save_png(output, canvas)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--side", type=int, default=300)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    config = load_config()
    manifest = load_pairs_manifest(config)
    pairs = {pair["k"]: pair for pair in manifest["pairs"]}
    subsets = json.loads(
        resolve_experiment_path(config["data"]["subsets"]).read_text(encoding="utf-8")
    )
    preview = subsets["subsets"]["pilot_3"]
    data_root = resolve_experiment_path(config["data"]["root"])
    output_root = run_dir / "preview_figures"
    outputs = []

    for item in preview:
        k = item["k"]
        pair = pairs[k]
        a = data_root / pair["path_A"]
        b = data_root / pair["path_B"]
        overview = output_root / "S1_S3" / f"{k}_high_quality_prompts.png"
        render_row(
            (
                f"Pair {k} — {item['regime']} — high-quality S1/S2/S3: "
                f"{pair['category_A']} → {pair['category_B']}"
            ),
            [
                ("A (untouched)", a),
                ("S3 / P0 minimal", run_dir / "images" / "S3" / "P0_MINIMAL" / f"{k}_mid_r01.png"),
                ("S2 / P1 symmetric", run_dir / "images" / "S2" / f"{k}_mid.png"),
                ("S1 / P2 directed", run_dir / "images" / "S1" / f"{k}_mid.png"),
                ("B (untouched)", b),
            ],
            overview,
            args.side,
        )
        outputs.append(overview)

        symmetry = output_root / "S4" / f"{k}_symmetry_repeats.png"
        render_row(
            f"Pair {k} — S4 P1 order symmetry versus independent-repeat floor",
            [
                ("A (untouched)", a),
                ("A→B rep 1", run_dir / "images" / "S4" / "AB" / f"{k}_mid_r01.png"),
                ("A→B rep 2", run_dir / "images" / "S4" / "AB" / f"{k}_mid_r02.png"),
                ("B→A rep 1", run_dir / "images" / "S4" / "BA" / f"{k}_mid_r01.png"),
                ("B→A rep 2", run_dir / "images" / "S4" / "BA" / f"{k}_mid_r02.png"),
                ("B (untouched)", b),
            ],
            symmetry,
            args.side,
        )
        outputs.append(symmetry)

        path = output_root / "S5" / f"{k}_path_t00_t10.png"
        path_cells = [("t=0.0 / A", a)]
        path_cells.extend(
            (
                f"t={index / 10:.1f}",
                run_dir / "images" / "S5" / f"t{index:02d}" / f"{k}_mid_r01.png",
            )
            for index in range(1, 10)
        )
        path_cells.append(("t=1.0 / B", b))
        render_row(
            f"Pair {k} — S5 independently prompted path (not chained)",
            path_cells,
            path,
            args.side,
        )
        outputs.append(path)

    index = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "display_resize": "Pillow LANCZOS fit within square; visualization only",
        "source_endpoints_untouched_before_display_resize": True,
        "files": [
            {
                "path": str(path.relative_to(EXPERIMENT_ROOT)),
                "sha256": sha256_file(path),
                "byte_count": path.stat().st_size,
            }
            for path in outputs
        ],
    }
    atomic_write_json(output_root / "index.json", index)
    print(f"Wrote {len(outputs)} expanded-preview figures under {output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
