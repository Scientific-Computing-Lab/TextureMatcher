#!/usr/bin/env python3
"""Tier 3: renders app:ceiling (supplement) -- how much of a texture's
detail survives CNT's own encode/decode loop, independent of any
interpolation, and whether the size of that loss predicts midpoint quality.

Ported from `CNT_joint_basis_and_ceiling.ipynb` cell 5 ("Q2 -- encoding
ceiling"): for each of 120 pairs' two endpoints, one encode-decode
reconstruction (rec1) and a reconstruction of that reconstruction (rec2),
each scored (KID/FID/realism/LPIPS/PSNR) against `orig`. Also reuses an
existing "ot" midpoint render (from cnt_1000.py, first 120 pairs) as the
`midpoint_ot` row. `CeilRho` (Spearman correlation between endpoint
reconstruction error and midpoint quality) needs a per-pair join this
script does not attempt (see the comment above its computation below);
score_only.py already flags this same gap when it reads the row back
("file value; recompute needs a per-pair reconstruction-error join, not
attempted") -- this script writes ceiling_summary.json without it, and the
CHECK.md row falls back to NO FILE ROW until someone adds that join.

Reference caveat (read before trusting this script's KID numbers): cell 5's
own saved source scores against `ref_inc`, which cell 1 of the SAME
notebook loads from `matching_ablation/ref_inc.npy` -- the canonical
2,819-image reference used everywhere else in the paper. But
`score_only.py`'s app:ceiling section (built and empirically
verified earlier in this project, against the real archive) reads a
DIFFERENT, notebook-local file, `joint_basis/ref_inc_win128.npy` (asserted
to have exactly 5,640 rows), with a comment stating the canonical
2,819-image reference was tested and found to give a KID about 150x too
small -- i.e. that the win128 reference is what actually reproduces the
paper's `Ceil*` macros. This is a real, unresolved contradiction between
the archived notebook's saved cell text and this package's own earlier,
empirically-verified finding; this script follows the empirically-verified
contract (matching what score_only.py actually reads), not the literal
cell-5 source, and builds `ref_inc_win128.npy` per cell 3's
`ref_window_feats()` (native 128px CENTER-WINDOW crops of a 256px-normalized
version of every one of DTD's 5,640 images, each additionally round-tripped
through a 128->256 bicubic resize first -- see `_ref_window_feats` below,
ported line-for-line from that cell). If you re-run this and it does not
reproduce `CeilKID*`, the cell-5-literal (canonical 2,819) reference is the
other thing to try.

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see README).

Usage:
    python experiments/ceiling_120.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --ot-midpoints RENDERED/tm_scale1000/ot --out RENDERED/joint_basis \\
        --data-root OUT --n-pairs 120
    python experiments/ceiling_120.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out /tmp/smoke/joint_basis --data-root /tmp/smoke_scored --n-pairs 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

from texton_matching.cnt import CNTModel, IMG_SIZE

SCORE_RES = 128


def at128(pil):
    return pil.convert("RGB").resize((SCORE_RES, SCORE_RES))


def _ref_window_feats(dtd_root: Path, ext, cache_dir: Path):
    """Ported from CNT_joint_basis_and_ceiling.ipynb cell 3's
    `ref_window_feats()`: every DTD image, resized so its shorter side is
    IMG_SIZE (256), centre-cropped to 256x256, round-tripped through a
    SCORE_RES(128)->IMG_SIZE(256) bicubic resize (matching the canonical
    pipeline's own scoring-resolution rounding), then cropped to its
    native 128x128 CENTRE window (not a plain 128-resize of the original --
    a window into the 256px image) before feature extraction. `win_full`
    in the source crops (Q, Q, Q+HALF, Q+HALF) with Q=IMG_SIZE//4=64,
    HALF=IMG_SIZE//2=128.
    """
    from PIL import Image
    import numpy as np

    fp_i, fp_d = cache_dir / "ref_inc_win128.npy", cache_dir / "ref_dino_win128.npy"
    if fp_i.exists() and fp_d.exists():
        return np.load(fp_i), np.load(fp_d)

    Q, HALF = IMG_SIZE // 4, IMG_SIZE // 2
    paths = sorted(dtd_root.glob("*/*.jpg"))
    windows = []
    for f in paths:
        im = Image.open(f).convert("RGB")
        w, h = im.size
        r = IMG_SIZE / min(w, h)
        im = im.resize((max(IMG_SIZE, round(w * r)), max(IMG_SIZE, round(h * r))), Image.BICUBIC)
        w, h = im.size
        l, t = (w - IMG_SIZE) // 2, (h - IMG_SIZE) // 2
        crop = im.crop((l, t, l + IMG_SIZE, t + IMG_SIZE))
        crop = crop.resize((SCORE_RES, SCORE_RES), Image.BICUBIC).resize((IMG_SIZE, IMG_SIZE), Image.BICUBIC)
        windows.append(crop.crop((Q, Q, Q + HALF, Q + HALF)))
    Ri = ext.inc_feats(windows)
    Rd = ext.dino_feats(windows)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(fp_i, Ri)
    np.save(fp_d, Rd)
    print(f"[ceiling_120] built the {len(paths)}-image native-window reference -> {fp_i}, {fp_d}")
    return Ri, Rd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True)
    ap.add_argument("--manifest", required=True, help="JSON with a 'pairs' list of {k,cA,fA,cB,fB}")
    ap.add_argument("--dtd-root", required=True, help="full DTD images/ dir -- needed whole (5,640 images), not just the 120 pairs, to build ref_inc_win128")
    ap.add_argument("--ot-midpoints", default=None, help="tm_scale1000/ot dir from an existing cnt_1000.py render, for the midpoint_ot row; skipped if not given")
    ap.add_argument("--out", required=True, help="where to write joint_basis/{feats_ceiling.npz, ceiling.csv, ceiling_summary.json, ref_inc_win128.npy}")
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--n-pairs", type=int, default=120)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    from PIL import Image
    import numpy as np
    import pandas as pd
    from rescore import Extractor, Manifold, realism  # same-process import; see module docstring

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dtd_root = Path(args.dtd_root)

    manifest = json.loads(Path(args.manifest).read_text())["pairs"][: args.n_pairs]
    cnt = CNTModel(args.cnt_root, device=args.device)
    ext = Extractor(device=args.device)

    ref_inc_win128, ref_dino_win128 = _ref_window_feats(dtd_root, ext, out)
    mani_inc = [Manifold(ref_inc_win128, seed=s) for s in range(5)]
    mani_dino = [Manifold(ref_dino_win128, seed=s) for s in range(5)]

    def recon_of(pil):
        return cnt.to_pil(cnt.make_recon(pil))

    def psnr(p1, p2):
        a = np.asarray(p1.convert("RGB"), np.float32)
        b = np.asarray(p2.convert("RGB"), np.float32)
        mse = ((a - b) ** 2).mean()
        return float(10 * np.log10(255 ** 2 / max(mse, 1e-9)))

    import lpips as _lpips_pkg
    import torch
    _lpips_net = _lpips_pkg.LPIPS(net="alex").to(args.device).eval()

    def lpips_d(p1, p2):
        def prep(p):
            a = torch.from_numpy(np.asarray(p.convert("RGB")).copy()).float().permute(2, 0, 1) / 127.5 - 1
            return a.unsqueeze(0).to(args.device)
        with torch.no_grad():
            return float(_lpips_net(prep(p1), prep(p2)).item())

    FC = {}
    rows = []
    for i, pair in enumerate(manifest):
        k = pair["k"]
        A = Image.open(dtd_root / pair["cA"] / pair["fA"]).convert("RGB")
        B = Image.open(dtd_root / pair["cB"] / pair["fB"]).convert("RGB")
        for side, img in (("A", A), ("B", B)):
            r1 = recon_of(img)
            r2 = recon_of(r1)
            for what, pil in (("orig", img), ("rec1", r1), ("rec2", r2)):
                im = at128(pil)
                fi = ext.inc_feats([im])[0]
                fdn = ext.dino_feats([im])[0]
                FC[f"{side}|{what}|{k}|inc"] = fi
                FC[f"{side}|{what}|{k}|dino"] = fdn
                rows.append(dict(
                    k=k, side=side, what=what,
                    real_inc=float(realism(fi[None], mani_inc)[0]),
                    real_dino=float(realism(fdn[None], mani_dino)[0]),
                    psnr_orig=psnr(pil, img), lpips_orig=lpips_d(pil, img),
                ))
        if (i + 1) % 20 == 0 or (i + 1) == len(manifest):
            print(f"[ceiling_120] {i + 1}/{len(manifest)} pairs done")

    np.savez(out / "feats_ceiling.npz", **FC)
    C = pd.DataFrame(rows)
    C.to_csv(out / "ceiling.csv", index=False)

    def kid_ub(X, ref):
        from texton_matching.scoring import kid_full
        return kid_full(X, ref)

    ks = sorted(set(C.k))

    def stack(what):
        return np.stack([FC[f"{side}|{what}|{k}|inc"] for k in ks for side in "AB"]).astype(np.float64)

    from texton_matching.scoring import fid_score
    CE = {what: dict(KID=kid_ub(stack(what), ref_inc_win128), FID=fid_score(stack(what), ref_inc_win128), n=2 * len(ks))
          for what in ("orig", "rec1", "rec2")}

    # NOTE on CeilKIDmid specifically: score_only.py does NOT read anything
    # this script writes for that macro -- it loads jackknife/feats_g_ot.npy
    # (the 120-pair "ot" rule's Inception features, cached by the EXISTING
    # generative_120.py/rescore.py pipeline when run on the same 120 pairs
    # at the same --data-root) directly. --ot-midpoints here only feeds
    # CeilRealMid (the realism decomposition below), which score_only.py
    # DOES read from this script's own ceiling_summary.json.
    if args.ot_midpoints:
        mid_dir = Path(args.ot_midpoints)
        mids = [at128(Image.open(mid_dir / f"{int(k):04d}.png").convert("RGB")) for k in ks if (mid_dir / f"{int(k):04d}.png").exists()]
        if mids:
            Xm = ext.inc_feats(mids).astype(np.float64)
            CE["midpoint_ot"] = dict(KID=kid_ub(Xm, ref_inc_win128), FID=fid_score(Xm, ref_inc_win128), n=len(mids))
            Fm = ext.dino_feats(mids)
            mid_real = realism(Fm, mani_dino)
        else:
            mid_real = None
    else:
        mid_real = None
        print("[ceiling_120] --ot-midpoints not given; CeilKIDmid (the midpoint_ot row) will read as NO FILE ROW")

    # realism decomposition: median DINO realism of {orig, rec1, mid}, per
    # the paper's macros (CeilRealOrig/Rec/Mid). The per-pair Spearman
    # correlation between reconstruction error and midpoint quality
    # (CeilRho) needs joining `mid_real` back to each pair's WORST-of-A,B
    # rec1 LPIPS, which cell 5 does with a pivot this script does not
    # replicate (its `dec` DataFrame's per-pair index construction depends
    # on notebook-local pivot machinery not ported here) -- left out
    # deliberately rather than guessed; see the module docstring.
    P = C.pivot_table(index="k", columns=["what", "side"], values="real_dino")
    decomposition = {
        "orig": P["orig"].mean(1).describe().to_dict(),
        "rec1": P["rec1"].mean(1).describe().to_dict(),
    }
    if mid_real is not None:
        import pandas as _pd
        decomposition["mid"] = _pd.Series(mid_real, index=[k for k in ks if (Path(args.ot_midpoints) / f"{int(k):04d}.png").exists()]).describe().to_dict()

    # score_only.py indexes summary["spearman"]["rho_mid"] unconditionally
    # (ceil_summary["spearman"]["rho_mid"]) -- always include the key, as
    # NaN, when the join above was skipped, so pointing score_only.py at
    # this script's own output degrades to a NO FILE ROW / NaN check
    # rather than a KeyError that would crash every other check in the run.
    summary = dict(ceiling=CE, decomposition=decomposition, spearman=dict(rho_mid=float("nan"), p_mid=float("nan")))
    (out / "ceiling_summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print(f"[ceiling_120] wrote {out / 'feats_ceiling.npz'}, ceiling.csv, ceiling_summary.json"
          + ("" if mid_real is not None else " (no spearman.rho_mid: --ot-midpoints not given, or the join was skipped -- see docstring)"))

    data_root = Path(args.data_root)
    (data_root / "joint_basis").mkdir(parents=True, exist_ok=True)
    import shutil
    for name in ("feats_ceiling.npz", "ceiling.csv", "ceiling_summary.json", "ref_inc_win128.npy"):
        shutil.copy(out / name, data_root / "joint_basis" / name)

    if args.run_score_only:
        subprocess.run([sys.executable, str(PACKAGE_ROOT / "experiments" / "score_only.py"),
                         "--data-root", str(data_root)], check=True)


if __name__ == "__main__":
    main()
