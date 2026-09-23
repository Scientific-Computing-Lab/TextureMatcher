# Expanded all-series preview report

Status: **completed successfully** on 2026-09-01 UTC. This report describes a
three-pair preview and is not a scientific comparison.

## Scope and execution

- Authorization: explicit user approval for at most 45 new paid calls.
- Frozen pairs: 0445 ordinary, 0725 periodic, and 0656 semantic.
- Settings: `gpt-image-1.5`, Azure API `2025-04-01-preview`, high quality,
  1024×1024 PNG, high input fidelity, serial execution.
- Matrix: 54 nominal S1–S5 cells; 9 exact cross-series reuses; 45 unique paid
  requests. S6 made no request.
- Outcome: 45 successes, 0 failures, 0 retries, and no revised prompts.
- Latency seconds: min 30.41, median 35.93, mean 36.04, p90 40.58, max 51.31.
- Output byte sizes: min 1,093,481; median 1,773,607; max 2,275,324.

## Integrity and visual review

All 45 manifest records and nine materialized aliases passed hash verification.
Automated diagnostics checked 54 output paths and flagged none for corruption,
blankness, near-uniform content, suspicious borders, or panel-like structure.
The six SHA-256 duplicate groups are exactly the declared S1/S2 outputs reused
under matching S3/S4 filenames.

The nine consolidated figures are under
`runs/preview_all_series_20260901/preview_figures/` and are embedded in
`PILOT_GALLERY.md`. Post-hoc visual observations are:

- Ordinary 0445: appearance/color changes are clearer than topology changes;
  S4 shows visible order and repeat variation; S5 retains a diamond-like
  interior structure and changes abruptly at B.
- Periodic 0725: outputs strongly favor the target mesh; S4 varies motif scale
  and density; S5 is structurally non-monotonic and mismatches B's background.
- Semantic 0656: roses persist in every midpoint and all nine generated path
  frames; P2 preserves the source object layout most strongly; the path changes
  abruptly from roses at `t=0.9` to the non-object B endpoint.

These observations are not hidden reasoning, preregistered thresholds, or a
claim that the foundation-model output is correct.

## Effect on a later full run

Exactly 24 of these high-quality request signatures also occur in the frozen
444-request full plan: six S1/S2 midpoint calls and 18 S5 calls for the two
pilot pairs that belong to the frozen S5 subset. If outputs and hashes remain
valid, resumability will reuse those 24 results, leaving at most 420 new paid
full-run requests. The full run remains unauthorized.
