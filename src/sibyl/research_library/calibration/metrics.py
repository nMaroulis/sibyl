"""Deterministic top-passage selection using fit labels only, with untouched validation."""

import math


def accepted(row, threshold):
    """Missing retrieval scores abstain; equal scores follow the same inclusive cutoff as search."""
    return row["similarity"] is not None and row["similarity"] >= threshold


def relevant(row):
    return row["passage_id"] is not None and row["passage_id"] in row["expected"]


def metrics(rows, threshold):
    """Report observed counts/rates, never probabilities of truth or future accuracy."""
    positives = sum(bool(row["expected"]) for row in rows)
    accept = sum(accepted(row, threshold) for row in rows)
    correct = sum(accepted(row, threshold) and relevant(row) for row in rows)
    return {
        "questions": len(rows),
        "answerable": positives,
        "no_source": len(rows) - positives,
        "accepted": accept,
        "correct_accepts": correct,
        "incorrect_accepts": accept - correct,
        "accepted_no_source": sum(accepted(row, threshold) and not row["expected"] for row in rows),
        "missed_answerable": positives - correct,
        "precision": correct / accept if accept else None,
        "answerable_coverage": correct / positives if positives else None,
    }


def calibrate(rows):
    """Choose the lowest cutoff above every incorrect fit match, maximizing safe fit coverage.

    Validation scores never influence the cutoff. A tied incorrect/correct score
    rejects both; a cutoff above one deliberately rejects every cosine score.
    The owner must separately review and activate an eligible report.
    """
    fit = [row for row in rows if row["partition"] == "fit"]
    bad = [row["similarity"] for row in fit if row["similarity"] is not None and not relevant(row)]
    threshold = math.nextafter(max(bad), math.inf) if bad else -1.0
    training = metrics(fit, threshold)
    validation = metrics([row for row in rows if row["partition"] == "validation"], threshold)
    return {
        "threshold": threshold,
        "fit": training,
        "validation": validation,
        "eligible": bool(
            training["correct_accepts"]
            and validation["correct_accepts"]
            and not validation["incorrect_accepts"]
        ),
        "rule": "top-one cosine >= threshold; retain only that passage",
        "note": "Owner-labeled retrieval evidence on this fixed corpus/index. Validation did not choose the cutoff. Zero observed errors on a small set is not a guarantee, calibrated answer confidence or factual verification. Broader representative evaluation remains necessary.",
    }
