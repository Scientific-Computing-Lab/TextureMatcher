# Full GPT Image 1.5 run report

Generated: 2026-09-02T10:46:16.732Z. Run: `full_pending_approval_20260901`.

## Completion

- Nominal S1–S5 cells: **516**.
- Unique request signatures: **444**.
- Reused exact high-quality preview signatures: **24**.
- New successful paid requests: **420**.
- Paid dispatches including retries: **420**.
- Failed logical requests: **0**.
- Missing usage payloads among new successes: **1**.
- Unexpected duplicate primary-output hashes: **0**.

| Series | Completed logical cells |
|---|---:|
| S1 | 120 |
| S2 | 120 |
| S3 | 72 |
| S4 | 96 |
| S5 | 108 |

## Service measurements and cost

| Series | Paid | Reused | Serial time | Billable tokens | Data Zone cost |
|---|---:|---:|---:|---:|---:|
| S1 | 117 | 3 | 75.4 min | 1,571,036 | $26.65 |
| S2 | 117 | 3 | 75.9 min | 1,571,693 | $26.65 |
| S3 | 24 | 0 | 15.9 min | 318,815 | $5.45 |
| S4 | 72 | 0 | 46.7 min | 963,565 | $16.37 |
| S5 | 90 | 18 | 58.4 min | 1,207,387 | $20.50 |

- Serial API time: **4.54 hours**; median
  **38.49s**, p90 **43.52s**,
  maximum **75.51s**.
- New output bytes: **0.72 GiB**.
- Billable token estimate: **5,632,496 total**;
  3,653,200 input-image,
  105,455 input-text,
  1,747,200 output-image, and
  126,641 output-text. This uses actual
  service usage except for 1 locally recovered response(s),
  imputed component-wise from the median for the same frozen prompt.
- Azure Data Zone retail estimate: **$95.62 USD**.
- Azure Global Standard retail equivalent: **$86.93 USD**.
- Local DINOv2/LPIPS evaluation: **53.11s** on
  **NVIDIA GeForce RTX 3090**; this is reported separately from API latency and
  is not comparable to the paper's local A100 method runtime.

These estimates use the frozen Azure retail meters in `config.yaml`; private
discounts, taxes, and local evaluation compute are excluded.

## Endpoint-conditioned metrics

The midpoint coordinate is `d(M,A)/(d(M,A)+d(M,B))`; 0.5 is balanced. Balance
error is its absolute deviation from 0.5. These are descriptive distances, not
ground-truth correctness scores.

| Method | Space | Stratum | n | Mean coordinate | Mean balance error |
|---|---|---|---:|---:|---:|
| GPT_P0 | DINOv2 | all | 24 | 0.4638 | 0.1056 |
| GPT_P0 | DINOv2 | ordinary | 8 | 0.4427 | 0.1080 |
| GPT_P0 | DINOv2 | periodic | 8 | 0.4996 | 0.1080 |
| GPT_P0 | DINOv2 | semantic | 8 | 0.4492 | 0.1007 |
| GPT_P0 | LPIPS | all | 24 | 0.4938 | 0.0560 |
| GPT_P0 | LPIPS | ordinary | 8 | 0.5069 | 0.0428 |
| GPT_P0 | LPIPS | periodic | 8 | 0.4844 | 0.0601 |
| GPT_P0 | LPIPS | semantic | 8 | 0.4902 | 0.0652 |
| GPT_P1 | DINOv2 | all | 120 | 0.4905 | 0.1632 |
| GPT_P1 | DINOv2 | ordinary | 14 | 0.4571 | 0.1577 |
| GPT_P1 | DINOv2 | periodic | 30 | 0.4921 | 0.1886 |
| GPT_P1 | DINOv2 | semantic | 76 | 0.4961 | 0.1542 |
| GPT_P1 | LPIPS | all | 120 | 0.5104 | 0.0630 |
| GPT_P1 | LPIPS | ordinary | 14 | 0.5095 | 0.0490 |
| GPT_P1 | LPIPS | periodic | 30 | 0.5031 | 0.0753 |
| GPT_P1 | LPIPS | semantic | 76 | 0.5134 | 0.0607 |
| GPT_P2 | DINOv2 | all | 120 | 0.3551 | 0.1854 |
| GPT_P2 | DINOv2 | ordinary | 14 | 0.3676 | 0.1462 |
| GPT_P2 | DINOv2 | periodic | 30 | 0.3664 | 0.1786 |
| GPT_P2 | DINOv2 | semantic | 76 | 0.3483 | 0.1953 |
| GPT_P2 | LPIPS | all | 120 | 0.4753 | 0.0782 |
| GPT_P2 | LPIPS | ordinary | 14 | 0.4813 | 0.0604 |
| GPT_P2 | LPIPS | periodic | 30 | 0.4606 | 0.1041 |
| GPT_P2 | LPIPS | semantic | 76 | 0.4799 | 0.0712 |

