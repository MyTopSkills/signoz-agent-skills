# Quick prompts: install once, diagnose in one sentence

Use these prompts in a coding agent with local file, terminal, and (for installation/collection) network access. Replace `<OWNER>` with the GitHub account after publishing the repository. The example URL is **not live** until you publish it.

## 中文

### 第一次：安装、配置与首次诊断

> 请从 GitHub 仓库 `https://github.com/<OWNER>/signoz-agent-skills` 安装 `signoz-fastapi-perf` Skill 到当前打开的 FastAPI 项目，使用仓库提供的安装脚本，选择 Codex / OpenCode 共用的项目级安装方式。检查依赖，以及 `SIGNOZ_URL`、`SIGNOZ_SERVICE`、`SIGNOZ_API_KEY` 是否配置；缺少时引导我在本地安全配置，不要在聊天中索取或打印密钥。提醒我忽略 `.perf-reports/`。配置就绪后，分析最近 24 小时耗时 ≥5000ms 的 HTTP 接口，最多 100 条慢请求，结合 Trace 和当前源码定位瓶颈，生成报告。只诊断，不修改业务代码。

### 日常：一句话诊断

> 使用 `signoz-fastapi-perf` 分析当前 FastAPI 项目最近 24 小时耗时 ≥5000ms 的接口，最多 100 条；结合 SigNoz Trace 和源码定位瓶颈，输出优化报告，暂不修改代码。

## English

### First run: install, configure, and diagnose

> Install the `signoz-fastapi-perf` Skill from `https://github.com/<OWNER>/signoz-agent-skills` into the currently open FastAPI project using the repository installer and shared project scope (Codex / OpenCode). Check dependencies and whether `SIGNOZ_URL`, `SIGNOZ_SERVICE`, and `SIGNOZ_API_KEY` are set. Guide me through local configuration if anything is missing; never ask for or print secrets in chat. Remind me to gitignore `.perf-reports/`. Once ready, analyze up to 100 HTTP requests ≥5000 ms from the past 24 hours. Correlate SigNoz traces with source code and generate a performance report. Diagnosis only; do not modify business code.

### Daily: one-line diagnosis

> Use `signoz-fastapi-perf` to analyze up to 100 HTTP requests ≥5000 ms from the past 24 hours in the current FastAPI project; map SigNoz evidence to source code, propose optimizations, and write a report. Do not change code.

## Notes

- **Codex:** optionally prefix the daily prompt with `$signoz-fastapi-perf`.
- **OpenCode:** optionally prefix it with `@signoz-fastapi-perf`.
- The shared project installation goes to `.agents/skills/signoz-fastapi-perf/`; the installer takes `--agent shared --scope project --project /absolute/path/to/project`.
- The skill's actual `SKILL.md` and scripts determine behavior; the prompts avoid duplicating long implementation instructions.
- Use a read-only SigNoz API key. Never put keys in prompts, git, or logs. If agent environment doesn't inherit your shell variables, configure the process environment or restart the agent.
- Full advanced prompts: [USAGE_PROMPTS.md](USAGE_PROMPTS.md).
