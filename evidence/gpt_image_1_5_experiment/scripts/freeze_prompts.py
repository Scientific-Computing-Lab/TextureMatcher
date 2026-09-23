#!/usr/bin/env python3
from __future__ import annotations

import string
import sys

from common import (
    atomic_write_json,
    load_config,
    resolve_experiment_path,
    sha256_file,
    utc_now,
)


def main() -> int:
    config = load_config()
    output_path = resolve_experiment_path(config["prompts"]["manifest"])
    records = {}
    for prompt_id, relative_path in config["prompts"].items():
        if prompt_id == "manifest":
            continue
        path = resolve_experiment_path(relative_path)
        text = path.read_text(encoding="utf-8")
        fields = sorted(
            {
                field_name
                for _, field_name, _, _ in string.Formatter().parse(text)
                if field_name is not None
            }
        )
        expected_fields = ["t"] if prompt_id == "P3_PATH" else []
        if fields != expected_fields:
            raise ValueError(
                f"{prompt_id}: expected placeholders {expected_fields}, found {fields}"
            )
        required = ("reference image 1", "reference image 2", "output", "only")
        missing = [needle for needle in required if needle.lower() not in text.lower()]
        if missing:
            raise ValueError(f"{prompt_id}: missing required language: {missing}")
        records[prompt_id] = {
            "path": str(path.relative_to(path.parents[1])),
            "sha256": sha256_file(path),
            "byte_count": path.stat().st_size,
            "template_variables": fields,
        }

    proposed = {"schema_version": 1, "frozen_utc": utc_now(), "prompts": records}
    if output_path.exists():
        import json

        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("prompts") != records:
            raise RuntimeError(
                "Prompt bytes differ from the frozen manifest. Create a new versioned prompt file."
            )
        print(f"Prompt manifest verified: {output_path}")
        return 0

    atomic_write_json(output_path, proposed)
    print(f"Prompt manifest frozen: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
