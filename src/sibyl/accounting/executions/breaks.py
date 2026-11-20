"""Economic treatment of explicit venue trade reversals retained in the fill ledger."""

BREAK_REVIEW = {
    "manual": "Gemini reported a manual reversal. Its separate balance adjustments need review.",
    "unverified": "Gemini reported a trade break with unverified balance effects.",
}
ACTIVE_FILL_SQL = "json_extract(payload,'$.trade_break') IS NULL"


def affected_assets(fill: dict) -> set[str]:
    """Include third-asset fees when a reversal can affect balances outside the market."""
    return set(fill["symbol"].split("/")) | {fee["currency"] for fee in fill["fees"] if fee["currency"]}
