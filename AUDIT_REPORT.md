# 当前项目重新审核报告

审核日期：2026-08-31  
审核范围：当前工作树、CARE v6 源码与制品、前后端回归、CI、迁移、真实 PostgreSQL/TimescaleDB 集成路径  
审核依据：`AGENTS.md`、原 `AUDIT_REPORT.md`、`EXECUTION_PROGRESS.md`、`EXECUTION_GOAL.md`、项目实际代码、当前制品和本轮独立测试结果

## 审核结论

**当前状态：NOT ACCEPTED。旧报告并未真正全部落实。**

本轮不采信 `EXECUTION_PROGRESS.md` 或旧报告中的 `DONE`，而是从当前代码、制品和测试重新验证。当前仍有：

- 3 个 Critical；
- 6 个 High；
- 其中 `CARE-C001`、`CARE-C003`、`CARE-C005` 是旧 Critical 的实质性未完成或假完成；
- 旧 `CARE-M004` 所声称的全量性能与运行验收也未成立，现以 High 问题重新登记；
- 普通单元测试、覆盖率、类型检查和前端构建大体健康，但这些结果没有覆盖下述生产语义和发布路径，不能支持“CARE 全部完成”的结论。

本报告只保留当前仍需处理的问题，不再列出已经关闭的历史问题。

## 当前问题登记

| ID | 严重度 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| CARE-C001 | Critical | REOPENED | CARE 根契约只有可重算的自哈希，没有可信锚点；重新签名后的真值和质量策略篡改会被接受 |
| CARE-C003 | Critical | REOPENED | B/C 状态连续性和信号佐证在生产全量路径从未计算，声明的过滤分支实际不可达 |
| CARE-C005 | Critical | REOPENED | 异常模型没有可用的生产 HTTP 激活/回滚成功路径；测试通过内部函数注入授权制造成功 |
| CARE-H006 | High | OPEN | 全量训练和预测忽略 7,386,831 条质量 mask，且没有声明“使用或忽略”策略及影响证据 |
| CARE-H007 | High | OPEN | 最小/离线阶段无法在同一权威数据库自然升级到全量阶段，注册身份发生内容冲突 |
| CARE-H008 | High | OPEN | CI 安装集合缺少 `benchmark` 依赖；干净 CI 等价环境中的 CARE 测试直接缺少 PyArrow |
| CARE-H009 | High | OPEN | 三条 CARE PostgreSQL 外部测试未进入 CI，普通全量测试中的 skip 不能形成发布证据 |
| CARE-H010 | High | OPEN | CARE 实现和测试未被当前提交追踪，制品记录的提交与依赖根也已分叉，无法从干净克隆复现 |
| CARE-H011 | High | OPEN | 真实 PostgreSQL 竖向回放吞吐和全量目录查询性能门槛可重复失败 |

## CARE-C001 — 根契约可被重新签名后篡改

### 现状与证据

- `backend/src/windops_backend/benchmarks/care/contract.py:147-154` 的 `verify_care_contract()` 只删除 `manifest_sha256` 后重算同一文档的哈希。
- `backend/src/windops_backend/benchmarks/care/quality.py:353-359` 的 `verify_quality_contract()` 同样只验证文档自哈希。
- `backend/src/windops_backend/benchmarks/care/fullscale.py:367-370` 只确认两个自哈希文档互相引用；没有批准根哈希、可信签名或从只读源重建后的精确比较。
- `backend/src/windops_backend/benchmarks/care/fullscale.py:963` 和 `:1439` 直接把来源 manifest 中的 `event_label` 作为下游真值，没有在边界处重新读取并核对 `event_info.csv`。
- 本轮对当前真实 manifest 做了对抗性验证：交换一个 anomaly 和一个 normal 的标签，保持官方 ZIP SHA-256 `ca61379e...4194f1`、45/50 汇总数量和所有源文件身份不变，然后重算 manifest 与 quality contract 自哈希；`build_full_scale_plan()` 接受了该文档。
- 本轮再把 `global_zero_to_null` 质量策略翻转并重算 quality contract 自哈希，`build_full_scale_plan()` 仍然接受。
- 对抗性探针结果为：`truth_tamper_accepted=true`、`quality_policy_tamper_accepted=true`、`zip_sha256_unchanged=true`、`anomaly_total_unchanged=true`。

