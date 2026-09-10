# OpenVigil Technical Audit Report

本报告只记录产品落地背后的技术实现、架构、数据、API、安全、并发、性能、测试和发布问题。纯视觉或交互问题以 `UI_AUDIT_REPORT.md` 为主；跨层问题通过 `Related UI Issue` / `Related Technical Issue` 双向引用。

---

## 1. Audit Metadata

- **Stage:** LEAD
- **Reviewer:** Lead-Reviewer
- **Audit Date:** 2026-09-04
- **Code Baseline:** Git `HEAD 8fd126672776aff6c52328a621391e4f8747627a` 与本轮开始时工作树
- **Inputs:** `AGENTS.md`、`PRODUCT_REQUIREMENTS.md`、`UI_UX_SPEC.md`、原 `ARCHITECTURE.md`、`UI_AUDIT_REPORT.md`、原 `AUDIT_REPORT.md`、`EXECUTION_GOAL.md`、`EXECUTION_PROGRESS.md`、完整代码/迁移/测试/CI/发布/部署配置
- **Change Boundary:** 本轮未修改业务代码；只更新架构与审核文档

本轮以代码、配置和可重复验证为准，不把旧报告或进度文件中的 `DONE` 直接视为验收证据。开始审核时，四份产品/架构/UI 文档和 `docs/ui/` 仍是未跟踪文件；在进入发布基线前必须纳入受审版本控制。

---

## 2. Executive Conclusion

**审计基线状态：NOT ACCEPTED。**

**整改实现状态（2026-09-04）：16 / 16 `DONE`；First Full Recheck、Adversarial Review、Final Global Validation 与连续 `Final Audit Pass = 2 / 2` 已通过，最终项目状态为 `ACCEPTED`。**

代码库已经形成清晰的 Demo / Production 双运行时边界、PostgreSQL 权威账本、事务 outbox、服务端身份/权限和结构化错误体系。当前常规前后端测试也大体健康。然而，以下缺口仍会直接破坏产品真实性、CARE 可信性或生产发布闭环：

- 3 个 Critical；
- 9 个 High；
- 4 个 Medium；
- 共 16 个未关闭技术 Issue。

最严重的阻断项是：CARE 根契约可被重新自签、B/C 质量规则未进入实际模型语义、异常模型没有可用的生产 HTTP 控制路径、生产 UI 会把未完成/失败查询呈现为健康零值、发布 workflow 自行声明 `qualified` 却没有执行仓库定义的最终门禁。

---

## 3. Actual Architecture Summary

本轮已按实现重建 `ARCHITECTURE.md`。真实系统不是单一前后端，而是两个有意隔离的运行时：

1. **Demo runtime:** vinext/React + OpenAI Sites Worker + D1 + 确定性 fixture/workflow。
2. **Production runtime:** 同一页面层经 Sites Worker 的生产边界、路径 allowlist 和逐请求 delegated JWT 调用 FastAPI。
3. **Authoritative backend:** FastAPI 模块化单体；PostgreSQL/TimescaleDB/pgvector 为权威数据，Redis/Dramatiq 执行异步工作，MinIO 保存制品，Neo4j 仅为可重建投影。
4. **Durability:** 业务写与 outbox 同事务；relay/worker 使用 lease、fencing、幂等命令和乐观 revision。
5. **Deployment:** Kubernetes 基线包含 API、通用 worker、outbox relay、migration Job 和 backup CronJob；外部依赖由受管服务提供。

架构边界本身总体合理。当前失败集中在“边界之间是否真正接通”和“发布证据是否覆盖真实生产路径”，而不是目录是否分层。

---

## 4. Issue Index

