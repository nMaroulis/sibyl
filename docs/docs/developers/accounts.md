# Active accounts and portfolio scopes

`services/accounts.py` separates saved connection metadata from active inclusion in account-dependent workflows. Neither a config `mode` nor a process restart activates an account. A fresh Store creates no Demo connection and no activation rows. Existing saved connections are retained; there is no inference that saved means active.

## Atomic selection

`active_accounts(account_id PRIMARY KEY)` stores the selection. `Store.add_connection(..., activate=True)` saves encrypted credentials and applies activation in one immediate transaction. An explicitly connected production/test account removes Demo activation and joins existing exchange selections. `activate=False` supports saving metadata without selecting it internally. `Store.activate_account()` toggles one row while preserving concurrent edits to others.

Demo is connected only by an explicit action. Activating it while any exchange account is active fails. Activating an exchange removes Demo. Deactivating/deleting the last exchange leaves the selection empty. No fallback to Demo occurs. Reopening a Store preserves these choices and does not reset the virtual ledger.

Connection metadata adds `active`; credentials remain write-only. Activation endpoints return no key material and use the existing workspace authentication/origin rules.

## API

- `GET /api/v1/accounts`: `mode` (`none`, `demo`, `live`, `test`), `active_ids`, saved `accounts`, available `scopes`, a stable active-ID `signature`, and `demo_available`. No provider calls. Responses use `Cache-Control: no-store`.
- `POST /api/v1/accounts/demo`: connect/reactivate the existing virtual wallet and return selection. Reject if an exchange is active.
- `POST /api/v1/connections/{id}/activation`: `{"active":true|false}`. Deactivated account imports are paused. Activation itself never validates credentials with the provider or enables exchange execution.
- `GET /api/v1/system`: adds `accounts` with the same selection metadata. The legacy `mode` field remains the independent research-data default; the UI uses `accounts.mode` for account status.
- `POST /api/v1/connections`: saving normally activates the connection and disables Demo; credential checking remains separate.

## Portfolio views

`GET /portfolio` and `/portfolio/accounts` accept `scope=all`, `exchange:<provider>`, or `account:<id>`. Unknown/inactive scopes fail rather than silently exposing another account. Resolution uses active saved metadata only.

The combined primary set contains production accounts when present, otherwise test accounts, otherwise the explicitly active Demo wallet. Test funds never enter production totals. Group scopes use that primary set; individual test scopes remain available even when production accounts are active.

Portfolio freezes its selected account list for a read. It combines native asset quantities, prices them through the independent valuation engine, and returns each holding's `accounts` contributors plus per-venue priced totals and exclusions. All widgets and exports follow the selected scope. History scopes hash the selected account IDs, keeping individual, group and differently composed account sets separate. An empty workspace returns empty state without fetching balances, resolving a market source or saving a zero history point.

Frontend pages use the selection signature as a remount boundary, clearing stale account data and order drafts on a selection change. Scope choices are stored in the page URL. Accountant receives the same validated `context.portfolio_scope` and reads that scope through its ProtoLink tool. The accounts panel further filters only within that scope.

## Execution and imports

Manual paper balance reads/previews/fills require explicit Demo activation. Fills recheck activation inside the ledger transaction. Exchange previews require an active account; confirmation checks selection before transitioning a preview to submitting. Already submitted intent status reads and retained records remain inspectable. Account activation never changes `SIBYL_ALLOW_LIVE_TRADING` or bypasses review/confirmation.

Deactivation pauses imports, and the worker independently checks activation before reading a page. A page already in flight may finish and checkpoint. Reactivation does not automatically resume a paused import. Saved inactive accounts retain history, and can be activated before another import is requested. Connected-account market feeds become unavailable when their account is inactive; independently configured public feeds remain usable.

## Empty states and Demo

Portfolio and Trade show a shared setup panel with a primary Connect exchange accounts action, activation choices for saved inactive accounts, and a smaller Preview with Demo action. A persistent preview banner and header badge identify virtual funds. Real/test selections do not render the Demo manual-order form. Settings distinguishes Active/Inactive from Verified/Unverified, since inclusion is not proof of credentials working.

Public Markets and configured research/news tools do not require an exchange account. Model setup remains separate too. Strategy backtests/paper jobs have isolated simulation capital; they do not implicitly activate the manual Demo wallet.
