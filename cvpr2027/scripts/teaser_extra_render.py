# Render hand-picked extra pairs (not in the 1,000-pair manifest) with colab_render_more_pairs.py.
# Run after the notebook's config/install/setup cells, like tier1_experiments.py.
import json
EXTRA = json.load(open(f"{MT}/teaser_extra_pairs.json"))["pairs"]
for p in EXTRA:
    BYK[int(p["k"])] = {k: p[k] for k in ("k", "cA", "fA", "cB", "fB")}
NEW_KS = [int(p["k"]) for p in EXTRA]
SMOKE = False
T_TEASER_OVERRIDE = [i / 8 for i in range(9)]   # 9 frames, as in renders/ (strips need more than 5)
TDIR_OVERRIDE = f"{OUT}/renders_teaser9"
exec(open(f"{MT}/colab_render_more_pairs.py").read())
