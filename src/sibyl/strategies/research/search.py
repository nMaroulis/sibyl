"""Price-independent, reproducible candidate plans for bounded strategy research.

Random search samples finite user-defined choices without replacement. Hash ranks
make a seed's draw order stable across Python RNG implementations. Every possible
combination is validated first; invalid unsampled choices are never hidden.
"""

import hashlib
import json
from itertools import product
from math import prod

SAMPLER = "sha256-rank-v1"
MAX_SAMPLES = 16
MAX_RANDOM_AXES = 4
MAX_RANDOM_VALUES = 8
MAX_SPACE = MAX_RANDOM_VALUES**MAX_RANDOM_AXES


def digest(value):
    """Fingerprint a JSON recipe or bounded candidate plan, including exact numeric choices."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def search_plan(parameters, grid, method="grid", *, sample_size=None, seed=None):
    """Validate the finite space and return selected candidates plus inspectable provenance.

    Sorted parameter names and the user's value order define one-based space
    indices. Candidate IDs follow evaluation order and retain their space index.
    Selection uses neither candle data nor scores; one plan is reused by all folds.
    """
    keys = sorted(grid)
    size = prod(len(grid[key]) for key in keys)
    if not 1 <= size <= MAX_SPACE:
        raise ValueError("The finite parameter space must contain 1–4,096 combinations.")
    space = []
    for values in product(*(grid[key] for key in keys)):
        overrides = dict(zip(keys, values, strict=True))
        fitted = type(parameters)(**(parameters.model_dump() | overrides))
        space.append({"overrides": overrides, "parameters": fitted})
    indices = list(range(len(space)))
    if method == "random":
        if (
            not grid
            or sample_size is None
            or seed is None
            or not 1 <= sample_size <= min(MAX_SAMPLES, len(space))
        ):
            raise ValueError(
                "Choose a random sample of 1–16 candidates, within the finite parameter space, and a seed."
            )
        indices.sort(key=lambda index: (hashlib.sha256(f"{SAMPLER}:{seed}:{index}".encode()).digest(), index))
        indices = indices[:sample_size]
    candidates = [{"id": i + 1, "space_index": index + 1, **space[index]} for i, index in enumerate(indices)]
    recipe = {
        "parameters": parameters.model_dump(),
        "axes": [{"key": key, "values": grid[key]} for key in keys],
    }
    evidence = {
        "method": "fixed" if not grid else method,
        "sampler": SAMPLER if method == "random" else "cartesian-v1",
        "seed": seed if method == "random" else None,
        "space_size": len(space),
        "evaluated_candidates": len(candidates),
        "coverage_pct": len(candidates) / len(space) * 100,
        "space_fingerprint": digest(recipe),
        "candidates": [{key: row[key] for key in ("id", "space_index", "overrides")} for row in candidates],
    }
    evidence["plan_fingerprint"] = digest(evidence)
    return candidates, evidence
