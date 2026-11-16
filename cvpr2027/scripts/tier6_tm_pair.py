# Tier 6, torch side: pairings for Texture Mixer's 32x32 local latent at t = .5, on the GPU. exec() in the main kernel
# (needs `matching` from the v2 setup cell, and WORK / MT set). Reads <WORK>/lat_<k>.npz, writes <WORK>/mid_<rule>_<k>.npy.
#   gaussian  : optimal affine map between Gaussians fitted to the two clouds (ridge 1e-4 x mean variance)
#   ot_r0.003 : soft OT, eps = 0.003 x median cost (10x sharper than the paper's 0.03), log-domain Sinkhorn in float64,
#               stopped at max marginal error < 1e-3 (the criterion of experiments/tm_1000.py's sink_log)
#   hard      : exact one-to-one OT, Hungarian on all 1,024 latent vectors (no sampling needed)
#   ot_r0.03chk (first 20 pairs only): the paper's soft OT recomputed here, to check this pipeline against the existing
#               tmc1000/ot_r0.03 renders pixel by pixel.
import os, json, time, numpy as np, torch
from scipy.optimize import linear_sum_assignment
MAN6 = json.load(open(f"{MT}/tm_scale1000/manifest.json"))["pairs"][:globals().get("N6", 1000)]

def sink_t(C, eps, tol=1e-3, max_it=20000):
    n, m = C.shape; la, lb = -np.log(n), -np.log(m)
    f = torch.zeros(n, dtype=C.dtype, device=C.device); g = torch.zeros(m, dtype=C.dtype, device=C.device); it = 0
    while it < max_it:
        for _ in range(50):
            f = eps * (la - torch.logsumexp((g[None] - C) / eps, 1)); g = eps * (lb - torch.logsumexp((f[:, None] - C) / eps, 0)); it += 1
        P = torch.exp((f[:, None] + g[None] - C) / eps)
        err = max(float((P.sum(1) * n - 1).abs().max()), float((P.sum(0) * m - 1).abs().max()))
        if err < tol: break
    return P, err, it

def gauss_t(X, Y):
    v = 0.5 * float(X.var(0).mean() + Y.var(0).mean())
    return matching._gaussian_map(X, Y, ridge=1e-4 * v).double()

t0 = time.time(); worst = 0.0; its = []
for i, p in enumerate(MAN6):
    k = f"{int(p['k']):04d}"; rules = ["gaussian", "ot_r0.003", "hard"] + (["ot_r0.03chk"] if i < 20 else [])
    if all(os.path.exists(f"{WORK}/mid_{r}_{k}.npy") for r in rules): continue
    z = np.load(f"{WORK}/lat_{k}.npz"); C_, H, W = z["lA"].shape[1:]
    X = torch.from_numpy(z["lA"][0].reshape(C_, -1).T.astype(np.float64)).to(DEV)
    Y = torch.from_numpy(z["lB"][0].reshape(C_, -1).T.astype(np.float64)).to(DEV)
    Cm = ((X[:, None, :] - Y[None, :, :]) ** 2).sum(-1); med = float(Cm.median())
    U = {"gaussian": gauss_t(X, Y)}
    P, err, it = sink_t(Cm, 0.003 * med); worst = max(worst, err); its.append(it)
    U["ot_r0.003"] = (P / P.sum(1, keepdim=True)) @ Y
    r_, c_ = linear_sum_assignment(Cm.cpu().numpy()); Uh = torch.empty_like(Y); Uh[torch.as_tensor(r_)] = Y[torch.as_tensor(c_)]; U["hard"] = Uh
    if i < 20:
        P2, _, _ = sink_t(Cm, 0.03 * med); U["ot_r0.03chk"] = (P2 / P2.sum(1, keepdim=True)) @ Y
    for r, u in U.items():
        np.save(f"{WORK}/mid_{r}_{k}.npy", (0.5 * X + 0.5 * u).T.reshape(1, C_, H, W).float().cpu().numpy())
    if (i + 1) % 200 == 0 or i + 1 == len(MAN6):
        print(f"[tier6 pair] {i + 1}/{len(MAN6)}  {(time.time() - t0) / 60:.1f} min  worst marginal err {worst:.1e}  "
              f"median Sinkhorn iters {int(np.median(its)) if its else 0}  C={C_}", flush=True)
