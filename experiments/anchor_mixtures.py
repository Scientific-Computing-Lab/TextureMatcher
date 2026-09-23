#!/usr/bin/env python3
"""Tier 3: renders the k-way "anchor mixture" study behind `fig:app-mixtures`
/ `fig:app-mixtures2` / `fig:app-palette` and the `AnchorChangeA` (46%) /
`AnchorChangeB` (38%) / "14%/32% [OT-sym] re-run noise" prose in the
supplement's anchor-mixtures subsection.

Ported from notebooks_raw/dtd/images/anchor_mixtures_and_stability.ipynb:
  - cell 13 ("BARYCENTRE FIGURE") defines the three k-way barycentre
    strategies this script ports verbatim: `bary_anchored` (asymmetric,
    expressed on one source's support), `bary_sym` (average the anchored
    solutions over every anchor choice, in image space), and `bary_linear`
    (plain weighted blend of style maps, the control).
  - cell 14 ("HEADLINE FIGURE") is the one that actually prints
    `AnchorChangeA`/`AnchorChangeB` and the re-run-noise floors: it defines
    the two source quadruples (`QUADS` below, verbatim) and the exact
    formula --
      anchor_dependence_pct = 100 * mean_pairwise_DINOv2_dist(4 anchored
                               barycentres) / mean_pairwise_DINOv2_dist(4
                               source images)
      rerun_noise_pct       = 100 * DINOv2_dist(bary_sym run twice)
                               / mean_pairwise_DINOv2_dist(4 source images)
    -- confirmed against docs/INVENTORY.md's printed-output values exactly:
    quad A ([honeycombed, cracked, woven, scaly]) prints 46%/14%, quad B
    ([marbled, grid, fibrous, bumpy]) prints 38%/32%. (Cell 13 also
    contains an earlier, rougher version of the same src_sep computation,
    averaging only adjacent source pairs rather than all six pairs; this
    script follows cell 14's full-pairwise version, since that is the one
    whose printed numbers match the paper.)

THIS CLAIM IS PRINTED ONLY IN THE ARCHIVE -- there is no cached CSV/JSON
anywhere under data/stability_apps/results/ holding AnchorChangeA/B or the
noise floors (checked directly), and score_only.py has no
Tier-1 check for it either (grep for "Anchor" in that file: no hits). That
means this script's correctness cannot be checked here against any cached
ground truth the way cnt_1000.py/tm_1000.py's outputs can be spot-checked
against archived KID/FID numbers -- it is a genuine from-scratch render,
and the only way to confirm it reproduces the paper's 46%/38%/14%/32% is to
actually run it on a GPU with CNT installed. Do not treat this script as
verified; treat it as a faithful, honest port of the saved cell source.

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see docs/PROVENANCE.md).

Usage:
    python experiments/anchor_mixtures.py --cnt-root ../cnt-siga24 \\
        --dtd-root ../dtd/images --out RENDERED
    python experiments/anchor_mixtures.py --cnt-root ../cnt-siga24 \\
        --dtd-root ../dtd/images --out /tmp/smoke --quads A   # smoke test (one quad only)
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import random
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

from texton_matching.cnt import CNTModel
from texton_matching import matching

# The two source quadruples the paper's anchor-mixture study uses, verbatim
# from anchor_mixtures_and_stability.ipynb cell 14. Key "A"/"B" here is our own
# naming for AnchorChangeA/AnchorChangeB -- the notebook itself just calls
# them "quad 0"/"quad 1" (its `QUADS` list, in this order).
QUADS = {
    "A": ["honeycombed", "cracked", "woven", "scaly"],
    "B": ["marbled", "grid", "fibrous", "bumpy"],
}
W_EQ = [0.25, 0.25, 0.25, 0.25]
N_SUB = 4096  # cell 13/14's bary_* default n_sub, matching texton_matching.cnt.NSUB


def quad_paths(dtd_root: Path, cats: list[str], categories: list[str], tag: str) -> list[str]:
    """Deterministic one-file-per-category pick. Verbatim seeding from cell
    14's `quad_paths`: random.Random(f'{tag}{c}').choice(sorted(glob(...))).
    `tag` is `f'hero{qi}'` in the notebook, qi=0 for quad A, qi=1 for quad B."""
    out = []
    for c in categories:
        if c not in cats:
            continue
        files = sorted(glob.glob(str(dtd_root / c / "*.jpg")))
        if files:
            out.append(random.Random(f"{tag}{c}").choice(files))
    return out[:4]


def style_flat(cnt: CNTModel, path: str):
    """One texture's flattened largest style map plus its own blob (needed
    to decode on its own support). Verbatim port of cell 13's `_style_flat`,
    built from CNTModel's own get_gen_inputs/build_style_maps instead of
    re-deriving CNT loading from scratch."""
    img = cnt.load_image(path)
    blob, bf, si = cnt.get_gen_inputs(img)
    sm = cnt.build_style_maps(bf, si)[max(cnt.FMS)][0]
    C, H, W = sm.shape
    return sm.permute(1, 2, 0).reshape(-1, C), blob, (C, H, W)


def decode_style(cnt: CNTModel, st, ref):
    import torch.nn.functional as F
    L = max(cnt.FMS)
    sm = {s: (st if s == L else F.interpolate(st, size=s, mode="bilinear", align_corners=False)) for s in set(cnt.FMS)}
    return cnt.to_pil(cnt.decode_with_style_maps(ref, sm))


def bary_anchored(cnt: CNTModel, paths: list[str], weights: list[float], anchor: int, n_sub: int = N_SUB):
    """k-way OT barycentre expressed on `anchor`'s support (asymmetric).
    Verbatim port of cell 13's `bary_anchored`, using
    texton_matching.matching.sinkhorn_plan (eps=0.05, iters=100, matching
    the notebook's local `sinkhorn_transport` defaults exactly) for the
    pairwise transport instead of a second hand-rolled Sinkhorn loop --
    the only difference is the numerical stabiliser added to the Sinkhorn
    denominators (1e-30 here vs. the notebook's local 1e-10), which does
    not materially change the converged plan."""
    import torch
    flats, blobs, shape = [], [], None
    for p in paths:
        f, b, s = style_flat(cnt, p)
        flats.append(f)
        blobs.append(b)
        shape = s
    C, H, W = shape
    base = flats[anchor]
    N = base.shape[0]
    idx = torch.randperm(N, device=base.device)[:n_sub]
    nn = torch.cdist(base, base[idx]).argmin(1)
    mix = torch.zeros_like(base)
    for w, f in zip(weights, flats):
        if w == 0:
            continue
        if f is base:
            mix += w * base
        else:
            j = torch.randperm(f.shape[0], device=base.device)[:n_sub]
            P, _ = matching.sinkhorn_plan(base[idx], f[j], eps=0.05, iters=100)
            transported = (P / (P.sum(1, keepdim=True) + 1e-10)) @ f[j]
            mix += w * transported[nn]
    return mix.reshape(H, W, C).permute(2, 0, 1).unsqueeze(0), blobs[anchor]


def bary_sym(cnt: CNTModel, paths: list[str], weights: list[float], n_sub: int = N_SUB):
    """Symmetric k-way barycentre: average the anchored solutions over
    EVERY anchor choice, in image space (supports differ per anchor, so
    feature-space averaging is not well defined). Verbatim port of cell
    13's `bary_sym` -- the k-way analogue of OT-sym."""
    import numpy as np
    from PIL import Image
    imgs = []
    for a in range(len(paths)):
        st, ref = bary_anchored(cnt, paths, weights, anchor=a, n_sub=n_sub)
        imgs.append(np.asarray(decode_style(cnt, st, ref), dtype=np.float32))
    return Image.fromarray(np.clip(np.mean(imgs, axis=0), 0, 255).astype(np.uint8))


def bary_linear(cnt: CNTModel, paths: list[str], weights: list[float]):
    """k-way linear blend of style maps -- the control. Verbatim port of
    cell 13's `bary_linear`. `ref_i = argmax(weights)` picks the reference
    blob to decode with; with W_EQ all-equal, numpy's argmax deterministically
    picks index 0, matching the notebook exactly."""
    import numpy as np
    sms = []
    for p in paths:
        img = cnt.load_image(p)
        _, bf, si = cnt.get_gen_inputs(img)
        sms.append(cnt.build_style_maps(bf, si))
    ref_i = int(np.argmax(weights))
    ref_img = cnt.load_image(paths[ref_i])
    blob, _, _ = cnt.get_gen_inputs(ref_img)
    mixed = {s: sum(w * sm[s] for w, sm in zip(weights, sms)) for s in set(cnt.FMS)}
    return cnt.to_pil(cnt.decode_with_style_maps(blob, mixed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True, help="path to the cloned+checked-out CNT repo (install/cnt.sh)")
    ap.add_argument("--dtd-root", required=True, help="DTD images/ dir (texton_matching.data.download_dtd)")
    ap.add_argument("--out", required=True, help="where to write stability_apps/results/*")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quads", default="A,B", help="comma-separated subset of QUADS keys to run ('A,B' by default; 'A' alone for a quick smoke test)")
    args = ap.parse_args()

    import numpy as np
    from PIL import Image
    # Reuses rescore.py's DINOv2 extractor (same vit_small_patch14_dinov2.lvd142m
    # model the notebook's own setup cell loads) instead of re-deriving a
    # second DINO loader -- this is a direct module import, not a subprocess,
    # since this script needs per-call feature vectors, not rescore.py's CLI.
    from rescore import Extractor

    dtd_root = Path(args.dtd_root)
    cats = sorted(c for c in os.listdir(dtd_root) if (dtd_root / c).is_dir())
    out = Path(args.out) / "stability_apps" / "results"
    out.mkdir(parents=True, exist_ok=True)

    cnt = CNTModel(args.cnt_root, device=args.device)
    ext = Extractor(device=args.device)

    rows = []
    for key in args.quads.split(","):
        key = key.strip()
        if key not in QUADS:
            print(f"[anchor_mixtures] WARNING: unknown quad key {key!r} (expected 'A' or 'B'); skipping")
            continue
        categories = QUADS[key]
        qi = list(QUADS.keys()).index(key)  # A -> hero0, B -> hero1, matching the notebook's QUADS order
        paths = quad_paths(dtd_root, cats, categories, tag=f"hero{qi}")
        if len(paths) < 4:
            print(f"[anchor_mixtures] WARNING: quad {key} ({categories}) only found {len(paths)}/4 categories "
                  f"in {dtd_root}; skipping (the notebook silently skips these too)")
            continue

        anchored_imgs = [decode_style(cnt, *bary_anchored(cnt, paths, W_EQ, anchor=a)) for a in range(4)]
        for a, im in enumerate(anchored_imgs):
            im.save(out / f"quad_{key}_anchor{a}.png")

        sym_img = bary_sym(cnt, paths, W_EQ)
        sym_img.save(out / f"quad_{key}_sym.png")
        sym_img2 = bary_sym(cnt, paths, W_EQ)  # a second independent run, for the re-run-noise measurement

        lin_img = bary_linear(cnt, paths, W_EQ)
        lin_img.save(out / f"quad_{key}_linear.png")

        src_imgs = [Image.open(p).convert("RGB").resize((256, 256)) for p in paths]

        Fa = ext.dino_feats(anchored_imgs)
        D = np.linalg.norm(Fa[:, None] - Fa[None, :], axis=2)
        spread = float(D[np.triu_indices(4, 1)].mean())

        Fs = ext.dino_feats(src_imgs)
        Ds = np.linalg.norm(Fs[:, None] - Fs[None, :], axis=2)
        src_sep = float(Ds[np.triu_indices(4, 1)].mean())

        Fsym = ext.dino_feats([sym_img, sym_img2])
        sym_noise = float(np.linalg.norm(Fsym[0] - Fsym[1]))

        anchor_pct = 100 * spread / max(src_sep, 1e-9)
        noise_pct = 100 * sym_noise / max(src_sep, 1e-9)
        paper_anchor = {"A": 46, "B": 38}[key]
        paper_noise = {"A": 14, "B": 32}[key]
        print(f"[anchor_mixtures] quad {key} [{', '.join(categories)}]: "
              f"AnchorChange{key} = {anchor_pct:.0f}% of source separation (paper: {paper_anchor}%), "
              f"OT-sym re-run noise = {noise_pct:.0f}% (paper: {paper_noise}%)")
        rows.append(dict(quad=key, categories="|".join(categories), spread=spread, src_sep=src_sep,
                          sym_noise=sym_noise, anchor_change_pct=anchor_pct, rerun_noise_pct=noise_pct))

    out_csv = out / "anchor_mixtures.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["quad", "categories", "spread", "src_sep", "sym_noise",
                                           "anchor_change_pct", "rerun_noise_pct"])
        w.writeheader()
        w.writerows(rows)
    print(f"[anchor_mixtures] wrote {out_csv}")
    print("[anchor_mixtures] NOTE: this table has no Tier-1 check in score_only.py yet (no cached file existed to")
    print("[anchor_mixtures]       check against before this script existed) -- wiring one up now just means")
    print("[anchor_mixtures]       pointing it at this CSV's anchor_change_pct/rerun_noise_pct columns.")
    print("[anchor_mixtures] NOTE: fig:app-mixtures/fig:app-mixtures2/fig:app-palette panel assembly (arranging")
    print("[anchor_mixtures]       the saved PNGs above into the final multi-panel figure) is left to whoever")
    print("[anchor_mixtures]       picks the final figure, same as every other figure in this package -- see")
    print("[anchor_mixtures]       docs/INVENTORY.md §2 item 28, 'Figure provenance stops at the candidate stage.'")


if __name__ == "__main__":
    main()
