"""Narrow evidence contracts, not an LLM judge or a general truth/quality score.

Checks inspect only native EvaluationSample outputs and terminal ToolEvidence.
They neither execute tools nor rewrite an answer or reconstruct native events.
"""

import json
import re
from dataclasses import asdict

from protolink import EvaluationCase, EvaluationReport, EvaluationSample, EvaluationScore


def observations(sample):
    """Use successful JSON-visible native receipts, including owned specialist consultations."""
    return (
        [
            item
            for item in sample.report.tool_evidence
            if item.outcome == "completed" and not item.result_omitted
        ]
        if sample.report
        else []
    )


_MISSING = object()


def value_at(data, path):
    """Read a declared dotted evidence field without evaluating expressions."""
    for part in path.split("."):
        if isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        elif isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return _MISSING
    return data


def matches(item, rule):
    """Match the actual tool owner/name and declared argument/result field expectations."""
    return (
        item.agent_name == "sibyl-" + rule["agent"]
        and item.tool_name == rule["tool"]
        and all(value_at(item.arguments, path) == value for path, value in rule.get("arguments", {}).items())
        and all(value_at(item.result, path) == value for path, value in rule.get("result", {}).items())
    )


def answer_present(sample):
    """Require a nonempty final text answer, not exposed internal action JSON."""
    text = sample.output
    valid = isinstance(text, str) and bool(text.strip())
    if valid:
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and parsed.get("type") in {"tool_call", "agent_call"}:
            valid = False
    return EvaluationScore("answer_present", float(valid), "A final user-facing text answer is required.")


def required_evidence(sample):
    """Require each declared observation from its actual specialist, not a claimed consultation."""
    rules = sample.case.metadata.get("required", [])
    missing = [
        f"{rule['agent']}.{rule['tool']}"
        for rule in rules
        if not any(matches(item, rule) for item in observations(sample))
    ]
    return EvaluationScore(
        "required_evidence",
        float(not missing),
        "Missing: " + ", ".join(missing)
        if missing
        else "Actual native receipts match the declared requirements.",
    )


def selection_scope(sample):
    """Reject extra observations on the wrong market/source instead of accepting one correct call."""
    wrong = []
    for rule in sample.case.metadata.get("scope", []):
        for item in observations(sample):
            if (
                item.agent_name == "sibyl-" + rule["agent"]
                and item.tool_name == rule["tool"]
                and not matches(item, rule)
            ):
                wrong.append(f"{rule['agent']}.{rule['tool']}")
    return EvaluationScore(
        "selection_scope",
        float(not wrong),
        "Wrong selection: " + ", ".join(wrong) if wrong else "No conflicting observation selections.",
    )


def unwanted_reads(sample):
    """Check that setup/instruction questions did not attempt unrelated workspace reads."""
    forbidden = set(sample.case.metadata.get("forbidden_tools", []))
    attempted = (
        [
            f"{item.agent_name}.{item.tool_name}"
            for item in sample.report.tool_evidence
            if item.tool_name in forbidden
        ]
        if sample.report
        else []
    )
    return EvaluationScore(
        "unwanted_reads",
        float(not attempted),
        ", ".join(attempted) if attempted else "No prohibited tool attempts.",
    )


def answer_markers(sample):
    """Check explicit phrases/disclosures only; their presence does not prove semantic correctness."""
    answer = str(sample.output or "").casefold()
    missing = [
        group
        for group in sample.case.metadata.get("answer_any", [])
        if not any(word.casefold() in answer for word in group)
    ]
    forbidden = [
        word for word in sample.case.metadata.get("answer_excludes", []) if word.casefold() in answer
    ]
    return EvaluationScore(
        "answer_markers",
        float(not missing and not forbidden),
        f"Missing groups: {missing}; forbidden markers: {forbidden}",
    )


def native_consultations(sample):
    """Require correlated native delegation receipts for coordinator cases with evidence requirements."""
    if sample.case.metadata.get("module") != "sibyl":
        return EvaluationScore("native_consultations", 1, "Direct specialist case.")
    rules = sample.case.metadata.get("required", [])
    matched = all(
        any(matches(item, rule) and item.delegation_id for item in observations(sample)) for rule in rules
    )
    return EvaluationScore(
        "native_consultations", float(matched), "Delegation IDs must accompany required specialist evidence."
    )


def numeric_grounding(sample):
    """Check specifically requested rounded numbers against actual evidence, without judging other claims."""
    tokens = set(
        re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w|\.\d)", str(sample.output or "").replace(",", ""))
    )
    missing = []
    for rule in sample.case.metadata.get("numbers", []):
        readings = [
            value_at(item.result, rule["path"])
            for item in observations(sample)
            if item.agent_name == "sibyl-" + rule["agent"] and item.tool_name == rule["tool"]
        ]
        wanted = {
            f"{value:.{rule.get('decimals', 1)}f}"
            for value in readings
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if not wanted or not wanted.intersection(tokens):
            missing.append(rule["path"])
    return EvaluationScore(
        "numeric_grounding",
        float(not missing),
        "Missing requested readings: " + ", ".join(missing)
        if missing
        else "Requested numerical readings match native evidence at the declared rounding.",
    )


def _links(data):
    if isinstance(data, dict):
        for value in data.values():
            yield from _links(value)
    elif isinstance(data, list):
        for value in data:
            yield from _links(value)
    elif (
        isinstance(data, str)
        and (data.startswith("https://") or data.startswith("http://") or data.startswith("/"))
        and not re.search(r"\s", data)
    ):
        yield data


def returned_links(sample):
    """Allow answer links only when present in recorded evidence or explicitly declared by the case."""
    allowed = set(sample.case.metadata.get("allowed_links", []))
    for item in observations(sample):
        allowed.update(_links(item.result))
    answer = str(sample.output or "")
    links = re.findall(
        r"https?://[^\s<>`\[\]()]+|(?<![\w:/])/(?:[A-Za-z][A-Za-z0-9_-]*)(?:[/?#][^\s<>`\[\]()]*)?", answer
    )
    wrong = sorted({link.rstrip(".,;:!") for link in links} - allowed)
    return EvaluationScore(
        "returned_links",
        float(not wrong),
        "Unobserved links: " + ", ".join(wrong)
        if wrong
        else "Links match returned evidence. This does not judge surrounding claims.",
    )


def checks_for(case):
    """Apply only relevant checks so neutral cases cannot inflate aggregate success rates."""
    metadata = case.metadata
    checks = [answer_present, returned_links]
    for key, check in (
        ("required", required_evidence),
        ("scope", selection_scope),
        ("forbidden_tools", unwanted_reads),
        ("numbers", numeric_grounding),
    ):
        if metadata.get(key):
            checks.append(check)
    if metadata.get("answer_any") or metadata.get("answer_excludes"):
        checks.append(answer_markers)
    if metadata.get("module") == "sibyl" and metadata.get("required"):
        checks.append(native_consultations)
    return tuple(checks)


def restore_scores(data):
    """Restore native saved score records for compare_evaluations, without replaying tools or traces."""
    samples = tuple(
        EvaluationSample(
            case=EvaluationCase(**row["case"]),
            repetition=row["repetition"],
            error=row.get("error"),
            scores=[EvaluationScore(**score) for score in row["scores"]],
        )
        for row in data["samples"]
    )
    return EvaluationReport(samples)


def compatible_cases(baseline, cases):
    """Refuse comparisons with changed prompts, selections or expectations before spending model calls."""
    before = {item.case.name: asdict(item.case) for item in baseline.samples}
    after = {item.name: asdict(item) for item in cases}
    return before == after
