# COVERAGE.md — every table and figure, mapped to what reproduces it

One row per labeled table/figure in the main text and supplement (from
`INVENTORY.md` §1A). Status definitions:

- **reproducible** — an `experiments/*.py` script renders it from scratch (a
  GPU/CNT/Texture Mixer/Vacher install is still required; none of these
  scripts were executed in this environment, which has no GPU — see each
  script's own docstring and `docs/PROVENANCE.md` (Verification)).
- **rescorable** — no render script exists or is needed; the value recomputes
  from cached features/images already in the archive, via `score_only.py`
  (Tier 1) or `rescore.py` (Tier 2).
- **not reproducible** — neither of the above; a reason is given per row.

A claim can be both reproducible (Tier 3 render script exists) and
rescorable (Tier 1 already checks the archive's own cache) at once — that's
the strongest state, and it's independently verified: **245 of 257 checked
rows in `CHECK.md` MATCH the paper, 0 MISMATCH.**

## Main text

| Label | Producing script / notebook | Data it needs | Status |
|---|---|---|---|
| `tab:canonical` | `experiments/cnt_1000.py` + `experiments/tm_1000.py` (render); `score_only.py` (rescore, Tier1 58 rows MATCH) | `evidence/pairs_demo.csv` or a fresh DTD draw; archive: `tm_scale1000/*`, `matching_ablation/final128_n1000.csv`, `jackknife/tm1000_*` | **reproducible + rescorable** |
| `fig:qualitative` | `notebooks/4_1_canonical_rescore_128px.ipynb` (was `finish_day`) c12 + `notebooks/S_older_evaluations/paper_figure_candidate_factory.ipynb` | `paper_figs/grid/set{A,B,C}_fixed.png` (candidates) | **not reproducible** as the exact published figure — INVENTORY §0 item 10: no notebook writes the final picked filenames, and `paper/` ships no images to checksum against. The candidate source images *are* reproducible (`cnt_1000.py`'s six-pair grid). |
| `tab:eqsample` | `experiments/cnt_matched_200.py` (render); `score_only.py` (Tier1, 45 rows MATCH) | `matching_ablation/eqsample/*`, `tm_scale1000/ot` | **reproducible + rescorable** |
| `tab:generative` | `experiments/generative_120.py` (render/assemble, CNT+TM rows); `score_only.py` (Tier1, part of 77+5-row generative blocks, MATCH) | 12 dirs under `tm_scale1000/`; GPT rows below | **reproducible + rescorable** for pix/tex/gauss/ot/hard/tm rows. GPT rows (`gpt`,`gptsym`): **rescorable, not reproducible** — see "GPT-Image-1.5" section below. |
| `fig:gptstrip` | `notebooks/4_3b_generative_gpt_staging.ipynb` (was `Untitled6`) c7 | `paper_figs/gpt/gpt_strip_first8.png` | **not reproducible** as the exact figure — the panel-assembly code for this specific strip isn't preserved (INVENTORY §2). The underlying GPT images are shipped/hostable (rescorable). |
| `fig:app-mixtures` | `experiments/anchor_mixtures.py` | `pairs_120`-style category quads; CNT | **reproducible, unverified** — no cached file anywhere in the archive ever held `AnchorChangeA/B` (always printed-only); this script's output can only be confirmed by running it on a GPU. |
| `fig:transfer` | `notebooks/S_older_evaluations/stability_applications_5_8.ipynb` + candidate factory | `stability_apps/results/hero_kway_anchor.png` | **not reproducible** as the exact figure; the anchor-mixing mechanism itself is exercised by `anchor_mixtures.py`. |
| `fig:overview` (teaser) | `notebooks/S_older_evaluations/paper_figure_candidate_factory.ipynb` | `paper_figs_day2/fig01_teaser`, `fig02_method` | **not reproducible** — figure-only, no script, candidate images only. |

## Supplement

| Label | Producing script / notebook | Data it needs | Status |
|---|---|---|---|
| `tab:app-generative` | Same as `tab:generative` above (full 120-pair table) | Same | **reproducible + rescorable** (non-GPT rows); GPT rows rescorable/not-reproducible as above |
| `fig:app-gpt` | Same as `fig:gptstrip` | Same | **not reproducible** as exact figure; images rescorable |
| `tab:app-vacher` | `experiments/vacher_50.py` (FID column only) | `corrected_rerun/lit_manifest.csv`-style 50-pair draw; Vacher repo (`install/vacher.sh`) | **FID column: reproducible in principle, self-flagged approximate** — the script could not recover one parameter (`P26_REF_CAP`, reference images per category) from the saved notebook cell and exposed it as `--ref-per-category` with a documented default; treat its output as "same protocol shape," not a byte-exact replay of 268.3/284.6/318.4/273.9. **Timing (`VacherWSec`): rescorable but not wired** — `paper_completion/timing_n20.csv` exists in the archive but no script or Tier-1 check reads it (see "Open items" below). |
| `tab:app-primitives` | `experiments/primitives_120.py` + `texton_matching/primitives.py`; `score_only.py` (Tier1, 14 rows MATCH) | `pairs_120/pairs.csv`; CNT | **reproducible + rescorable** |
| `tab:rules` | `experiments/rules_200.py`; `score_only.py` (Tier1, 32 rows MATCH) | `matching_ablation/ref_list.json`-style 2,819-image reference; CNT | **reproducible + rescorable** |
| `tab:app-representation` | `notebooks/S_older_evaluations/cnt_sam_dino_compare.ipynb` + `never_gonna_give_you_up.ipynb` | none (`item2_representation_n40.json` is missing from the archive entirely) | **not reproducible** — printed-only, and the file that would hold it was never in the archive to begin with. The printed values are still preserved in `INVENTORY.md` §2's cross-check column even though the shipped notebooks have their saved outputs stripped (see "A note on stripped outputs" below). |
| `tab:app-realism` | `notebooks/S_older_evaluations/Vortex.ipynb` | none | **not reproducible** — printed-only, no file; values preserved in `INVENTORY.md` §2. |
| `tab:app-position` | `notebooks/S_older_evaluations/position_estimator_4_9.ipynb` | none | **not reproducible** — printed-only, AND flagged: this run fed CNT images in `[0,1]` instead of `[-1,1]` (INVENTORY §0 item 5), a bug fixed elsewhere (`corrected_pipeline_rerun.ipynb`) but never re-applied to this specific table. Rerunning the shipped notebook as-is reproduces a *known-buggy* run, not what the paper reports as fixed. |
| `tab:app-order` | `notebooks/S_older_evaluations/compute_cost_5_4.ipynb` + `corrected_pipeline_rerun.ipynb` | `compute_cost/order_dependence_n6.csv` (exists in archive) | **rescorable but not checked by Tier 1** (see "Open items"). The Vacher rows in this specific table are separately flagged in INVENTORY as **unverified/mismatched** against that same file (swap distance .634 in the paper vs .085 in the file) — a genuine discrepancy for the paper's authors to resolve, not something this package should silently paper over. |
| `fig:app-epsilon` | `notebooks/S_completion_eps_rho_timing20.ipynb` (was `paper_completion`) + candidate factory | `paper_completion/eps_sweep.json` (exists in archive) | **rescorable but not checked by Tier 1** (see "Open items") |
| `tab:app-repeat` | `notebooks/S_older_evaluations/degradation_ot_vs_tm_5_9.ipynb` | `degradation_5_9/results/degradation.csv` (exists in archive) | **rescorable but not checked by Tier 1**, except the autoencoder control row, which is printed-only even in the source notebook |
| `tab:runtime` | `experiments/runtime_120.py`; `score_only.py` (Tier1, 6 rows MATCH) | `pairs_120/pairs.csv`; CNT + Texture Mixer; one GPU | **reproducible + rescorable** for the CNT/TM columns (`EncodeSec`,`DecSec`,`OTTransportSec`,`HardAssignSec`,`TMEncSec`,`TMInterpSec`). `VacherWSec`/`GPTsec` in this same table come from other protocols entirely (see `tab:app-vacher` and the GPT section) and were never this table's own timings, even in the source notebook. `DecSecLow` (128px pass): the archive itself never saved `timing_120_ours128.csv` — permanently printed-only, not this package's gap to fill. |
| `fig:app-qualitative` | Same source as `fig:qualitative` | Same | **not reproducible** as exact figure; candidates reproducible via `cnt_1000.py` |
| `fig:app-boundary` | `notebooks/4_1_canonical_rescore_128px.ipynb` c6/c11/c14 + candidate factory | `paper_figs/boundary` | **not reproducible** as exact figure; the underlying correspondence-progression images are producible by varying `eta` in `texton_matching.matching`'s field-linear rule via `cnt_1000.py`. |
| `fig:app-alignshift` | `experiments/alignment.py`; `score_only.py` (Tier1, 8 rows MATCH) | `evidence/alignment_scores.csv`; CNT | **reproducible + rescorable** |
| `fig:app-mixtures2` | `experiments/anchor_mixtures.py` (second quad) | Same as `fig:app-mixtures` | **reproducible, unverified** (same caveat as `fig:app-mixtures`) |
| `fig:app-palette` | `experiments/anchor_mixtures.py` (palette output) | Same | **reproducible, unverified** (same caveat) |
| `fig:app-semantic` | `notebooks/S_older_evaluations/stability_applications_5_8.ipynb` (`tm_comparison/regions_*.png`) | none | **not reproducible** — exploratory, no cached number, no script |
| `fig:app-coding` | *(none shipped)* | none | **not reproducible, permanently** — INVENTORY §2 states the paper itself says the raw coding outputs were not retained. The source notebook, `fps_basis_5_7.ipynb`, is classified **LEGACY** (INVENTORY §3b, by the paper's own topic rule, not by this package), so it is intentionally not shipped here — see "Open items." |
| `fig:app-rho` | `notebooks/S_completion_eps_rho_timing20.ipynb` c10 | `paper_completion/rhostar_1000_sharp_exact.csv` (exists in archive) | **rescorable but not checked by Tier 1** (see "Open items") |
| `app:ceiling` | `experiments/ceiling_120.py`; `score_only.py` (Tier1, 9 rows MATCH) | CNT; `matching_ablation/ref_inc.npy` (for the 5,640-window reference builder) | **reproducible + rescorable**, except `CeilRho`: the new script writes this as `NaN` rather than fabricating it — it could not fully reconstruct the per-pair reconstruction-error/midpoint-quality join from the saved notebook cell, and said so rather than guessing. `score_only.py` still checks `CeilRho` against the archive's own cached `ceiling_summary.json` value (MATCH), just not against a *fresh* render. |

## GPT-Image-1.5 (`introduction.tex`, `generative.tex`, `statements.tex`)

Generation is **not reproducible**: the model is a proprietary Azure API,
its outputs are stochastic, and the repository does not call it. The scores
are reproducible from the shipped outputs. The full description (call
parameters, verbatim prompts, latency, scoring) is in `README.md`, section
"GPT-Image-1.5 comparator". What is shipped, at
`evidence/gpt_image_1_5_experiment/` (account-specific endpoint removed):

- `prompts/` -- the versioned prompt templates (P0 to P3) and their frozen
  sha256 hashes.
- `runs/call_ledger.jsonl` (475 dispatch records) and each run's
  `manifest.jsonl` -- per call: prompt, pair, input order, latency, token
  usage, output hash.
- `reports/`, `EXPERIMENT_PLAN.md`, `config.yaml` -- run reports, the frozen
  design and the execution configuration.

Also shipped: `evidence/gpt_pair_scores.csv` (per-pair realism, DINOv2
distances and placement for both GPT rows) and `evidence/gpt_call_summary.csv`
(one row per scored call, produced by `experiments/gpt_call_stats.py`).

The scoring-input images (`tm_scale1000/gpt/` = directed, prompt P2, series
S1; `tm_scale1000/gpt_p1/` = symmetric, prompt P1, series S2; 120 pairs each,
1024x1024) are part of the image archive released with the paper, not of this
repository. All 240 files are byte-identical to the hashes in the manifests.
`experiments/generative_120.py`'s `--gpt-dir` / `--gptsym-dir` point at those
two folders.

**What a co-author still has to provide.** Nothing is needed to score the
GPT rows. Items that no file in the archive can supply: `item2_representation_n40.json`
(`tab:app-representation`), `timing_120_ours128.csv` (the 128-px column of
`tab:runtime`), `tm_coupling1000_stats.csv` and `tm_pair_distance_120.csv`,
and the code that wrote `gpt_subset_numbers.json` and `gpt_subset_scores.csv`
(their values are traceable; the generating code was not preserved). The
runtime table's `\GPTsec` (36 s) matches the 45-call preview median (35.93 s);
the 240 scored calls have a median of 38.4 s.

## Every KEEP notebook (INVENTORY §3b, 28 total)

All 28 appear under `notebooks/` (14 individually renamed by paper
section, 14 bundled under `notebooks/S_older_evaluations/`) — none are
missing. See `notebooks/*.ipynb`'s first (header) cell for which claim
each one backs and whether a maintained script now supersedes it for
day-to-day reproduction. Outputs and execution metadata were stripped from
all 28 on the way in (see "A note on stripped outputs" below); Drive
mount paths were replaced with a `DATA_ROOT` environment variable read.

## Open items

Found during the coverage audit and not addressed:

- **`tab:app-order`, `fig:app-epsilon`, `tab:app-repeat`, `fig:app-rho`**:
  each has a real cached file in the archive
  (`compute_cost/order_dependence_n6.csv`, `paper_completion/eps_sweep.json`,
  `degradation_5_9/results/degradation.csv`,
  `paper_completion/rhostar_1000_sharp_exact.csv`) that could become a
  `score_only.py` Tier-1 check the same way `fig:app-alignshift` and
  `tab:runtime` are checked -- low effort, no GPU needed. Not done yet.
- **`fig:app-coding`**: permanently not reproducible (paper's own
  admission, no retained outputs); its source notebook is LEGACY-classified
  by the paper's own topic rule and therefore intentionally not shipped in
  this package.
- **The 7,000-pair path study** (`interpolation scaled up expiriments.ipynb`,
  INVENTORY #32): no macro from this notebook is cited anywhere in the
  paper (`LargePathN` and `LargePathMonotonicity` are in INVENTORY §1D's
  "defined but never used" list). It backs no paper claim, so there is
  nothing to reproduce; the notebook is classified SUPERSEDED and is not
  shipped.

## A note on stripped outputs

Every notebook under `notebooks/` had its cell outputs stripped (standard
hygiene/anonymity practice, and it cut `notebooks/`'s size from 49.7MB to
1.6MB). For claims that are "printed only" with no backing file
(`tab:app-representation`, `tab:app-realism`, `tab:app-position`, the
anchor-mixture prose, the round-trip and
sparse-coding prose), the ORIGINAL saved printed values are not visible in
the notebooks as shipped — but they were never lost: `INVENTORY.md`
(shipped at the repo root) already quotes every one of them verbatim in
its §2 cross-check column, e.g. "DINO 60%→66%", "65/100 p=2.58e-4". If a
reviewer wants the original notebook's live cell output (not just the
quoted number), that means going back to `notebooks_raw/`, which is not
part of this package.

## Summary

- 29 labeled tables/figures total (8 main text, 21 supplement).
- **12** reproducible + rescorable (script exists, Tier-1 MATCHes archive).
- **1** reproducible + rescorable except one sub-value (`app:ceiling`'s
  `CeilRho` — MATCHes the archive's cache but the new script can't
  re-derive it from scratch).
- **3** reproducible in principle but unverified (`anchor_mixtures.py`'s
  three outputs — no cached ground truth exists to check against).
- **1** reproducible-but-approximate, self-flagged (`tab:app-vacher`'s FID).
- **8** not reproducible as exact figures/tables (candidates located,
  final picks or generating code not preserved) — mostly figures.
- **4** genuinely not reproducible, no file, notebook is the sole record.
- **4** rescorable in the archive but not wired into `score_only.py` yet
  (listed above under "Open items").
- **1** permanently not reproducible by the paper's own admission
  (`fig:app-coding`).
- GPT-Image-1.5 rows: rescorable (images released, prompts/ledger shipped),
  generation itself not reproducible (proprietary, already run).

`CHECK.md`: **245 MATCH, 0 MISMATCH, 257 rows checked.**
