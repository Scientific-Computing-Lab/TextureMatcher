"""Wrapper around Compositional Neural Textures (CNT): encode, splat,
build the dense per-cell appearance field, and decode.

This module is a direct port of the canonical September setup cell shared
by mechanism_study.ipynb, CNT_correspondence_experiments.ipynb,
CNT_joint_basis_and_ceiling.ipynb, finishing_experiments.ipynb,
jackknife_dKID.ipynb and presubmission_additions.ipynb (verified identical
across all of them during package construction). Install CNT itself first
with install/cnt.sh.

Imports of torch and of CNT's own `src.inference.core` are guarded: this
module is importable (e.g. for reading CNT_COMMIT / IMG_SIZE constants, or
from a CPU-only environment that only needs texton_matching.scoring) even
when neither is installed. Instantiating CNTModel requires both.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import torch
    import torch.nn.functional as F
    _HAVE_TORCH = True
except ImportError:  # pragma: no cover
    _HAVE_TORCH = False

from PIL import Image
import numpy as np

# Canonical protocol constants (identical across every September-generation
# notebook; see paper/appendix/supplement.tex "Transport configuration").
CNT_REPO = "https://github.com/phtu-cs/compositional-neural-textures.git"
CNT_COMMIT = "07269302610c92ce38e2dbbe31c492fd09e1c73e"
IMG_SIZE = 256
EPS = 0.05          # default entropic regularisation, raw squared-feature units
ITERS = 100         # canonical (float32, multiplicative) Sinkhorn iterations
NSUB = 4096         # sampled vectors per field
N_EXACT = 1024      # samples used for the exact (Hungarian) assignment


class CNTModel:
    """Loads a checkpoint and exposes encode/splat/field/decode as plain
    tensor operations, matching the notebooks' `get_gen_inputs`,
    `build_style_maps`, `decode_with_style_maps`, `decode_interp`,
    `_grids`, `sm_from_field` and `_dec` helpers exactly.
    """

    def __init__(self, cnt_root: str | Path, ckpt_path: str | Path | None = None, device: str = "cuda"):
        if not _HAVE_TORCH:
            raise ImportError("torch is required for CNTModel; run install/scoring.sh first")
        self.cnt_root = Path(cnt_root)
        if str(self.cnt_root) not in sys.path:
            sys.path.insert(0, str(self.cnt_root))
        try:
            from src.inference.core import TexAutoEncoderInference, load_image
        except ImportError as e:
            raise ImportError(
                f"could not import CNT from {self.cnt_root}; run install/cnt.sh first"
            ) from e
        self._load_image = load_image

        # Same default path install/cnt.sh downloads the checkpoint to
        # (<cnt_root>/ckpts/finetuned-model256.ckpt) -- these two must
        # agree, or you get a confusing failure far from the real cause.
        ckpt_path = Path(ckpt_path) if ckpt_path is not None else self.cnt_root / "ckpts" / "finetuned-model256.ckpt"
        if not ckpt_path.exists():
            raise FileNotFoundError(
                f"no CNT checkpoint at {ckpt_path}. Run install/cnt.sh first (it downloads "
                f"finetuned-model256.ckpt to exactly this path), or pass ckpt_path= explicitly "
                f"if you've placed it somewhere else."
            )
        min_bytes = 1_000_000_000  # ~1.27GB real file; a failed/rate-limited download can leave a tiny HTML error page
        got_bytes = ckpt_path.stat().st_size
        if got_bytes < min_bytes:
            raise ValueError(
                f"{ckpt_path} is only {got_bytes} bytes (expected >= {min_bytes}); this looks like a "
                f"failed or partial download (e.g. a Google Drive rate-limit error page), not the real "
                f"checkpoint. Re-run install/cnt.sh, or delete this file and download it again by hand."
            )

        self.device = device
        # CNT resolves some of its own paths (its Mask2Former config files
        # in particular) relative to the current working directory, not to
        # its own package location -- construct the model from inside the
        # CNT repo root, then always restore the caller's cwd, success or not.
        prev_cwd = Path.cwd()
        try:
            os.chdir(self.cnt_root)
            self.model = TexAutoEncoderInference(ckpt_path=ckpt_path, device=device)
        finally:
            os.chdir(prev_cwd)
        self.FMS = [round(IMG_SIZE * r) for r in self.model.generator.feature_map_size_ratios]

        commit = self._git_head()
        if commit and commit != CNT_COMMIT:
            print(
                f"[texton_matching.cnt] WARNING: {self.cnt_root} is at commit {commit[:10]}, "
                f"expected {CNT_COMMIT[:10]} (the commit every canonical notebook pinned)."
            )

    def _git_head(self) -> str | None:
        import subprocess
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.cnt_root, capture_output=True, text=True, check=True
            )
            return out.stdout.strip()
        except Exception:
            return None

    # -- loading --------------------------------------------------------
    def load_image(self, x, size: int = IMG_SIZE):
        """Accepts a path or a PIL.Image; always routed through CNT's own
        load_image so preprocessing (range, resize) matches the notebooks."""
        if isinstance(x, (str, Path)):
            return self._load_image(Path(x), size).to(self.device)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            x.convert("RGB").save(f.name)
            return self._load_image(Path(f.name), size).to(self.device)

    @staticmethod
    def to_pil(decoded: "torch.Tensor") -> Image.Image:
        a = ((decoded.squeeze(0).detach().cpu().clamp(-1, 1) + 1) / 2).permute(1, 2, 0).numpy()
        return Image.fromarray((a * 255).astype(np.uint8))

    # -- encode / splat ---------------------------------------------------
    def get_gen_inputs(self, img_tensor):
        """blob (the encoded Gaussian primitives), bf (blob_features, the
        per-primitive appearance vectors), si (score_img, the splat
        weights) for the finest pyramid level."""
        with torch.no_grad():
            blob = self.model.encode(img_tensor)
            L = self.model.splat(blob)
            layer = L["layer_level_layouts"][-1][0]
            return blob, layer["blob_features"].clone(), layer["score_img"].clone()

    def build_pair(self, img_a, img_b):
        blob_a, bf_a, si_a = self.get_gen_inputs(img_a)
        blob_b, bf_b, si_b = self.get_gen_inputs(img_b)
        return {"blob_a": blob_a, "bf_a": bf_a, "si_a": si_a, "blob_b": blob_b, "bf_b": bf_b, "si_b": si_b}

    def make_recon(self, pil: Image.Image):
        """t=0 reconstruction of a single image (field-linear at eta=0)."""
        e = self.load_image(pil)
        d = self.build_pair(e, e)
        return self.field_linear(d, 0.0)

    # -- style-map pyramid ------------------------------------------------
    def _pyr(self, si):
        sp = {}
        s = si
        sp[s.shape[-1]] = s
        while s.shape[-1] > min(self.FMS):
            s = F.interpolate(s, s.shape[-1] // 2, mode="bilinear", align_corners=False)
            sp[s.shape[-1]] = s
        return sp

    def build_style_maps(self, bf, si):
        sp = self._pyr(si)
        return {size: torch.einsum("bnc,bnhw->bchw", bf, sp[size]) for size in set(self.FMS)}

    def decode_with_style_maps(self, blob_ref, sm):
        with torch.no_grad():
            L = self.model.splat(blob_ref)
            si = L["layer_level_layouts"][-1][0]["score_img"]
            fms = [round(si.shape[-1] * r) for r in self.model.generator.feature_map_size_ratios]
            sp = self._pyr(si)
            fi = sp[fms[0]][:, 1:].amax(dim=1)[:, None].repeat(1, self.model.generator.n_embedding, 1, 1)
            x = fi.clone()
            for i in range(len(fms)):
                x = self.model.generator.spade_blocks[i](x, sm[fms[i]])
                if i == len(fms) - 1:
                    break
                elif fms[i] != fms[i + 1]:
                    x = F.interpolate(x, size=x.shape[-1] * 2, mode="bilinear", align_corners=False)
            return torch.tanh(x.unsqueeze(1)).flatten(1, 2)

    def decode_interp(self, blob_ref, bf, si):
        """Primitive-linear decode: bf/si are already the eta-blended
        Gaussian-primitive appearance vectors and splat weights (CNT's own
        representation, blended BEFORE splatting -- distinct from
        field-linear, which blends the already-splatted dense field)."""
        with torch.no_grad():
            L = self.model.splat(blob_ref)
            L["layer_level_layouts"][-1][0]["blob_features"] = bf
            L["layer_level_layouts"][-1][0]["score_img"] = si
            return self.model.decode(L)

    # -- dense field (for the matching rules in texton_matching.matching) -
    def grids(self, d):
        """Flatten both images' finest-level style maps to (N, C) clouds."""
        sa = self.build_style_maps(d["bf_a"], d["si_a"])
        sb = self.build_style_maps(d["bf_b"], d["si_b"])
        L = max(self.FMS)
        A, B = sa[L][0], sb[L][0]
        C, H, W = A.shape
        return L, C, H, W, A.permute(1, 2, 0).reshape(-1, C), B.permute(1, 2, 0).reshape(-1, C)

    def sm_from_field(self, Z, L, H, W, C):
        it = Z.reshape(H, W, C).permute(2, 0, 1).unsqueeze(0)
        return {s: (it if s == L else F.interpolate(it, size=s, mode="bilinear", align_corners=False)) for s in set(self.FMS)}

    def decode_field(self, d, Z, L, H, W, C, layout: str = "a"):
        return self.decode_with_style_maps(d["blob_" + layout], self.sm_from_field(Z.float(), L, H, W, C))

    # -- field-linear (positional blending of the dense field) ------------
    def field_linear(self, d, eta: float):
        sa = self.build_style_maps(d["bf_a"], d["si_a"])
        sb = self.build_style_maps(d["bf_b"], d["si_b"])
        return self.decode_with_style_maps(d["blob_a"], {s: (1 - eta) * sa[s] + eta * sb[s] for s in set(self.FMS)})

    # -- primitive-linear (positional blending of the sparse primitives) --
    def primitive_linear(self, d, eta: float):
        return self.decode_interp(d["blob_a"], (1 - eta) * d["bf_a"] + eta * d["bf_b"], (1 - eta) * d["si_a"] + eta * d["si_b"])
