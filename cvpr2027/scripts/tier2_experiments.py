# Tier-2 CVPR experiments (plan: "CVPR push: three experiments, Nov 10-16").
# Run in the Colab kernel AFTER the v2 notebook's config (cell 1) + setup (cell 5) and after
#   RUN_E1 = RUN_E2 = RUN_E3 = False; SMOKE = False; exec(open(".../tier1_experiments.py").read())   # helpers only
# then
#   T2_SMOKE = True;  exec(open(".../tier2_experiments.py").read())   # few pairs per part, into tier2_smoke/
#   T2_SMOKE = False; exec(open(".../tier2_experiments.py").read())   # full, into tier2/ (resumable)
# Parts (each switchable with RUN_R / RUN_A / RUN_C / RUN_B = False before exec):
#   R  regression check: soft OT vs positional at t = .5 on the 1,000 pairs must reproduce -9.35 (x1e-3)
#   A  pairing diagnostic: slack s and excess Gelbrich gap g per pair (CNT 1,000; DINO-RAE 120; SD-VAE 120),
#      A0 calibration on cyclic shifts, A1 tercile Delta-KID (report set = pairs 201-1,000), A2, A3
#   C  gradual hand-over on the two-sided path (field blend, window t in [.5, .75], smoothstep), 120 pairs
#   B  spatial transition: feasibility checks + field-blend canvas renders for 12 fixed-seed pairs (no gates tonight)
# Every part writes per-pair CSVs and a config JSON. Gates are the ones fixed in the plan, printed next to results.
import os, sys, json, time, glob, random, traceback, numpy as np, pandas as pd, torch, torch.nn.functional as F
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.stats import spearmanr

T2_SMOKE = globals().get("T2_SMOKE", True)
RUN_R, RUN_A, RUN_C, RUN_B = (globals().get(n, True) for n in ("RUN_R", "RUN_A", "RUN_C", "RUN_B"))
T2 = f"{OUT}/tier2_smoke" if T2_SMOKE else f"{OUT}/tier2"
os.makedirs(T2, exist_ok=True)
INP = f"{OUT}/tier2_inputs"
CFG = dict(smoke=T2_SMOKE, m_cells=1024, slack_seed="pair id", report_set="manifest pairs 201-1000", dev_set="manifest pairs 1-200",
           handover_window=[0.5, 0.75], handover_shape="smoothstep", b_canvas=[256, 768], b_fixed_seed="tier2-fixed-12",
           n_boot=500)
