# Tier 4: do texture distances respect DTD's human categories?
# 10 random DTD classes x 10 random images (fixed seed). For each model (CNT field cells, DINOv2 tokens of DINO-RAE,
# SD-VAE latent vectors), compute three distances between every pair of images:
#   positional : mean squared distance between features at the same location
#   gaussian   : Bures-Wasserstein distance between Gaussians fitted to the two feature sets (classic texture stats)
#   ot         : entropic OT cost between the two feature sets (same settings as the paper's soft OT)
# Report leave-one-out 1-NN class accuracy, within/between distance ratio, and 10x10 class-mean matrices.
# Run after the models are loaded (exec colab_render_more_pairs.py once: cnt, enc_dino, vae_tokens exist).
import os, json, random, numpy as np, torch, time
T4 = f"{OUT}/tier4"; os.makedirs(T4, exist_ok=True)
rng = random.Random(2026)
classes = sorted(c for c in os.listdir(DTD_ROOT) if os.path.isdir(f"{DTD_ROOT}/{c}") and c != "freckled")
CLS = sorted(rng.sample(classes, 10))
IMGS = []
for c in CLS:
    fs = sorted(f for f in os.listdir(f"{DTD_ROOT}/{c}") if f.endswith(".jpg"))
    for f in sorted(rng.sample(fs, 10)): IMGS.append((c, f))
labels = np.array([CLS.index(c) for c, _ in IMGS])
print("classes:", CLS)

def bures(X, Y, ridge_rel=1e-3):
    X, Y = X.double(), Y.double()
    mx, my = X.mean(0), Y.mean(0)
    Sx, Sy = torch.cov(X.T), torch.cov(Y.T)
    r = ridge_rel * 0.5 * (Sx.diagonal().mean() + Sy.diagonal().mean())
    I = torch.eye(X.shape[1], dtype=X.dtype, device=X.device)
    Sx, Sy = Sx + r * I, Sy + r * I
    w, V = torch.linalg.eigh(Sx); Sx_h = (V * w.clamp_min(0).sqrt()) @ V.T
    M = Sx_h @ Sy @ Sx_h; wm = torch.linalg.eigvalsh(M).clamp_min(0)
    return float(((mx - my) ** 2).sum() + Sx.trace() + Sy.trace() - 2 * wm.sqrt().sum())

def ot_cost(X, Y, eps_abs=None, eps_rel=None):
    C = torch.cdist(X.float(), Y.float()) ** 2
    eps = eps_abs if eps_abs is not None else eps_rel * float(C.median())
    P, _ = matching.sinkhorn_plan(X.float(), Y.float(), eps)
    return float((P * C).sum())

def feats_cnt(img):
    d = cnt.build_pair(cnt.load_image(img), cnt.load_image(img))
    L, C, H, W, sf, tf = cnt.grids(d); return sf
def feats_rae(img):
    x = enc_dino(img).float(); return x[0] if x.dim() == 3 else x
def feats_vae(img): return vae_tokens(img)[0].float()

NS = matching.NSUB
MODELS = {"CNT": (feats_cnt, dict(eps_abs=matching.EPS), True), "DINO-RAE": (feats_rae, dict(eps_rel=EPS_REL), False),
          "SD-VAE": (feats_vae, dict(eps_rel=EPS_REL), False)}
res = {}
for name, (fn, epskw, sub) in MODELS.items():
    t0 = time.time()
    with torch.no_grad():
        F = [fn(endpoint(c, f)).to(DEV) for c, f in IMGS]
        g = torch.Generator(device=DEV).manual_seed(7)
        Fs = [x[torch.randperm(x.shape[0], generator=g, device=DEV)[:NS]] if (sub and x.shape[0] > NS) else x for x in F]
        n = len(F); D = {k: np.zeros((n, n)) for k in ("positional", "gaussian", "ot")}
        for i in range(n):
            for j in range(i + 1, n):
                D["positional"][i, j] = float(((F[i] - F[j]) ** 2).sum(1).mean())
                D["gaussian"][i, j] = bures(F[i], F[j])
                D["ot"][i, j] = ot_cost(Fs[i], Fs[j], **epskw)
        for k in D: D[k] = D[k] + D[k].T
    m = {}
    for k, M in D.items():
        Mi = M + np.diag(np.full(n, np.inf)); nn = Mi.argmin(1)
        acc = float((labels[nn] == labels).mean())
        same = labels[:, None] == labels[None, :]; off = ~np.eye(n, dtype=bool)
        ratio = float(M[same & off].mean() / M[~same].mean())
        cm = np.array([[M[np.ix_(labels == a, labels == b)][(off[np.ix_(labels == a, labels == b)])].mean()
                        if a == b else M[np.ix_(labels == a, labels == b)].mean() for b in range(10)] for a in range(10)])
        # 5-per-class sub-draws (the original design), 20 random draws
        accs = []
        r2 = np.random.default_rng(0)
        for _ in range(20):
            idx = np.concatenate([r2.choice(np.where(labels == a)[0], 5, replace=False) for a in range(10)])
            Ms = M[np.ix_(idx, idx)] + np.diag(np.full(len(idx), np.inf)); accs.append(float((labels[idx][Ms.argmin(1)] == labels[idx]).mean()))
        m[k] = dict(nn_acc=acc, nn_acc_5pc_mean=float(np.mean(accs)), nn_acc_5pc_sd=float(np.std(accs)), within_between=ratio)
        np.save(f"{T4}/{name}_{k}_D.npy", M); np.save(f"{T4}/{name}_{k}_class.npy", cm)
    res[name] = m
    print(name, f"({(time.time() - t0) / 60:.1f} min)", json.dumps(m))
json.dump(dict(classes=CLS, images=IMGS, results=res), open(f"{T4}/tier4_results.json", "w"), indent=1)
print("saved", T4)
