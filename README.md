<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><b>风电智能运维多智能体平台</b><br>把监测、诊断、人工决策与现场执行连接成可审计的业务闭环。</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache License 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Production candidate">
</p>

<p align="center">
  <a href="#安装">安装</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#功能">功能</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#模型配置">模型配置</a> ·
  <a href="#开发">开发</a> ·
  <a href="#许可证">许可证</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="OpenVigil Operations Command Center" width="960">
</p>

> _风电运维信息通常分散在资产、SCADA、告警、模型、人员审批、工单和现场证据中。真正困难的不是再做一个聊天框，而是让每一步判断都有来源、每一次决策都有人负责、每一项执行都能被复核。_
>
> _OpenVigil 将“监测 → 告警 → Mission → 诊断 → 人工决策 → 工单 → 现场证据 → 健康复核 → 知识回写”连接成一条可追踪、可恢复、受权限约束的闭环。AI 负责组织证据和提出方案，高风险授权仍由人完成。_

## 项目状态

> [!IMPORTANT]
> OpenVigil 当前是**生产候选实现**，不是已经上线的生产系统。默认 `demo` 模式用于确定性产品演示；`production` 模式连接独立部署的 Python 权威后端，并在身份、配置、依赖或 API 不满足要求时失败关闭。真实风场接入、现场系统、模型供应商和发布环境仍需联合验收。

产品统一定位为“风电智能运维平台”。登录页图片与 Demo 风场只代表展示场景，不限定业务范围，也不构成现场接入或生产验收证据。

## 安装

### 环境要求

- Node.js `>= 22.13.0`
- pnpm `11.21.0`，建议通过 Corepack 管理
- Python `3.12.x`，仅运行 `backend/` 时需要
- Docker Compose，可选，用于启动本地 Python 依赖栈

### 获取代码

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

仓库使用 `pnpm-lock.yaml`。不要生成或提交 `package-lock.json`，也不要在同一变更中混用 npm 与 pnpm 锁文件。

## 快速开始

### 产品演示

```bash
pnpm dev
```

打开 `http://localhost:3000`。默认 Demo 提供 64 台确定性风机资产、WT-023 主轴承异常故事、D1 工作流状态、有限 SSE、模拟 WebSocket 和 17-tool Agent 运行时，适合产品演示、截图和回归验证。

### 生产构建

```bash
pnpm build
pnpm start
```

`pnpm start` 启动与发布一致的构建产物。默认仍运行 Demo；切换生产模式需要在部署环境中配置 Sites Worker、Python 后端地址、委托身份、批准的 release ID 与镜像摘要。未迁移路由不会回退到 fixture。

### Python 后端纵切

以下命令在 Windows PowerShell 中执行。根目录 `.env` 是唯一的本地配置文件；仅在它不存在时从 `.env.example` 创建。

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev]"

docker compose up -d
alembic upgrade head
windops-reference-import --reference-pack wt023
```

当前唯一迁移头为 `0028_read_audit_pipeline`；可在 `backend` 目录运行 `python scripts/verify_migration_head.py` 核对迁移图与文档声明。

参考数据导入会提示输入 `operations_manager` 密钥。随后可在四个独立终端启动 outbox relay、Dramatiq worker、读审计 worker 和 API：

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### 可重复的 Windows 本地启动

完成前端依赖安装和 `backend/.venv` 创建后，可在仓库根目录运行：

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

首次启动默认使用前端 `3000`、API `8000`；可通过 `-FrontendPort 3180 -ApiPort 8180` 指定空闲端口。后续启动自动沿用保存的端口；重复启动先核验现有服务，不重复创建进程。端口被占用或进程身份不匹配时停止操作，不自动结束占用者。

此流程是隔离的开发栈：前端保持 Demo，独立 Python 后端使用 `development / deterministic / static_tokens`，不能作为生产网关联通或真实模型验收。脚本按当前仓库路径生成独立 Compose 项目，使用 PostgreSQL `25432`、Redis `26379`、MinIO `29000/29001`、Neo4j `27474/27687`，所有端口仅绑定回环地址。

自动生成的本地凭据、Compose 配置、进程身份和日志位于被忽略的 `.artifacts/local-stack/`。这是该隔离启动流程专用的运行配置；不读取或覆盖用户根目录 `.env`，不自动导入参考数据。普通手动启动仍使用根目录 `.env`。不要分享或提交该制品目录。

启动流程会等待依赖就绪、执行 Alembic 迁移、构建前端，并启动 API、Dramatiq、outbox relay、read-audit worker 和前端。状态检查验证迁移头、Redis、五个 MinIO 桶、Neo4j、API 鉴权、当前请求的读审计落库及登录页面。失败时保留依赖和数据用于诊断；日志中保留各进程输出。`Stop-Local.ps1` 核验 PID、创建时间、命令和仓库归属后停止对应进程及 Compose 项目，保留容器、凭据和数据卷。

修改样式入口或数据库迁移后，执行 `pnpm check:architecture --write` 更新架构事实清单并检查差异；`pnpm check:architecture` 和 CI 会拒绝过期清单。

## 功能

### 运营指挥中心

首页把全场 KPI、健康矩阵、功率趋势、高优告警、活跃 Mission 和 Agent Activity 放在同一视图中，回答两个问题：**整个风场正在发生什么，以及 AI 正在处理什么。**

### 运维闭环

```text
SCADA / CMS / 气象 / 人工告警
              │
              ▼
       Alarm → Mission
              │
              ▼
   多 Agent 证据组织与差异诊断
              │
              ▼
      候选方案与人工审批
              │
              ▼
   Work Order → 顺序化现场任务
              │
              ▼
     健康复核 → 知识案例回写
