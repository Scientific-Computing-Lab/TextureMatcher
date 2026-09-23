#!/usr/bin/env python3
"""Tier 2: turn a directory of rendered midpoint images into the same
feature caches and per-pair CSVs score_only.py reads, then run
score_only.py against them.

This is the bridge between Tier 3 (which needs CNT / Texture Mixer / a GPU
to render images) and Tier 1 (score_only.py, which only needs numpy/scipy/
pandas and never touches a renderer). Every Tier 3 experiment script calls
this at the end; you can also call it by hand after rendering images
however you like, as long as they're laid out the way this script expects
(see --images below).

Feature extraction matches the canonical scoring cell exactly (same DINOv2
model, same Inception weights, same resize-then-normalize order); install
it with install/scoring.sh first.

--images layout (only the subdirectories relevant to the tables you're
rescoring need to exist):

    <images>/tm_scale1000/<method>/{k:04d}.png          # Table 1, CNT block (n=1000): method in
                                                         #   pixel_linear, texton_linear, gaussian_w2,
                                                         #   ot, exact, target_mean
                                                         #   (NOT ot_sym -- removed from the paper; NOT tm --
                                                         #   that's Texture Mixer's own output, see tm_1000.py)
    <images>/tm_scale1000/recon_A/{k:04d}.png           # t=0 reconstructions, for the balance ("place") column
    <images>/tm_scale1000/recon_B/{k:04d}.png
    <images>/jackknife/tm1000/<rule>/{k:04d}.png         # Table 1, Texture Mixer block (n=1000): rule in lerp, mean, ot_r0.03
    <images>/matching_ablation/rules200/<rule>/{k:04d}.png   # tab:rules (200 pairs): rule in
                                                         #   random, uniform, pixel_linear, texton_linear,
                                                         #   gauss, nn, exact, ot, ot_sharp
    <images>/jackknife/generative120/<rule>/{k:04d}.png  # tab:generative / tab:app-generative (120 pairs):
                                                         #   rule in pix, tex, gauss, ot, hard, tm, gpt, gptsym,
                                                         #   tmlerp, tmmean, tmot, tmhard
    <images>/matching_ablation/eqsample200/<rule>/{k:04d}.png  # tab:eqsample (200 pairs): rule in
                                                         #   linear_cp, hard, ot_e0.005, ot_e0.05, ot_paper

The frozen 2,819-image reference is looked up from --data-root's
matching_ablation/ref_inc.npy / ref_dino.npy if present, else rebuilt from
--dtd-root with the same seed=2819, 60-per-category sample as every
canonical notebook (needs --dtd-root; download DTD with
texton_matching.data.download_dtd first).

NOT covered by this script (see README "what's not covered"): the
app:ceiling and tab:app-primitives tables, whose per-pair CSVs mix A-side/
B-side reconstructions and Gaussian-primitive arms in a way this generic
rescorer doesn't attempt to replicate. score_only.py still checks them --
against data/'s existing cached features -- when you point it at the
original archive; it will report "NO FILE ROW" for anything this script
didn't produce.

Usage:
    python rescore.py --images RENDERED_DIR --data-root OUT_DIR \\
        --dtd-root DTD_DIR --table all --run-score-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Must be set before `import timm` (which pulls in huggingface_hub) --
# recent huggingface_hub versions auto-detect a Colab/Jupyter runtime and
# proactively look for an HF_TOKEN via Colab's secrets UI, prompting the
# user for access even for a fully public, anonymous model download
# (DINOv2's weights need no token at all). This disables that.
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

import numpy as np
import pandas as pd
from PIL import Image

PACKAGE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_ROOT))

try:
    import torch
    import torch.nn.functional as F
    _HAVE_TORCH = True
except ImportError:
    _HAVE_TORCH = False


# ---------------------------------------------------------------------------
# Feature extraction (matches the canonical scoring cell exactly)
# ---------------------------------------------------------------------------

class Extractor:
    def __init__(self, device: str = "cuda"):
        if not _HAVE_TORCH:
            raise ImportError("torch is required for rescore.py; run install/scoring.sh first")
        import timm
        from torchvision.models import inception_v3, Inception_V3_Weights
        self.device = device
        self.dino = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0).to(device).eval()
        self.inc = inception_v3(weights=Inception_V3_Weights.IMAGENET1K_V1, aux_logits=True).to(device).eval()
        self.inc.fc = torch.nn.Identity()
        for p in list(self.dino.parameters()) + list(self.inc.parameters()):
            p.requires_grad_(False)
        self._M = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 3, 1, 1)
        self._S = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 3, 1, 1)

    def _stack(self, pils):
        return torch.stack([
            torch.from_numpy(np.asarray(p.convert("RGB").resize((256, 256))).copy()).float().permute(2, 0, 1) / 255.0
            for p in pils
        ]).to(self.device)

    @torch.no_grad()
    def dino_feats(self, pils, bs: int = 64):
        out = []
        for i in range(0, len(pils), bs):
            b = F.interpolate(self._stack(pils[i:i + bs]), size=518, mode="bilinear", align_corners=False)
            out.append(self.dino((b - self._M) / self._S).cpu().numpy())
        return np.concatenate(out)

    @torch.no_grad()
    def inc_feats(self, pils, bs: int = 64):
        out = []
        for i in range(0, len(pils), bs):
            b = F.interpolate(self._stack(pils[i:i + bs]), size=299, mode="bilinear", align_corners=False)
            out.append(self.inc((b - self._M) / self._S).cpu().numpy())
        return np.concatenate(out)


def load_pils(dir_: Path, ks: list[int], pattern: str = "{k:04d}.png") -> list[Image.Image]:
    return [Image.open(dir_ / pattern.format(k=k)) for k in ks]


def list_ks(dir_: Path, pattern_glob: str = "*.png") -> list[int]:
    return sorted(int(p.stem) for p in dir_.glob(pattern_glob) if p.stem.isdigit())


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

def build_or_load_reference(data_root: Path, dtd_root: Path | None, ext: Extractor, seed: int = 2819, per_cat: int = 60):
    ref_inc_path = data_root / "matching_ablation" / "ref_inc.npy"
    ref_dino_path = data_root / "matching_ablation" / "ref_dino.npy"
    if ref_inc_path.exists() and ref_dino_path.exists():
        print(f"[rescore] reusing existing reference at {ref_inc_path}")
        return np.load(ref_inc_path), np.load(ref_dino_path)

    if dtd_root is None:
        raise SystemExit(
            "No reference found at matching_ablation/ref_inc.npy and --dtd-root was not given; "
            "can't build the frozen 2,819-image reference. Pass --dtd-root, or copy an existing "
            "ref_inc.npy/ref_dino.npy from the archive."
        )

    import random
    print(f"[rescore] building the reference from {dtd_root} (seed={seed}, {per_cat}/category)")
    cats = sorted(c for c in dtd_root.iterdir() if c.is_dir())
    rng = random.Random(seed)
    paths = []
    for c in cats:
        files = sorted((c).glob("*.jpg"))
        paths.extend(rng.sample(files, min(per_cat, len(files))))
    paths = paths[:2819]
    pils = [Image.open(p) for p in paths]
    ref_inc = ext.inc_feats(pils)
    ref_dino = ext.dino_feats(pils)
    (data_root / "matching_ablation").mkdir(parents=True, exist_ok=True)
    np.save(ref_inc_path, ref_inc)
    np.save(ref_dino_path, ref_dino)
    (data_root / "matching_ablation" / "ref_list.json").write_text(json.dumps([str(p) for p in paths]))
    print(f"[rescore] reference built: {len(paths)} images -> {ref_inc_path}, {ref_dino_path}")
    return ref_inc, ref_dino


def balance_place(mid_dino, a_dino, b_dino):
    dA = np.linalg.norm(mid_dino - a_dino, axis=1)
    dB = np.linalg.norm(mid_dino - b_dino, axis=1)
    return dA / (dA + dB)


class Manifold:
    """Kynkaanniemi et al. (2019) continuous realism score against a fixed
    k-NN radius manifold. Ported verbatim from the canonical scoring cell
    (jackknife_dKID.ipynb cell 1): k=3, one manifold per seed in range(5),
    realism = median over the 5 manifolds.
    """
    def __init__(self, R, k=3, n=1000, seed=0):
        rng = np.random.RandomState(seed)
        self.R = R[rng.choice(len(R), min(n, len(R)), replace=False)]
        D = np.linalg.norm(self.R[:, None] - self.R[None], axis=-1)
        D.sort(1)
        rad = D[:, k]
        keep = rad <= np.median(rad)
        self.R = self.R[keep]
        self.rad = rad[keep]

    def __call__(self, X, bs=256):
        out = []
        for i in range(0, len(X), bs):
            D = np.linalg.norm(X[i:i + bs, None] - self.R[None], axis=-1)
            out.append((self.rad[None] / (D + 1e-9)).max(1))
        return np.concatenate(out)


def realism(feats, manifolds):
    return np.median(np.stack([m(feats) for m in manifolds]), 0)


# ---------------------------------------------------------------------------
# Per-table rescorers
# ---------------------------------------------------------------------------

def rescore_flat_table(images_root: Path, subdir: str, rules: dict[str, str], ext: Extractor,
                        ref_inc, ref_dino, anchors=None, feats_out: Path | None = None,
                        feat_prefix: str = "feat") -> pd.DataFrame:
    """Shared driver: for every `rule` under `images_root/subdir/<rule>/`,
    extract Inception+DINO features, per-image realism against the frozen
    reference, and (if `anchors` is given) DINO-distance balance ("place"),
    saving per-rule .npy feature caches under `feats_out`. Returns one
    long-format DataFrame with columns k, rule, real_inc, real_dino, place.
    """
    mani_inc = [Manifold(ref_inc, seed=s) for s in range(5)]
    mani_dino = [Manifold(ref_dino, seed=s) for s in range(5)]

    rows = []
    base = images_root / subdir
    if not base.exists():
        print(f"[rescore] {base} not found, skipping")
        return pd.DataFrame(rows)
    for rule_dir_name, rule_label in rules.items():
        d = base / rule_dir_name
        if not d.exists():
            print(f"[rescore]   {d} not found, skipping rule '{rule_label}'")
            continue
        ks = list_ks(d)
        if not ks:
            print(f"[rescore]   {d} has no PNGs, skipping rule '{rule_label}'")
            continue
        pils = load_pils(d, ks)
        inc = ext.inc_feats(pils)
        dino = ext.dino_feats(pils)
        if feats_out is not None:
            feats_out.mkdir(parents=True, exist_ok=True)
            np.save(feats_out / f"{feat_prefix}_{rule_label}_inc.npy", inc)
            np.save(feats_out / f"{feat_prefix}_{rule_label}_dino.npy", dino)
        r_inc = realism(inc, mani_inc)
        r_dino = realism(dino, mani_dino)
        place = np.full(len(ks), np.nan)
        if anchors is not None:
            recon_a_dir, recon_b_dir = anchors
            if recon_a_dir.exists() and recon_b_dir.exists():
                a_dino = ext.dino_feats(load_pils(recon_a_dir, ks))
                b_dino = ext.dino_feats(load_pils(recon_b_dir, ks))
                place = balance_place(dino, a_dino, b_dino)
            else:
                print(f"[rescore]   no anchor reconstructions at {recon_a_dir} / {recon_b_dir}; "
                      f"'{rule_label}' balance ('place') left NaN")
        for i, k in enumerate(ks):
            rows.append(dict(k=k, rule=rule_label, real_inc=float(r_inc[i]), real_dino=float(r_dino[i]),
                              place=(float(place[i]) if not np.isnan(place[i]) else None)))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, help="directory of rendered midpoints; see module docstring for layout")
    ap.add_argument("--data-root", required=True, help="output directory in score_only.py's expected layout")
    ap.add_argument("--dtd-root", default=None, help="DTD images/ dir, needed only if the reference isn't already in --data-root")
    ap.add_argument("--table", default="all", choices=["all", "table1_cnt_1000", "table1_tm_1000", "rules_200", "generative_120", "eqsample_200"])
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true", help="invoke score_only.py against --data-root when done")
    args = ap.parse_args()

    images_root = Path(args.images)
    data_root = Path(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    dtd_root = Path(args.dtd_root) if args.dtd_root else None

    ext = Extractor(device=args.device)
    ref_inc, ref_dino = build_or_load_reference(data_root, dtd_root, ext)

    anchors = (images_root / "tm_scale1000" / "recon_A", images_root / "tm_scale1000" / "recon_B")

    tables = [args.table] if args.table != "all" else ["table1_cnt_1000", "table1_tm_1000", "rules_200", "generative_120", "eqsample_200"]

    if "table1_cnt_1000" in tables:
        # ot_sym is not scored here -- removed from the paper. tm is not
        # scored here either -- it's Texture Mixer's own output, produced
        # and scored by tm_1000.py / the table1_tm_1000 table below, not by
        # anything CNT renders. target_mean IS included: cnt_1000.py's
        # --include-target-mean renders it, and rescore_flat_table already
        # skips any rule whose directory doesn't exist, so this list is safe
        # to keep even when you didn't render every rule in it.
        rules = {"pixel_linear": "pixel_linear", "texton_linear": "texton_linear", "gaussian_w2": "gaussian_w2",
                 "ot": "ot", "exact": "exact", "target_mean": "target_mean"}
        df = rescore_flat_table(images_root, "tm_scale1000", rules, ext, ref_inc, ref_dino, anchors=anchors,
                                 feats_out=data_root / "matching_ablation", feat_prefix="feat")
        if len(df):
            out = df.rename(columns={"rule": "method"})[["k", "method", "real_inc", "real_dino", "place"]]
            (data_root / "matching_ablation").mkdir(parents=True, exist_ok=True)
            out.to_csv(data_root / "matching_ablation" / "final128_n1000.csv", index=False)
            print(f"[rescore] wrote matching_ablation/final128_n1000.csv ({len(out)} rows)")

    if "table1_tm_1000" in tables:
        rules = {"lerp": "lerp", "mean": "mean", "ot_r0.03": "ot_r0.03"}
        df = rescore_flat_table(images_root, "jackknife/tm1000", rules, ext, ref_inc, ref_dino, anchors=anchors,
                                 feats_out=data_root / "jackknife", feat_prefix="feats_tm1000")
        for rule, sub in df.groupby("rule"):
            (data_root / "jackknife").mkdir(parents=True, exist_ok=True)
            sub[["k", "real_inc", "real_dino", "place"]].assign(dA=np.nan, dB=np.nan).to_csv(
                data_root / "jackknife" / f"scores_tm1000_{rule}.csv", index=False)

    if "rules_200" in tables:
        rules = {"random": "random", "uniform": "uniform", "pixel_linear": "pixel_linear",
                 "texton_linear": "texton_linear", "gauss": "gauss", "nn": "nn", "exact": "exact",
                 "ot": "ot", "ot_sharp": "ot_sharp"}
        base = images_root / "matching_ablation" / "rules200"
        df = rescore_flat_table(images_root, "matching_ablation/rules200", rules, ext, ref_inc, ref_dino,
                                 anchors=anchors, feats_out=None)
        if base.exists() and len(df):
            npz = {}
            for rule_dir, rule_label in rules.items():
                d = base / rule_dir
                if not d.exists():
                    continue
                ks = list_ks(d)
                if not ks:
                    continue
                inc = ext.inc_feats(load_pils(d, ks))
                for i, k in enumerate(ks):
                    npz[f"{k}_{rule_label}_inc"] = inc[i]
            (data_root / "matching_ablation").mkdir(parents=True, exist_ok=True)
            np.savez(data_root / "matching_ablation" / "rules_feats.npz", **npz)
            gap = np.full(len(df), np.nan)  # endpoint_gap needs a t=1 render; not produced by this generic rescorer
            df.assign(endpoint_gap=gap).rename(columns={"rule": "rule"}).to_csv(
                data_root / "matching_ablation" / "rules_n200.csv", index=False)
            print(f"[rescore] wrote matching_ablation/rules_feats.npz and rules_n200.csv ({len(df)} rows; "
                  f"endpoint_gap left NaN -- this rescorer only takes the eta=0.5 midpoint you rendered, not the t=1 endpoint)")

    if "generative_120" in tables:
        rules = {"pix": "pix", "tex": "tex", "gauss": "gauss", "ot": "ot", "hard": "hard", "tm": "tm",
                 "gpt": "gpt", "gptsym": "gptsym", "tmlerp": "tmlerp", "tmmean": "tmmean", "tmot": "tmot", "tmhard": "tmhard"}
        df = rescore_flat_table(images_root, "jackknife/generative120", rules, ext, ref_inc, ref_dino,
                                 anchors=anchors, feats_out=data_root / "jackknife", feat_prefix="feats_g")
        for rule, sub in df.groupby("rule"):
            (data_root / "jackknife").mkdir(parents=True, exist_ok=True)
            sub[["k", "real_inc", "real_dino", "place"]].assign(dA=np.nan, dB=np.nan).to_csv(
                data_root / "jackknife" / f"scores_g_{rule}.csv", index=False)

    if "eqsample_200" in tables:
        rules = {"linear_cp": "linear_cp", "hard": "hard", "ot_e0.005": "ot_e0.005",
                 "ot_e0.05": "ot_e0.05", "ot_paper": "ot_paper"}
        df = rescore_flat_table(images_root, "matching_ablation/eqsample200", rules, ext, ref_inc, ref_dino,
                                 anchors=anchors, feats_out=data_root / "jackknife", feat_prefix="feats_eq")
        for rule, sub in df.groupby("rule"):
            (data_root / "jackknife").mkdir(parents=True, exist_ok=True)
            sub[["k", "real_inc", "real_dino", "place"]].assign(dA=np.nan, dB=np.nan).to_csv(
                data_root / "jackknife" / f"scores_eq_{rule}.csv", index=False)

    # pairs_120/pairs.csv is needed by score_only.py to define KS120;
    # if the caller already has one (e.g. copied from the archive, or
    # produced by texton_matching.data.build_manifest_120), leave it; else
    # derive it from whichever 120-pair rule directory has images.
    pfg = data_root / "pairs_120"
    if not (pfg / "pairs.csv").exists():
        any_120 = None
        for cand in [images_root / "jackknife" / "generative120" / "pix"]:
            if cand.exists():
                any_120 = cand
                break
        if any_120 is not None:
            ks = list_ks(any_120)
            pfg.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(dict(k=ks)).to_csv(pfg / "pairs.csv", index=False)
            print(f"[rescore] wrote a minimal pairs_120/pairs.csv ({len(ks)} pairs) from {any_120}")

    print("[rescore] done.")
    if args.run_score_only:
        print("[rescore] running score_only.py against", data_root)
        subprocess.run([sys.executable, str(PACKAGE_ROOT / "score_only.py"),
                         "--data-root", str(data_root)], check=True)


if __name__ == "__main__":
    main()
