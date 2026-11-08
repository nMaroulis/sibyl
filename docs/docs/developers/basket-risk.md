# Historical basket-risk contracts

`accounting/risk/` separates request contracts, numerical analysis and saved-study ownership. `Portfolio.risk` reuses active Account scopes, current balances, the source-pinned `Market.snapshot()` and `Valuation`'s observed conversion routes. It does not reuse illustrative account chart history.

| API | Behavior |
| --- | --- |
| `GET /api/v1/account/risk?scope=all` | Read the latest 50 saved metadata rows for this scope; no provider refresh. |
| `POST /api/v1/account/risk` | Explicitly read selected current holdings and exact-source daily history, calculate and save. |
| `GET /api/v1/account/risk/{id}` | Read/export full frozen evidence. |
| `DELETE /api/v1/account/risk/{id}` | Remove one explicitly selected retained study. |

Normal workspace authentication applies and responses use `no-store`. Requests select 1–8 distinct assets, an Account scope and a maximum window. Current values determine positive normalized weights; unknown/unpriced selected assets fail instead of being dropped. Other unpriced holdings and failed accounts remain explicit. At most sixteen distinct legs, one in-process study and 100 saved reports are admitted. A full registry rejects before provider reads. This is single-worker ownership, not distributed coordination.

Daily closes must be finite, positive, aligned, closed and unique. Inverse/bridge conversion intersects exact leg timestamps; an identity holding uses the daily denomination calendar. The latest consecutive common suffix avoids compressing missing intervals. Simple returns form sample covariance (`ddof=1`); daily basket variance is calculated directly from weighted returns to avoid cancellation error. Correlations of constant series, zero-risk variance contributions and diversification ratios are undefined. The path compounds the same fixed daily weights without costs. Annualization is √365. Historical tails use the explicit linear empirical fifth percentile and all returns at/below it; small samples, ties, subset selection and nonstationarity stay visible. Numerically unusable returns, covariance or paths fail without clipping.

Full reports retain current quantities/values/routes, actual input candles, converted closes, source/account identity, timestamps, excluded coverage, metrics, matrix, path and content fingerprint. These are private local SQLite research records, not separately encrypted credential storage. Accountant's native `basket_risk` tool exposes compact saved evidence and setup instructions, never starts a study or changes risk policy.
