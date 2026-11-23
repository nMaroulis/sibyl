# Semantic retrieval calibration contracts

`research_library/calibration/` separates Pydantic contracts, deterministic metrics and experiment/policy ownership. `snapshot.py` provides the same corpus/vector identity used by ranking evaluations. SQLite lives in the existing private research database. No new model adapter, agent runtime, vector database or dependency is added.

## Experiment contract

`CalibrationCreate` accepts 8–32 distinct trimmed/casefolded queries, a source kind and explicit `fit`/`validation` partitions. Each partition requires two positive and two no-source judgments. An empty `expected` array means the owner asserts that no relevant passage exists in the selected scope; it is not a missing label. Relevant IDs must exist in scope at admission, and their exact text/source receipts are retained. Source/model completeness and a maximum 100 reports/one active job are checked transactionally.

The existing supervised-worker framework runs `retrieval-calibration`, one query per turn, with no SQLite write lock held during embedding. Existing native local/ProtoLink hosted adapters perform the actual search. Jobs request raw top-one semantic rankings through a domain-only bypass, unavailable in HTTP and model-facing tool parameters. Both admission and pre/post-query commits bind the same exact corpus/index snapshot. Stop and restart fence late success; no automatic query replay or activation occurs.

`metrics.calibrate` examines only fit results. An accepted query is correct only when its leading passage ID is among that query's explicit relevant IDs. The threshold is `math.nextafter(max(incorrect_fit_scores), math.inf)`, or -1 when there is no scored incorrect fit match. Search uses inclusive `score >= threshold`. This is the least restrictive scalar cutoff excluding every observed incorrect fit score; ties cannot be split. A threshold above 1 rejects all cosine scores. No-score retrieval abstains. Validation is evaluated once at the fitted threshold, never used to select it.

Counts distinguish accepted relevant matches, incorrect accepts, no-source accepts and missed answerable questions. Precision is undefined for no accepts; answerable coverage divides correctly accepted queries by positively labeled queries. Eligibility requires correctly accepted fit and validation queries and zero incorrect validation accepts. This is an explicit empirical activation rule, not statistical calibration, a confidence interval, representative-data certification or a guarantee. Repeated validation-guided experimentation can overfit.

## Policy and search contract

Each exact source scope has its own revision-checked opt-in policy. Activation requires a completed eligible report for that same kind and an unchanged snapshot. Search reads the policy before retrieval and rechecks its revision/snapshot afterward. Enabled search embeds against the normal model, requests one result and releases only that leading passage when it meets the cutoff. Stale policies withhold before provider access. Concurrent policy/source changes discard the search evidence instead of returning a late success. Provider failures retain their existing error semantics; they are not converted into apparently successful empty retrieval.

Raw keyword/hybrid methods are uncalibrated and scopes do not inherit policies. Direct document/passage reads remain available: this filter is not authorization. Disabled semantic search keeps its former rankings, with an explicit disabled calibration receipt. Existing ranking evaluations bypass cutoffs to avoid selection bias. Changing an enabled cutoff during an initially unfiltered search also fences that result.

The snapshot includes all source passages/metadata, semantic revision/model/provider identity and vector bytes. Even a source outside the selected kind can conservatively stale a policy. Hosted aliases cannot establish unchanged weights. Hash checks run locally on status/search, not on a UI polling timer; they do not make provider calls. Enabled reports cannot be deleted. Startup interrupts unfinished experiments but retains completed reports/policies. Bounded native query errors are sanitized, and keys/opaque credential references never enter report evidence.

## HTTP and native tools

All routes are under `/api/v1/library`, use normal workspace authentication and return `Cache-Control: no-store`.

| Route | Behavior |
| --- | --- |
| `GET /calibrations` | Compact report/current-snapshot projections and all three policy states; no inference. |
| `POST /calibrations` | Queue a labeled experiment, 202; no immediate query or activation. |
| `GET /calibrations/{id}` | Saved exact evidence/export. |
| `POST /calibrations/{id}/stop` | Fence future/late query commits. |
| `DELETE /calibrations/{id}` | Remove an inactive report not used by an enabled policy. |
| `POST /calibration-policy/{kind}` | Revision-checked enable/disable. |
| `GET /search?...&method=semantic` | Apply the exact-scope policy; no public bypass flag. |

Wiki/Reporter's existing native `retrieval_evaluation` tool reads ranking or calibration reports; `research_search_status` includes current policy states. Page selection uses private `retrieval_calibration_id` context. Native Tool validation, thread execution, request context and evidence remain unchanged. Agents cannot fit or activate a cutoff. Prompts and page help explain abstention/staleness and prohibit silent fallback; no-model UI summaries describe actual withheld evidence separately from generated answers.

`tests/test_retrieval_calibration.py` exercises actual local and native hosted ranking with controlled HTTP vectors, independent cutoff arithmetic, held-out failures/ties, scope isolation, stale checks before provider access, concurrent policy/corpus changes, raw evaluation comparisons, stop/drain/restart, privacy and native HTTP/tool integration. These are contract tests; live model/corpus relevance and independent forward-quality evaluation remain pending.
