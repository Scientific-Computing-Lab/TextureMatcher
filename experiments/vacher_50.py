#!/usr/bin/env python3
"""Tier 3: renders tab:app-vacher's FID column (supplement) -- the 50-pair
comparison between texton matching and Vacher et al.'s optimization-based
interpolation baseline, scored at 128px.

Ported from two notebooks (see docs/INVENTORY.md's claims map for `tab:app-vacher`):

  - `vacher_comparison_corrected.ipynb` cells 1-2: the "corrected loader"
    rerun of the 50-pair comparison. Cell 1's `vacher_interp` is the exact
    Vacher invocation, ported verbatim below (`--model` in {tex_wasser,
    tex_gram, tex_gauss}, `--n_iter 30 --bfgs_iter 20 --shape 256,256`, via
    Vacher's own `BaseOptions`/`create_model`/`utils.tensor2im`, run from
    inside `<vacher_root>/texture-synthesis-algorithm` -- NOT the repo
    root; `install/vacher.sh` clones the repo but the model code is one
    level down). "The corrected loader" (this notebook's own banner
    comment: "THE loader. Always go through load_image, via a temp file if
    needed") means every image -- ours and Vacher's midpoints alike -- is
    always routed through CNT's own `load_image` (proper [-1,1] range),
    the same class of fix docs/INVENTORY.md flags for `position_estimator`
    (naive [0,1] loading elsewhere silently lost ~68% of contrast); this
    script inherits that fix for free by using texton_matching.cnt, which
    always calls CNT's `load_image` too.

    Cell 2's exact 50-pair sampler is ported verbatim below: `cats` is the
    sorted DTD category list, `dtd_path(cat, seed) = sorted(glob(cat/*.jpg))
    [random.Random(seed).choice(...)]`, and pairs are drawn as
    `random.Random(4242).sample(cats, 2)` per pair index `i`, with A's file
    seeded `20000+i` and B's file seeded `40000+i`. This is a SEPARATE
    sampler from `pairs_120/pairs.csv` / `build_manifest_1000` -- do not
    substitute either; the paper's own 50-pair set was drawn this way.

    Cell 2 also renders "ours" at three of the six canonical rules --
    `pixel_linear` (field-linear), `texton_linear` (primitive-linear), `ot`
    (soft OT, eps=0.05, n_sub=4096, the paper's main "ours" operator) --
    which is exactly `texton_matching.matching`'s field_linear /
    primitive_linear / soft_ot, reused here rather than reimplemented. The
    notebook ALSO renders a fourth CNT row, `ot_sym` (a symmetric average
    of two directed OT paths, A->B and B->A) -- this script does NOT
    reproduce `ot_sym`: it is not one of the six canonical rules in
    texton_matching.matching, and rescore.py's own header comment already
    documents it as "removed from the paper." A CNT `recon` row (t=0
    reconstruction, field_linear at eta=0 on a self-pair) is added here to
    match the FID table's "reconstruction floor" row, described next.

  - `ot_direction_fid_and_barycenters.ipynb` cell 20 ("Cell P30: SOTA FID column
    -- Texture Mixer + Vacher vs ours, fair protocol") is where the FID
    numbers actually get computed -- cell 2 above only computes realism/
    balance/structure, NOT FID. Cell 20's recipe, ported as faithfully as
    what's readable in that single cell allows: gather each method's
    already-rendered midpoints, resize everything (ours, Vacher's, and a
    freshly built DTD reference) to 128px, subsample every method's file
    list down to a COMMON n (`n_common = min(len(v) for v in gather.values
    ())`) with `random.Random(55)`, then run FID (Inception-v3 pool-2048
    features, matching pytorch-fid's `calculate_fid_given_paths`) between
    each method's 128px set and the 128px reference.

    IMPORTANT HONESTY NOTE: cell 20 is NOT self-contained -- it reads
    `dirs[m]` (the "ours" render locations), `fid_root`, `P26_REF_CAP` (the
    reference's per-category image cap) and `cats_all` from earlier cells
    in that same very large (4.8MB, ~36-cell), sprawling exploratory
    notebook (cells P1-P29), which this port does NOT trace through --
    doing so would mean reading most of a 4.8MB notebook's cell outputs to
    reconstruct one CLI script's worth of logic, most of which (barycenter
    collapse demos, basis-selection ablations, etc.) is unrelated to this
    one table. This script reimplements cell 20's DOCUMENTED recipe (common-
    n resample to 128px, then FID against a small ad-hoc DTD reference,
    Inception-v3 pool-2048 features) using texton_matching.scoring.fid_score
    and rescore.py's Extractor (the same Inception-v3-pool2048 feature
    extractor used everywhere else in this package) -- but the exact
    `P26_REF_CAP` value, and therefore the exact reference-image count and
    selection, could NOT be pinned down from what was read, so this
    script's `--ref-per-category` defaults to a judgment-call value (20)
    rather than the archived run's real one. Do not expect this script's
    FID numbers to reproduce the archive's printed 268.3/284.6/318.4/273.9
    values exactly; expect them to be in the same ballpark under the same
    protocol shape. tab:app-vacher's FID column remains, honestly,
    printed-only for exact reproduction -- this script only upgrades it
    from "no script exists at all" to "a documented, re-runnable
    approximation of the same protocol."

    `texture_mixer` (an older, separate `texturemixer/midpoints` render,
    not `tm_scale1000`) is intentionally NOT reproduced here -- that render
    no longer exists in a form this script can locate, and Texture Mixer's
    current-protocol numbers are already covered by experiments/tm_1000.py
    under the paper's main 1,000-pair table instead.

Requires: install/scoring.sh, install/cnt.sh, and install/vacher.sh (a GPU
is strongly recommended -- this is not run in this environment; see
README). Vacher's own dependencies (a PyTorch optimization loop per call,
see `install/vacher.sh`'s header) are whatever `<vacher_root>/texture-
synthesis-algorithm`'s own code needs; this script does not install them.

Usage:
    python experiments/vacher_50.py --cnt-root ../cnt-siga24 \\
        --vacher-root ../texture-interpolation --dtd-root ../dtd/images \\
        --out RENDERED/vacher50 --data-root OUT --n-pairs 50
    python experiments/vacher_50.py --cnt-root ../cnt-siga86 \\
        --vacher-root ../texture-interpolation --dtd-root ../dtd/images \\
        --out /tmp/smoke --data-root /tmp/smoke_scored --n-pairs 5   # smoke test
"""
from __future__ import annotations

