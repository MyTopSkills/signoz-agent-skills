# SigNoz Agent Skills

**Evidence-driven performance diagnosis for FastAPI, from SigNoz traces to real source code.**

Open-source, cross-agent [Agent Skills](https://agentskills.io/) package. Works with **Codex** and **OpenCode** using the same `.agents/skills` installation; Claude Code can use a `.claude/skills` installation. Other agents can read `SKILL.md` manually if they do not implement discovery.

> Status: initial public-ready template, **not yet verified against every SigNoz deployment/version**. The collector expects SigNoz v5 query API. No production environment is bundled.

## Why it exists

- Find HTTP Server spans slower than a threshold (default: 5000 ms)
- Retrieve their nested spans and flag repeated MongoDB calls / long external dependencies
- Estimate non-overlapping interval coverage to locate tracing blind spots
- Export HTML, CSV, JSON and a machine-readable `codex_diagnosis.json` evidence handoff
- Guide a coding agent through **source-backed** performance investigation, without modifying business code by default

### Prerequisites

Python 3.9+, `requests`, SigNoz v5-compatible HTTP API, a read-only SigNoz API key, a working network route to the SigNoz instance, and a coding agent with local file and shell access.

## Two prompts: install once, diagnose in one sentence

For coding agents with local file, shell and network access. Replace `<OWNER>` after publishing the GitHub repository.

**First time — install, configure, and diagnose:**

> Install the `signoz-fastapi-perf` Skill from `https://github.com/<OWNER>/signoz-agent-skills` into the currently open FastAPI project using the repository installer and shared project scope (Codex / OpenCode). Check dependencies and whether `SIGNOZ_URL`, `SIGNOZ_SERVICE`, and `SIGNOZ_API_KEY` are set. Guide me through local configuration if anything is missing; never ask for or print secrets in chat. Remind me to gitignore `.perf-reports/`. Once ready, analyze up to 100 HTTP requests ≥5000 ms from the past 24 hours. Correlate SigNoz traces with source code and generate a performance report. Diagnosis only; do not modify business code.

**Daily — one sentence:**

> Use `signoz-fastapi-perf` to analyze up to 100 HTTP requests ≥5000 ms from the past 24 hours in the current FastAPI project; map SigNoz evidence to source code, propose optimizations, and write a report. Do not change code.

Codex can explicitly invoke `$signoz-fastapi-perf`; OpenCode can use `@signoz-fastapi-perf`. Reload the agent if it does not discover a newly installed Skill. Never paste your API key into a chat.

[Quick prompts (Chinese/English)](docs/QUICK_START_PROMPTS.md) · [Advanced prompts](docs/USAGE_PROMPTS.md)

---

## Installation

Clone this GitHub repository (replace `OWNER` with the publisher's account after uploading):

```bash
git clone https://github.com/OWNER/signoz-agent-skills.git
cd signoz-agent-skills
python3 -m pip install -r requirements.txt
```

Install into your **application project**, not necessarily into this repo:

```bash
python3 scripts/install.py --agent shared --scope project --project /path/to/your-fastapi-repo
```

`--agent shared` installs to `.agents/skills/`, read by both Codex and OpenCode. Other options: `--agent opencode` (`.opencode/skills`), `--agent claude` (`.claude/skills`); `--scope user` installs for the user instead of a single project. To see all options run `python3 scripts/install.py --help`. Existing skills are not overwritten unless you pass `--force`.

Add `.perf-reports/` to your **application's** `.gitignore` (do not replace the project's existing ignore rules).

## Configure (in your application repo)

```bash
export SIGNOZ_URL='https://your-signoz.example.com'
export SIGNOZ_SERVICE='your-fastapi-service'
export SIGNOZ_API_KEY='your-read-only-api-key'   # never commit or paste into agent conversations
```

## Run directly

```bash
python3 .agents/skills/signoz-fastapi-perf/scripts/run.py \
  --hours 24 --threshold-ms 5000 --limit 100 \
  --report-dir .perf-reports/latest
```

## Ask the agent

Codex:

> `$signoz-fastapi-perf Analyze all requests >5000 ms in the past 24 hours, inspect the real FastAPI source files, and write PERFORMANCE_ANALYSIS.md. Analysis only. Do not change code.`

OpenCode:

> `@signoz-fastapi-perf Analyze recent slow FastAPI traces using the installed skill. Locate candidate bottlenecks in source. Do not modify code.`

If no credentials are available but `analysis.json` exists:

```bash
python3 .agents/skills/signoz-fastapi-perf/scripts/run.py --from-existing --report-dir .perf-reports/latest
```

## Complete agent prompts

For a thorough, ready-to-copy diagnosis prompt, single-Trace analysis, offline mode, and explicitly approved optimization workflow, see **[Usage Prompts (Chinese & English)](docs/USAGE_PROMPTS.md)**. Start by installing/configuring the skill above; prompts never need an API key pasted into chat.

## Artifacts

| File | Purpose |
| --- | --- |
| `report.html` | Visual report for reviewing the collected slow samples |
| `endpoint_summary.csv` | Counts and latencies within collected *slow samples*, **not global P95** |
| `slow_requests.csv` | Per-request summaries |
| `spans.csv` | Span-level details |
| `analysis.json` | Original interval and operation-group analysis |
| `codex_diagnosis.json` | Structured **hypotheses** and evidence for any coding agent |
| `CODEX_DIAGNOSIS.md` | Human / agent readable investigation guide |
| `PERFORMANCE_ANALYSIS.md` | Analysis the agent writes after verifying source code |

## Safety and precision

- This skill is **read-only** against SigNoz. It does not autonomously alter databases, indexes, source code or infrastructure.
- Do not commit trace reports, API keys, full request/response bodies, tokens, personal data or production hostnames.
- Duplicate MongoDB spans may indicate N+1 but are not conclusive by themselves.
- Uninstrumented time isn't automatically CPU time; overlapping/nested span durations can't simply be summed.
- Public users should inspect scripts before running them. Treat skills as executable code and instructions.

## Tests

```bash
python3 -m unittest discover -s skills/signoz-fastapi-perf/tests -v
python3 -m compileall -q skills/signoz-fastapi-perf/scripts
```

## Contributing

Issues and pull requests welcome. Start by including a redacted trace fixture, SigNoz API version, steps to reproduce, and expected/actual result. Avoid posting production secrets or personally identifiable data.

## License

MIT. See [LICENSE](LICENSE).
