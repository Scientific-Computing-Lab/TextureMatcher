#!/usr/bin/env python3
"""Pack the cached inputs of score_only.py into evidence/tier1/.

Copies every archive file that score_only.py reads, keeping the archive's
relative layout, and stores floating-point arrays as float16 (.npy and the
arrays inside .npz). score_only.py casts them back to float64 on load. CSV and
JSON files are copied unchanged.

Usage:
    python experiments/pack_tier1.py --archive /path/to/archive
"""
import argparse
import shutil
from pathlib import Path

import numpy as np

FILES = [
    "correspondence/feats/E1.npz",
    "correspondence/feats/E4.npz",
    "correspondence/feats/dense.npz",
    "evidence/alignment_scores.csv",
    "evidence/eqsample_summary.csv",
    "evidence/timing_120.csv",
    "evidence/timing_120_tm.csv",
    "jackknife/feats_eq_hard.npy",
    "jackknife/feats_eq_linear_cp.npy",
    "jackknife/feats_eq_ot_e0.005.npy",
    "jackknife/feats_eq_ot_e0.05.npy",
    "jackknife/feats_eq_ot_paper.npy",
    "jackknife/feats_g_gauss.npy",
    "jackknife/feats_g_gpt.npy",
    "jackknife/feats_g_gptsym.npy",
    "jackknife/feats_g_hard.npy",
    "jackknife/feats_g_ot.npy",
    "jackknife/feats_g_pix.npy",
    "jackknife/feats_g_tex.npy",
    "jackknife/feats_g_tm.npy",
    "jackknife/feats_g_tmhard.npy",
    "jackknife/feats_g_tmlerp.npy",
    "jackknife/feats_g_tmmean.npy",
    "jackknife/feats_g_tmot.npy",
    "jackknife/feats_tm1000_lerp.npy",
    "jackknife/feats_tm1000_mean.npy",
    "jackknife/feats_tm1000_ot_r0.03.npy",
    "jackknife/scores_eq_hard.csv",
    "jackknife/scores_eq_linear_cp.csv",
    "jackknife/scores_eq_ot_e0.005.csv",
    "jackknife/scores_eq_ot_e0.05.csv",
    "jackknife/scores_g_gauss.csv",
    "jackknife/scores_g_gpt.csv",
    "jackknife/scores_g_gptsym.csv",
    "jackknife/scores_g_hard.csv",
    "jackknife/scores_g_ot.csv",
    "jackknife/scores_g_pix.csv",
    "jackknife/scores_g_tex.csv",
    "jackknife/scores_g_tm.csv",
    "jackknife/scores_g_tmhard.csv",
    "jackknife/scores_g_tmlerp.csv",
    "jackknife/scores_g_tmmean.csv",
    "jackknife/scores_g_tmot.csv",
    "jackknife/scores_tm1000_lerp.csv",
    "jackknife/scores_tm1000_mean.csv",
    "jackknife/scores_tm1000_ot_r0.03.csv",
    "joint_basis/ceiling.csv",
    "joint_basis/ceiling_summary.json",
    "joint_basis/feats_ceiling.npz",
    "joint_basis/ref_inc_win128.npy",
    "matching_ablation/feat_exact_inc.npy",
    "matching_ablation/feat_gaussian_w2_inc.npy",
    "matching_ablation/feat_ot_inc.npy",
    "matching_ablation/feat_ot_sym_inc.npy",
    "matching_ablation/feat_pixel_linear_inc.npy",
    "matching_ablation/feat_texton_linear_inc.npy",
    "matching_ablation/feat_tm_inc.npy",
    "matching_ablation/final128_n1000.csv",
    "matching_ablation/ref_dino.npy",
    "matching_ablation/ref_inc.npy",
    "matching_ablation/rules_feats.npz",
    "matching_ablation/rules_n200.csv",
    "pairs_120/pairs.csv",
]

SOURCE_RENAMES = {"pairs_120/": "pairs_for_"}


def source_path(archive: Path, rel: str) -> Path:
    p = archive / rel
    if p.exists():
        return p
    for new, old_prefix in SOURCE_RENAMES.items():
        if rel.startswith(new):
            for legacy in sorted(archive.glob(old_prefix + "*")):
                q = legacy / rel[len(new):]
                if q.exists():
                    return q
    raise FileNotFoundError(rel)


def to_f16(a: np.ndarray) -> np.ndarray:
    return a.astype(np.float16) if a.dtype.kind == "f" else a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "evidence" / "tier1"))
    args = ap.parse_args()
    archive, out = Path(args.archive), Path(args.out)
    for rel in FILES:
        src, dst = source_path(archive, rel), out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".npy"):
            np.save(dst, to_f16(np.load(src)))
        elif rel.endswith(".npz"):
            with np.load(src) as z:
                np.savez_compressed(dst, **{k: to_f16(z[k]) for k in z.files})
        else:
            shutil.copy(src, dst)
    print(f"packed {len(FILES)} files into {out}")


if __name__ == "__main__":
    main()