### 影响

任何能够替换控制 JSON 的错误流程或攻击者，都可以在不改变官方 ZIP 身份和汇总数量的情况下重写真值或质量语义，随后污染全量计划、评分、激活证据和数据库。当前“哈希一致”只证明文档和它自己一致，不证明它来自批准的数据根。

### Required Changes

1. 为 CARE 根契约引入不可由当前输入自行生成的可信锚点，例如受保护配置/数据库中的批准根哈希或由受信密钥生成的分离签名。
2. 在导入和全量注册边界，从只读官方 ZIP 重新读取 `event_info.csv`、schema、header、行数和文件哈希，重建 canonical source manifest，并与批准文档逐字段精确比较。
3. 从批准 source manifest 和实际审计结果重建 quality contract；不能只接受调用方提供的 `source_manifest_sha256` 与自哈希。
4. 将批准根 ID、签名/根哈希和完整 lineage 写入下游 import、evaluation、model、activation 与数据库记录。
5. 增加重新哈希后的真值交换、质量策略翻转、列映射替换、来源引用替换等对抗性测试。

### Acceptance Criteria

- 修改任一真值、质量策略、映射或来源引用后，即使重算全部下游自哈希，也必须在任何写入发生前失败。
- 从同一批准 ZIP 和同一实现重建的 canonical manifest/quality contract 必须字节级确定；非批准根不得进入全量计划、评估或注册。
- 外部 PostgreSQL 验收必须证明数据库中的 event truth 与重新读取的 `event_info.csv` 完全一致，而不是只检查 45/50 汇总数量。

## CARE-C003 — B/C 状态过滤生产分支不可达

### 现状与证据

- `backend/src/windops_backend/benchmarks/care/quality.py:223-247` 声明：B/C 非可信状态只有在连续长度至少 3 且有版本化信号佐证时才无效。
- 同一函数默认 `disagreement_run_length=1`、`corroborated_by_signal=False`；`backend/src/windops_backend/benchmarks/care/scoring.py:385-393` 的 `PredictionPoint` 也使用同样默认值。
- 生产全量预测在 `backend/src/windops_backend/benchmarks/care/fullscale.py:1816-1847` 只读取 timestamp、row ID、split、status 和 feature score，构造 `PredictionPoint` 时没有计算或传入连续长度与信号佐证。
- 对当前 `full-scale-v5` 的 73 个 B/C 预测制品（230,656 个点）重新扫描：
  - 23,930 个非可信状态点全部标为 `bc-short-status-disagreement-retained`；
  - 所有点的 `disagreement_run_length` 都是 1；
  - `corroborated_by_signal=true` 为 0；
  - `valid_point_mask=false` 为 0；
  - 独立按状态序列计算，B 有 4,906 个点位于长度至少 3 的连续段，最大连续段 955；C 有 17,667 个点位于长度至少 3 的连续段，最大连续段 1,270。
- `backend/tests/test_care_scoring.py:60-78` 由测试直接注入连续长度和佐证值，因此只证明评分器在收到人工字段后工作。
- `backend/tests/test_care_fullscale.py:90-121` 的全量 fixture 所有 status 都是 `0`，没有覆盖生产路径如何从 B/C 原始状态与信号产生这些字段。

### 影响

旧报告声称已实现的状态连续性语义在真实全量路径中没有发生。当前所有 B/C prediction 点都有效，评分、事件结果和激活指标使用的是一条与声明协议不一致的路径；单元测试通过不能证明生产算法存在。

### Required Changes

1. 在预测冻结前按 event、资产和源顺序计算连续非可信状态长度，明确事件边界和缺口处理。
2. 实现版本化、可审计的信号佐证算法，记录输入列、规则版本、证据值和结果；若产品决定不做佐证，应删除不可达分支并重新冻结协议，而不是保留永远为 false 的字段。
3. 由 verifier 从原始 status、信号和规则重新计算 `disagreement_run_length`、`corroborated_by_signal`、reason 与 `valid_point_mask`，拒绝调用方伪造字段。
4. 重新生成受影响的 prediction、evaluation、score、model/activation 与数据库制品。
5. 增加含短段、长段、跨 batch、缺口、事件边界和有/无佐证信号的 B/C 全量路径测试。

