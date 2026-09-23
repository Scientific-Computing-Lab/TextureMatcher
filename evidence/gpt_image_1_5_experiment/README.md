# Azure GPT Image 1.5 midpoint benchmark

This directory is the self-contained experiment harness published beside the
repository's frozen input dataset. Live calls additionally require the
`AZURE_OPENAI_API_KEY` environment variable. It never uses OpenAI Platform
billing. The batch runner always sends A and B together, in that order, to
Azure `images.edit` and generates only the midpoint M.

Start with [`PILOT_GALLERY.md`](PILOT_GALLERY.md) to inspect the initial pilot
and every expanded S1–S5 preview result directly on GitHub.

## Required input layout

The benchmark is already present at the parent repository root:

```text
../pairs.csv
../A/
../B/
../preview/          # optional; never used as input
```

`pairs.csv` must have exactly the columns `k,category_A,category_B,file_A,file_B`
and exactly 120 rows. Source data are ignored by Git.

## Reproducible workflow

From this experiment directory:

```bash
uv sync --extra dev
uv run python scripts/freeze_prompts.py
uv run python scripts/validate_pairs.py
uv run python scripts/prepare_strata.py
# Review only untouched A/B images, fill data/strata_annotations.csv, then:
uv run python scripts/select_subsets.py
uv run python scripts/preflight.py
uv run python scripts/plan_matrix.py --phase pilot
```

The live runner requires explicit acknowledgement of the paid-call cap:

```bash
uv run python scripts/run_batch.py \
  --jobs runs/<run_id>/pilot_jobs.jsonl \
  --execute --acknowledge-paid-calls --max-new-calls 10
```

The runner refuses to proceed when the pair manifest, prompt hashes, subset
selection, endpoint/deployment configuration, or call ledger do not match the
frozen plan. Full-series job plans can be generated, but `run_batch.py` also
requires `--approval-file` containing the exact token documented in
`EXPERIMENT_PLAN.md`; no such approval file is created here.

## Core artifacts

- `EXPERIMENT_PLAN.md`: preregistration and scientific contract.
- `config.yaml`: sanitized execution configuration.
- `prompts/`: versioned prompt text plus frozen hashes.
- `data/pairs_manifest.json`: generated only after all 120 rows validate.
- `data/subsets.json`: generated only after source-only regime annotations.
- `runs/<run_id>/manifest.jsonl`: one terminal record per logical request.
- `runs/call_ledger.jsonl`: append-only accounting of every dispatched API call.
- `reports/`: smoke/pilot reports and machine-readable summaries.
- `human_study/`: protocol and static blinded-study generator.

Generated images are deliberately ignored by Git; manifests and reports are
not. Existing filenames are never accepted as proof of completion without a
matching successful manifest record and verified output hash.

The already completed pilot images and contact sheets are intentionally tracked
on the publication branch so they can be reviewed in GitHub. The ignore rules
apply to future runs.
