# Provenance notes

Notes on how the shipped artifacts relate to the original experiment files.
`docs/COVERAGE.md` maps every table and figure to its script or notebook;
`docs/INVENTORY.md` lists which notebook and data file each paper number came
from; `docs/CHECK.md` is the generated Tier 1 report.

## Tier 1 inputs

`evidence/tier1/` holds the 63 cached files that `score_only.py` reads, in the
layout of the original results archive. Floating-point arrays are stored as
float16 (`experiments/pack_tier1.py` rebuilds the folder from the archive) and
are cast to float64 on load. The packed inputs give the same 245 MATCH and 0
MISMATCH as the full-precision archive; recomputed values differ from it by
about 1e-7 in KID. The folder `pairs_120/` is the 120-pair subset; an older
archive layout names it `pairs_for_*`, and both are accepted.

`evidence/paper_numbers/` holds the paper's macro files (`numbers.tex`,
`numbers_v2.tex`) and `numbers_tmfid.tex`, three macros for the Texture Mixer FID
of Table 1 (`\TMkFIDlerp`, `\TMkFIDmean`, `\TMkFIDot`) that `score_only.py`
recomputes from the cached Inception features against the canonical reference.

## Tier 2 balance columns

The generic rescorer computes KID, FID and per-image realism for every table. The
balance column needs reconstruction anchors at t=0, and the `tab:rules`
endpoint-gap column needs a t=1 render. `cnt_1000.py` and `tm_1000.py` render the
anchors. The assembled tables of `cnt_matched_200.py` and `generative_120.py`
have none, and the endpoint-gap column of `cnt_matched_200.py` is written as
NaN. `app:ceiling` and `tab:app-primitives` do not use the generic rescorer;
`ceiling_120.py` and `primitives_120.py` write their own features in the layout
`score_only.py` reads.

## GPT-Image-1.5

- `matching_ablation/gpt_subset_numbers.json` in the original archive holds an
  earlier summary of the GPT rows (KID 0.0056 and 0.0093 for the two GPT
  variants, 0.0116 for Texture Mixer, 0.0185 for soft OT). It predates the
  rescoring under the canonical reference and the trace-corrected KID, and it is
  superseded. `evidence/gpt_pair_scores.csv` and `score_only.py` hold the final
  values.
- The ledger records dispatch times only. Per-call latency comes from the run
  manifests, joined on `request_signature` (`experiments/gpt_call_stats.py`).
  Six of the 240 scored outputs (three per series) come from the preview run and
  were reused unchanged; their latency is read from the preview manifest. The
  preview alone had a median latency of 35.93 s over 45 calls.
- The harness configuration lists 128x128 as the evaluation size and marks the
  resize method as unresolved. The scores use the paper's `at128` transform
  described in the README.
- Cost is not recorded in the ledger. Token usage per call is in the manifests,
  and `reports/FULL_RUN_REPORT.md` in the harness folder derives a list-price
  estimate from it.

## Coverage limits

- `tab:app-order`, `fig:app-epsilon`, `tab:app-repeat` and `fig:app-rho` each
  have a cached file in the archive (`compute_cost/order_dependence_n6.csv`,
  `paper_completion/eps_sweep.json`, `degradation_5_9/results/degradation.csv`,
  `paper_completion/rhostar_1000_sharp_exact.csv`) that `score_only.py` does not
  read. No script renders these from scratch.
- `experiments/vacher_50.py` follows the protocol of the source notebook. The
  number of reference images per category could not be recovered from it, so its
  FID values follow the same protocol without being a byte-exact replay of the
  archived values. The Vacher timing comes from a separate 20-pair run
  (`paper_completion/timing_n20.csv`).
- `tab:app-representation`, `tab:app-realism` and `tab:app-position` were
  printed by their notebooks and never saved to a file; `docs/INVENTORY.md`
  quotes the printed values. `tab:app-position` ran before a fix to CNT's input
  range.
- `experiments/anchor_mixtures.py` renders and measures `AnchorChangeA` and
  `AnchorChangeB`. No cached value exists to compare against.
- `fig:app-coding`: the raw outputs were not retained.
- `ceiling_120.py` writes `CeilRho` as NaN; `score_only.py` checks it against the
  cached `ceiling_summary.json`.

## Verification

- `score_only.py` reproduces 245 checks with 0 mismatches (`docs/CHECK.md`).
- Both Colab notebooks were run end to end on a T4 GPU. The CNT notebook passes
  its placement check at tolerance 0.01; the Texture Mixer notebook passes its
  pixel check with a maximum difference of 1 grey level.
- `cnt_1000.py` and `tm_1000.py` are exercised by the notebooks at n = 5. The full
  protocols, and the scripts `cnt_matched_200.py`, `generative_120.py`,
  `primitives_120.py`, `ceiling_120.py`, `rules_200.py`, `alignment.py`,
  `anchor_mixtures.py`, `vacher_50.py` and `runtime_120.py`, were ported from the
  original notebooks' cell source. The first five of these write the layout
  `score_only.py` reads; `alignment.py` and `runtime_120.py` match the schemas of
  the archive's `alignment_scores.csv` and `timing_120*.csv`.