### Acceptance Criteria

- 生产全量 fixture 必须证明：短时 disagreement 保留；满足冻结条件的持续且被佐证 disagreement 被屏蔽；跨 batch 计算结果稳定。
- verifier 对手工修改连续长度、佐证值或 mask 的制品必须失败。
- 真实全量制品中这些字段必须由可追溯算法生成，不能全部停留在 dataclass 默认值；重新评分结果必须有差异说明和批准记录。

## CARE-C005 — 异常模型不存在生产激活成功路径

### 现状与证据

- `backend/src/windops_backend/services/models.py:247-279` 要求 anomaly 模型激活必须收到服务器签发的 `AnomalyActivationAuthorization`，缺失时 fail closed。
- 公开激活端点 `backend/src/windops_backend/api/model_registry.py:375-406` 调用 `activate_deployment()` 时没有加载评估证据、执行 `evaluate_activation_gate()` 或传入授权。
- rollback 端点 `backend/src/windops_backend/api/model_registry.py:409-434` 也没有 anomaly 授权路径。
- 前端 `components/pages/model-management-page.tsx:424-443` 只发送 `traffic_percent` 和 `reason`，并在 `:801-808` 对所有非 active deployment 展示同一激活按钮。
- `backend/tests/test_care_anomaly.py:620-624` 先明确断言 HTTP 激活失败；随后在 `:626-654` 由测试自身构造授权并直接调用内部 `activate_deployment()`，把内部函数成功当成垂直切片成功。
- 真实 PostgreSQL 竖向测试在 `backend/tests/external/test_postgres_care_vertical_slice.py:511-536` 采用相同的内部调用方式，没有经过生产 API。
- `evaluate_activation_gate()` 在生产 API/service 中没有调用点，当前调用点来自测试或离线构造逻辑。

### 影响

真实 UI/API 用户无法激活 anomaly deployment，也无法按同一安全语义回滚。当前测试既证明公开路径失败，又绕过公开路径制造成功，属于假完成；服务层的 fail-closed 防线本身正确，但产品工作流没有接通。

### Required Changes

1. 在服务器端为激活/回滚实现一条完整事务：锁定 deployment，加载权威 evaluation run、metric snapshots、model package、批准和审计事件，验证制品哈希与 invalidation 状态，执行冻结 gate，再原子切换流量。
2. 授权必须由服务器从权威状态生成并立即消费；不得接受客户端提供的 capability 或客户端声称的指标。
3. 为缺失证据、制品漂移、评估失效、指标不达标、错误 model/deployment 绑定、并发激活和 rollback 定义稳定错误与审计事件。
4. 前端按模型类型展示 gate 状态和阻断原因，并只调用公开 HTTP 路径。

### Acceptance Criteria

- HTTP + 真实 PostgreSQL 测试可以在不直接调用 `activate_deployment(..., anomaly_authorization=...)` 的情况下完成 anomaly 激活和允许的 rollback。
- 所有负向条件和并发条件均 fail closed，并证明没有部分流量切换。
- UI 端到端测试使用公开 API 完成成功和失败流程；测试代码不得自行签发生产授权来替代服务器流程。

## CARE-H006 — 质量 mask 未进入模型语义

### 现状与证据

- 当前全量 import manifest 的 73 个 B/C event 全部含非空 mask，共 7,386,831 条 mask 记录；mask JSON 合计约 3,231,531,488 bytes。
- `backend/src/windops_backend/benchmarks/care/fullscale.py:1653-1708` 的训练统计只读取 Parquet feature、split 和 status，以 finite 值计算 moments，没有加载质量 mask。
- `backend/src/windops_backend/benchmarks/care/fullscale.py:1795-1847` 的预测同样只对非 finite 值做均值填补，没有加载质量 mask。
- 当前 model/fold/prediction 制品记录 quality contract 身份，但没有冻结 `quality_mask_policy=apply|ignore`、实际使用的 mask hash/count 或忽略影响分析。
- `docs/care-v6-integration-development-plan.md:329-336` 明确要求模型训练声明如何使用或忽略质量掩码；当前实现没有满足该要求。

