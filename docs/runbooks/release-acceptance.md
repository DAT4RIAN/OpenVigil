# WindOps 发布验收清单

> 适用范围：生产候选版本。仓库内单元测试通过不能替代本清单中的外部验收。

## 1. 变更与构建门禁

- 记录 Git 提交、构建制品摘要和审批单号。
- 执行前端 `format:check`、`typecheck`、`lint`、完整构建与测试。
- 执行后端 Ruff、MyPy、完整 Pytest、Bandit、pip-audit 和 `pnpm audit --prod`。
- 确认 Alembic 从 `0015_alarm_command_state` 升级到唯一 head
  `0026_schema_contract_alignment`，并保留离线 SQL 审阅结果。
- 核心集合的 10 万行查询计划、延迟与响应预算遵循
  [collection-performance.md](collection-performance.md)，并保留 JUnit 指标证据。
- 检查 `/api/v1/platform/configuration-status` 的
  `pending_credential_rotations = 0`；若不为零，严格执行
  `platform-configuration-secret-remediation.md`，不得绕过 readiness 门禁。
- 对完成 namespace、镜像摘要、网络和存储覆盖后的最终 Kubernetes 渲染清单执行：

```powershell
windops-deployment-policy `
  --manifests <rendered-manifest.yaml> `
  --expected-image-digest sha256:<approved-release-digest> `
  --expected-release-id <approved-release-id> `
  --expected-commit-sha <full-git-commit-sha> `
  --approved-backup-storage-class <approved-encrypted-class> `
  --report <release-evidence-directory>/deployment-policy.json
```

该报告必须与 Kubernetes API schema、准入策略及签名验证结果一起审阅。校验器会拒绝
内嵌 Secret、错误/占位镜像、root/特权容器、缺失资源限制或探针、无目标约束的 egress、
可用性策略缺失以及未批准的备份存储类。

受保护的 `release-candidate` workflow 只能从 `main` 的同一 commit 构建，并要求
`frontend`、`backend` 和 `postgres-contract` 三个 prior check 已成功。基础镜像来自
`backend/deploy/release-policy.json` 中固定的 Python 3.12.11/Trixie digest；所有 GitHub
Action 也固定到完整 commit。流水线必须保留 GitHub provenance、Cosign 签名、Trivy
CRITICAL/HIGH 零发现报告、SPDX SBOM 及其 attestation、制品结构检查、镜像迁移与
health/ready smoke、精确 digest 清单、真实外部验收 JUnit、备份摘要和 release chain。
任何缺失、skip 或保护环境配置缺失都会失败，不得以手工 tag 或仓库占位摘要继续。

任一检查失败、跳过或使用旧制品时，候选版本不得发布。

所有阶段报告必须汇总到一个内容寻址的发布证据目录。最终 go/no-go 前执行：

```powershell
windops-release-gate --evidence-dir <release-evidence-directory>
```

该命令要求镜像扫描、SBOM、签名验证、渲染部署策略、迁移、真实依赖、灾练、DAST、
WCAG/视觉、SLO 演练和 Sites 发布后验证十一类报告全部存在且摘要匹配；任何占位
镜像摘要、缺项、重复项、空报告、路径逃逸、符号链接或篡改都会失败。

每个 `report_path` 必须是符合 `GATE_REPORT_SCHEMA` 的 UTF-8 JSON 验收摘要，而不是
任意工具日志或手写的 `passed` 标记。摘要必须绑定同一个 release ID、commit SHA 和
镜像摘要，记录有时区的开始/完成时间、目标、工具及版本，并覆盖
`REQUIRED_GATE_CHECKS` 为该门禁声明的全部检查。每个检查至少引用一个 `artifacts`
条目；原始扫描结果、命令日志、截图差异、审批记录或运行证明必须作为非空文件存放在
同一证据目录内并记录 SHA-256。摘要时间必须与 manifest 一致，任何制品缺失、摘要
不符、未声明引用、重复检查或旧版本证据复用都会被拒绝。

## 2. 隔离环境迁移与真实依赖联合验收

候选环境必须使用真实的 PostgreSQL/TimescaleDB/pgvector、Redis、四个 MinIO
权威桶、Neo4j、LiteLLM、embedding 服务和至少一个活动在线模型部署。所有 TLS、
可信 Host、Sites 委托身份、指标令牌、限流与 OTLP 设置必须通过生产配置校验。

先在备份完成的隔离候选环境执行迁移，再运行：

```powershell
alembic current
alembic upgrade head
alembic current
$env:WINDOPS_RUN_EXTERNAL_RELEASE_TESTS = "1"
python -m pytest tests/external/test_release_environment.py -m external_release -q
```

