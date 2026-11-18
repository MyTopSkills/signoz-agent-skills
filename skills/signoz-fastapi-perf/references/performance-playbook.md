# Evidence-first FastAPI slow endpoint playbook

## Read a trace accurately

- HTTP **Server** root span's elapsed milliseconds describes an observed request latency, not necessarily browser-end-to-end latency.
- `duration_nano` is nanoseconds in SigNoz APIs. UI exports can show milliseconds. Never apply the wrong conversion.
- Span count includes root/children and may include framework/instrumentation spans; repeated spans are observational, not necessarily one query per item.
- `sum_ms` over a group is arithmetic sum; may exceed wall-clock latency with overlaps. `wall_union_ms` merges same-group intervals; groups still overlap with each other. `max_self_ms` in this collector means span interval not covered by its *direct* children's intervals (not CPU time). `uncovered_ms` is root interval not overlapped by any descendant span (not CPU time).
- Traces can be truncated or have missing parents from sampling. Do not assert precise accounting when that happens.

## Code mapping and MongoDB N+1

1. Find the route (`rg "<slow-route-path>" .`) and the router method. Follow Depends dependencies, DTO validation, middleware, services and DAO.
2. For repeated MongoDB `find` spans: locate nested `for`/`async for` loops and `await collection.find_one()`/`find().to_list()`, count queries triggered *per returned item*, and assess whether unique keys vary. Be wary of Motor cursor laziness.
3. If N+1 appears real, sketch batched query with `$in` and an in-memory key map; preserve ordering, duplicates, missing records, permission scopes, stable pagination and joins. Complexity also depends on index and document size.
4. Compare query plan evidence using safe **read-only** `explain()` on representative queries when access/approval is available; `COLLSCAN`/`IXSCAN`, `totalDocsExamined`, `totalKeysExamined`, selectivity and sort can matter. Never deploy an index just because a query is repeated.
5. Distinguish repeated auth/profile lookups by middleware from direct endpoint queries.

## Other latency sources

- **S3**: distinguish object transfers/size, retries, response content handling, reused client/session and blocking SDK calls inside async handlers.
- **OpenSearch**: inspect query structure, expensive filters/sorts, page size, batching and remote search latency.
- **HTTP external**: identify connection setup, DNS/TLS, retries, timeouts, concurrency and back-pressure.
- **FastAPI**: sync/blocking calls in event loop, unbounded fan-out, serialization, dependency injection, blocking file I/O.
- **Missing spans**: add one business Span around a meaningful phase and re-observe. Do not attribute uninstrumented time to CPU without a profiler.

## Prioritize intelligently

Prioritize where many **collected slow samples** repeat with high latency and a verified code path. Slow-only samples are not endpoint traffic rate or percentiles; get representative full HTTP server spans/metrics for P95/P99 and incident severity. Use a simple evidence table with explicit unknowns; never claim guaranteed latency improvements before bench tests.

## Validation checklist

- Deterministic response equivalence (including permissions, sorting, pagination, nulls and error cases).
- Tests for nonempty/empty large lists and partial missing Mongo lookup documents.
- Inspect query count and critical-path elapsed on matched sample requests.
- Verify against real end-to-end tests and compare p50/p95/p99 on representative traffic if available.
- For any proposed index, discuss storage/write overhead and deployment/rollback; production schema/DB changes only with approval.