### 影响

大量被质量规则标记为疑似缺失的零段仍直接影响训练均值、标准差和 max-z score。即使最终选择“忽略 mask”，当前也没有显式协议、敏感性比较或批准证据，无法证明评估结果稳健。

### Required Changes

1. 冻结每个模型族的 mask 策略：应用时定义 feature/row 级语义、训练和预测填补；忽略时提供量化敏感性分析和批准依据。
2. 每个 fold/model/prediction 记录实际读取的 mask 制品哈希、规则版本、命中计数、处理计数和最终策略。
3. verifier 必须确认宣称应用的 mask 确实影响输入，宣称忽略时对应影响报告存在且绑定同一 source/feature set。
4. 重新训练和评估，并解释指标与阈值变化。

### Acceptance Criteria

- 含 B/C 长零段的生产路径测试能证明 apply 与 ignore 的确定性差异，并与冻结策略一致。
- 任意替换 mask、漏读 mask 或伪造计数都被 verifier 拒绝。
- 最终制品和数据库可以回答每个 fold 使用了哪个 mask、如何处理、影响了多少输入。

## CARE-H007 — 阶段制品不能在同一数据库升级

### 现状与证据

- `backend/src/windops_backend/services/benchmark_metadata.py:304-323` 把 quality report 身份固定为 `event_id + quality_rule_version + feature_set_version`；同一身份只允许 artifact、mask 和 summary 全部相同。
- 对 event A/0，最小和全量制品的底层 `source_quality_report_sha256` 完全相同，均为 `442c208b...8baa1`，但阶段包装后的 report file SHA 分别为 `6bac1793...ac52` 和 `0f8e2fdb...2261`，mask file SHA 分别为 `a1215ee7...70c3` 和 `d3e73044...dace`。
- 本轮在一个全新、迁移到 `0026_schema_contract_alignment` 的数据库中先运行最小/离线注册，阶段 1 成功；随后运行全量注册，稳定失败于 `ConflictError: quality-report identity already exists with different content`。
- 此前把 offline、vertical、full-scale 测试按真实顺序放入同一库时，还会因 `RegisteredModel` 不可变身份包含 `created_by`，而测试中的不同 worker subject 冲突。当前测试通过各用干净库掩盖了阶段组合问题。

### 影响

真实部署不能从最小接入、离线评估和竖向验证自然扩展到最终 95 event，而必须清库、换库或绕过不可变身份；这破坏发布升级和幂等语义。

### Required Changes

1. 明确 canonical 质量报告与阶段包装制品的身份：相同底层审计应复用同一 canonical 记录，或把 producer/stage/artifact kind 纳入明确版本化身份和查询语义。
2. 审查 `created_by` 是否应属于 RegisteredModel 的不可变业务身份；将审计主体与模型内容身份分离，或保证所有阶段使用同一受治理主体。
3. 如需 schema/unique constraint 调整，提供兼容迁移、既有数据回填和并发行为证明。
4. 增加单库阶段序列测试，不得在阶段之间 drop、truncate 或替换数据库。

### Acceptance Criteria

- 同一新库可依次执行 minimal import → offline evaluation → vertical slice → full-scale import/evaluation，全部成功且引用同一 canonical lineage。
- 完整序列再次运行时所有写入精确幂等；并发运行时不产生重复或内容冲突。
- 旧阶段记录在升级后仍可查询和审计，不通过清理历史数据达成通过。

## CARE-H008 — CI 依赖闭包缺少 benchmark extra

### 现状与证据

- `backend/pyproject.toml:47-49` 只在 `benchmark` extra 中声明 PyArrow 和 scikit-learn。
- `.github/workflows/ci.yml:189-190` 的主后端 job 安装 `.[test,dev]`；PostgreSQL job 在 `:289-290` 只安装 `.[test]`，两者都没有 `benchmark`。
- 当前本地 `.venv` 已预装 benchmark 依赖，因此普通本地全量测试通过，不能代表干净 CI。
- 本轮使用 CI 等价干净环境执行：
  - `uv run --isolated --extra test --extra dev --no-dev pytest tests/test_care_importer.py::test_a_minimal_import_is_wide_licensed_truth_isolated_and_deterministic`
  - 结果失败于 `ModuleNotFoundError: No module named 'pyarrow'`，随后抛出 `CarePipelineError: CARE pipeline requires the optional dependency group`。

