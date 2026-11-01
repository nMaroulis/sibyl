"""Turn retained native tool receipts into bounded, inspectable research sources."""

import hashlib
import json
from urllib.parse import urlsplit


def source_links(value, depth=0):
    """Extract links actually returned by tools; never fetch model-generated URLs."""
    if depth > 6:
        return []
    found = []
    if isinstance(value, dict):
        for key, item in list(value.items())[:80]:
            if key in {"url", "link", "website", "source_url"} and isinstance(item, str):
                try:
                    parts = urlsplit(item)
                except ValueError:
                    continue
                if (
                    parts.scheme in {"https", "http"}
                    and parts.netloc
                    and not parts.username
                    and not parts.password
                ) or (item.startswith("/") and not item.startswith("//")):
                    found.append(item)
            found.extend(source_links(item, depth + 1))
    elif isinstance(value, list):
        for item in value[:30]:
            found.extend(source_links(item, depth + 1))
    return list(dict.fromkeys(found))[:12]


def report_sources(report):
    """Keep completed exposed tool results with native correlation and retrieval times.

    Read a retained, redacted ProtoLink report. Previews are explicitly bounded;
    fingerprints identify the redacted observation, not an independently verified fact.
    """
    sources = []
    if report is None:
        return sources
    for receipt in report.tool_evidence:
        if receipt.outcome != "completed" or receipt.result_omitted:
            continue
        data = json.dumps(receipt.result, ensure_ascii=False, sort_keys=True, allow_nan=False)
        agent = (receipt.agent_name or "unknown").removeprefix("sibyl-")
        sources.append(
            {
                "id": receipt.action_id or f"source-{len(sources) + 1}",
                "key": f"{agent}.{receipt.tool_name}",
                "agent_id": agent,
                "tool": receipt.tool_name,
                "retrieved_at": receipt.finished_at,
                "task_id": receipt.task_id,
                "delegation_id": receipt.delegation_id,
                "links": source_links(receipt.result),
                "fingerprint": hashlib.sha256(data.encode()).hexdigest(),
                "preview": data[:16000],
                "truncated": len(data) > 16000,
            }
        )
    return sources


def validate_references(report, sources):
    """Reject claimed agent/tool citations that have no completed native receipt."""
    available = {source["key"] for source in sources}
    if any(source not in available for finding in report.findings for source in finding.sources):
        raise ValueError("The report cited a tool observation that was not recorded.")
