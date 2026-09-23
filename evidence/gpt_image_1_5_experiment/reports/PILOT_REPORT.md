# Pilot report

Status: **completed**. Reported UTC: 2026-09-01T19:00:29.395Z.

## Deployment and execution

- OpenAI Python SDK: 3.6.0.
- Multi-file `images.edit` declared: True.
- Azure client instantiated during local preflight: True.
- Endpoint: `AZURE_ENDPOINT_REDACTED`.
- API version/deployment: `2025-04-01-preview`, `gpt-image-1.5`.
- Secrets recorded: no.
- Paid API dispatches in this run: **10** (cap: 10).
- Successful logical requests: 10; failed logical requests: 0.
- Successful latency seconds: min 17.591053, median 20.099736999999998,
  p10 17.809426, p90 34.369981, max 62.556505.
- Output byte sizes: min 1475626, median 1937906.5, max 2276629.

## Preregistered pairs

0445 (ordinary: Irregular marbled and wrinkled material cues lack a dominant repeat); 0725 (periodic: Dominant mesh repetition is visible); 0656 (semantic: Recognizable flowers are visible)

## Contact sheets and compliance

Contact sheets: runs/pilot_20260901T185300Z/contact_sheets/SMOKE/P0_MINIMAL/0445_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P0_MINIMAL/0445_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P1_PERCEPTUAL_SYMMETRIC/0445_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P2_SOURCE_LAYOUT/0445_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P0_MINIMAL/0725_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P1_PERCEPTUAL_SYMMETRIC/0725_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P2_SOURCE_LAYOUT/0725_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P0_MINIMAL/0656_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P1_PERCEPTUAL_SYMMETRIC/0656_AB_r01.png, runs/pilot_20260901T185300Z/contact_sheets/PILOT/P2_SOURCE_LAYOUT/0656_AB_r01.png.
Automated diagnostics: 10 images checked;
0 flagged; 0
exact duplicate groups. Visual compliance review: All ten outputs are single edge-to-edge square textures with no visible text, labels, borders, panels, or endpoint reproductions inside M; P0, P1, and P2 therefore obey the basic output-format contract on this pilot.
Prompt observations: P0 produced coherent textures but sometimes weak endpoint evidence; P1 generally retained cues from both endpoints but the semantic pair showed faint object-like rose structure; P2 preserved the source flower layout most clearly on pair 0656, while pair 0725 was strongly target-mesh-like and source-layout compliance was not unequivocal. No prompt winner is inferred from three pairs.
These three pairs are prompt/compliance diagnostics only and are not used to
select a scientific winner.

## Proposed full run

S1 120 new; S2 120 new; S3 72 nominal/48 reused/24 new; S4 96 nominal/24
reused/72 new; S5 108 new; S6 zero. Total: **444 new paid requests** after the
pilot, with 72 exact high-quality cells reused.

Cost must be estimated from the actual Azure account/region/deployment meter or
billing export at approval time. Record timestamp/currency and reconcile the
manifest's actual usage; no public or guessed unit price is substituted.

## Approval gate / blocker

Pilot complete. Full execution remains prohibited without explicit series approval.
