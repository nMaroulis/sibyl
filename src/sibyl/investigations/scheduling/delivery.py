"""Render saved report text for Telegram without another model request or invented links."""


def briefing_text(title: str, run: dict, presentation: str, *, document: bool = False) -> str:
    """Prepare plain text from a completed report, retaining model/data attribution."""
    report = run["report"]
    lines = [f"Sibyl briefing · {title}", f"Report version {run['version']} · {run['finished_at']}"]
    if run["models"]["sibyl"]["provider"] == "mock":
        lines.append("Simulated model · illustrative output")
    if not run.get("sources"):
        lines.append(
            "No tool observations were recorded. This is model interpretation without supporting source receipts."
        )
    context = run["context"]
    if context.get("market_source") == "demo" or context.get("news_mode") == "demo":
        lines.append("Demo starting context · synthetic observations may be included")
    lines.extend(["", report["summary"]])
    if presentation == "full":
        for finding in report["findings"]:
            lines.extend(["", finding["title"], finding["detail"]])
            if finding["sources"]:
                lines.append("Sources: " + ", ".join(finding["sources"]))
    if report["uncertainties"]:
        lines.extend(["", "What remains uncertain", *[f"• {item}" for item in report["uncertainties"]]])
    lines.extend(
        [
            "",
            f"Full report: Sibyl → Investigations → {title} → version {run['version']}.",
            "Model interpretation · inspect the recorded sources in Sibyl.",
        ]
    )
    text = "\n".join(lines)
    if not document and len(text) > 18000:
        text = text[:17800] + "\n[Briefing shortened. Read the full report in Sibyl → Investigations.]"
    return text
