# CVPR 2027 version: "Interpolate Distributions, Not Positions"

This folder adds everything that is new in the CVPR version of the paper: the same pairing operator in four more
models (DINOv2 with a representation autoencoder, Texture Mixer with every rule, the Stable Diffusion VAE latent,
and DiffMorpher's attention), two-sided paths, the distance experiment, the controls in the supplement, and the
blind human study. The library in `../texton_matching/` and the CNT experiments in `../experiments/` are unchanged.

## Check the numbers without a GPU

```bash
cd cvpr2027
python check_cvpr_numbers.py        # numpy only; writes CHECK_CVPR.md
```

The script recomputes 139 values printed in the paper and supplement from the per-pair scores in `evidence/`
and the answer codes in `human_study/`. Current result: 133 match exactly, 3 human-study interval bounds are within
one percentage point (Monte Carlo bootstrap), 3 interval bounds differ by one unit in their last printed digit,
and none mismatch. `CHECK_CVPR.md` lists every value.

## Where each result comes from

| Paper | What | Code | Scores |
|---|---|---|---|
| Fig. 1, Table 1 (CNT, 1,000 pairs) | positional vs soft OT along the path | `scripts/tier1_experiments.py` (E1) | `evidence/tier1/e1_*.csv` |
| Table 1 (CNT, DINO-RAE rows) | every rule at every t, 120 pairs, 128 px | `notebook/cvpr_experiments.ipynb` (C, E, F) | `evidence/scores/kid_by_t_128.csv`, `delta_kid_by_t_128.csv` |
| Table 1 (Texture Mixer row) | every rule, 1,000 pairs | `scripts/tier6_tm_{pair,render,score}.py` | `evidence/tier6/` |
| Table 1 (SD-VAE row) | latent interpolation, 120 pairs | `scripts/tier1_experiments.py` (E2) | `evidence/tier1/e2_*.csv` |
| Fig. 1, Sec. 4.2 (DiffMorpher) | OT pairing inside attention | `scripts/dm_ot_patch.py`, notebook (B) | `evidence/scores/dm_ot_vs_official_*.csv` |
| Fig. 4, Supp. distance table | nearest-neighbour test on crops and DTD classes | `scripts/tier4_distance_matrix.py`, `scripts/tier5_distance_more.py` | `evidence/tier4*/`, `evidence/tier5/` |
| Fig. 4 drawing | rank matrices | `figures/make_readable.py`, `figures/make_matrices.py` | `evidence/tier5/` + DTD |
| Table 4, Supp. G | blind human study | `human_study/analyze_responses.py` | `human_study/responses.txt`, `answer_key.csv` |
| Supp. path table | rules along the path, two-sided paths | notebook (C, F), `scripts/tier1b_followup.py` | `evidence/scores/`, `evidence/tier1/` |
| Supp. controls | map extension, slack, spatial transitions | `scripts/tier2_experiments.py`, `scripts/tier3_extension_control.py` | `evidence/tier2/`, `evidence/tier3/` |
| Supp. (LoRA, reversal, self-interpolation, jump) | decoder fine-tuning and path diagnostics | notebook (D, F) | `evidence/scores/` |
| Supp. cross-fade study | pixel cross-fade and reconstruction floor | (scores only) | `evidence/crossfade/metrics_v2.csv` |
| Teaser and qualitative strips | renders for the figures | `scripts/teaser_*.py`, `scripts/colab_render_more_pairs.py` | (images) |

## Re-running the experiments

All experiments ran on one A100 in Google Colab. `notebook/cvpr_experiments.ipynb` installs the models (CNT, the
DINOv2 representation autoencoder, SAM2, DiffMorpher in its own environment) and defines the shared helpers; every
section is resumable and writes one file per pair. The scripts in `scripts/` are run with `exec` after the notebook's
setup cells, as noted at the top of each script, and each has a `SMOKE = True` mode that runs a few pairs first.
Paths: the notebook reads and writes under `MT` (default `/content/drive/MyDrive/masters_texture`, override with
the `CVPR_MT` environment variable); outputs go to `MT/cvpr_experiments/`. Pairs and images come from DTD, as in
the main package (`../texton_matching/data.py`).

DiffMorpher is not deterministic even with fixed seeds, so its renders and KIDs vary slightly between runs; the
shipped scores are the ones in the paper.

## Human study

`responses.txt` holds one anonymous code per completed session; no names or other identifying information were
collected. `analyze_responses.py` decodes the codes against `answer_key.csv` (which option was OT on each screen)
and computes every number in Table 4 and Supp. G. `stimuli.json` is the exact set of images shown, and
`STIMULUS_SELECTION.md` describes how the 25 screens were chosen.
