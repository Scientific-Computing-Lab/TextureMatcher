# Tier-1b follow-up. exec() in the same kernel right after tier1_experiments.py (it reuses its helpers).
#   E1B  t = .875 on the 1,000 pairs (directed and two-sided), and two-sided soft OT vs two-sided Gaussian at .75/.875
#   E2B  SD-VAE latents: DINOv2 progress, balance, end placement and jump share, plus excess KID (from saved frames)
#   E3B  spatial transitions re-run with every output saved, and a left-to-right profile (place per column band)
import os, time, numpy as np, pandas as pd, torch
from PIL import Image
RUN_E1B, RUN_E2B, RUN_E3B = (globals().get(n, True) for n in ("RUN_E1B", "RUN_E2B", "RUN_E3B"))
T1 = f"{OUT}/tier1"
def prog_summary(w):
    steps = np.diff(w, axis=1); span = w[:, -1] - w[:, 0]; mv = span > 0.05
    return dict(place_t0=w[:, 0].mean(), place_mid=w[:, w.shape[1] // 2].mean(), place_t1=w[:, -1].mean(), span=span.mean(),
                balance_mid=np.abs(w[:, w.shape[1] // 2] - 0.5).mean(), monotone=(steps >= -0.01).mean(),
                max_jump_share=np.median(steps[mv].max(1) / span[mv]) if mv.any() else np.nan)

# ============================== E1B ==============================
if RUN_E1B:
    t0 = time.time()
    ALL = [MAN["pairs"][i] for i in range(len(MAN["pairs"]))]; CH = 50
    for c0 in range(0, len(ALL), CH):
        path = f"{T1}/e1b_chunk_{c0:04d}.npz"
        if os.path.exists(path): continue
        feats = {}
        with torch.no_grad():
            for p in ALL[c0:c0 + CH]:
                k = int(p["k"]); dAB, dBA = pair_d(p), pair_d(p, rev=True); imgs = {}
                imgs["field_linear@0.875"] = cnt.to_pil(cnt.field_linear(dAB, 0.875))
                imgs["field_linear_2s@0.875"] = cnt.to_pil(cnt.field_linear(dBA, 0.125))
                for r in ("gaussian", "soft_ot"):
                    fA = matching.field(cnt, dAB, r, seed=k, **MATCH_KW); imgs[f"{r}@0.875"] = cnt.to_pil(dec(dAB, fA, 0.875)); del fA
                    fB = matching.field(cnt, dBA, r, seed=k, **MATCH_KW); imgs[f"{r}_2s@0.875"] = cnt.to_pil(dec(dBA, fB, 0.125)); del fB
                for key, im in imgs.items(): feats.setdefault(key, []).append(im)
        np.savez(path, ks=np.array([int(p["k"]) for p in ALL[c0:c0 + CH]]), **{key: inc128(v) for key, v in feats.items()})
        say(f"E1B chunk {c0 // CH + 1}/{(len(ALL) + CH - 1) // CH} saved ({(time.time() - t0) / 60:.1f} min)")
    F = {}
    for pre in ("e1", "e1b"):
        Z = [np.load(f"{T1}/{pre}_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]
        assert all((za["ks"] == zb["ks"]).all() for za, zb in zip(Z, [np.load(f"{T1}/e1_chunk_{c0:04d}.npz") for c0 in range(0, len(ALL), CH)]))
        F.update({key: np.concatenate([z[key] for z in Z]) for key in Z[0].files if key != "ks"})
    S = pd.DataFrame([dict(method=key.split("@")[0], t=float(key.split("@")[1]), n=len(v), KIDx1e3=round(kid(v), 2)) for key, v in F.items()])
    S.sort_values(["t", "method"]).to_csv(f"{T1}/e1_all_kid.csv", index=False)
    R = []
    for t in (0.75, 0.875):
        for a_, b_ in (("soft_ot_2s", "field_linear_2s"), ("gaussian_2s", "field_linear_2s"), ("soft_ot_2s", "gaussian_2s"),
                       ("soft_ot", "field_linear"), ("gaussian", "field_linear"), ("soft_ot", "gaussian")):
            R.append(dict(method=a_, base=b_, t=t, **dkid(F[f"{a_}@{t}"], F[f"{b_}@{t}"])))
    R = pd.DataFrame(R); R.to_csv(f"{T1}/e1_all_delta_kid.csv", index=False)
    say("\nE1 + E1B KID x1000:\n" + S.pivot(index="method", columns="t", values="KIDx1e3").to_string()
        + "\n\nDelta-KID x1000 (1,000 pairs):\n" + R.to_string(index=False))
    say(f"E1B done ({(time.time() - t0) / 60:.1f} min)")

# ============================== E2B ==============================
if RUN_E2B:
    t0 = time.time()
    M2 = [m for m in methods_on_disk() if m.startswith("sdvae_")]
    z = np.load(f"{OUT}/feats/endpoints.npz"); EA, EB = z["a"], z["b"]; EI = {int(k): i for i, k in enumerate(z["ks"])}
    rows, byt = [], []
    for m in M2:
        ks = ks_on_disk(m); W = np.zeros((len(ks), len(T_GRID)))
        for j0 in range(0, len(ks), 30):
            fr = np.stack([load_frames(m, k) for k in ks[j0:j0 + 30]]); ia = np.array([EI[k] for k in ks[j0:j0 + 30]])
            for ti in range(len(T_GRID)):
                dn = ext.dino_feats([Image.fromarray(x) for x in fr[:, ti]])
                dA = np.linalg.norm(dn - EA[ia], axis=1); dB = np.linalg.norm(dn - EB[ia], axis=1); W[j0:j0 + len(fr), ti] = dA / (dA + dB + 1e-12)
        for i_, k in enumerate(ks):
            for ti, t in enumerate(T_GRID): byt.append(dict(method=m, k=k, t=t, place=W[i_, ti]))
        rows.append(dict(method=m, n=len(ks), **{a: round(float(b), 3) for a, b in prog_summary(W).items()}))
    PS = pd.DataFrame(rows); PS.to_csv(f"{T1}/e2_progress_summary.csv", index=False); pd.DataFrame(byt).to_csv(f"{T1}/e2_progress_by_t.csv", index=False)
    S2 = pd.read_csv(f"{T1}/e2_kid_by_t.csv"); S2["excess"] = S2.KIDx1e3 - S2.groupby("method").KIDx1e3.transform("first")
    S2.to_csv(f"{T1}/e2_kid_by_t_excess.csv", index=False)
    say("\nE2B progress (DINOv2 place; balance_mid lower = more in between; place_t1 = 1 means it reaches B):\n" + PS.to_string(index=False)
        + "\n\nE2 excess KID x1000 over own t = 0:\n" + S2.pivot(index="method", columns="t", values="excess").round(2).to_string())
    say(f"E2B done ({(time.time() - t0) / 60:.1f} min)")

# ============================== E3B ==============================
if RUN_E3B:
    t0 = time.time()
    def ramp(W, dev):                           # smoothstep from 0 (left 20%) to 1 (right 20%) across columns
        x = torch.linspace(0, 1, W, device=dev); s = ((x - 0.2) / 0.6).clamp(0, 1); return s * s * (3 - 2 * s)
    P3 = PAIRS[:2] if SMOKE else PAIRS
    e3o = f"{T1}/e3_out"
    for m_ in M3: os.makedirs(f"{e3o}/{m_}", exist_ok=True)
    M3 = ["rgb_alpha", "positional", "gaussian", "soft_ot", "soft_ot_sharprel"]
    rows3, feats3 = [], {m: [] for m in M3}; mids3 = {m: [] for m in M3}
    pano_dir = f"{T1}/e3_panoramas_b"; os.makedirs(pano_dir, exist_ok=True)
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
                out[m].resize((256, 256)).save(f"{e3o}/{m}/{k:04d}.png")
                feats3[m].append(out[m]); mids3[m].append(out[m].resize((256, 256)).crop((64, 0, 192, 256)))   # central band
            if i < 12 or SMOKE:                 # panoramas: rows = methods; columns = A | transition | B
                s = 256; cv = Image.new("RGB", (3 * s, len(M3) * s), (255, 255, 255))
                for r_, m in enumerate(M3):
                    cv.paste(Image.fromarray(a.astype(np.uint8)), (0, r_ * s)); cv.paste(out[m].resize((s, s)), (s, r_ * s))
                    cv.paste(Image.fromarray(b.astype(np.uint8)), (2 * s, r_ * s))
                cv.save(f"{pano_dir}/e3_{k:04d}.png")
            if (i + 1) % 30 == 0: say(f"E3 {i + 1}/{len(P3)} ({(time.time() - t0) / 60:.1f} min)")
    if not SMOKE:
        # left-to-right profile: DINOv2 place of each 64 px column band against the same band of A and of B
        BANDS = [(x, x + 64) for x in range(0, 193, 32)]
        PR = []
        for m in M3:
            for p in P3:
                k = int(p["k"]); o = Image.open(f"{e3o}/{m}/{k:04d}.png").convert("RGB")
                a = endpoint(p["cA"], p["fA"]).convert("RGB").resize((256, 256)); b = endpoint(p["cB"], p["fB"]).convert("RGB").resize((256, 256))
                crops = lambda im: [im.crop((x0, 0, x1, 256)) for x0, x1 in BANDS]
                fo, fa, fb = ext.dino_feats(crops(o)), ext.dino_feats(crops(a)), ext.dino_feats(crops(b))
                dA = np.linalg.norm(fo - fa, axis=1); dB = np.linalg.norm(fo - fb, axis=1)
                for (x0, _), pl in zip(BANDS, dA / (dA + dB + 1e-12)): PR.append(dict(method=m, k=k, band_x=x0, place=pl))
        PR = pd.DataFrame(PR); PR.to_csv(f"{T1}/e3_profile_by_pair.csv", index=False)
        prof = PR.groupby(["method", "band_x"]).place.mean().unstack().round(3); prof.to_csv(f"{T1}/e3_profile.csv")
        say("\nE3B left-to-right profile (mean DINOv2 place per 64 px band; 0 = like A, 1 = like B; ideal rises from 0 to 1):\n" + prof.to_string())
    say(f"E3B done ({(time.time() - t0) / 60:.1f} min)")
