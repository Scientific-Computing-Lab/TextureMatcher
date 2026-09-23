"""DTD download and the stratified pair manifests used by every experiment.

DTD source: the official Oxford VGG release, exactly what finish_day.ipynb
and exact_finish.ipynb fall back to when their Drive-cached copy is
missing:
    https://www.robots.ox.ac.uk/~vgg/data/dtd/download/dtd-r1.0.1.tar.gz
5,640 images, 47 categories.

Pair manifests: ported from tm_scale1000_headtohead.ipynb "PHASE 1, CELL 3"
(the 1,000-pair sampler that both the CNT and Texture Mixer sides read) and
`subset of dtd.ipynb` (the 120-pair stratified subset used for the
generative-comparison and timing tables). The 200-pair matching-rule
ablation is simply the first 200 entries of the 1,000-pair manifest, in
manifest order (matching_ablation.ipynb: `N_PAIRS=200` = first 200 of
tm_scale1000/manifest.json) -- there is no separate sampler for it.

No torch/CNT dependency; this module only needs the standard library plus
Pillow for the 128px endpoint copies.
"""
from __future__ import annotations

import itertools
import json
import os
import random
import tarfile
import urllib.request
from pathlib import Path

from PIL import Image

DTD_URL = "https://www.robots.ox.ac.uk/~vgg/data/dtd/download/dtd-r1.0.1.tar.gz"


def download_dtd(dest_dir: str | Path, force: bool = False) -> Path:
    """Downloads and extracts DTD; returns the path to its `images/` dir."""
    dest_dir = Path(dest_dir)
    images_dir = dest_dir / "images"
    if images_dir.exists() and not force and len(list(images_dir.glob("*/*.jpg"))) >= 5000:
        print(f"[texton_matching.data] DTD already present at {images_dir}")
        return images_dir

    dest_dir.mkdir(parents=True, exist_ok=True)
    tar_path = dest_dir / "dtd-r1.0.1.tar.gz"
    if not tar_path.exists():
        print(f"[texton_matching.data] downloading DTD from {DTD_URL}")
        urllib.request.urlretrieve(DTD_URL, tar_path)

    print(f"[texton_matching.data] extracting {tar_path}")
    with tarfile.open(tar_path) as tf:
        # the archive's top-level dir is "dtd/", containing "images/"
        tf.extractall(dest_dir)
    extracted = dest_dir / "dtd" / "images"
    if extracted.exists() and not images_dir.exists():
        extracted.rename(images_dir)
    if not images_dir.exists():
        raise RuntimeError(f"expected {images_dir} to exist after extracting DTD; check the archive layout")
    n = len(list(images_dir.glob("*/*.jpg")))
    print(f"[texton_matching.data] DTD ready: {n} images")
    return images_dir


def build_manifest_1000(dtd_images_dir: str | Path, out_dir: str | Path, seed: int = 2026, n_pairs: int = 1000) -> Path:
    """Stratified cross-category pair sampler: uniform over unordered
    category pairs, then one file from each side. Deterministic in `seed`.
    Ported verbatim from tm_scale1000_headtohead.ipynb PHASE 1 CELL 3.

    Writes manifest.json (`{seed, n, pairs: [{k, cA, fA, cB, fB}, ...]}`)
    and 128px copies of every A/B endpoint (Texture Mixer's native
    resolution; CNT upsamples these to 256px on load) into out_dir.
    """
    dtd_images_dir = Path(dtd_images_dir)
    out_dir = Path(out_dir)
    for d in ("A", "B"):
        (out_dir / d).mkdir(parents=True, exist_ok=True)

    cats = sorted(c for c in os.listdir(dtd_images_dir) if (dtd_images_dir / c).is_dir())
    rng = random.Random(seed)
    cat_pairs = list(itertools.combinations(cats, 2))
    manifest = []
    for k in range(n_pairs):
        cA, cB = rng.choice(cat_pairs)
        fA = rng.choice(sorted(os.listdir(dtd_images_dir / cA)))
        fB = rng.choice(sorted(os.listdir(dtd_images_dir / cB)))
        manifest.append(dict(k=k, cA=cA, fA=fA, cB=cB, fB=fB))
        Image.open(dtd_images_dir / cA / fA).convert("RGB").resize((128, 128)).save(out_dir / "A" / f"{k:04d}.png")
        Image.open(dtd_images_dir / cB / fB).convert("RGB").resize((128, 128)).save(out_dir / "B" / f"{k:04d}.png")

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(dict(seed=seed, n=n_pairs, pairs=manifest)))
    print(f"[texton_matching.data] {n_pairs} pairs over {len(cat_pairs)} category pairs -> {manifest_path}")
    return manifest_path


