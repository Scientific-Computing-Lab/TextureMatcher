"""Single source of truth for where the results archive lives.

Every script in this package resolves data through `resolve_data_root()`
instead of hardcoding a Drive path. Set the DATA_ROOT environment variable,
or pass --data-root on the command line, to point at wherever the archive
has been unpacked.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_data_root(explicit: str | os.PathLike | None = None) -> Path:
    """Resolve the results-archive root.

    Priority: explicit argument > DATA_ROOT env var > ../data next to this
    package (the layout used during development, where data/ is a symlink
    into the archive) > ./data relative to the current working directory.
    """
    candidates = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env = os.environ.get("DATA_ROOT")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent
    candidates.append(here.parent.parent / "data")  # package/texton_matching/.. /.. /data
    candidates.append(Path.cwd() / "data")

    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(
        "Could not find the data archive. Set DATA_ROOT to the unpacked "
        "results archive, or pass --data-root explicitly. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


def pairs_dir(data_root: str | os.PathLike) -> Path:
    """Directory holding the 120-pair subset's `pairs.csv`.

    The hosted archive names it `pairs_120/`. Older local copies of the
    archive used a `pairs_for_*` directory name for the same folder; that
    layout is still accepted so Tier 1 runs against either.
    """
    data_root = Path(data_root)
    preferred = data_root / "pairs_120"
    if (preferred / "pairs.csv").exists():
        return preferred
    for legacy in sorted(data_root.glob("pairs_for_*")):
        if (legacy / "pairs.csv").exists():
            return legacy
    return preferred
