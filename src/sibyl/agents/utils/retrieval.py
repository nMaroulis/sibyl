"""Compact saved retrieval evidence shared by Wiki and Reporter; no evaluation writes."""

import re

from protolink import ToolRejectedError

from sibyl.agents.utils.common import selected


def evaluation_evidence(library, identity):
    if not library:
        return {"available": False, "url": "/research?tab=library"}
    identity = selected("retrieval_evaluation_id", identity or None, "")
    if not identity:
        return {
            "kind": "retrieval_evaluation",
            "items": library.evaluations.catalog()["runs"][:10],
            "url": "/research?tab=library",
        }
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ToolRejectedError("Choose a saved retrieval evaluation ID.", code="invalid_evaluation")
    result = library.evaluations.get(identity)
    return {
        "kind": "retrieval_evaluation",
        **{
            key: result[key]
            for key in (
                "id",
                "title",
                "state",
                "k",
                "methods",
                "snapshot",
                "coverage",
                "summary",
                "completed",
                "total",
                "note",
                "error",
            )
        },
        "queries": [
            {
                "query": row["query"],
                "method": row["method"],
                "metrics": row["metrics"],
                "milliseconds": row["milliseconds"],
                "citations": [{"id": item["id"], "url": item["url"]} for item in row["items"]],
            }
            for row in result["results"]
        ],
        "url": "/research?tab=library",
    }
