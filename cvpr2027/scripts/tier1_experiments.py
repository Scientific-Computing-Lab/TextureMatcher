# Tier-1 CVPR experiments. exec() in the Colab kernel AFTER the v2 notebook's config (cell 1) + setup (cell 5).
#   SMOKE = True; exec(open(PATH).read())     -> 2 pairs per experiment into OUT/tier1_smoke (catch errors in ~3 min)
#   SMOKE = False; exec(open(PATH).read())    -> full runs into OUT/tier1 (resumable: rerun after any disconnect)
# Experiments (each can be switched off with RUN_E1/RUN_E2/RUN_E3 = False before exec):
#   E1  two-sided operator on the full 1,000-pair benchmark: KID at t = .25 / .5 / .75 (features only, chunked + resumable)
#   E2  SD VAE latent interpolation: positional vs the matching family (+ two-sided), 120 pairs x 9 t
#   E3  spatial transitions (t ramps across the image): RGB alpha / positional / Gaussian / soft OT / sharp OT, 120 pairs
import os, sys, time, json, numpy as np, pandas as pd, torch
from PIL import Image

SMOKE = globals().get("SMOKE", True)
RUN_E1, RUN_E2, RUN_E3 = (globals().get(n, True) for n in ("RUN_E1", "RUN_E2", "RUN_E3"))
T1 = f"{OUT}/tier1_smoke" if SMOKE else f"{OUT}/tier1"
os.makedirs(T1, exist_ok=True)
sys.path.insert(0, "/content/package")
import rescore
ext = rescore.Extractor(DEV)
ref_inc = np.load(REF_INC); kyy = scoring._reference_self_term(ref_inc)
cnt = get_cnt()
if "lora_mods" in globals(): set_lora(False)


def inc128(pils): return ext.inc_feats([p.convert("RGB").resize((128, 128), Image.BICUBIC) for p in pils])
def kid(f): return 1e3 * scoring.kid_full(f, ref_inc, kyy)
def dkid(a, b):
    r = scoring.paired_jackknife_delta_kid(a, b, ref_inc)
    return dict(dKIDx1e3=round(1e3 * r.delta, 2), lo=round(1e3 * r.lo, 2), hi=round(1e3 * r.hi, 2), excl0=r.excludes_zero)
def dec(d, fd, t): return cnt.decode_field(d, matching.zt(fd, t), fd["L"], fd["H"], fd["W"], fd["C"])
def pair_d(p, rev=False):
    a, b = cnt.load_image(endpoint(p["cA"], p["fA"])), cnt.load_image(endpoint(p["cB"], p["fB"]))
    return cnt.build_pair(b, a) if rev else cnt.build_pair(a, b)
def say(*a): print(*a, flush=True)


