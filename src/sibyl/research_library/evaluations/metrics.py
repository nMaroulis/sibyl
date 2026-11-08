"""Binary relevance metrics at a fixed cutoff against explicit human judgments."""

import math


def score(retrieved, expected, k):
    """Precision divides by k, recall by all gold passages; an empty result scores zero."""
    gold = set(expected)
    hits = [index + 1 for index, identity in enumerate(retrieved[:k]) if identity in gold]
    dcg = sum(1 / math.log2(rank + 1) for rank in hits)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(gold)) + 1))
    return {
        "precision": len(hits) / k,
        "recall": len(hits) / len(gold),
        "reciprocal_rank": 1 / hits[0] if hits else 0,
        "ndcg": dcg / ideal,
        "hit": int(bool(hits)),
    }