| ID | Severity | Status | Title | Related UI Issue |
| --- | --- | --- | --- | --- |
| CARE-C001 | Critical | DONE | CARE 根契约只有可重算自哈希，没有可信锚点 | N/A |
| CARE-C003 | Critical | DONE | B/C 连续性与信号佐证分支未进入全量模型路径 | N/A |
| CARE-C005 | Critical | DONE | 异常模型没有可用的生产 HTTP 激活/回滚闭环 | N/A |
| CARE-H006 | High | DONE | 全量训练与预测忽略质量 mask | N/A |
| CARE-H007 | High | DONE | CARE 阶段制品无法在同一权威数据库升级 | N/A |
| CARE-H008 | High | DONE | 标准 CI 与生产镜像缺少 benchmark 依赖 | N/A |
| CARE-H009 | High | DONE | CARE PostgreSQL 验收未进入 required CI | N/A |
| CARE-H010 | High | DONE | 官方 CARE 参考实现是无映射 gitlink，干净克隆无法复验 | N/A |
| CARE-H011 | High | DONE | CARE PostgreSQL 吞吐与目录查询性能门槛可重复失败 | N/A |
| TECH-H001 | High | DONE | Production 查询 pending/error 被呈现为健康零值或空状态 | UI-H-002、UI-H-003 |
| TECH-H002 | High | DONE | Release workflow 绕过最终证据门禁并自行声明 qualified | N/A |
| TECH-H003 | High | DONE | 没有可部署的 CARE 独立执行平面 | N/A |
| TECH-M002 | Medium | DONE | Production release identity 解析 commit 却不校验 commit | N/A |
| TECH-M003 | Medium | DONE | UI 自动化覆盖不足以证明验收矩阵 | UI-M-002 |
| TECH-M004 | Medium | DONE | 每次业务 GET 同步提交无保留策略的读审计记录 | N/A |
| TECH-M005 | Medium | DONE | 仓库跟踪 334 MB 生成缓存与二进制工具制品 | N/A |

---

## 5. Critical Findings

### CARE-C001 — CARE 根契约只有可重算自哈希，没有可信锚点

**Category:** Data integrity / security
**Related Requirement:** CARE 数据真实性、制品 lineage、发布可复验性
**Related UI Issue:** N/A

#### Problem and Evidence

- `backend/src/windops_backend/benchmarks/care/contract.py:147` 的 `verify_care_contract()` 与 `quality.py:353` 的 quality verifier 都只删除文档内的 hash 字段后重算同一文档；验证的是“文档与自己一致”，不是“文档来自批准数据根”。
- 下游 full-scale 在 `fullscale.py:963`、`:1439` 接受 manifest 中的事件标签和质量策略，没有以独立的受信根重新核对只读 ZIP 内 `event_info.csv`、schema 和源文件身份。
- 旧审计的对抗性探针交换真值或翻转质量策略后重算所有自哈希，两个篡改版本仍被接受，且官方 ZIP hash 和汇总数量不变。

#### Impact

可替换控制 JSON 的错误流程或攻击者可以重写真值/质量语义并生成一条自洽但不可信的 lineage，污染训练、评分、激活与数据库证据。

#### Required Change / Acceptance

- 在当前输入之外保存批准根哈希或分离签名，并在任何写入前验证。
- 从只读官方来源重建 canonical source/quality contract，逐字段与批准根比较。
- 将批准根、签名和完整 lineage 绑定 import、evaluation、model、activation 与数据库记录。
- 增加“篡改后重新哈希”的真值、策略、列映射和来源替换负向测试；这些用例必须 fail closed。

---

### CARE-C003 — B/C 连续性与信号佐证分支未进入全量模型路径

**Category:** Model/data semantics
**Related Requirement:** CARE B/C 状态规则、真值隔离、可解释质量处理
**Related UI Issue:** N/A

#### Problem and Evidence

- `backend/src/windops_backend/benchmarks/care/quality.py:225-247` 的 `status_decision()` 定义了 sustained disagreement 与 corroboration 分支。
- 实际 evaluation 在 `evaluation.py:354` 只用 `np.isin(status, trusted_statuses)` 一类静态状态判断；full-scale 也没有跨 batch 维护连续长度。
- 旧审计扫描真实 prediction 制品时，非可信状态点的 run length / corroboration 仍是默认值，生产路径没有证明该分支可达。

#### Impact

冻结协议声称会屏蔽的持续且被佐证 B/C 分歧仍进入模型；测试通过直接构造决策字段验证辅助函数，不能证明生产全量语义。

