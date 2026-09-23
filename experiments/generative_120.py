#!/usr/bin/env python3
"""Tier 3: scores tab:generative / tab:app-generative (120 pairs).

This is scoring-only: it does not render anything. It assembles the
120-pair subset of images you already rendered (with cnt_1000.py for pix/
tex/gauss/ot/hard, and tm_1000.py's coupling ablation for tmlerp/tmmean/
tmot/tmhard) plus the GPT-Image-1.5 outputs (gpt/gptsym), which this
package cannot produce -- GPT-Image-1.5 is a proprietary API and its exact
prompts were not retained in the archive (see paper/appendix/
supplement.tex's Reproducibility Statement and docs/INVENTORY.md). Provide them
yourself; see --gpt-dir / --gptsym-dir below.

Requires: install/scoring.sh (this only extracts features and scores; no
CNT, no Texture Mixer, no GPU strictly required, though it is much faster
with one).

Usage:
    python experiments/generative_120.py \\
        --pairs-120 RENDERED/pairs_120/pairs.csv \\
        --cnt-1000-dir RENDERED_CNT/tm_scale1000 \\
        --tm-1000-dir RENDERED_TM \\
        --gpt-dir MY_GPT_OUTPUTS/directed --gptsym-dir MY_GPT_OUTPUTS/symmetric \\
        --out RENDERED_120 --data-root OUT --run-score-only
    # smoke test: pass --n-pairs 5 to only assemble/score the first 5 of the 120
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

# rescore.py's "jackknife/generative120/<rule>/" directory name -> where to
# find that rule's already-rendered images (each is a (source_dir, filename
# pattern) pair; filename patterns take {k:04d}).
CNT_RULES = {
    "pix": "pixel_linear", "tex": "texton_linear", "gauss": "gaussian_w2", "ot": "ot", "hard": "exact",
}
TM_RULES = {
    "tmlerp": "lerp", "tmmean": "mean", "tmot": None,  # "tmot"'s source dir name depends on --tm-eps-rel
}


def assemble(pairs_120: Path, cnt_1000_dir: Path | None, tm_1000_dir: Path | None,
             gpt_dir: Path | None, gptsym_dir: Path | None, tm_eps_rel: float, out_dir: Path, n_pairs: int | None):
    ks = sorted(pd.read_csv(pairs_120)["k"].tolist())
    if n_pairs:
        ks = ks[:n_pairs]
    base = out_dir / "jackknife" / "generative120"

    def copy_rule(rule_out, src_dir, missing_ok=False):
        d = base / rule_out
        d.mkdir(parents=True, exist_ok=True)
        n_copied = 0
        for k in ks:
            src = src_dir / f"{k:04d}.png"
            if src.exists():
                shutil.copy(src, d / f"{k:04d}.png")
                n_copied += 1
        if n_copied < len(ks):
            level = "note" if missing_ok else "WARNING"
            print(f"[generative_120]   {level}: only {n_copied}/{len(ks)} images found in {src_dir} for rule '{rule_out}'")
        return n_copied

    if cnt_1000_dir:
        for rule_out, method_dir in CNT_RULES.items():
            copy_rule(rule_out, cnt_1000_dir / method_dir)
    else:
        print("[generative_120] --cnt-1000-dir not given; skipping pix/tex/gauss/ot/hard")

    if tm_1000_dir:
        tm_base = tm_1000_dir / "jackknife" / "tm1000"
        copy_rule("tmlerp", tm_base / "lerp")
        copy_rule("tmmean", tm_base / "mean")
        copy_rule("tmot", tm_base / f"ot_r{tm_eps_rel}")
    else:
        print("[generative_120] --tm-1000-dir not given; skipping tmlerp/tmmean/tmot")

    if gpt_dir:
        copy_rule("gpt", gpt_dir, missing_ok=True)
    else:
        print("[generative_120] --gpt-dir not given (GPT-Image-1.5 outputs must be supplied by you); skipping 'gpt'")
    if gptsym_dir:
        copy_rule("gptsym", gptsym_dir, missing_ok=True)
    else:
        print("[generative_120] --gptsym-dir not given; skipping 'gptsym'")

    # 'tmhard' (one-to-one Texture Mixer coupling) is only scored on the
    # 120-pair subset in the paper and this package's tm_1000.py doesn't
    # render it (it renders lerp/mean/ot only, matching Table 1's TM
    # block); if you have it, drop it directly under generative120/tmhard/.
    if not (base / "tmhard").exists():
        print("[generative_120] 'tmhard' not assembled (tm_1000.py doesn't render it); "
              "drop images at <out>/jackknife/generative120/tmhard/{k:04d}.png yourself if you have them")

    return ks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs-120", required=True, help="pairs_120/pairs.csv (defines the 120 k values)")
    ap.add_argument("--cnt-1000-dir", default=None, help="the tm_scale1000/ dir produced by experiments/cnt_1000.py")
    ap.add_argument("--tm-1000-dir", default=None, help="the --out dir produced by experiments/tm_1000.py")
    ap.add_argument("--gpt-dir", default=None, help="directory of GPT-Image-1.5 'directed'-prompt outputs, {k:04d}.png")
    ap.add_argument("--gptsym-dir", default=None, help="directory of GPT-Image-1.5 'symmetric'-prompt outputs")
    ap.add_argument("--tm-eps-rel", type=float, default=0.03)
    ap.add_argument("--out", required=True, help="where to assemble jackknife/generative120/<rule>/*.png")
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--n-pairs", type=int, default=None, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    ks = assemble(Path(args.pairs_120), Path(args.cnt_1000_dir) if args.cnt_1000_dir else None,
                   Path(args.tm_1000_dir) if args.tm_1000_dir else None,
                   Path(args.gpt_dir) if args.gpt_dir else None, Path(args.gptsym_dir) if args.gptsym_dir else None,
                   args.tm_eps_rel, out, args.n_pairs)
    print(f"[generative_120] assembled {len(ks)} pairs under {out}/jackknife/generative120/")

    # rescore.py also wants tm_scale1000/recon_A, recon_B (balance anchors)
    # and pairs_120/pairs.csv; reuse the caller's if not already copied.
    (out / "pairs_120").mkdir(parents=True, exist_ok=True)
    shutil.copy(args.pairs_120, out / "pairs_120" / "pairs.csv")
    if args.cnt_1000_dir:
        for side in ("recon_A", "recon_B"):
            src = Path(args.cnt_1000_dir) / side
            if src.exists() and not (out / "tm_scale1000" / side).exists():
                shutil.copytree(src, out / "tm_scale1000" / side)

    cmd = [sys.executable, str(PACKAGE_ROOT / "rescore.py"),
           "--images", str(out), "--data-root", str(args.data_root),
           "--table", "generative_120", "--device", args.device]
    if args.run_score_only:
        cmd.append("--run-score-only")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
