# Teaser renders for NEW pairs (not yet run; review before use).
#
# How to run (same pattern as tier1_experiments.py):
#   1. nvidia-smi (must be an A100), mount Drive.
#   2. In notebook/cvpr_experiments.ipynb: run cell 1 (config), cell 3 (install), then restart the runtime.
#   3. Run cell 1 (config) again with every RUN_* flag set to False, then cell 5 (setup).
#   4. SMOKE = True;  exec(open('/content/drive/MyDrive/masters_texture/colab_render_more_pairs.py').read())
#      This renders 2 pairs into renders_teaser_smoke/ and prints the time per pair and per model.
#   5. SMOKE = False; exec(open(...).read())
#      This renders all of NEW_KS into renders_teaser/. It is resumable: finished (method, pair) files are skipped.
#
# Output: OUT/renders_teaser/<method>/<kkkk>.npz with keys frames (5, 256, 256, 3) uint8 and t = [0, .25, .5, .75, 1].
# This is the same format as renders/, but with 5 frames instead of 9.
# Methods: cnt_field_linear, cnt_soft_ot, rae_field_linear, rae_soft_ot_sharp, sdvae_field_linear, sdvae_soft_ot.
#
# Reused from the notebook's setup cell (cell 5), unchanged:
#   PAIRS, BYK, EVAL_KS, endpoint, get_cnt, matching.field, token_targets (with EPS_REL / EPS_REL_SHARP),
#   enc_dino, rae_decode, to01, TOKEN_EFF.
# Copied from tier1_experiments.py E2: vae_tokens and vae_decode (SD 2.1-base VAE from SD_DIR/vae).
# Copied from notebook cell 13 (CNT) and cell 17 (RAE): the per-rule render loops.
import os, glob, time, json, numpy as np, torch
from PIL import Image

SMOKE = globals().get("SMOKE", True)
T_TEASER = globals().get("T_TEASER_OVERRIDE", [0.0, 0.25, 0.5, 0.75, 1.0])
TDIR = globals().get("TDIR_OVERRIDE") or (f"{OUT}/renders_teaser_smoke" if SMOKE else f"{OUT}/renders_teaser")
N_NEW = globals().get("N_NEW", 120)

# ---- which pairs to render ----
# Default rule: the first N_NEW manifest ids, in ascending order, that are not among the 120 already rendered and
# have no "freckled" endpoint (face close-ups). To render a hand-made list instead, set NEW_KS = [...] before exec.
# The LoRA section drew its training pairs from the same manifest (disjoint from the 120). That does not matter for
# rendering frozen models, so those pairs are not excluded.
if "NEW_KS" not in globals() or not NEW_KS:
    done120 = set(int(k) for k in EVAL_KS)
    NEW_KS = [k for k in sorted(BYK) if k not in done120
              and "freckled" not in (BYK[k]["cA"], BYK[k]["cB"])][:N_NEW]
KS = NEW_KS[:2] if SMOKE else NEW_KS
print(f"{len(KS)} pairs -> {TDIR} (first ids: {KS[:6]})")


def tpath(m, k): return f"{TDIR}/{m}/{int(k):04d}.npz"
def thave(m, k): return os.path.exists(tpath(m, k))
def tsave(m, k, frames):
    arr = np.stack([np.asarray(f.convert("RGB").resize((256, 256), Image.BICUBIC)) if isinstance(f, Image.Image)
                    else np.asarray(f) for f in frames]).astype(np.uint8)
    os.makedirs(f"{TDIR}/{m}", exist_ok=True)
    tmp = tpath(m, k)[:-4] + "_tmp.npz"
    np.savez_compressed(tmp, frames=arr, t=np.array(T_TEASER))
    os.replace(tmp, tpath(m, k))


# ---- RAE checkpoint fix (transformers 5.x renamed the DINOv2 attention modules) ----
# Old -> new: '.attention.attention.{query,key,value}.' -> '.attention.{q,k,v}_proj.', '.attention.output.dense.' ->
# '.attention.o_proj.'. Expected leftover: only 'decoder.decoder_pos_embed' unexpected (identical to the model buffer).
# ASSUMPTION: AutoencoderRAE.from_config builds the full module tree without fetching weights, and the repo's weights
# are *.safetensors files. If from_config itself downloads DINOv2 weights, that is fine, because they are overwritten.
def load_rae_fixed():
    from diffusers import AutoencoderRAE
    from huggingface_hub import snapshot_download
    from safetensors.torch import load_file
    d = snapshot_download(RAE_REPO, allow_patterns=["*.json", "*.safetensors"])
    model = AutoencoderRAE.from_config(AutoencoderRAE.load_config(d))
    sd = {}
    for f in sorted(glob.glob(f"{d}/**/*.safetensors", recursive=True)): sd.update(load_file(f))
    ren = {".attention.attention.query.": ".attention.q_proj.", ".attention.attention.key.": ".attention.k_proj.",
           ".attention.attention.value.": ".attention.v_proj.", ".attention.output.dense.": ".attention.o_proj."}
    fixed = {}
    for key, v in sd.items():
        for a, b in ren.items(): key = key.replace(a, b)
        fixed[key] = v
    missing, unexpected = model.load_state_dict(fixed, strict=False)
    assert not missing, f"RAE: missing keys after rename: {missing[:8]}"
    assert set(unexpected) <= {"decoder.decoder_pos_embed"}, f"RAE: unexpected keys: {unexpected[:8]}"
    return model.to(DEV).eval()

