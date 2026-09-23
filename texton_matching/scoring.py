"""KID / FID / paired-jackknife scoring, matched to the paper's canonical protocol.

This module is CPU-only (numpy + scipy) and has no CNT, torch or TensorFlow
dependency, so it can run in the minimal score-only environment against
cached Inception/DINOv2 feature files.

KID uses the standard cubic polynomial kernel k(a, b) = (a . b / d + 1)^3
(Binkowski et al. 2018) and the unbiased U-statistic estimator. The
reference (real-image) self-term subtracts the kernel's own diagonal
(np.trace(K_ref)), not len(ref) -- the two differ here because the cubic
kernel's diagonal is not 1 (k(x, x) = (||x||^2/d + 1)^3). The trace form is
what the paper's numbers.tex / numbers_v2.tex macros were computed with, in
notebooks jackknife_dKID.ipynb and presubmission_additions.ipynb. Earlier
notebooks used the len(ref) form, which biases every absolute KID up by a
constant offset of about +0.000245 for this reference set; the offset
cancels exactly in every KID difference (paired jackknife), so it only
matters for absolute-KID reproduction, not for the delta-KID claims.

Paired leave-one-pair-out jackknife: for two same-length, same-pair-order
feature sets (A, B) scored against one fixed reference, the delta is
Delta = KID(B, ref) - KID(A, ref). For each pair i, delete it from both A
and B and recompute both KIDs on the remaining n-1 samples; theta_i is the
resulting delta. The jackknife standard error is
    SE = sqrt((n-1)/n * sum_i (theta_i - mean(theta))^2)
and the reported interval is Delta +/- 1.96 * SE. This reproduces
data/jackknife/jackknife_final.csv exactly (validated during package
construction; see docs/CHECK.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import linalg


# ---------------------------------------------------------------------------
# KID
# ---------------------------------------------------------------------------

def _poly_kernel(a: np.ndarray, b: np.ndarray, d: float) -> np.ndarray:
    return (a @ b.T / d + 1.0) ** 3


def _reference_self_term(ref: np.ndarray) -> float:
    """KYY: the (fixed) reference self-similarity term, trace-corrected."""
    ref = np.asarray(ref, dtype=np.float64)
    d = ref.shape[1]
    m = len(ref)
    Kyy = _poly_kernel(ref, ref, d)
    return float((Kyy.sum() - np.trace(Kyy)) / (m * (m - 1)))


def kid_full(gen: np.ndarray, ref: np.ndarray, kyy: float | None = None) -> float:
    """Unbiased polynomial-kernel KID of `gen` against the fixed `ref` set."""
    gen = np.asarray(gen, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    d = gen.shape[1]
    n = len(gen)
    if kyy is None:
        kyy = _reference_self_term(ref)
    Kxx = _poly_kernel(gen, gen, d)
    np.fill_diagonal(Kxx, 0.0)
    Kxy = _poly_kernel(gen, ref, d)
    return float(Kxx.sum() / (n * (n - 1)) + kyy - 2.0 * Kxy.mean())


def kid_leave_one_out(gen: np.ndarray, ref: np.ndarray, kyy: float | None = None) -> np.ndarray:
    """KID recomputed with each pair i deleted from `gen`, for i in range(n).

    Returns an array of length n. Used as the building block of the paired
    jackknife below; the reference set itself is never subsampled (it is
    the fixed 2,819-image pool), matching the notebooks' protocol.
    """
    gen = np.asarray(gen, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    d = gen.shape[1]
    n = len(gen)
    m = len(ref)
    if kyy is None:
        kyy = _reference_self_term(ref)
    Kxx = _poly_kernel(gen, gen, d)
    np.fill_diagonal(Kxx, 0.0)
    Kxy = _poly_kernel(gen, ref, d)

    Kxx_total = Kxx.sum()
    Kxx_row = Kxx.sum(1)
    Kxy_total = Kxy.sum()
    Kxy_row = Kxy.sum(1)

    out = np.empty(n)
    for i in range(n):
        xx_i = (Kxx_total - 2 * Kxx_row[i]) / ((n - 1) * (n - 2))
        xy_i = (Kxy_total - Kxy_row[i]) / ((n - 1) * m)
        out[i] = xx_i + kyy - 2.0 * xy_i
    return out


@dataclass
class PairedJackknifeResult:
    delta: float
    lo: float
    hi: float
    se: float
    n: int
    excludes_zero: bool


def paired_jackknife_delta_kid(
    gen_b: np.ndarray, gen_a: np.ndarray, ref: np.ndarray, z: float = 1.96
) -> PairedJackknifeResult:
    """Delta-KID(B - A) with a paired leave-one-pair-out jackknife CI.

    `gen_a` and `gen_b` must be aligned pair-for-pair (same row order, same
    set of pair ids) -- e.g. two columns of the same 120- or 200-pair
    evaluation. This reproduces every EqdKID*/TMdKID*/GdKID*/GEdKID*/TMkdKID*
    macro in the paper (see docs/CHECK.md).
    """
    kyy = _reference_self_term(ref)
    kid_b = kid_full(gen_b, ref, kyy)
    kid_a = kid_full(gen_a, ref, kyy)
    delta = kid_b - kid_a

    loo_b = kid_leave_one_out(gen_b, ref, kyy)
    loo_a = kid_leave_one_out(gen_a, ref, kyy)
    theta = loo_b - loo_a
    n = len(theta)
    tbar = theta.mean()
    se = float(np.sqrt((n - 1) / n * np.sum((theta - tbar) ** 2)))
    lo, hi = delta - z * se, delta + z * se
    return PairedJackknifeResult(delta=delta, lo=lo, hi=hi, se=se, n=n, excludes_zero=(lo > 0 or hi < 0))


# ---------------------------------------------------------------------------
# KID, repeated-subsample form (matched to the F3/F2 generation of notebooks:
# matching_ablation.ipynb, exact_finish.ipynb, finish_day.ipynb -- used for
# Table 1's CNT block and tab:rules). Unlike kid_full above (one pass against
# the whole fixed 2,819-image reference, used by the September/F4 notebooks
# for the generative, eqsample, primitive and Texture Mixer tables), this
# form draws n_rep independent subsamples of size min(n_sub, len(gen),
# len(ref)) from BOTH the generated and the reference set and averages the
# per-draw KID. Both forms use the trace-corrected self-term; they agree
# closely but not to machine precision, since they are different (both
# textbook-valid) unbiased estimators of the same population quantity.
# ---------------------------------------------------------------------------

def kid_subsampled(gen: np.ndarray, ref: np.ndarray, n_sub: int = 1000, n_rep: int = 20, seed: int = 0) -> float:
    rng = np.random.RandomState(seed)
    gen = np.asarray(gen, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    d = gen.shape[1]
    m = min(n_sub, len(gen), len(ref))
    vals = []
    for _ in range(n_rep):
        x = gen[rng.choice(len(gen), m, replace=False)]
        y = ref[rng.choice(len(ref), m, replace=False)]
        Kxx, Kyy, Kxy = _poly_kernel(x, x, d), _poly_kernel(y, y, d), _poly_kernel(x, y, d)
        vals.append(
            (Kxx.sum() - np.trace(Kxx)) / (m * (m - 1))
            + (Kyy.sum() - np.trace(Kyy)) / (m * (m - 1))
            - 2 * Kxy.mean()
        )
    return float(np.mean(vals))


# ---------------------------------------------------------------------------
# FID
# ---------------------------------------------------------------------------

def fid_score(gen: np.ndarray, ref: np.ndarray) -> float:
    """Frechet distance between two Gaussians fit to `gen` and `ref`."""
    gen = np.asarray(gen, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    mu_g, mu_r = gen.mean(0), ref.mean(0)
    cov_g, cov_r = np.cov(gen, rowvar=False), np.cov(ref, rowvar=False)
    covmean, _ = linalg.sqrtm(cov_g @ cov_r, disp=False)
    if np.iscomplexobj(covmean):
        covmean = covmean.real
    return float(((mu_g - mu_r) ** 2).sum() + np.trace(cov_g + cov_r - 2 * covmean))


# ---------------------------------------------------------------------------
# Balance / placement (from per-pair distance-to-endpoint CSVs)
# ---------------------------------------------------------------------------

def balance_from_place(place: np.ndarray) -> np.ndarray:
    """b_i = |place_i - 0.5|, where place_i = d(o,A) / (d(o,A) + d(o,B))."""
    return np.abs(np.asarray(place, dtype=np.float64) - 0.5)
