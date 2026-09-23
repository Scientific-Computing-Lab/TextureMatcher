#!/usr/bin/env bash
# Installs Texture Mixer (Yu et al.) into its own conda environment and
# fetches the released "earth texture" checkpoint used throughout the paper.
#
# Mirrors tm_scale1000_headtohead.ipynb "PHASE 1, CELL 1" / finishing_
# experiments.ipynb's TF1 phase exactly: repo clone, its tensorflow_vgg
# dependency, the TF2->TF1-compat shim (see environment_tm.yml for why a
# real TF1.15 env is not used), and the checkpoint download. The checkpoint
# download happens right after cloning, before the tensorflow_vgg clone and
# the tfutil.py patch -- same fail-fast principle as install/cnt.sh.
#
# Checked against the CNT-side failure modes install/cnt.sh had to fix
# (2026-09-22 review): this script itself installs no pinned old package
# versions (its only pip step is `pip install -q gdown`; TextureMixer's own
# `requirements.txt`, which DOES pin ancient TF1.12-era versions, is never
# installed here or by any notebook -- both bypass it entirely via the
# TF2+compat.v1+tf_slim shim above). The one place a version pin COULD
# bite on a new Python the way CNT's requirements.in did is an upper-bounded
# `tensorflow<X` constraint imposed by a CALLER (this script doesn't set
# one) -- environment_tm.yml deliberately leaves tensorflow's upper bound
# unconstrained for exactly this reason; don't add one.
#
# Checkpoint (earth_texture/network-final.pkl): every notebook loads this
# from a cache in our project's own Drive, but it is fetched there with a
# plain, unauthenticated gdown call the first time it's needed:
#   gdown 1ObAFBPGaRJFo11LUa0qNhRX14nTEWKC1 -O earth.zip
# VERIFIED against the authors' own repository (2026-09-22): the
# TextureMixer GitHub README (https://github.com/ningyu1991/TextureMixer,
# raw at https://raw.githubusercontent.com/ningyu1991/TextureMixer/master/README.md,
# "Pre-Trained Models" section) lists three pretrained models by name, and
# "Earth texture" links to
#   https://drive.google.com/file/d/1ObAFBPGaRJFo11LUa0qNhRX14nTEWKC1/view?usp=sharing
# -- the same file ID as above, exactly. (The README also separately links
# a prepared earth-texture *test dataset*, a different public share, ID
# 1A08JnZEUJGAFuLkhYtkqz7t9qnjMjVVj -- that one appears verbatim in some
# notebooks too, e.g. sota_baselines_rabin_5_5.ipynb, but it is a dataset,
# not the checkpoint, and this script does not use it.) This is the
# authors' own distribution channel, not a link into our private Drive.
#
# Usage (run AFTER creating+activating the conda env from environment_tm.yml):
#   conda env create -f install/environment_tm.yml
#   conda activate texton-matching-tm
#   bash install/texture_mixer.sh [target_dir]     # default target_dir: ./TextureMixer
set -euo pipefail

TARGET_DIR="${1:-TextureMixer}"
TM_REPO="https://github.com/ningyu1991/TextureMixer.git"
VGG_REPO="https://github.com/machrisaa/tensorflow-vgg.git"
CKPT_GDRIVE_ID="1ObAFBPGaRJFo11LUa0qNhRX14nTEWKC1"
# Full sha256 of earth_texture/network-final.pkl (233,627,047 bytes, dated
# 2018-12-13 inside the zip), obtained by downloading this ID directly
# while building this package (2026-09-22) -- no prior recorded hash
# existed to cross-check against (unlike CNT's), so this is the first
# recording of it; if it ever changes, the authors have re-released the file.
CKPT_SHA256="b2361d5e1ac5bff7e4c32548531dab1d93b91c15c9d448d4324f6adedaff1abf"
PYTHON="${PYTHON:-python3}"

echo "[texture_mixer.sh] cloning Texture Mixer into $TARGET_DIR"
if [ -d "$TARGET_DIR/.git" ]; then
  echo "[texture_mixer.sh] $TARGET_DIR already exists; leaving it as-is"
else
  git clone -q "$TM_REPO" "$TARGET_DIR"
fi

# Checkpoint download happens NOW, right after cloning and before anything
# else (the tensorflow_vgg clone, the tfutil.py patch) -- same fail-fast
# principle as install/cnt.sh: a Drive rate-limit on this >200MB file
# should surface immediately, not after other (admittedly cheap, here)
# setup work. This script's only hard-failure condition is this checkpoint.
mkdir -p "$TARGET_DIR/earth_texture"
CKPT_PATH="$TARGET_DIR/earth_texture/network-final.pkl"
if [ -f "$CKPT_PATH" ]; then
  echo "[texture_mixer.sh] checkpoint already present at $CKPT_PATH"
else
  echo "[texture_mixer.sh] downloading the earth-texture checkpoint"
  "$PYTHON" -m pip install -q gdown
  "$PYTHON" -m gdown "$CKPT_GDRIVE_ID" -O earth.zip || true   # check the result explicitly below, not gdown's own exit code
  if [ -f earth.zip ]; then
    unzip -oq earth.zip -d "$TARGET_DIR"
    rm -f earth.zip
  fi
