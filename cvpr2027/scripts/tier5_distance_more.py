# Tier 5 (pre-specified before running; all results reported):
#  (1) categories: 20 random DTD classes x 10 images (seed 2027, 'freckled' excluded)
#  (2) crop retrieval: 40 random images (one per random class, seed 2028), 4 random crops each (side = 60% of the
#      shorter image side, uniform position, seed 2029), resized like the paper's endpoints (bicubic to 128 px).
#      A crop's "class" is its source image.
# Distances: positional (mean sq. distance at the same location), gaussian (Bures-Wasserstein), ot_div (debiased
# Sinkhorn divergence, paper's eps). Metrics: leave-one-out 1-NN accuracy, mean average precision, within/between.
import os, json, random, time, numpy as np, torch
from PIL import Image
T5 = f"{OUT}/tier5"; os.makedirs(T5, exist_ok=True)
classes_all = sorted(c for c in os.listdir(DTD_ROOT) if os.path.isdir(f"{DTD_ROOT}/{c}") and c != "freckled")

def bures(X, Y, ridge_rel=1e-3):
    X, Y = X.double(), Y.double(); mx, my = X.mean(0), Y.mean(0)
    Sx, Sy = torch.cov(X.T), torch.cov(Y.T)
    r = ridge_rel * 0.5 * (Sx.diagonal().mean() + Sy.diagonal().mean()); I = torch.eye(X.shape[1], dtype=X.dtype, device=X.device)
    Sx, Sy = Sx + r * I, Sy + r * I
    w, V = torch.linalg.eigh(Sx); Sh = (V * w.clamp_min(0).sqrt()) @ V.T
    return float(((mx - my) ** 2).sum() + Sx.trace() + Sy.trace() - 2 * torch.linalg.eigvalsh(Sh @ Sy @ Sh).clamp_min(0).sqrt().sum())
def ot(X, Y, kw):
    C = torch.cdist(X.float(), Y.float()) ** 2
    eps = kw["eps_abs"] if "eps_abs" in kw else kw["eps_rel"] * float(C.median())
    P, _ = matching.sinkhorn_plan(X.float(), Y.float(), eps); return float((P * C).sum())
def feats_cnt(img):
    d = cnt.build_pair(cnt.load_image(img), cnt.load_image(img)); return cnt.grids(d)[4]
def feats_rae(img):
    x = enc_dino(img).float(); return x[0] if x.dim() == 3 else x
def feats_vae(img): return vae_tokens(img)[0].float()
MODELS = {"CNT": (feats_cnt, dict(eps_abs=matching.EPS), True), "DINO-RAE": (feats_rae, dict(eps_rel=EPS_REL), False),
          "SD-VAE": (feats_vae, dict(eps_rel=EPS_REL), False)}

def metrics(M, labels):
    n = len(M); Mi = M + np.diag(np.full(n, np.inf)); same = labels[:, None] == labels[None, :]; off = ~np.eye(n, dtype=bool)
    acc = float((labels[Mi.argmin(1)] == labels).mean())
    aps = []
    for i in range(n):
        order = np.argsort(Mi[i])[:-1]; rel = (labels[order] == labels[i]).astype(float)
        if rel.sum() == 0: continue
        prec = np.cumsum(rel) / (np.arange(len(rel)) + 1); aps.append(float((prec * rel).sum() / rel.sum()))
    return dict(nn_acc=acc, mAP=float(np.mean(aps)), within_between=float(M[same & off].mean() / M[~same].mean()))

def run(tag, images, labels):
    out = {}
    for name, (fn, kw, sub) in MODELS.items():
        t0 = time.time()
        with torch.no_grad():
            F = [fn(im).to(DEV) for im in images]; g = torch.Generator(device=DEV).manual_seed(7)
            Fs = [x[torch.randperm(x.shape[0], generator=g, device=DEV)[:matching.NSUB]] if (sub and x.shape[0] > matching.NSUB) else x for x in F]
            n = len(F); selfc = [ot(Fs[i], Fs[i], kw) for i in range(n)]
            D = {k: np.zeros((n, n)) for k in ("positional", "gaussian", "ot_div")}
            for i in range(n):
                for j in range(i + 1, n):
                    D["positional"][i, j] = float(((F[i] - F[j]) ** 2).sum(1).mean())
                    D["gaussian"][i, j] = bures(F[i], F[j])
                    D["ot_div"][i, j] = ot(Fs[i], Fs[j], kw) - 0.5 * (selfc[i] + selfc[j])
            for k in D: D[k] = D[k] + D[k].T; np.save(f"{T5}/{tag}_{name}_{k}_D.npy", D[k])
        out[name] = {k: metrics(M, labels) for k, M in D.items()}
        print(tag, name, f"({(time.time() - t0) / 60:.1f} min)", json.dumps(out[name]), flush=True)
    return out

RES = {}
# (2) crop retrieval first (cheaper)
rng = random.Random(2028); cls40 = sorted(rng.sample(classes_all, 40))
srcs = [(c, sorted(rng.sample(sorted(f for f in os.listdir(f"{DTD_ROOT}/{c}") if f.endswith(".jpg")), 1))[0]) for c in cls40]
rc = random.Random(2029); crops, clab = [], []
for si, (c, f) in enumerate(srcs):
    im = Image.open(f"{DTD_ROOT}/{c}/{f}").convert("RGB"); W, H = im.size; s = int(0.6 * min(W, H))
    for _ in range(4):
        x0, y0 = rc.randint(0, W - s), rc.randint(0, H - s)
        crops.append(im.crop((x0, y0, x0 + s, y0 + s)).resize((128, 128), Image.BICUBIC)); clab.append(si)
RES["crops"] = run("crops", crops, np.array(clab))
json.dump(dict(sources=srcs, results=RES), open(f"{T5}/tier5_results.json", "w"), indent=1)
# (1) 20 classes x 10 images
rng = random.Random(2027); cls20 = sorted(rng.sample(classes_all, 20)); imgs, lab = [], []
for ci, c in enumerate(cls20):
    for f in sorted(rng.sample(sorted(f for f in os.listdir(f"{DTD_ROOT}/{c}") if f.endswith(".jpg")), 10)):
        imgs.append(endpoint(c, f)); lab.append(ci)
RES["classes20"] = run("classes20", imgs, np.array(lab))
json.dump(dict(sources=srcs, classes20=cls20, results=RES), open(f"{T5}/tier5_results.json", "w"), indent=1)
print("saved", T5)
