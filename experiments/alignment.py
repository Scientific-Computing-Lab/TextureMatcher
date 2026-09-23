#!/usr/bin/env python3
"""Tier 3: renders the spatial-alignment study behind `fig:app-alignshift`
and the `\\Align*` macros (supplement) -- how sensitive each matching rule
is to *positional* misalignment between A and B, isolated from any change
in the underlying texture statistics.

Ported verbatim (same helper functions, same constants, same per-pair
seeding) from `finishing_experiments.ipynb` cell 8 ("7. SPATIAL ALIGNMENT
ISOLATED"). This table currently has NO coverage anywhere else in this
package -- unlike Table 1 / tab:eqsample / tab:generative / tab:rules /
tab:app-primitives / app:ceiling, `score_only.py` does not
check any `Align*` macro yet, even though the archive already has a cached
file for it (`data/evidence/alignment_scores.csv`). This script's output
CSV uses the exact same column schema as that cached file (`img, shift,
rule, t, dino_dev, lpips_recA, hf_ret, real_dino`), so a Tier-1 check can
be wired into score_only.py later by pointing it at either file.

The protocol: 40 DTD source images (`AlignN`), each turned into a 256x256
*seamless* texture by mirror-tiling a 128px center crop (so the underlying
texture statistics never change), reconstructed once through CNT to get a
reference R_A (`make_recon`), then paired against four cyclically-shifted
copies of itself (`shift` = 0/4/16/64 px, a numpy `roll` along the width
axis -- B is NOT a different texture, it is A itself with its positional
correspondence to A scrambled by exactly `shift` px). For each shift, one
field-linear, one Gaussian, and one soft-OT interpolation is decoded at
t = 0.25/0.5/0.75 and compared against R_A: DINO-feature deviation
(`dino_dev` = ||dino(mid) - dino(R_A)||_2, the texture-statistic-drift
metric the Align* macros come from), LPIPS to R_A, high-frequency energy
retention relative to R_A, and DINO realism.

Formula recovered for the six named macros (verified against the printed
t=0.5 pivot table in cell 8's own output, and against INVENTORY.md's phase-1
recompute, which is why this is "recovered" rather than "guessed"):
  - AlignN            = 40 (the image count)
  - AlignLinZero       = median dino_dev, rule=linear, shift=0,  t=0.5  (trivially 0: no shift, no deviation)
  - AlignLinFour       = median dino_dev, rule=linear, shift=4,  t=0.5  (defined in numbers.tex but not cited in the tex)
  - AlignLinSixteen    = median dino_dev, rule=linear, shift=16, t=0.5  (recomputed here: 15.159, paper: 15.2)
  - AlignLinMax        = median dino_dev, rule=linear, shift=64, t=0.5  (recomputed here: 23.947, paper: 23.9 -- INVENTORY's own recompute got 23.95, matching)
  - AlignGaussDev      = mean, over the four shifts, of (median dino_dev, rule=gauss, t=0.5) (recomputed here: 18.201, paper: 18.2)
  - AlignOTdev         = mean, over the four shifts, of (median dino_dev, rule=ot,    t=0.5) (recomputed here: 22.316, paper: 22.4 -- within INVENTORY's own noted range 21.95-22.48)
  - AlignCrossLo/Hi    = 16 / 64 -- these are literally the two shift amounts (px) used for the
                          "crosses over" comparison in mechanism.tex prose, not a statistic computed
                          from the data; they are NOT reproduced by this script's numeric output.
AlignGaussDev and AlignOTdev are close to shift-invariant by construction
(that is the point of the study: Gaussian/OT stay robust to misalignment
while field-linear degrades badly), which is why a single representative
number, rather than one number per shift, is reported for them. The exact
downstream aggregation across the four per-shift medians is NOT shown in
cell 8's own saved output (only the per-shift pivot table is printed there);
"plain mean of the four per-shift medians" is what best reproduces the
paper's AlignGaussDev value (to five significant figures) and reproduces
AlignOTdev to within the tolerance INVENTORY.md's own phase-1 audit already
flagged as the best it could recover. Take AlignOTdev as approximate.

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see README).

Usage:
    python experiments/alignment.py --cnt-root ../cnt-siga24 --dtd-root ../dtd/images \\
        --out RENDERED --data-root OUT --n-pairs 40
    python experiments/alignment.py --cnt-root ../cnt-siga24 --dtd-root ../dtd/images \\
        --out /tmp/smoke --data-root /tmp/smoke_scored --n-pairs 5   # smoke test
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

from texton_matching.cnt import CNTModel
from texton_matching import matching

SHIFTS = [0, 4, 16, 64]
TS = [0.25, 0.5, 0.75]
RULES = ["linear", "gauss", "ot"]  # -> field_linear, gaussian, soft_ot
RULE_MAP = {"linear": "field_linear", "gauss": "gaussian", "ot": "soft_ot"}
N_IMG_DEFAULT = 40  # AlignN


def seamless(path, size: int = 256, crop: int = 128):
    """Mirror-tile a `crop`-px center crop into a `size`x`size` seamless
    texture, so cyclic shifting never introduces a seam. Verbatim from
    finishing_experiments.ipynb cell 8's `seamless()`."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    r = size / min(w, h)
    im = im.resize((max(size, round(w * r)), max(size, round(h * r))), Image.BICUBIC)
    w, h = im.size
    c = im.crop(((w - crop) // 2, (h - crop) // 2, (w - crop) // 2 + crop, (h - crop) // 2 + crop))
    out = Image.new("RGB", (size, size))
    out.paste(c, (0, 0))
    out.paste(c.transpose(Image.FLIP_LEFT_RIGHT), (crop, 0))
    out.paste(c.transpose(Image.FLIP_TOP_BOTTOM), (0, crop))
    out.paste(c.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM), (crop, crop))
    return out


def cyclic_shift(im, s: int):
    """Cyclic horizontal roll by `s` px. Verbatim `shift()` from cell 8:
    B is A itself, positionally scrambled by exactly `s` px -- the texture
    distribution is identical for every shift; only correspondence changes."""
    import numpy as np
    from PIL import Image
    a = np.asarray(im)
    return Image.fromarray(np.roll(a, s, axis=1))


def hf_energy(pil, r0: int = 32) -> float:
    """High-frequency energy retained outside radius r0 in the 2D FFT, as a
    fraction of total energy. Verbatim `hf_energy()` from cell 8."""
    import numpy as np
    g = np.asarray(pil.convert("L"), np.float32) / 255.0
    Fm = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean()))) ** 2
    h, w = g.shape
    yy, xx = np.mgrid[:h, :w]
    rr = np.hypot(yy - h / 2, xx - w / 2)
    return float(Fm[rr > r0].sum() / (Fm.sum() + 1e-9))