# ============================== E1: 1,000-pair benchmark, directed vs two-sided ==============================
if RUN_E1:
    t0 = time.time()
    ALL = [MAN["pairs"][i] for i in range(len(MAN["pairs"]))]
    ALL = ALL[:4] if SMOKE else ALL
    CH = 2 if SMOKE else 50
    RULES1 = ["field_linear", "gaussian", "soft_ot"]
    for c0 in range(0, len(ALL), CH):
        path = f"{T1}/e1_chunk_{c0:04d}.npz"
        if os.path.exists(path): continue
        feats = {}
        with torch.no_grad():
            for p in ALL[c0:c0 + CH]:
                k = int(p["k"]); dAB, dBA = pair_d(p), pair_d(p, rev=True)
                imgs = {}
                for r in RULES1:
                    if r == "field_linear":
                        for t in (0.25, 0.5, 0.75): imgs[f"{r}@{t}"] = cnt.to_pil(cnt.field_linear(dAB, t))
                        imgs[f"{r}_2s@0.75"] = cnt.to_pil(cnt.field_linear(dBA, 0.25))
                    else:
                        fA = matching.field(cnt, dAB, r, seed=k, **MATCH_KW)
                        for t in (0.25, 0.5, 0.75): imgs[f"{r}@{t}"] = cnt.to_pil(dec(dAB, fA, t))
                        del fA
                        fB = matching.field(cnt, dBA, r, seed=k, **MATCH_KW)
                        imgs[f"{r}_2s@0.75"] = cnt.to_pil(dec(dBA, fB, 0.25)); del fB
                for key, im in imgs.items(): feats.setdefault(key, []).append(im)
        np.savez(path, ks=np.array([int(p["k"]) for p in ALL[c0:c0 + CH]]), **{key: inc128(v) for key, v in feats.items()})
        say(f"E1 chunk {c0 // CH + 1}/{(len(ALL) + CH - 1) // CH} saved ({(time.time() - t0) / 60:.1f} min)")
    Z = [np.load(f"{T1}/e1_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]
    F1 = {key: np.concatenate([z[key] for z in Z]) for key in Z[0].files if key != "ks"}
    rows = [dict(method=key.split("@")[0], t=float(key.split("@")[1]), n=len(v), KIDx1e3=round(kid(v), 2)) for key, v in F1.items()]
    S1 = pd.DataFrame(rows).sort_values(["t", "method"]); S1.to_csv(f"{T1}/e1_kid.csv", index=False)
    D1 = []
    for t in (0.25, 0.5, 0.75):
        for r in ("gaussian", "soft_ot"):
            D1.append(dict(method=r, base="field_linear", t=t, **dkid(F1[f"{r}@{t}"], F1[f"field_linear@{t}"])))
        D1.append(dict(method="soft_ot", base="gaussian", t=t, **dkid(F1[f"soft_ot@{t}"], F1[f"gaussian@{t}"])))
    for r in ("gaussian", "soft_ot"):
        D1.append(dict(method=f"{r}_2s", base="field_linear_2s", t=0.75, **dkid(F1[f"{r}_2s@0.75"], F1["field_linear_2s@0.75"])))
        D1.append(dict(method=f"{r}_2s", base=r, t=0.75, **dkid(F1[f"{r}_2s@0.75"], F1[f"{r}@0.75"])))
    D1 = pd.DataFrame(D1); D1.to_csv(f"{T1}/e1_delta_kid.csv", index=False)
    say(f"\nE1 ({len(ALL)} pairs) KID x1000:\n" + S1.to_string(index=False) + "\n\nE1 Delta-KID x1000:\n" + D1.to_string(index=False))
    say(f"E1 done ({(time.time() - t0) / 60:.1f} min)")


# ============================== E2: SD VAE latent interpolation ==============================
if RUN_E2:
    t0 = time.time()
    from diffusers import AutoencoderKL
    vae = AutoencoderKL.from_pretrained(f"{SD_DIR}/vae").to(DEV).eval()
    SF = vae.config.scaling_factor

    @torch.no_grad()
    def vae_tokens(pil):                       # 256 px -> (1, 4, 32, 32) latent -> (1024, 4) tokens, plus the grid shape
        z = vae.encode((to01(pil, 256) * 2 - 1).to(DEV)).latent_dist.mean * SF
        return z[0].flatten(1).t().contiguous(), z.shape
    @torch.no_grad()
    def vae_decode(tok, shape):
        z = tok.t().reshape(shape) / SF
        x = (vae.decode(z).sample.clamp(-1, 1) + 1) * 127.5
        return x[0].permute(1, 2, 0).round().byte().cpu().numpy()
    RULES2 = ["field_linear", "target_mean", "gaussian", "soft_ot", "soft_ot_sharp", "exact_ot"]
    P2 = PAIRS[:2] if SMOKE else PAIRS
    for i, p in enumerate(P2):
        k = int(p["k"])
        if all(have(f"sdvae_{r}", k) for r in RULES2) and all(have(f"sdvae_twosided_{r}", k) for r in ("field_linear", "soft_ot_sharp")) and not SMOKE: continue
        Xa, sh = vae_tokens(endpoint(p["cA"], p["fA"])); Xb, _ = vae_tokens(endpoint(p["cB"], p["fB"]))
        for r in RULES2:
            Ua = token_targets(Xa.float(), Xb.float(), r, k)
            frA = [vae_decode((1 - t) * Xa + t * Ua, sh) for t in T_GRID]
            if not SMOKE: save_frames(f"sdvae_{r}", k, frA)
            if r in ("field_linear", "soft_ot_sharp"):   # two-sided: B's layout (B -> A transport) after the midpoint
                Ub = token_targets(Xb.float(), Xa.float(), r, k)
                fr2 = frA[:5] + [vae_decode(t * Xb + (1 - t) * Ub, sh) for t in T_GRID[5:]]
                if not SMOKE: save_frames(f"sdvae_twosided_{r}", k, fr2)
        if SMOKE: say(f"E2 smoke pair {k}: tokens {tuple(Xa.shape)}, frame {frA[4].shape}, eff {TOKEN_EFF}")
        elif (i + 1) % 30 == 0: say(f"E2 {i + 1}/{len(P2)} ({(time.time() - t0) / 60:.1f} min)")
    if not SMOKE:
        M2 = [f"sdvae_{r}" for r in RULES2] + ["sdvae_twosided_field_linear", "sdvae_twosided_soft_ot_sharp"]
        F2 = {}
        for m in M2:
            ks = ks_on_disk(m); fr = np.stack([load_frames(m, k) for k in ks])
            F2[m] = np.stack([inc128([Image.fromarray(x) for x in fr[:, ti]]) for ti in range(len(T_GRID))])
        S2 = pd.DataFrame([dict(method=m, t=t, KIDx1e3=round(kid(F2[m][ti]), 2)) for m in M2 for ti, t in enumerate(T_GRID)])
        S2.to_csv(f"{T1}/e2_kid_by_t.csv", index=False)
        D2 = [dict(method=m, base="sdvae_field_linear", t=t, **dkid(F2[m][ti], F2["sdvae_field_linear"][ti]))
              for m in M2 if m != "sdvae_field_linear" and "twosided" not in m for ti, t in enumerate(T_GRID) if t in (0.25, 0.5, 0.75)]
        D2 += [dict(method="sdvae_twosided_soft_ot_sharp", base="sdvae_twosided_field_linear", t=t,
                    **dkid(F2["sdvae_twosided_soft_ot_sharp"][ti], F2["sdvae_twosided_field_linear"][ti])) for ti, t in enumerate(T_GRID) if t in (0.25, 0.5, 0.75)]
        D2 = pd.DataFrame(D2); D2.to_csv(f"{T1}/e2_delta_kid.csv", index=False)
        say("\nE2 KID x1000 by t:\n" + S2.pivot(index="method", columns="t", values="KIDx1e3").to_string()
            + "\n\nE2 Delta-KID x1000:\n" + D2.to_string(index=False))
    del vae; torch.cuda.empty_cache()
    say(f"E2 done ({(time.time() - t0) / 60:.1f} min)")


# ============================== E3: spatial transitions (t varies across the image) ==============================
if RUN_E3:
    t0 = time.time()
    def ramp(W, dev):                           # smoothstep from 0 (left 20%) to 1 (right 20%) across columns
        x = torch.linspace(0, 1, W, device=dev); s = ((x - 0.2) / 0.6).clamp(0, 1); return s * s * (3 - 2 * s)
    P3 = PAIRS[:2] if SMOKE else PAIRS
    M3 = ["rgb_alpha", "positional", "gaussian", "soft_ot", "soft_ot_sharprel"]
    rows3, feats3 = [], {m: [] for m in M3}; mids3 = {m: [] for m in M3}
    pano_dir = f"{T1}/e3_panoramas"; os.makedirs(pano_dir, exist_ok=True)
    with torch.no_grad():
        for i, p in enumerate(P3):
            k = int(p["k"]); d = pair_d(p); L, C, H, W, sf, tf = cnt.grids(d)
            assert sf.shape[0] == H * W, f"field has {sf.shape[0]} cells, expected H*W = {H * W}"
            tcol = ramp(W, sf.device); tcell = tcol[None, :].expand(H, W).reshape(-1, 1)      # row-major (h, w) cells
            U = {"positional": tf, "gaussian": matching.field(cnt, d, "gaussian", seed=k, **MATCH_KW)["U"],
                 "soft_ot": matching.field(cnt, d, "soft_ot", seed=k, **MATCH_KW)["U"]}
            i_s = matching._sub(sf.shape[0], k, "s", 4096, sf.device); i_t = matching._sub(tf.shape[0], k, "t", 4096, sf.device)
            eps = 0.005 * float(torch.cdist(sf[i_s], tf[i_t]).pow(2).median())
            tt, _ = _soft_bary(sf[i_s], tf[i_t], eps_abs=eps); U["soft_ot_sharprel"] = tt[_nearest(sf, sf[i_s])]
            out = {}
            for m, Um in U.items(): out[m] = cnt.to_pil(cnt.decode_field(d, (1 - tcell) * sf + tcell * Um, L, H, W, C))
            a = np.asarray(endpoint(p["cA"], p["fA"]).resize((256, 256)), np.float32); b = np.asarray(endpoint(p["cB"], p["fB"]).resize((256, 256)), np.float32)
            tr = ramp(256, "cpu").numpy()[None, :, None]
            out["rgb_alpha"] = Image.fromarray(np.clip((1 - tr) * a + tr * b, 0, 255).astype(np.uint8))
            for m in M3:
                feats3[m].append(out[m]); mids3[m].append(out[m].resize((256, 256)).crop((64, 0, 192, 256)))   # central band
            if i < 12 or SMOKE:                 # panoramas: rows = methods; columns = A | transition | B
                s = 256; cv = Image.new("RGB", (3 * s, len(M3) * s), (255, 255, 255))
                for r_, m in enumerate(M3):
                    cv.paste(Image.fromarray(a.astype(np.uint8)), (0, r_ * s)); cv.paste(out[m].resize((s, s)), (s, r_ * s))
                    cv.paste(Image.fromarray(b.astype(np.uint8)), (2 * s, r_ * s))
                cv.save(f"{pano_dir}/e3_{k:04d}.png")
            if (i + 1) % 30 == 0: say(f"E3 {i + 1}/{len(P3)} ({(time.time() - t0) / 60:.1f} min)")
    if not SMOKE:
        Fw = {m: inc128(v) for m, v in feats3.items()}; Fm = {m: inc128(v) for m, v in mids3.items()}
        S3 = pd.DataFrame([dict(method=m, KID_tile=round(kid(Fw[m]), 2), KID_band=round(kid(Fm[m]), 2)) for m in M3])
        D3 = pd.DataFrame([dict(method=m, base="positional", region=reg, **dkid(FF[m], FF["positional"]))
                           for reg, FF in (("tile", Fw), ("band", Fm)) for m in M3 if m != "positional"])
        S3.to_csv(f"{T1}/e3_kid.csv", index=False); D3.to_csv(f"{T1}/e3_delta_kid.csv", index=False)
        say("\nE3 spatial transitions KID x1000:\n" + S3.to_string(index=False) + "\n\nE3 Delta-KID x1000 vs positional:\n" + D3.to_string(index=False))
    say(f"E3 done ({(time.time() - t0) / 60:.1f} min) | panoramas in {pano_dir}")