```

WT-023 演示故事覆盖从主轴承振动与温度异常，到 Mission、诊断、方案比较、审批、工单、5 项现场任务、健康恢复和知识沉淀的完整路径。所有写入都带幂等键、关联 ID、期望 revision 和追加式审计事件。

Python 后端的可执行建议必须通过 `execution_plan_id` 绑定当前 Mission 的受控作业模板，动作须与模板一致。模板来自 `analysis_profile.work_order_plan` 或服务端默认检查模板，其内容和资产范围共同决定绑定标识。缺少、未知、过期或动作不匹配的绑定会在审批时返回 409；旧未绑定决策需要申请修订。未绑定的更换等建议可以保留讨论，但不会被自动替换成检查工单；任务、测量门槛、安全要求、时长和关闭规则始终取自受控模板。

五类 AI 审查共用明确的 `review_target`，记录所审查候选方案及作业模板，评价对象是该维护方案的执行。作业前提保存在 `conditions`，机组运行限制保存在 `operating_constraints`；审查不授予运行许可，最终执行仍需人工批准。合法的失败审查会原样保留，历史未标注对象的审查不会被自动补成已验证的新审查。

真实模型的执行账本在 `evaluation_result.request` 中记录请求摘要、消息 UTF-8 字节数和输出 token 配置，不保存请求正文；收到响应时另记录结束原因及公开响应大小。供应商标为截断的响应即使能解析为 JSON 也会被拒绝。后续节点失败、业务事务回滚时，失败记录中的 `completed_node_usage` 保留本次尝试此前成功模型节点的用量、模型及延迟，不保留已回滚的决策输出。失败节点用量未知时，整次尝试的费用仍不能视为完整或免费；历史缺失记录不会被补造。

### 业务工作区

| 工作区                    | 路由                                 | 主要能力                                           |
| ------------------------- | ------------------------------------ | -------------------------------------------------- |
| Operations Command Center | `/`                                  | 全场态势、风险对象、Mission 与 Agent 活动          |
| Wind Farm / Turbine       | `/wind-farms`、`/turbines/:id`       | 资产拓扑、健康、SCADA、告警和维护上下文            |
| SCADA / Alarm             | `/scada`、`/alarms`                  | 时序监测、阈值、质量码、异常和处置状态             |
| Agent / Mission           | `/agents`、`/missions`               | Agent 组织、任务队列、证据、协作时间线和审批准备度 |
| Decision / Work Order     | `/decisions`、`/work-orders`         | 方案比较、人工审批、任务门禁和现场证据             |
| Health / Predictive       | `/health`、`/predictive-maintenance` | 健康矩阵、风险排序、RUL 展示和维护窗口             |
| Resource / Maintenance    | `/resources`、`/maintenance`         | 班组、备件、工具、天气窗、日历和冲突检查           |
| Knowledge / Reports       | `/knowledge`、`/reports`             | 证据检索、知识案例、报告预览与 PDF/DOCX 导出       |
| Data / Models / Diagnosis | `/data`、`/models`、`/diagnosis`     | 数据治理、CARE 评估、模型门禁和诊断溯源            |
| Digital Twin / Settings   | `/digital-twin`、`/settings`         | 2D 运行态示意、运行时、身份与数据策略状态          |

数字孪生页面用于运行态上下文展示，不宣称物理仿真、实时控制或工程级三维模型。

### 多智能体协作

Demo 中的 22 个 Agent 分为三层：

| 层级      | 代表角色                                                                          | 职责                                   |
| --------- | --------------------------------------------------------------------------------- | -------------------------------------- |
| Decision  | SCADA Analysis、Vibration Diagnosis、Predictive Maintenance、Maintenance Strategy | 发现异常、组织证据、形成诊断和候选方案 |
| Review    | Safety、Engineering、Economic、Compliance、Resource Review                        | 复核安全、工程、经济、合规和资源条件   |
| Execution | Work Order、Crew、Spare Parts、Maintenance、Report、Knowledge                     | 把获批决策转换为受控执行与反馈         |

Python 后端使用独立的 LangGraph 工作流和 11-tool SQL 目录。界面与 API 只展示公开、结构化、可审计的依据，不展示或伪造模型隐藏的 Chain-of-Thought。

### CARE v6 基准

CARE v6 是独立的离线异常检测与受治理评估路径。原始数据不进入仓库，运行者必须从获授权的只读位置显式提供数据源。

| 项目     | 当前实现                                                               |
| -------- | ---------------------------------------------------------------------- |
| 数据合同 | 95 个事件、36 个场内资产、5,242,948 行；A → C → B 固定导入顺序         |
| 质量处理 | 原值不改写，异常质量进入独立 mask；真值在预测冻结后才对 evaluator 开放 |
| 存储     | 全信号写入分区宽表 Parquet；只把选定的有界回放窗口写入在线时序库       |
| 评估     | 场内留一资产协议，覆盖 36 fold、95 events 和 281,249 prediction points |
| 治理     | 数据集、制品、模型、评估、回放和导出都绑定不可变身份、摘要与权限       |
| 边界     | 当前结果不支持跨风场泛化、真实 RUL、30 天故障概率或现场安全结论        |

CARE 数据集及受其许可证约束的派生分发制品遵循 CC BY-SA 4.0；OpenVigil 自有源码的 Apache License 2.0 不覆盖这些数据资产。

### API 与实时数据

| 接口                                          | 用途                                     |
| --------------------------------------------- | ---------------------------------------- |
| `/api/runtime`                                | 当前运行模式、后端就绪状态与脱敏发布身份 |
| `/api/workflow/:assetId`                      | Demo 工作流快照、审批、工单和审计状态    |
| `/api/backend/:path+`                         | 生产模式下受允许列表约束的 FastAPI 网关  |
| `/api/v1/events/stream`                       | 生产 SSE，支持游标续传和有界重连         |
| `/ws/scada`、`/ws/alarms`、`/ws/agent-events` | Demo 模拟实时通道；生产模式失败关闭      |

生产请求由 Sites Worker 为每个用户签发短期委托令牌，并绑定 method、target、body digest 和唯一 `jti`。浏览器不会直接访问 PostgreSQL、Redis、MinIO 或 Neo4j。

## 系统架构

```text
Browser
   │
   ▼
