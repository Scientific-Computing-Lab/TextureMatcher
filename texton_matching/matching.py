"""The six texton-matching rules compared in the paper: field-linear,
primitive-linear, Gaussian (moment alignment), target mean, soft OT
(entropic transport, the paper's main method) and exact OT (one-to-one
Hungarian assignment).

Ported from the canonical `_targets` / `field` / `zt` helpers shared by
mechanism_study.ipynb, CNT_correspondence_experiments.ipynb,
finishing_experiments.ipynb and jackknife_dKID.ipynb. field-linear and
primitive-linear operate directly on CNT's representations and are
implemented as methods on texton_matching.cnt.CNTModel instead (they don't
go through a sampled matching plan at all); this module supplies the other
four rules plus the shared field-sampling/extension machinery, and a single
`interpolate()` entry point that dispatches on rule name.

Imports of torch are guarded the same way as texton_matching.cnt.
"""
from __future__ import annotations

try:
    import torch
    _HAVE_TORCH = True
except ImportError:  # pragma: no cover
    _HAVE_TORCH = False

from .cnt import EPS, ITERS, NSUB, N_EXACT

RULES = ("field_linear", "primitive_linear", "gaussian", "target_mean", "soft_ot", "exact_ot")

# Two more sampled-rule names, used only by tab:rules' 200-pair ablation
# (experiments/rules_200.py), not part of the paper's six canonical rules
# above. Ported verbatim from matching_ablation.ipynb cell 2's `_targets`
# (the "F2 ablation setup" family, INVENTORY.md §4a; read directly, not
# reconstructed from a description): "nn" pairs each sampled source cell
# with its nearest sampled target cell (`tgt[cdist(src,tgt).argmin(1)]`,
# no transport plan at all); "random" pairs the same n_sub source and
# target samples via a uniformly random bijection seeded `seed+7`
# (`tgt[randperm(M, seed+7)]`) -- distinct from exact_ot's `seed+11` --
# i.e. a permutation that preserves the target sample's marginal but
# destroys correspondence entirely (the paper's own framing:
# "random permutation preserves the sample marginal but destroys
# correspondence", supplement.tex tab:rules caption). Both are exposed
# through `targets()` / `field()` / `interpolate()` exactly like the four
# rules above.
ABLATION_ONLY_RULES = ("nn", "random")

_TAG = {"s": 1, "t": 2}


def _sub(N: int, seed: int, tag: str, n_sub: int, device):
    """Seeded subsample of `n_sub` of the N field cells. Deterministic in
    `seed` (the pair id) and `tag` ('s' for source, 't' for target) --
    identical seeding scheme across every canonical notebook."""
    g = torch.Generator(device=device).manual_seed(int(seed) * 7919 + _TAG[tag])
    return torch.randperm(N, generator=g, device=device)[:n_sub]


def sinkhorn_plan(x, y, eps: float, iters: int = ITERS):
    """Canonical (float32, multiplicative) balanced entropic transport
    plan between two equally-weighted point clouds. Returns (P, cost)."""
    Cm = torch.cdist(x, y).pow(2)
    K = torch.exp(-Cm / eps)
    u = torch.ones(len(x), device=x.device) / len(x)
    v = torch.ones(len(y), device=y.device) / len(y)
    a = torch.ones_like(u)
    b = torch.ones_like(v)
    for _ in range(iters):
        a = u / (K @ b + 1e-30)
        b = v / (K.T @ a + 1e-30)
    return a[:, None] * K * b[None, :], Cm


def sinkhorn_log(x, y, eps: float, iters: int = 3000, tol: float = 1e-6):
    """float64 log-domain Sinkhorn with duals; used for the matched-
    rendering (equal-sample) ablation, iterated to a marginal-error
    tolerance rather than a fixed iteration count. Returns
    (P, f, g, cost, residual, iterations)."""
    import math
    X, Y = x.double(), y.double()
    Cm = torch.cdist(X, Y).pow(2)
    n, m = Cm.shape
    la, lb = -math.log(n), -math.log(m)
    f = torch.zeros(n, device=X.device, dtype=torch.float64)
    g = torch.zeros(m, device=X.device, dtype=torch.float64)
    it = 0
    for it in range(1, iters + 1):
        f = eps * (la - torch.logsumexp((g[None, :] - Cm) / eps, 1))
        g = eps * (lb - torch.logsumexp((f[:, None] - Cm) / eps, 0))
        if it % 10 == 0:
            logP = (f[:, None] + g[None, :] - Cm) / eps
            res = float((torch.exp(logP).sum(1) - 1 / n).abs().max() * n)
            if res < tol:
                break
    logP = (f[:, None] + g[None, :] - Cm) / eps
    P = torch.exp(logP)
    res = float(max((P.sum(1) - 1 / n).abs().max() * n, (P.sum(0) - 1 / m).abs().max() * m))
    return P, f, g, Cm, res, it


