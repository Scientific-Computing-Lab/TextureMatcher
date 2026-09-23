#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

from common import (
    EXPERIMENT_ROOT,
    atomic_write_json,
    atomic_write_text,
    load_config,
    load_pairs_manifest,
    load_prompt_manifest,
    request_signature,
    resolve_experiment_path,
    sha256_text,
    utc_now,
)


def load_subsets(config: dict, dataset_digest: str) -> dict:
    path = resolve_experiment_path(config["data"]["subsets"])
    if not path.exists():
        raise FileNotFoundError(f"Frozen subsets missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["pairs_dataset_digest"] != dataset_digest:
        raise RuntimeError("Subset file refers to a different pair-manifest digest")
    return data


def prompt_text(prompt_manifest: dict, prompt_id: str, t: float | None = None) -> tuple[str, str]:
    item = prompt_manifest["prompts"][prompt_id]
    template = resolve_experiment_path(item["path"]).read_text(encoding="utf-8").strip()
    rendered = template.format(t=t) if t is not None else template
    return rendered, sha256_text(rendered)


def make_job(
    *,
    config: dict,
    run_id: str,
    pair: dict,
    series_id: str,
    prompt_manifest: dict,
    prompt_id: str,
    order: str,
    replicate: int,
    quality: str,
    output_path: Path,
    t: float | None = None,
) -> dict:
    prompt, rendered_hash = prompt_text(prompt_manifest, prompt_id, t)
    azure = config["azure"]
    generation = config["generation"]
    job = {
        "schema_version": 1,
        "run_id": run_id,
        "series_id": series_id,
        "series_aliases": [],
        "prompt_id": prompt_id,
        "prompt_template_hash": prompt_manifest["prompts"][prompt_id]["sha256"],
        "prompt": prompt,
        "prompt_hash": rendered_hash,
        "t": t,
        "k": pair["k"],
        "category_A": pair["category_A"],
        "category_B": pair["category_B"],
        "file_A": pair["file_A"],
        "file_B": pair["file_B"],
        "path_A": pair["path_A"],
        "path_B": pair["path_B"],
        "sha256_A": pair["sha256_A"],
        "sha256_B": pair["sha256_B"],
        "input_order": order,
        "endpoint": azure["endpoint"],
        "api_version": azure["api_version"],
        "deployment": azure["deployment"],
        "n": int(generation["n"]),
        "size": generation["size"],
        "quality": quality,
        "input_fidelity": generation["input_fidelity"],
        "output_format": generation["output_format"],
        "replicate": replicate,
        "output_path": str(output_path.relative_to(EXPERIMENT_ROOT)),
    }
    job["request_signature"] = request_signature(job)
    return job


def output_name(k: str, repeated: bool = False, replicate: int = 1) -> str:
    return f"{k}_mid_r{replicate:02d}.png" if repeated else f"{k}_mid.png"


def pilot_jobs(
    config: dict, run_id: str, pairs_by_id: dict, subsets: dict, prompts: dict
) -> list[dict]:
    pilot = subsets["subsets"]["pilot_3"]
    pair_ids = [item["k"] for item in pilot]
    if len(pair_ids) != 3 or [item["regime"] for item in pilot] != [
        "ordinary",
        "periodic",
        "semantic",
    ]:
        raise RuntimeError("Pilot subset must be exactly ordinary, periodic, semantic")
    run_root = EXPERIMENT_ROOT / "runs" / run_id
    jobs = [
        make_job(
            config=config,
            run_id=run_id,
            pair=pairs_by_id[pair_ids[0]],
            series_id="SMOKE",
            prompt_manifest=prompts,
            prompt_id="P0_MINIMAL",
            order="AB",
            replicate=1,
            quality=config["generation"]["smoke_quality"],
            output_path=run_root / "images" / "SMOKE" / output_name(pair_ids[0], True, 1),
        )
    ]
    for pair_id in pair_ids:
        for prompt_id in ("P0_MINIMAL", "P1_PERCEPTUAL_SYMMETRIC", "P2_SOURCE_LAYOUT"):
            jobs.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pairs_by_id[pair_id],
                    series_id="PILOT",
                    prompt_manifest=prompts,
                    prompt_id=prompt_id,
                    order="AB",
                    replicate=1,
                    quality=config["generation"]["pilot_quality"],
                    output_path=run_root
                    / "images"
                    / "PILOT"
                    / prompt_id
                    / output_name(pair_id, True, 1),
                )
            )
    if len(jobs) != 10:
        raise AssertionError(f"Pilot plan must contain exactly 10 calls, got {len(jobs)}")
    return jobs


