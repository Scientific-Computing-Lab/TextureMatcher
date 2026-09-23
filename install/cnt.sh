#!/usr/bin/env bash
# Installs Compositional Neural Textures (CNT) at the exact commit every
# September-generation notebook pinned, and fetches its released checkpoint.
#
# This is a bash port of the EXACT cell that succeeded on a fresh Colab T4,
# Python 3.13, after several stricter variants failed (see
# colab/reproduce.ipynb's install cell, which is this same logic inline).
# It mirrors the paper notebooks' canonical setup cell
# (CNT_joint_basis_and_ceiling.ipynb cell 1 and siblings) with two
# documented additions, and deliberately does NOT tighten anything else:
#
#   1. THE CHECKPOINT DOWNLOAD. The notebooks symlinked it from our
#      project's own Drive cache (`ln -sfn {BASE}/cnt_ckpts ckpts`); a
#      reviewer has no access to that, so this script downloads it via
#      gdown instead (see the checkpoint section below for the source).
#   2. AN EXPLICIT UPGRADE LINE at the end: `pip install -U timm
#      "hydra-core>=1.3" "omegaconf>=2.3" "antlr4-python3-runtime==4.9.3"`.
#      CNT's requirements.in pins 2024-era versions that are not
#      installable at all on Python 3.13 (metadata-generation-failed), and
#      even where they DO install, they break at *runtime*: old
#      hydra-core/omegaconf pull in antlr4-python3-runtime 4.8, which
#      raises `ModuleNotFoundError: typing.io` on 3.13 (that module was
#      removed); old timm raises `ValueError: mutable default
#      MaxxVitConvCfg` on newer Python/dataclasses. The notebooks never hit
#      this because they ran on an older Colab Python. This is why the
#      requirements.in install below is NOT done line by line, even though
#      that sounds like it should be "safer": line-by-line succeeds at
#      planting exactly those broken old pins, which then break later, at
#      model-build or inference time, far from the install cell -- a much
#      more confusing failure than requirements.in just partially failing
#      up front and being immediately overridden by the upgrade line.
#
# What this script deliberately does NOT do, because the notebooks didn't
# either:
#   - It does not use `set -e`. The canonical cell's install line is
#     `os.system('pip install -q -r requirements.in; pip install -q
#     "git+...detectron2.git"')` -- note the `;`, not `&&`: the detectron2
#     install runs regardless of whether requirements.in fully succeeded,
#     and neither failure stops the cell (os.system's return code is never
#     checked). A `set -e` script that aborts on requirements.in's failure
#     is STRICTER than the notebooks, not a faithful port of them, and (on
#     current Colab) dies at a step the notebooks always tolerated.
#   - It does not install requirements.in line by line. That was an
#     earlier, worse idea (see above) -- it "succeeds" at installing
#     exactly the pins that break at runtime.
#   - It does not gate the detectron2 install behind CNT's own import
#     failing. `from src.inference.core import TexAutoEncoderInference,
#     load_image` typically succeeds WITHOUT detectron2 -- it's needed for
#     CNT's Mask2Former-based texture segmentation, only actually invoked
#     once you construct TexAutoEncoderInference(...) and build the model.
#     So this script checks `import detectron2` directly and installs it
#     if missing, independent of whether the plain CNT import succeeds.
#
# The one and only hard-failure condition in this script is the checkpoint:
# if it's missing, or under 1GB (almost certainly a Google Drive rate-limit
# error page instead of the real ~1.27GB file -- a real risk on a shared
# Colab IP), this script exits 1 immediately, before spending any time on
# the (comparatively slow) detectron2 build.
#
# Checkpoint (finetuned-model256.ckpt) source, verified against the
# authors' own repository: the CNT GitHub README
# (https://github.com/phtu-cs/compositional-neural-textures, raw at
# https://raw.githubusercontent.com/phtu-cs/compositional-neural-textures/main/README.md)
# says, verbatim: "download model checkpoint from Google Drive" linking to
#   https://drive.google.com/file/d/1kIGSZlI6O_rEssw9IYaZyBA0wycD8JBG/view?usp=sharing
# -- the same file ID this script uses, exactly; this is the authors' own
# distribution channel, actually downloaded and sha256-verified while
# building this package (see CKPT_SHA256_PREFIX below).
# (The project page at https://phtu-cs.github.io/cnt-siga24/ is NOT a
# reliable source for this: its HTML mixes the CNT title/authors with
# leftover content and Drive links from an unrelated, older MPI-INF project
# template (XNect). Use the GitHub README, not that page.)
#
# Usage:
#   bash install/cnt.sh [target_dir]      # default target_dir: ./cnt-siga24
set -uo pipefail
# NOT `set -e` -- see the header comment above.

TARGET_DIR="${1:-cnt-siga24}"
CNT_REPO="https://github.com/phtu-cs/compositional-neural-textures.git"
CNT_COMMIT="07269302610c92ce38e2dbbe31c492fd09e1c73e"
CKPT_GDRIVE_ID="1kIGSZlI6O_rEssw9IYaZyBA0wycD8JBG"
CKPT_NAME="finetuned-model256.ckpt"
CKPT_MIN_BYTES=1000000000   # real file is ~1.27GB; a rate-limited/failed gdown call can
                             # leave a few-KB HTML "too many users have viewed this file" page instead
CKPT_SHA256_PREFIX="a3f80515ac5d8c8d"   # from CNT_correspondence_experiments.ipynb; verified by an actual download
PYTHON="${PYTHON:-python3}"

echo "[cnt.sh] pip install -q timm lpips einops gdown (matches the canonical cell's inline install)"
"$PYTHON" -m pip install -q timm lpips einops gdown

