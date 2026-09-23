#!/usr/bin/env python3
"""Tier 3: renders tab:app-primitives (supplement), CNT's Gaussian-primitive
matching study -- one-to-one Hungarian assignment of the sparse primitives
themselves (not the dense per-cell field texton_matching.matching operates
on), under Position (P) / Appearance (A) / mixed (PA) cost, fixed vs moving
layout, plus a soft entropic bridge (E4) that connects the primitive-level
matching back to the paper's actual dense soft-OT operator.

Ported from `CNT_correspondence_experiments.ipynb`: cell 2 (the element API,
cost construction, fixed/moving decoders -- see texton_matching/primitives.py,
which this script calls into), cell 8 ("E1 MAIN MATRIX": {P,A,PA} x
{morph,fixA} at t=0.5, scored with the canonical bundle -- this script
renders exactly the 5 of these 6 combinations tab:app-primitives actually
uses; fixB is part of the notebook's own direction-symmetry validation and
is not rendered here), and cell 13 ("E4 BRIDGE TO THE ACTUAL OPERATOR":
Gaussian-level entropic appearance matching on an eps grid, picking the eps
whose retained variance is closest to dense soft-OT's).

NOT ported (validation/robustness machinery for the notebook's own internal
protocol, confirmed via docs/INVENTORY.md's claims map to feed no paper macro):
E2a latent counterfactuals, E2b real-image replication, E3 corrupt-the-cue,
the 24-pair sensitivity sweep, the 80-pair replication set, and the timing
batch.

Calibration caveat: the notebook calibrates cost scales (s_pos, s_app) on a
20-pair set disjoint from its 120-pair main set (`CAL`, drawn from a larger
pool this package doesn't have the manifest for -- docs/INVENTORY.md's read of
the saved cells doesn't preserve the exact pool). This script calibrates
from --calibration-manifest if given, else from the SAME --n-pairs pairs
being matched -- a reasonable approximation, not a byte-identical
reproduction of the notebook's disjoint calibration split. The scales only
rescale the mixed-cost combination weight; they do not change what P-only
or A-only assignments are (those never look at the other cost's scale).

Requires: install/scoring.sh and install/cnt.sh (a GPU is strongly
recommended -- this is not run in this environment; see docs/PROVENANCE.md). Needs
torch, scipy and rescore.py's Extractor in the SAME process (unlike the
other Tier-3 scripts, which subprocess into rescore.py at the end, this one
needs rescore.Extractor inline to build the custom multi-arm feature caches
tab:app-primitives needs -- rescore.py's own generic rescorer explicitly
does not cover this table; see its module docstring).

Usage:
    python experiments/primitives_120.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --dense-images RENDERED/tm_scale1000 --out RENDERED/correspondence \\
        --data-root OUT --n-pairs 120
    python experiments/primitives_120.py --cnt-root ../cnt-siga24 \\
        --manifest RENDERED/manifest.json --dtd-root ../dtd/images \\
        --out /tmp/smoke/correspondence --data-root /tmp/smoke_scored --n-pairs 5
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
from texton_matching import matching, primitives as prim

# tab:app-primitives' 5 macros: {cost}_{layout} -> macro suffix, matching
# score_only.py's `arms` dict exactly (tab:app-primitives-120 section).
ARMS = {"P_morph": "GEKIDmorphP", "A_morph": "GEKIDmorphA",
        "P_fixA": "GEKIDfixP", "A_fixA": "GEKIDfixA", "PA_fixA": "GEKIDfixPA"}
CELLS1 = [("P", "morph"), ("A", "morph"), ("P", "fixA"), ("A", "fixA"), ("PA", "fixA")]

# tab:app-primitives' dense-OT / dense-exact reference rows re-used from an
# existing cnt_1000.py render, at the same pairs -- E4's job is to check
# whether the Gaussian-level bridge is in the same "how much detail
# survives" regime as these, not to re-render them.
DENSE_RULES = {"ot": "GEKIDdenseOT"}  # only the rule score_only.py actually reads back out of dense.npz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnt-root", required=True)
    ap.add_argument("--manifest", required=True, help="JSON with a 'pairs' list of {k,cA,fA,cB,fB}")
    ap.add_argument("--dtd-root", required=True)
    ap.add_argument("--calibration-manifest", default=None, help="optional separate manifest for cost-scale calibration; default: reuse --n-pairs")
    ap.add_argument("--dense-images", default=None, help="tm_scale1000/ dir from an existing cnt_1000.py render, for the dense-OT reference row (GEKIDdenseOT); skipped if not given")
    ap.add_argument("--out", required=True, help="where to write correspondence/{feats/{E1,E4,dense}.npz, assignment_metrics.csv}")
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--n-pairs", type=int, default=120)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--run-score-only", action="store_true")
    args = ap.parse_args()

    from PIL import Image
    import numpy as np
    from rescore import Extractor  # same-process import; see module docstring

    out = Path(args.out)
    (out / "feats").mkdir(parents=True, exist_ok=True)

    manifest = json.loads(Path(args.manifest).read_text())["pairs"][: args.n_pairs]
    dtd_root = Path(args.dtd_root)
    cnt = CNTModel(args.cnt_root, device=args.device)
    ext = Extractor(device=args.device)

    def load_pair_image(cat, fn):
        return cnt.load_image(Image.open(dtd_root / cat / fn).convert("RGB"))

    def get_elements(pair):
        A = load_pair_image(pair["cA"], pair["fA"])
        B = load_pair_image(pair["cB"], pair["fB"])
        d = cnt.build_pair(A, B)
        return d, prim.elements(d["blob_a"]), prim.elements(d["blob_b"])

    cal_source = json.loads(Path(args.calibration_manifest).read_text())["pairs"] if args.calibration_manifest else manifest
    scales = prim.calibrate_scales(cnt, [p["k"] for p in cal_source], lambda k: get_elements(next(p for p in cal_source if p["k"] == k))[1:])
    print(f"[primitives_120] calibrated cost scales: {scales}")

    E1, E4, DENSE = {}, {}, {}
    arows = []

    for i, pair in enumerate(manifest):
        k = pair["k"]
        d, EA, EB = get_elements(pair)
        asg = {}
        for cost in ("P", "A", "PA"):
            a, Cp, Ca = prim.solve_cost(EA, EB, cost, scales)
            asg[cost] = a
            arows.append(dict(k=k, cost=cost, n_matched=int(len(a["r"])), nA=a["nA"], nB=a["nB"],
                               A_cost=float(Ca[a["r"], a["c"]].mean() / scales["s_app"]),
                               G_cost=float(Cp[a["r"], a["c"]].mean() / scales["s_pos"])))

        for cost, layout in CELLS1:
            arm = f"{cost}_{layout}"
            if layout == "morph":
                decoded = prim.decode_moving(cnt, d, EA, EB, asg[cost], 0.5)
            else:
                decoded = prim.decode_fixed(cnt, d, "a", EA, EB, asg[cost], 0.5)
            pil = cnt.to_pil(decoded)
            fi = ext.inc_feats([pil])[0]
            fd = ext.dino_feats([pil])[0]
            E1[f"{arm}|{k}|inc"] = fi
            E1[f"{arm}|{k}|dino"] = fd

        # E4: Gaussian-level entropic (soft) appearance bridge, fixed layout,
        # picking the eps whose retained variance matches the dense soft-OT
        # rule's retained variance (computed via texton_matching.matching's
        # canonical field(), the same machinery cnt_1000.py's "soft_ot" row uses).
        _, Cp0, Ca0 = prim.solve_cost(EA, EB, "A", scales)  # reuses cost_mats via solve_cost's Cp/Ca cache
        fd_dense = matching.field(cnt, d, "soft_ot", k)
        dense_var_ret = float(fd_dense["U"].double().var(0).sum() / fd_dense["Y"].double().var(0).sum())
        best_eps, best_gap, best_Fstar, best_info = None, None, None, None
        for eps in prim.EPS_GRID:
            Fstar, info = prim.gauss_sinkhorn_primitive_map(EA, EB, Ca0, eps, scales["s_app"])
            gap = abs(info["var_ret"] - dense_var_ret)
            if best_gap is None or gap < best_gap:
                best_eps, best_gap, best_Fstar, best_info = eps, gap, Fstar, info
        decoded = prim.decode_fixed_feats(cnt, d, "a", EA, best_Fstar, EB["bg"], 0.5, EA["ptf"].shape[-1])
        pil = cnt.to_pil(decoded)
        E4[f"gA_sink{best_eps}_fixA|{k}|inc"] = ext.inc_feats([pil])[0]
        E4[f"gA_sink{best_eps}_fixA|{k}|dino"] = ext.dino_feats([pil])[0]

        if args.dense_images:
            for rule in DENSE_RULES:
                fp = Path(args.dense_images) / rule / f"{int(k):04d}.png"
                if fp.exists() and f"{rule}|{k}|inc" not in DENSE:
                    pil_d = Image.open(fp).convert("RGB")
                    DENSE[f"{rule}|{k}|inc"] = ext.inc_feats([pil_d])[0]
                    DENSE[f"{rule}|{k}|dino"] = ext.dino_feats([pil_d])[0]

        if (i + 1) % 20 == 0 or (i + 1) == len(manifest):
            print(f"[primitives_120] {i + 1}/{len(manifest)} pairs done (E4 eps this pair: {best_eps})")

    np.savez(out / "feats" / "E1.npz", **E1)
    np.savez(out / "feats" / "E4.npz", **E4)
    if DENSE:
        np.savez(out / "feats" / "dense.npz", **DENSE)
    else:
        print("[primitives_120] --dense-images not given (or 'ot' rule missing there); "
              "GEKIDdenseOT will read as NO FILE ROW until you run cnt_1000.py and pass --dense-images")

    import pandas as pd
    pd.DataFrame(arows).to_csv(out / "assignment_metrics.csv", index=False)
    print(f"[primitives_120] wrote {out / 'feats' / 'E1.npz'}, E4.npz"
          + (", dense.npz" if DENSE else "") + f", {out / 'assignment_metrics.csv'}")

    data_root = Path(args.data_root)
    (data_root / "correspondence" / "feats").mkdir(parents=True, exist_ok=True)
    import shutil
    for name in ("E1.npz", "E4.npz") + (("dense.npz",) if DENSE else ()):
        shutil.copy(out / "feats" / name, data_root / "correspondence" / "feats" / name)
    shutil.copy(out / "assignment_metrics.csv", data_root / "correspondence" / "assignment_metrics.csv")

    if args.run_score_only:
        subprocess.run([sys.executable, str(PACKAGE_ROOT / "experiments" / "score_only.py"),
                         "--data-root", str(data_root)], check=True)


if __name__ == "__main__":
    main()
