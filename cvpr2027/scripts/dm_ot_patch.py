"""OT-coupled attention blending for DiffMorpher (commit 111627b).

DiffMorpher's LoadProcessor (model.py line 63) builds the K/V source of each in-between frame's self-attention as
    (1 - alpha) * map0 + alpha * map1
i.e. token i of A's stored self-attention input is blended with token i of B's: a positional coupling.
Attention is permutation-invariant over its K/V set, so that pairing has no meaning for unregistered textures.

This module replaces ONLY that blend. Everything else in LoadProcessor (the lamd step cut-off, the beta mix with the
current hidden states, the id counter and its reset) is kept line for line.

Couplings (env var DM_COUPLING):
    positional    the official formula
    ot_twosided   sharp entropic OT (eps = DM_OT_EPS_REL x median squared cost) on DM_OT_NSUB sampled tokens, extended
                  to every token by its nearest sample's displacement; targets cached once per (layer, step) and
                  reused for every frame. alpha <= .5 moves A's tokens toward their partners in B; alpha > .5 moves
                  B's tokens toward their partners in A, so the K/V set is exactly map0 at alpha = 0 and exactly map1
                  at alpha = 1. Layout comes from the slerped latent, not the K/V tokens, so the side switch at .5
                  should not snap the layout.
    ot_onesided   A-side path for all alpha (the set at alpha = 1 is the contracted T(map0), not map1).

Usage inside the DiffMorpher driver, after `from model import DiffMorpherPipeline`:
    import dm_ot_patch; dm_ot_patch.install()
    ...
    for each pair:  dm_ot_patch.reset(); imgs = pipe(...)
"""
import math
import os
import zlib

import torch

MODE = os.environ.get("DM_COUPLING", "positional")
EPS_REL = float(os.environ.get("DM_OT_EPS_REL", "0.005"))
ITERS = int(os.environ.get("DM_OT_ITERS", "100"))
NSUB = int(os.environ.get("DM_OT_NSUB", "1024"))
_CACHE = {}          # (layer name, step id) -> (TA, TB), each (B, N, C) in the maps' dtype
STATS = {"solves": 0, "eff_partners": [], "fallback_non3d": 0}


def reset():
    """Call before every pair: the cached targets belong to one (A, B) pair."""
    _CACHE.clear()
    STATS["solves"] = 0
    STATS["eff_partners"] = []
    STATS["fallback_non3d"] = 0


def _bary(src, tgt):
    """Balanced entropic OT in the log domain (uniform masses), barycentric projection of src onto tgt."""
    C = torch.cdist(src, tgt).pow(2)
    eps = EPS_REL * C.median().clamp_min(1e-12)
    n, m = C.shape
    la, lb = -math.log(n), -math.log(m)
    f = torch.zeros(n, device=src.device)
    g = torch.zeros(m, device=src.device)
    for _ in range(ITERS):
        f = eps * (la - torch.logsumexp((g[None] - C) / eps, 1))
        g = eps * (lb - torch.logsumexp((f[:, None] - C) / eps, 0))
    W = torch.softmax((f[:, None] + g[None] - C) / eps, 1)
    STATS["eff_partners"].append(float(torch.exp(-(W * torch.log(W.clamp_min(1e-30))).sum(1)).mean()))
    STATS["solves"] += 1
    return W @ tgt


def _transport(src, tgt, seed):
    """Targets for every src token: exact barycentric map if small, else solve on NSUB samples and move each token by
    its nearest sample's displacement (keeps the K/V set diverse instead of duplicating sampled values)."""
    N = src.shape[0]
    if N <= NSUB:
        return _bary(src, tgt)
    g = torch.Generator(device="cpu").manual_seed(seed)
    i_s = torch.randperm(N, generator=g)[:NSUB].to(src.device)
    i_t = torch.randperm(tgt.shape[0], generator=g)[:NSUB].to(src.device)
    s = src[i_s]
    disp = _bary(s, tgt[i_t]) - s
    nn_ = torch.cdist(src, s).argmin(1)
    return src + disp[nn_]


def _targets(name, id_, map0, map1):
    key = (name, id_)
    if key not in _CACHE:
        m0, m1 = map0.float(), map1.float()
        seed = (zlib.crc32(name.encode()) % 100003) * 101 + int(id_)   # deterministic across processes
        TA = torch.stack([_transport(m0[b], m1[b], seed + 7 * b) for b in range(m0.shape[0])]).to(map0.dtype)
        TB = torch.stack([_transport(m1[b], m0[b], seed + 7 * b + 3) for b in range(m1.shape[0])]).to(map1.dtype)
        _CACHE[key] = (TA, TB)
    return _CACHE[key]


def blend(name, id_, map0, map1, alpha):
    if MODE == "positional" or map0.dim() != 3:
        if MODE != "positional": STATS["fallback_non3d"] += 1
        return (1 - alpha) * map0 + alpha * map1
    TA, TB = _targets(name, id_, map0, map1)
    if MODE == "ot_onesided" or alpha <= 0.5:
        return (1 - alpha) * map0 + alpha * TA
    return alpha * map1 + (1 - alpha) * TB


def install():
    import model as dm_model

    def __call__(self, attn, hidden_states, *args, encoder_hidden_states=None, attention_mask=None, **kwargs):
        # Is self attention  (identical control flow to DiffMorpher's LoadProcessor.__call__)
        if encoder_hidden_states is None:
            if self.id < 50 * self.lamd:
                map0 = self.img0_dict[self.name][self.id]
                map1 = self.img1_dict[self.name][self.id]
                cross_map = self.beta * hidden_states + \
                    (1 - self.beta) * blend(self.name, self.id, map0, map1, self.alpha)   # <- the one changed line
                res = self.original_processor(attn, hidden_states, *args,
                                              encoder_hidden_states=cross_map,
                                              attention_mask=attention_mask,
                                              **kwargs)
            else:
                res = self.original_processor(attn, hidden_states, *args,
                                              encoder_hidden_states=encoder_hidden_states,
                                              attention_mask=attention_mask,
                                              **kwargs)
            self.id += 1
            if self.id == len(self.img0_dict[self.name]):
                self.id = 0
        else:
            res = self.original_processor(attn, hidden_states, *args,
                                          encoder_hidden_states=encoder_hidden_states,
                                          attention_mask=attention_mask,
                                          **kwargs)
        return res

    dm_model.LoadProcessor.__call__ = __call__
    print(f"[dm_ot_patch] LoadProcessor patched: coupling={MODE}, eps_rel={EPS_REL}, iters={ITERS}, nsub={NSUB}", flush=True)
