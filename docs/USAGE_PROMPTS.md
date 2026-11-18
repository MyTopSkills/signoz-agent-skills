# Ready-to-use agent prompts / 可直接复制的使用提示词

These prompts work with the `signoz-fastapi-perf` Agent Skill in this repository. **Install the skill into the target application first.** They are written for coding agents with local-file and terminal access. Never paste your API key into a prompt or repository.

**Want the shortest workflow?** Start with [two copy-paste prompts](QUICK_START_PROMPTS.md): first-time installation + daily one-liner. This page covers optional advanced cases.

## 0. First-time setup / 首次安装（先阅读）

In a local terminal, from the cloned `signoz-agent-skills` source repository:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/install.py --agent shared --scope project --project /absolute/path/to/your-fastapi-repo
```

Then, in the application repository's terminal environment (not in chat):

```bash
export SIGNOZ_URL='https://your-signoz.example.com'
export SIGNOZ_SERVICE='your-fastapi-service'
export SIGNOZ_API_KEY='your-read-only-api-key'
```

Add `.perf-reports/` to the **application project's** `.gitignore`. Restart/reload the coding agent if it does not discover newly installed skills. An API key alone does not guarantee permission or network access to SigNoz.

- Codex: invoke `$signoz-fastapi-perf` (installed at `.agents/skills/signoz-fastapi-perf/`).
- OpenCode: invoke `@signoz-fastapi-perf` (same `.agents/skills/` installation).
- Other agents: ask the agent to read `.agents/skills/signoz-fastapi-perf/SKILL.md` directly if it has local-file access but no skill discovery.

## 1. Full prompt (Chinese, recommended) / 完整中文诊断提示词

Copy the text below into the coding agent **while the target FastAPI repository is open**. In Codex, begin with `$signoz-fastapi-perf`; in OpenCode, begin with `@signoz-fastapi-perf`.

> 使用已安装的 `signoz-fastapi-perf` Skill，面向**当前打开的 FastAPI 项目**执行一次“SigNoz 慢接口性能诊断”。请严格遵循 SKILL.md 及当前项目的 AGENTS.md / 开发约束。
>
> **分析范围**：使用环境变量 `SIGNOZ_URL`、`SIGNOZ_SERVICE`、`SIGNOZ_API_KEY`；查询最近 **24 小时**，筛选 **HTTP Server Span 耗时 ≥ 5000ms** 的请求，最多获取 **100 个慢请求样本**，输出到 `.perf-reports/latest/`。如需专门分析某条 Trace，我会另给 Trace ID。
>
> **第一步：环境和安全检查**
> - 确认 Skill 已安装、Python 版本与 requests 依赖满足要求，读取 Skill 的实际脚本路径和支持参数，不要猜测 API 或命令。
> - 检查配置存在与否，只显示配置项是否就绪，不要输出、记录或上传 API Key、请求体、用户敏感字段。
> - 确认 `.perf-reports/` 已被 `.gitignore` 忽略；如果没有，**先提示我**，不要为此擅自修改项目文件。
> - 默认只读：不修改业务代码、数据库、索引、生产配置，也不执行生产压测。
>
> **第二步：获取可观测性证据**
> - 当 API 已配置且可访问时，运行 Skill 的 `scripts/run.py`，参数：`--hours 24 --threshold-ms 5000 --limit 100 --report-dir .perf-reports/latest`。
> - 读取 `analysis.json`、`spans.csv`、`slow_requests.csv`、`endpoint_summary.csv`、`codex_diagnosis.json` 和 `CODEX_DIAGNOSIS.md`；需要时参考 `report.html`。
> - 如果 SigNoz 无法访问但已有 `.perf-reports/latest/analysis.json`，可执行 `--from-existing` 离线诊断，并明确说明数据采集时间。两者都不可用则报告障碍，不要编造数据。
>
> **第三步：按接口找慢在哪里**
> - 聚合同一接口的慢请求，给出代表 Trace ID、最慢请求、重复出现次数及最有价值的调查方向。
> - 分析 MongoDB、S3、HTTP、OpenSearch 及业务 Span，重点识别：重复 find、疑似 N+1、循环里的 await、串行/并发关系、超时重试、阻塞 I/O、较慢单次操作、未覆盖的业务等待。
> - 定位最长 Span 与关键路径上的主要延迟，区分嵌套与并行 Span。不可将重叠 Span 耗时直接相加当作请求耗时；未覆盖时间不等于 CPU 时间。
> - 将发现分成“Trace 直接观察到的事实”“代码确认的根因”“有待验证的假设”，为每项给出证据和可信度。重复 MongoDB find 只能先标记为疑似 N+1。
>
> **第四步：和当前 FastAPI 源码对应**
> - 从 Route → Depends/中间件 → Service → Repository/DAO → MongoDB/S3/HTTP/OpenSearch 逐层定位。
> - 写明**真实文件路径、函数名、行号**以及 Trace ID；找不到代码时标注无法定位，不得虚构。
> - 检查循环内查询、批量 `$in` 可行性、分页/排序与权限边界、MongoDB 索引建议、同步阻塞调用、客户端复用、外部服务重试与超时。
> - 解释每个优化方案是否会影响响应结构、用户权限、结果顺序、分页、缺失值、异常处理等业务语义。
>
> **第五步：输出正式报告，不直接修改业务**
> - 在当前项目根目录生成 `PERFORMANCE_ANALYSIS.md`。
> - 报告至少包含：慢接口排行；逐接口耗时与 Trace 证据；已确认/待验证根因；代码位置；按 P0/P1/P2 排序的低风险优化建议；缺失的业务 Span 及埋点建议；验证测试和回滚风险；需要我进一步提供的访问条件。
> - **不要**把仅从 `≥5000ms` 筛出的慢样本算作全量接口流量、P50/P95/P99；如需要这些指标，说明必须使用全量/有代表性的请求样本或指标数据。
> - 最终在对话中用简洁表格总结最值得处理的 **前 5 个问题**，包含优先级、接口、证据、代码位置、置信度、建议和验证方式。
> - 先完成诊断并停下来，**得到我明确授权之后**才可以修改代码、运行有负载风险的测试或执行任何数据库/索引变更。

## 2. Full prompt (English) / 英文通用版

> Use the installed `signoz-fastapi-perf` Skill in the **currently open FastAPI repository**, following its SKILL.md and any project AGENTS.md instructions. Run a **read-only** investigation of slow HTTP Server requests in the **last 24 hours**, threshold **≥5000 ms**, up to **100 slow samples**, writing evidence to `.perf-reports/latest/`. Read connection and service settings only from `SIGNOZ_URL`, `SIGNOZ_SERVICE`, and `SIGNOZ_API_KEY`; never print or store secrets.
>
> Verify skill discovery, script parameters, dependencies and `.perf-reports/` gitignore status before execution. Run `scripts/run.py --hours 24 --threshold-ms 5000 --limit 100 --report-dir .perf-reports/latest` using the installed skill's real absolute path. If the API is unavailable but `analysis.json` already exists, use `--from-existing` and label the data age. Otherwise, disclose the blocker and do not fabricate results.
>
> Analyze `analysis.json`, `spans.csv`, `slow_requests.csv`, `endpoint_summary.csv`, `codex_diagnosis.json`, and `CODEX_DIAGNOSIS.md`. For each high-priority endpoint, compare representative traces, quantify repeated MongoDB operations and slow S3/HTTP/OpenSearch calls, investigate serial awaits / retries / tracing blind spots, and differentiate observed facts, suspected causes, and source-verified root causes. Never sum nested or overlapping span times as wall-clock latency. Uncovered time is not automatically CPU time; repeated DB spans alone do not prove N+1.
>
> Trace the actual FastAPI route through dependencies, middleware, service, and repository to external operations. Cite verified file paths, functions, line numbers and Trace IDs; never invent locations. Propose minimal, low-risk fixes with notes on auth, pagination, ordering, errors, missing records and response-schema compatibility. Generate `PERFORMANCE_ANALYSIS.md` with a ranked P0/P1/P2 findings table, evidence, confidence levels, code locations, proposed optimizations, instrumentation gaps and an equivalence/benchmark plan. Summarize the top five findings in the chat. **Do not change application code, production state, indexes, or run load tests without explicit approval.** Do not calculate whole-service P95/P99 from slow-only samples.

## 3. Follow-up prompts / 常用后续提示词

### Diagnose one known Trace / 指定 Trace ID

> `$signoz-fastapi-perf` 针对 `TRACE_ID`（替换为实际 ID）拉取完整 Trace，使用 `--trace-id TRACE_ID --hours 48 --report-dir .perf-reports/single-trace`；结合当前 FastAPI 源码定位关键路径、重复 MongoDB 查询和未被埋点的耗时，写报告。只分析，不修改业务代码。

### Offline diagnosis / 离线复用历史报告

> `$signoz-fastapi-perf` 不访问 SigNoz，只使用 `.perf-reports/latest/analysis.json`，运行 `--from-existing --report-dir .perf-reports/latest`，然后结合当前仓库源码生成 `PERFORMANCE_ANALYSIS.md`，标记数据时间和证据不足之处。不要修改业务代码。

### Approved optimization / 用户确认后再优化

> 已批准优化 `接口路径` 的 `明确问题`。只修改此前报告中已验证的相关代码，保持鉴权、请求响应、排序分页、异常行为完全一致。先补回归测试，再做最小改动。对比优化前后的 MongoDB 查询数量、匹配负载下的端到端耗时与关键 Trace，报告结果及无法验证的部分。禁止在未经单独批准时修改生产数据库索引或执行生产压测。

## 4. What users get / 交付结果

- `.perf-reports/latest/report.html` — local trace visualization.
- `.perf-reports/latest/codex_diagnosis.json` — machine-readable evidence and **hypotheses**, usable by different agents despite the legacy name.
- `.perf-reports/latest/CODEX_DIAGNOSIS.md` — evidence handoff.
- `PERFORMANCE_ANALYSIS.md` — source-checked analysis produced by the coding agent.

**Compatibility note:** The collector targets the SigNoz **v5 query API**. Instances can vary; verify against your deployment. The project is an initial template, not a guarantee of compatibility with every SigNoz installation.