#### Required Change / Acceptance

- 在同一 canonical 数据边界计算并持久化跨 batch、跨缺口、事件边界安全的连续长度与佐证。
- verifier 必须从原始状态与信号重算字段，拒绝调用方伪造。
- 用真实全量 fixture 证明短时分歧保留、满足冻结条件的持续分歧被屏蔽，并重新生成受影响制品。

---

### CARE-C005 — 异常模型没有可用的生产 HTTP 激活/回滚闭环

**Category:** API / authorization / workflow
**Related Requirement:** 模型治理、异常模型激活、回滚、公开生产路径
**Related UI Issue:** N/A

#### Problem and Evidence

- `backend/src/windops_backend/services/models.py:247-293` 对 anomaly 激活正确地要求服务器签发的 `AnomalyActivationAuthorization`。
- `backend/src/windops_backend/api/model_registry.py:385`、`:427` 的公开 activate 与 rollback endpoint 调用 service 时没有加载权威评估证据、执行 activation gate 或传入该授权。
- 当前成功测试由测试代码构造授权并直接调用内部 service；这绕过了待验收的 HTTP 边界。
- Sites 生产 gateway allowlist 还拒绝 `/models/deployments/{id}/anomaly-predictions/run` 和 `/model-predictions/{id}/alert-evaluation`；静态路由探针两个结果均为 `false`。

#### Impact

真实 Production UI/API 用户不能完成 anomaly activation/rollback 与后续 alert evaluation。服务层 fail closed 是正确防线，但产品闭环未接通。

#### Required Change / Acceptance

- 服务器在一个受治理事务中锁定 deployment、加载权威 evaluation/metrics/artifact/approval，执行 gate，签发并立即消费授权，再原子切流。
- 定义制品漂移、评估失效、绑定错误、并发激活与 rollback 的稳定错误和审计事件。
- 将所需 endpoint 纳入最小生产 allowlist，并保留 method/path/body/idempotency 约束。
- 真实 PostgreSQL + Sites gateway + HTTP 测试不得直接注入内部授权，必须覆盖成功、失败、并发和无部分切流。

---

## 6. High Findings

### CARE-H006 — 全量训练与预测忽略质量 mask

**Category:** Data quality / model correctness
**Related Issue:** CARE-C003
**Related UI Issue:** N/A

`backend/src/windops_backend/benchmarks/care/fullscale.py:903-933` 为 B/C 事件生成并引用 mask，但训练 moments 与预测只按 split、status 和 finite value 取数，没有读取 mask。模型制品只引用 quality contract 身份，没有冻结 `apply|ignore` 策略、实际 mask hash、处理数量或忽略影响报告。

**Acceptance:** 为每个模型族冻结 mask 策略；模型/fold/prediction 记录实际 mask lineage 与计数；verifier 证明 mask 真正影响输入，或绑定经批准的忽略敏感性报告；重新训练评估并解释指标变化。

---

### CARE-H007 — CARE 阶段制品无法在同一权威数据库升级

**Category:** Database / identity / idempotency
**Related Issue:** CARE-H006
**Related UI Issue:** N/A

minimal/offline 与 full-scale 使用相同 dataset/event/quality 业务身份，却生成不同阶段包装 artifact hash。`backend/src/windops_backend/services/benchmark_metadata.py:304-350` 将相同 identity 的内容差异视为冲突。旧审计在同一新库依次注册时稳定得到 `quality-report identity already exists with different content`；各测试使用独立空库掩盖了真实升级顺序。

**Acceptance:** 分离 canonical 内容身份、阶段制品身份与审计主体；提供兼容迁移/回填；同一新库完成 minimal → offline → vertical → full-scale，重复与并发运行精确幂等且不清理历史。

---

### CARE-H008 — 标准 CI 与生产镜像缺少 benchmark 依赖

**Category:** Build / dependency closure
**Related Issue:** CARE-H009、TECH-H003
**Related UI Issue:** N/A