import argparse
import glob
import os
import random
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

from texton_matching.cnt import CNTModel
from texton_matching import matching
from texton_matching.scoring import fid_score

# "ours" rows rendered via texton_matching (field-linear, primitive-linear,
# soft OT at the paper's default eps=0.05/n_sub=4096) plus a CNT
# reconstruction-floor row. NOT rendered: ot_sym (see module docstring).
OURS_RULES = {
    "pixel_linear": "field_linear",
    "texton_linear": "primitive_linear",
    "ot": "soft_ot",
}
VACHER_MODELS = ["tex_wasser", "tex_gram", "tex_gauss"]
VACHER_SHAPE = "256,256"     # vacher_comparison_corrected.ipynb cell 1, verbatim
VACHER_N_ITER = 30           # verbatim (matches supplement.tex: "we run them for 30 iterations")
VACHER_BFGS_ITER = 20        # verbatim (vacher_interp's default, never overridden in cell 2's call)
FID_RES = 128                # supplement.tex: "scored at 128px"


def dtd_path(dtd_root: Path, cat: str, seed: int) -> Path:
    """Ported verbatim from vacher_comparison_corrected.ipynb cell 0's
    `dtd_path`: a deterministic, seeded choice of one file in `cat`."""
    files = sorted(glob.glob(str(dtd_root / cat / "*.jpg")))
    return Path(random.Random(seed).choice(files))


def sample_50_pairs(dtd_root: Path, n_pairs: int) -> list[dict]:
    """Ported verbatim from vacher_comparison_corrected.ipynb cell 2:
    `random.Random(4242)` draws unordered category pairs; A's/B's file are
    then independently seeded `20000+i` / `40000+i`. This is NOT the same
    sampler as build_manifest_1000 / pairs_120/pairs.csv -- tab:app-vacher
    used its own 50-pair set."""
    cats = sorted(c for c in os.listdir(dtd_root) if (dtd_root / c).is_dir())
    rngp = random.Random(4242)
    pairs = []
    while len(pairs) < n_pairs:
        i = len(pairs)
        a, b = rngp.sample(cats, 2)
        fa, fb = dtd_path(dtd_root, a, 20000 + i), dtd_path(dtd_root, b, 40000 + i)
        pairs.append(dict(k=i, cA=a, fA=fa.name, cB=b, fB=fb.name, pathA=fa, pathB=fb))
    return pairs


