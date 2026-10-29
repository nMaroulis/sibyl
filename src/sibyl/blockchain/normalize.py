"""Turn indexer observations into bounded research evidence, retaining integer satoshis."""

import math

from sibyl.blockchain.identifiers import address, txid

MAX_MONEY = 21_000_000 * 100_000_000
PAGE_SIZE = 20


def integer(value, maximum=2**63 - 1, minimum=0):
    """Reject coerced booleans/floats, negative counts and out-of-range provider amounts."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid Bitcoin provider integer.")
    return value


def status(raw, tip):
    """Calculate observed confirmations from inclusion and a separately read tip, not finality."""
    confirmed = raw["confirmed"]
    if type(confirmed) is not bool:
        raise ValueError("Invalid Bitcoin confirmation status.")
    if not confirmed:
        return {
            "confirmed": False,
            "confirmations": 0,
            "block_height": None,
            "block_hash": None,
            "block_time": None,
        }
    height = integer(raw["block_height"], 100_000_000)
    return {
        "confirmed": True,
        "block_height": height,
        "block_hash": txid(raw["block_hash"]),
        "block_time": integer(raw["block_time"], 2**40),
        "confirmations": tip - height + 1 if tip is not None and tip >= height else None,
    }


def output(raw, index):
    """Expose value, address and script type, excluding executable/raw scripts and witnesses."""
    kind = raw.get("scriptpubkey_type", "unknown")
    if kind not in {
        "p2pk",
        "p2pkh",
        "p2sh",
        "v0_p2wpkh",
        "v0_p2wsh",
        "v1_p2tr",
        "multisig",
        "op_return",
        "empty",
        "unknown",
    }:
        kind = "other"
    return {
        "index": index,
        "value_sats": integer(raw["value"], MAX_MONEY),
        "address": address(raw["scriptpubkey_address"]) if raw.get("scriptpubkey_address") else None,
        "script_type": kind,
    }


def transaction(raw, tip, input_offset=0, output_offset=0):
    """Validate a full response, compute exact totals, and return twenty inputs/outputs per view."""
    vin, vout = raw["vin"], raw["vout"]
    if (
        not isinstance(vin, list)
        or not isinstance(vout, list)
        or not 1 <= len(vin) <= 10_000
        or not 1 <= len(vout) <= 10_000
    ):
        raise ValueError("Unsupported Bitcoin transaction input/output count.")
    inputs, outputs = [], [output(row, index) for index, row in enumerate(vout)]
    for index, row in enumerate(vin):
        coinbase = row.get("is_coinbase", False)
        if type(coinbase) is not bool:
            raise ValueError("Invalid coinbase flag.")
        previous = row.get("prevout")
        if coinbase and previous is not None:
            raise ValueError("Invalid coinbase previous output.")
        inputs.append(
            {
                "index": index,
                "coinbase": coinbase,
                "txid": None if coinbase else txid(row["txid"]),
                "vout": None if coinbase else integer(row["vout"], 2**32 - 1),
                "previous_output": None if coinbase or previous is None else output(previous, row["vout"]),
            }
        )
    coinbase = any(row["coinbase"] for row in inputs)
    if coinbase and (len(inputs) != 1 or inputs[0]["previous_output"] is not None):
        raise ValueError("Invalid coinbase inputs.")
    outpoints = [(row["txid"], row["vout"]) for row in inputs if not row["coinbase"]]
    if len(set(outpoints)) != len(outpoints):
        raise ValueError("Duplicate Bitcoin input outpoints.")
    missing = sum(row["previous_output"] is None for row in inputs if not row["coinbase"])
    input_total = None if coinbase or missing else sum(row["previous_output"]["value_sats"] for row in inputs)
    output_total = sum(row["value_sats"] for row in outputs)
    fee = integer(raw["fee"], MAX_MONEY)
    if (
        output_total > MAX_MONEY
        or input_total is not None
        and (input_total > MAX_MONEY or input_total - output_total != fee)
    ):
        raise ValueError("Inconsistent Bitcoin transaction totals.")
    if coinbase and fee != 0:
        raise ValueError("Invalid coinbase fee.")
    weight, size = integer(raw["weight"], 4_000_000, 1), integer(raw["size"], 4_000_000, 1)
    if not size <= weight <= size * 4:
        raise ValueError("Invalid Bitcoin transaction weight.")
    vsize = math.ceil(weight / 4)
    if input_offset >= len(inputs) and input_offset or output_offset >= len(outputs) and output_offset:
        raise ValueError("The requested input/output page is beyond this transaction.")
    return {
        "txid": txid(raw["txid"]),
        "status": status(raw["status"], tip),
        "version": integer(raw["version"], 2**31 - 1, -(2**31)),
        "locktime": integer(raw["locktime"], 2**32 - 1),
        "size": size,
        "weight": weight,
        "vsize": vsize,
        "fee_sats": fee,
        "fee_rate_sat_vb": fee / vsize,
        "coinbase": coinbase,
        "input_count": len(inputs),
        "output_count": len(outputs),
        "missing_prevouts": missing,
        "input_total_sats": input_total,
        "output_total_sats": output_total,
        "inputs": inputs[input_offset : input_offset + PAGE_SIZE],
        "outputs": outputs[output_offset : output_offset + PAGE_SIZE],
        "input_offset": input_offset,
        "output_offset": output_offset,
        "next_input_offset": input_offset + PAGE_SIZE if input_offset + PAGE_SIZE < len(inputs) else None,
        "next_output_offset": output_offset + PAGE_SIZE if output_offset + PAGE_SIZE < len(outputs) else None,
    }


def address_stats(raw):
    """Keep confirmed totals and pending deltas separate; received volume is not wallet income."""
    fields = ("tx_count", "funded_txo_count", "funded_txo_sum", "spent_txo_count", "spent_txo_sum")
    chain, pending = (
        {key: integer(raw[group][key]) for key in fields} for group in ("chain_stats", "mempool_stats")
    )
    confirmed = chain["funded_txo_sum"] - chain["spent_txo_sum"]
    if confirmed < 0 or confirmed > MAX_MONEY:
        raise ValueError("Invalid Bitcoin confirmed address balance.")
    delta = pending["funded_txo_sum"] - pending["spent_txo_sum"]
    if abs(delta) > MAX_MONEY:
        raise ValueError("Invalid Bitcoin pending address balance.")
    projected = confirmed + delta

    # Lifetime turnover can exceed JavaScript's exact integer range; preserve it as decimal text.
    def public_stats(values):
        return {key: str(value) if key.endswith("_sum") else value for key, value in values.items()}

    return {
        "address": address(raw["address"]),
        "chain_stats": public_stats(chain),
        "mempool_stats": public_stats(pending),
        "confirmed_balance_sats": confirmed,
        "pending_delta_sats": delta,
        "projected_balance_sats": projected if 0 <= projected <= MAX_MONEY else None,
    }


def history_row(raw, selected_address, tip):
    """Compute this address's observed net change, never inferring owners or counterparty identity."""
    result = transaction(raw, tip)

    def matches(row):
        return (
            bool(row.get("scriptpubkey_address")) and address(row["scriptpubkey_address"]) == selected_address
        )

    received = sum(integer(row["value"], MAX_MONEY) for row in raw["vout"] if matches(row))
    previous = [row.get("prevout") for row in raw["vin"] if not row.get("is_coinbase")]
    spent = (
        None
        if any(row is None for row in previous)
        else sum(integer(row["value"], MAX_MONEY) for row in previous if matches(row))
    )
    if (
        not any(matches(row) for row in raw["vout"])
        and not any(row and matches(row) for row in previous)
        and spent is not None
    ):
        raise ValueError("Unrelated transaction in Bitcoin address history.")
    return {
        key: result[key]
        for key in ("txid", "status", "fee_sats", "fee_rate_sat_vb", "input_count", "output_count")
    } | {
        "received_sats": received,
        "spent_sats": spent,
        "net_sats": None if spent is None else received - spent,
    }