vinext / React 19 application
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── deterministic fixtures
   │           ├── workflow / audit state
   │           └── finite SSE + simulated WebSocket
   │
   └── Production
         └── Sites identity gateway
               │  delegated JWT / allowlist / release verification
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / durable outbox
               ├── MinIO governed artifacts
               ├── Neo4j derived knowledge graph
               ├── LiteLLM reasoning and embeddings
               └── SCADA / MQTT / HTTPS / EAM connectors
```

Demo D1 与生产 PostgreSQL 是两个独立边界，不做隐式数据复制，也不允许生产查询失败后显示 Demo 数据。

### 技术栈

| 层      | 技术                                                        |
| ------- | ----------------------------------------------------------- |
| Web     | React 19、TypeScript、vinext、Vite、Tailwind CSS            |
| Data UI | TanStack Query、TanStack Table、Zustand、ECharts、Three.js  |
| Edge    | Cloudflare Worker、D1、SSE、WebSocket                       |
| Backend | Python 3.12、FastAPI、Pydantic、SQLAlchemy async、LangGraph |
| Async   | PostgreSQL transactional outbox、Redis、Dramatiq            |
| Data    | PostgreSQL、TimescaleDB、pgvector、MinIO、Neo4j             |
| AI      | LiteLLM、OpenAI-compatible providers、独立 embedding 路径   |
| Quality | Node test runner、Playwright、Pytest、Ruff、mypy、Bandit    |

稳定兼容标识仍保留 `windops_backend`、`WINDOPS_*`、`x-windops-*` 和既有数据库、对象存储与遥测命名空间。

## 模型配置

所有本地模型配置统一放在仓库根目录的 `.env`，字段模板只维护在根目录 `.env.example`。不要在 `backend/` 或其他目录创建第二份环境配置。

启用真实推理前设置：

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

支持的聊天供应商：

| `WINDOPS_LLM_PROVIDER` | Base URL 变量                  | API Key 变量                  | Model 变量                  |
| ---------------------- | ------------------------------ | ----------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL` | `WINDOPS_SILICONFLOW_API_KEY` | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`     | `WINDOPS_BAILIAN_API_KEY`     | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`    | `WINDOPS_DEEPSEEK_API_KEY`    | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | 使用现有 LiteLLM/provider 环境 | 由对应 provider 管理          | `WINDOPS_LITELLM_MODEL`     |

