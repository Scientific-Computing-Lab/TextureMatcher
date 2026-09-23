# Colab notebooks

Two notebooks reproduce the five demo pairs end to end on a Colab GPU runtime
(`Runtime -> Change runtime type -> GPU`) and print PASS or FAIL. Download the
repository as a zip and upload it through Colab's file panel before the first
run; any zip name works. Every cell after the restart adds `/content/package` to
`sys.path` and uses absolute paths, so "Run cell and below" from the first
post-restart cell works in a fresh kernel.

Both notebooks build the five endpoints with
`texton_matching.data.prepare_demo_endpoints` from a fresh download of the public
DTD release (fallback: `evidence/demo_pairs/`) and write them to
`/content/rendered/A|B/<k>.png`. The pairs are k = 0006, 0009, 0017, 0022, 0053
of `pairs_120/pairs.csv`.

## `reproduce.ipynb` (CNT)

Cells, identified by their `#@title`:

1. *(markdown)* Reproduce: CNT side (texton matching)
2. Environment setup (no secrets, please)
3. Get the package
4. Install CNT exactly as the paper notebooks did (5 to 10 minutes; ends with a
   restart instruction)
5. *(markdown)* Restart the session now
6. Get the paper's 5 demo pairs (from data/pairs_120/pairs.csv)
7. Render every CNT rule for the 5 demo pairs
8. Score them (quick reference; see the markdown note at the top)
9. Run rescore.py end to end and print the rows
10. PASS/FAIL: field-linear placement against the shipped evidence CSV

The check compares each pair's field-linear placement (a DINOv2 distance ratio)
with `evidence/field_linear_place_1000.csv` at tolerance 0.01. The value depends
on the installed DINOv2/timm version. If the check fails, compare library
versions first.

## `reproduce_tm.ipynb` (Texture Mixer)

1. *(markdown)* Reproduce: Texture Mixer side (TF1-on-TF2 path)
2. Get the package
3. Install Texture Mixer (TF1-on-TF2 shim; NOT the torch/CNT env)
4. Get the paper's 5 demo pairs and render every TM rule
5. *(markdown)* Restart the session now
6. Score native-lerp/mean/soft-OT and print the rows
7. PASS/FAIL: native-lerp pixels against the shipped evidence PNGs

The check compares the rendered native-lerp midpoints with
`evidence/tm_lerp_demo/`: PASS when the maximum absolute difference is at most 8
and the mean at most 1 grey level, per pair. Texture Mixer rendering is
deterministic up to GPU nondeterminism, while feature-based scores depend on the
observer version, so the check is pixel-based. A DINOv2 placement table below it
is informational; its differences from `evidence/tm_lerp_place_1000.csv` reflect
library versions, not the rendered pixels.
