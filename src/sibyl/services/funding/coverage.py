"""Intervals outside completed fetched windows; these are not completeness or settlement claims."""


def cover_gaps(db, account_id, stream, start, end):
    """Subtract an exhausted manual/rolling range from known unfetched intervals."""
    rows = db.execute(
        "SELECT start_ms,end_ms FROM funding_coverage_gaps WHERE account_id=? AND stream=? AND start_ms<=? AND end_ms>=?",
        (account_id, stream, end, start),
    ).fetchall()
    for left, right in rows:
        db.execute(
            "DELETE FROM funding_coverage_gaps WHERE account_id=? AND stream=? AND start_ms=? AND end_ms=?",
            (account_id, stream, left, right),
        )
        for new_left, new_right in ((left, start - 1), (end + 1, right)):
            if new_left <= new_right:
                db.execute(
                    "INSERT OR IGNORE INTO funding_coverage_gaps VALUES(?,?,?,?)",
                    (account_id, stream, new_left, new_right),
                )
