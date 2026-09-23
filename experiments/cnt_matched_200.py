#!/usr/bin/env python3
"""Tier 3: renders tab:eqsample, the matched-rendering / equal-sample
ablation (200 pairs, one rendering path and one scoring session, hard and
the two soft-OT epsilons all sharing the same 1,024-sample cloud).

Ported from finishing_experiments.ipynb's equal-sample cell and
jackknife_dKID.ipynb cell 4 ("ONE CONSISTENT SET"): field-linear
(`linear_cp`), exact OT on 1,024 samples (`hard`), soft OT on the SAME
1,024 samples at eps=0.005 (`ot_e0.005`, "sharp") and eps=0.05
(`ot_e0.05`). The fifth row in tab:eqsample, `ot_paper` (the main-text
"ours" operator, 4,096 samples), is NOT re-rendered here -- it reuses
tm_scale1000/ot from experiments/cnt_1000.py on the same first-200 pairs,
exactly as jackknife_dKID.ipynb did (it never re-rendered that row either).
Run cnt_1000.py first (or at least its first 200 pairs) if you want that
row scored too.

Requires: install/scoring.sh and install/cnt.sh.

Usage:
    python experiments/cnt_matched_200.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --out RENDERED --data-root OUT --n-pairs 200
    python experiments/cnt_matched_200.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --out /tmp/smoke --data-root /tmp/smoke_scored --n-pairs 5
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

N_SHARED_SAMPLES = 1024  # the equal-sample protocol's shared cloud size (vs. the main protocol's 4,096)

RULES = {
    "linear_cp": ("field_linear", {}),
    "hard": ("exact_ot", dict(n_sub=N_SHARED_SAMPLES, n_exact=N_SHARED_SAMPLES)),
    "ot_e0.005": ("soft_ot", dict(n_sub=N_SHARED_SAMPLES, eps=0.005)),
    "ot_e0.05": ("soft_ot", dict(n_sub=N_SHARED_SAMPLES, eps=0.05)),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True)
    ap.add_argument("--manifest", required=True, help="tm_scale1000/manifest.json (or any manifest with an A/B dir alongside it)")
    ap.add_argument("--out", required=True, help="where to render matching_ablation/eqsample200/<rule>/{k:04d}.png")
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--n-pairs", type=int, default=200, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())["pairs"][: args.n_pairs]
    ab_dir = manifest_path.parent

    out = Path(args.out) / "matching_ablation" / "eqsample200"
    out.mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        (out / rule).mkdir(exist_ok=True)
    anchors_a = Path(args.out) / "tm_scale1000" / "recon_A"
    anchors_b = Path(args.out) / "tm_scale1000" / "recon_B"
    anchors_a.mkdir(parents=True, exist_ok=True)
    anchors_b.mkdir(parents=True, exist_ok=True)

    cnt = CNTModel(args.cnt_root, device=args.device)

    for i, pair in enumerate(manifest):
        k = pair["k"]
        A_path, B_path = ab_dir / "A" / f"{k:04d}.png", ab_dir / "B" / f"{k:04d}.png"
        if not (A_path.exists() and B_path.exists()):
            print(f"[cnt_matched_200] WARNING: {A_path} / {B_path} not found; skipping k={k}")
            continue
        imgA, imgB = cnt.load_image(A_path), cnt.load_image(B_path)
        d = cnt.build_pair(imgA, imgB)

        if not (anchors_a / f"{k:04d}.png").exists():
            cnt.to_pil(cnt.field_linear(d, 0.0)).save(anchors_a / f"{k:04d}.png")
        if not (anchors_b / f"{k:04d}.png").exists():
            d_swap = cnt.build_pair(imgB, imgB)
            cnt.to_pil(cnt.field_linear(d_swap, 0.0)).save(anchors_b / f"{k:04d}.png")

        for rule_name, (rule, kw) in RULES.items():
            fp = out / rule_name / f"{k:04d}.png"
            if fp.exists():
                continue
            decoded = matching.interpolate(cnt, d, rule, 0.5, seed=k, **kw)
            cnt.to_pil(decoded).save(fp)

        if (i + 1) % 50 == 0 or (i + 1) == len(manifest):
            print(f"[cnt_matched_200] {i + 1}/{len(manifest)} pairs rendered")

    print("[cnt_matched_200] rendering done. Handing off to rescore.py ...")
    cmd = [sys.executable, str(PACKAGE_ROOT / "rescore.py"),
           "--images", str(Path(args.out)), "--data-root", str(args.data_root),
           "--table", "eqsample_200", "--device", args.device]
    if args.run_score_only:
        cmd.append("--run-score-only")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
