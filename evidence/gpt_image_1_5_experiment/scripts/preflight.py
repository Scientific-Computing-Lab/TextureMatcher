#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import os
import sys
from typing import get_type_hints

import openai
from common import (
    EXPERIMENT_ROOT,
    atomic_write_json,
    load_config,
    load_pairs_manifest,
    load_prompt_manifest,
    resolve_experiment_path,
    utc_now,
)
from openai import AzureOpenAI

EXPECTED_ENDPOINT = "AZURE_ENDPOINT_REDACTED"
EXPECTED_API_VERSION = "2025-04-01-preview"
EXPECTED_DEPLOYMENT = "gpt-image-1.5"


def main() -> int:
    config = load_config()
    azure = config["azure"]
    if azure["endpoint"] != EXPECTED_ENDPOINT:
        raise ValueError("Configured endpoint does not match the preregistered Azure endpoint")
    if azure["api_version"] != EXPECTED_API_VERSION:
        raise ValueError("Configured API version does not match the preregistration")
    if azure["deployment"] != EXPECTED_DEPLOYMENT:
        raise ValueError("Configured deployment does not match the preregistration")

    key_name = azure["api_key_env"]
    key_present = bool(os.environ.get(key_name))
    edit_signature = inspect.signature(openai.resources.images.Images.edit)
    parameters = edit_signature.parameters
    required_parameters = {"image", "prompt", "model", "input_fidelity", "output_format"}
    missing_parameters = sorted(required_parameters - set(parameters))
    try:
        hints = get_type_hints(openai.resources.images.Images.edit)
    except Exception:
        hints = {}
    image_annotation = str(hints.get("image", parameters["image"].annotation))
    multiple_inputs_declared = any(
        token in image_annotation for token in ("Sequence", "List", "list")
    )

    client_instantiated = False
    if key_present:
        AzureOpenAI(
            api_key=os.environ[key_name],
            azure_endpoint=azure["endpoint"],
            api_version=azure["api_version"],
            timeout=float(config["generation"]["request_timeout_seconds"]),
        )
        client_instantiated = True

    missing_prerequisites = []
    try:
        load_prompt_manifest(config)
    except Exception as exc:
        missing_prerequisites.append(str(exc))
    try:
        load_pairs_manifest(config)
    except Exception as exc:
        missing_prerequisites.append(str(exc))
    subsets = resolve_experiment_path(config["data"]["subsets"])
    if not subsets.exists():
        missing_prerequisites.append(f"Frozen subsets missing: {subsets}")
    if not key_present:
        missing_prerequisites.append(f"Environment variable {key_name} is not set")
    if missing_parameters:
        missing_prerequisites.append(f"SDK images.edit missing parameters: {missing_parameters}")
    if not multiple_inputs_declared:
        missing_prerequisites.append(
            f"SDK image annotation does not declare a multi-file sequence: {image_annotation}"
        )

    report = {
        "schema_version": 1,
        "checked_utc": utc_now(),
        "status": "ready" if not missing_prerequisites else "blocked",
        "key_variable": key_name,
        "key_present": key_present,
        "key_value_recorded": False,
        "endpoint": azure["endpoint"],
        "api_version": azure["api_version"],
        "deployment": azure["deployment"],
        "openai_sdk_version": openai.__version__,
        "images_edit_parameters": sorted(parameters),
        "images_edit_image_annotation": image_annotation,
        "multiple_inputs_declared": multiple_inputs_declared,
        "client_instantiated": client_instantiated,
        "network_or_paid_call_made": False,
        "missing_prerequisites": missing_prerequisites,
    }
    output = EXPERIMENT_ROOT / "reports" / "preflight.json"
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PREFLIGHT FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
