# Human-study readiness

Status: **prepared, power-checked, and not deployed**.

The blinded endpoint-conditioned protocol and deterministic asset builder are
implemented. The prospective seed-2026 simulation estimates 0.9064 power for
180 eligible participants at the preregistered 55:45 smallest effect, exceeding
the 0.90 target. No participants have been recruited and no responses have been
collected.

The final frozen trial manifest and static preview cannot yet be generated
without inventing data. The repository is missing the required 120-pair
candidate exports for AAT, Gaussian, Texture Mixer, pixel-linear, and
position-linear baselines. Once those exact `{k}_mid.png` directories are
provided, `scripts/build_human_study.py` will verify all candidates, blind and
balance the comparisons, hash every asset, and create the local-only HTML
preview. GPT P1 and GPT P2 exports are produced by this run.

Deployment, recruitment, consent, compensation, and response collection still
require separate explicit authorization and any applicable ethics review.
