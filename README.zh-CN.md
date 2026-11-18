# SigNoz Agent Skills｜通用 AI Agent 慢接口诊断

这是一个可发布到 GitHub 的跨 Agent Skill，遵循 [Agent Skills](https://agentskills.io/) 标准。Codex、OpenCode 均可从 `.agents/skills` 读取；其他 Agent 如支持该标准也可安装，或手动读取 `SKILL.md`。

**主要能力**：用 SigNoz v5 HTTP API 筛选超过阈值（默认 5000ms）的 FastAPI HTTP Server 请求，拉取 Trace、统计 MongoDB/S3/HTTP/OpenSearch 调用及未覆盖区间，生成 `codex_diagnosis.json` 等证据文件，然后由 Agent 结合真实源码定位瓶颈。默认**只分析，不修改代码和数据库**。

## 两段提示词，快速开始

适用于能访问本地终端和文件的 Codex / OpenCode 等 Agent。**首次安装一段提示词，日常诊断一句话。** 请在发布仓库后将 `<OWNER>` 替换为真实 GitHub 用户名。

### ① 首次安装（直接复制给 Agent）

> 请从 GitHub 仓库 `https://github.com/<OWNER>/signoz-agent-skills` 安装 `signoz-fastapi-perf` Skill 到当前打开的 FastAPI 项目，使用仓库提供的安装脚本，选择 Codex / OpenCode 共用的项目级安装方式。检查依赖，以及 `SIGNOZ_URL`、`SIGNOZ_SERVICE`、`SIGNOZ_API_KEY` 是否配置；缺少时引导我在本地安全配置，不要在聊天中索取或打印密钥。提醒我忽略 `.perf-reports/`。配置就绪后，分析最近 24 小时耗时 ≥5000ms 的 HTTP 接口，最多 100 条慢请求，结合 Trace 和当前源码定位瓶颈，生成报告。只诊断，不修改业务代码。

### ② 日常使用（直接复制给 Agent）

> 使用 `signoz-fastapi-perf` 分析当前 FastAPI 项目最近 24 小时耗时 ≥5000ms 的接口，最多 100 条；结合 SigNoz Trace 和源码定位瓶颈，输出优化报告，暂不修改代码。

第一次安装后，如果 Agent 未识别到新 Skill，请重新加载 Agent。Codex 可显式使用 `$signoz-fastapi-perf`，OpenCode 可显式使用 `@signoz-fastapi-perf`。**不要把 API Key 发进聊天。**

[中英文快速提示词](docs/QUICK_START_PROMPTS.md) · [高级场景提示词](docs/USAGE_PROMPTS.md)

---

## 安装

将本仓库克隆到本地后运行：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/install.py --agent shared --scope project --project /path/to/your-fastapi-project
```

`shared` 会安装到目标项目的 `.agents/skills/`，供 Codex 和 OpenCode 共用。`--scope user` 可安装到用户级。`--agent opencode` 或 `claude` 可使用各自独立目录。

在目标项目配置：

```bash
export SIGNOZ_URL='https://your-signoz.example.com'
export SIGNOZ_SERVICE='your-fastapi-service'
export SIGNOZ_API_KEY='你的只读 SigNoz API Key'
```

然后执行：

```bash
python3 .agents/skills/signoz-fastapi-perf/scripts/run.py \
  --hours 24 --threshold-ms 5000 --limit 100 \
  --report-dir .perf-reports/latest
```

在 Codex 中输入：`$signoz-fastapi-perf 分析最近24小时5000ms以上的请求，定位代码瓶颈，仅生成报告，不修改代码。`

OpenCode 中可输入：`@signoz-fastapi-perf 分析最近24小时慢接口，结合代码给出优化建议。`

**安全提醒**：把 `.perf-reports/` 添加到目标项目 `.gitignore`，不要提交真实 Trace、API Key、客户信息或私有服务地址；真实生产 API 兼容性需要使用者自行验证。见 [英文 README](README.md) 获取完整说明。

## 完整使用提示词（可直接复制到 Codex / OpenCode）

除了上面的简短示例，已提供**[完整中英文提示词及常见场景](docs/USAGE_PROMPTS.md)**，包括首次运行前检查、批量慢接口分析、指定 Trace ID、离线诊断和经授权后的优化流程。请勿把 API Key 粘贴到对话。
