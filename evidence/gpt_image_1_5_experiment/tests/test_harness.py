from __future__ import annotations

import csv
import sys
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import (  # noqa: E402
    find_repo_root,
    load_config,
    load_prompt_manifest,
    request_signature,
    sha256_file,
)
from diagnose_outputs import diagnose_image  # noqa: E402
from plan_matrix import expanded_preview_jobs, full_jobs, pilot_jobs  # noqa: E402
from run_batch import CallCapReached, reserve_call, serialize_usage  # noqa: E402
from validate_pairs import validate  # noqa: E402


def fake_pairs() -> list[dict]:
    return [
        {
            "k": f"{index:04d}",
            "category_A": f"a{index % 47}",
            "category_B": f"b{index % 47}",
            "file_A": f"{index:04d}_A.png",
            "file_B": f"{index:04d}_B.png",
            "path_A": f"A/{index:04d}_A.png",
            "path_B": f"B/{index:04d}_B.png",
            "sha256_A": f"a{index:063d}"[-64:],
            "sha256_B": f"b{index:063d}"[-64:],
        }
        for index in range(120)
    ]


def test_full_matrix_deduplicates_to_444(tmp_path: Path) -> None:
    config = load_config()
    prompts = load_prompt_manifest(config)
    pairs = fake_pairs()
    regimes = ("ordinary", "periodic", "semantic")
    s3 = [
        {"k": f"{regime_index * 8 + offset:04d}", "regime": regime}
        for regime_index, regime in enumerate(regimes)
        for offset in range(8)
    ]
    s5 = [
        {"k": f"{regime_index * 4 + offset:04d}", "regime": regime}
        for regime_index, regime in enumerate(regimes)
        for offset in range(4)
    ]
    subsets = {"subsets": {"s3_24": s3, "s5_12": s5}}
    jobs = full_jobs(config, "test", {pair["k"]: pair for pair in pairs}, subsets, prompts)
    assert len(jobs) == 444
    assert len({job["request_signature"] for job in jobs}) == 444
    assert sum(len(job["series_aliases"]) for job in jobs) == 72


def test_pilot_is_exactly_ten_calls() -> None:
    config = load_config()
    prompts = load_prompt_manifest(config)
    pairs = fake_pairs()
    subsets = {
        "subsets": {
            "pilot_3": [
                {"k": "0000", "regime": "ordinary"},
                {"k": "0001", "regime": "periodic"},
                {"k": "0002", "regime": "semantic"},
            ]
        }
    }
    jobs = pilot_jobs(config, "test", {pair["k"]: pair for pair in pairs}, subsets, prompts)
    assert len(jobs) == 10
    assert jobs[0]["series_id"] == "SMOKE"
    assert jobs[0]["quality"] == "low"
    assert all(job["quality"] == "medium" for job in jobs[1:])


def test_expanded_preview_is_exactly_45_high_quality_calls() -> None:
    config = load_config()
    prompts = load_prompt_manifest(config)
    pairs = fake_pairs()
    subsets = {
        "subsets": {
            "pilot_3": [
                {"k": "0000", "regime": "ordinary"},
                {"k": "0001", "regime": "periodic"},
                {"k": "0002", "regime": "semantic"},
            ]
        }
    }
    jobs = expanded_preview_jobs(
        config, "test", {pair["k"]: pair for pair in pairs}, subsets, prompts
    )
    assert len(jobs) == 45
    assert len({job["request_signature"] for job in jobs}) == 45
    assert sum(len(job["series_aliases"]) for job in jobs) == 9
    assert all(job["quality"] == "high" for job in jobs)
    assert all(job["execution_scope"] == "expanded_preview" for job in jobs)


def test_call_ledger_enforces_invocation_cap(tmp_path: Path) -> None:
    ledger = tmp_path / "call_ledger.jsonl"
    job = {"run_id": "r", "series_id": "PILOT", "k": "0000", "request_signature": "s"}
    reserve_call(ledger, job, "initial_pilot", 10, 0, 1)
    try:
        reserve_call(ledger, job, "initial_pilot", 10, 0, 1)
    except CallCapReached:
        pass
    else:
        raise AssertionError("Invocation cap was not enforced")


def test_request_signature_ignores_series_and_output() -> None:
    base = {
        "k": "0001",
        "sha256_A": "a",
        "sha256_B": "b",
        "input_order": "AB",
        "prompt_hash": "p",
        "deployment": "gpt-image-1.5",
        "endpoint": "https://example.invalid/",
        "api_version": "v",
        "n": 1,
        "size": "1024x1024",
        "quality": "high",
        "input_fidelity": "high",
        "output_format": "png",
        "replicate": 1,
        "series_id": "S1",
        "output_path": "first.png",
    }
    other = {**base, "series_id": "S3", "output_path": "second.png"}
    assert request_signature(base) == request_signature(other)


def test_validator_accepts_complete_fixture(tmp_path: Path) -> None:
    root = tmp_path / "frozen"
    a_dir = root / "A"
    b_dir = root / "B"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    rows = []
    for index in range(120):
        k = f"{index:04d}"
        file_a = f"{k}_A.png"
        file_b = f"{k}_B.png"
        Image.new("RGB", (256, 256), (index % 256, 20, 30)).save(a_dir / file_a)
        Image.new("RGB", (256, 256), (40, index % 256, 50)).save(b_dir / file_b)
        rows.append([k, f"cat{index % 10}", f"other{index % 11}", file_a, file_b])
    pairs_csv = root / "pairs.csv"
    with pairs_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["k", "category_A", "category_B", "file_A", "file_B"])
        writer.writerows(rows)
    config = load_config()
    config["data"] = {
        **config["data"],
        "root": str(root),
        "pairs_csv": str(pairs_csv),
        "a_dir": str(a_dir),
        "b_dir": str(b_dir),
    }
    result = validate(config)
    assert result["row_count"] == 120
    assert len(result["pairs"]) == 120
    assert result["pairs"][0]["sha256_A"] == sha256_file(a_dir / "0000_A.png")


def test_diagnostics_flags_uniform_image(tmp_path: Path) -> None:
    path = tmp_path / "blank.png"
    Image.new("RGB", (1024, 1024), "white").save(path)
    result = diagnose_image(path)
    assert result["decodable"]
    assert result["blank"]
    assert "blank" in result["flags"]


def test_diagnostics_are_json_serializable(tmp_path: Path) -> None:
    path = tmp_path / "seams.png"
    image = Image.new("RGB", (1024, 1024), "black")
    for x in range(500, 524):
        for y in range(1024):
            image.putpixel((x, y), (255, 255, 255))
    image.save(path)
    import json

    json.dumps(diagnose_image(path))


def test_prompt_manifest_has_exact_four_prompts() -> None:
    manifest = load_prompt_manifest(load_config())
    assert set(manifest["prompts"]) == {
        "P0_MINIMAL",
        "P1_PERCEPTUAL_SYMMETRIC",
        "P2_SOURCE_LAYOUT",
        "P3_PATH",
    }


def test_find_repo_root_uses_nearest_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "experiment" / "scripts"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    assert find_repo_root(nested) == repo


def test_serialize_usage_preserves_typed_payload() -> None:
    class Usage:
        def model_dump(self, *, mode: str) -> dict:
            assert mode == "json"
            return {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}

    class Response:
        usage = Usage()

    assert serialize_usage(Response()) == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
    }
