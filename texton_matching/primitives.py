"""Matching CNT's Gaussian primitives directly (one-to-one Hungarian, and a
soft entropic bridge), instead of the dense per-cell field texton_matching.
matching operates on. This is `tab:app-primitives` in the supplement:
"KID for one-to-one matchings of CNT's Gaussian primitives ... Position (P)
/ Appearance (A) / mixed (PA) cost, fixed vs moving layout".

Ported from `CNT_correspondence_experiments.ipynb`, cells 1-2 (the element
API, cost construction, fixed/moving decoders -- read directly from the
notebook's saved cell source; the docstrings below the function defs quote
the notebook's own comments where they explain a design choice this module
would otherwise look arbitrary) and cell 13 (the Gaussian-level entropic
bridge, E4). Everything else in that notebook (E2a/E2b latent counterfactuals,
E3 corrupt-the-cue, the SENS/REPL/timing cells) is validation machinery for
the notebook's own internal protocol and does not feed any paper macro
(confirmed via INVENTORY.md's claims map) -- it is deliberately not ported
here.

Scope note: `ACTIVE_THR` and `ROT_IS_APPEARANCE` below are copied verbatim
from the notebook's cell 2 as fixed constants (the notebook computed them
once via an audit cell and asserted they held; that audit is not repeated
here -- if a different CNT checkpoint ever violates them, the geometry
below will silently be wrong, not error out).
"""
from __future__ import annotations

import math

try:
    import torch
    import torch.nn.functional as F
    _HAVE_TORCH = True
except ImportError:  # pragma: no cover
    _HAVE_TORCH = False

ACTIVE_THR = 0.5   # layout_net.py inference branch: weights = round(exist_prob) -> admissible element := weight > 0.5
ROT_IS_APPEARANCE = True  # layout_splat.py (texton_encoder=disentangled_local_texton) concatenates rot_feature into blob_features

LAM = {"A": 0.0, "PA": 0.5, "P": 1.0}  # mixed_cost blend weight toward the position cost
EPS_GRID = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0)  # E4's normalised-cost Sinkhorn epsilon grid


def _tl(blob):
    return blob["layer_tree_levels"][-1][0]


def elements(blob, active_thr: float = ACTIVE_THR):
    """Active Gaussian elements in native slot order. `pos` = normalised
    image coords in [0,1] (splat convention: (xy+3)/6 * img_size)."""
    T = _tl(blob)
    w = T["weights"][0, :, 0]
    idx = torch.nonzero(w > active_thr)[:, 0]
    E = dict(
        idx=idx, xy=T["xy"][0, idx], covs=T["covs"][0, idx], w=w[idx],
        ptf=T["per_texel_feature"][0, idx], rot=T["rot_feature"][0, idx],
        bg=blob["bg_features"][0], K=int(w.shape[0]), n=int(len(idx)),
    )
    E["f"] = torch.cat([E["ptf"], E["rot"]], -1) if ROT_IS_APPEARANCE else E["ptf"]
    E["pos"] = (E["xy"] + 3) / 6
    return E


def cost_mats(ES, ET):
    """Squared position and appearance cost matrices between two elements
    sets' active primitives (unnormalised; divide by the frozen scales from
    calibrate_scales before combining or matching)."""
    return (
        torch.cdist(ES["pos"].double(), ET["pos"].double()).pow(2),
        torch.cdist(ES["f"].double(), ET["f"].double()).pow(2),
    )


def calibrate_scales(cnt_model, pairs, build_pair_fn) -> dict:
    """Global robust cost scales: median over a calibration pair set of the
    per-pair median admissible-edge cost, for both position and appearance.
    The notebook calibrates on a 20-pair set disjoint from its 120-pair
    main/dev sets (`CAL`); this package has no equivalent separately-drawn
    calibration split; callers pass whatever pairs they want used (e.g. a
    slice of the same manifest, or a held-out set) via `pairs`, and
    `build_pair_fn(k) -> (ES, ET)` to get that pair's elements.
    """
    mp, ma = [], []
    for k in pairs:
        ES, ET = build_pair_fn(k)
        Cp, Ca = cost_mats(ES, ET)
        mp.append(float(Cp.median()))
        ma.append(float(Ca.median()))
    import numpy as np
    s_pos, s_app = float(np.median(mp)), float(np.median(ma))
    if s_pos <= 1e-8 or s_app <= 1e-8:
        raise ValueError(f"zero calibration scale (s_pos={s_pos}, s_app={s_app}); calibration pairs are degenerate")
    return dict(s_pos=s_pos, s_app=s_app)