PR 的 `postgres-contract` 必须在固定 digest 的 PostgreSQL 16 + TimescaleDB + pgvector 镜像中
以 `WINDOPS_FAIL_ON_SKIPPED=1` 执行空库、上一受支持 revision、故障回滚/重试、advisory lock、
关键事务、Outbox claim 与唯一约束测试。失败处置严格遵循
`postgresql-migration-recovery.md`，不得用 SQLite 或 `alembic stamp` 替代。

验收证据必须包含：依赖就绪探针、受保护指标、MinIO 写入/摘要回读、真实 embedding、
有证据引用的 LiteLLM 诊断，以及活动模型的在线推理结果。测试跳过即视为失败。

## 3. 备份恢复与灾难恢复演练

为源环境配置四个权威桶，为演练目标配置完全不同的数据库和桶，然后执行：

```powershell
windops-dr-drill --output-dir <approved-evidence-directory> `
  --confirm-target <exact-isolated-target-database-name>
```

保留 `dr-drill-evidence-*.json`、签名清单摘要、恢复后 schema 版本、行数不变量、
对象回读摘要、实际 RTO 与恢复点。源和目标任何重叠都会阻止演练；不得以生产库作为
恢复目标。

## 4. 安全验收

- 对 Sites 入口和 FastAPI 入口执行经过批准的 DAST；覆盖匿名、普通用户、审批人、
  运维经理和现场人员边界，并保留扫描配置、目标、时间、工具版本和完整报告。
- 验证生产 OpenAPI 路由关闭、可信 Host、防大请求、双层 Redis 限流、限流故障关闭、
  安全响应头、委托令牌请求绑定、角色越权、IDOR、上传类型/大小/摘要和 SSRF 边界。
- 按
  [delegated-replay-and-command-idempotency.md](delegated-replay-and-command-idempotency.md)
  在真实 PostgreSQL 多实例环境验证委托 nonce 原子消费、store 故障关闭、稳定命令重放与
  `Idempotency-Replayed` 透传；串行、并发和响应丢失均只能产生一次副作用。
- 对发现项完成分级、修复和复测。未关闭的高危或严重项阻止发布。
- 由独立评审人员完成威胁模型和必要的人工渗透复核；Bandit、依赖审计和 DAST
  不能单独替代人工渗透测试。

## 5. WCAG 与视觉验收

在受支持的桌面和移动浏览器中覆盖全部生产工作区，至少保留以下证据：

- 自动化可访问性扫描报告及零严重/高影响违规结论；
- 仅键盘导航、可见焦点、对话框焦点圈定/恢复、Escape 关闭和跳转顺序；
- 屏幕阅读器的标题、地标、表格、表单错误和动态状态播报；
- 200% 缩放、窄屏重排、颜色对比、非颜色状态表达和减少动画偏好；
- 基准截图与差异报告，包含所有关键页面、空态、错误态、加载态和高风险审批流程。

静态 JSX 可访问性 Lint 通过不等于本节通过。没有浏览器证据时必须记录为待验收。

## 6. Sites 与发布后验证

- 确认 Sites 环境显式设置 `WINDOPS_RUNTIME_MODE=production`：该变量未设置时缺省为
  `demo`（fail-open），漏配不会校验失败，而是静默以演示模式对外服务。
- Sites 必须配置生产模式、外部 HTTPS 后端、`sites_delegation` 和由密钥管理系统提供的
  48 字符以上委托密钥；后端必须配置相同活动密钥和角色映射。Sites 还必须配置
  `WINDOPS_BACKEND_EXPECTED_RELEASE_ID` 与 `WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST`，
  且与候选后端的不可变发布身份完全一致。
- 后端必须为每个 Sites 人员主体配置
  `WINDOPS_IDENTITY_SCOPE_MAPPINGS`，至少包含租户或风场范围，并按职责声明
  `data_scopes`；没有映射的生产主体只能得到 `GRAPH_SCOPE_REQUIRED`，不能读取知识图谱。
- 发布后验证 `/api/runtime` 返回预期 release ID、完整 commit SHA 与镜像摘要，并验证
  22 个生产工作区、SSE 断点重放、审批与工单写入、证据
  上传、报告导出、知识检索、知识图谱租户/风场边界、模型推理、指标抓取和追踪关联。
- 使用两个不同的 Sites 主体分别读取同一图谱实体：允许主体只能看到已授权租户/风场/数据域，
  未映射主体必须得到 `GRAPH_SCOPE_REQUIRED`，跨租户实体必须以 `404` 隐藏，不得通过
  `entityId`、搜索或子图深度扩大可见范围；将该结果作为 `knowledge_graph_scope_boundary`
  检查写入 Sites post-deploy 报告。
- 确认生产响应不包含 fixture、D1、确定性 WebSocket 或固定 WT-023 演示状态。
- 记录发布 URL、版本、验证人、验证时间、回滚版本和最终 go/no-go 决策。

任何外部依赖联合验收、灾练、安全、WCAG/视觉或 Sites 发布后验证缺少证据时，状态只能
是“待发布验收”，不能标记为“生产已上线”。
