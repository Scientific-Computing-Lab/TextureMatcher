#!/usr/bin/env python3
"""Tier 3: renders tab:rules, the matching-rule ablation (200 pairs, one
rendering path, nine rules).

Ported from matching_ablation.ipynb cell 2 (`_targets` / `interp_rule` --
read directly, not reconstructed from a description) and cell 4 ("3. MAIN
RUN -- n pairs from the saved tm_scale1000 manifest"), which is also where
the notebook's own cell 1 setup ("F2 ablation setup" family, INVENTORY.md
§4a) lives. FID-by-rule is additionally computed in exact_finish.ipynb
cell 4 ("1. FID BY MATCHING RULE"), a GPU-eigvalsh reimplementation of the
same fid() formula this package's texton_matching.scoring.fid_score
already uses -- not a different formula, just a faster one, so this
script doesn't need anything from that cell beyond confirming the formula
matches (it does: both are the standard Frechet distance with a matrix
square root).

The nine rules: `random` and `nn` are ablation-only (not part of the six
canonical rules texton_matching.matching implements for Table 1 --
see texton_matching/matching.py's ABLATION_ONLY_RULES docstring for the
exact ported formulas, including the seed offsets); `uniform` is Table 1's
`target_mean` rule under a different directory name; `pixel_linear` /
`texton_linear` are CNT's field-linear / primitive-linear baselines, named
identically to Table 1's CNT block directories; `gauss` is the same
Gaussian moment-alignment rule as Table 1's `gaussian_w2` (this ablation's
own cell 2 divides the sample covariance by M instead of M-1 --
texton_matching.matching._gaussian_map uses M-1, the unbiased estimator;
with M=NSUB=4096 the difference is ~0.02% relative, well under this
package's tolerance, so no separate implementation was added for it);
`exact` is `exact_ot`; `ot` is `soft_ot` at the canonical eps (0.05);
`ot_sharp` is `soft_ot` at eps=0.005 (matching_ablation.ipynb hardcodes
this value directly in cell 2's `_targets`, independent of the --eps flag
below, which only affects the `ot` row).

This script only RENDERS the nine rule directories under
matching_ablation/rules200/<rule>/{k:04d}.png; all scoring (feature
extraction, KID/FID, rules_feats.npz, rules_n200.csv) is already handled
by rescore.py's existing `--table rules_200` path (read rescore.py's
`main()` for the exact rule-name -> file-key mapping this script's output
directories must match -- they already do, verified against that code).

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see README).

Usage:
    python experiments/rules_200.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out RENDERED --data-root OUT --n-pairs 200
    python experiments/rules_200.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out /tmp/smoke --data-root /tmp/smoke_scored --n-pairs 5   # smoke test
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

from texton_matching.cnt import CNTModel
from texton_matching import matching

# Directory name (matching rescore.py's `rules_200` table exactly, which in
# turn matches score_only.py's `rule_name_macro` keys) -> (matching.py rule
# name, extra kwargs for matching.interpolate).
RULES = {
    "random": ("random", {}),
    "uniform": ("target_mean", {}),
    "pixel_linear": ("field_linear", {}),
    "texton_linear": ("primitive_linear", {}),
    "gauss": ("gaussian", {}),
    "nn": ("nn", {}),
    "exact": ("exact_ot", {}),
    "ot": ("soft_ot", {}),
    "ot_sharp": ("soft_ot", dict(eps=0.005)),  # matching_ablation.ipynb cell 2: hardcoded, not the --eps flag
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True, help="path to the cloned+checked-out CNT repo (install/cnt.sh)")
    ap.add_argument("--manifest", required=True, help="tm_scale1000/manifest.json (or any manifest with an A/B dir alongside it)")
    ap.add_argument("--dtd-root", default=None, help="DTD images/ dir; only needed if --data-root has no cached reference yet")
    ap.add_argument("--out", required=True, help="where to render matching_ablation/rules200/<rule>/{k:04d}.png")
    ap.add_argument("--data-root", required=True, help="where rescore.py writes score_only.py's input files")
    ap.add_argument("--n-pairs", type=int, default=200, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--eps", type=float, default=0.05, help="epsilon for the 'ot' row only; 'ot_sharp' is always 0.005")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())["pairs"][: args.n_pairs]
    ab_dir = manifest_path.parent

    out = Path(args.out) / "matching_ablation" / "rules200"
    out.mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        (out / rule).mkdir(exist_ok=True)
    # rescore.py's rules_200 path (like every other Tier-2 table) needs
    # t=0 reconstructions for the balance ("place") column, at the shared
    # tm_scale1000/recon_A|B anchor path -- reuse cnt_1000.py's if you ran
    # it on the same manifest already; otherwise this script renders them.
    anchors_a = Path(args.out) / "tm_scale1000" / "recon_A"
    anchors_b = Path(args.out) / "tm_scale1000" / "recon_B"
    anchors_a.mkdir(parents=True, exist_ok=True)
    anchors_b.mkdir(parents=True, exist_ok=True)

    cnt = CNTModel(args.cnt_root, device=args.device)

    for i, pair in enumerate(manifest):
        k = pair["k"]
        A_path, B_path = ab_dir / "A" / f"{k:04d}.png", ab_dir / "B" / f"{k:04d}.png"
        if not (A_path.exists() and B_path.exists()):
            print(f"[rules_200] WARNING: {A_path} / {B_path} not found; skipping k={k}")
            continue
        imgA, imgB = cnt.load_image(A_path), cnt.load_image(B_path)
        d = cnt.build_pair(imgA, imgB)

        if not (anchors_a / f"{k:04d}.png").exists():
            cnt.to_pil(cnt.field_linear(d, 0.0)).save(anchors_a / f"{k:04d}.png")
        if not (anchors_b / f"{k:04d}.png").exists():
            d_swap = cnt.build_pair(imgB, imgB)
            cnt.to_pil(cnt.field_linear(d_swap, 0.0)).save(anchors_b / f"{k:04d}.png")

        for rule_dir, (rule, kw) in RULES.items():
            fp = out / rule_dir / f"{k:04d}.png"
            if fp.exists():
                continue
            call_kw = dict(kw)
            if rule_dir == "ot":  # the only row that honours --eps; ot_sharp's 0.005 is fixed in RULES
                call_kw["eps"] = args.eps
            decoded = matching.interpolate(cnt, d, rule, 0.5, seed=k, **call_kw)
            cnt.to_pil(decoded).save(fp)

        if (i + 1) % 50 == 0 or (i + 1) == len(manifest):
            print(f"[rules_200] {i + 1}/{len(manifest)} pairs rendered")

    print("[rules_200] rendering done. Handing off to rescore.py ...")
    cmd = [sys.executable, str(PACKAGE_ROOT / "rescore.py"),
           "--images", str(Path(args.out)), "--data-root", str(args.data_root),
           "--table", "rules_200", "--device", args.device]
    if args.dtd_root:
        cmd += ["--dtd-root", args.dtd_root]
    if args.run_score_only:
        cmd.append("--run-score-only")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
