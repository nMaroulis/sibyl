"""Read-only acquisition-lot carryover for a deliberately narrow transfer contract.

Current zero-fee pairs or explicitly reviewed same-asset fee allocations can
carry lots. All accounts in a connected asset component share one exact market.
Unsupported facts remain funding coverage gaps; they never receive guessed fees,
exchange rates or a made-up acquisition cost.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import localcontext

from sibyl.services.fifo import FifoBook, decimal, public
from sibyl.services.transfer_allocation import lot_evidence, movement_plan, split_lots
from sibyl.services.transfer_reconciliation import link_view

MAX_LINKS = 2000
MAX_FUNDING = 20_000
EVIDENCE_LIMIT = 50
LOT_LIMIT = 100


def snapshot(db, account_id: str, symbol: str, environment: str, max_fills: int) -> dict:
    """Load dependency accounts before filtering report rows, in the caller's snapshot.

    Budgets apply to dependencies too. Reject oversized selections; never silently
    truncate acquisitions or confirmations needed to compute destination basis.
    """
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    links = []
    if "transfer_links" in tables:
        clauses, args = ["state='confirmed'"], []
        for field, value in (("asset", symbol.split("/")[0] if symbol else ""), ("environment", environment)):
            if value:
                clauses.append(f"json_extract(payload,'$.outgoing.{field}')=?")
                args.append(value)
        records = db.execute(
            "SELECT * FROM transfer_links WHERE " + " AND ".join(clauses) + " LIMIT ?",
            [*args, MAX_LINKS + 1],
        ).fetchall()
        if len(records) > MAX_LINKS:
            raise ValueError(
                "Transfer dependency budget exceeded. Filter to a market/environment; links are never silently truncated."
            )
        if account_id:
            accounts = {account_id}
            changed = True
            while changed:
                changed = False
                for row in records:
                    saved = json.loads(row["payload"])
                    pair = {saved["outgoing"]["account_id"], saved["incoming"]["account_id"]}
                    if pair & accounts and not pair <= accounts:
                        accounts.update(pair)
                        changed = True
            records = [
                row for row in records if json.loads(row["payload"])["outgoing"]["account_id"] in accounts
            ]
        else:
            accounts = None
        links = [link_view(db, dict(row)) for row in records]
    else:
        accounts = {account_id} if account_id else None
    # A bounded account set is encoded as one SQLite JSON parameter, avoiding
    # SQLite variable limits for a long chain of linked accounts.
    clauses, args = [], []
    if accounts is not None:
        clauses.append("account_id IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(accounts)))
    if environment:
        clauses.append("json_extract(payload,'$.environment')=?")
        args.append(environment)
    fill_clauses, fill_args = list(clauses), list(args)
    if symbol:
        fill_clauses.append("symbol=?")
        fill_args.append(symbol)
    where = " AND ".join(fill_clauses) or "1=1"
    count = db.execute(f"SELECT COUNT(*) FROM account_fills WHERE {where}", fill_args).fetchone()[0]
    if count > max_fills:
        raise ValueError(
            "This report supports up to 20,000 fills including transfer dependencies. Choose a single account or market; history is never silently truncated."
        )
    fills = [
        json.loads(row[0])
        for row in db.execute(
            f"SELECT payload FROM account_fills WHERE {where} ORDER BY timestamp_ms,id", fill_args
        )
    ]
    basis = [
        dict(row)
        for row in db.execute("SELECT * FROM opening_inventory")
        if (accounts is None or row["account_id"] in accounts) and (not symbol or row["symbol"] == symbol)
    ]
    markets = defaultdict(set)
    for identity, pair in db.execute(
        "SELECT account_id,symbol FROM account_fills UNION SELECT account_id,symbol FROM opening_inventory"
    ):
        for asset in pair.split("/"):
            markets[(identity, asset)].add(pair)
    funding = []
    if "funding_events" in tables:
        if symbol:
            asset = symbol.split("/")[0]
            clauses.append("(asset=? OR json_extract(payload,'$.fee.currency')=?)")
            args.extend([asset, asset])
        where = " AND ".join(clauses) or "1=1"
        count_funding = db.execute(f"SELECT COUNT(*) FROM funding_events WHERE {where}", args).fetchone()[0]
        if count_funding > MAX_FUNDING:
            raise ValueError(
                "Funding dependency budget exceeded. Filter the report; observations are never silently truncated."
            )
        funding = [
            json.loads(row[0])
            for row in db.execute(
                f"SELECT payload FROM funding_events WHERE {where} ORDER BY timestamp_ms,id", args
            )
        ]
    return {"fills": fills, "basis": basis, "markets": markets, "funding": funding, "links": links}


def boundary(group: dict) -> float:
    """An explicit valid opening assertion covers observations strictly before it."""
    opening = group["opening"] if group["opening_applied"] else None
    return datetime.fromisoformat(opening["as_of"]).timestamp() * 1000 if opening else float("-inf")


def affects(event: dict, group: dict) -> bool:
    """Include pending/unknown funding and base-denominated fees, excluding failures."""
    base = group["symbol"].split("/")[0]
    return (
        event["account_id"] == group["account_id"]
        and event["environment"] == group["environment"]
        and event["status"] not in {"failed", "cancelled"}
        and event["timestamp_ms"] >= boundary(group)
        and (event["asset"] == base or (event["fee"]["currency"] == base and event["fee"]["cost"]))
    )


def replay(groups: dict, links: list[dict], funding: list[dict], markets: dict) -> dict:
    """Replay fills, dispatches and receipts once, preserving lot age across hops.

    `groups` holds account/exact-market metadata, augmented with transfer-only
    destinations when the component has one unambiguous quote denomination.
    Caller-owned input facts are never modified. Output evidence is bounded;
    the calculation always uses every input inside the checked budgets.
    """
    with localcontext() as context:
        context.prec = 50
        return _replay(groups, links, funding, markets)


def _replay(groups: dict, links: list[dict], funding: list[dict], markets: dict) -> dict:
    funding_times = Counter()
    for event in funding:
        if event["status"] not in {"failed", "cancelled"}:
            assets = {event["asset"]}
            if event["fee"]["currency"] and event["fee"]["cost"]:
                assets.add(event["fee"]["currency"])
            for asset in assets:
                funding_times[(event["account_id"], event["environment"], asset, event["timestamp_ms"])] += 1
    pairs = _component_pairs(links, markets)
    evidence, events = [], {}
    for link in links:
        out, inc = (link["reviewed"][side] for side in ("outgoing", "incoming"))
        pair = pairs.get((out["environment"], out["asset"], out["account_id"]), "")
        item = {
            "link_id": link["id"],
            "status": "unapplied",
            "reason": "",
            "symbol": pair,
            "environment": out["environment"],
            "asset": out["asset"],
            "outgoing_account_id": out["account_id"],
            "incoming_account_id": inc["account_id"],
            "outgoing_account": out["account"],
            "incoming_account": inc["account"],
            "outgoing_id": out["id"],
            "incoming_id": inc["id"],
            "sent_at": out["created_at"],
            "received_at": inc["created_at"],
            "quantity": out["quantity"],
            "known_quantity": None,
            "unknown_quantity": None,
            "carried_cost": None,
            "shortfall_quantity": None,
            "lots": [],
            "lot_count": 0,
            "lot_limit": LOT_LIMIT,
            "allocation": link.get("allocation") or link["reviewed"].get("allocation"),
            "movement": None,
            "outgoing_fee_evidence": None,
            "incoming_fee_evidence": None,
        }
        evidence.append(item)
        # Create a receiving-only row as well as intermediate accounts in a chain.
        if pair:
            for event in (out, inc):
                key = (event["account_id"], pair)
                groups.setdefault(
                    key,
                    {
                        **{
                            field: event[field]
                            for field in ("account_id", "account", "exchange", "environment")
                        },
                        "symbol": pair,
                        "executions": [],
                        "opening": None,
                        "opening_applied": False,
                        "cross_market": False,
                        "initial_issues": [],
                    },
                )
        reason, out, inc = _eligibility(link, pair, groups, funding_times)
        item["reason"] = reason
        if not reason:
            plan = movement_plan(link, out, inc)
            item["movement"] = plan
            for event, kind in ((out, "dispatch"), (inc, "receipt")):
                events[event["id"]] = (item, event, kind, (event["account_id"], pair))
    books = {
        key: FifoBook(group["executions"], group["opening"] if group["opening_applied"] else None)
        for key, group in groups.items()
    }
    timeline, funding_counts = _timeline(groups, funding, evidence, events)
    unresolved, tainted = defaultdict(int), set()
    transit = {}
    charged = defaultdict(list)
    for stamp, _, identity, kind, key, payload in sorted(timeline, key=lambda entry: entry[:3]):
        book = books[key]
        if kind == "fill":
            book.execute(payload)
        elif kind in {"unresolved", "taint"}:
            unresolved[key] += kind == "unresolved"
            tainted.add(key)
        else:
            item, event, _, _ = payload
            if kind == "dispatch":
                if key in tainted or not book.reliable or groups[key]["initial_issues"]:
                    item["reason"] = (
                        "Source inventory has earlier unresolved funding, fees, ordering or opening coverage."
                    )
                    unresolved[key] += 1
                    tainted.add(key)
                    continue
                plan = item["movement"]
                slices, shortfall = book.take(decimal(plan["source_debit"]), stamp, identity)
                dispatched, fee_slices = split_lots(slices, decimal(plan["dispatch_quantity"]))
                transit[item["link_id"]] = dispatched
                charged[key].extend(fee_slices)
                item["outgoing_fee_evidence"] = lot_evidence(fee_slices, LOT_LIMIT)
                item["shortfall_quantity"] = public(shortfall)
            else:
                slices = transit.pop(item["link_id"], None)
                if slices is None:
                    unresolved[key] += 1
                    tainted.add(key)
                    if not item["reason"]:
                        item["reason"] = "The source dispatch could not be applied in this snapshot."
                    continue
                credited, fee_slices = split_lots(slices, decimal(item["movement"]["destination_credit"]))
                charged[key].extend(fee_slices)
                item["incoming_fee_evidence"] = lot_evidence(fee_slices, LOT_LIMIT)
                credited_evidence = lot_evidence(credited, LOT_LIMIT)
                item.update(
                    known_quantity=credited_evidence["known_quantity"],
                    unknown_quantity=credited_evidence["unknown_quantity"],
                    carried_cost=credited_evidence["known_cost"],
                    lot_count=credited_evidence["lot_count"],
                    lots=credited_evidence["lots"],
                )
                book.receive(credited, transferred=True)
                item.update(
                    status="applied",
                    reason="Original FIFO acquisition dates and quote costs carried without a disposal.",
                )
    return {
        "summaries": _summaries(groups, books, evidence, unresolved, funding_counts, charged),
        "transfers": evidence,
    }


def _component_pairs(links: list[dict], markets: dict) -> dict:
    """Resolve one exact market across each connected asset/environment component."""
    graph = defaultdict(lambda: defaultdict(set))
    for link in links:
        out, inc = (link["reviewed"][side] for side in ("outgoing", "incoming"))
        graph[(out["environment"], out["asset"])][out["account_id"]].add(inc["account_id"])
        graph[(out["environment"], out["asset"])][inc["account_id"]].add(out["account_id"])
    pairs = {}
    for (env, asset), adjacency in graph.items():
        seen = set()
        for account in adjacency:
            if account in seen:
                continue
            component, todo = set(), [account]
            while todo:
                current = todo.pop()
                if current in component:
                    continue
                component.add(current)
                todo.extend(adjacency[current] - component)
            seen.update(component)
            options = set().union(*(markets.get((item, asset), set()) for item in component))
            pair = next(iter(options)) if len(options) == 1 else ""
            if pair and pair.split("/")[0] != asset:
                pair = ""
            for identity in component:
                pairs[(env, asset, identity)] = pair
    return pairs


def _eligibility(link: dict, pair: str, groups: dict, funding_times: Counter) -> tuple[str, dict, dict]:
    """Explain why reviewed facts cannot carry lots; never infer missing fee semantics."""
    out, inc = (link["reviewed"][side] for side in ("outgoing", "incoming"))
    reason = ""
    if link["status"] != "confirmed" or not link["current"] or not link["current"]["valid"]:
        reason = "Source records changed or are unavailable. Review the saved link again."
    elif not pair:
        reason = "The connected asset accounts do not have one unambiguous exact-market quote denomination."
    else:
        out, inc = (link["current"][side] for side in ("outgoing", "incoming"))
        try:
            movement_plan(link, out, inc)
        except ValueError as error:
            return str(error), out, inc
        if inc["timestamp_ms"] <= out["timestamp_ms"]:
            reason = "Receipt must follow dispatch; equal/reversed timestamps have unresolved ordering."
        elif any(
            funding_times[(event["account_id"], event["environment"], event["asset"], event["timestamp_ms"])]
            > 1
            for event in (out, inc)
        ):
            reason = "Multiple funding observations share an account timestamp; inventory ordering is not established."
        elif any(
            groups[(event["account_id"], pair)]["environment"] != event["environment"] for event in (out, inc)
        ):
            reason = "Retained market history and transfer environments differ."
        elif any(
            event["timestamp_ms"] <= boundary(groups[(event["account_id"], pair)]) for event in (out, inc)
        ):
            reason = "An opening assertion overlaps this transfer. Review opening dates to avoid counting inventory twice."
        elif any(groups[(event["account_id"], pair)]["cross_market"] for event in (out, inc)):
            reason = "Cross-market or mixed-environment inventory is ambiguous."
        elif any(
            any(
                fill["timestamp_ms"] == event["timestamp_ms"]
                for fill in groups[(event["account_id"], pair)]["executions"]
            )
            for event in (out, inc)
        ):
            reason = "A transfer and fill share a timestamp; their inventory ordering is not established."
    return reason, out, inc


def _timeline(groups: dict, funding: list[dict], evidence: list[dict], events: dict) -> tuple[list, dict]:
    """Order all retained fills and relevant funding, including missing-source review gaps."""
    funding_counts = defaultdict(int)
    timeline = []
    funding_by_asset = defaultdict(list)
    for event in funding:
        funding_by_asset[(event["account_id"], event["environment"], event["asset"])].append(event)
        fee = event["fee"]
        if fee["currency"] != event["asset"] and fee["currency"] and fee["cost"]:
            funding_by_asset[(event["account_id"], event["environment"], fee["currency"])].append(event)
    for key, group in groups.items():
        timeline.extend(
            (fill["timestamp_ms"], 1, fill["id"], "fill", key, fill) for fill in group["executions"]
        )
        for event in funding_by_asset[(key[0], group["environment"], key[1].split("/")[0])]:
            if affects(event, group):
                funding_counts[key] += 1
                special = events.get(event["id"])
                if special and special[3] == key:
                    timeline.append((event["timestamp_ms"], 0, event["id"], special[2], key, special))
                else:
                    timeline.append((event["timestamp_ms"], -1, event["id"], "unresolved", key, event))
        # A missing/corrected source can remove the funding row itself. Preserve
        # the review gap as a dependency blocker without inventing a source fact.
        for item in evidence:
            if (
                item["reason"]
                and item["environment"] == group["environment"]
                and item["asset"] == group["symbol"].split("/")[0]
                and (not item["symbol"] or item["symbol"] == key[1])
            ):
                for side in ("outgoing", "incoming"):
                    if item[f"{side}_account_id"] == key[0]:
                        stamp = (
                            datetime.fromisoformat(
                                item["sent_at" if side == "outgoing" else "received_at"]
                            ).timestamp()
                            * 1000
                        )
                        if stamp >= boundary(group):
                            timeline.append((stamp, -2, item["link_id"], "taint", key, item))
    return timeline, funding_counts


def _summaries(
    groups: dict, books: dict, evidence: list[dict], unresolved: dict, funding_counts: dict, charged: dict
) -> dict:
    """Add bounded provenance and coverage flags to the shared FIFO summaries."""
    results = {}
    for key, book in books.items():
        row = book.summary()
        group = groups[key]
        row["issues"].extend(group["initial_issues"])
        related = [
            item
            for item in evidence
            if key[0] in {item["outgoing_account_id"], item["incoming_account_id"]}
            and (not item["symbol"] or item["symbol"] == key[1])
            and item["environment"] == group["environment"]
            and item["asset"] == group["symbol"].split("/")[0]
            and datetime.fromisoformat(
                item["sent_at" if item["outgoing_account_id"] == key[0] else "received_at"]
            ).timestamp()
            * 1000
            >= boundary(group)
        ]
        applied = [item for item in related if item["status"] == "applied"]
        fee = lot_evidence(charged[key], LOT_LIMIT)
        has_fee = any(
            decimal(item["movement"][side]) for item in applied for side in ("outgoing_fee", "incoming_fee")
        )
        row.update(
            funding_event_count=funding_counts[key],
            unresolved_funding_count=unresolved[key],
            transfer_in_count=sum(item["incoming_account_id"] == key[0] for item in applied),
            transfer_out_count=sum(item["outgoing_account_id"] == key[0] for item in applied),
            basis_transfers=related[:EVIDENCE_LIMIT],
            basis_transfer_count=len(related),
            basis_transfer_limit=EVIDENCE_LIMIT,
            transfer_fee_quantity=fee["quantity"],
            transfer_fee_known_inventory_cost=fee["known_cost"],
            transfer_fee_unknown_quantity=fee["unknown_quantity"],
        )
        if unresolved[key]:
            row["issues"].append(
                f"{unresolved[key]} retained funding observations remain unapplied after the opening boundary. Net results remain provisional; review transfer eligibility and other funding coverage."
            )
        if any(item["unknown_quantity"] for item in applied):
            row["issues"].append(
                "A transfer carried unknown-cost units. Missing source acquisition history is not assigned zero basis."
            )
        if any(item["shortfall_quantity"] for item in applied):
            row["issues"].append(
                "A source transfer exceeded retained inventory. The shortfall is carried as unknown cost, without inventing a purchase."
            )
        if any(item["status"] != "applied" for item in related):
            row["issues"].append(
                "Some reviewed transfer links cannot carry basis in this snapshot. Inspect their reasons below."
            )
        if has_fee:
            row["issues"].append(
                "Transfer-fee inventory cost is disclosed separately from trading P&L. Historical fee valuation is unavailable; final net results remain provisional."
            )
        if any("user_asserted" in item["movement"]["fee_sources"].values() for item in applied):
            row["issues"].append(
                "Transfer fee coverage includes an explicit user assertion for missing source data; it is not a reported provider fee."
            )
        if (
            unresolved[key]
            or group["initial_issues"]
            or group["cross_market"]
            or has_fee
            or any(item["status"] != "applied" or item["shortfall_quantity"] for item in related)
        ):
            row.update(net_known=False, net_matched_realized=None)
        results[key] = row
    return results