def mixed_cost(Cp, Ca, lam: float, scales: dict):
    return (1 - lam) * Ca / scales["s_app"] + lam * Cp / scales["s_pos"]


def hungarian_assign(C) -> dict:
    """Deterministic rectangular Hungarian assignment (scipy), rows sorted.
    `map_full` gives a target for every source element: matched elements
    get their assigned partner; unmatched elements (unequal active counts
    between the two sides) get the argmin of the same cost row -- the
    notebook's "many-to-one, fixed-layout policy" for leftover elements.
    """
    from scipy.optimize import linear_sum_assignment
    import numpy as np
    device = C.device
    Cn = C.detach().cpu().numpy()
    r, c = linear_sum_assignment(Cn)
    o = np.argsort(r)
    r, c = r[o], c[o]
    nA, nB = Cn.shape
    mA = np.zeros(nA, bool); mA[r] = True
    mB = np.zeros(nB, bool); mB[c] = True
    mf = np.empty(nA, np.int64); mf[r] = c
    unA = np.nonzero(~mA)[0]
    if len(unA):
        mf[unA] = Cn[unA].argmin(1)
    T = lambda a: torch.as_tensor(np.asarray(a), device=device, dtype=torch.long)
    return dict(r=T(r), c=T(c), unA=T(unA), unB=T(np.nonzero(~mB)[0]), map_full=T(mf),
                matched=T(mA.astype(np.int64)).bool(), cost=float(Cn[r, c].sum()), nA=int(nA), nB=int(nB))


def solve_cost(ES, ET, name: str, scales: dict, Cp=None, Ca=None):
    """name in {'P','A','PA'}: solve the Hungarian assignment under the
    named cost. Returns (assignment, Cp, Ca)."""
    if Cp is None or Ca is None:
        Cp, Ca = cost_mats(ES, ET)
    C = mixed_cost(Cp, Ca, LAM[name], scales)
    return hungarian_assign(C), Cp, Ca


# --- fixed layout: A's complete geometry is kept; only active elements' -----
# --- appearance interpolates toward their assigned B partner ---------------

def _lerp(a, b, t):
    return (1 - t) * a + t * b


def _nptf(x, dp):
    return F.normalize(x, p=2, dim=-1)


def fixed_bf(d, side: str, ES, fT, bgT, t: float, dp: int):
    """Frozen-layout feature rows: side's complete geometry stays (all K
    slots including inactive ones, native order, native score_img); only
    the appearance rows of the active elements change:
    f_i(t) = (1-t) f_i^S + t fT_i, blocks renormalised as in CNT's own
    code; the background row is lerped too. `fT` is (n, DP+DR)."""
    bf = d["bf_" + side].clone()
    fS = torch.cat([ES["ptf"], ES["rot"]], -1)
    f = _lerp(fS, fT, t)
    rot = F.normalize(f[:, dp:], p=2, dim=-1) if ROT_IS_APPEARANCE else fS[:, dp:]
    bf[0, 1 + ES["idx"]] = torch.cat([F.normalize(f[:, :dp], p=2, dim=-1), rot], -1)
    bf[0, 0] = _lerp(ES["bg"], bgT, t)
    return bf


def decode_fixed_feats(cnt_model, d, side: str, ES, fT, bgT, t: float, dp: int):
    bf = fixed_bf(d, side, ES, fT, bgT, t, dp)
    sm = cnt_model.build_style_maps(bf, d["si_" + side])
    return cnt_model.decode_with_style_maps(d["blob_" + side], sm)


def decode_fixed(cnt_model, d, side: str, ES, ET, asg: dict, t: float):
    dp = ES["ptf"].shape[-1]
    fT = torch.cat([ET["ptf"], ET["rot"]], -1)[asg["map_full"]]
    return decode_fixed_feats(cnt_model, d, side, ES, fT, ET["bg"], t, dp)


# --- moving layout: matched elements' position AND appearance interpolate; -
# --- unmatched source fades out, unmatched target fades in -----------------

