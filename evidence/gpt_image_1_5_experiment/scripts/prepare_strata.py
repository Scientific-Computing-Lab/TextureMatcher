#!/usr/bin/env python3
from __future__ import annotations

import html
import sys
from pathlib import Path

from common import (
    EXPERIMENT_ROOT,
    atomic_save_png,
    atomic_write_text,
    load_config,
    load_pairs_manifest,
    resolve_experiment_path,
)
from PIL import Image, ImageDraw


def main() -> int:
    config = load_config()
    manifest = load_pairs_manifest(config)
    annotations = resolve_experiment_path(config["data"]["strata_annotations"])
    review_dir = EXPERIMENT_ROOT / "data" / "source_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    if not annotations.exists():
        rows = ["k,regime,rationale,annotator,annotated_utc"]
        rows.extend(f"{pair['k']},,,," for pair in manifest["pairs"])
        atomic_write_text(annotations, "\n".join(rows) + "\n")

    data_root = resolve_experiment_path(config["data"]["root"])
    page_paths: list[Path] = []
    thumb = 160
    row_height = 205
    per_page = 12
    for page_index in range(0, len(manifest["pairs"]), per_page):
        chunk = manifest["pairs"][page_index : page_index + per_page]
        canvas = Image.new("RGB", (2 * thumb + 40, len(chunk) * row_height), "white")
        draw = ImageDraw.Draw(canvas)
        for row_index, pair in enumerate(chunk):
            y = row_index * row_height
            with Image.open(data_root / pair["path_A"]) as image_a:
                a = image_a.convert("RGB").resize((thumb, thumb), Image.Resampling.LANCZOS)
            with Image.open(data_root / pair["path_B"]) as image_b:
                b = image_b.convert("RGB").resize((thumb, thumb), Image.Resampling.LANCZOS)
            canvas.paste(a, (0, y + 25))
            canvas.paste(b, (thumb + 20, y + 25))
            label = f"k={pair['k']}  A:{pair['category_A']}  B:{pair['category_B']}"
            draw.text((2, y + 4), label, fill="black")
            draw.text((2, y + 188), "A", fill="black")
            draw.text((thumb + 22, y + 188), "B", fill="black")
        page_path = review_dir / f"page_{page_index // per_page + 1:02d}.png"
        atomic_save_png(page_path, canvas)
        page_paths.append(page_path)

    links = "\n".join(
        f'<li><a href="{html.escape(path.name)}">{html.escape(path.name)}</a></li>'
        for path in page_paths
    )
    page = f"""<!doctype html>
<meta charset="utf-8"><title>Source-only stratum review</title>
<h1>Source-only stratum review</h1>
<p>Review untouched A/B inputs only. Assign exactly one regime in
<code>../strata_annotations.csv</code>: ordinary, periodic, or semantic, with a
short rationale. Do not open generated-model outputs during annotation.</p>
<ul>{links}</ul>
"""
    atomic_write_text(review_dir / "index.html", page)
    print(f"Annotation template: {annotations}")
    print(f"Source-only review: {review_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