### 影响

一旦当前未追踪 CARE 文件进入提交，主 CI 不能按现有安装步骤执行已收集的 CARE 单元测试。当前“本地通过”依赖工作站残留环境，不是可复现的 CI 证据。

### Required Changes

1. 在负责收集 CARE 测试的 job 安装锁定的 `benchmark,test,dev` 完整集合，或把 CARE 测试拆到显式 benchmark job。
2. 让 CI 安装方式与受审 `uv.lock` 一致，避免工作站已有包掩盖依赖缺口。
3. 增加干净环境 import/collection smoke，验证 PyArrow、scikit-learn 和 CARE CLI/worker 入口。

### Acceptance Criteria

- 从无项目虚拟环境和无预装包的 runner，按 workflow 原样安装后，CARE 单元测试可收集并执行。
- CI 中记录实际依赖锁哈希；移除 `benchmark` extra 后测试必须按预期失败，证明门槛有效。

## CARE-H009 — CARE PostgreSQL 验收未进入 CI

### 现状与证据

- 后端全量测试本轮收集 393 项：369 通过、24 skip、0 失败；3 条 CARE PostgreSQL 测试因没有外部环境而在这 24 条中跳过。
- 三个文件分别在以下位置通过环境变量 skip：
  - `backend/tests/external/test_postgres_care_offline_evaluation.py:27-30`；
  - `backend/tests/external/test_postgres_care_vertical_slice.py:90-93`；
  - `backend/tests/external/test_postgres_care_fullscale.py:35-38`。
- `.github/workflows/ci.yml:293-300` 的 PostgreSQL job 虽设置 `WINDOPS_FAIL_ON_SKIPPED=1`，但只显式收集 migrations、concurrency、service resilience 和 prediction lock 四个文件；三个 CARE 文件根本没有被收集。
- 对全部 workflow 搜索，没有任何 `test_postgres_care_offline_evaluation.py`、`test_postgres_care_vertical_slice.py` 或 `test_postgres_care_fullscale.py` 引用。
- 本轮手工启用这些测试后，暴露了阶段冲突和两类可重复性能失败，证明省略不是无害的覆盖差异。

### 影响

CI 的 `FAIL_ON_SKIPPED` 只能约束被收集的测试，无法发现完全未列入命令的验收文件。旧报告把手工、分库运行结果当成持续发布证据，属于测试证据不完整。

### Required Changes

1. 在 CI 中显式收集三条 CARE PostgreSQL 测试，并校验预期文件/测试数量，防止以后再次静默遗漏。
2. 为可提交的小型 fixture 建立每次变更运行的 job；真实大制品建立受保护的 scheduled/release job，并保存 JUnit、根哈希和性能属性。
3. 同时保留隔离单项测试和 CARE-H007 要求的单库阶段序列测试。
4. CARE 发布 job 必须 fail on skip、missing artifact、根哈希漂移和性能门槛失败。

### Acceptance Criteria

- Workflow 日志和 JUnit 明确包含三个 CARE PostgreSQL 文件，预期测试数与实际一致，skip 为 0。
- 删除或重命名任一验收文件会使 CI 失败，而不是减少收集数量后继续成功。
- 当前 CARE-H007/H011 的复现用例在修复前能使该 job 失败，修复后才转绿。

## CARE-H010 — 发布来源不可复现

### 现状与证据

- 当前 HEAD 为 `e70788b8fe040603fb3be718568db9da44eacbb1`。
- `git ls-files` 对 CARE 源码、CARE 单元测试和 CARE PostgreSQL 测试返回 0 个已追踪路径；当前至少 30 个相关文件仍是 untracked。
- 当前提交的 tree 中不存在这套 CARE 实现，但批准 manifest 与全量制品的 `generator.git_commit` 都记录上述 HEAD。
- `backend/src/windops_backend/benchmarks/care/contract.py:749-794` 只读取 `.git/HEAD`/ref，未检查 dirty/untracked tree，也未记录实际源码 tree 或 diff 哈希。
- 当前 `backend/uv.lock` SHA-256 为 `d6f55ffa...393de`；批准 `contract/manifest.json` 记录旧依赖锁 `27909000...c2c3`，manifest SHA 为 `ccf14bf3...f974b`。
- `contract/manifest-current-20260828.json` 记录当前锁，manifest SHA 为 `7d609d1c...7fe6a`；但 `full-scale-v5` 仍引用旧 source manifest `ccf14bf3...f974b`。当前同时存在两个根，最终制品没有沿用最新候选根。