def build_manifest_120(dtd_images_dir: str | Path, manifest_1000_path: str | Path, out_dir: str | Path,
                        seed: int = 2026, n_pairs: int = 120) -> Path:
    """Stratified-by-category-A subset of the 1,000-pair manifest, used for
    the generative-comparison and timing (120-pair) tables. Ported from
    `subset of dtd.ipynb` cell 2 (the kept v2 run): quotas
    round(120 * n_c / 1000) per source category, `random.Random(2026)`.
    """
    manifest_1000 = json.loads(Path(manifest_1000_path).read_text())
    pairs = manifest_1000["pairs"]
    out_dir = Path(out_dir)
    for d in ("A", "B"):
        (out_dir / d).mkdir(parents=True, exist_ok=True)

    from collections import Counter, defaultdict
    by_cat = defaultdict(list)
    for p in pairs:
        by_cat[p["cA"]].append(p)
    counts = Counter(p["cA"] for p in pairs)
    rng = random.Random(seed)
    chosen = []
    for cat, n_c in counts.items():
        quota = round(n_pairs * n_c / len(pairs))
        chosen.extend(rng.sample(by_cat[cat], min(quota, len(by_cat[cat]))))
    chosen = chosen[:n_pairs]

    rows = []
    for p in chosen:
        k = p["k"]
        Image.open(dtd_images_dir / p["cA"] / p["fA"]).convert("RGB").resize((256, 256)).save(out_dir / "A" / f"{k:04d}_A.png")
        Image.open(dtd_images_dir / p["cB"] / p["fB"]).convert("RGB").resize((256, 256)).save(out_dir / "B" / f"{k:04d}_B.png")
        rows.append(dict(k=k, category_A=p["cA"], category_B=p["cB"], file_A=p["fA"], file_B=p["fB"]))

    import csv
    pairs_csv = out_dir / "pairs.csv"
    with open(pairs_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["k", "category_A", "category_B", "file_A", "file_B"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["k"]))
    print(f"[texton_matching.data] {len(rows)} pairs, {len(counts)} categories represented -> {pairs_csv}")
    return pairs_csv


def matched_200_pairs(manifest_1000_path: str | Path) -> list[dict]:
    """The 200-pair matching-rule ablation is just the first 200 entries of
    the 1,000-pair manifest, in manifest order (matching_ablation.ipynb)."""
    manifest_1000 = json.loads(Path(manifest_1000_path).read_text())
    return manifest_1000["pairs"][:200]


def load128(cat: str, fn: str, dtd_root: str | Path):
    """Ported verbatim from tm_scale1000_headtohead.ipynb (the notebook
    that built the paper's 120-pair demo subset in the first place):
    resize to 128x128 and return a PIL Image; CNT's own loader upsamples
    to 256px on read, Texture Mixer consumes 128px natively."""
    return Image.open(f"{dtd_root}/{cat}/{fn}").convert("RGB").resize((128, 128))


def prepare_demo_endpoints(package_root: str | Path, out_dir: str | Path,
                            dtd_images_dir: str | Path | None = None) -> list[dict]:
    """Builds `out_dir/A/{k}.png` and `out_dir/B/{k}.png` for the paper's 5
    demo pairs (package_root/evidence/pairs_demo.csv: k=0006/0009/0017/
    0022/0053), and returns the 5 rows as a list of dicts
    (k, cA, fA, cB, fB).

    THIS IS THE SINGLE SOURCE OF TRUTH both colab/reproduce.ipynb (CNT) and
    colab/reproduce_tm.ipynb (Texture Mixer) call, so the two notebooks
    always render from byte-identical endpoint images at the same path --
    an earlier version had each notebook build its own copies at different
    paths (CNT at out_dir/A|B, Texture Mixer at out_dir/tm_scale1000/A|B),
    which meant a cross-check expecting one shared layout found nothing at
    the path it looked at, even though the Texture Mixer side had in fact
    rendered.

    Tries to reconstruct from a fresh, official DTD download first (via
    `load128`, matching the paper's own preprocessing exactly); falls back
    to the 128px PNGs shipped at package_root/evidence/demo_pairs/ (the
    same 5 pairs, produced the same way while building this package) if
    that reconstruction fails for any reason -- a missing dtd_images_dir,
    a network error, or the source files not being where expected.
    """
    package_root = Path(package_root)
    out_dir = Path(out_dir)
    out_a, out_b = out_dir / "A", out_dir / "B"
    out_a.mkdir(parents=True, exist_ok=True)
    out_b.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    demo = pd.read_csv(package_root / "evidence" / "pairs_demo.csv", dtype={"k": str})
    rows = [dict(row) for _, row in demo.iterrows()]

    fallback_dir = package_root / "evidence" / "demo_pairs"
    used_fallback = []
    for row in rows:
        k = row["k"]
        a_path, b_path = out_a / f"{k}.png", out_b / f"{k}.png"
        if a_path.exists() and b_path.exists():
            continue  # already built (e.g. by an earlier cell, or a rerun after a restart)
        try:
            if dtd_images_dir is None:
                raise FileNotFoundError("no dtd_images_dir given")
            load128(row["cA"], row["fA"], dtd_images_dir).save(a_path)
            load128(row["cB"], row["fB"], dtd_images_dir).save(b_path)
        except Exception as e:
            used_fallback.append(k)
            Image.open(fallback_dir / f"{k}_A.png").convert("RGB").save(a_path)
            Image.open(fallback_dir / f"{k}_B.png").convert("RGB").save(b_path)

    if used_fallback:
        print(f"[texton_matching.data] DTD reconstruction unavailable for pair(s) {used_fallback}; "
              f"used the shipped evidence/demo_pairs/ PNGs instead.")
    print(f"[texton_matching.data] endpoints ready at {out_a} / {out_b} for {[r['k'] for r in rows]}")
    return rows