json.dump(CFG, open(f"{T2}/config.json", "w"), indent=1)
LOG = open(f"{T2}/log.txt", "a")
def say2(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.write(s + "\n"); LOG.flush()
def part(name, fn):
    t0 = time.time(); say2(f"\n========== {name} ==========")
    try:
        fn(); say2(f"{name} done ({(time.time() - t0) / 60:.1f} min)")
    except Exception as e:
        say2(f"{name} FAILED: {type(e).__name__}: {e}"); say2(traceback.format_exc()[-3000:])
def smooth(u): u = np.clip(u, 0, 1); return u * u * (3 - 2 * u)


# ============================== shared: slack and Gelbrich gap ==============================
def _psd_sqrt(M):
    w, V = np.linalg.eigh((M + M.T) / 2); return (V * np.sqrt(np.clip(w, 0, None))) @ V.T
def gelbrich(x, y):
    """Squared W2 between the Gaussians fitted to x and y (population moments, no ridge)."""
    ma, mb = x.mean(0), y.mean(0); Sa = np.cov(x, rowvar=False, bias=True); Sb = np.cov(y, rowvar=False, bias=True)
    ra = _psd_sqrt(Sa); w = np.linalg.eigvalsh(ra @ Sb @ ra)
    return float(((ma - mb) ** 2).sum() + np.trace(Sa) + np.trace(Sb) - 2 * np.sqrt(np.clip(w, 0, None)).sum())
def ot_cost(x, y):
    C = ((x[:, None, :] - y[None, :, :]) ** 2).sum(-1) if x.shape[1] <= 8 else (
        (x ** 2).sum(1)[:, None] + (y ** 2).sum(1)[None, :] - 2 * x @ y.T)
    r, c = linear_sum_assignment(C); return float(np.clip(C[r, c], 0, None).mean())
def slack_stats(X, Y, seed, m=1024, null=True):
    """X, Y: (N, C) co-indexed features of A and B (cell i of A sits where cell i of B sits)."""
    X = np.asarray(X, np.float64); Y = np.asarray(Y, np.float64); N = len(X)
    idx = np.random.default_rng(int(seed)).permutation(N)[:min(m, N)]
    x, y = X[idx], Y[idx]
    c_pos = float(((x - y) ** 2).sum(1).mean()); c_ot = ot_cost(x, y); wg = gelbrich(x, y)
    s = 0.0 if c_pos <= 1e-12 else 1 - c_ot / c_pos
    g = float("nan") if c_ot <= 1e-12 else 1 - wg / c_ot
    out = dict(n=len(idx), C_pos=c_pos, C_ot=c_ot, W2G=wg, s=s, g=g)
    if null:   # Gaussian null: same sample sizes drawn from the fitted Gaussians, g computed the same way
        rng = np.random.default_rng(int(seed) + 1)
        def draw(z):
            mu = z.mean(0); R = _psd_sqrt(np.cov(z, rowvar=False, bias=True)); return mu + rng.standard_normal(z.shape) @ R
        xn, yn = draw(x), draw(y); cn = ot_cost(xn, yn)
        out["g_null"] = float("nan") if cn <= 1e-12 else 1 - gelbrich(xn, yn) / cn
        out["g_excess"] = out["g"] - out["g_null"]
    return out
def slack_unit_tests():
    rng = np.random.default_rng(0); X = rng.standard_normal((512, 6))
    r = slack_stats(X, X.copy(), 1, null=False); assert abs(r["s"]) < 1e-12, r
    r = slack_stats(X, X[rng.permutation(512)], 1, null=False); assert abs(r["s"] - 1) < 1e-9, r
    r = slack_stats(X, X + 0.7, 1, null=False); assert abs(r["s"]) < 1e-9, r
    A = rng.standard_normal((1024, 6)); B = rng.standard_normal((1024, 6)) * 1.5 + 0.3
    r = slack_stats(A, B, 2); assert 0 <= r["g"] <= 1 and abs(r["g_excess"]) < 0.15, r
    say2(f"slack unit tests passed (Gaussian clouds: g={r['g']:.3f}, null={r['g_null']:.3f})")


# ============================== R: regression check ==============================
def part_R():
    ALL = MAN["pairs"]; CH = 50
    Z = [np.load(f"{OUT}/tier1/e1_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]
    Fs = np.concatenate([z["soft_ot@0.5"] for z in Z]); Fp = np.concatenate([z["field_linear@0.5"] for z in Z])
    r = dkid(Fs, Fp); say2("regression: soft OT vs positional, t=.5, 1,000 pairs:", r, "(expected -9.35)")
    assert abs(r["dKIDx1e3"] + 9.35) < 0.15, "regression check failed: the scorer does not reproduce the paper"


# ============================== A ==============================
def a_cnt_rows(pairs, path, with_recon=True):
    done = set(pd.read_csv(path).k) if os.path.exists(path) else set(); rows = []
    for i, p in enumerate(pairs):
        k = int(p["k"])
        if k in done: continue
        with torch.no_grad():
            d = pair_d(p); _, _, _, _, sf, tf = cnt.grids(d)
            r = dict(rep="CNT", k=k, **slack_stats(sf.float().cpu().numpy(), tf.float().cpu().numpy(), k))
            if with_recon:
                rec = cnt.to_pil(cnt.field_linear(d, 0.0)); a = endpoint(p["cA"], p["fA"]).convert("RGB").resize((256, 256))
                fd = ext.dino_feats([rec, a]); r["recon_err"] = float(np.linalg.norm(fd[0] - fd[1]))
        rows.append(r)
        if len(rows) == 25 or i == len(pairs) - 1:
            pd.DataFrame(rows).to_csv(path, mode="a", header=not os.path.exists(path), index=False); rows = []
            say2(f"  CNT slack {i + 1}/{len(pairs)}")
    if rows: pd.DataFrame(rows).to_csv(path, mode="a", header=not os.path.exists(path), index=False)

def part_A():
    slack_unit_tests()
    # ---- A0: calibration on cyclic shifts of seamless images (mirror-tiled 128 px endpoints, 40 images)
    a0p = f"{T2}/a0_shift_calibration.csv"
    if not os.path.exists(a0p):
        rows = []
        srcs = MAN["pairs"][:4 if T2_SMOKE else 40]
        for j, p in enumerate(srcs):
            a = np.asarray(endpoint(p["cA"], p["fA"]).convert("RGB").resize((128, 128)))
            tile = np.vstack([np.hstack([a, a[:, ::-1]]), np.hstack([a[::-1], a[::-1, ::-1]])])   # seamless 256 px
            fa = None
            for sh in (0, 4, 16, 64):
                b = np.roll(tile, sh, axis=1)
                with torch.no_grad():
                    d = cnt.build_pair(cnt.load_image(Image.fromarray(tile)), cnt.load_image(Image.fromarray(b)))
                    _, _, _, _, sf, tf = cnt.grids(d)
                r = slack_stats(sf.float().cpu().numpy(), tf.float().cpu().numpy(), 1000 + j, null=False)
                rows.append(dict(img=j, k=int(p["k"]), shift=sh, s=r["s"], C_pos=r["C_pos"], C_ot=r["C_ot"]))
        pd.DataFrame(rows).to_csv(a0p, index=False)
    A0 = pd.read_csv(a0p); W = A0.pivot(index="img", columns="shift", values="s")
    zero = (W[0].abs() < 1e-9).all(); mono = int((np.diff(W.values, axis=1) >= -1e-9).all(1).sum())
    need = int(np.ceil(0.9 * len(W)))
    say2("A0 mean s by shift:", W.mean().round(3).to_dict(), f"| s=0 at shift 0: {zero} | monotone in {mono}/{len(W)}",
         f"| GATE (s=0 at 0 and monotone in >= {need}): {'PASS' if zero and mono >= need else 'FAIL -> A1-A3 below are conditional on fixing the index'}")
    # ---- slack per pair and representation
    cntp = f"{T2}/a_slack_cnt.csv"
    a_cnt_rows(MAN["pairs"][:6] if T2_SMOKE else MAN["pairs"], cntp)
    raep = f"{T2}/a_slack_rae.csv"
    if not os.path.exists(raep):
        rows = []
        for p in (PAIRS[:3] if T2_SMOKE else PAIRS):
            k = int(p["k"]); xa = enc_dino(endpoint(p["cA"], p["fA"])); xb = enc_dino(endpoint(p["cB"], p["fB"]))
            rows.append(dict(rep="DINO-RAE", k=k, **slack_stats(xa.float().cpu().numpy().reshape(-1, xa.shape[-1]),
                                                                xb.float().cpu().numpy().reshape(-1, xb.shape[-1]), k)))
        pd.DataFrame(rows).to_csv(raep, index=False)
    sdp = f"{T2}/a_slack_sdvae.csv"
    if not os.path.exists(sdp):
        from diffusers import AutoencoderKL
        vae = AutoencoderKL.from_pretrained(f"{SD_DIR}/vae").to(DEV).eval(); SF = vae.config.scaling_factor
        rows = []
        for p in (PAIRS[:3] if T2_SMOKE else PAIRS):
            k = int(p["k"]); toks = []
            for c_, f_ in ((p["cA"], p["fA"]), (p["cB"], p["fB"])):
                with torch.no_grad():
                    z = vae.encode((to01(endpoint(c_, f_), 256) * 2 - 1).to(DEV)).latent_dist.mean * SF
                toks.append(z[0].flatten(1).t().float().cpu().numpy())
            rows.append(dict(rep="SD-VAE", k=k, **slack_stats(toks[0], toks[1], k)))
        pd.DataFrame(rows).to_csv(sdp, index=False); del vae; torch.cuda.empty_cache()
    S = pd.concat([pd.read_csv(p) for p in (cntp, raep, sdp)])
    say2("slack summary by representation:\n" + S.groupby("rep")[["s", "g", "g_null", "g_excess"]].agg(["mean", "median"]).round(3).to_string())
    # ---- A1: tercile Delta-KID on the report set (pairs 201-1,000), CNT
    if T2_SMOKE: say2("A1-A3 skipped in smoke mode"); return
    ALL = MAN["pairs"]; CH = 50
    Z = [np.load(f"{OUT}/tier1/e1_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]
    ks = np.concatenate([z["ks"] for z in Z]); Fs = np.concatenate([z["soft_ot@0.5"] for z in Z]); Fp = np.concatenate([z["field_linear@0.5"] for z in Z])
    C = pd.read_csv(cntp).drop_duplicates("k").set_index("k")
    pos = {int(k): i for i, k in enumerate(ks)}
    def tercile_test(sel, label, nb=CFG["n_boot"]):
        sub = C.loc[[k for k in sel if k in C.index]]; order = sub.sort_values("s").index.tolist(); n3 = len(order) // 3
        terc = [order[:n3], order[n3:2 * n3], order[2 * n3:]]
        rows = []
        for ti, kk in enumerate(terc):
            ii = [pos[k] for k in kk]; rows.append(dict(set=label, tercile=ti + 1, n=len(ii), s_mean=float(sub.loc[kk, "s"].mean()), **dkid(Fs[ii], Fp[ii])))
        ib, it = np.array([pos[k] for k in terc[0]]), np.array([pos[k] for k in terc[2]])
        def dk(ii): return kid(Fs[ii]) - kid(Fp[ii])
        point = dk(it) - dk(ib); rng = np.random.default_rng(7); bs = []
        for _ in range(nb):
            bs.append(dk(rng.choice(it, len(it))) - dk(rng.choice(ib, len(ib))))
        lo, hi = np.percentile(bs, [2.5, 97.5])
        return rows, dict(set=label, top_minus_bottom=round(point, 2), lo=round(lo, 2), hi=round(hi, 2), excl0=bool(lo > 0 or hi < 0))
    rep_ks = [int(p["k"]) for p in ALL[200:]]; all_ks = [int(p["k"]) for p in ALL]
    out, summ = [], []
    for sel, lab in ((rep_ks, "report 201-1000"), (all_ks, "all 1000")):
        r, s_ = tercile_test(sel, lab); out += r; summ.append(s_)
    med = C.loc[rep_ks, "recon_err"].median()
    for half, cond in (("low recon error", C.loc[rep_ks, "recon_err"] <= med), ("high recon error", C.loc[rep_ks, "recon_err"] > med)):
        r, s_ = tercile_test([k for k, c in zip(rep_ks, cond) if c], f"report, {half}", nb=200); out += r; summ.append(s_)
    pd.DataFrame(out).to_csv(f"{T2}/a1_terciles.csv", index=False); pd.DataFrame(summ).to_csv(f"{T2}/a1_top_minus_bottom.csv", index=False)
    say2("A1 Delta-KID (soft OT - positional, t=.5) by slack tercile:\n" + pd.DataFrame(out).to_string(index=False)
         + "\nA1 top minus bottom tercile (negative = high-slack pairs gain more):\n" + pd.DataFrame(summ).to_string(index=False)
         + "\nA1 GATE (report set, interval excludes zero, high slack gains more): "
         + ("PASS" if summ[0]["excl0"] and summ[0]["top_minus_bottom"] < 0 else "FAIL"))
    # ---- A2: across representations (descriptive)
    gain = {"CNT": -3.43, "DINO-RAE": -5.79 - (-6.38), "SD-VAE": -19.83 - (-20.39)}   # soft OT minus Gaussian at t=.5, x1e-3
    A2 = S.groupby("rep").g_excess.mean().rename("mean_excess_g").to_frame(); A2["softOT_minus_gaussian_t05"] = [gain.get(r) for r in A2.index]
    A2.to_csv(f"{T2}/a2_across.csv"); say2("A2 (descriptive; gate: SD-VAE lowest excess g, CNT highest):\n" + A2.round(3).to_string())
    # ---- A3: study vote share vs slack (CNT and DINO-RAE study pairs; TM and DiffMorpher have no slack features here)
    key = list(pd.read_csv(f"{INP}/key_AUTHORS_ONLY.csv").to_dict("records")); codes = [l.strip() for l in open(f"{INP}/responses.txt") if l.strip()]
    votes = np.zeros(25); n = 0
    for c in codes:
        h = c.split("-")[2][:-1]; b = [int(x) for dd in h for x in f"{int(dd, 16):04b}"]
        if b[50:] != [1, 0]: continue
        n += 1
        for t_ in key: votes[int(t_["trial"])] += (t_["option_b"] if b[int(t_["trial"])] else t_["option_a"]) == "OT"
    rows = []
    for t_ in key:
        r = t_["representation"]; k = int(t_["k"])
        src = {"CNT": C, "RAE": pd.read_csv(raep).set_index("k")}.get(r)
        if src is not None and k in src.index: rows.append(dict(rep=r, k=k, vote_OT=votes[int(t_["trial"])] / n, s=float(src.loc[k, "s"])))
    A3 = pd.DataFrame(rows); A3.to_csv(f"{T2}/a3_votes_vs_slack.csv", index=False)
    rho, pv = spearmanr(A3.s, A3.vote_OT) if len(A3) > 3 else (np.nan, np.nan)
    say2(f"A3 Spearman(slack, OT vote share) on {len(A3)} study pairs ({n} participants): rho={rho:.3f}, p={pv:.3f} (reported whatever it is)")


# ============================== shared hand-over decode (C and B) ==============================
GEN = cnt.model.generator
def _splat_si(blob):
    with torch.no_grad(): return cnt.model.splat(blob)["layer_level_layouts"][-1][0]["score_img"]
def _fi(si, size):
    """Generator input exactly as CNT builds it: halve the splat map repeatedly (its _pyr), then max over primitives."""
    s = si
    while s.shape[-1] > size[1]:
        s = F.interpolate(s, size=(s.shape[-2] // 2, s.shape[-1] // 2), mode="bilinear", align_corners=False)
    assert tuple(s.shape[-2:]) == tuple(size), (s.shape, size)
    return s[:, 1:].amax(dim=1)[:, None].repeat(1, GEN.n_embedding, 1, 1)
def decode_mix(fiA, smA, fiB, smB, alpha, sizes):
    """CNT's decode_with_style_maps with the generator input and every style map blended by alpha (scalar or (H, W) map).
    `sizes` is the per-block list of (h, w), in CNT's order, repeats included. alpha = 0 reproduces A's decode exactly."""
    def mix(a, b, size):
        if isinstance(alpha, (int, float)):
            return a if alpha == 0 else (b if alpha == 1 else (1 - alpha) * a + alpha * b)
        al = F.interpolate(alpha[None, None], size=size, mode="bilinear", align_corners=False)
        return (1 - al) * a + al * b
    with torch.no_grad():
        x = mix(fiA, fiB, sizes[0])
        for i, s in enumerate(sizes):
            x = GEN.spade_blocks[i](x, mix(smA[s], smB[s], s))
            if i == len(sizes) - 1: break
            if sizes[i] != sizes[i + 1]: x = F.interpolate(x, size=(x.shape[-2] * 2, x.shape[-1] * 2), mode="bilinear", align_corners=False)
        return torch.tanh(x.unsqueeze(1)).flatten(1, 2)
def square_inputs(d_layout, Z, fd):
    """Generator input and style maps for a square CNT field Z under layout blob d_layout['blob_a']."""
    si = _splat_si(d_layout["blob_a"]); fms = [round(si.shape[-1] * r) for r in GEN.feature_map_size_ratios]
    sm = cnt.sm_from_field(Z.float(), fd["L"], fd["H"], fd["W"], fd["C"])
    return _fi(si, (fms[0], fms[0])), {(s, s): sm[s] for s in fms}, [(s, s) for s in fms]


# ============================== C: gradual hand-over along the two-sided path ==============================
def part_C():
    meth = "cnt_twosided_handover"; P = PAIRS[:3] if T2_SMOKE else PAIRS
    def frames_for(p, ts):
        k = int(p["k"]); dAB, dBA = pair_d(p), pair_d(p, rev=True)
        fA = matching.field(cnt, dAB, "soft_ot", seed=k, **MATCH_KW); fB = matching.field(cnt, dBA, "soft_ot", seed=k, **MATCH_KW)
        out = []
        for t in ts:
            al = float(smooth((t - 0.5) / 0.25))
            if al == 0: out.append(cnt.to_pil(dec(dAB, fA, t)))
            elif al == 1: out.append(cnt.to_pil(dec(dBA, fB, 1 - t)))
            else:
                fiA, smA, sz = square_inputs(dAB, matching.zt(fA, t), fA); fiB, smB, _ = square_inputs(dBA, matching.zt(fB, 1 - t), fB)
                out.append(cnt.to_pil(decode_mix(fiA, smA, fiB, smB, al, sz)))
        return out, (dAB, fA, dBA, fB)
    # identity tests first: decode_mix at alpha 0 / 1 equals CNT's own decode; t <= .5 and t >= .75 equal the stored two-sided frames
    p0 = PAIRS[0]; k0 = int(p0["k"]); dAB = pair_d(p0); fA = matching.field(cnt, dAB, "soft_ot", seed=k0, **MATCH_KW)
    fiA, smA, sz = square_inputs(dAB, matching.zt(fA, 0.3), fA)
    ref = dec(dAB, fA, 0.3); mine = decode_mix(fiA, smA, fiA, smA, 0, sz)
    say2(f"C identity (decode_mix alpha=0 vs CNT decode): max abs diff {float((ref - mine).abs().max()):.2e}")
    assert float((ref - mine).abs().max()) < 1e-4, "decode_mix does not reproduce CNT's decoder"
    worst = 0
    for p in PAIRS[:5]:
        fr, _ = frames_for(p, T_GRID); old = load_frames("cnt_twosided_soft_ot", int(p["k"]))
        for ti, t in enumerate(T_GRID):
            if t <= 0.5 or t >= 0.75:
                worst = max(worst, int(np.abs(np.asarray(fr[ti], np.int16) - old[ti].astype(np.int16)).max()))
    say2(f"C identity vs stored two-sided frames at t<=.5 and t>=.75 (5 pairs): max pixel diff {worst} / 255 "
         f"-> {'PASS' if worst <= 2 else 'FAIL'}")
    # render the 120 pairs at the nine coefficients
    for i, p in enumerate(P):
        k = int(p["k"])
        if have(meth, k) and not T2_SMOKE: continue
        fr, _ = frames_for(p, T_GRID)
        if not T2_SMOKE: save_frames(meth, k, fr)
        if (i + 1) % 30 == 0: say2(f"  C {i + 1}/{len(P)}")
    # clips: 12 fixed-seed pairs at 17 coefficients
    clipd = f"{T2}/c_clips"; os.makedirs(clipd, exist_ok=True)
    fixed = random.Random(CFG["b_fixed_seed"]).sample(EVAL_KS, 2 if T2_SMOKE else 12)
    BYK_ = {int(p["k"]): p for p in PAIRS}; ts17 = list(np.linspace(0, 1, 17))
    for k in fixed:
        fr, _ = frames_for(BYK_[k], ts17)
        fr[0].save(f"{clipd}/handover_{k:04d}.gif", save_all=True, append_images=fr[1:], duration=180, loop=0)
        strip = Image.new("RGB", (17 * 128, 128)); [strip.paste(f.resize((128, 128)), (i * 128, 0)) for i, f in enumerate(fr)]
        strip.save(f"{clipd}/handover_{k:04d}_strip.png")
    if T2_SMOKE: say2("C smoke renders ok"); return
    # metrics
    z = np.load(f"{OUT}/feats/endpoints.npz"); EA, EB = z["a"], z["b"]; EI = {int(k): i for i, k in enumerate(z["ks"])}
    lp = get_lpips()
    def lpips_steps(fr):
        x = torch.stack([torch.from_numpy(f).permute(2, 0, 1).float() / 127.5 - 1 for f in fr]).to(DEV)
        with torch.no_grad(): return lp(x[:-1], x[1:]).flatten().cpu().numpy()
    rows, INC = [], {}
    for m in (meth, "cnt_twosided_soft_ot", "cnt_twosided_field_linear"):
        ks = [k for k in EVAL_KS if have(m, k)]; Wp = np.zeros((len(ks), len(T_GRID))); inc = []
        for j, k in enumerate(ks):
            fr = load_frames(m, k); dn = ext.dino_feats([Image.fromarray(x) for x in fr])
            dA = np.linalg.norm(dn - EA[EI[k]], axis=1); dB = np.linalg.norm(dn - EB[EI[k]], axis=1); Wp[j] = dA / (dA + dB + 1e-12)
            st = lpips_steps(fr); inc.append(Image.fromarray(fr[list(T_GRID).index(0.625)]))
            rows.append(dict(method=m, k=k, **{f"place_t{t}": Wp[j, ti] for ti, t in enumerate(T_GRID)},
                             lpips_in_window=float(st[4:6].max()), lpips_outside=float(np.delete(st, [4, 5]).max())))
        steps = np.diff(Wp, axis=1); span = Wp[:, -1] - Wp[:, 0]; mv = span > 0.05
        INC[m] = (ks, inc128(inc)); say2(f"  {m}: max_jump_share {np.median(steps[mv].max(1) / span[mv]):.3f} (n={len(ks)})")
    R = pd.DataFrame(rows); R.to_csv(f"{T2}/c_per_pair.csv", index=False)
    def fe(m, ks_): kk, f = INC[m]; idx = {k: i for i, k in enumerate(kk)}; return f[[idx[k] for k in ks_]]
    common = sorted(set(INC[meth][0]) & set(INC["cnt_twosided_soft_ot"][0]) & set(INC["cnt_twosided_field_linear"][0]))
    d_old = dkid(fe(meth, common), fe("cnt_twosided_soft_ot", common)); d_pos = dkid(fe(meth, common), fe("cnt_twosided_field_linear", common))
    js = {}
    for m in (meth, "cnt_twosided_soft_ot"):
        g = R[R.method == m]; Wp = g[[f"place_t{t}" for t in T_GRID]].values; st = np.diff(Wp, axis=1); sp = Wp[:, -1] - Wp[:, 0]; mv = sp > 0.05
        js[m] = float(np.median(st[mv].max(1) / sp[mv]))
    g = R[R.method == meth]; flick = float((g.lpips_in_window > g.lpips_outside).mean())
    summ = dict(jump_share_handover=round(js[meth], 3), jump_share_old_twosided=round(js["cnt_twosided_soft_ot"], 3),
                dKID_t0625_vs_old_twosided=d_old, dKID_t0625_vs_twosided_positional=d_pos, share_pairs_window_lpips_above_outside=round(flick, 3))
    json.dump(summ, open(f"{T2}/c_summary.json", "w"), indent=1, default=str)
    say2("C results:", json.dumps(summ, default=str))
    say2("C GATES: spread (jump <= .35): " + ("PASS" if js[meth] <= 0.35 else "FAIL")
         + " | not worse at .625 (upper CI < +2.5): " + ("PASS" if d_old["hi"] < 2.5 else "FAIL")
         + " | beats two-sided positional at .625 (CI < 0): " + ("PASS" if d_pos["hi"] < 0 else "FAIL")
         + " | flicker: see share above and the clips (look before believing the jump number)")


# ============================== B: spatial transition (feasibility + 12 fixed-seed canvases) ==============================
def part_B():
    H_, W_ = CFG["b_canvas"]; bd = f"{T2}/b_canvas"; os.makedirs(bd, exist_ok=True)
    def native(cat, fn):
        im = Image.open(f"{DTD_ROOT}/{cat}/{fn}").convert("RGB"); w, h = im.size; im = im.resize((max(1, round(w * H_ / h)), H_), Image.LANCZOS)
        a = np.asarray(im)
        while a.shape[1] < W_: a = np.concatenate([a, a[:, ::-1]], axis=1)   # mirror-extend narrow images
        x0 = (a.shape[1] - W_) // 2; return Image.fromarray(a[:, x0:x0 + W_])
    # feasibility 1: CNT's normalisation, then encode/decode a non-square canvas
    p0 = PAIRS[0]; sq = native(p0["cA"], p0["fA"]).crop((0, 0, H_, H_)); ref = cnt.load_image(sq)
    base = torch.from_numpy(np.asarray(sq)).permute(2, 0, 1).float()[None].to(ref.device)
    PM1 = float((ref - (base / 127.5 - 1)).abs().max()) <= float((ref - base / 255).abs().max())
    def to_t(pil):
        x = torch.from_numpy(np.asarray(pil)).permute(2, 0, 1).float()[None].to(ref.device); return x / 127.5 - 1 if PM1 else x / 255
    def to_pm1(pil): x = to_t(pil); return x if PM1 else x * 2 - 1
    say2(f"B feasibility: CNT input range {'[-1, 1]' if PM1 else '[0, 1]'}, reproduced to {float((ref - to_t(sq)).abs().max()):.3f}")
    def rect_inputs(blob, bf, si, Z=None):
        """Generator input, rectangular style maps and per-block sizes; Z (C, h, w) replaces the finest field if given."""
        h, w = si.shape[-2:]; sizes = [(round(h * r), round(w * r)) for r in GEN.feature_map_size_ratios]
        fin = torch.einsum("bnc,bnhw->bchw", bf, si) if Z is None else Z[None]
        sm = {s: (fin if s == (h, w) else F.interpolate(fin, size=s, mode="bilinear", align_corners=False)) for s in set(sizes)}
        return _fi(si, sizes[0]), sm, fin[0], sizes
    # CNT's layout network only accepts square 128 / 256 px inputs (feasibility check 1 failed), so a wide canvas is
    # encoded as overlapping square crops whose fields and generator inputs are blended linearly across the overlaps.
    say2("B feasibility: CNT encoder requires square 256 px input -> canvas built from overlapping square crops")
    X0 = [0, 170, 341, 512]
    def wide_inputs(pil):
        h, w = H_, W_; sizes = [(round(h * r), round(w * r)) for r in GEN.feature_map_size_ratios]
        Z = None; FI = None; wz = torch.zeros(w, device=ref.device); wf = torch.zeros(sizes[0][1], device=ref.device)
        for x0 in X0:
            crop = pil.crop((x0, 0, x0 + H_, H_))
            with torch.no_grad():
                blob = cnt.model.encode(to_t(crop)); lay = cnt.model.splat(blob)["layer_level_layouts"][-1][0]
            bf, si = lay["blob_features"], lay["score_img"]
            z = torch.einsum("bnc,bnhw->bchw", bf, si)[0]
            fi = _fi(si, (sizes[0][0], sizes[0][0]))
            if Z is None:
                Z = torch.zeros(z.shape[0], h, w, device=ref.device); FI = torch.zeros(fi.shape[1], sizes[0][0], sizes[0][1], device=ref.device)
            ramp = torch.ones(H_, device=ref.device); ov = 86
            if x0 > 0: ramp[:ov] = torch.linspace(0, 1, ov, device=ref.device)
            if x0 + H_ < w: ramp[-ov:] = torch.linspace(1, 0, ov, device=ref.device)
            Z[:, :, x0:x0 + H_] += z * ramp; wz[x0:x0 + H_] += ramp
            s = sizes[0][0] / H_; a0 = round(x0 * s); rr = F.interpolate(ramp[None, None], size=sizes[0][0], mode="linear", align_corners=False)[0, 0]
            FI[:, :, a0:a0 + sizes[0][0]] += fi[0] * rr; wf[a0:a0 + sizes[0][0]] += rr
        return Z / wz.clamp_min(1e-6), (FI / wf.clamp_min(1e-6))[None], sizes
    def sm_of(Z, sizes): return {s: F.interpolate(Z[None], size=s, mode="bilinear", align_corners=False) if s != tuple(Z.shape[-2:]) else Z[None] for s in set(sizes)}
    wide = native(p0["cA"], p0["fA"]); Zw, FIw, sz = wide_inputs(wide)
    rec = cnt.to_pil(decode_mix(FIw, sm_of(Zw, sz), FIw, sm_of(Zw, sz), 0, sz)); rec.save(f"{bd}/feasibility_wide_recon.png"); wide.save(f"{bd}/feasibility_wide_input.png")
    lp = get_lpips()
    with torch.no_grad(): lpv = float(lp(to_pm1(rec.resize(wide.size)), to_pm1(wide)).mean())
    say2(f"B feasibility: wide decode OK {rec.size}; reconstruction LPIPS {lpv:.3f} (square reconstructions are about 0.21); saved for a look")
    fixed = random.Random(CFG["b_fixed_seed"]).sample(EVAL_KS, 2 if T2_SMOKE else 12); BYK_ = {int(p["k"]): p for p in PAIRS}
    xs = np.linspace(0, 1, W_); amap = smooth((xs - 1 / 3) * 3)
    for k in fixed:
        p = BYK_[k]; ia, ib = native(p["cA"], p["fA"]), native(p["cB"], p["fB"])
        SA, fiA, sz = wide_inputs(ia); SB, fiB, _ = wide_inputs(ib)
        Cc, h, w = SA.shape; XA = SA.reshape(Cc, -1).t().contiguous(); XB = SB.reshape(Cc, -1).t().contiguous()
        def transport(X, Y, rule):
            i_s, tt = matching.targets(X, Y, rule, k, **MATCH_KW)
            nn = torch.cat([torch.cdist(X[j:j + 32768], X[i_s]).argmin(1) for j in range(0, len(X), 32768)]); return tt[nn]
        tcol = torch.tensor(xs, dtype=SA.dtype, device=SA.device)[None, None, :]
        amap2 = torch.tensor(amap, dtype=SA.dtype, device=SA.device)[None, :].expand(h, w).contiguous()
        outs = {}
        for rule in ("soft_ot", "gaussian"):
            UA = transport(XA, XB, rule).t().reshape(Cc, h, w); UB = transport(XB, XA, rule).t().reshape(Cc, h, w)
            FA = (1 - tcol) * SA + tcol * UA; FB = tcol * SB + (1 - tcol) * UB
            outs[f"twosided_{rule}_handover"] = cnt.to_pil(decode_mix(fiA, sm_of(FA, sz), fiB, sm_of(FB, sz), amap2, sz))
            if rule == "soft_ot": outs["directed_soft_ot"] = cnt.to_pil(decode_mix(fiA, sm_of(FA, sz), fiA, sm_of(FA, sz), 0, sz))
        PZ = (1 - tcol) * SA + tcol * SB
        outs["positional"] = cnt.to_pil(decode_mix(fiA, sm_of(PZ, sz), fiA, sm_of(PZ, sz), 0, sz))
        tr = xs[None, :, None]
        outs["rgb_alpha"] = Image.fromarray(np.clip((1 - tr) * np.asarray(ia, np.float32) + tr * np.asarray(ib, np.float32), 0, 255).astype(np.uint8))
        order = ["rgb_alpha", "positional", "directed_soft_ot", "twosided_gaussian_handover", "twosided_soft_ot_handover"]
        cv = Image.new("RGB", (W_, H_ * len(order)), "white")
        for r_, m in enumerate(order): cv.paste(outs[m].resize((W_, H_)), (0, r_ * H_))
        cv.save(f"{bd}/canvas_{k:04d}.png"); ia.save(f"{bd}/input_A_{k:04d}.png"); ib.save(f"{bd}/input_B_{k:04d}.png")
        say2(f"  B canvas {k:04d} saved (rows: {', '.join(order)})")
    say2("B: renders only tonight; gates and the field-blend vs primitive decision are made by eye in the morning")


if RUN_R: part("R regression", part_R)
if RUN_A: part("A pairing diagnostic", part_A)
if RUN_C: part("C gradual hand-over", part_C)
if RUN_B: part("B spatial transition (feasibility + renders)", part_B)
say2("TIER-2 FINISHED", "(smoke)" if T2_SMOKE else "")