### 影响

干净克隆到制品声称的提交后，没有生成这些制品的 CARE 代码和测试；同一提交号也不能区分当前大量未提交修改。依赖锁与 source root 分叉后，现有 lineage 不能支持可复现发布或事故追责。

### Required Changes

1. 把最终 CARE 源码、测试、迁移和 workflow 作为逻辑完整变更纳入版本控制；不得把未追踪工作树当作发布实现。
2. 发布生成器对 dirty/untracked tree fail closed，或记录并批准实际 source tree digest；仅记录 HEAD 不足够。
3. 选择唯一 canonical source manifest，绑定实际提交、依赖锁和工具版本，随后重建 quality、import、evaluation、model、prediction、activation 与数据库证据。
4. 增加 clean-clone reproducibility job，从记录的 commit + lock 重建并比较关键哈希。

### Acceptance Criteria

- 在干净克隆中 checkout 制品记录的 commit 后，所有 CARE 生成器和测试均存在，依赖锁哈希精确匹配。
- 发布运行时 `git status --porcelain` 为空，或有受批准且进入 provenance 的 source tree digest；任意未追踪/dirty 代码会阻断发布。
- 从干净克隆重建的 canonical manifest、quality contract 和选定关键制品哈希与发布证据一致，且只有一个批准根。

## CARE-H011 — 真实 PostgreSQL 性能门槛可重复失败

### 现状与证据

- 本轮使用固定 digest 的 TimescaleDB/pgvector 镜像，在各自全新数据库迁移到唯一 head `0026_schema_contract_alignment` 后单独运行测试；测试结束后临时容器和数据库已移除。
- 通用 100k 行 bounded collection 性能测试在无竞争负载下通过，因此没有把第一次并发运行的 963ms 误报为项目回归。
- CARE 竖向测试在两次全新数据库上均完成所有功能断言，但最终吞吐门槛失败：
  - 第一次 378 samples / 18.426745s = 20.514 rows/s；
  - 第二次 378 samples / 27.441022s = 13.775 rows/s；
  - 测试门槛为 50 rows/s。
- CARE 全量注册和目录功能断言完成后，查询 p95 在两次运行中均超过 500ms 门槛：
  - 第一次最大 p95 504.507ms；
  - 同库幂等重跑最大 p95 1,194.824ms，最慢为 `/api/v1/benchmarks/evaluations?limit=32&offset=32`。
- 证据保存在 `.artifacts/current-audit/postgres-care-vertical-isolated*.xml` 和 `.artifacts/current-audit/postgres-care-fullscale-isolated*.xml`。

### 影响

旧报告声称的全量性能与运行门槛不能复现，而且结果波动显著。当前外部测试若真正进入发布 CI 会失败；如果继续省略，则无法知道生产目录和回放写入是否满足容量目标。

### Required Changes

1. 对回放写入逐批 profile，减少每批事务、幂等、outbox 或 inline drain 的固定开销，并保持真实审计语义。
2. 对 evaluation 列表执行 `EXPLAIN (ANALYZE, BUFFERS)`，检查分页、关联加载、排序和索引；避免每页重复加载大 JSON 或 N+1 查询。
3. 固定性能测试环境、数据规模、预热、重复次数和资源预算，保存逐路径分位数而非只保存最终最大值。
4. 不得通过放宽门槛或缩小数据规模掩盖失败；任何门槛调整必须有容量模型和明确批准。

### Acceptance Criteria

- 至少 3 次独立新库运行均达到回放写入 ≥50 rows/s，并有合理余量。
- 全量五个目录路径各自 p95 均 ≤500ms，连续运行和幂等重跑均满足门槛，无单页尾延迟尖峰。
- 上述测试进入 CARE CI/release job，fail on skip，并保存数据规模、镜像 digest、迁移 head 和逐路径性能属性。

