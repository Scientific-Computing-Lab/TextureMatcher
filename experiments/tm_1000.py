#!/usr/bin/env python3
"""Tier 3: renders Table 1's Texture Mixer block (n=1,000 by default):
native positional blending ("lerp"), target-mean coupling ("mean"), and
soft-OT coupling at eps=0.03*median-cost ("ot_r0.03") in Texture Mixer's
own 32x32 local latent.

Runs in the texton-matching-tm conda environment (install/environment_tm.yml
+ install/texture_mixer.sh) -- NOT the same environment/process as the CNT
side, because this substitutes a global `tensorflow` module. Ported from
finishing_experiments.ipynb "PHASE 1, CELL 3" (TM coupling ablation) with
the pair set widened from 120 to --n-pairs.

Requires: install/texture_mixer.sh (a GPU is strongly recommended -- this
is not run in this environment; see README).

Usage (inside the texton-matching-tm env):
    python experiments/tm_1000.py --tm-root ../TextureMixer \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out RENDERED --data-root OUT --n-pairs 1000
    python experiments/tm_1000.py --tm-root ../TextureMixer \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out /tmp/smoke --data-root /tmp/smoke_scored --n-pairs 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
import importlib
import importlib.util
import importlib.machinery
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def load_texture_mixer(tm_root: Path):
    """The exact TF1-on-TF2 shim from tm_scale1000_headtohead.ipynb PHASE 1
    CELL 1 / install/texture_mixer.sh. Returns (Es_zg, Es_zl, Gs, tf_slim's
    tf1 module) after loading the earth-texture checkpoint."""
    sys.path.insert(0, str(tm_root))

    if "imp" not in sys.modules:
        _imp = types.ModuleType("imp")
        def _load_source(name, pathname, file=None):
            spec = importlib.util.spec_from_file_location(name, pathname)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod
        def _find_module(name, path=None):
            spec = importlib.machinery.PathFinder().find_spec(name, path)
            if spec is None:
                raise ImportError(name)
            return (None, spec.origin, (".py", "r", 1))
        _imp.load_source = _load_source
        _imp.find_module = _find_module
        _imp.new_module = lambda n: types.ModuleType(n)
        _imp.reload = importlib.reload
        _imp.acquire_lock = lambda: None
        _imp.release_lock = lambda: None
        _imp.PY_SOURCE = 1
        sys.modules["imp"] = _imp

    import tensorflow as _tf2
    tf1 = _tf2.compat.v1
    tf1.disable_eager_execution()
    tf1.disable_v2_behavior()
    tf1.logging.set_verbosity(tf1.logging.ERROR)
    if not hasattr(tf1, "Dimension"):
        tf1.Dimension = getattr(_tf2, "Dimension", int)

    import tf_slim as _slim
    _contrib = types.ModuleType("tensorflow.contrib")
    _contrib.slim = _slim
    _contrib.framework = _slim
    _contrib.layers = _slim
    sys.modules["tensorflow.contrib"] = _contrib
    sys.modules["tensorflow.contrib.slim"] = _slim
    sys.modules["tensorflow.contrib.framework"] = _slim
    sys.modules["tensorflow.contrib.layers"] = _slim
    tf1.contrib = _contrib
    sys.modules["tensorflow"] = tf1

    import tfutil, misc
    sess = tfutil.create_session(force_as_default=True)
    ckpt = tm_root / "earth_texture" / "network-final.pkl"
    obj = misc.load_pkl(str(ckpt))
    nets = {getattr(o, "name", f"_{i}"): o for i, o in enumerate(obj)}
    return nets["Es_zg"], nets["Es_zl"], nets["Gs"]


def sink_log(C, eps, tol=1e-3, max_it=5000):
    """numpy log-domain Sinkhorn (finishing_experiments.ipynb PHASE 1 CELL 3)."""
    import numpy as np
    def lse(M, ax):
        mx = M.max(ax, keepdims=True)
        return (mx + np.log(np.exp(M - mx).sum(ax, keepdims=True))).squeeze(ax)
    n, m = C.shape
    la, lb = -np.log(n), -np.log(m)
    f, g = np.zeros(n), np.zeros(m)
    it = 0
    while it < max_it:
        for _ in range(50):
            f = eps * (la - lse((g[None, :] - C) / eps, 1))
            g = eps * (lb - lse((f[:, None] - C) / eps, 0))
            it += 1
        P = np.exp((f[:, None] + g[None, :] - C) / eps)
        err = max(np.abs(P.sum(1) * n - 1).max(), np.abs(P.sum(0) * m - 1).max())
        if err < tol:
            break
    return P, float(err), it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tm-root", required=True, help="path to the cloned Texture Mixer repo (install/texture_mixer.sh)")
    ap.add_argument("--manifest", required=True, help="tm_scale1000/manifest.json")
    ap.add_argument("--dtd-root", default=None, help="only needed for pairs not already covered by the canonical out/A|B layout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--n-pairs", type=int, default=1000, help="use a small number (e.g. 5) for a smoke test")
    ap.add_argument("--eps-rel", type=float, default=0.03, help="soft-OT eps as a multiple of the median pairwise cost (0.03 is the paper-matched value)")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    import numpy as np
    from PIL import Image

    manifest = json.loads(Path(args.manifest).read_text())["pairs"][: args.n_pairs]
    dtd_root = Path(args.dtd_root) if args.dtd_root else None

    Es_zg, Es_zl, Gs = load_texture_mixer(Path(args.tm_root))
    TM_RES, LATENT_IDX = 128, 0

    def tm_prep(pil):
        a = np.asarray(pil.convert("RGB").resize((TM_RES, TM_RES)), dtype=np.float32)
        return (a / 127.5 - 1.0).transpose(2, 0, 1)[None]

    def tm_to_pil(arr):
        a = np.asarray(arr)
        a = a[0] if a.ndim == 4 else a
        return Image.fromarray(np.clip((a.transpose(1, 2, 0) + 1) * 127.5, 0, 255).astype(np.uint8))

    def enc(pil):
        x = tm_prep(pil)
        return Es_zg.run(x, return_as_list=True)[LATENT_IDX], Es_zl.run(x, return_as_list=True)[LATENT_IDX]

    def gen(zg, zl):
        zg_t = np.tile(zg, (1, 1, zl.shape[2], zl.shape[3]))
        return tm_to_pil(Gs.run(zg_t, zl, return_as_list=True)[0])

    out = Path(args.out)
    for rule in ("lerp", "mean", f"ot_r{args.eps_rel}"):
        (out / "jackknife" / "tm1000" / rule).mkdir(parents=True, exist_ok=True)
    # TM's own encode-decode reconstruction of each single endpoint (zg,zl
    # from A fed straight back into Gs, and likewise for B) -- the anchors a
    # placement ("place" = d(mid,A)/(d(mid,A)+d(mid,B))) check needs. Not
    # part of Table 1's TM block itself, just infrastructure for
    # reproduce_tm.ipynb's PASS/FAIL cell.
    (out / "tm_scale1000" / "recon_A").mkdir(parents=True, exist_ok=True)
    (out / "tm_scale1000" / "recon_B").mkdir(parents=True, exist_ok=True)

    ot_rule = f"ot_r{args.eps_rel}"
    for i, pair in enumerate(manifest):
        # pair["k"] may be an int (Table 1's 1000-pair manifest) or a
        # 4-digit string like "0006" (evidence/pairs_demo.csv, so its keys
        # line up with evidence/*.csv without a lossy round-trip through int).
        k_str = f"{int(pair['k']):04d}"

        # Endpoints: prefer the canonical out/A/{k}.png, out/B/{k}.png
        # layout if it's already there (built by
        # texton_matching.data.prepare_demo_endpoints, which
        # colab/reproduce.ipynb's CNT side and colab/reproduce_tm.ipynb's
        # Texture Mixer side now BOTH call, so they render from
        # byte-identical endpoint images at the same path). Only fall back
        # to loading + resizing from raw DTD (needs --dtd-root) for pairs
        # that layout doesn't cover, e.g. the full n=1,000 protocol.
        demo_a, demo_b = out / "A" / f"{k_str}.png", out / "B" / f"{k_str}.png"
        if demo_a.exists() and demo_b.exists():
            A = Image.open(demo_a).convert("RGB")
            B = Image.open(demo_b).convert("RGB")
        else:
            if dtd_root is None:
                raise SystemExit(
                    f"no endpoint images at {demo_a} / {demo_b}, and --dtd-root was not given; "
                    f"can't build pair {k_str}'s endpoints. Either pre-build the canonical A/B "
                    f"layout (texton_matching.data.prepare_demo_endpoints) or pass --dtd-root."
                )
            A = Image.open(dtd_root / pair["cA"] / pair["fA"]).convert("RGB").resize((TM_RES, TM_RES))
            B = Image.open(dtd_root / pair["cB"] / pair["fB"]).convert("RGB").resize((TM_RES, TM_RES))

        (gA, lA), (gB, lB) = enc(A), enc(B)
        C, H, W = lA.shape[1:]
        X = lA[0].reshape(C, -1).T.astype(np.float64)
        Y = lB[0].reshape(C, -1).T.astype(np.float64)
        Cm = ((X[:, None, :] - Y[None, :, :]) ** 2).sum(-1)
        med_c = float(np.median(Cm))
        zg_mid = 0.5 * (gA + gB)

        recon_a_fp = out / "tm_scale1000" / "recon_A" / f"{k_str}.png"
        if not recon_a_fp.exists():
            gen(gA, lA).save(recon_a_fp)
        recon_b_fp = out / "tm_scale1000" / "recon_B" / f"{k_str}.png"
        if not recon_b_fp.exists():
            gen(gB, lB).save(recon_b_fp)

        targets = {"lerp": Y, "mean": np.tile(Y.mean(0), (len(X), 1))}
        P, err, it = sink_log(Cm, args.eps_rel * med_c)
        targets[ot_rule] = (P / P.sum(1, keepdims=True)) @ Y

        for rule, U in targets.items():
            fp = out / "jackknife" / "tm1000" / rule / f"{k_str}.png"
            if fp.exists():
                continue
            mid = (0.5 * X + 0.5 * U).T.reshape(1, C, H, W).astype(np.float32)
            gen(zg_mid, mid).save(fp)

        if (i + 1) % 50 == 0 or (i + 1) == len(manifest):
            print(f"[tm_1000] {i + 1}/{len(manifest)} pairs rendered")

    print("[tm_1000] rendering done.")
    print("[tm_1000] NOTE: rescore.py and score_only.py need torch/timm/torchvision, which are")
    print("[tm_1000]       deliberately NOT installed in this TF env (install/environment_tm.yml).")
    print("[tm_1000]       Switch to the scoring environment (install/scoring.sh) and run:")
    print(f"[tm_1000]         python rescore.py --images {out} --data-root {args.data_root} --table table1_tm_1000" +
          (" --run-score-only" if args.run_score_only else ""))
    if args.run_score_only:
        print("[tm_1000] --run-score-only was requested but this script cannot invoke it itself from inside")
        print("[tm_1000] the TF1-shimmed environment (importing torch here can crash the TF1 compat shim).")
        print("[tm_1000] Run the command printed above from the scoring environment instead.")


if __name__ == "__main__":
    main()
