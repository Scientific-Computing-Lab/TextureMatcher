# Tier 6 scoring: every Texture Mixer rule on the 1,000 pairs, one session, the paper's canonical KID protocol
# (Inception features at 128 px, frozen 2,819-image DTD reference, unbiased KID, paired leave-one-pair-out jackknife).
# exec() in the main kernel after the v2 notebook's config (cell 1) + setup (cell 5). Writes OUT/tier6/.
import os, sys, json, numpy as np, pandas as pd
from PIL import Image
sys.path.insert(0, "/content/package")
import rescore
T6 = f"{OUT}/tier6"; os.makedirs(T6, exist_ok=True)
BASE = f"{MT}/tm_scale1000/tmc1000"
RULES6 = ["lerp", "mean", "gaussian", "ot_r0.03", "ot_r0.003", "hard"]
# pipeline check: the paper's soft OT recomputed by tier6 (first 20 pairs) vs the existing renders, mean abs pixel difference
_c = sorted(os.listdir(f"{BASE}/ot_r0.03chk")) if os.path.isdir(f"{BASE}/ot_r0.03chk") else []
if _c:
    _d = [np.abs(np.asarray(Image.open(f"{BASE}/ot_r0.03chk/{k}"), dtype=float) - np.asarray(Image.open(f"{BASE}/ot_r0.03/{k}"), dtype=float)).mean() for k in _c]
    print(f"pipeline check on {len(_c)} pairs: mean |pixel diff| = {np.mean(_d):.2f} (max {np.max(_d):.2f}) grey levels of 255")
ext = rescore.Extractor(DEV)
ref_inc = np.load(REF_INC); kyy = scoring._reference_self_term(ref_inc)
ks = sorted(set.intersection(*[set(f for f in os.listdir(f"{BASE}/{r}") if f.endswith(".png")) for r in RULES6]))
print("pairs with every rule:", len(ks))
F = {}
for r in RULES6:
    fp = f"{T6}/inc_{r}.npy"
    if os.path.exists(fp) and len(np.load(fp)) == len(ks): F[r] = np.load(fp); continue
    feats = []
    for i in range(0, len(ks), 100):
        feats.append(ext.inc_feats([Image.open(f"{BASE}/{r}/{k}").convert("RGB").resize((128, 128), Image.BICUBIC) for k in ks[i:i + 100]]))
    F[r] = np.concatenate(feats); np.save(fp, F[r])
rows = [dict(rule=r, n=len(ks), KIDx1e3=round(1e3 * scoring.kid_full(F[r], ref_inc, kyy), 2)) for r in RULES6]
def dk(a, b):
    q = scoring.paired_jackknife_delta_kid(F[a], F[b], ref_inc)
    return dict(rule=a, base=b, dKIDx1e3=round(1e3 * q.delta, 2), lo=round(1e3 * q.lo, 2), hi=round(1e3 * q.hi, 2), excl0=bool(q.excludes_zero))
deltas = [dk(r, "lerp") for r in RULES6[1:]] + [dk("ot_r0.03", "gaussian"), dk("ot_r0.003", "gaussian"), dk("ot_r0.03", "mean"),
                                               dk("ot_r0.003", "ot_r0.03"), dk("hard", "ot_r0.03")]
pd.DataFrame(rows).to_csv(f"{T6}/tm_kid.csv", index=False); pd.DataFrame(deltas).to_csv(f"{T6}/tm_delta_kid.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False)); print(pd.DataFrame(deltas).to_string(index=False))

# ---- the same rules on the paper's 120-pair subset (the pairs CNT, DINO-RAE and SD-VAE use), for the cross-model table ----
idx = [ks.index(f"{k:04d}.png") for k in EVAL_KS if f"{k:04d}.png" in ks]
print("120-subset pairs found:", len(idx))
G = {r: F[r][idx] for r in RULES6}
rows120 = [dict(rule=r, n=len(idx), KIDx1e3=round(1e3 * scoring.kid_full(G[r], ref_inc, kyy), 2)) for r in RULES6]
def dk120(a, b):
    q = scoring.paired_jackknife_delta_kid(G[a], G[b], ref_inc)
    return dict(rule=a, base=b, dKIDx1e3=round(1e3 * q.delta, 2), lo=round(1e3 * q.lo, 2), hi=round(1e3 * q.hi, 2), excl0=bool(q.excludes_zero))
d120 = [dk120(r, "lerp") for r in RULES6[1:]] + [dk120("ot_r0.03", "gaussian")]
pd.DataFrame(rows120).to_csv(f"{T6}/tm_kid_120.csv", index=False); pd.DataFrame(d120).to_csv(f"{T6}/tm_delta_kid_120.csv", index=False)
print(pd.DataFrame(rows120).to_string(index=False)); print(pd.DataFrame(d120).to_string(index=False))