def full_jobs(
    config: dict, run_id: str, pairs_by_id: dict, subsets: dict, prompts: dict
) -> list[dict]:
    quality = config["generation"]["full_quality"]
    run_root = EXPERIMENT_ROOT / "runs" / run_id
    all_pairs = [pairs_by_id[k] for k in sorted(pairs_by_id)]
    s3_pairs = [pairs_by_id[item["k"]] for item in subsets["subsets"]["s3_24"]]
    s5_pairs = [pairs_by_id[item["k"]] for item in subsets["subsets"]["s5_12"]]
    candidates: list[dict] = []

    for pair in all_pairs:
        for series_id, prompt_id in (("S1", "P2_SOURCE_LAYOUT"), ("S2", "P1_PERCEPTUAL_SYMMETRIC")):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id=series_id,
                    prompt_manifest=prompts,
                    prompt_id=prompt_id,
                    order="AB",
                    replicate=1,
                    quality=quality,
                    output_path=run_root / "images" / series_id / output_name(pair["k"]),
                )
            )

    for pair in s3_pairs:
        for prompt_id in ("P0_MINIMAL", "P1_PERCEPTUAL_SYMMETRIC", "P2_SOURCE_LAYOUT"):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id="S3",
                    prompt_manifest=prompts,
                    prompt_id=prompt_id,
                    order="AB",
                    replicate=1,
                    quality=quality,
                    output_path=run_root
                    / "images"
                    / "S3"
                    / prompt_id
                    / output_name(pair["k"], True, 1),
                )
            )
        for order in ("AB", "BA"):
            for replicate in (1, 2):
                candidates.append(
                    make_job(
                        config=config,
                        run_id=run_id,
                        pair=pair,
                        series_id="S4",
                        prompt_manifest=prompts,
                        prompt_id="P1_PERCEPTUAL_SYMMETRIC",
                        order=order,
                        replicate=replicate,
                        quality=quality,
                        output_path=run_root
                        / "images"
                        / "S4"
                        / order
                        / output_name(pair["k"], True, replicate),
                    )
                )

    for pair in s5_pairs:
        for index, t in enumerate(config["series"]["S5"]["t_values"], 1):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id="S5",
                    prompt_manifest=prompts,
                    prompt_id="P3_PATH",
                    order="AB",
                    replicate=1,
                    quality=quality,
                    t=float(t),
                    output_path=run_root
                    / "images"
                    / "S5"
                    / f"t{index:02d}"
                    / output_name(pair["k"], True, 1),
                )
            )

    unique: OrderedDict[str, dict] = OrderedDict()
    for job in candidates:
        signature = job["request_signature"]
        if signature not in unique:
            unique[signature] = job
        else:
            unique[signature]["series_aliases"].append(
                {"series_id": job["series_id"], "output_path": job["output_path"]}
            )
    jobs = list(unique.values())
    if len(candidates) != 516 or len(jobs) != 444:
        raise AssertionError(
            f"Expected 516 nominal and 444 unique full cells, got {len(candidates)} and {len(jobs)}"
        )
    return jobs