def lpips_d(pil_a, pil_b, device: str = "cuda"):
    """AlexNet LPIPS between two 256x256 RGB PIL images, [-1,1] normalized.
    Not wrapped in texton_matching/ (this is the only script that needs
    LPIPS); mirrors the net='alex' choice used throughout the archive
    (see joint_basis/ceiling.csv's CeilLPIPSrec and the GPT-Image-1.5
    experiment harness's own config.yaml, both net='alex')."""
    import numpy as np
    import torch
    import lpips
    if not hasattr(lpips_d, "_model"):
        lpips_d._model = lpips.LPIPS(net="alex").to(device).eval()

    def prep(pil):
        a = np.asarray(pil.convert("RGB").resize((256, 256)), np.float32) / 127.5 - 1.0
        return torch.from_numpy(a).permute(2, 0, 1)[None].to(device)

    with torch.no_grad():
        return float(lpips_d._model(prep(pil_a), prep(pil_b)).item())


def select_images(dtd_root: Path, n_img: int, min_size: int = 256, seed: int = 7):
    """Verbatim selection from cell 8: sort every DTD jpg, permute with
    `np.random.RandomState(7)`, keep only images whose shorter side is
    already >= 256px, take the first `n_img`."""
    import numpy as np
    from PIL import Image
    files = sorted(glob.glob(str(dtd_root / "*" / "*.jpg")))
    files = [files[i] for i in np.random.RandomState(seed).permutation(len(files))]
    sel = [f for f in files if min(Image.open(f).size) >= min_size][:n_img]
    return sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True, help="path to the cloned+checked-out CNT repo (install/cnt.sh)")
    ap.add_argument("--dtd-root", required=True, help="DTD images/ dir (texton_matching.data.download_dtd)")
    ap.add_argument("--out", required=True, help="where to write alignment/alignment_scores.csv and debug images")
    ap.add_argument("--data-root", required=True, help="reserved for symmetry with the other Tier-3 scripts; this script does not call rescore.py (scoring is inline, matching cell 8)")
    ap.add_argument("--n-pairs", type=int, default=N_IMG_DEFAULT, help="AlignN; use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--eps", type=float, default=0.05, help="soft-OT epsilon (matches matching.py's canonical EPS default)")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    from PIL import Image
    import numpy as np

    ald = Path(args.out) / "alignment"
    ald.mkdir(parents=True, exist_ok=True)
    imgs_dir = ald / "imgs"

    csv_path = ald / "alignment_scores.csv"
    have = set()
    rows = []
    if csv_path.exists():
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                rows.append(row)
                have.add((int(row["img"]), int(row["shift"]), row["rule"], float(row["t"])))

    cnt = CNTModel(args.cnt_root, device=args.device)

    # DINO features + realism manifold, reused from rescore.py rather than
    # reimplemented -- these are the exact same Extractor/Manifold/realism
    # cell 8 itself was built from (the shared "canonical September setup").
    sys.path.insert(0, str(PACKAGE_ROOT))
    from rescore import Extractor, Manifold, realism, build_or_load_reference
    ext = Extractor(device=args.device)
    _, ref_dino = build_or_load_reference(Path(args.data_root), Path(args.dtd_root), ext)
    mani_dino = [Manifold(ref_dino, seed=s) for s in range(5)]

    def at128(pil):
        return pil.resize((128, 128))

    sel = select_images(Path(args.dtd_root), args.n_pairs)
    if len(sel) < args.n_pairs:
        print(f"[alignment] WARNING: only found {len(sel)}/{args.n_pairs} DTD images with shorter side >= 256px")

    for ii, f in enumerate(sel):
        if all((ii, s, r, t) in have for s in SHIFTS for r in RULES for t in TS):
            continue
        A = seamless(f)
        RA_tensor = cnt.make_recon(A)
        RA = cnt.to_pil(RA_tensor)
        fRA = ext.dino_feats([at128(RA)])[0]
        hfA = hf_energy(RA)
        a_loaded = cnt.load_image(A)

        for s in SHIFTS:
            Bs = cyclic_shift(A, s)
            b_loaded = cnt.load_image(Bs)
            d = cnt.build_pair(a_loaded, b_loaded)
            # Field computed ONCE per (image, shift) for gauss/ot, then
            # decoded at all three t values -- matches cell 8's structure
            # exactly (and avoids re-running Sinkhorn 3x for no reason).
            fds = {
                "gauss": matching.field(cnt, d, "gaussian", ii),
                "ot": matching.field(cnt, d, "soft_ot", ii, eps=args.eps),
            }
            for r in RULES:
                for t in TS:
                    if (ii, s, r, t) in have:
                        continue
                    if r == "linear":
                        decoded = cnt.field_linear(d, t)
                    else:
                        fd = fds[r]
                        Z = matching.zt(fd, t)
                        decoded = cnt.decode_field(d, Z, fd["L"], fd["H"], fd["W"], fd["C"])
                    pil = cnt.to_pil(decoded)

                    if ii < 3:
                        imgs_dir.mkdir(parents=True, exist_ok=True)
                        pil.save(imgs_dir / f"img{ii}_s{s}_{r}_t{t}.png")
                        recA_path = imgs_dir / f"img{ii}_recA.png"
                        if not recA_path.exists():
                            RA.save(recA_path)
                        Bs.save(imgs_dir / f"img{ii}_s{s}_B.png")

                    fd_dino = ext.dino_feats([at128(pil)])[0]
                    rows.append(dict(
                        img=ii, shift=s, rule=r, t=t,
                        dino_dev=float(np.linalg.norm(fd_dino - fRA)),
                        lpips_recA=lpips_d(pil, RA, device=args.device),
                        hf_ret=hf_energy(pil) / (hfA + 1e-9),
                        real_dino=float(realism(fd_dino[None], mani_dino)[0]),
                    ))
                    have.add((ii, s, r, t))

        with open(csv_path, "w", newline="") as fcsv:
            w = csv.DictWriter(fcsv, fieldnames=["img", "shift", "rule", "t", "dino_dev", "lpips_recA", "hf_ret", "real_dino"])
            w.writeheader()
            w.writerows(rows)
        print(f"[alignment] {ii + 1}/{len(sel)} images done -> {csv_path}")

    print("[alignment] rendering + scoring done.")
    print(f"[alignment] {csv_path} matches data/evidence/alignment_scores.csv's column schema exactly;")
    print("[alignment] see this script's docstring for the exact AlignN/AlignLin*/AlignGaussDev/AlignOTdev formulas.")


if __name__ == "__main__":
    main()
