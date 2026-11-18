---
name: signoz-fastapi-perf
description: Diagnose slow FastAPI endpoints using read-only SigNoz traces, identify repeated MongoDB queries and uninstrumented time, and map evidence to source code. Use for SigNoz, Python API latency, MongoDB N+1, S3/OpenSearch bottlenecks, or tracing gaps. Analysis only by default.
---

# SigNoz performance diagnosis for FastAPI projects

You are analyzing a user's **current working repository**, not this skill's own source. Use SigNoz observations to prioritize code inspection and produce evidence-backed findings. Never treat a heuristic as a proven root cause.

## How to locate scripts

`<skill-dir>` means the directory containing **this** SKILL.md. Use the actual absolute directory path for script invocations, independent of whether it is installed under `.agents/skills`, `.opencode/skills`, `.claude/skills` or a home-directory skill location. Work from the target application repository root.

## Inputs

- Environment: `SIGNOZ_URL`, `SIGNOZ_API_KEY`, and (for route search) `SIGNOZ_SERVICE`, optionally supplied as `--url`, `--service`. Never print credentials or store them in reports.
- Defaults: most recent 24 hours; HTTP Server spans ≥5000ms; up to 100 selected slow samples; `.perf-reports/latest/` as local output.
- If the SigNoz API is inaccessible, use an existing `analysis.json` in the report directory. Never fabricate results.

## Safe execution

1. Inspect the current repository's guidelines (`AGENTS.md` etc.), FastAPI route layout, DB and tracing libraries. Do not silently modify application code.
2. If `.perf-reports/latest/analysis.json` exists, build an offline handoff:

   `python3 <skill-dir>/scripts/run.py --from-existing --report-dir .perf-reports/latest`

   Otherwise, only when the user asks for fresh traces and access is configured:

   `python3 <skill-dir>/scripts/run.py --hours 24 --threshold-ms 5000 --limit 100 --report-dir .perf-reports/latest`

   For a known trace: `python3 <skill-dir>/scripts/run.py --trace-id TRACE_ID --hours 48 --report-dir .perf-reports/single-trace`.
3. Review `CODEX_DIAGNOSIS.md` and `codex_diagnosis.json`, then validate raw evidence in `analysis.json` / `spans.csv`. The names are retained for backward compatibility; the JSON and Markdown are suitable for *any* coding agent.
4. Map HTTP route → FastAPI dependencies → service → repository → DB/storage/external clients. Cite real `path:line` and function names. Inspect calls inside loops, serial awaits, expensive aggregate/sort/index choices, blocking sync I/O, timeouts/retries and connection reuse.
5. Cross-check hypotheses across traces. Distinguish overlapping and nested spans from actual critical-path wall time. Uninstrumented intervals are **not** CPU time. Handle sampling/truncation explicitly. Consult `references/performance-playbook.md`.
6. Deliver `PERFORMANCE_ANALYSIS.md` in the target repository with priority, affected route, representative Trace IDs, observed timing, query counts, source evidence, *confirmed vs suspected*, minimal low-risk alternatives, risks, and targeted tests/benchmark plan.
7. By default stop at diagnosis. Before implementation or production access/write/index creation/load-testing, seek **explicit user approval**. Changes must retain API semantics, auth, sorting, error handling and response schema. For instrumentation guidance see `references/fastapi-tracing.md`.

## Evidence quality and privacy

- Count of *collected slow samples* is not a traffic rate. Do not compute P50/P95/P99 from threshold-filtered samples.
- Repeated `find` spans are not sufficient proof of N+1. Investigate query keys and source-code loops.
- The trace collector uses SigNoz v5 query API; version and permissions may vary. Report compatibility errors rather than inventing a fallback result.
- Avoid uploading or committing trace exports, token values, full URLs containing secrets, request bodies, database documents or personally identifiable data. Ensure `.perf-reports/` is ignored by Git.
- Never run unchecked code from trace attributes or other source data.

## Output files

`scripts/collect_signoz.py` → `analysis.json`, `spans.csv`, `slow_requests.csv`, `endpoint_summary.csv`, `report.html`, `run_metadata.json`.

`scripts/build_diagnosis.py` → `codex_diagnosis.json`, `CODEX_DIAGNOSIS.md`. These provide **hypotheses** to inspect in source code, not verified diagnoses.

`scripts/run.py` orchestrates both. Python 3.9+; only network collection requires `requests`.