Paired values below are P2 minus P1 absolute balance error, so negative favors
P2 only for this descriptive balance criterion. They do not establish
perceptual correctness.

| Metric | n | Mean paired difference | Stratified bootstrap 95% CI | dz | Holm p |
|---|---:|---:|---:|---:|---:|
| DINOv2_midpoint_balance | 120 | 0.0222 | [0.0028, 0.0422] | 0.1983 | 0.03039 |
| LPIPS_midpoint_balance | 120 | 0.0152 | [0.0051, 0.0251] | 0.2676 | 0.0085 |

Both observed differences are positive: P1 is closer to symmetric endpoint
balance in these feature spaces. P2's stronger source bias is consistent with
its different directed source-layout contract, so this is not a method ranking.

## Prompt, symmetry, and path diagnostics

S3 distances are means over the frozen 24-pair subset. Larger values mean the
prompt variants produced more perceptually separated samples.

| Space | n | P0–P1 | P0–P2 | P1–P2 |
|---|---:|---:|---:|---:|
| DINOv2 | 24 | 0.2310 | 0.2901 | 0.3455 |
| LPIPS | 24 | 0.3884 | 0.4042 | 0.4470 |

The preregistered S4 ratio is mean between-order distance divided by mean
within-order repeat distance. A value near one means order effects are no
larger than the stochastic repeat floor.

| Space | n | Between order | Within repeat | Ratio | Bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|
| DINOv2 | 24 | 0.2472 | 0.1829 | 1.3513 | [1.2096, 1.5577] |
| LPIPS | 24 | 0.4026 | 0.3660 | 1.1001 | [1.0473, 1.1584] |

S5 values below are means over the frozen 12-pair path subset. Monotonicity and
R² are descriptive prompt-control measures, not evidence of a latent geodesic.

| Space | n | Midpoint balance | Coordinate monotonicity | Linearity R² | Step CV |
|---|---:|---:|---:|---:|---:|
| DINOv2 | 12 | 0.1782 | 0.6333 | 0.5192 | 0.8646 |
| LPIPS | 12 | 0.0668 | 0.6833 | 0.5779 | 0.4187 |

All pair-level values are stored beside the raw metric CSVs under
`runs/full_pending_approval_20260901/evaluation/perceptual/`.

## S6 scope and blockers

The source-only frozen strata are used below; flags are conservative automated
review cues and flagged outputs remain in every analysis.

| Series | Stratum | n | Any flag | Blank | Uniform | Border | Panel-like |
|---|---|---:|---:|---:|---:|---:|---:|
| S1 | ordinary | 14 | 0 | 0 | 0 | 0 | 0 |
| S1 | periodic | 30 | 0 | 0 | 0 | 0 | 0 |
| S1 | semantic | 76 | 0 | 0 | 0 | 0 | 0 |
| S2 | ordinary | 14 | 0 | 0 | 0 | 0 | 0 |
| S2 | periodic | 30 | 1 | 0 | 0 | 0 | 1 |
| S2 | semantic | 76 | 2 | 0 | 0 | 0 | 2 |
| S3 | ordinary | 24 | 0 | 0 | 0 | 0 | 0 |
| S3 | periodic | 24 | 1 | 0 | 0 | 0 | 1 |
| S3 | semantic | 24 | 1 | 0 | 0 | 0 | 1 |
| S4 | ordinary | 32 | 0 | 0 | 0 | 0 | 0 |
| S4 | periodic | 32 | 0 | 0 | 0 | 0 | 0 |
| S4 | semantic | 32 | 3 | 0 | 0 | 0 | 3 |
| S5 | ordinary | 36 | 0 | 0 | 0 | 0 | 0 |
| S5 | periodic | 36 | 0 | 0 | 0 | 0 | 0 |
| S5 | semantic | 36 | 0 | 0 | 0 | 0 | 0 |

Automated output diagnostics are stratified by the frozen source-only regime
labels in `FULL_RUN_REPORT.json`. The post-hoc disposition of all six flags is
recorded in `reports/VISUAL_QC.md`; every flagged output remains included.
KID/FID, cross-method paired tests, and the
complete blinded human-study trial build were not fabricated because the
repository does not contain the required baseline outputs, fixed DTD reference
manifest, or recovered 128x128 evaluator transform. The human-study protocol
and power analysis remain ready but undeployed.
