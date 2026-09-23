#!/usr/bin/env bash
# Installs the CPU/GPU scoring stack: torch, torchvision (Inception-v3
# weights), DINOv2, LPIPS. This is everything score_only.py and rescore.py
# need beyond plain numpy/scipy/pandas; it does NOT include CNT itself
# (install/cnt.sh) or Texture Mixer (install/texture_mixer.sh).
#
# Source of truth: the canonical September setup cell shared by
# mechanism_study.ipynb, CNT_correspondence_experiments.ipynb,
# jackknife_dKID.ipynb, finishing_experiments.ipynb and others --
#   pip install -q timm lpips einops
#   dino = timm.create_model('vit_small_patch14_dinov2.lvd142m', pretrained=True, num_classes=0)
#   from torchvision.models import inception_v3, Inception_V3_Weights
#   inc = inception_v3(weights=Inception_V3_Weights.IMAGENET1K_V1, ...)
# Both DINOv2 and Inception-v3 weights are downloaded by timm/torchvision
# themselves from their own public hosts on first use -- no separate
# checkpoint file or URL to fetch here.
#
# Deliberate deviation from a literal reading of "DINOv2 via torch.hub":
# every notebook that scores DINOv2 features loads it through timm's
# 'vit_small_patch14_dinov2.lvd142m', not torch.hub.load('facebookresearch/
# dinov2', ...). timm re-hosts the same released weights under that name.
# We mirror what the notebooks actually ran. If you specifically need the
# facebookresearch/dinov2 torch.hub entry point instead, swap the loader in
# texton_matching/scoring_features.py; the feature vectors should match to
# floating-point noise (same weights, same architecture) but this has not
# been cross-checked here.
#
# Usage:
#   bash install/scoring.sh            # CPU-only torch
#   DEVICE=cuda CUDA_TAG=cu121 bash install/scoring.sh   # CUDA build
set -euo pipefail

DEVICE="${DEVICE:-cpu}"
CUDA_TAG="${CUDA_TAG:-cu121}"   # only used when DEVICE=cuda; see https://pytorch.org/get-started/locally/
PYTHON="${PYTHON:-python3}"

echo "[scoring.sh] installing scoring dependencies (DEVICE=$DEVICE)"

if [ "$DEVICE" = "cuda" ]; then
  "$PYTHON" -m pip install --index-url "https://download.pytorch.org/whl/${CUDA_TAG}" torch torchvision
else
  "$PYTHON" -m pip install torch torchvision
fi

# Versions match what the notebooks pinned where they pinned anything
# (timm==1.0.11 appears in the VORTEX / cnt-sam-dino-compare notebooks);
# left otherwise unpinned so pip can resolve compatible current releases.
"$PYTHON" -m pip install "timm>=1.0.11" lpips einops numpy scipy pandas pillow

echo "[scoring.sh] verifying imports and triggering the one-time weight downloads..."
"$PYTHON" - <<'PYEOF'
import os
# Must be set before `import timm` (pulls in huggingface_hub). Recent
# huggingface_hub versions auto-detect a Colab/Jupyter runtime and
# proactively look for an HF_TOKEN via Colab's secrets UI, prompting for
# access even for a fully public, anonymous model download (DINOv2's
# weights need no token at all). This disables that.
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
import torch, torchvision, timm, lpips
print("torch", torch.__version__, "| cuda available:", torch.cuda.is_available())
print("torchvision", torchvision.__version__)
from torchvision.models import inception_v3, Inception_V3_Weights
_ = inception_v3(weights=Inception_V3_Weights.IMAGENET1K_V1, aux_logits=True)
print("Inception-v3 (IMAGENET1K_V1) weights OK")
_ = timm.create_model('vit_small_patch14_dinov2.lvd142m', pretrained=True, num_classes=0)
print("DINOv2 ViT-S/14 (timm: vit_small_patch14_dinov2.lvd142m) weights OK")
_ = lpips.LPIPS(net='alex')
print("LPIPS (alex) weights OK")
PYEOF

echo "[scoring.sh] done."
