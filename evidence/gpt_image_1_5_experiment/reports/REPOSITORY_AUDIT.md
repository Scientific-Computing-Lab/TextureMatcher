# Repository and data audit

Audit date: 2026-09-01 UTC.

- The assigned workspace `<workspace>` was empty and
  was not a Git repository at the start. No project-level `AGENTS.md`, README,
  package metadata, script, configuration, or `pairs.csv` existed there.
- The separate paper repository `<paper-repo>` was clean on
  branch `main`. Its artifact statement says executable experiments, frozen
  pair manifests, baseline logs, and generated outputs were not supplied. It
  was inspected read-only and was not modified.
- The user-supplied external-evaluation repository
  `CODE_URL`
  was inspected at commit
  `366d4e53631c2d610969b557028d41f0d843f7de`. Its `pairs.csv`, `A/`, and `B/`
  were copied without modification into the experiment's ignored data area;
  the source and copied CSV SHA-256 both equal
  `7c061cff9dfc4df248e8c44e4b6653f19b8addab1ed250bfa75ca7351f7b18e9`.
- All 120 rows passed validation before generation: unique four-digit `k`,
  A/B filename correspondence, cross-category pairing, file existence,
  readability, RGB mode, and exact 256×256 dimensions. Per-file SHA-256 values
  and category counts are frozen in `data/pairs_manifest.json`; dataset digest:
  `d2d26791b48a367063fb93dbc241d98089bcb94b19157195ef0b100771f4484c`.
- Source-only regime annotations and deterministic seed-2026 selections were
  frozen before viewing any generated result. The pilot is 0445 ordinary, 0725
  periodic, and 0656 semantic.
- Neither requested global Azure helper path exists; a broader search under
  `.codex` also found no `azure_imagegen.py`. The project-local runner therefore
  implements the required Azure client behavior without changing global skills.
- `AZURE_OPENAI_API_KEY` was present. Its value was never printed or written.
  OpenAI Python SDK 3.6.0 declares multi-file `images.edit`, `input_fidelity`,
  and `output_format`; the required Azure client instantiated successfully.
- The workspace itself has no Git history, so manifest `git_commit` and
  `dirty_worktree` fields are explicitly null; the upstream data commit and all
  input, prompt, job-plan, and output hashes remain recorded.
- No Azure CLI/account configuration was available, so account-specific price
  and quota values could not be retrieved. The cost procedure is frozen, but a
  dollar estimate remains blocked on the account meter or billing export.
- The paper prose specifies 128×128 evaluation but the exact resize kernel and
  color pipeline, fixed DTD reference pool, and method outputs are absent.
  Evaluation therefore remains fail-closed until those artifacts are supplied.
