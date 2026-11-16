# Two-sided renders (A's layout up to t=.5, then B's layout with the B->A pairing; Eq. 2 of the paper)
# for hand-picked pairs, CNT and DINO-RAE. Run after colab_render_more_pairs.py has been exec'd once in
# this session (it defines cnt, the RAE fix, tsave/T_TEASER helpers). Set TS_KS = [...] before exec.
import numpy as np, torch
T9 = [i / 8 for i in range(9)]
TSDIR = f"{OUT}/renders_teaser9_twosided"
def ts_save(m, k, frames):
    arr = np.stack([np.asarray(f.convert("RGB").resize((256, 256))) if hasattr(f, "convert") else np.asarray(f) for f in frames]).astype(np.uint8)
    os.makedirs(f"{TSDIR}/{m}", exist_ok=True); np.savez_compressed(f"{TSDIR}/{m}/{int(k):04d}.npz", frames=arr, t=np.array(T9))
for k in TS_KS:
    p = BYK[int(k)]; A, B = endpoint(p["cA"], p["fA"]), endpoint(p["cB"], p["fB"])
    with torch.no_grad():
        d = cnt.build_pair(cnt.load_image(A), cnt.load_image(B)); dr = cnt.build_pair(cnt.load_image(B), cnt.load_image(A))
        ts_save("cnt_twosided_field_linear", k, [cnt.to_pil(cnt.field_linear(d, t) if t <= .5 else cnt.field_linear(dr, 1 - t)) for t in T9])
        f = matching.field(cnt, d, "soft_ot", seed=int(k), **MATCH_KW); fr = matching.field(cnt, dr, "soft_ot", seed=int(k), **MATCH_KW)
        ts_save("cnt_twosided_soft_ot", k, [cnt.to_pil(cnt.decode_field(d, matching.zt(f, t), f["L"], f["H"], f["W"], f["C"]) if t <= .5
                                            else cnt.decode_field(dr, matching.zt(fr, 1 - t), fr["L"], fr["H"], fr["W"], fr["C"])) for t in T9])
        Xa, Xb = enc_dino(A).float(), enc_dino(B).float()
        for rule in ("field_linear", "soft_ot_sharp"):
            Ua = token_targets(Xa, Xb, rule, int(k)); Ub = token_targets(Xb, Xa, rule, int(k))
            Z = torch.stack([(1 - t) * Xa + t * Ua if t <= .5 else t * Xb + (1 - t) * Ub for t in T9]).to(DEV)
            ts_save(f"rae_twosided_{rule}", k, [(im.permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8) for im in rae_decode(Z)])
    print("two-sided done", k, flush=True)
