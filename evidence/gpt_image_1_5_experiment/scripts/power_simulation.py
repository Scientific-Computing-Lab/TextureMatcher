#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from common import EXPERIMENT_ROOT, atomic_write_json, load_config, utc_now


def logit(probability: float) -> float:
    return math.log(probability / (1 - probability))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=EXPERIMENT_ROOT / "human_study" / "POWER_REPORT.json",
    )
    args = parser.parse_args()
    config = load_config()["human_study"]
    seed = int(config["seed"])
    simulations = int(config["power_simulations"])
    participants = int(config["target_participants"])
    trials_per_participant = int(config["primary_trials_per_participant"])
    pair_count = int(config["endpoint_pairs"])
    true_preference = float(config["smallest_effect_preference"])
    participant_sd = float(config["participant_logit_sd"])
    pair_sd = float(config["pair_logit_sd"])
    alpha = float(config["alpha"])
    if alpha != 0.05:
        raise ValueError("This fixed simulation currently implements the two-sided 0.05 threshold")

    rng = np.random.default_rng(seed)
    assignment = np.empty((participants, trials_per_participant), dtype=np.int64)
    for participant in range(participants):
        assignment[participant] = rng.choice(pair_count, size=trials_per_participant, replace=False)
    significant = 0
    estimates = np.empty(simulations, dtype=np.float64)
    for simulation in range(simulations):
        participant_effect = rng.normal(0, participant_sd, size=participants)
        pair_effect = rng.normal(0, pair_sd, size=pair_count)
        successes = np.zeros(pair_count, dtype=np.float64)
        counts = np.zeros(pair_count, dtype=np.float64)
        for participant in range(participants):
            chosen = assignment[participant]
            eta = logit(true_preference) + participant_effect[participant] + pair_effect[chosen]
            probability = 1 / (1 + np.exp(-eta))
            outcomes = rng.binomial(1, probability)
            np.add.at(successes, chosen, outcomes)
            np.add.at(counts, chosen, 1)
        pair_preferences = successes[counts > 0] / counts[counts > 0]
        estimate = float(pair_preferences.mean())
        estimates[simulation] = estimate
        standard_error = float(pair_preferences.std(ddof=1) / math.sqrt(len(pair_preferences)))
        if standard_error > 0 and abs(estimate - 0.5) / standard_error > 1.959964:
            significant += 1
    power = significant / simulations
    result = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "seed": seed,
        "simulations": simulations,
        "test": "two-sided pair-clustered normal approximation at alpha 0.05",
        "smallest_effect_preference": true_preference,
        "participant_count": participants,
        "primary_trials_per_participant": trials_per_participant,
        "endpoint_pair_count": pair_count,
        "participant_logit_sd": participant_sd,
        "pair_logit_sd": pair_sd,
        "estimated_power": power,
        "target_power": float(config["target_power"]),
        "passes_target": power >= float(config["target_power"]),
        "mean_estimated_preference": float(estimates.mean()),
        "preference_estimate_95_range": [
            float(np.percentile(estimates, 2.5)),
            float(np.percentile(estimates, 97.5)),
        ],
        "limitations": [
            "Prospective simulation; assumptions are not estimated from study outcomes.",
            "Final analysis uses a mixed-effects/Bradley-Terry model; this is a "
            "conservative design check rather than an exact model-based power proof.",
        ],
    }
    atomic_write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0 if result["passes_target"] else 2


if __name__ == "__main__":
    sys.exit(main())