_M["rae"] = load_rae_fixed()            # enc_dino / rae_decode in setup use get_rae() -> this model
print("RAE loaded with key rename")

# ---- SD 2.1-base VAE (as in tier1 E2) ----
from diffusers import AutoencoderKL
vae = AutoencoderKL.from_pretrained(f"{SD_DIR}/vae").to(DEV).eval(); SF = vae.config.scaling_factor
@torch.no_grad()
def vae_tokens(pil):
    z = vae.encode((to01(pil, 256) * 2 - 1).to(DEV)).latent_dist.mean * SF
    return z[0].flatten(1).t().contiguous(), z.shape
@torch.no_grad()
def vae_decode(tok, shape):
    z = tok.t().reshape(shape) / SF
    x = (vae.decode(z).sample.clamp(-1, 1) + 1) * 127.5
    return x[0].permute(1, 2, 0).round().byte().cpu().numpy()

# ---- CNT (cell 13). Clear Hydra first in case SAM2 initialised it in this session ----
try:
    from hydra.core.global_hydra import GlobalHydra; GlobalHydra.instance().clear()
except Exception:
    pass
cnt = get_cnt()
if "lora_mods" in globals(): set_lora(False)

TIMES = {"cnt": [], "rae": [], "sdvae": []}
t_all = time.time()
for i, k in enumerate(KS):
    p = BYK[int(k)]
    A, B = endpoint(p["cA"], p["fA"]), endpoint(p["cB"], p["fB"])
    # CNT: positional = field_linear, OT = soft_ot (the paper's default eps, matching.field)
    t0 = time.time()
    if not (thave("cnt_field_linear", k) and thave("cnt_soft_ot", k)) or SMOKE:
        with torch.no_grad():
            d = cnt.build_pair(cnt.load_image(A), cnt.load_image(B))
            tsave("cnt_field_linear", k, [cnt.to_pil(cnt.field_linear(d, t)) for t in T_TEASER])
            fd = matching.field(cnt, d, "soft_ot", seed=int(k), **MATCH_KW)
            tsave("cnt_soft_ot", k, [cnt.to_pil(cnt.decode_field(d, matching.zt(fd, t), fd["L"], fd["H"], fd["W"], fd["C"]))
                                     for t in T_TEASER])
            del fd, d
    TIMES["cnt"].append(time.time() - t0)
    # DINO-RAE: positional = field_linear, OT = soft_ot_sharp (EPS_REL_SHARP); path on A's token layout
    t0 = time.time()
    if not (thave("rae_field_linear", k) and thave("rae_soft_ot_sharp", k)) or SMOKE:
        Xa, Xb = enc_dino(A).float(), enc_dino(B).float()
        for rule in ("field_linear", "soft_ot_sharp"):
            U = token_targets(Xa, Xb, rule, int(k))
            imgs = rae_decode(torch.stack([(1 - t) * Xa + t * U for t in T_TEASER]).to(DEV))
            tsave(f"rae_{rule}", k, [(im.permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8) for im in imgs])
    TIMES["rae"].append(time.time() - t0)
    # SD-VAE latent: positional = field_linear, OT = soft_ot (EPS_REL), one-sided (A's layout)
    t0 = time.time()
    if not (thave("sdvae_field_linear", k) and thave("sdvae_soft_ot", k)) or SMOKE:
        Xa, sh = vae_tokens(A); Xb, _ = vae_tokens(B)
        for rule in ("field_linear", "soft_ot"):
            U = token_targets(Xa.float(), Xb.float(), rule, int(k))
            tsave(f"sdvae_{rule}", k, [vae_decode((1 - t) * Xa + t * U, sh) for t in T_TEASER])
    TIMES["sdvae"].append(time.time() - t0)
    if SMOKE or (i + 1) % 10 == 0:
        print(f"pair {k} ({i + 1}/{len(KS)}) | s/pair: " + ", ".join(f"{m} {np.mean(v):.1f}" for m, v in TIMES.items())
              + f" | total {(time.time() - t_all) / 60:.1f} min")

per = sum(np.mean(v) for v in TIMES.values())
print(f"done: {len(KS)} pairs in {(time.time() - t_all) / 60:.1f} min; ~{per:.1f} s/pair "
      f"-> 100 new pairs ~ {100 * per / 60:.0f} min")
json.dump(dict(ks=[int(k) for k in KS], t=T_TEASER, smoke=SMOKE), open(f"{TDIR}/manifest_teaser.json", "w"))
del vae; torch.cuda.empty_cache()