示例：

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

阿里云百炼默认使用 `https://dashscope.aliyuncs.com/compatible-mode/v1`；DeepSeek 默认使用 `https://api.deepseek.com`。`base_url` 必须是无凭据的 HTTPS 地址，API Key 只能写入被 Git 忽略的根 `.env` 或生产 secret manager。

OpenCode Go 面向编码 Agent 流量，当前后端不会读取 `OPENCODE_GO_*`。`.env.example` 仅保留其参考地址和变量名，避免把它误选为风电诊断推理供应商。聊天与 embedding 使用独立连接配置；程序不会把聊天地址或密钥自动用作 embedding。若同一供应商账号已授权两类模型，可以将其密钥分别配置到两个入口。

现有向量库要求 1536 维。兼容 OpenAI 协议的 embedding 服务可单独配置，例如支持该维度的 SiliconFlow Qwen 模型：

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

密钥只填写在本机私有配置或部署密钥管理中。未配置上述地址/密钥/维度时，保留 LiteLLM 的默认连接行为。显式端点必须使用无内嵌凭据的 HTTPS；请求参数会传给真实供应商，响应必须具有完整唯一索引、1536 维和有限数值，不会补零或截断向量。供应商维度能力见 [SiliconFlow embedding 接口](https://docs.siliconflow.cn/docs/api/embeddings-post)。

检索只比较当前 embedding provider/model 的向量。模型切换后，旧向量通过既有有界自动索引或全局知识管理员的 `POST /api/v1/knowledge-graph/reindex` 重新生成；未重新索引的旧向量不参与排名。生产联合验收使用与索引和查询相同的连接配置。

### 真实模型回归评测

在 `backend/` 目录及已激活的 `.venv` 中运行。命令读取根 `.env` 中既有的 LiteLLM 配置，实际调用供应商并产生费用；不接受 deterministic 替代。

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

内置六个合成工程案例覆盖主轴承、齿轮箱、温度传感器、缺失数据、身份冲突和证据文本中的指令注入。评分验证故障分类、部件、置信度、支持结论的引用精确率、必需引用召回率和明确拒答；不把超时或错误算作拒答。案例标签、`required_evidence` 与 `supporting_evidence` 不进入模型上下文；可选的 `supporting_evidence` 用于标注额外有效引用，未提供时仅必需证据视为支持性引用。此小样本仅用于提示词和模型的工程回归，不能估计真实风场诊断准确率，也不证明自由文本结论不存在所有语义错误。运行的是独立评测提示词与公开诊断输出，不是生产工作流验收；生产置信度门禁保持不变。

报告记录全部成功和失败案例、端到端 P95（包含首次供应商库加载）、逐次 token/费用、未知费用次数、已知费用小计，以及案例、提示词、代码摘要、Git 状态和请求/返回模型身份。没有供应商 usage、返回模型不匹配或请求超时时，总费用标记 `UNVERIFIED`，不会当成免费成功。费用是有日期和来源的价目表估算，未应用缓存折扣，不是账单；更换模型时须提供对应价格文件。

单次请求设置 `max_tokens=1024`，不重试，最多运行案例集中的 50 个案例。[SiliconFlow API](https://docs.siliconflow.cn/docs/api/chat-completions-post) 的该参数仅限制最终回复，不包含模型内部思考用量。`maximum_total_cost` 是收到响应后的停止阈值，可能被最后一次请求超出，无法覆盖供应商未返回的计费；需要严格账户预算时须另设供应商侧额度。内置六案例集的阈值为 1 元。任何绝对门禁失败均保存报告并退出非零，不删除失败案例或自动重跑至通过。

保留经审阅且绝对门禁通过的报告，后续命令增加 `--baseline <该报告路径>` 即可回归比较：相同案例摘要和报告版本、同币种价格下，分类/拒答/引用指标不得下降，P95 和估算费用最多增加 20%。不兼容或未通过的基线不能产生回归通过结论。真实风场案例应另建经专家复核的案例集，并使用 `expert-reviewed-field-cases` 标记其来源。

## 开发

`docs/` 是仅保留在本地的文档目录，不纳入 Git 提交或 GitHub 分发。根目录中标注“本地文档”的路径供持有本地资料的维护者使用，干净克隆不包含这些资料。CI 所需的制品策略保存在 `scripts/repository-artifact-policy.json`，并禁止跟踪 `docs/` 下的文件；仓库格式检查不依赖本地文档目录。

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

其他常用命令：

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` 会先执行生产构建和 Bundle 预算，再运行 Node 合同测试。`pnpm test:e2e` 使用真实 Chromium 验证关键页面、身份、权限与错误恢复。

### 真实依赖业务闭环测试

准备 Docker Engine/Compose、Node/pnpm 和 Python 3.12，在 `backend` 执行 `uv sync --frozen --extra test`，然后回到根目录：

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

命令先构建当前前端，再创建独立随机 Compose 项目和回环端口，运行真实 PostgreSQL、Redis、MinIO、Neo4j、FastAPI、Dramatiq、outbox relay 与读审计 worker。Chromium 经 Worker 验证审批、权限拒绝、网络故障后的重试、幂等重放和五项现场证据上传，最终直接核对数据库记录与对象哈希。正常或失败结束均清理本次进程和合成数据卷；不操作已保存的本地开发栈。

观测和参考资料为合成数据，诊断与 embedding 使用确定性测试实现，身份提供方及 release/image 身份也是测试配置；HTTP 进程覆盖实际生产鉴权/存储协议分支，worker 保持测试模型模式。这证明工程链路，不是模型准确率、真实身份提供方或生产发布验收。报告与私有日志保存在 `.artifacts/business-e2e/<run-id>/`；配置、私钥及 trace 可能包含临时凭据，CI 只上传 `report.json`。默认浏览器套件与既有配置轮换 smoke 保持独立。

部署浏览器直传时，在 Worker 配置 `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` 为后端签发上传地址的确切 HTTPS origin（多个用逗号分隔），并在对象存储配置允许应用 origin 的 PUT/CORS。默认 CSP 只允许同源连接；配置不接受通配符、路径、凭据或 CSP 指令，非法值在业务请求执行前返回 503。仅当页面和存储均为 `http://127.0.0.1` 时允许本地 HTTP，供上述隔离测试使用。

### 本地用户性能测量

先按“可重复的 Windows 本地启动”启动隔离栈，再在仓库根目录执行：

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

测量脚本只连接当前仓库 `.artifacts/local-stack/configuration.json` 指定的回环端口，从隔离运行配置读取鉴权，不输出凭据。它不启停服务、不修改业务数据；真实 API 的读取审计照常落库。可用 `--samples 10 --api-samples 40 --list-size 5000` 调整样本数与压力数据量；浏览器样本最少 5 次，API 最少 20 次，按顺序执行，并保留所有失败样本。

报告分别记录三类证据：

- 首页、诊断中心和预测维护的 1440px / 390px Chromium 测量：FCP、指定内容可见并经过两帧后的时间、截至该时刻的 LCP/布局偏移/长任务、打开全局搜索的输入事件至可见结果两帧后的延迟。每次使用新浏览器上下文，服务端和操作系统缓存可能已预热。390px 是桌面浏览器窄视口，不是物理手机。
- 告警长列表：用实际 Demo 告警结构生成 2,000 条合成记录，仅在本次浏览器中拦截读取响应，经真实页面和 DataTable 完成刷新、分页及筛选。现有 Demo 查询有 30 秒缓存；每次等待 31 秒真实时间再触发重连，此准备时间不计入刷新到绘制的延迟，不修改浏览器时钟。报告保留记录数、响应字节数、数据摘要和实际 DOM 行数。
- 独立真实 FastAPI：鉴权请求 `/catalog`、`/turbines`、`/data-catalog`，一次预热后逐次记录完整响应及 JSON 解析耗时，计算 P50/P95，记录返回数量与字节数。空库的空列表会明确记为 0 条；不能把它解释为生产数据规模下的吞吐能力，也不能据此声称前后端生产链路已通过。

固定本地预算为 FCP 2,500ms、内容就绪及列表刷新 4,000ms、交互 300ms、大列表筛选 1,000ms、API P95 500ms。缺样、请求失败、浏览器异常或超预算均退出非零，并保存报告；P95 使用 nearest-rank，5 次采样时等于最大值。报告同时保存 CPU/系统/浏览器、视口、数据量、Git 状态、构建及脚本摘要。这里的内容就绪、LCP 截止值与两帧交互测量属于本机实验指标，不能冒充真实用户的完整 LCP、INP 或正式 SLO 验收。

### Python

在已激活的 `backend/.venv` 中执行：

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

需要验证 CARE 可选依赖时：

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

SQLite 测试使用确定性 embedding、内存制品 verifier 和内存图存储替身，不能替代 PostgreSQL、TimescaleDB、MinIO、Neo4j 或真实模型供应商验收。

测试数量以命令和 CI 自动发现结果为准。普通本地运行缺少外部资源时，`external_release` 测试可能跳过；这些 skip 不被描述为发布通过。指定的外部验收环境必须设置 `WINDOPS_FAIL_ON_SKIPPED=1`，出现 skip 即失败，并按 发布验收清单（本地文档：`docs/runbooks/release-acceptance.md`） 保存实际证据。

## 生产验收边界

生产候选代码已经覆盖身份委托、RBAC、数据范围、幂等、revision、outbox、审计、备份恢复、发布身份和失败关闭路径。以下事项仍需在批准环境完成：

- Python API 与 worker 的正式集群部署、镜像扫描、SBOM、签名和准入验证；
- PostgreSQL、TimescaleDB、Redis、MinIO、Neo4j、LiteLLM 和 embedding 服务联合验收；
- 真实 SCADA、CMS、气象、EAM 数据契约和现场权限联调；
- 灾难恢复、负载、SLO、告警路由、DAST、人工渗透与发布后验证；
- 浏览器 WCAG、视觉回归和受支持终端验收；
- CARE 许可证复核、生产对象存储回放和跨场 ontology 人工审核。

Cloudflare Sites 只承载 Web 与身份网关，不托管 Python 后端。Sites 发布成功不能替代后端、依赖栈和现场系统验收。详细证据状态以 [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md)、[AUDIT_REPORT.md](./AUDIT_REPORT.md) 和 [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md) 为准。

## 贡献

开发环境、验证要求和 PR 流程见 [贡献指南](./CONTRIBUTING.md)；漏洞报告与凭据保护要求见 [安全政策](./SECURITY.md)。

欢迎提交 Issue 和 Pull Request：

- 修复业务闭环、权限、幂等或恢复路径中的真实问题；
- 改进可访问性、响应式布局、数据可视化和运行状态表达；
- 增加有真实数据来源、权限模型和验收标准的能力；
- 补充能够复现问题并验证真实行为的测试。

请勿通过删除失败测试、弱化断言、固定返回值、静默吞错或 fixture 回退制造通过结果。

## 许可证

OpenVigil 自有源码采用 [Apache License 2.0](./LICENSE)。

CARE v6 数据集及其受许可证约束的派生分发制品不受 Apache License 2.0 覆盖，也不随本仓库分发；相关资产遵循 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，并要求保留来源归属、许可链接、变更说明和 ShareAlike。

## 致谢

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück、Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — 固定版本的官方 CARE 评分复验参考
- PyScada、NetBird Dashboard、OpenClaw Mission Control、next-shadcn-dashboard-starter 与 Grafana — 信息架构、交互和视觉研究参考

完整第三方来源、固定提交、许可证和 clean-room 边界见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
