#!/usr/bin/env python3
"""Tier 3: times the per-stage wall clock of CNT's interpolation and of
Texture Mixer on the 120-pair subset (`tab:runtime`), one protocol per the
paper's caption.

IMPORTANT LIMITATION, unlike every other Tier-3 script in this package:
timings are hardware-specific and NOT reproducible across machines. The
paper's own numbers were measured on one A100 (supplement.tex: "Recorded
stage timings in seconds, 120 pairs on one A100 under the same protocol").
Running this script on different hardware will NOT match `evidence/
timing_120.csv` / `evidence/timing_120_tm.csv`, and that mismatch is
expected, not a bug -- this script exists so a reviewer with comparable
hardware (or the original authors, on the original machine) has something
runnable, not so its output can be diffed against the archive the way
cnt_1000.py's or tm_1000.py's pixel outputs can be.

Also note (docs/INVENTORY.md §0 item 7): the paper's full `tab:runtime` mixes
protocols beyond what this script covers. `VacherWSec` comes from a
SEPARATE 20-pair run (`paper_completion/timing_n20.csv`, see
experiments/vacher_50.py's docstring), not this 120-pair protocol.
`GPTsec` is Azure API latency from `evidence/gpt_image_1_5_experiment/`'s
run report, not local compute. This script reproduces only the CNT/TM
columns: `EncodeSec`, `DecSec`, `OTTransportSec`, `HardAssignSec`,
`TMEncSec`, `TMInterpSec` (all directly the median of the matching raw
column below).

`DecSecLow` (the 128px decode timing, cell 8 -- "PHASE 2, CELL 5b -- OUR
SIDE at 128px") is deliberately NOT reproduced here, for two independent
reasons, not just one: (1) the archive itself never saved a comparable
file (`timing_120_ours128.csv` is missing; docs/INVENTORY.md §0 item 7 / §6
item 1 flags this number as printed-output-only even in the original
run, so there is nothing to compare against regardless); and (2) more
importantly, `texton_matching.cnt.CNTModel.FMS` is computed once in
`__init__` from the fixed module constant `IMG_SIZE=256` (see cnt.py),
not from the actual size of whatever image `load_image()` loads -- the
notebook's cell 8 builds an entirely separate `FMS128` pyramid for its
128px pass precisely because the feature-map pyramid depends on
resolution. Reusing `CNTModel.grids()` / `.build_style_maps()` /
`.decode_field()` (all `self.FMS`-dependent) against 128px-loaded images
would silently mismatch or crash. Supporting this correctly needs
`CNTModel` itself to take a resolution-aware FMS, which is out of this
script's scope; flagging it here rather than shipping a broken flag.

Ported verbatim (read directly, not reconstructed from a description)
from `notebooks_raw/timing_120_pairs (1).ipynb`: cell 6 ("PHASE 2, CELL 5
-- OUR SIDE -- 120 pairs, per-stage wall clock, medians") for the CNT
`stages()` function and its `timing_120.csv` column layout (k, enc, ot,
hard, dec, pix, ot_midpoint, ot_interp, ot_path11, hard_midpoint,
pix_midpoint, pix_path11); cell 3 ("PHASE 1, CELL 3 -- Texture Mixer
timing") for the TM side and `timing_120_tm.csv`'s layout (k, enc, gen,
midpoint, path11); cell 8 ("PHASE 2, CELL 5b -- OUR SIDE at 128px") for
the optional low-resolution decode pass. The notebook times raw CNT
internals directly (`model.encode`, `model.splat`, hand-built style-map
pyramids); this port instead calls the equivalent public
texton_matching.cnt.CNTModel / texton_matching.matching methods so the
timed stage boundaries match conceptually (encode / OT-solve+NN-extend /
Hungarian-solve+NN-extend / decode / pixel-blend), even though the exact
sequence of internal torch ops is not byte-identical to the archived
notebook cell -- if you need the literal original internals timed, read
that cell directly; this is a faithful but not verbatim reimplementation
for this one script only (every other Tier-3 script in this package IS a
verbatim port; timing is the exception, because the target here is
"time our own public API," not "reproduce a saved number").

Warm-up: the notebook runs the first 3 pairs untimed before the timed
loop (cuDNN autotune, CUDA allocator warm-up) -- reproduced here via
--warmup (default 3).

Requires: install/scoring.sh and install/cnt.sh and (for the TM side)
install/texture_mixer.sh -- run the CNT and TM halves as two separate
invocations in their respective environments, same as the archive's own
two-phase notebook (a scripted restart between TF1 and torch).

Usage:
    # CNT side (torch env):
    python experiments/runtime_120.py cnt --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --out OUT --n-pairs 120
    # Texture Mixer side (texton-matching-tm env, separate process):
    python experiments/runtime_120.py tm --tm-root ../TextureMixer \\
        --manifest RENDERED/manifest.json --out OUT --n-pairs 120
    # smoke test (either side):
    python experiments/runtime_120.py cnt --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --out /tmp/smoke --n-pairs 5 --warmup 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT))

NSUB = 4096
N_EXACT = 1024


def _cnt_stage_timing(cnt, A_path: Path, B_path: Path, seed: int):
    """One pair's per-stage wall clock, CNT side. Mirrors
    timing_120_pairs (1).ipynb cell 6's `stages()`: image load/resize is
    NOT timed (I/O, identical across methods); enc/ot/hard/dec/pix are.
    """
    import torch
    from scipy.optimize import linear_sum_assignment
    from texton_matching import matching

    def tic():
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        return time.perf_counter()

    imgA, imgB = cnt.load_image(A_path), cnt.load_image(B_path)

    t = tic()
    d = cnt.build_pair(imgA, imgB)
    t_enc = tic() - t

    L, C, H, W, sf, tf = cnt.grids(d)
    N = sf.shape[0]
    g = torch.Generator(device=sf.device).manual_seed(seed)
    i_s = torch.randperm(N, generator=g, device=sf.device)[:NSUB]
    i_t = torch.randperm(N, generator=g, device=sf.device)[:NSUB]

    t = tic()
    with torch.no_grad():
        P, _ = matching.sinkhorn_plan(sf[i_s], tf[i_t], eps=0.05)
        tt = (P / (P.sum(1, keepdim=True) + 1e-10)) @ tf[i_t]
    nn = torch.cdist(sf, sf[i_s]).argmin(1)
    U = tt[nn]
    t_ot = tic() - t

    t = tic()
    js, jt = i_s[:N_EXACT], i_t[:N_EXACT]
    Cm = torch.cdist(sf[js], tf[jt]).pow(2).cpu().numpy()
    r, c = linear_sum_assignment(Cm)
    th = torch.empty(N_EXACT, C, device=sf.device)
    th[torch.as_tensor(r, device=sf.device)] = tf[jt][torch.as_tensor(c, device=sf.device)]
    nnh = torch.cdist(sf, sf[js]).argmin(1)
    Uh = th[nnh]
    t_hard = tic() - t

    t = tic()
    Z = 0.5 * sf + 0.5 * U
    _ = cnt.decode_field(d, Z, L, H, W, C)
    t_dec = tic() - t

    t = tic()
    sa = cnt.build_style_maps(d["bf_a"], d["si_a"])
    sb = cnt.build_style_maps(d["bf_b"], d["si_b"])
    _ = {s: 0.5 * sa[s] + 0.5 * sb[s] for s in set(cnt.FMS)}
    t_pix = tic() - t

    return dict(enc=t_enc, ot=t_ot, hard=t_hard, dec=t_dec, pix=t_pix)


def run_cnt(args):
    from texton_matching.cnt import CNTModel

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())["pairs"][: args.n_pairs]
    ab_dir = manifest_path.parent

    cnt = CNTModel(args.cnt_root, device=args.device)

    for pair in manifest[: args.warmup]:
        k = pair["k"]
        A_path, B_path = ab_dir / "A" / f"{k:04d}.png", ab_dir / "B" / f"{k:04d}.png"
        if A_path.exists() and B_path.exists():
            _cnt_stage_timing(cnt, A_path, B_path, seed=0)
    print(f"[runtime_120] warm-up done ({args.warmup} pairs, untimed)")

    rows = []
    for i, pair in enumerate(manifest):
        k = pair["k"]
        A_path, B_path = ab_dir / "A" / f"{k:04d}.png", ab_dir / "B" / f"{k:04d}.png"
        if not (A_path.exists() and B_path.exists()):
            print(f"[runtime_120] WARNING: {A_path} / {B_path} not found; skipping k={k}")
            continue
        s = _cnt_stage_timing(cnt, A_path, B_path, seed=k)
        s["k"] = k
        rows.append(s)
        if (i + 1) % 50 == 0 or (i + 1) == len(manifest):
            print(f"[runtime_120] {i + 1}/{len(manifest)} pairs timed")

    T = pd.DataFrame(rows)
    T["ot_midpoint"] = T.enc + T.ot + T.dec
    T["ot_interp"] = T.ot + T.dec
    T["ot_path11"] = T.enc + T.ot + 11 * T.dec
    T["hard_midpoint"] = T.enc + T.hard + T.dec
    T["pix_midpoint"] = T.enc + T.pix + T.dec
    T["pix_path11"] = T.enc + T.pix + 11 * T.dec

    out = Path(args.out) / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    T.to_csv(out / "timing_120.csv", index=False)

    med = T.median(numeric_only=True)
    print(f"[runtime_120] n={len(T)} | median seconds (compare to evidence/timing_120.csv, SAME hardware only):")
    for col, macro in [("enc", "EncodeSec"), ("dec", "DecSec"), ("ot", "OTTransportSec"), ("hard", "HardAssignSec")]:
        print(f"  {col:6} (~{macro:16}) {med[col]:.3f}")
    print(f"[runtime_120] wrote {out / 'timing_120.csv'}")


def run_tm(args):
    """Texture Mixer side. Must run in install/texture_mixer.sh's
    TF1-on-TF2-shimmed environment; reuses experiments/tm_1000.py's
    `load_texture_mixer` loader rather than duplicating the shim.
    """
    import importlib.util

    tm1000_path = PACKAGE_ROOT / "experiments" / "tm_1000.py"
    spec = importlib.util.spec_from_file_location("tm_1000", tm1000_path)
    tm_1000 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tm_1000)

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())["pairs"][: args.n_pairs]
    ab_dir = manifest_path.parent

    Es_zg, Es_zl, Gs = tm_1000.load_texture_mixer(Path(args.tm_root))
    TM_RES, LATENT_IDX = 128, 0

    def tm_prep(pil):
        a = np.asarray(pil.convert("RGB").resize((TM_RES, TM_RES)), dtype=np.float32)
        return (a / 127.5 - 1.0).transpose(2, 0, 1)[None]

    def enc_arr(x):
        return Es_zg.run(x, return_as_list=True)[LATENT_IDX], Es_zl.run(x, return_as_list=True)[LATENT_IDX]

    def gen_arr(zg, zl):
        zg_t = np.tile(zg, (1, 1, zl.shape[2], zl.shape[3]))
        return Gs.run(zg_t, zl, return_as_list=True)[0]

    # all I/O + preprocessing before the clock, exactly like the notebook
    prepped = {}
    for pair in manifest:
        k = pair["k"]
        A_path, B_path = ab_dir / "A" / f"{k:04d}.png", ab_dir / "B" / f"{k:04d}.png"
        if A_path.exists() and B_path.exists():
            prepped[k] = (tm_prep(Image.open(A_path)), tm_prep(Image.open(B_path)))

    ks = list(prepped)
    for k in ks[: args.warmup]:
        a, b = prepped[k]
        (zgA, zlA), (zgB, zlB) = enc_arr(a), enc_arr(b)
        gen_arr(0.5 * (zgA + zgB), 0.5 * (zlA + zlB))
    print(f"[runtime_120] TM warm-up done ({min(args.warmup, len(ks))} pairs, untimed)")

    rows = []
    for i, k in enumerate(ks):
        a, b = prepped[k]
        t = time.perf_counter()
        (zgA, zlA), (zgB, zlB) = enc_arr(a), enc_arr(b)
        t_enc = time.perf_counter() - t
        t = time.perf_counter()
        gen_arr(0.5 * (zgA + zgB), 0.5 * (zlA + zlB))
        t_gen = time.perf_counter() - t
        rows.append(dict(k=k, enc=t_enc, gen=t_gen, midpoint=t_enc + t_gen, path11=t_enc + 11 * t_gen))
        if (i + 1) % 50 == 0 or (i + 1) == len(ks):
            print(f"[runtime_120] TM {i + 1}/{len(ks)} pairs timed")

    T = pd.DataFrame(rows)
    out = Path(args.out) / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    T.to_csv(out / "timing_120_tm.csv", index=False)
    med = T.median(numeric_only=True)
    print(f"[runtime_120] TM n={len(T)} | enc (~TMEncSec) {med.enc:.3f}s | gen (~TMInterpSec) {med.gen:.3f}s")
    print(f"[runtime_120] wrote {out / 'timing_120_tm.csv'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="side", required=True)

    cnt_ap = sub.add_parser("cnt", help="time the CNT side (torch env)")
    cnt_ap.add_argument("--cnt-root", required=True)
    cnt_ap.add_argument("--manifest", required=True, help="pairs_120/pairs.csv-equivalent manifest.json, with an A/B dir alongside it")
    cnt_ap.add_argument("--out", required=True, help="where to write evidence/timing_120.csv")
    cnt_ap.add_argument("--n-pairs", type=int, default=120)
    cnt_ap.add_argument("--warmup", type=int, default=3)
    cnt_ap.add_argument("--device", default="cuda")

    tm_ap = sub.add_parser("tm", help="time the Texture Mixer side (texton-matching-tm env)")
    tm_ap.add_argument("--tm-root", required=True)
    tm_ap.add_argument("--manifest", required=True)
    tm_ap.add_argument("--out", required=True, help="where to write evidence/timing_120_tm.csv")
    tm_ap.add_argument("--n-pairs", type=int, default=120)
    tm_ap.add_argument("--warmup", type=int, default=3)

    args = ap.parse_args()
    if args.side == "cnt":
        run_cnt(args)
    else:
        run_tm(args)


if __name__ == "__main__":
    main()
