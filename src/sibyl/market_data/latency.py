"""Fixed-width bounded histograms; percentiles are disclosed bucket upper bounds."""

import bisect
import json
import math

BOUNDS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)


def bucket(latency_ms):
    """Select one finite boundary or the explicit greater-than-30-second tail."""
    return bisect.bisect_left(BOUNDS_MS, latency_ms)


def distribution(documents, requests):
    """Aggregate retained counters without pretending legacy means contain percentile samples."""
    counts = [0] * (len(BOUNDS_MS) + 1)
    invalid = False
    for document in documents:
        try:
            values = json.loads(document)
            if not isinstance(values, dict):
                raise ValueError
            for key, value in values.items():
                if not key.isdigit() or int(key) >= len(counts) or type(value) is not int or value < 0:
                    raise ValueError
                counts[int(key)] += value
        except (ValueError, TypeError):
            invalid = True
    samples = sum(counts)
    invalid = invalid or samples > requests

    def percentile(fraction):
        if not samples or invalid:
            return None
        rank = math.ceil(samples * fraction)
        cumulative = 0
        for index, count in enumerate(counts):
            cumulative += count
            if cumulative >= rank:
                return BOUNDS_MS[index] if index < len(BOUNDS_MS) else None
        return None

    return {
        "status": "invalid"
        if invalid
        else "partial"
        if samples < requests
        else "observed"
        if samples
        else "unobserved",
        "samples": samples,
        "coverage_pct": round(samples / requests * 100, 2) if requests and not invalid else None,
        "p50_upper_ms": percentile(0.5),
        "p95_upper_ms": percentile(0.95),
        "overflow_samples": counts[-1],
        "overflow_above_ms": BOUNDS_MS[-1],
        "buckets": [
            {"upper_ms": bound, "samples": count}
            for bound, count in zip([*BOUNDS_MS, None], counts, strict=True)
        ],
        "method": "Fixed latency buckets. p50/p95 are upper bounds, not exact quantiles. Null with tail samples can mean above 30 seconds. Legacy reads without buckets are excluded.",
    }
