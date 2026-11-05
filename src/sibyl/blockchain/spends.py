"""Validate indexer output-spend observations without inferring ownership or spendability."""

from sibyl.blockchain import normalize
from sibyl.blockchain.identifiers import txid


def output_spend(raw, output, identity, tip):
    """Bind one indexed observation to its parent output; absent spend details stay unknown."""
    if not isinstance(raw, dict) or type(raw.get("spent")) is not bool:
        raise ValueError("Invalid output spending observation.")
    spent = raw["spent"]
    spending_id = txid(raw["txid"]) if raw.get("txid") is not None else None
    input_index = normalize.integer(raw["vin"], 2**32 - 1) if raw.get("vin") is not None else None
    status = normalize.status(raw["status"], tip) if raw.get("status") is not None else None
    if (
        spending_id == identity
        or not spent
        and any(x is not None for x in (spending_id, input_index, status))
    ):
        raise ValueError("Inconsistent output spending observation.")
    complete = spending_id is not None and input_index is not None and status is not None
    return {
        **output,
        "spent": spent,
        "state": "unspent"
        if not spent
        else "unknown"
        if not complete
        else "confirmed"
        if status["confirmed"]
        else "pending",
        "spending_txid": spending_id,
        "spending_input_index": input_index,
        "status": status,
        "reason": "The source reports a spend but its transaction details are incomplete."
        if spent and not complete
        else None,
    }