echo "[cnt.sh] cloning CNT at $CNT_COMMIT into $TARGET_DIR"
rm -rf "$TARGET_DIR"
git clone -q "$CNT_REPO" "$TARGET_DIR"
( cd "$TARGET_DIR" && git checkout -q "$CNT_COMMIT" )
GOT_COMMIT="$(cd "$TARGET_DIR" 2>/dev/null && git rev-parse HEAD 2>/dev/null || echo MISSING)"
echo "[cnt.sh] commit: $GOT_COMMIT"

mkdir -p "$TARGET_DIR/ckpts"
CKPT_PATH="$TARGET_DIR/ckpts/$CKPT_NAME"
echo "[cnt.sh] downloading checkpoint NOW, before any further pip work (fail fast on a Drive rate-limit"
echo "[cnt.sh] rather than discovering it after a 5-10 minute detectron2 build)"
"$PYTHON" -m gdown -q "$CKPT_GDRIVE_ID" -O "$CKPT_PATH"

# THE ONLY HARD FAILURE IN THIS SCRIPT.
if [ ! -f "$CKPT_PATH" ]; then
  echo "[cnt.sh] ERROR: no file at $CKPT_PATH after the download attempt." >&2
  echo "[cnt.sh]        Retry, or download it by hand from the URL in this script's header" >&2
  echo "[cnt.sh]        comment and place it at $CKPT_PATH yourself." >&2
  exit 1
fi
CKPT_BYTES="$(wc -c < "$CKPT_PATH" | tr -d ' ')"
if [ "$CKPT_BYTES" -lt "$CKPT_MIN_BYTES" ]; then
  echo "[cnt.sh] ERROR: $CKPT_PATH is only $CKPT_BYTES bytes (expected >= $CKPT_MIN_BYTES)." >&2
  echo "[cnt.sh]        This is almost certainly a Google Drive rate-limit error page, not the" >&2
  echo "[cnt.sh]        checkpoint. Contents (first 300 bytes):" >&2
  head -c 300 "$CKPT_PATH" >&2 || true
  echo >&2
  rm -f "$CKPT_PATH"
  echo "[cnt.sh]        Removed the bad file. Retry, or fetch it by hand and place it at" >&2
  echo "[cnt.sh]        $CKPT_PATH yourself." >&2
  exit 1
fi
echo "[cnt.sh] checkpoint size OK: $CKPT_BYTES bytes"
GOT_SHA="$("$PYTHON" - "$CKPT_PATH" <<'PYEOF'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()[:16])
PYEOF
)"
if [ "$GOT_SHA" = "$CKPT_SHA256_PREFIX" ]; then
  echo "[cnt.sh] checkpoint sha256 prefix matches: $GOT_SHA"
else
  echo "[cnt.sh] WARNING: checkpoint sha256 prefix is $GOT_SHA, expected $CKPT_SHA256_PREFIX." >&2
  echo "[cnt.sh]          This may be a newer release of the checkpoint. Proceed only if you understand why." >&2
fi

PREV_CWD="$(pwd)"
cd "$TARGET_DIR"
echo "[cnt.sh] checking CNT's own plain import (this does NOT need detectron2 -- that's checked separately, below)"
if "$PYTHON" -c "import sys; sys.path.insert(0,'.'); from src.inference.core import TexAutoEncoderInference, load_image" 2>/tmp/cnt_sh_import_err.$$; then
  echo "[cnt.sh] CNT imports OK"
  rm -f /tmp/cnt_sh_import_err.$$
else
  echo "[cnt.sh] installing missing deps: $(cat /tmp/cnt_sh_import_err.$$ | tail -1)"
  rm -f /tmp/cnt_sh_import_err.$$
  # `;` not `&&`, matching the canonical cell exactly: the detectron2 install
  # runs regardless of whether requirements.in fully succeeds, and neither
  # failure aborts this script (no `set -e`; see header comment).
  "$PYTHON" -m pip install -q -r requirements.in
  "$PYTHON" -m pip install -q "git+https://github.com/facebookresearch/detectron2.git"
fi

echo "[cnt.sh] checking detectron2 directly (independent of whether the plain import above needed it)"
if "$PYTHON" -c "import detectron2" 2>/dev/null; then
  echo "[cnt.sh] detectron2 already importable"
else
  echo "[cnt.sh] installing detectron2 from source (compiles CUDA ops if a GPU toolchain is present;"
  echo "[cnt.sh] 5-10 minutes on a Colab T4)"
  "$PYTHON" -m pip install -q "git+https://github.com/facebookresearch/detectron2.git"
fi

echo "[cnt.sh] upgrading timm/hydra-core/omegaconf/antlr4-python3-runtime explicitly -- CNT's own"
echo "[cnt.sh] requirements.in pins break at runtime on Python 3.13 (see header comment); this line"
echo "[cnt.sh] is what actually fixes that, regardless of what requirements.in just installed"
"$PYTHON" -m pip install -q -U timm "hydra-core>=1.3" "omegaconf>=2.3" "antlr4-python3-runtime==4.9.3"

cd "$PREV_CWD"

echo "[cnt.sh] installing the scoring stack too (install/scoring.sh) -- same as the notebook's install cell"
if [ -f "$(dirname "$0")/scoring.sh" ]; then
  bash "$(dirname "$0")/scoring.sh"
fi

echo "[cnt.sh] done."
echo "[cnt.sh]   ckpt: $(( $(wc -c < "$CKPT_PATH" | tr -d ' ') / 1000000 )) MB"
echo "[cnt.sh]   detectron2: $("$PYTHON" -c "import importlib.util; print(importlib.util.find_spec('detectron2') is not None)")"
