#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import random
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import openai
from common import (
    EXPERIMENT_ROOT,
    append_jsonl,
    atomic_write_bytes,
    git_state,
    load_config,
    load_pairs_manifest,
    load_prompt_manifest,
    read_jsonl,
    request_signature,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)
from diagnose_outputs import diagnose_image
from openai import AzureOpenAI
from PIL import Image
from validate_pairs import validate

FULL_APPROVAL_TOKEN = "AUTHORIZE_FULL_PAID_RUN_444"
PREVIEW_APPROVAL_TOKEN = "AUTHORIZE_EXPANDED_PREVIEW_45"


class CallCapReached(RuntimeError):
    pass


def sanitize(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value


def reserve_call(
    ledger_path: Path,
    job: dict,
    budget: str,
    cap: int,
    invocation_start_total: int,
    invocation_cap: int,
) -> int:
    import fcntl

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        records = [json.loads(line) for line in handle if line.strip()]
        used = sum(record.get("budget") == budget for record in records)
        if used >= cap:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise CallCapReached(f"Paid-call cap reached for {budget}: {used}/{cap}")
        invocation_used = len(records) - invocation_start_total
        if invocation_used >= invocation_cap:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise CallCapReached(f"Invocation call cap reached: {invocation_used}/{invocation_cap}")
        sequence = used + 1
        record = {
            "schema_version": 1,
            "dispatched_utc": utc_now(),
            "budget": budget,
            "budget_sequence": sequence,
            "run_id": job["run_id"],
            "series_id": job["series_id"],
            "k": job["k"],
            "request_signature": job["request_signature"],
        }
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return sequence


def verify_png(data: bytes, expected_size: tuple[int, int]) -> dict[str, Any]:
    if len(data) < 4096:
        raise ValueError(f"Decoded output is implausibly small: {len(data)} bytes")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            metadata = {"format": image.format, "dimensions": list(image.size), "mode": image.mode}
    except Exception as exc:
        raise ValueError(f"Output is not a decodable image: {exc}") from exc
    if metadata["format"] != "PNG":
        raise ValueError(f"Expected PNG output, got {metadata['format']}")
    if tuple(metadata["dimensions"]) != expected_size:
        raise ValueError(f"Expected output size {expected_size}, got {metadata['dimensions']}")
    return metadata


def all_successes() -> dict[str, dict]:
    successes: dict[str, dict] = {}
    for path in sorted((EXPERIMENT_ROOT / "runs").glob("*/manifest.jsonl")):
        for record in read_jsonl(path):
            if record.get("status") in {"success", "skipped_existing"}:
                successes[record["request_signature"]] = record
    return successes


def valid_existing(record: dict) -> Path | None:
    value = record.get("output_path")
    digest = record.get("output_sha256")
    if not value or not digest:
        return None
    path = resolve_experiment_path(value)
    if path.is_file() and sha256_file(path) == digest:
        return path
    return None


def materialize(source: Path, destination: Path) -> None:
    if destination.resolve() == source.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.copy.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def serialize_usage(response: Any) -> dict[str, Any] | None:
    """Convert the SDK's typed usage payload to stable JSON-compatible metadata."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        value = usage.model_dump(mode="json")
    elif isinstance(usage, dict):
        value = usage
    else:
        raise TypeError(f"Unsupported response usage type: {type(usage).__name__}")
    return value


def record_reuse(job: dict, source_record: dict, source: Path) -> dict:
    now = utc_now()
    commit, dirty = git_state()
    destination = resolve_experiment_path(job["output_path"])
    materialize(source, destination)
    aliases = []
    for alias in job.get("series_aliases", []):
        alias_path = resolve_experiment_path(alias["output_path"])
        materialize(source, alias_path)
        aliases.append({**alias, "sha256": sha256_file(alias_path)})
    record = {
        **{key: value for key, value in job.items() if key != "prompt"},
        "sdk_version": openai.__version__,
        "started_utc": now,
        "ended_utc": now,
        "latency_seconds": 0.0,
        "attempt_count": 0,
        "attempts": [],
        "status": "skipped_existing",
        "error_code": None,
        "error_message": None,
        "request_id": None,
        "revised_prompt": source_record.get("revised_prompt"),
        "usage": source_record.get("usage"),
        "output_dimensions": source_record.get("output_dimensions"),
        "output_mode": source_record.get("output_mode"),
        "output_byte_count": destination.stat().st_size,
        "output_sha256": sha256_file(destination),
        "diagnostics": source_record.get("diagnostics"),
        "materialized_aliases": aliases,
        "reused_from": {
            "run_id": source_record.get("run_id"),
            "series_id": source_record.get("series_id"),
            "request_id": source_record.get("request_id"),
        },
        "git_commit": commit,
        "dirty_worktree": dirty,
    }
    append_jsonl(EXPERIMENT_ROOT / "runs" / job["run_id"] / "manifest.jsonl", record)
    return record


def verify_job(job: dict, config: dict, pairs_by_id: dict, prompt_manifest: dict) -> None:
    if job["request_signature"] != request_signature(job):
        raise RuntimeError(f"k={job.get('k')}: request signature mismatch")
    pair = pairs_by_id.get(job["k"])
    if pair is None:
        raise RuntimeError(f"Unknown pair k={job['k']}")
    for key in ("sha256_A", "sha256_B", "path_A", "path_B", "category_A", "category_B"):
        if job[key] != pair[key]:
            raise RuntimeError(f"k={job['k']}: planned {key} differs from frozen pair manifest")
    prompt_item = prompt_manifest["prompts"].get(job["prompt_id"])
    if prompt_item is None or prompt_item["sha256"] != job["prompt_template_hash"]:
        raise RuntimeError(f"k={job['k']}: prompt template hash mismatch")
    if job["endpoint"] != config["azure"]["endpoint"]:
        raise RuntimeError("Job endpoint differs from config")
    if job["api_version"] != config["azure"]["api_version"]:
        raise RuntimeError("Job API version differs from config")
    if job["deployment"] != config["azure"]["deployment"]:
        raise RuntimeError("Job deployment differs from config")
    if job["input_order"] not in {"AB", "BA"}:
        raise RuntimeError("Input order must be AB or BA")


def error_details(exc: Exception, secret: str) -> tuple[int | None, str | None, str]:
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            code = error.get("code", code)
    message = sanitize(str(exc), secret)[:2000]
    return status, str(code) if code is not None else None, message


def execute_job(
    client: AzureOpenAI,
    job: dict,
    config: dict,
    secret: str,
    invocation_start_total: int,
    invocation_cap: int,
) -> tuple[dict, bool]:
    retry = config["retry"]
    data_root = resolve_experiment_path(config["data"]["root"])
    path_a = data_root / job["path_A"]
    path_b = data_root / job["path_B"]
    if sha256_file(path_a) != job["sha256_A"] or sha256_file(path_b) != job["sha256_B"]:
        raise RuntimeError(f"k={job['k']}: endpoint hash changed after manifest freeze")
    ordered_paths = [path_a, path_b] if job["input_order"] == "AB" else [path_b, path_a]
    output_path = resolve_experiment_path(job["output_path"])
    manifest_path = EXPERIMENT_ROOT / "runs" / job["run_id"] / "manifest.jsonl"
    ledger_path = EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl"
    commit, dirty = git_state()
    started = utc_now()
    start_clock = time.perf_counter()
    attempts = []
    request_id = None
    revised_prompt = None
    max_attempts = int(retry["max_attempts"])
    scope = job.get("execution_scope")
    if scope == "expanded_preview":
        budget = "approved_expanded_preview"
        cap = int(config["generation"]["expanded_preview_call_cap"])
    elif job["series_id"] in {"SMOKE", "PILOT"}:
        budget = "initial_pilot"
        cap = int(config["generation"]["paid_call_cap"])
    else:
        budget = "approved_full"
        cap = 444

    for attempt in range(1, max_attempts + 1):
        reserve_call(
            ledger_path,
            job,
            budget,
            cap,
            invocation_start_total,
            invocation_cap,
        )
        try:
            with ordered_paths[0].open("rb") as first, ordered_paths[1].open("rb") as second:
                raw = client.images.with_raw_response.edit(
                    model=job["deployment"],
                    image=[first, second],
                    prompt=job["prompt"],
                    n=job["n"],
                    size=job["size"],
                    quality=job["quality"],
                    input_fidelity=job["input_fidelity"],
                    output_format=job["output_format"],
                )
            response = raw.parse()
            usage = serialize_usage(response)
            headers = raw.headers
            request_id = (
                headers.get("x-request-id")
                or headers.get("apim-request-id")
                or getattr(response, "_request_id", None)
            )
            if not response.data or not response.data[0].b64_json:
                raise ValueError("Successful response contained no base64 image data")
            revised_prompt = getattr(response.data[0], "revised_prompt", None)
            try:
                image_bytes = base64.b64decode(response.data[0].b64_json, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(f"Invalid base64 image data: {exc}") from exc
            metadata = verify_png(image_bytes, tuple(map(int, job["size"].split("x"))))
            atomic_write_bytes(output_path, image_bytes)
            diagnostics = diagnose_image(output_path, tuple(map(int, job["size"].split("x"))))
            aliases = []
            for alias in job.get("series_aliases", []):
                alias_path = resolve_experiment_path(alias["output_path"])
                materialize(output_path, alias_path)
                aliases.append({**alias, "sha256": sha256_file(alias_path)})
            record = {
                **{key: value for key, value in job.items() if key != "prompt"},
                "sdk_version": openai.__version__,
                "started_utc": started,
                "ended_utc": utc_now(),
                "latency_seconds": round(time.perf_counter() - start_clock, 6),
                "attempt_count": attempt,
                "attempts": attempts + [{"attempt": attempt, "status": "success"}],
                "status": "success",
                "error_code": None,
                "error_message": None,
                "request_id": request_id,
                "revised_prompt": revised_prompt,
                "usage": usage,
                "output_dimensions": metadata["dimensions"],
                "output_mode": metadata["mode"],
                "output_byte_count": len(image_bytes),
                "output_sha256": sha256_file(output_path),
                "diagnostics": diagnostics,
                "materialized_aliases": aliases,
                "git_commit": commit,
                "dirty_worktree": dirty,
            }
            append_jsonl(manifest_path, record)
            compliant = not diagnostics["flags"]
            return record, compliant
        except Exception as exc:
            status, code, message = error_details(exc, secret)
            attempts.append(
                {"attempt": attempt, "status": "failed", "http_status": status, "error_code": code}
            )
            transient = status in set(retry["retry_http_statuses"])
            if transient and attempt < max_attempts:
                delay = min(
                    float(retry["max_delay_seconds"]),
                    float(retry["base_delay_seconds"]) * (2 ** (attempt - 1)),
                ) + random.SystemRandom().uniform(0, float(retry["jitter_seconds"]))
                time.sleep(delay)
                continue
            record = {
                **{key: value for key, value in job.items() if key != "prompt"},
                "sdk_version": openai.__version__,
                "started_utc": started,
                "ended_utc": utc_now(),
                "latency_seconds": round(time.perf_counter() - start_clock, 6),
                "attempt_count": attempt,
                "attempts": attempts,
                "status": "failed",
                "error_code": code or type(exc).__name__,
                "error_message": message,
                "http_status": status,
                "request_id": request_id,
                "revised_prompt": revised_prompt,
                "usage": None,
                "output_exists": False,
                "output_dimensions": None,
                "output_mode": None,
                "output_byte_count": None,
                "output_sha256": None,
                "git_commit": commit,
                "dirty_worktree": dirty,
            }
            append_jsonl(manifest_path, record)
            return record, False
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-paid-calls", action="store_true")
    parser.add_argument("--max-new-calls", type=int, required=True)
    parser.add_argument("--approval-file", type=Path)
    args = parser.parse_args()
    if not args.execute or not args.acknowledge_paid_calls:
        raise RuntimeError("Live execution requires --execute and --acknowledge-paid-calls")
    if args.max_new_calls <= 0:
        raise ValueError("--max-new-calls must be positive")

    config = load_config()
    secret_name = config["azure"]["api_key_env"]
    secret = os.environ.get(secret_name, "")
    if not secret:
        raise RuntimeError(f"Required environment variable is absent: {secret_name}")
    pairs = load_pairs_manifest(config)
    current_validation = validate(config)
    if current_validation["dataset_digest"] != pairs["dataset_digest"]:
        raise RuntimeError("Current 120-pair inputs differ from the frozen manifest")
    prompts = load_prompt_manifest(config)
    jobs = read_jsonl(args.jobs.resolve())
    if not jobs:
        raise ValueError("Job plan is empty")
    pairs_by_id = {pair["k"]: pair for pair in pairs["pairs"]}
    for job in jobs:
        verify_job(job, config, pairs_by_id, prompts)
    scopes = {job.get("execution_scope") for job in jobs}
    if len(scopes) != 1:
        raise RuntimeError(f"Job plan mixes execution scopes: {sorted(map(str, scopes))}")
    execution_scope = next(iter(scopes))
    is_series_plan = any(job["series_id"] in {"S1", "S2", "S3", "S4", "S5", "S6"} for job in jobs)
    if execution_scope == "expanded_preview":
        if args.approval_file is None or not args.approval_file.is_file():
            raise RuntimeError("Expanded-preview execution requires --approval-file")
        if args.approval_file.read_text(encoding="utf-8").strip() != PREVIEW_APPROVAL_TOKEN:
            raise RuntimeError("Expanded-preview approval token is absent or incorrect")
        if args.max_new_calls > int(config["generation"]["expanded_preview_call_cap"]):
            raise RuntimeError("Expanded-preview --max-new-calls exceeds the authorized cap")
    elif is_series_plan:
        if args.approval_file is None or not args.approval_file.is_file():
            raise RuntimeError("Full-series execution requires --approval-file")
        if args.approval_file.read_text(encoding="utf-8").strip() != FULL_APPROVAL_TOKEN:
            raise RuntimeError("Full-series approval token is absent or incorrect")
    elif args.max_new_calls > int(config["generation"]["paid_call_cap"]):
        raise RuntimeError("Pilot --max-new-calls exceeds the preregistered total cap")

    client = AzureOpenAI(
        api_key=secret,
        azure_endpoint=config["azure"]["endpoint"],
        api_version=config["azure"]["api_version"],
        timeout=float(config["generation"]["request_timeout_seconds"]),
    )
    successes = all_successes()
    current_manifest = EXPERIMENT_ROOT / "runs" / jobs[0]["run_id"] / "manifest.jsonl"
    event_log = EXPERIMENT_ROOT / "runs" / jobs[0]["run_id"] / "logs" / "events.jsonl"
    append_jsonl(
        event_log,
        {
            "utc": utc_now(),
            "event": "batch_start",
            "planned_jobs": len(jobs),
            "max_new_calls": args.max_new_calls,
        },
    )
    current_signatures = {
        record.get("request_signature") for record in read_jsonl(current_manifest)
    }
    dispatched_before = len(read_jsonl(EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl"))
    processed = 0
    for index, job in enumerate(jobs):
        existing = successes.get(job["request_signature"])
        existing_path = valid_existing(existing) if existing else None
        if existing_path:
            if job["request_signature"] not in current_signatures:
                existing = record_reuse(job, existing, existing_path)
                current_signatures.add(job["request_signature"])
            else:
                materialize(existing_path, resolve_experiment_path(job["output_path"]))
                for alias in job.get("series_aliases", []):
                    materialize(existing_path, resolve_experiment_path(alias["output_path"]))
            print(f"REUSE {index + 1}/{len(jobs)} k={job['k']} {job['series_id']}")
            append_jsonl(
                event_log,
                {
                    "utc": utc_now(),
                    "event": "reuse",
                    "request_signature": job["request_signature"],
                    "k": job["k"],
                },
            )
            if job["series_id"] == "SMOKE" and existing.get("diagnostics", {}).get("flags"):
                print("STOP reused smoke output failed diagnostics", file=sys.stderr)
                return 4
            continue
        dispatched_now = (
            len(read_jsonl(EXPERIMENT_ROOT / "runs" / "call_ledger.jsonl")) - dispatched_before
        )
        if dispatched_now >= args.max_new_calls:
            print(f"Stopped at explicit --max-new-calls={args.max_new_calls}")
            break
        print(f"CALL {index + 1}/{len(jobs)} k={job['k']} {job['series_id']} {job['prompt_id']}")
        append_jsonl(
            event_log,
            {
                "utc": utc_now(),
                "event": "dispatch_start",
                "request_signature": job["request_signature"],
                "k": job["k"],
            },
        )
        record, compliant = execute_job(
            client,
            job,
            config,
            secret,
            dispatched_before,
            args.max_new_calls,
        )
        processed += 1
        append_jsonl(
            event_log,
            {
                "utc": utc_now(),
                "event": "request_terminal",
                "request_signature": job["request_signature"],
                "k": job["k"],
                "status": record["status"],
                "error_code": record.get("error_code"),
            },
        )
        if record["status"] != "success":
            print(
                f"STOP {record.get('http_status')} {record['error_code']}: "
                f"{record['error_message']}",
                file=sys.stderr,
            )
            return 3
        if job["series_id"] == "SMOKE" and not compliant:
            print(
                f"STOP smoke output failed diagnostics: {record['diagnostics']['flags']}",
                file=sys.stderr,
            )
            return 4
    print(f"Completed/reused plan entries; newly successful logical requests: {processed}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CallCapReached as exc:
        print(f"CALL CAP: {exc}", file=sys.stderr)
        sys.exit(5)
    except Exception as exc:
        print(f"BATCH FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