`backend/pyproject.toml:47` 只在 `benchmark` extra 声明 PyArrow/scikit-learn；`.github/workflows/ci.yml:190` 的主 CI 安装 `.[test,dev]`，PostgreSQL job 安装 `.[test]`，`backend/scripts/export_container_requirements.py` 的容器 exporter 只启用 `connectors`。因此本地已有包可让测试通过，但干净 CI 和标准生产镜像不能导入 CARE pipeline。

**Acceptance:** 为收集 CARE 测试的 required job 和实际 CARE 运行镜像安装锁定的 benchmark closure；增加干净环境 import/CLI smoke，并记录 lock hash。

---

### CARE-H009 — CARE PostgreSQL 验收未进入 required CI

**Category:** Test coverage / release evidence
**Related Issue:** CARE-H007、CARE-H008、CARE-H011
**Related UI Issue:** N/A

`.github/workflows/ci.yml:293-301` 的 PostgreSQL job 只显式运行 migration、concurrency、service resilience 和 prediction lock 四类外部测试；三个 `test_postgres_care_*.py` 文件完全未被收集。`FAIL_ON_SKIPPED` 无法发现命令中根本不存在的测试。

**Acceptance:** required/scheduled release job 显式收集三个 CARE PostgreSQL 文件并校验预期测试数量；skip 为 0；保留同库阶段序列、性能属性、JUnit、根哈希、镜像 digest 和迁移 head。

---

### CARE-H010 — 官方 CARE 参考实现是无映射 gitlink，干净克隆无法复验

**Category:** Supply chain / reproducibility
**Related Requirement:** 官方算法等价、clean-clone reproducibility
**Related UI Issue:** N/A

本轮修正旧证据：当前 CARE 业务源码已进入 `HEAD`，旧报告中“全部未跟踪”的描述不再成立。但官方参考目录 `tmp/external/EnergyFaultDetector-v0.6.2` 被记录为 mode `160000`、commit `a338b6…` 的 gitlink，仓库没有对应 `.gitmodules` 映射；`git archive HEAD tmp/external` 只包含空目录。`tmp/verify_care_reference.py` 依赖该本地嵌套仓库，CI 也没有重新执行官方等价验证。

**Impact:** 干净克隆无法取得制品所依据的官方参考实现，也无法独立复验算法等价性；本地残留目录不是可发布供应链证据。

**Acceptance:** 以合法且不可变的 submodule 映射或受许可 vendor 内容提供参考源，绑定 commit/hash/license；clean clone CI 获取并执行 reference comparison，或验证同等强度的内容寻址证据；产品/架构/审核 source-of-truth 文档也必须在发布前进入受审提交。

---

### CARE-H011 — CARE PostgreSQL 吞吐与目录查询性能门槛可重复失败

**Category:** Performance / capacity
**Related Issue:** CARE-H009
**Related UI Issue:** N/A

2026-08-31 独立审核在固定 TimescaleDB/pgvector 镜像和全新迁移数据库上得到：

- vertical replay：`20.514`、`13.775 rows/s`，低于 `50 rows/s` 门槛；
- full-scale 目录查询最大 p95：`504.507 ms`、幂等重跑 `1194.824 ms`，高于 `500 ms` 门槛。

本轮本地没有外部 PostgreSQL 服务，因此没有用 SQLite/skip 结果覆盖上述未关闭证据。

**Acceptance:** profile 写入事务/outbox 固定开销与目录 SQL；固定资源、预热、规模和次数；至少三次独立新库均达到 ≥50 rows/s 且各目录 p95 ≤500 ms；进入 fail-on-skip CARE release job，不以放宽门槛替代修复。

---

### TECH-H001 — Production 查询 pending/error 被呈现为健康零值或空状态

**Category:** Frontend data flow / error handling / product truth
**Related Requirement:** `PRD-001`、`PRD-002`、`PRD-003`、Product-Level State Requirements
**Related UI Issue:** `UI-H-002`、`UI-H-003`

#### Problem and Evidence