def vacher_interp(vacher_root: Path, path_a: Path, path_b: Path, model_name: str,
                   weight: float = 0.5, n_iter: int = VACHER_N_ITER, bfgs_iter: int = VACHER_BFGS_ITER,
                   shape: str = VACHER_SHAPE, seed: int = 0):
    """Ported verbatim from vacher_comparison_corrected.ipynb cell 1's
    `vacher_interp`: shells into Vacher's own `run_synthesis.py`-style CLI
    entry point (`BaseOptions`/`create_model`) via a temporary `sys.argv`
    swap, from inside `<vacher_root>/texture-synthesis-algorithm` (the
    model code's actual location, one level below where install/vacher.sh
    clones the repo -- NOT the repo root)."""
    from PIL import Image
    import numpy as np

    vacher_dir = str(Path(vacher_root) / "texture-synthesis-algorithm")
    cwd = os.getcwd()
    os.chdir(vacher_dir)
    if vacher_dir not in sys.path:
        sys.path.insert(0, vacher_dir)
    for mod in [m for m in list(sys.modules) if m.startswith(("models", "options"))]:
        del sys.modules[mod]
    from options.base_options import BaseOptions
    from models import create_model, utils

    argv_bak = sys.argv
    sys.argv = ["run_synthesis.py", "--input_tex_1", str(path_a), "--input_tex_2", str(path_b),
                "--weight_1", str(weight), "--model", model_name,
                "--n_iter", str(n_iter), "--bfgs_iter", str(bfgs_iter),
                "--shape", shape, "--seed", str(seed), "--display_freq", "100000"]
    try:
        opt = BaseOptions().parse()
        m = create_model(opt)
        m.get_net_and_loss()
        for _ in range(opt.n_iter + 1):
            m.optimize_parameters()
        arr = utils.tensor2im(m.output_tex.data.clamp_(0, 1))
        return Image.fromarray(arr.astype(np.uint8)).convert("RGB")
    finally:
        sys.argv = argv_bak
        os.chdir(cwd)


