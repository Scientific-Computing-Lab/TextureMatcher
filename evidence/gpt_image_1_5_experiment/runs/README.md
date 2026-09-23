# Runs

Each run uses a UTC identifier and contains planned jobs, append-only
`manifest.jsonl`, logs, original PNGs, derived evaluation artifacts, and offline
contact sheets. Binary directories are ignored by Git; JSONL manifests are not.

`call_ledger.jsonl` at this level accounts for every dispatched Azure request
across run IDs and enforces the first-run cap.