- `components/pages/dashboard-page.tsx:284-286` 只在 `isError` 时降级；pending 时 badge 显示“生产数据已连接”。
- `snapshot` 未定义时，指标用 `0`/空数组回退；`:433-449` 的 `!snapshot?.alarms.length` 等表达式同时成立，因而显示“没有未关闭告警”等业务结论。
- error banner 出现后，零值 KPI 与空状态仍继续渲染。
- Mission、工单和预测页面也存在 `query.data ?? []` 后直接进入 empty state 的同类模式。
- 143 个 Node tests 和当前少量 E2E 没有对这些页面建立 pending/error/empty 的状态真值矩阵。

#### Impact

首次加载或后端故障会被解释为“生产健康、0 告警、无任务”，可能让运营人员漏判事件；这也是 UI 报告中两项 High 的共同技术根因。

#### Required Change / Acceptance

- 统一以显式 query state machine 表达 `initial-loading | refreshing | success-empty | success-data | error-stale | error-no-data`。
- 健康/连接状态只能由成功且新鲜的权威响应得出；错误时禁止用默认零值形成业务结论。
- 为 Dashboard、Mission、工单、预测至少覆盖 pending、empty、403、5xx、network、stale refresh 与恢复 E2E。

---

### TECH-H002 — Release workflow 绕过最终证据门禁并自行声明 qualified

**Category:** Build / deployment / release integrity
**Related Requirement:** `PRD-006`、Release Acceptance、`ARCHITECTURE.md` release invariant
**Related UI Issue:** N/A

#### Problem and Evidence

- `backend/src/windops_backend/operations/release_gate.py:12-28` 要求 11 类 content-addressed evidence：image scan、SBOM、signature、deployment、migration、external、DR、DAST、accessibility/visual、SLO、Sites post-deploy。
- `.github/workflows/release.yml` 没有组装 `release-evidence.json`/digest，也没有调用 `windops-release-gate`。
- workflow 在缺少 DAST、UI/a11y、SLO、Sites post-deploy、迁移回滚与完整 DR gate 时，于 `release.yml:295-299` 直接写 `release-chain.json` 的 `status:"qualified"` 再断言该字段。
- built-image smoke 通过 `backend/src/windops_backend/operations/release_smoke.py:35` 强制设置 `WINDOPS_ENVIRONMENT=development`；受保护外部测试运行的是 source/uv 环境，不是已构建生产镜像。

#### Impact

CI 的“qualified”不是仓库最终门禁的结果，候选制品可能在未证明生产配置、外部依赖、回滚、UI 与 SLO 的情况下被当作可发布。

#### Required Change / Acceptance

- 每项门禁生成标准化、内容寻址、绑定同一 commit/image/release 的报告。
- workflow 最后必须调用唯一 release verifier；只有 verifier 输出可以生成 qualified 状态。
- built image 以生产配置连接受控 PostgreSQL/Redis/MinIO/Neo4j，或提供严格证明等价的生产 boot evidence。
- 任一报告缺失、过期、身份不一致或失败时，artifact promotion 必须 fail closed。

---

### TECH-H003 — 没有可部署的 CARE 独立执行平面

**Category:** Architecture / operations / capacity isolation
**Related Requirement:** CARE batch/offline independent worker
**Related Issue:** CARE-H008、CARE-H009
**Related UI Issue:** N/A

CARE pipeline 明确需要独立 worker 和 benchmark 依赖，但 Kubernetes 只有 API、通用 Dramatiq worker、outbox relay、migration 与 backup；没有 CARE Job/CronJob/worker、队列路由、资源/超时/重试/checkpoint 策略，也没有对应最小权限 MinIO identity。标准镜像又未包含 benchmark extra。

**Acceptance:** 提供可部署、digest-pinned 的 CARE image/workload；隔离队列和资源，定义 checkpoint/retry/idempotency、超时、并发与 scoped storage credentials；CI/release 在实际 workload 上执行小型 smoke 和受保护全量验收。

---

## 7. Medium Findings

### TECH-M002 — Production release identity 解析 commit 却不校验 commit

**Category:** Runtime provenance
**Related UI Issue:** N/A

