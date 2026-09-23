from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]


def find_repo_root(start: Path) -> Path:
    """Return the nearest Git worktree, with the standalone workspace as fallback."""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return EXPERIMENT_ROOT.parents[1]


REPO_ROOT = find_repo_root(EXPERIMENT_ROOT)
CONFIG_PATH = EXPERIMENT_ROOT / "config.yaml"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_experiment_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (EXPERIMENT_ROOT / path).resolve()


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return config


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def atomic_save_png(path: Path, image: Image.Image) -> None:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    atomic_write_bytes(path, buffer.getvalue())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            records.append(value)
    return records


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(record) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_pairs_manifest(config: dict[str, Any]) -> dict[str, Any]:
    path = resolve_experiment_path(config["data"]["pair_manifest"])
    if not path.exists():
        raise FileNotFoundError(
            f"Frozen pair manifest is missing: {path}. Run validate_pairs.py first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt_manifest(config: dict[str, Any], verify: bool = True) -> dict[str, Any]:
    path = resolve_experiment_path(config["prompts"]["manifest"])
    if not path.exists():
        raise FileNotFoundError(f"Prompt manifest is missing: {path}. Run freeze_prompts.py.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if verify:
        for prompt_id, item in manifest["prompts"].items():
            prompt_path = resolve_experiment_path(item["path"])
            actual = sha256_file(prompt_path)
            if actual != item["sha256"]:
                raise RuntimeError(
                    f"Prompt {prompt_id} changed after freeze: "
                    f"expected {item['sha256']}, got {actual}"
                )
    return manifest


def git_state() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return commit, bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None, None


def request_signature(job: dict[str, Any]) -> str:
    keys = (
        "k",
        "sha256_A",
        "sha256_B",
        "input_order",
        "prompt_hash",
        "deployment",
        "endpoint",
        "api_version",
        "n",
        "size",
        "quality",
        "input_fidelity",
        "output_format",
        "replicate",
    )
    return sha256_text(canonical_json({key: job.get(key) for key in keys}))


def require_exact_keys(actual: Iterable[str], expected: Iterable[str], label: str) -> None:
    actual_set = set(actual)
    expected_set = set(expected)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        raise ValueError(f"{label}: missing columns {missing}; extra columns {extra}")