fi

if [ ! -f "$CKPT_PATH" ]; then
  echo "[texture_mixer.sh] ERROR: no file at $CKPT_PATH after the download attempt." >&2
  echo "[texture_mixer.sh]        gdown may have been rate-limited (a real risk on a shared Colab IP" >&2
  echo "[texture_mixer.sh]        for a >200MB file), or the zip's internal layout may have changed." >&2
  echo "[texture_mixer.sh]        Retry, or download it by hand from the URL in this script's header" >&2
  echo "[texture_mixer.sh]        comment and place it at $CKPT_PATH yourself." >&2
  exit 1
fi
CKPT_BYTES="$(wc -c < "$CKPT_PATH" | tr -d ' ')"
if [ "$CKPT_BYTES" -lt 100000000 ]; then   # real file is 233,627,047 bytes; a Drive error page is a few KB
  echo "[texture_mixer.sh] ERROR: $CKPT_PATH is only $CKPT_BYTES bytes (expected ~233MB)." >&2
  echo "[texture_mixer.sh]        This is almost certainly a Google Drive rate-limit error page." >&2
  head -c 300 "$CKPT_PATH" >&2 || true
  echo >&2
  rm -f "$CKPT_PATH"
  exit 1
fi
echo "[texture_mixer.sh] checkpoint size OK: $CKPT_BYTES bytes"

GOT_SHA="$("$PYTHON" - "$CKPT_PATH" <<'PYEOF'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PYEOF
)"
if [ "$GOT_SHA" = "$CKPT_SHA256" ]; then
  echo "[texture_mixer.sh] checkpoint sha256 matches: $GOT_SHA"
else
  echo "[texture_mixer.sh] WARNING: checkpoint sha256 is $GOT_SHA, expected $CKPT_SHA256." >&2
  echo "[texture_mixer.sh]          This may be a different release of the checkpoint than the one" >&2
  echo "[texture_mixer.sh]          recorded when this script was written. Proceed only if you understand why." >&2
fi

if [ ! -d "$TARGET_DIR/tensorflow_vgg" ]; then
  echo "[texture_mixer.sh] cloning tensorflow_vgg dependency"
  git clone -q "$VGG_REPO" "$TARGET_DIR/tensorflow_vgg"
fi

echo "[texture_mixer.sh] patching two is-comparison bugs in tfutil.py (Python 3 changed small-int identity caching)"
TFUTIL="$TARGET_DIR/tfutil.py"
if [ -f "$TFUTIL" ]; then
  "$PYTHON" - "$TFUTIL" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace("v.shape.ndims is 0", "v.shape.ndims == 0").replace("v.shape.ndims is 1", "v.shape.ndims == 1")
open(p, "w").write(s)
print(f"patched {p}")
PYEOF
fi

echo "[texture_mixer.sh] verifying the TF1-on-TF2 shim imports cleanly"
"$PYTHON" - <<PYEOF
import sys, types, importlib, importlib.util, importlib.machinery
sys.path.insert(0, "$TARGET_DIR")
if "imp" not in sys.modules:
    _imp = types.ModuleType("imp")
    def _load_source(name, pathname, file=None):
        spec = importlib.util.spec_from_file_location(name, pathname)
        mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
        spec.loader.exec_module(mod); return mod
    def _find_module(name, path=None):
        spec = importlib.machinery.PathFinder().find_spec(name, path)
        if spec is None: raise ImportError(name)
        return (None, spec.origin, (".py", "r", 1))
    _imp.load_source = _load_source; _imp.find_module = _find_module
    _imp.new_module = lambda n: types.ModuleType(n); _imp.reload = importlib.reload
    _imp.acquire_lock = lambda: None; _imp.release_lock = lambda: None; _imp.PY_SOURCE = 1
    sys.modules["imp"] = _imp

import tensorflow as _tf2
tf1 = _tf2.compat.v1
tf1.disable_eager_execution(); tf1.disable_v2_behavior()
tf1.logging.set_verbosity(tf1.logging.ERROR)
if not hasattr(tf1, "Dimension"):
    tf1.Dimension = getattr(_tf2, "Dimension", int)

import tf_slim as _slim
_contrib = types.ModuleType("tensorflow.contrib")
_contrib.slim = _slim; _contrib.framework = _slim; _contrib.layers = _slim
sys.modules["tensorflow.contrib"] = _contrib
sys.modules["tensorflow.contrib.slim"] = _slim
sys.modules["tensorflow.contrib.framework"] = _slim
sys.modules["tensorflow.contrib.layers"] = _slim
tf1.contrib = _contrib
sys.modules["tensorflow"] = tf1

import tfutil, misc
print("Texture Mixer repo + TF1-on-TF2 shim import OK; TF", _tf2.__version__)
PYEOF

echo "[texture_mixer.sh] done. Texture Mixer is at $TARGET_DIR, checkpoint at $TARGET_DIR/earth_texture/network-final.pkl"
