"""Monotonic inbox sequencing so retention cannot make delivery cursors skip new notices."""


def ensure_schema(db):
    """Preserve every existing ID, payload and rowid while adopting SQLite AUTOINCREMENT."""
    db.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in db.execute("PRAGMA table_info(alert_notifications)")}
    definition = """(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE, rule_id TEXT NOT NULL, cycle INTEGER NOT NULL,
        created_at TEXT NOT NULL, read_at TEXT, payload TEXT NOT NULL, UNIQUE(rule_id,cycle))"""
    if not columns:
        db.execute("CREATE TABLE alert_notifications " + definition)
    elif "sequence" not in columns:
        db.execute("CREATE TABLE notification_sequence_upgrade " + definition)
        db.execute(
            "INSERT INTO notification_sequence_upgrade(sequence,id,rule_id,cycle,created_at,read_at,payload) SELECT rowid,id,rule_id,cycle,created_at,read_at,payload FROM alert_notifications ORDER BY rowid"
        )
        db.execute("DROP TABLE alert_notifications")
        db.execute("ALTER TABLE notification_sequence_upgrade RENAME TO alert_notifications")
    db.execute("CREATE INDEX IF NOT EXISTS inbox_history_age ON alert_notifications(read_at,created_at)")
