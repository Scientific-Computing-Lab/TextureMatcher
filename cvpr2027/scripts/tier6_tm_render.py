#!/usr/bin/env python3
# Tier 6 (every rule in every model). Texture Mixer, 1,000 pairs, t = .5.
# TF side only (run as a SUBPROCESS: the TF1 shim must not share a process with torch). Two modes:
#   --mode encode   : encode every endpoint pair (tm_scale1000/A|B/<k>.png) -> <work>/lat_<k>.npz (zg, zl for A and B)
#   --mode generate : decode <work>/mid_<rule>_<k>.npy (the t=.5 local latent, computed on the GPU by tier6_tm_pair.py)
#                     with zg_mid = (zgA + zgB)/2 -> tm_scale1000/tmc1000/<rule>/<k>.png
# Same encode/generate path as experiments/tm_1000.py (which rendered the existing lerp / mean / ot_r0.03 folders).
import argparse, json, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, "/content/package/experiments"); sys.path.insert(0, "/content/package")
from tm_1000 import load_texture_mixer

ap = argparse.ArgumentParser()
ap.add_argument("--tm-root", required=True); ap.add_argument("--base", required=True); ap.add_argument("--work", required=True)
ap.add_argument("--mode", required=True, choices=["encode", "generate"]); ap.add_argument("--n", type=int, default=1000)
ap.add_argument("--rules", default="gaussian,ot_r0.003,hard")
a = ap.parse_args()
base, work = Path(a.base), Path(a.work); work.mkdir(parents=True, exist_ok=True)
man = json.loads((base / "manifest.json").read_text())["pairs"][: a.n]
Es_zg, Es_zl, Gs = load_texture_mixer(Path(a.tm_root))

def prep(pil):
    x = np.asarray(pil.convert("RGB").resize((128, 128)), dtype=np.float32)
    return (x / 127.5 - 1.0).transpose(2, 0, 1)[None]
def gen(zg, zl):
    zg_t = np.tile(zg, (1, 1, zl.shape[2], zl.shape[3])); arr = Gs.run(zg_t, zl, return_as_list=True)[0][0]
    return Image.fromarray(np.clip((arr.transpose(1, 2, 0) + 1) * 127.5, 0, 255).astype(np.uint8))

t0 = time.time()
for i, p in enumerate(man):
    k = f"{int(p['k']):04d}"
    if a.mode == "encode":
        fp = work / f"lat_{k}.npz"
        if fp.exists(): continue
        xa = prep(Image.open(base / "A" / f"{k}.png")); xb = prep(Image.open(base / "B" / f"{k}.png"))
        np.savez(fp, gA=Es_zg.run(xa, return_as_list=True)[0], lA=Es_zl.run(xa, return_as_list=True)[0],
                 gB=Es_zg.run(xb, return_as_list=True)[0], lB=Es_zl.run(xb, return_as_list=True)[0])
    else:
        z = np.load(work / f"lat_{k}.npz"); zg_mid = 0.5 * (z["gA"] + z["gB"])
        for r in a.rules.split(","):
            out = base / "tmc1000" / r / f"{k}.png"
            if out.exists(): continue
            out.parent.mkdir(parents=True, exist_ok=True)
            gen(zg_mid, np.load(work / f"mid_{r}_{k}.npy").astype(np.float32)).save(out)
    if (i + 1) % 200 == 0 or i + 1 == len(man):
        print(f"[tier6 {a.mode}] {i + 1}/{len(man)}  {(time.time() - t0) / 60:.1f} min", flush=True)
print(f"[tier6 {a.mode}] done")
