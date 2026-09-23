# Blinded endpoint-conditioned human-study protocol

Status: prepared but **not deployed and not authorized for data collection**.

## Design

The study uses 42 endpoint pairs, selected deterministically as 14 each from
the frozen ordinary, periodic, and semantic regimes. Each trial shows untouched
A and B above two anonymized candidate midpoints. Required methods are AAT,
Gaussian, Texture Mixer, GPT P1, GPT P2, pixel-linear, and position-linear.
Every unordered method pair appears for every endpoint pair (21 blocks per
pair). Candidate left/right order is balanced and randomized with seed 2026.
Endpoint display order is randomized only for comparisons in which reversing
the task is scientifically valid; P2/AAT directed trials retain A→B and carry a
`directed=true` flag.

Participants answer two separate forced-choice questions:

1. Which candidate is the better coherent midpoint for this specific A–B pair?
2. Which candidate looks more like one realistic, self-consistent texture
   rather than a blend or overlay?

No method names are shown. “Tie/uncertain” is recorded as an explicit third
response and is not silently split.

## Sampling, power, and burden

The preregistered target is 180 eligible participants, 30 scored trials plus 2
attention checks each, target power 0.90, and familywise alpha 0.05. Twelve
scored trials per participant are reserved for the primary AAT-versus-GPT-P2
contrast; 18 use the balanced incomplete block over the other method pairs.
The frozen assignment generator balances regime, endpoint pair, candidate side,
and exposure counts within these primary and secondary blocks. Before
collection, the power simulation must be run with a smallest effect of interest
of a 55:45 primary preference and clustered participant/pair variation;
collection must not begin if the fixed design does not achieve 0.90 simulated
power. Increasing sample size after outcomes are seen is prohibited.

## Exclusions and attention checks

Exclude a participant only for a preregistered reason: failed consent,
duplicate enrollment, less than 80% completed scored trials, median response
time below 1.5 seconds, or failure of both attention checks. One failed check is
flagged for sensitivity analysis but not excluded. Attention checks use obvious
unaltered-texture versus deliberately corrupted/overlaid controls and never use
a study method as the “wrong” answer. Report exclusions and sensitivity results.

## Analysis

Analyze the two questions separately. The primary contrast is AAT versus GPT
P2 on directed midpoint quality; secondary contrasts include AAT versus
Gaussian/Texture Mixer/pixel/position and GPT P1 versus GPT P2. Use a
mixed-effects logistic or Bradley–Terry model with participant and endpoint-pair
random effects, regime and method interactions, pair-bootstrap 95% intervals,
and Holm-adjusted secondary tests. Ties are modeled explicitly in the primary
analysis and resolved as 0.5 only in a declared sensitivity analysis. Report
effect sizes, raw counts, intervals, missingness, and all preregistered strata.

## Freeze and privacy

`build_human_study.py` verifies every source/candidate hash and writes a frozen
JSONL trial manifest plus static local HTML. The manifest, study code version,
and hashes are frozen before the first participant. The generated site contains
no model labels or API metadata. Deployment, participant recruitment, consent
language, compensation, and collection require separate authorization and any
applicable ethics review.