## 本轮验证矩阵

| 验证 | 结果 | 说明 |
| --- | --- | --- |
| 后端全量 pytest + coverage | PASS WITH SKIPS | 393 collected；369 pass；24 external skip；0 failure；总覆盖率 75.82%，门槛 68% |
| CARE 定向 pytest | PASS WITH SKIPS | 110 selected；106 pass；4 external skip；无法替代真实 PostgreSQL 验收 |
| Ruff format/lint | PASS | 192 个 Python 文件格式检查通过，lint 通过 |
| mypy strict | PASS | 92 个 source 文件通过 |
| Bandit / pip-audit | PASS | 无阻断发现；editable project 被 pip-audit 按工具行为跳过 |
| uv lock / container requirements / Alembic head | PASS | lock 校验、容器依赖导出、唯一迁移 head 均通过 |
| 前端 lint / typecheck / Prettier / production build | PASS | 全部通过 |
| 前端 Node tests | PASS | 143/143 |
| 前端 coverage | PASS | lines 90.34%、branches 51.31%、functions 33.09%，均超过 89/49/32 门槛 |
| 浏览器 E2E | PASS WITH SKIP | 6 pass、1 个环境依赖用例 skip |
| pnpm production audit | PASS | 未发现 production vulnerability |
| 干净 CI 依赖闭包 | FAIL | `test,dev` 环境缺少 PyArrow，CARE importer 失败；见 CARE-H008 |
| 根契约对抗性重签名 | FAIL | 真值交换和质量策略翻转重算自哈希后均被接受；见 CARE-C001 |
| B/C 真实 prediction 语义扫描 | FAIL | 23,930 个非可信点全部保留，连续长度/佐证字段全为默认值；见 CARE-C003 |
| PostgreSQL offline evaluation（独立新库） | PASS | 注册与幂等路径通过 |
| PostgreSQL minimal/offline → full-scale（同一新库） | FAIL | quality-report identity 内容冲突；见 CARE-H007 |
| PostgreSQL CARE vertical（两次独立新库） | FAIL | 20.514、13.775 rows/s，低于 50；见 CARE-H011 |
| PostgreSQL CARE full-scale（独立库 + 幂等重跑） | FAIL | 最大 p95 504.507、1194.824ms，高于 500ms；见 CARE-H011 |
| PostgreSQL 通用 100k 性能（独立空载） | PASS | 证明第一次并发负载下的失败不是单独登记依据 |

## 测试有效性结论

当前测试数量和覆盖率本身不低，但对本轮问题存在系统性盲区：

1. 自哈希测试只验证“修改后不重算哈希会失败”，没有验证“修改后重新哈希仍必须失败”。
2. 状态规则测试直接注入生产路径本应计算的字段；全量 fixture 又全部使用可信状态。
3. anomaly 激活测试先证明 HTTP 失败，再直接调用内部 service 并注入授权，绕过待验收边界。
4. PostgreSQL CARE tests 默认 skip，且 CI PostgreSQL job 根本不收集这些文件。
5. 各阶段使用独立干净数据库，掩盖同库升级冲突。
6. 本地已安装 benchmark extra，掩盖 workflow 的干净依赖缺口。

因此，`369 pass`、`143/143` 和覆盖率门槛通过都是真实结果，但不能证明 CARE 根契约、生产状态语义、激活路径、阶段升级、可复现发布和性能验收已经完成。

## 完成门槛

只有在以下条件全部满足后，才能重新声明 CARE 当前任务完成：

1. `CARE-C001`、`CARE-C003`、`CARE-C005` 与 `CARE-H006` 至 `CARE-H011` 均按各自 Acceptance Criteria 完成；
2. 从唯一批准根重新生成全部受影响制品和数据库证据；
3. 干净克隆、锁定依赖、单库阶段序列和隔离 PostgreSQL 测试全部通过；
4. CARE 外部验收进入 CI/release workflow，预期测试文件明确收集且 skip 为 0；
5. `EXECUTION_PROGRESS.md` 只能在实现与验证之后更新，不得继续沿用本轮已经证伪的 DONE 结论。
