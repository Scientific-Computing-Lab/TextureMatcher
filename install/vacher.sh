#!/usr/bin/env bash
# Installs Vacher et al.'s optimization-based texture-interpolation baseline
# (tab:app-vacher / the Gram/Gaussian/Wasserstein rows), used for a
# not-yet-scriptable comparison; no experiments/ script renders it (see
# docs/PROVENANCE.md).
#
# Mirrors every notebook that used it (compute_cost_5_4.ipynb,
# literature_baselines_4_1.ipynb, literature_baselines_corrected.ipynb,
# dtd/images/stability_applications_5_8.ipynb, paper_completion.ipynb):
#   git clone -q --depth 1 https://github.com/JonathanVacher/texture-interpolation.git
#
# No pinned commit: every one of those clones is `--depth 1` (shallow,
# whatever HEAD is at clone time), and none of the notebooks recorded a
# commit hash for this repo the way they did for CNT
# (07269302610c92ce38e2dbbe31c492fd09e1c73e, checked and asserted against).
# So there is no commit to reproduce here -- VACHER_COMMIT below defaults to
# empty (clone HEAD, matching the notebooks exactly); set it if you find and
# want to pin a specific commit yourself.
#
# Usage:
#   bash install/vacher.sh [target_dir]                 # default target_dir: ./texture-interpolation
#   VACHER_COMMIT=<sha> bash install/vacher.sh           # pin to a specific commit (not what the notebooks did)
set -euo pipefail

TARGET_DIR="${1:-texture-interpolation}"
VACHER_REPO="https://github.com/JonathanVacher/texture-interpolation.git"
VACHER_COMMIT="${VACHER_COMMIT:-}"
PYTHON="${PYTHON:-python3}"

if [ -d "$TARGET_DIR/.git" ]; then
  echo "[vacher.sh] $TARGET_DIR already exists; leaving it as-is"
elif [ -n "$VACHER_COMMIT" ]; then
  echo "[vacher.sh] cloning Vacher texture-interpolation and checking out $VACHER_COMMIT"
  git clone -q "$VACHER_REPO" "$TARGET_DIR"
  ( cd "$TARGET_DIR" && git checkout -q "$VACHER_COMMIT" )
else
  echo "[vacher.sh] cloning Vacher texture-interpolation at HEAD (shallow, matching the notebooks -- no pinned commit exists upstream)"
  git clone -q --depth 1 "$VACHER_REPO" "$TARGET_DIR"
fi

GOT_COMMIT="$(cd "$TARGET_DIR" && git rev-parse HEAD)"
echo "[vacher.sh] at commit $GOT_COMMIT -- record this yourself if you need to reproduce exactly across runs"

echo "[vacher.sh] done. Vacher texture-interpolation is at $TARGET_DIR"
echo "[vacher.sh] NOTE: no experiments/ script in this package renders the Vacher baseline;"
echo "[vacher.sh]       tab:app-vacher's FID column is one of the values docs/INVENTORY.md and docs/CHECK.md"
echo "[vacher.sh]       both flag as printed-only in the source notebooks (see paper_completion.ipynb"
echo "[vacher.sh]       cell 3 for the timing numbers, which score_only.py does reproduce)."
