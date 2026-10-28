"""Local checkpoint controls and explicit limits for balance comparisons."""

from pydantic import Field

from sibyl.models import Request

MAX_RECORDS = 10_000
MAX_ASSETS = 2_000
HISTORY_LIMIT = 20
BOUNDARY_MS = 1_000
NOTE = (
    "Observed configured-wallet quantities compared with retained imported activity. "
    "This is not complete account reconciliation, investment return or settlement verification. "
    "Missing markets, funding, wallet types and provider retention can leave unexplained changes. "
    "Balances and history are not an atomic exchange snapshot."
)


class SaveCheckpoint(Request):
    """Replace only the checkpoint the user actually viewed; never overwrite a newer one."""

    replace_id: str | None = Field(default=None, min_length=1, max_length=100)


class CompareBalances(Request):
    """Compare against a fixed saved checkpoint, without replacing it or modifying fills."""

    checkpoint_id: str = Field(min_length=1, max_length=100)