def build_128px_reference(dtd_root: Path, out_dir: Path, cats: list[str], per_category: int):
    """Cell 20's ad-hoc 128px DTD reference: center-crop square, LANCZOS to
    128px. `per_category` stands in for the archive's own `P26_REF_CAP` /
    len(cats) computation, which this port could not recover exactly (see
    module docstring) -- pass --ref-per-category to match a known value."""
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for cat in cats:
        cdir = dtd_root / cat
        if not cdir.is_dir():
            continue
        for f in sorted(os.listdir(cdir))[:per_category]:
            if not f.lower().endswith((".jpg", ".png")):
                continue
            img = Image.open(cdir / f).convert("RGB")
            s = min(img.size)
            l, t = (img.width - s) // 2, (img.height - s) // 2
            img.crop((l, t, l + s, t + s)).resize((FID_RES, FID_RES), Image.LANCZOS).save(
                out_dir / f"{cat}_{f.rsplit('.', 1)[0]}.png"
            )
            n += 1
    print(f"[vacher_50] 128px reference: {n} images -> {out_dir}")
    return out_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cnt-root", required=True, help="path to the cloned+checked-out CNT repo (install/cnt.sh)")
    ap.add_argument("--vacher-root", required=True, help="path to the cloned Vacher repo (install/vacher.sh)")
    ap.add_argument("--dtd-root", required=True, help="DTD images/ dir")
    ap.add_argument("--out", required=True, help="where to render vacher50/<method>/{k:04d}.png")
    ap.add_argument("--data-root", required=True, help="where the 128px reference and fid_by_method.json are written")
    ap.add_argument("--n-pairs", type=int, default=50, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--ref-per-category", type=int, default=20,
                     help="images per DTD category in the ad-hoc 128px reference; the archive's exact "
                          "P26_REF_CAP value could not be recovered from the cell actually read (see module docstring)")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    dtd_root = Path(args.dtd_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    methods = list(OURS_RULES) + ["recon"] + VACHER_MODELS
    for m in methods:
        (out / m).mkdir(exist_ok=True)

    pairs = sample_50_pairs(dtd_root, args.n_pairs)
    (out / "manifest.json").write_text(
        __import__("json").dumps(dict(seed=4242, n=len(pairs),
                                       pairs=[{k: str(v) for k, v in p.items() if k != "pathA" and k != "pathB"} for p in pairs]))
    )

    cnt = CNTModel(args.cnt_root, device=args.device)

    for i, pair in enumerate(pairs):
        k = pair["k"]
        imgA, imgB = cnt.load_image(pair["pathA"]), cnt.load_image(pair["pathB"])
        d = cnt.build_pair(imgA, imgB)

        recon_fp = out / "recon" / f"{k:04d}.png"
        if not recon_fp.exists():
            cnt.to_pil(cnt.field_linear(cnt.build_pair(imgA, imgA), 0.0)).save(recon_fp)

        for method, rule in OURS_RULES.items():
            fp = out / method / f"{k:04d}.png"
            if fp.exists():
                continue
            decoded = matching.interpolate(cnt, d, rule, 0.5, seed=k, eps=0.05, n_sub=4096)
            cnt.to_pil(decoded).save(fp)

        for vm in VACHER_MODELS:
            fp = out / vm / f"{k:04d}.png"
            if fp.exists():
                continue
            try:
                img = vacher_interp(args.vacher_root, pair["pathA"], pair["pathB"], vm)
                img.save(fp)
            except Exception as e:
                print(f"[vacher_50] pair {k} {vm} FAILED: {type(e).__name__}: {str(e)[:160]}")

        if (i + 1) % 10 == 0 or (i + 1) == len(pairs):
            print(f"[vacher_50] {i + 1}/{len(pairs)} pairs rendered")

    print("[vacher_50] rendering done; scoring (Cell P30's recipe: common-n resample to 128px, FID vs an ad-hoc DTD reference) ...")
    from rescore import Extractor  # noqa: E402  (deliberately imported late -- torch/timm only needed for scoring)

    data_root = Path(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    ext = Extractor(device=args.device)

    cats = sorted(c for c in os.listdir(dtd_root) if (dtd_root / c).is_dir())
    ref_dir = build_128px_reference(dtd_root, data_root / "vacher50" / "ref128", cats, args.ref_per_category)

    from PIL import Image
    ref_pils = [Image.open(p) for p in sorted(ref_dir.glob("*.png"))]
    ref_feats = ext.inc_feats(ref_pils)

    rng = random.Random(55)  # cell 20, verbatim
    file_lists = {m: sorted((out / m).glob("*.png")) for m in methods}
    n_common = min(len(v) for v in file_lists.values())
    print(f"[vacher_50] set sizes: " + ", ".join(f"{m}:{len(v)}" for m, v in file_lists.items()) +
          f"  (common n = {n_common})")

    fid_by_method = {}
    for method, files in file_lists.items():
        sample = rng.sample(files, n_common) if n_common else []
        pils = [Image.open(f).convert("RGB").resize((FID_RES, FID_RES)) for f in sample]
        if not pils:
            continue
        feats = ext.inc_feats(pils)
        fid_by_method[method] = fid_score(feats, ref_feats)

    out_json = data_root / "vacher50" / "fid_by_method.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(__import__("json").dumps(dict(n_common=n_common, ref_per_category=args.ref_per_category,
                                                        fid_by_method=fid_by_method), indent=2))
    print(f"[vacher_50] wrote {out_json}")
    for m, fid in fid_by_method.items():
        print(f"  {m:14s} {fid:8.2f}")
    if "recon" in fid_by_method:
        print("\n[vacher_50] delta over the reconstruction floor:")
        for m, fid in fid_by_method.items():
            if m != "recon":
                print(f"  {m:14s} {fid - fid_by_method['recon']:+8.1f}")
    print("\n[vacher_50] NOTE: these numbers are a re-implementation of Cell P30's documented protocol, not")
    print("[vacher_50]       a byte-exact replay of the archived run (see module docstring for why); compare")
    print("[vacher_50]       shape/ordering against the paper's 268.3/284.6/318.4/... row, not exact values.")


if __name__ == "__main__":
    main()
