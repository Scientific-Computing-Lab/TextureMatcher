# Preregistered experiment plan

Status: **preregistered and frozen before generation; the capped pilot,
expanded preview, and authorized full execution completed on 2026-09-02.**
Seed: 2026. Model outputs must never be used to
choose pairs, prompts, replicates, or reported outputs.

## Scientific questions and hypotheses

This experiment asks two related but distinct questions.

1. For the paper-aligned directed task, can a foundation image model preserve
   A's layout while moving local appearance halfway toward B? The preregistered
   descriptive hypothesis is that explicit source-layout instructions (P2)
   improve layout retention relative to a generic midpoint prompt, especially
   on stochastic textures, but may struggle with regular structures.
2. For the broader symmetric task, can the model synthesize a coherent natural
   midpoint that retains evidence of both endpoints? The preregistered
   hypothesis is that P1 improves coherence relative to P0, but that order
   effects will exceed the stochastic repeat floor for some pairs.

The hypotheses are not claims of correctness. `gpt-image-1.5` is a strong
foundation-model comparator/reference, not ground truth, semi-ground-truth, or
an oracle. Closeness to one generated sample does not prove a midpoint is
correct. A returned `revised_prompt` is recorded verbatim as service metadata;
any visual explanation is post-hoc analysis, not hidden model reasoning.

## Tasks and immutable prompts

- **P0_MINIMAL:** minimally specified symmetric midpoint control.
- **P1_PERCEPTUAL_SYMMETRIC:** coherent natural perceptual midpoint.
- **P2_SOURCE_LAYOUT:** directed A-layout/B-appearance midpoint, closest to AAT.
- **P3_PATH:** independently synthesized directed coordinate `t`.

Every prompt identifies reference image 1 and reference image 2 explicitly and
asks for M only, edge-to-edge. Quantitative endpoints are never model-redrawn;
A–M–B displays are assembled offline from untouched A/B files.

Prompt files are immutable and versioned. `prompts/manifest.json` freezes their
SHA-256 values. Any edit requires a new filename/version and a new experiment
run.

## Data freeze and predeclared subsets

The canonical join key is the four-digit `k` from the externally supplied
120-row `pairs.csv`. Before any paid request, `validate_pairs.py` must verify:

- exact columns and 120 rows; unique four-digit `k` values;
- cross-category rows and filename-to-`k` correspondence in both A and B;
- existence, readability, 256×256 dimensions, and allowed color mode;
- endpoint SHA-256 values and category counts.

The validator writes one atomic `data/pairs_manifest.json`. Generation refuses
to run if revalidation changes its digest.

Regime labels (`ordinary`, `periodic`, `semantic`) are assigned using only
`pairs.csv`, categories, and untouched source images. The annotator records a
short source-only rationale in `data/strata_annotations.csv`. The label file is
frozen before any model output is inspected. Within each regime, selection is
by ascending `SHA256("2026:<subset>:<k>")`, which makes these subsets exact and
auditable once the fixed pair IDs exist:

- pilot: one pair per regime (3 total), ordered ordinary, periodic, semantic;
- S3/S4: eight pairs per regime (24 total);
- S5: four pairs per regime (12 total);
- human study: fourteen pairs per regime (42 total).

The source dataset is frozen at upstream commit
`366d4e53631c2d610969b557028d41f0d843f7de`; its 120-row manifest digest is
`d2d26791b48a367063fb93dbc241d98089bcb94b19157195ef0b100771f4484c`.
The pilot IDs selected before generation are 0445 (ordinary), 0725 (periodic),
and 0656 (semantic). The complete deterministic subsets and source-only
rationales are frozen in `data/subsets.json` and `data/strata_annotations.csv`.

## Phase 1 and capped pilot

The paid-call ledger counts every dispatched HTTP request conservatively,
including failed or retried requests. The cap is 10 across the first run.

1. One P0 call on the ordinary pilot pair at low quality is the two-reference
   smoke handshake.
2. All 3×3 pair/prompt cells (P0, P1, P2) are then run at medium quality.
3. The low-quality smoke result differs in settings and is therefore not reused
   as a medium-quality cell. Total: 1 + 9 = **10 dispatched calls**. There is no
   spare repeat under this preregistration.

Execution is serial. Retry is limited to HTTP 429/5xx with bounded exponential
backoff and jitter. Authentication/authorization, missing deployment,
endpoint/API mismatch, invalid request, moderation, and user-input failures
stop without unchanged retries. The runner never changes endpoint, API version,
deployment, prompt, or number/order of images as a fallback.

## Full experiment matrix (completed after authorization)

After the initial 10-call pilot, the user explicitly authorized a separate
45-dispatch expanded preview on the same frozen three pairs. It exercises the
exact high-quality settings for S1-S5: 54 nominal cells, 9 exact reuses, and 45
unique requests. This preview remains descriptive and does not change the
predeclared full subsets, hypotheses, or analysis thresholds. S6 uses these
outputs only for source-stratified qualitative review and makes no API call.

All full-series calls use 1024×1024 PNG, high quality, high input fidelity, and
one output. Pilot medium/low outputs do not match and are not reused.

