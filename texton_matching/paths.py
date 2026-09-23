"""Single source of truth for where the cached Tier 1 inputs live.

Every script resolves data through `resolve_data_root()`. By default that is
evidence/tier1/; set DATA_ROOT or pass --data-root to use another folder with
the same layout.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_data_root(explicit: str | os.PathLike | None = None) -> Path:
    """Resolve the folder holding the cached inputs of Tier 1.

    Priority: explicit argument, then the DATA_ROOT environment variable, then
    the packed inputs shipped in evidence/tier1/.
    """
    candidates = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env = os.environ.get("DATA_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parent.parent / "evidence" / "tier1")

    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(
        "Could not find the Tier 1 inputs. Pass --data-root or set DATA_ROOT. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


def pairs_dir(data_root: str | os.PathLike) -> Path:
    """Directory holding the 120-pair subset's `pairs.csv`.

    The folder is named `pairs_120/`; a `pairs_for_*` folder from an
    older archive layout is also accepted.
    """
    data_root = Path(data_root)
    preferred = data_root / "pairs_120"
    if (preferred / "pairs.csv").exists():
        return preferred
    for legacy in sorted(data_root.glob("pairs_for_*")):
        if (legacy / "pairs.csv").exists():
            return legacy
    return preferred