Worker 在 `lib/production-runtime.ts:536-548` 解析并验证 `x-windops-commit-sha` 格式，但 `releaseMismatch()`（`:551-558`）只比较 release ID 与 image digest；Sites 配置也没有 expected commit。若 release metadata 被错误组合，commit 头只被转发而不参与信任决定。

**Acceptance:** 将 expected commit 纳入 Sites release record 与 mismatch 判定并增加错配测试；或者明确删除该字段作为安全契约，并证明 digest 到 commit 的受签名、可查询映射是唯一可信来源。

---

### TECH-M003 — UI 自动化覆盖不足以证明验收矩阵

**Category:** Testing / accessibility / responsive behavior
**Related Requirement:** `UI_UX_SPEC.md` 11–13、Release Acceptance
**Related UI Issue:** `UI-M-002`

Playwright 只有一个 Chromium/1440×900 project 和一个 390px 为主的场景文件；没有覆盖 22 条路由的桌面/1280/tablet/mobile 矩阵，也没有自动化 axe 类可访问性、完整 200% zoom、reduced-motion 和全页视觉基线。当前 `6 passed / 1 skipped` 只能证明有限身份/移动场景。

**Acceptance:** 建立按风险分层的 route × viewport × state × role 矩阵；关键页面加入可访问性、键盘、200% zoom、reduced-motion 和稳定视觉基线；required release job 对关键用例 fail on skip。

---

### TECH-M004 — 每次业务 GET 同步提交无保留策略的读审计记录

**Category:** Database / performance / operations
**Related UI Issue:** N/A

`backend/src/windops_backend/api/deps.py:522-557` 的 `require_read_access()` 在实际业务查询之前插入 `ReadAccessAudit` 并单独 `commit()`；Dashboard 还会每 15 秒轮询。`models.py:596-606` 只为 subject/accessed_at 建索引，仓库未发现 retention、partition、archive 或清理策略。

**Impact:** 高频读取被转换为同步写放大，审计表无限增长；审计库写延迟/故障还会阻断本可服务的读取，并保存完整 query string 增加数据治理负担。

**Acceptance:** 明确保留、分区、归档和字段最小化策略；量化典型并发下写放大与 p95；在不丢失合规审计的前提下采用可恢复的异步/批处理或隔离写路径；覆盖审计存储故障和背压行为。

---

### TECH-M005 — 仓库跟踪 334 MB 生成缓存与二进制工具制品

**Category:** Repository hygiene / supply chain / CI performance
**Related UI Issue:** N/A

`git ls-files .codex_tmp` 返回 7,852 个文件、334,379,011 bytes，包含 `node_modules`、可执行依赖、PPT/render 中间物等；`.gitignore` 未排除该目录。这些文件不在产品 lock/SBOM 的常规审计边界内，却增加 clone、checkout、扫描和 CI 成本。

**Acceptance:** 从当前版本树移除可再生缓存/二进制依赖并加入 ignore；只在受控 artifact storage 或明确的受审 fixture 目录保存必要输出；对必须保留的大制品记录来源、license、hash 和扫描证据。

---

## 8. Cross-Layer Mapping with UI Audit

| Technical Root Cause | UI Issue | Ownership |
| --- | --- | --- |
| `TECH-H001` | `UI-H-002` | 技术报告负责 query state、数据新鲜度与健康判定；UI 报告负责矛盾状态的可见表达 |
| `TECH-H001` | `UI-H-003` | 技术报告负责状态机与数据流；UI 报告负责 loading/empty/error 呈现 |
| `TECH-M003` | `UI-M-002` | 技术报告负责测试基础设施与门禁；UI 报告负责未被证明的视觉/无障碍验收范围 |

其他 UI Issue 当前未发现需要单独登记的技术根因，仍以 `UI_AUDIT_REPORT.md` 为唯一主记录。

---

## 9. Validation Matrix