| Series | Design | Nominal cells | Reused high-quality cells | New paid requests |
|---|---:|---:|---:|---:|
| S1 | 120, P2, A→B, rep 1 | 120 | 0 | 120 |
| S2 | 120, P1, A→B, rep 1 | 120 | 0 | 120 |
| S3 | 24 × (P0,P1,P2), A→B | 72 | 48 from S1/S2 | 24 |
| S4 | 24 × 2 orders × 2 reps, P1 | 96 | 24 A→B rep 1 from S2 | 72 |
| S5 | 12 × 9 independent coordinates, P3 | 108 | 0 | 108 |
| S6 | analysis-only stratification | 0 | 0 | 0 |
| **Total after approval** | | **516** | **72** | **444** |

S1 and S2 remain separate in every table and claim because S1 approximates the
paper's directed source-layout contract while S2 asks a broader symmetric
natural-midpoint question. S4 predefines
`mean d(M_AB,M_BA) / mean within-order repeat distance`, separately in DINOv2
and LPIPS; values above 1 indicate order sensitivity beyond the repeat floor,
without implying a significance threshold. S5 uses independent calls at
`t=0.1,...,0.9`; original A/B are frames 0/10. It is prompt-controlled
synthesis, not a latent geodesic.

Full execution required explicit user approval after the pilot and a local
approval file containing exactly:

```text
AUTHORIZE_FULL_PAID_RUN_444
```

The approval token records scope only; it contains no secret.

Authorization was received on 2026-09-02. The expanded preview contains 24
successful requests whose full request signatures exactly match full-plan
jobs. Those outputs are reused without another paid call, leaving 420 expected
new requests and up to 24 dispatches of retry headroom under the original
444-dispatch authorization cap.

Execution completed with 420 new successful requests, 24 exact cross-run
reuses, zero failed logical requests, and zero API retries. The complete
444-record terminal manifest materializes all 516 logical S1–S5 outputs. S6
analysis uses the frozen strata and includes every output without selection.

## Output and reliability contract

Original 1024×1024 PNGs are preserved. S1 evaluator exports are exactly
`{k}_mid.png`; repeated/ablation artifacts use `{k}_mid_r{rep:02d}.png` in
separate directories. Writes are atomic. Each logical request has a stable
content signature over inputs, prompt hash, order, `t`, model/deployment,
API version, size, quality, fidelity, format, and replicate. Resume accepts a
result only when a successful manifest record and the output hash both match.

Each terminal manifest record contains the run/series/prompt identifiers and
hash, pair metadata/hashes/order, sanitized Azure/SDK settings, replicate,
timestamps, latency, attempts, status/error, request ID, revised prompt,
output metadata/hash, and Git state. Failures remain in the manifest and no
generated artifact is manually selected or beautified.

## Evaluation

All methods must join on the same 120 pair IDs and fixed DTD reference pool.
The published 1,000-pair numbers are not comparable to this 120-pair run.
Baseline outputs/reference lists are currently absent and no value may be
fabricated. Tooling prepares exact joins and deterministic derived images.

The available manuscript specifies 128×128 feature inputs but does not record
the resize kernel/color-handling details. `prepare_evaluation.py` therefore
fails closed while `evaluation.resize_method` is unresolved. It may be changed
only after recovering the original evaluator or an explicit prospective
protocol decision applied identically to all methods.

Planned metrics: KID with uncertainty; descriptive FID at n=120; Inception and
DINOv2 per-image realism; DINO endpoint balance; LPIPS/DINO path ratios,
monotonicity, step size, and path-linearity R². Pairwise comparisons use
seed-2026 stratified paired bootstrap confidence intervals, paired sign-flip
permutation tests, standardized paired effects, and Holm correction. Any
distance to a GPT output is secondary and labeled “distance to
foundation-model reference.” API latency/cost and local A100 runtime are
reported separately.

Before full-run metric computation, the endpoint/symmetry/path implementation
was operationally frozen to `facebook/dinov2-base` revision
`f9e44c814b77203eaa57a6bdbbd535f21ede1415` using cosine distance between
normalized CLS embeddings, plus LPIPS 0.1/AlexNet on RGB images resized to
256×256 with bicubic resampling. This choice was made without inspecting the
full-run outputs and is separate from the unresolved 128×128 paper evaluator
transform needed for comparable KID/FID and Inception results.

## Human evaluation

`human_study/PROTOCOL.md` preregisters a blinded endpoint-conditioned study and
`build_human_study.py` prepares a frozen trial manifest/static local preview.
No participant recruitment, collection, publishing, or deployment is
authorized. Two judgments remain separate: pair-specific coherent midpoint
quality and realistic self-consistent texture quality.

## Cost and service limitations

The cost procedure is: retrieve the account/region/deployment's current Azure
price or billing-meter export; record its retrieval timestamp and currency;
map low/medium/high image-edit requests and high-fidelity input accounting to
that meter; multiply by the manifest's actual successful/billable usage; and
reconcile against the Azure cost report. Public or guessed prices are never
substituted for unavailable account pricing. Quota is recorded from the actual
deployment/account before increasing concurrency above one.

There is no assumed seed control. Repeats are independent stochastic
replicates. Three pilot pairs cannot establish scientific superiority, and
visual inspection is limited to compliance/failure analysis under the fixed
plan.