def _gaussian_map(src, tgt, ridge: float = 1e-4):
    """Quadratic-cost optimal affine (Monge) map between fitted Gaussians
    (the moment-alignment baseline; app:gaussian in the supplement)."""
    X, Y = src.double(), tgt.double()
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    C = X.shape[1]
    I = torch.eye(C, device=X.device, dtype=torch.float64)
    Sa = (Xc.T @ Xc) / (len(X) - 1) + ridge * I
    Sb = (Yc.T @ Yc) / (len(Y) - 1) + ridge * I

    def psd_sqrt(M, floor):
        e, V = torch.linalg.eigh(0.5 * (M + M.T))
        e = e.clamp_min(floor)
        return (V * e.sqrt()) @ V.T

    def psd_isqrt(M, floor):
        e, V = torch.linalg.eigh(0.5 * (M + M.T))
        e = e.clamp_min(floor)
        return (V * e.rsqrt()) @ V.T

    Sh, Sih = psd_sqrt(Sa, ridge), psd_isqrt(Sa, ridge)
    A = Sih @ psd_sqrt(Sh @ Sb @ Sh, 0.0) @ Sih
    A = 0.5 * (A + A.T)
    return (my + Xc @ A.T).float()


def targets(sf, tf, rule: str, seed: int, eps: float = EPS, n_sub: int = NSUB, n_exact: int = N_EXACT):
    """Compute the sampled target vector `tt` for each of the `n_sub`
    sampled source cells (indices `i_s`), under one of: gaussian,
    target_mean, soft_ot, exact_ot. Returns (i_s, tt).

    field_linear and primitive_linear are NOT sampled matching rules (they
    never solve a transport problem); call CNTModel.field_linear /
    .primitive_linear directly for those.
    """
    seed = int(seed)  # a numpy int64 (e.g. from a pandas column) breaks torch's manual_seed
    N = sf.shape[0]
    i_s = _sub(N, seed, "s", n_sub, sf.device)
    i_t = _sub(N, seed, "t", n_sub, sf.device)
    src, tgt = sf[i_s], tf[i_t]

    if rule == "soft_ot":
        P, _ = sinkhorn_plan(src, tgt, eps)
        tt = (P / (P.sum(1, keepdim=True) + 1e-30)) @ tgt
    elif rule == "exact_ot":
        g = torch.Generator(device=sf.device).manual_seed(seed + 11)
        js = torch.randperm(n_sub, generator=g, device=sf.device)[:n_exact]
        is_ = torch.randperm(n_sub, generator=g, device=sf.device)[:n_exact]
        from scipy.optimize import linear_sum_assignment
        r, c = linear_sum_assignment(torch.cdist(src[is_], tgt[js]).pow(2).cpu().numpy())
        tt = torch.full_like(src, float("nan"))
        tt[is_[torch.as_tensor(r, device=sf.device)]] = tgt[js[torch.as_tensor(c, device=sf.device)]]
        ok = ~torch.isnan(tt[:, 0])
        tt[~ok] = tt[ok][torch.cdist(src[~ok], src[ok]).argmin(1)]
    elif rule == "gaussian":
        tt = _gaussian_map(src, tgt)
    elif rule == "target_mean":
        tt = tgt.mean(0, keepdim=True).expand_as(src).clone()
    elif rule == "nn":
        tt = tgt[torch.cdist(src, tgt).argmin(1)]
    elif rule == "random":
        # matching_ablation.ipynb cell 2 `_targets`, rule=='random': seed+7
        # (distinct from exact_ot's seed+11 -- verbatim, not a guess).
        g = torch.Generator(device=sf.device).manual_seed(seed + 7)
        tt = tgt[torch.randperm(len(tgt), generator=g, device=sf.device)]
    else:
        raise ValueError(f"unknown rule {rule!r}; expected one of gaussian, target_mean, soft_ot, exact_ot, nn, random")
    return i_s, tt


def field(cnt_model, d, rule: str, seed: int, **kw):
    """Extend a sampled matching rule to the full dense field via nearest-
    sampled-source-cell lookup (the canonical extension: every unsampled
    cell reuses the partner of its nearest sampled source vector)."""
    seed = int(seed)
    L, C, H, W, sf, tf = cnt_model.grids(d)
    i_s, tt = targets(sf, tf, rule, seed, **kw)
    nn = torch.cdist(sf, sf[i_s]).argmin(1)
    return dict(U=tt[nn], X=sf, Y=tf, L=L, C=C, H=H, W=W, i_s=i_s, tt=tt, nn=nn)


def zt(fd, t: float):
    return (1 - t) * fd["X"] + t * fd["U"]


def interpolate(cnt_model, d, rule: str, eta: float, seed: int = 0, **kw):
    """Single entry point: decode the eta-interpolated midpoint under any
    of the six rules. `d` is a CNTModel.build_pair(...) dict."""
    if rule == "field_linear":
        return cnt_model.field_linear(d, eta)
    if rule == "primitive_linear":
        return cnt_model.primitive_linear(d, eta)
    if rule in ("gaussian", "target_mean", "soft_ot", "exact_ot") + ABLATION_ONLY_RULES:
        fd = field(cnt_model, d, rule, seed, **kw)
        Z = zt(fd, eta)
        return cnt_model.decode_field(d, Z, fd["L"], fd["H"], fd["W"], fd["C"])
    raise ValueError(f"unknown rule {rule!r}; expected one of {RULES + ABLATION_ONLY_RULES}")