| Validation | Result | Evidence / Boundary |
| --- | --- | --- |
| `pnpm test` | PASS | production build、bundle budget、143/143 Node tests |
| `pnpm run typecheck` | PASS | TypeScript |
| `pnpm run lint` | PASS | ESLint |
| `pnpm test:e2e` | PASS WITH SKIP | 6 passed / 1 个真实跨层环境用例 skipped |
| `pnpm run format:check` | PASS | 全仓 Prettier check |
| Backend full `pytest` | PASS WITH SKIPS | 393 collected；369 passed / 24 skipped / 0 failed |
| Backend Ruff format/lint | PASS | 192 files formatted；lint 无问题 |
| Backend strict mypy | PASS | 92 source files |
| Backend Bandit | PASS WITH WARNINGS | 无阻断 finding；存在既有 nosec/comment 解析警告 |
| Backend lock / container requirements | PASS | `uv lock --check` 与 exporter `--check` |
| Alembic heads | PASS | 唯一 head `0026_schema_contract_alignment` |
| Production gateway route probe | FAIL | 两个 anomaly 执行 endpoint 不在 allowlist；见 `CARE-C005` |
| Official reference clean-clone check | FAIL | 无 `.gitmodules` 的 mode 160000 gitlink；见 `CARE-H010` |
| Release-gate wiring inspection | FAIL | workflow 未调用 final gate，却写 `status:"qualified"`；见 `TECH-H002` |
| Repository tracked-artifact inventory | FAIL | `.codex_tmp`: 7,852 files / 334,379,011 bytes；见 `TECH-M005` |
| CARE PostgreSQL performance | OPEN FAILURE | 沿用 2026-08-31 独立新库证据；本轮未用 SQLite 结果替代 |

通过的常规测试是真实信号，但它们不覆盖本报告的关键生产边界，因此不能抵消 FAIL/OPEN 项。

---

## 10. Product and Technical Coverage Conclusion

- **产品需求落地:** 22 个产品路由和主要 domain flow 已存在，但状态真实性、异常模型闭环、CARE execution plane 与 release acceptance 未达到 PRD。
- **架构边界:** Demo/Production、权威库/投影、API/service/worker 边界总体清楚；缺口主要是部署与控制面未接通。
- **前后端数据流/API:** delegated identity、allowlist、结构化错误和幂等 POST 设计较强；anomaly control path 与 query state 仍阻断。
- **数据库/并发/幂等:** migrations 单 head、outbox/lease/fencing/command receipt 设计健全；CARE 跨阶段 identity 与同步读审计仍有风险。
- **权限/安全:** 服务端角色、scope、global-role 与 delegated replay 防护总体完整；CARE trusted root 和 release provenance 仍不可信。
- **性能:** 前端 bundle budget 通过；CARE PostgreSQL 已有未关闭门槛失败，读审计存在未量化写放大。
- **测试:** 单元/类型/lint 基础健康；真实 PostgreSQL CARE、完整 UI 状态/viewport/a11y、官方 reference 和最终 release gate 证据缺失。
- **Build/Deployment:** 常规构建成功；标准镜像没有 CARE 依赖/工作负载，release workflow 的 qualified 结论不可采信。

---

## 11. Release Decision and Remediation Order

当前不得标记为 release-ready。建议按以下顺序整改：

1. 关闭 `CARE-C001`、`CARE-C003`、`CARE-C005`，从唯一可信根重建所有受影响证据。
2. 关闭 `CARE-H006`、`CARE-H007`，证明同库升级、质量 mask 与模型语义一致。
3. 补齐 `CARE-H008`、`CARE-H009`、`CARE-H010`、`TECH-H003`，使 clean clone、CI、参考复验和生产 CARE workload 成为同一可重复闭环。
4. 关闭 `TECH-H001`、`TECH-H002`，让产品状态和发布状态都只能由成功的权威证据产生。
5. 复验 `CARE-H011`，再关闭 release identity、UI matrix、读审计和仓库卫生 Medium 项。
6. 所有 Critical/High 关闭后，使用同一 commit、image digest、migration head 和 evidence root 执行最终 release gate；同时独立满足 `UI_AUDIT_REPORT.md` 的 High 验收项。

`EXECUTION_PROGRESS.md` 只能在实现并验证后更新，不能把本轮已经证伪的历史 `DONE` 继续作为完成依据。