def moving_params(ES, ET, asg: dict, t: float):
    m = asg["matched"][:, None]
    mf = asg["map_full"]
    xy = torch.where(m, _lerp(ES["xy"], ET["xy"][mf], t), ES["xy"])
    covs = torch.where(m[:, :, None], _lerp(ES["covs"], ET["covs"][mf], t), ES["covs"])
    ptf = torch.where(m, F.normalize(_lerp(ES["ptf"], ET["ptf"][mf], t), p=2, dim=-1), ES["ptf"])
    rot = torch.where(m, F.normalize(_lerp(ES["rot"], ET["rot"][mf], t), p=2, dim=-1), ES["rot"])
    w = torch.where(m[:, 0], torch.ones_like(ES["w"]), (1 - t) * torch.ones_like(ES["w"]))
    u = asg["unB"]
    if len(u) > 1:
        # fade-in extras composited in raster order (y, then x): label-free, deterministic
        o = torch.argsort(ET["xy"][u, 0], stable=True)
        o = o[torch.argsort(ET["xy"][u, 1][o], stable=True)]
        u = u[o]
    xy = torch.cat([xy, ET["xy"][u]]); covs = torch.cat([covs, ET["covs"][u]])
    ptf = torch.cat([ptf, ET["ptf"][u]]); rot = torch.cat([rot, ET["rot"][u]])
    w = torch.cat([w, float(t) * torch.ones(len(u), device=w.device, dtype=w.dtype)])
    return xy, covs, w, ptf, rot, _lerp(ES["bg"], ET["bg"], t)


def make_blob(base, xy, covs, w, ptf, rot, bg):
    T = dict(_tl(base))
    T.update(xy=xy[None], covs=covs[None], weights=w[None, :, None], exist_prob=w[None, :, None],
              per_texel_feature=ptf[None], rot_feature=rot[None])
    b = dict(base)
    ltl = base["layer_tree_levels"]
    ltl2 = dict(ltl) if isinstance(ltl, dict) else list(ltl)
    ltl2[-1] = [T]
    b["layer_tree_levels"] = ltl2
    b["bg_features"] = bg[None]
    return b


def decode_blob(cnt_model, blob):
    with torch.no_grad():
        L = cnt_model.model.splat(blob)["layer_level_layouts"][-1][0]
        sm = cnt_model.build_style_maps(L["blob_features"], L["score_img"])
        return cnt_model.decode_with_style_maps(blob, sm)


def decode_moving(cnt_model, d, ES, ET, asg: dict, t: float, side: str = "a"):
    return decode_blob(cnt_model, make_blob(d["blob_" + side], *moving_params(ES, ET, asg, t)))


# --- E4: Gaussian-level entropic (soft) appearance matching, fixed layout --

def gauss_sinkhorn_primitive_map(EA, EB, Ca, eps: float, s_app: float, iters: int = 3000, tol: float = 1e-6):
    """Balanced Sinkhorn with uniform marginals on the active elements
    (normalised appearance cost only -- this is an appearance-space bridge,
    not a position+appearance one); barycentric projection of B's
    [ptf|rot]. Returns (F*, info) where F* has the same shape as EA's
    [ptf|rot] and info includes the retained-variance fraction `var_ret`
    used to pick the epsilon that matches dense soft-OT's variance
    retention (E4's whole point: is the Gaussian-level bridge operating in
    the same "how much detail survives" regime as the paper's actual dense
    operator?).
    """
    Cn = (Ca / s_app).double()
    n, m = Cn.shape
    la, lb = -math.log(n), -math.log(m)
    fdu = torch.zeros(n, device=Ca.device, dtype=torch.float64)
    gdu = torch.zeros(m, device=Ca.device, dtype=torch.float64)
    it = 0
    for it in range(1, iters + 1):
        fdu = eps * (la - torch.logsumexp((gdu[None, :] - Cn) / eps, 1))
        gdu = eps * (lb - torch.logsumexp((fdu[:, None] - Cn) / eps, 0))
        if it % 10 == 0:
            P = torch.exp((fdu[:, None] + gdu[None, :] - Cn) / eps)
            if float((P.sum(1) - 1 / n).abs().max() * n) < tol:
                break
    P = torch.exp((fdu[:, None] + gdu[None, :] - Cn) / eps)
    Q = P / (P.sum(1, keepdim=True) + 1e-300)
    fB = torch.cat([EB["ptf"], EB["rot"]], -1).double()
    Fstar = (Q @ fB).float()
    var_ret = float(Fstar.double().var(0).sum() / fB.var(0).sum())
    return Fstar, dict(var_ret=var_ret, iters=it)
