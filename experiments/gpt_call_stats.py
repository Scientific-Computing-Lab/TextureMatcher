#!/usr/bin/env python3
"""Latency and token statistics for the 240 GPT-Image-1.5 calls behind Table 3.

The two GPT rows of tab:generative are series S1 (prompt P2, "GPT directed")
and S2 (prompt P1, "GPT symmetric") of the shipped run: 120 pairs each. This
script joins the run manifests to the call ledger on `request_signature` and
writes evidence/gpt_call_summary.csv (one row per call), then prints median /
mean latency.

The ledger (runs/call_ledger.jsonl) records only when each paid call was
dispatched. Per-call latency and token usage are recorded in each run's
manifest.jsonl. Six of the 240 outputs (3 per series) were produced during the
earlier preview run and reused unchanged by the full run; their latency is
read from the preview manifest, matched by request signature.

Pure standard library; needs no GPU and no API access.

Usage:
    python experiments/gpt_call_stats.py
"""
import csv
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "evidence" / "gpt_image_1_5_experiment" / "runs"
OUT = Path(__file__).resolve().parent.parent / "evidence" / "gpt_call_summary.csv"


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def main():
    full = load(ROOT / "full_pending_approval_20260901" / "manifest.jsonl")
    preview = {r["request_signature"]: r for r in load(ROOT / "preview_all_series_20260901" / "manifest.jsonl")
               if r["status"] == "success"}
    ledger = {r["request_signature"]: r for r in load(ROOT / "call_ledger.jsonl")}

    rows = []
    for r in full:
        if r["series_id"] not in ("S1", "S2"):
            continue
        src, call = "full_run", r
        if r["status"] != "success":
            src, call = "preview_run_reused", preview[r["request_signature"]]
        usage = call.get("usage") or {}
        rows.append(dict(
            k=r["k"], series=r["series_id"], prompt_id=r["prompt_id"], quality=r["quality"],
            input_order=r["input_order"], produced_in=src,
            dispatched_utc=ledger[r["request_signature"]]["dispatched_utc"],
            latency_seconds=call["latency_seconds"], attempts=call["attempt_count"],
            input_tokens=usage.get("input_tokens", ""), output_tokens=usage.get("output_tokens", ""),
            output_sha256=call["output_sha256"],
        ))
    rows.sort(key=lambda d: (d["series"], d["k"]))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def summarize(name, sub):
        lat = sorted(d["latency_seconds"] for d in sub)
        print(f"{name:>10}: n={len(lat)} median={st.median(lat):.2f}s mean={st.mean(lat):.2f}s "
              f"p90={lat[int(0.9 * len(lat))]:.2f}s max={lat[-1]:.2f}s")

    summarize("S1+S2", rows)
    summarize("S1 (P2)", [d for d in rows if d["series"] == "S1"])
    summarize("S2 (P1)", [d for d in rows if d["series"] == "S2"])
    print(f"retries: {sum(d['attempts'] > 1 for d in rows)}; wrote {OUT}")


if __name__ == "__main__":
    main()
