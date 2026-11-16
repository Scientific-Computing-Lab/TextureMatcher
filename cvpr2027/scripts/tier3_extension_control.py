# Tier 3: map-extension control (does sampling plus nearest-neighbour extension explain part of the gain?).
# On the 1,000-pair CNT benchmark, render POSITIONAL pairing through the same path as soft OT:
#   pos_df  : U = Y (co-located target), decoded with decode_field (same decoder path as soft OT, no extension)
#   pos_ext : U = Y at the same seeded sample i_s, extended to all cells by the same nearest-sampled-source lookup
#             that soft OT uses (matching.field)  -> only the pairing differs from soft OT
# Compare (paired jackknife, full-reference KID) with the stored E1 features: field_linear (CNT's own positional
# path) and soft_ot. Resumable per 50-pair chunk. Run after notebook setup (cells 1, 3, restart, 1, 5).
import os, time, numpy as np, pandas as pd, torch
SMOKE = globals().get("SMOKE", True)
RUN_E1 = RUN_E2 = RUN_E3 = False
_sm = SMOKE; SMOKE = False
exec(open(f"{MT}/tier1_experiments.py").read())      # helpers only: cnt, inc128, kid, dkid, dec, pair_d, T1
SMOKE = _sm
T3 = f"{OUT}/tier3_smoke" if SMOKE else f"{OUT}/tier3"; os.makedirs(T3, exist_ok=True)
NS = MATCH_KW.get("n_sub", matching.NSUB)
TS = (0.25, 0.5, 0.75)
ALL = MAN["pairs"][:4] if SMOKE else MAN["pairs"]
CH = 2 if SMOKE else 50
t0 = time.time()
for c0 in range(0, len(ALL), CH):
    path = f"{T3}/ext_chunk_{c0:04d}.npz"
    if os.path.exists(path): continue
    feats = {}
    with torch.no_grad():
        for p in ALL[c0:c0 + CH]:
            k = int(p["k"]); d = pair_d(p)
            L, C, H, W, sf, tf = cnt.grids(d)
            i_s = matching._sub(sf.shape[0], k, "s", NS, sf.device)
            nn = torch.cdist(sf, sf[i_s]).argmin(1)
            fd_df = dict(X=sf, U=tf, L=L, C=C, H=H, W=W)
            fd_ext = dict(X=sf, U=tf[i_s][nn], L=L, C=C, H=H, W=W)
            for t in TS:
                feats.setdefault(f"pos_df@{t}", []).append(cnt.to_pil(dec(d, fd_df, t)))
                feats.setdefault(f"pos_ext@{t}", []).append(cnt.to_pil(dec(d, fd_ext, t)))
            del d, sf, tf, nn
    np.savez(path, ks=np.array([int(p["k"]) for p in ALL[c0:c0 + CH]]), **{key: inc128(v) for key, v in feats.items()})
    print(f"chunk {c0 // CH + 1}/{(len(ALL) + CH - 1) // CH} ({(time.time() - t0) / 60:.1f} min)", flush=True)

Z3 = [np.load(f"{T3}/ext_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]
F = {key: np.concatenate([z[key] for z in Z3]) for key in Z3[0].files if key != "ks"}
ks3 = np.concatenate([z["ks"] for z in Z3])
if not SMOKE:
    Z1 = [np.load(f"{T1}/e1_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), 50)]
    ks1 = np.concatenate([z["ks"] for z in Z1]); assert (ks1 == ks3).all(), "pair order mismatch"
    for key in ("field_linear", "soft_ot"):
        for t in TS: F[f"{key}@{t}"] = np.concatenate([z[f"{key}@{t}"] for z in Z1])
rows = [dict(method=m.split("@")[0], t=float(m.split("@")[1]), KIDx1e3=round(kid(v), 2)) for m, v in F.items()]
S = pd.DataFrame(rows).sort_values(["t", "method"]); S.to_csv(f"{T3}/ext_kid.csv", index=False)
D = []
if not SMOKE:
    for t in TS:
        for a, b in [("pos_df", "field_linear"), ("pos_ext", "field_linear"), ("pos_ext", "pos_df"),
                     ("soft_ot", "pos_ext"), ("soft_ot", "pos_df"), ("soft_ot", "field_linear")]:
            D.append(dict(method=a, base=b, t=t, **dkid(F[f"{a}@{t}"], F[f"{b}@{t}"])))
    D = pd.DataFrame(D); D.to_csv(f"{T3}/ext_delta_kid.csv", index=False)
print(S.to_string(index=False)); print(pd.DataFrame(D).to_string(index=False) if len(D) else "smoke ok")
