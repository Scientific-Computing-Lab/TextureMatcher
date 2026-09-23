#!/usr/bin/env python3
"""Tier 3: renders Table 1's CNT block (n=1,000 by default) with all six
matching rules plus the field-linear/primitive-linear baselines, then calls
rescore.py to score them and run score_only.py.

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see docs/PROVENANCE.md).

Usage:
    python experiments/cnt_1000.py --cnt-root ../cnt-siga24 --dtd-root ../dtd/images \\
        --out RENDERED/tm_scale1000 --data-root OUT --n-pairs 1000
    python experiments/cnt_1000.py --cnt-root ../cnt-siga24 --dtd-root ../dtd/images \\
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
from texton_matching.data import build_manifest_1000, download_dtd

# Table 1's CNT block: directory name (matching the archive's tm_scale1000/
# layout, which is what rescore.py expects) -> rule name for
# texton_matching.matching.interpolate(). This is five of the six canonical
# rules (field-linear, primitive-linear, Gaussian, soft OT, exact OT); the
# sixth (target mean) has no row of its own in Table 1's CNT block -- it
# appears in Table 1's Texture Mixer block instead (experiments/tm_1000.py)
# and can be rendered here too with --include-target-mean for comparison.
# Table 1's "tm" / Mixer row and "ot_sym" / Symmetric row are NOT CNT
# matching rules: "tm" is Texture Mixer's own output (tm_1000.py), and
# "ot_sym" (a symmetric average of two directed transport paths) is outside
# the six rules texton_matching.matching implements by design -- neither is
# rendered by this script.
METHODS = {
    "pixel_linear": "field_linear",
    "texton_linear": "primitive_linear",
    "gaussian_w2": "gaussian",
    "ot": "soft_ot",
    "exact": "exact_ot",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True, help="path to the cloned+checked-out CNT repo (install/cnt.sh)")
    ap.add_argument("--dtd-root", required=True, help="DTD images/ dir (texton_matching.data.download_dtd)")
    ap.add_argument("--out", required=True, help="where to render tm_scale1000/<method>/{k:04d}.png")
    ap.add_argument("--data-root", required=True, help="where rescore.py writes score_only.py's input files")
    ap.add_argument("--manifest", default=None, help="reuse an existing manifest.json instead of resampling pairs")
    ap.add_argument("--n-pairs", type=int, default=1000, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--include-target-mean", action="store_true", help="also render a target_mean/ row (not part of Table 1's CNT block; see METHODS note)")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    methods = dict(METHODS)
    if args.include_target_mean:
        methods["target_mean"] = "target_mean"

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for m in methods:
        (out / m).mkdir(exist_ok=True)
    (out / "recon_A").mkdir(exist_ok=True)
    (out / "recon_B").mkdir(exist_ok=True)

    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text())["pairs"][: args.n_pairs]
    else:
        manifest_path = build_manifest_1000(args.dtd_root, out.parent, n_pairs=args.n_pairs)
        manifest = json.loads(manifest_path.read_text())["pairs"]

    cnt = CNTModel(args.cnt_root, device=args.device)

    for i, pair in enumerate(manifest):
        k = pair["k"]
        A_path, B_path = out.parent / "A" / f"{k:04d}.png", out.parent / "B" / f"{k:04d}.png"
        if not (A_path.exists() and B_path.exists()):
            print(f"[cnt_1000] WARNING: {A_path} / {B_path} not found (expected from build_manifest_1000); skipping k={k}")
            continue
        imgA, imgB = cnt.load_image(A_path), cnt.load_image(B_path)
        d = cnt.build_pair(imgA, imgB)

        cnt.to_pil(cnt.field_linear(d, 0.0)).save(out / "recon_A" / f"{k:04d}.png")
        d_swap = cnt.build_pair(imgB, imgB)
        cnt.to_pil(cnt.field_linear(d_swap, 0.0)).save(out / "recon_B" / f"{k:04d}.png")

        for method, rule in methods.items():
            fp = out / method / f"{k:04d}.png"
            if fp.exists():
                continue
            decoded = matching.interpolate(cnt, d, rule, 0.5, seed=k, eps=args.eps)
            cnt.to_pil(decoded).save(fp)

        if (i + 1) % 50 == 0 or (i + 1) == len(manifest):
            print(f"[cnt_1000] {i + 1}/{len(manifest)} pairs rendered")

    print("[cnt_1000] rendering done. Handing off to rescore.py ...")
    cmd = [sys.executable, str(PACKAGE_ROOT / "rescore.py"),
           "--images", str(out.parent), "--data-root", str(args.data_root),
           "--dtd-root", str(args.dtd_root), "--table", "table1_cnt_1000", "--device", args.device]
    if args.run_score_only:
        cmd.append("--run-score-only")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