def expanded_preview_jobs(
    config: dict, run_id: str, pairs_by_id: dict, subsets: dict, prompts: dict
) -> list[dict]:
    """Build the exact high-quality S1-S5 preview authorized after the pilot."""
    quality = config["generation"]["full_quality"]
    run_root = EXPERIMENT_ROOT / "runs" / run_id
    preview = subsets["subsets"]["pilot_3"]
    pair_ids = [item["k"] for item in preview]
    if len(pair_ids) != 3 or [item["regime"] for item in preview] != [
        "ordinary",
        "periodic",
        "semantic",
    ]:
        raise RuntimeError("Expanded preview requires the frozen three-regime pilot subset")
    preview_pairs = [pairs_by_id[k] for k in pair_ids]
    candidates: list[dict] = []

    for pair in preview_pairs:
        for series_id, prompt_id in (
            ("S1", "P2_SOURCE_LAYOUT"),
            ("S2", "P1_PERCEPTUAL_SYMMETRIC"),
        ):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id=series_id,
                    prompt_manifest=prompts,
                    prompt_id=prompt_id,
                    order="AB",
                    replicate=1,
                    quality=quality,
                    output_path=run_root / "images" / series_id / output_name(pair["k"]),
                )
            )

    for pair in preview_pairs:
        for prompt_id in ("P0_MINIMAL", "P1_PERCEPTUAL_SYMMETRIC", "P2_SOURCE_LAYOUT"):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id="S3",
                    prompt_manifest=prompts,
                    prompt_id=prompt_id,
                    order="AB",
                    replicate=1,
                    quality=quality,
                    output_path=run_root
                    / "images"
                    / "S3"
                    / prompt_id
                    / output_name(pair["k"], True, 1),
                )
            )
        for order in ("AB", "BA"):
            for replicate in (1, 2):
                candidates.append(
                    make_job(
                        config=config,
                        run_id=run_id,
                        pair=pair,
                        series_id="S4",
                        prompt_manifest=prompts,
                        prompt_id="P1_PERCEPTUAL_SYMMETRIC",
                        order=order,
                        replicate=replicate,
                        quality=quality,
                        output_path=run_root
                        / "images"
                        / "S4"
                        / order
                        / output_name(pair["k"], True, replicate),
                    )
                )

    for pair in preview_pairs:
        for index, t in enumerate(config["series"]["S5"]["t_values"], 1):
            candidates.append(
                make_job(
                    config=config,
                    run_id=run_id,
                    pair=pair,
                    series_id="S5",
                    prompt_manifest=prompts,
                    prompt_id="P3_PATH",
                    order="AB",
                    replicate=1,
                    quality=quality,
                    t=float(t),
                    output_path=run_root
                    / "images"
                    / "S5"
                    / f"t{index:02d}"
                    / output_name(pair["k"], True, 1),
                )
            )

    unique: OrderedDict[str, dict] = OrderedDict()
    for job in candidates:
        job["execution_scope"] = "expanded_preview"
        signature = job["request_signature"]
        if signature not in unique:
            unique[signature] = job
        else:
            unique[signature]["series_aliases"].append(
                {"series_id": job["series_id"], "output_path": job["output_path"]}
            )
    jobs = list(unique.values())
    if len(candidates) != 54 or len(jobs) != 45:
        raise AssertionError(
            "Expected 54 nominal and 45 unique expanded-preview cells, "
            f"got {len(candidates)} and {len(jobs)}"
        )
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "preview", "full"), required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    config = load_config()
    pairs = load_pairs_manifest(config)
    subsets = load_subsets(config, pairs["dataset_digest"])
    prompts = load_prompt_manifest(config)
    pairs_by_id = {pair["k"]: pair for pair in pairs["pairs"]}
    run_id = args.run_id or utc_now().replace(":", "").replace("-", "").replace(".", "")
    if args.phase == "pilot":
        jobs = pilot_jobs(config, run_id, pairs_by_id, subsets, prompts)
    elif args.phase == "preview":
        jobs = expanded_preview_jobs(config, run_id, pairs_by_id, subsets, prompts)
    else:
        jobs = full_jobs(config, run_id, pairs_by_id, subsets, prompts)
    run_root = EXPERIMENT_ROOT / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    jobs_path = run_root / f"{args.phase}_jobs.jsonl"
    atomic_write_text(jobs_path, "".join(json.dumps(job, sort_keys=True) + "\n" for job in jobs))
    summary = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "run_id": run_id,
        "phase": args.phase,
        "dataset_digest": pairs["dataset_digest"],
        "subsets_digest": subsets["subsets_digest"],
        "unique_request_count": len(jobs),
        "jobs_sha256": sha256_text(jobs_path.read_text(encoding="utf-8")),
        "authorized": args.phase == "preview",
        "authorization_basis": (
            "User explicitly authorized the 45-call three-pair expanded preview."
            if args.phase == "preview"
            else None
        ),
    }
    atomic_write_json(run_root / f"{args.phase}_plan.json", summary)
    print(f"Planned {len(jobs)} unique {args.phase} requests: {jobs_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PLANNING FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
