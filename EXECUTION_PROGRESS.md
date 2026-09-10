# EXECUTION_PROGRESS.md

# Long-running Execution Progress

## 当前活动运行：2026-09-04 技术与 UI 审计整改

本节是当前执行状态的唯一 Source of Truth。任务来自 2026-09-04 `AUDIT_REPORT.md` 与 2026-09-03 `UI_AUDIT_REPORT.md`；后文所有旧轮次的 `COMPLETED`、`PASS` 或 `2 / 2` 仅作为历史证据，不能覆盖本轮状态。

### Metadata

- Project：`OpenVigil / wind-agent`
- Requirements：`PRODUCT_REQUIREMENTS.md`、`UI_UX_SPEC.md`
- Architecture：`ARCHITECTURE.md`
- Active Issues：`AUDIT_REPORT.md` 16 项 + `UI_AUDIT_REPORT.md` 8 项
- Execution Rules：`EXECUTION_GOAL.md` + `AGENTS.md`
- Started：`2026-09-04 09:48 +08:00`
- Last Updated：`2026-09-04 22:29 +08:00`

### Overall Status

- Current Phase：`COMPLETED`
- Current Issue：`NONE`
- Next Issue：`NONE`
- Final State：`COMPLETED`

### Statistics

| State | Count |
|---|---:|
| Total | 24 |
| TODO | 0 |
| IN_PROGRESS | 0 |
| DONE | 24 |
| BLOCKED | 0 |
| NOT_APPLICABLE | 0 |

### Severity Remaining

| Severity | Count |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

### Active Issue Register

| ID | Severity | Status | Dependencies / shared root | Evidence / Next action |
|---|---|---|---|---|
| CARE-C001 | Critical | DONE | — | Ed25519 独立签名根绑定 source/truth/mapping/quality/archive；导入、评估、模型与数据库记录传播并 fail-closed；真实 101 CSV/95 事件/5,242,948 行重建一致 |
| CARE-C003 | Critical | DONE | C001 | canonical 状态序列跨 batch 保持、缺口/split/event 重置；训练/预测真实应用，raw Parquet verifier 复算；官方 B/C 4,046,201 行分支实证 |
| CARE-C005 | Critical | DONE | C001,C003 | 权威 HTTP 激活/回滚、稳定拒绝审计、原子切流与 Sites 最小 allowlist；本地 17/17、网关 20/20，并在隔离 PostgreSQL 16.15 + TimescaleDB 2.29.2 + pgvector 0.8.6 完整迁移后通过真实并发激活/替换/回滚测试 |
| CARE-H006 | High | DONE | C003 | A/B/C full-scale 模型统一冻结 `apply`；训练 moments 排除 mask、预测按 fold mean 插补，model/fold/prediction 绑定完整 lineage 与计数，raw verifier 复算；官方 5,242,948 行重训重评记录 64,459,679 个训练特征值与 3,548,610 个预测特征值受影响 |
| CARE-H007 | High | DONE | C001,H006 | `0027` 分离 canonical parent 与 append-only stage artifact；同一新 PostgreSQL 库 minimal→offline→vertical→full-scale 真实通过，legacy 回填、冷/热并发幂等、97 条 stage 历史与 vertical 业务记录均验证保留 |
| CARE-H008 | High | DONE | H006 | backend/postgres required CI 改用 frozen uv lock 安装 benchmark；生产 container lock/image build/release verifier 共用 closure，clean wheel 验证 9 模块/9 CLI/6 包并记录双 lock hash |
| CARE-H009 | High | DONE | H007,H008; H011 performance gate | main-only self-hosted required job 显式运行三 CARE PostgreSQL 文件；evidence verifier 强制 4 tests/0 skip、同库阶段、性能、JUnit/root/commit/image/lock/head 同身份；本地三新库 4/4 |
| CARE-H010 | High | DONE | — | 官方 `v0.6.2/a338…` 映射为 immutable submodule；URL/commit/tree/MIT/source/docs/golden vectors 失败关闭并生成跨 checkout 相同证据根，干净递归克隆 19/19 |
| CARE-H011 | High | DONE | H007,H009 | PostgreSQL accepted batch 收据/stream lock/flush 有界化，边缘语义 fallback；3 次最终代码独立新库 replay 为 1062.266/524.165/529.685 rows/s，目录最大 p95 为 13.595/15.664/14.831 ms，SQL profile 进入 release verifier |
| TECH-H001 | High | DONE | shared: UI-H-002,UI-H-003 | 六态 query lifecycle + 权威 freshness + correlation/idempotency 恢复；四页生产状态矩阵浏览器通过 |
| TECH-H002 | High | DONE | — | v2 同身份证据集、11 类精确报告、受保护独立证据包和唯一 verifier qualification；生产镜像真实配置 boot 门禁 |
| TECH-H003 | High | DONE | H008,H009 | 同一 digest 镜像内独立 CARE CronJob/SA/Secret/PVC/egress；单并发/3 attempts/72,000s、断点重放 smoke 与受保护全量验收 |
| UI-H-001 | High | DONE | — | Demo/Production 共用事件决策区；6 KPI、7/5 主区、4/4/4 下层；1440/1280 与稳定/单一/多事件真实截图、键盘激活均通过 |
| UI-H-002 | High | DONE | shared: TECH-H001 | Production 仅表示模式；Shell/页面共用 Ready/Degraded/Stale/Offline，Dashboard 全错/局部错证据通过 |
| UI-H-003 | High | DONE | shared: TECH-H001 | 核心页 loading/refreshing/empty/filtered/error/partial/conflict/stale 及预测 long-running/result-unknown 已验证 |
| UI-H-004 | High | DONE | — | 核心流程移除未验证 RUL/失效概率；Demo/Production、外部模型和非 RUL 提前量边界就地可读；22 路由与生产 Agent 回归通过 |
| UI-H-005 | High | DONE | — | 13/12/11px 语义字号与行高 token；22 路由计算样式、图表字号、1440/1280/390 和 200% reflow 截图通过 |
| UI-H-006 | High | DONE | — | 1023px overlay drawer、焦点约束/Esc/返回焦点、laptop 折叠记忆、全路由移动 44px 目标与 200% reflow 均通过 |
| TECH-M002 | Medium | DONE | — | Sites release 记录、Worker 配置与 ready/代理 mismatch 均强制 release/commit/image 三元组；错 commit 失败关闭 |
| TECH-M003 | Medium | DONE | shared: UI-M-002 | 22 route×4 viewport 风险矩阵、5 页状态矩阵、4 角色 capability、关键页 axe/键盘/200%/reduced-motion、稳定基线与 fail-on-skip required 门禁 |
| TECH-M004 | Medium | DONE | — | Redis 有界队列、批量/幂等、分区/归档/保留和性能合同通过；两轮复查修复 Alembic drift/ORM 约束，并以数据库 advisory transaction lock 串行化手工/重试维护实例，真实 PostgreSQL 并发回归通过 |
| TECH-M005 | Medium | DONE | — | 7,852 个 / 334,332,149 bytes `.codex_tmp` 与新 `tmp/` scratch 均退出候选树；完整隔离候选 574 blobs / 23,611,578 bytes 通过，精确例外外的强制 `tmp` 注入失败关闭，真实索引 hash 不变 |
| UI-M-001 | Medium | DONE | — | Mission/风机详情统一 route ownership；当前侧栏 aria-current；可聚焦返回面包屑与键盘往返通过 |
| UI-M-002 | Medium | DONE | shared: TECH-M003 | 1440/1280/390 全页基线、900 tablet、22 路由语义/溢出 smoke、关键页 20 次 axe、6 页 200% 与完整状态闭环通过 |

### Stage / Convergence

- Critical：`COMPLETE`
- High：`COMPLETE`
- Medium：`COMPLETE`
- First Full Recheck：`PASS`
- Adversarial Review：`PASS`
- Final Global Validation：`PASS`
- Final Audit Pass：`2 / 2`
- Completion Gates：`MET`

### Completion Gate Review

| Gate | Result | Evidence |
|---|---|---|
| A — Coverage | PASS | technical `16/16 DONE`、UI `8/8 DONE`、Progress `24/24 DONE`，集合精确相等且无未登记活动问题 |
| B — Critical / High | PASS | 3 Critical、15 High 全部 `DONE`；remaining 均为 0 |
| C — Medium | PASS | 6 Medium 全部 `DONE`；Pass #2 发现的 TECH-M005 同根缺口已修复并完成正/负候选索引验证 |
| D — Evidence | PASS | 每项 DONE 均有实现、定向测试及可复验日志；最终 JUnit、coverage、CARE evidence 与 UI screenshots 均保留 |
| E — Recheck | PASS | First Full Recheck 与 Adversarial Review 均完成；发现项均先重开、修复、验证后关闭 |
| F — Global Validation | PASS | frontend required gates、425-test backend global suite、fresh PostgreSQL 23/23、真实跨层 E2E 1/1、Playwright 29/29 均通过 |
| G — Convergence | PASS | 两轮独立 Final Audit 均未发现新的 Critical/High，计数 `2 / 2` |
| H — Persistent State | PASS | 本节 Metadata、统计、Issue register、阶段、Gate 表与最终状态已同步为当前真实树 |

### Execution Log

#### Initialization / CARE-C001 Investigation Start (2026-09-04 09:48 +08:00)

- 已完整读取 `AGENTS.md`、`PRODUCT_REQUIREMENTS.md`、`UI_UX_SPEC.md`、`ARCHITECTURE.md`、两份 Audit、`EXECUTION_GOAL.md`、本文件全部历史内容，以及 `docs/ui/reference/` 的 README、生成提示和原始 `dashboard-desktop.png`。
- Git 起始状态不是 clean：`AUDIT_REPORT.md` 已修改，`ARCHITECTURE.md`、`PRODUCT_REQUIREMENTS.md`、`UI_AUDIT_REPORT.md`、`UI_UX_SPEC.md` 与 `docs/ui/` 未跟踪；这些均视为用户资产，不覆盖、不清理。
- 最新 Audit 证伪了旧 CARE `COMPLETED`：当前为 3 Critical、15 High、6 Medium；同根 `TECH-H001/UI-H-002/UI-H-003` 和 `TECH-M003/UI-M-002` 只实施一次、分别保留逐项验收证据。
- 当前先按 Critical 顺序调查 `CARE-C001`；尚未修改业务代码或将任何 Issue 标记为 DONE。

#### CARE-C001 Completed / CARE-C003 Start (2026-09-04 10:26 +08:00)

- 新增打包进 wheel 的 `care-v6-approved-root.json` 与只读公钥信任锚；批准根以 Ed25519 签名覆盖 canonical source、101 CSV 清单、95 条真值、A/B/C 映射、质量策略和 Zenodo 源压缩包身份，生产代码不包含私钥。
- minimal/full-scale import 在任何输出写入前从只读数据集和压缩包重建 source + quality contract；导入、预测、评估套件、模型包、顶层 manifest 及数据库 dataset/model/evaluation 记录均传播并复验同一批准根。自行重算 manifest/quality hash 的错误真值、错误零值策略、缺失映射或替换源压缩包仍被签名根拒绝。
- 官方真实源独立重建通过：101 CSV、95 事件、5,242,948 行；source manifest `33a11962...5c206`、quality `2241d0f2...c33b`、approved root `b08ba910...f446`、archive `ca61379e...194f1` 完全匹配。
- 验证通过：CARE 专项完整测试退出 0（仅显示 4 个默认关闭的真实外部环境用例）；full-scale 专项 9/9；Ruff 定向检查；mypy strict 5 个变更源文件；wheel 构建并确认批准根 JSON 被收录。pytest 缓存 ACL 警告仅影响缓存写入，不影响测试断言。
- `CARE-C001` 标记 `DONE`；开始 `CARE-C003`，先核对最新审计给出的 B/C 评分连续段、来源佐证和 verifier 复算缺口。

#### CARE-C003 Completed / CARE-C005 Start (2026-09-04 10:51 +08:00)

- 新增 canonical `StatusSequenceState`：run scope 固定为 dataset/farm/event/split/status，跨 record batch 保持状态，非连续 source row、split 与事件边界确定性重置；B/C 佐证只使用批准 Avg 集中的匿名缩放功率信号，规则与列集写入模型和 prediction 制品。
- full-scale 训练不再只做静态 `status in allowlist`：trusted、短/未佐证保留、持续佐证屏蔽均进入实际 moments，并按总量/held-out asset 写入 fold profile；prediction 每点保存 run length、佐证信号总数/finite 数/zero-or-invalid 数、rule ID、判定与 criticality。
- full-scale verifier 重新读取不可变 Parquet 的原始 row ID/split/status/批准信号，逐点复算 prediction 字段，并重算全局与每 fold 训练计数；调用方篡改佐证计数并重算 prediction 自哈希仍以 raw mismatch fail closed。prediction schema 升至 v2，full-scale 模型 schema/v6 实现与模型版本 `1.1.0` 避免旧制品冒充新语义。
- 固定 full-scale fixture 真实走 import→Parquet→training→prediction→verifier：短段 `[1,2]` 保留、持续段 `[1,2,3]` 的第三点屏蔽，训练侧 `2 retained / 1 masked`；跨 batch、缺口、split、事件边界有独立测试。
- 官方只读源全量逐行探针扫描 B/C `4,046,201` 行：`421,788` 条短/未佐证分歧保留，`9,064` 条持续佐证分歧屏蔽（train `9,022`、prediction `42`），覆盖 `67` 个事件，最大连续长度 `8,352`，证明生产分支不再停留在默认值。
- 验证通过：quality/scoring/offline/full-scale 定向套件退出 0；完整 CARE 选择套件退出 0（4 个默认关闭的外部环境用例）；Ruff lint/format、mypy strict、compileall、`git diff --check`。`CARE-C003` 标记 `DONE`，开始最后一个 Critical `CARE-C005`。

#### CARE-C005 Implementation Complete / PostgreSQL Gate Pending (2026-09-04 11:13 +08:00)

- 公开 activate/rollback endpoint 不再无授权调用 service：同一数据库事务先锁定 deployment/model/evaluation，校验 CARE online runtime、model package 三方绑定、完成且未失效的 evaluation、每条权威 metric 的制品 hash/方向/阈值/pass 状态，并从 CARE 专用 bucket/prefix 按数据库 SHA-256 读取 JSON evaluation artifact；model/evaluation/artifact 的 Ed25519 批准根 lineage 必须完全一致。
- 服务端由权威数据库 metric 重建 snapshot 和 activation policy，生成技术审批与 evidence-audited 事件，调用 gate 签发不可伪造授权并在同一事务立即消费；切流、授权证据、批准根和 activate/rollback 事件原子提交。制品漂移、评估失效、绑定漂移与并发重入分别返回稳定错误码并写 `model.activation.denied`，失败测试确认 deployment 保持 `staged / 0% / activated_at=null`。
- Sites 生产 gateway 仅新增两个精确资源 ID 路径：anomaly prediction run 与 alert evaluation；均只允许 POST 和 8–128 字符幂等键，prediction run 另强制 JSON，仍受 2 MiB 全局 body 上限、委托身份和 release identity 校验。编码斜线、过短 ID、GET/DELETE、缺 JSON/幂等键均 fail closed。
- 本地验证通过：anomaly + model-runtime HTTP 回归 `17/17`；覆盖公开激活成功、批准根传播、同部署第二次并发拒绝、替换部署、公开 rollback、制品漂移、invalidated evaluation、binding drift、拒绝审计和无部分切流；全后端 Ruff 与 strict mypy 通过。Sites production-runtime `20/20`、ESLint、Prettier 通过。
- 已把真实 PostgreSQL 并发 activate/rollback HTTP 测试加入既有 `tests/external/test_postgres_concurrency.py`，不直接构造或注入 `AnomalyActivationAuthorization`。当前机器未设置 PostgreSQL 测试 URL，项目 Docker Engine pipe 不存在，且无本地 PostgreSQL 服务/客户端；按安全边界未启动系统级 Docker 或触碰其他容器。因此本项仍保持 `IN_PROGRESS`，不能用 SQLite 或历史证据冒充本轮真实 PostgreSQL 通过。

#### CARE-C005 Completed / CARE-H006 Start (2026-09-04 11:38 +08:00)

- 在仓库内 `tmp/c005-postgres` 建立完全隔离、仅绑定 `127.0.0.1:55432` 的 PostgreSQL 16.15；没有创建 Windows 服务、修改全局 PATH、启动 Docker Desktop 或触碰其他项目容器。迁移最初依次真实暴露 TimescaleDB 与 pgvector 缺失，两次均在 PostgreSQL transactional DDL 内回滚，没有将环境失败误记为产品通过。
- 从官方 release 安装 TimescaleDB 2.29.2；pgvector 官方不发布普通 Windows DLL且本机无 MSVC，因此从官方仓库 tag `v0.8.6`（commit `8ee86c96`）源码用现有 MSYS2 GCC 构建。首个 DLL 真实暴露 32 位 pseudo-relocation 越界并由 PostgreSQL 自动恢复；改用 64 位 large code model 后成功加载。未执行检索到的第三方预编译 DLL。
- Alembic 从空库完整升级 `0001_wt023 -> 0026_schema_contract_alignment` 退出 0，TimescaleDB 与 vector 均由真实迁移创建。新增 PostgreSQL HTTP 合同测试退出 0：两个不同幂等键并发激活严格得到 `200 + 409 / ANOMALY_ACTIVATION_CONCURRENT_CHANGE`，随后替换部署激活、公开 rollback，并由数据库断言仅原 deployment 为 production active 100%。唯一告警仍是既有 pytest cache ACL，测试断言全部通过。
- `CARE-C005` 具备本地功能/负向/网关静态门禁与真实 PostgreSQL 事务并发证据，现标记 `DONE`；Critical 三项全部完成，进入 High 阶段并按依赖先开始 `CARE-H006`。

#### CARE-H006 Completed / CARE-H007 Start (2026-09-04 14:04 +08:00)

- A/B/C full-scale 模型统一冻结内容寻址的 `care-v6-model-quality-mask-apply-v1`：训练只用 `finite & ~quality_mask` 特征值计算 fold moments，预测对 mask 与 non-finite 值分别计数并用该 fold 的训练均值插补；同一 mask-trained profile 另计算仅预测时忽略 mask 的显式反事实，但不冒充完整旧模型重训。
- model package 绑定每个事件的 mask file/document/source-quality/source-event hash、range count 与 lineage hash；fold 绑定实际 profile、训练 mask 计数和 prediction mask 引用；prediction 绑定逐点 mask/imputation/反事实分数与总体计数。最终 verifier 重新读取 raw Parquet 和不可变 mask，精确复算训练 moments、逐点分数、二元判定、fold profile、impact 与所有引用；篡改 mask 计数并重签自哈希的测试仍 fail closed。
- 官方只读源重新完成 full import 与 full evaluation：95 事件、5,242,948 行、7,386,831 条 mask 区间；导入首次尝试即完成，资源策略通过，manifest file SHA-256 `69f6b33b...a241fc`。重训重评生成 3 个 farm model package、36 个 LOAO fold、95 个 prediction artifact、281,249 个预测点，最终 verifier 通过，manifest file SHA-256 `c771a7e9...20536`。
- 官方 impact 显示训练排除 64,459,679 个 masked feature values、影响 3,800,046 行；预测插补 3,548,610 个 masked values、影响 230,450 点；128,479 个分数及 86,026 个二元判定变化，最大/平均绝对分数差 `84.326869 / 3.542124`。36 个实际 fold 指标全部来自 mask-applied 分数；制品中的 counterfactual scope 明确限制为“同一 mask-trained profile，仅预测时忽略 mask”，因此对指标变化的解释可审计且没有夸大因果范围。
- 验证通过：官方 import/evaluate 两个 CLI 均退出 0、state=`completed`/attempt=1/无 resource violation；CARE 非外部完整选择回归退出 0；Ruff lint/format、mypy strict 与 `git diff --check` 均通过。最初一次导入在读取本轮临时质量 JSON 时因末尾字面 `\\n` 立即失败、未写派生数据；保留原语义并移除该封装字符后 JSON 自哈希不变，随后完成上述全量运行。
- `CARE-H006` 标记 `DONE`；开始 `CARE-H007`，先复现同一权威数据库 minimal → offline → vertical → full-scale 的 identity 冲突，再设计 canonical 内容身份与阶段制品身份的兼容迁移。

#### CARE-H007 Completed / CARE-H008 Start (2026-09-04 15:00 +08:00)

- 新增 `0027_quality_artifact_stages`：`benchmark_quality_reports` 增加可兼容 legacy 的 canonical 内容 hash，另建 append-only `benchmark_quality_artifacts` 保存阶段、wrapper/mask 身份与独立审计主体；迁移将所有旧 quality row 回填为 `legacy-migrated-v1` artifact，不删除或覆盖旧证据。注册服务按 event/rule/feature canonical scope 加事务 advisory lock，legacy 首次可信绑定、canonical 不一致失败关闭、阶段 artifact 精确幂等。
- minimal 与 full-scale registrar 统一传播签名根内的 `source_quality_report_sha256`，分别写 `minimal-import` / `full-scale-import`。父 quality row 保留最初 minimal wrapper；full-scale 只追加新 stage artifact/domain event。SQLite 正向、冲突、parent 不覆盖与 replay 单测 `4/4` 通过；真实 `0026→0027` legacy 回填与完整 migration suite `6/6`、0 skip，通过 JUnit SHA-256 `6D0608A2...F9218`。
- 从 template0 新建 `windops_h007_final` 并完整迁移 `0001→0027`；同一库先执行真实 minimal→offline→vertical（378 samples、7 predictions、1 Alarm/1 Mission/1 Decision），再追加 H006 官方 95-event/5,242,948-row full-scale。最终为 95/95 canonical parent、97 stage artifact/domain event（2 minimal + 95 full-scale），vertical 的 Alarm/Mission/Decision 均仍为 1，没有清理历史。
- 冷并发对首个 full-scale quality stage 精确得到 `created + replayed`，full-scale 总注册随后为 `1484 created / 87 replayed`；热并发为双 replay，历史总量不增长。阶段升级 JUnit `2 tests / 0 failures / 0 errors / 0 skips`、252.892 s，SHA-256 `5078AC49...92F424`。此前一次四重官方 verifier 实验已通过所有数据库/并发计数，最终仅因新增测试误把顶层 `farm` 当事件字段而失败；修正测试自身后改为一次官方全量 verifier + 数据库 service 冷/热并发，避免 required CI 重复扫描 9.27 GB。
- 权威 head/README/release 声明同步至 `0027`，完整 offline SQL render、Ruff lint/format、strict mypy 93 source files 与 `git diff --check` 均通过。`CARE-H007` 标记 `DONE`；开始 `CARE-H008`，核对 required CI 与生产镜像实际安装的锁定 benchmark closure。

#### CARE-H008 Completed / CARE-H009 Start (2026-09-04 15:12 +08:00)

- container requirements exporter 从只含 `connectors` 改为同时导出生产 `benchmark` extra，重新生成的 hash-locked closure 明确包含 PyArrow `23.0.1`、scikit-learn `1.9.0`、NumPy `2.5.2`、SciPy `1.18.1`、joblib `1.5.3` 与 threadpoolctl `3.6.0`；`uv.lock` SHA-256 为 `7366F9D5...3B08A`，`requirements.container.txt` 为 `90D01869...19E39`。
- 新增 `windops-care-dependency-closure`：逐包核对已安装版本与 container lock、导入 9 个 CARE production module、逐一执行 9 个 CARE CLI `--help`，输出含双 lock SHA-256 的确定性 JSON；缺包、版本漂移或 CLI 缺失均有负向测试并失败关闭。backend/postgres required jobs 改用 `uv sync --frozen` 安装 benchmark closure，并各自产出/上传报告。
- 标准 Dockerfile 在 runtime wheel/锁安装后强制生成 `/app/care-benchmark-dependency-closure.json`；release policy 把完整 CARE entrypoint 纳入镜像合同，container artifact verifier 在只读、non-root runtime 内再次运行 closure 并与 build-time JSON 精确比较，防止 build/runtime 漂移。发布镜像仍不包含 test/dev 依赖。
- 独立新 `uv venv` 从 `requirements.container.txt --require-hashes` 安装 125 个依赖，再从本轮 wheel 安装项目；验证 wheel 包含 closure 模块和 21 个 OpenVigil console scripts，9 模块/9 CARE CLI/6 包全部通过，`uv pip check` 对 126 packages 为兼容。首次用绝对路径启动 verifier 时未把 venv `Scripts` 加入 PATH，导致子进程误报 CLI 缺失；确认 wheel 元数据/脚本存在并按真实激活环境修正 PATH 后通过，分类为验证调用错误而非产品失败。
- 定向 deployment/release/CARE closure 回归 `55/55`，关联 trust/anomaly/import/metadata 回归 `21/21`；Ruff 全 197 files、strict mypy 94 source files、Bandit 0 finding、Prettier/TOML/YAML parse、lock reproducibility、wheel metadata 与 `git diff --check` 通过。本机 Docker Engine pipe 不存在，未启动系统服务或伪报本机 image build；实际 Docker build/release verification 已由同一失败关闭脚本写入 required workflow。
- `CARE-H008` 标记 `DONE`；开始 `CARE-H009`，把三个 CARE PostgreSQL 验收文件与同库阶段序列、测试数量、0 skip、JUnit 和 artifact/release identity 纳入 required CI。

#### CARE-H009 Completed / CARE-H011 Start (2026-09-04 15:36 +08:00)

- 新增 `windops-care-postgres-evidence` 与正/负向合同：读取三个指定 JUnit 并要求测试名集合严格为 offline `1`、full-scale `1`、vertical/stage-upgrade `2`，总计 `4` 且 failures/errors/skips 均为 0；缺测、skip、非有限性能值、阈值失败、root 不一致、placeholder image、commit/head/lock 漂移均拒绝。
- verifier 跨三个 JUnit 绑定 source manifest、quality contract、minimal import、offline evaluation、full import/evaluation 与 Ed25519 approved root 身份；同时绑定完整 Git commit、固定 TimescaleDB image digest、唯一 `0027` head、uv/container lock，并把各 JUnit SHA-256、所有属性与 canonical evidence root 写入原子报告。offline/full-scale/stage tests 已补齐这些属性，不依赖 workflow 自行声称成功。
- `.github/workflows/ci.yml` 新增 main-only `care-postgres-contract` required job；fork PR 永不进入 self-hosted runner。受控 `windops-care-v6` runner 必须提供两处只读 official artifact root，缺失即失败；三个独立新库逐一迁移至 head，显式运行三个审核指定文件，最后才由 evidence verifier 聚合。`verify_release_checks.py` 已将该 job 加入同 commit required checks；workflow/action 固定、结构和失败关闭合同 `36/36` 通过。
- 本地在 portable PostgreSQL 16.15 + TimescaleDB 2.29.2 + pgvector 0.8.6 上创建三套独立新库，按 required job 顺序得到 offline/full-scale/vertical `1 + 1 + 2 = 4` tests、0 skip/failure/error。JUnit SHA-256 分别 `2B17AFB8...B6BC33`、`EC39F242...CBA9B9`、`52501F6F...EDF3D3`；source root 三方均为 `33a11962...5c206`、approved root 三方均为 `b08ba910...ff446`，stage 为 95 parent/97 artifact、冷/热并发均精确。
- 本地不是容器，未把 workflow 的 TimescaleDB digest 伪写进本地 aggregate；image-bound canonical report 只允许 fixed-digest required job 生成。实际本地性能属性为目录最大 p95 `235.591 ms`、replay write `206.229 rows/s`，已进入下一项 H011 的 trial 1。`CARE-H009` 标记 `DONE`，按依赖立即开始 `CARE-H011` 的另外两次独立新库验证与 SQL/事务 profile。

#### CARE-H011 Completed / CARE-H010 Start (2026-09-04 16:20 +08:00)

- 根因画像确认目录服务已使用分页批量 SQL，主要不稳定源是 SCADA replay 的 54 点请求逐点执行 savepoint、receipt/stream 查询和 flush；慢资源下数据库往返被放大。新增 PostgreSQL accepted-batch 路径：一次 receipt `ON CONFLICT`、一次按稳定顺序的 stream-state 行锁、一次 flush；重复 receipt、批内重复 ID、quarantine 候选与直接告警样本先回滚 savepoint，再走原通用逐点路径，未改变幂等冲突、顺序、水位、隔离或告警/outbox 语义。
- 外部门禁现在对 7 个固定 `54` 点 replay 事务同时记录端到端时间、SQL 次数和数据库时间，并强制每批 SQL `<=40`；full-scale 在官方 `95` 事件、`36` evaluation、`1,285` mapping、`270` metric 上对 5 条路径各预热一次、测量 20 次，同时强制请求 SQL `<=12`、p95 `<=500 ms`、响应 `<=512 KiB`。显式 scoped evaluation metric 查询跳过全局 loader criteria 重编译，但仍由已经 scope-bounded 的 evaluation IDs 限制。
- 最终代码三套独立 fresh PostgreSQL 数据库的 replay 吞吐为 `1062.266 / 524.165 / 529.685 rows/s`，每轮 SQL 形状精确为首批 `14`、后六批 `13` 条；数据库总 SQL 时间为 `0.107085 / 0.106602 / 0.109597 s`。对应 JUnit SHA-256：`9B3818F5...D8EB21`、`5F689A90...10A78`、`01B03749...D2674`。
- 三套独立 fresh full-scale 数据库的最大目录端到端 p95 为 `13.595 / 15.664 / 14.831 ms`，SQL p95 为 `5.838 / 6.673 / 6.389 ms`，每次请求最多 `10` 条 SQL、最大响应 `125,313 bytes`；JUnit SHA-256：`12391847...64E2`、`EBE6B68A...FF14`、`DEB065EF...E6B0C`。六库均保持 migration head `0027` 与精确领域计数。
- 另在 fresh `windops_h011_release` 运行完整 vertical + stage-upgrade `2/2`、0 failure/error/skip；replay `738.588 rows/s`、最大 `14` SQL，最终 `95` canonical quality parents / `97` stage artifacts，JUnit SHA-256 `A85C1893...82E3`。release evidence verifier 现要求并复核上述 SQL profile 的测量数、有限值、聚合一致性和结构门槛；缺失或超限失败关闭。定向 ingest/catalog/access/transaction 回归 `58/58`，verifier `2/2`，Ruff、mypy strict、Bandit、compileall、diff check 全部通过。
- `CARE-H011` 标记 `DONE`。开始 `CARE-H010`，先调查审计所指无映射 gitlink 与当前 `docs/ui/reference/` 来源/许可/内容身份，建立不依赖本机目录的 clean-clone 复验链。

#### CARE-H010 Completed / TECH-H001 Start (2026-09-04 16:39 +08:00)

- 将原 gitlink 正式映射为 `.gitmodules` 中的官方 `https://github.com/AEFDI/EnergyFaultDetector.git` 子模块，并由 Gitlink 固定 `v0.6.2` commit `a338b6ef...2f63e` / tree `43c64cbe...45c912`；required backend job 使用递归 checkout，生产 runtime 不导入官方包。README、第三方声明、架构和 release runbook 明确该边界与 MIT 许可。
- 新增 `verify_care_reference.py` 失败关闭门禁：逐项绑定 upstream URL、tag、commit、tree、MIT license 原始 SHA-256、两份官方评分源码原始 SHA-256、五份 source-of-truth 的 UTF-8/LF 规范化 SHA-256，并动态运行官方 earliness/criticality 后与 OpenVigil golden vectors 比较。跨平台文档换行差异在复查中被发现并修正，官方源码与许可证仍为 byte-exact。
- backend `reference` extra 和 frozen `uv.lock` 提供复验所需 pandas；更新后 `uv.lock` SHA-256 `4D741E7D...D4E38D0`，生产 container requirements 仍为 `90D01869...19E39` 且 exporter check 通过，不把参考实现引入生产依赖闭包。
- 使用 alternate index/临时 ref 构造当前 prospective tree，真实 `git clone --recurse-submodules` 经 HTTPS 取得官方 submodule；新 clone 从 frozen lock 创建 161-package 环境并执行 verifier + scoring 合同 `19/19`。工作区与干净 clone 得到完全相同 evidence root `66497e8b...c7c4`、report SHA-256 `7AEC50EC...D3E54`；clean JUnit SHA-256 `A5EEB77E...ACC90`。真实 Git index 保持 0 staged，临时 ref 已删除。
- 本地定向复验同为 `19/19`，Ruff、`uv lock --check`、container requirement exporter 与 `git diff --check` 全部通过。`CARE-H010` 标记 `DONE`；开始共享根因 `TECH-H001 / UI-H-002 / UI-H-003`，一次建立权威 query lifecycle/freshness 状态并分别保留验收证据。

#### TECH-H001 + UI-H-002 + UI-H-003 Completed / TECH-H002 Start (2026-09-04 17:31 +08:00)

- 新增共享 `initial-loading | refreshing | success-empty | success-data | error-stale | error-no-data` 状态机，服务端数据时间优先于浏览器收包时间；错误分类保留 HTTP/code/correlation，Production 健康统一映射为 `Ready / Degraded / Stale / Offline`。App Shell 的 `Production`/`Demo` 标签改为中性模式标识，页面依赖与 `/api/runtime` 使用同一健康语义，生产侧栏、顶栏与页面不再固定显示成功。
- Dashboard 首次加载或全错只保留真实 Shell、页头和可重试状态，不渲染 KPI/空面板；权威空快照使用独立 Empty。非空快照的健康度、可利用率、电量和功率趋势缺失会逐模块列出 code、原因与各自最后时间，健康模块继续显示，Shell 降级为 Degraded；缺失数值使用 `—` 与原因而非伪零值。
- Mission、工单和预测页接入同一状态机，刷新保留旧记录并禁用依赖实时 revision 的动作；真实 Empty 与 Filtered Empty 分离，通用 DataTable 增加可键盘操作的“清除表格搜索”。全局 `loading.tsx` 使用真实 AppShell 与 6-KPI/主内容布局骨架，不再伪造独立 Shell。
- GET 403/409/5xx/network 均提供影响范围、上次成功、错误码、关联 ID 和就地重试；访问故障与恢复按 API scope 配对，其他健康请求不会误清除当前故障。预测在线评估进一步提供同步长运行时长、明确“无独立心跳/取消能力”，两次丢失响应后进入 `COMMAND_RESULT_UNKNOWN`，保留原幂等键核验且恢复成功后清除同 scope 全局故障，禁止新键重复提交。
- 新增 Chromium 状态矩阵：Dashboard/Mission/工单/预测逐页覆盖 pending、success-empty、403、409、500、network、stale refresh、刷新失败、同页恢复；另覆盖 Dashboard partial failure、三页 filtered-empty/clear 与预测 long-running/result-unknown/same-key reconciliation，共 `7/7`。保存并人工检查五张 stale/partial 全页截图及 `predictive-result-unknown.png`，未见假数据回退、空态闪烁或 Shell 健康矛盾。
- 验证通过：`pnpm typecheck`；`pnpm test` 的 build、bundle budget 与 Node `151/151`；完整 Playwright `13 passed / 1 skipped`，唯一 skip 为需显式真实后端环境的既有 `real-cross-layer` opt-in；ESLint/Prettier 定向检查和 `git diff --check` 通过。`TECH-H001`、`UI-H-002`、`UI-H-003` 分别标记 `DONE`；开始 `TECH-H002`，核对 release workflow 是否真正由唯一 verifier 生成 qualified。

#### TECH-H002 Completed / TECH-H003 Start (2026-09-04 17:58 +08:00)

- 新增 `windops-release-evidence`，以 release ID、完整 commit、镜像 digest 的规范化 SHA-256 生成 `evidence_set_id`；每类 gate 报告必须是 v2、检查集合精确完整、原始制品非空且内容寻址。assembler 只接受 11 类同身份证据并生成 manifest/digest，不生成发布结论；final verifier 拒绝跨候选、缺失、重复、篡改、路径逃逸、符号链接、单报告超 24h、证据跨度超 72h 和 assembly 延迟超 15 分钟的 bundle。
- `release.yml` 删除自行构造的 `release-chain.json status:qualified`。镜像扫描/SBOM/签名/部署策略/外部依赖五类报告由当前运行标准化；迁移回滚、DR、DAST、WCAG/视觉、SLO、Sites post-deploy 六类必须从受保护 HTTPS 下载、以预登记 ZIP SHA-256 验证，并由有界安全解包器拒绝缺项、覆盖、链接、逃逸和压缩炸弹。只有 `windops-release-gate --qualification-output` 在 11 类全部通过后创建 `release-qualification.json`，且拒绝覆盖已有结果。
- built-image smoke 不再写死 `WINDOPS_ENVIRONMENT=development` 或开发依赖。workflow 先加载不能覆盖 candidate identity 的受保护 production 配置，再以同一个 env-file 从已构建 digest 镜像执行 Alembic、启动 API，并要求 ready 响应精确返回当前 release/commit/image 及 PostgreSQL、Redis、MinIO、Neo4j 全部 ready；生产 trusted Host 同时用于 HTTP smoke 和 Docker healthcheck。
- 对抗性测试覆盖缺门禁、错检查、错 evidence-set、旧报告、篡改、路径逃逸、unsafe ZIP、缺独立 gate、development env、candidate identity override 和重复 qualification。发布专项 `46/46`，扩展 release/CARE 专项全通过；完整 backend 单测完成且零 failure（外部测试显式 skip）；Ruff 全后端、strict mypy `96` source files、frozen uv lock、workflow YAML/Prettier 和 `git diff --check` 通过。由于本机没有 Docker Engine 和受保护外部证据服务，本轮没有伪报真实镜像/外部门禁运行，但 workflow 对这些输入严格 fail closed。
- `TECH-H002` 标记 `DONE`；按 High 顺序开始 `TECH-H003`，建立 CARE 独立镜像、队列、资源、checkpoint/storage 权限与实际 workload smoke。

#### TECH-H003 Completed / UI-H-001 Start (2026-09-04 18:24 +08:00)

- 新增同一 digest 生产镜像中的 `windops-care-full-scale` suspended CronJob：专用 `windops-care-worker` ServiceAccount、外部 `windops-care-runtime` Secret、只读 40 GiB source PVC、独立 80 GiB workspace PVC；队列固定 `care-v6-offline`，`parallelism/completions=1`、`backoffLimit=2`（共 3 次）、72,000 秒 deadline。工作流按同 job/state 路径依次执行 dependency closure、95-event full import、36-fold evaluation、事务 registration，再重放三阶段验证幂等。
- CARE pod 不再继承 general runtime egress/Secret：独立 NetworkPolicy 只开放 DNS、PostgreSQL 5432 和 MinIO 9000 到双重 `care-dependency-access` 标签目标；专用 Pydantic runtime 只读取 `WINDOPS_CARE_DATABASE_URL` 与 MinIO 凭据，强制 PostgreSQL/MinIO TLS、强凭据、CARE bucket 与四个运维 bucket denial list。现有最小 MinIO policy 无 DeleteObject，storage policy hash 进入验收。
- 新增 built-image `windops-care-workload-smoke`，在 non-root/read-only 容器内真实执行小型 Parquet：首次在 durable checkpoint 停止、同 state 恢复、再次同 ID 重放并要求相同内容 hash。release workflow 对 exact image digest 执行该 smoke；没有用假 full-scale 数据替代 5,242,948 行验收。
- 受保护独立证据增加 `windops-care-fullscale-acceptance`：绑定当前 release/commit/image，解析并内容校验 dependency、import/evaluation manifest、两份 completed state、两份 replay、初次/重放注册、storage denial 共 10 个精确角色原始制品；强制 95 events、36 folds、资源通过、cross-farm disabled、transactional replay 与运维 bucket 全拒绝。`external_release` 的检查集合现同时要求 image smoke 和该 protected full-scale acceptance，缺项不能组装或 qualification。
- 客观验证通过：新 CARE execution/acceptance、full-scale、container、deployment、release gate/pipeline 相关 `77/77`；Ruff、strict mypy、frozen lock、Prettier、`git diff --check`；`kubectl kustomize` 渲染 19 resources/6 workloads 并由 deployment policy 通过；wheel 构建确认包含 runtime、smoke fixture、smoke/acceptance verifier。当前机器仍无 Docker Engine 和受保护外部证据服务，因此没有伪报当前 digest 的镜像/全量外部运行，发布流程对此严格失败关闭。
- `TECH-H003` 标记 `DONE`；High 技术项结束，开始 `UI-H-001`，按参考图重构 Dashboard 并执行桌面/移动截图循环。

#### UI-H-001 Completed / UI-H-004 Start (2026-09-04 18:40 +08:00)

- Demo 与 Production 首页现共用事件决策条：按严重度与持续时间稳定选取最高事件，展示公开 AI 状态、健康值、异常强度和权威数据时间；无高优事件使用独立绿色稳定态并跳转告警中心，不把未知值渲染为零。
- 两种运行模式均精确收敛为 6 个核心 KPI（当前功率、24h 电量、运行机组、平均健康度、活跃告警、活跃 Missions），桌面主区固定 7/5 功率趋势与优先队列，下层为 4/4/4 Mission、Agent 活动、作业窗口；窄屏顺序为事件、队列、趋势、Mission、Agent、天气，1280 下 KPI 精确为 3×2。
- 新增 Chromium E2E 覆盖 Demo 1440×900、Demo 1280×800、Production 稳定/单一 P1/多条高优事件，以及真实焦点和 Enter 触发的键盘链接激活；`3/3` 通过。五张全页截图已逐张人工复核，生产下方面板语义结构和文本布局在第二轮修正后通过。
- 验证通过：Prettier、TypeScript、ESLint、production build；真实截图位于 `.artifacts/playwright/test-results/dashboard-incident-layout-*`。`UI-H-001` 标记 `DONE`，开始 `UI-H-004` 全仓术语/数据来源扫描和 22 路由业务边界整改。

#### UI-H-004 Completed / UI-H-005 Start (2026-09-04 19:05 +08:00)

- 核心业务数据、类型、排序、风险矩阵、活动流、Mission 证据、报告、资产健康、风机详情、数字孪生、诊断与预测性维护均移除合成 RUL / 30 天失效概率；改由异常分数、健康评分、告警事实、证据等级与运营后果驱动。Production adapter 会丢弃后端遗留的寿命/概率字段后重新计算证据等级，Demo 模型明确为隔离的状态证据演示，不参与生产决策。
- 前端 Agent catalog 删除 `predict_rul`；后端生产 Agent 同根替换为 `assess_condition_evidence`，只返回原始异常/趋势输入、状态与证据等级，不再计算预计天数或失效概率。外部模型登记仍可描述独立验证过的预测合同，但合同旁就地说明 CARE 不验证、Demo 不生成或展示此类结论；诊断提前量明确为来源行偏移而非 RUL。
- 验证通过：Node 全量 `155/155`，随后受影响前端定向 `17/17 + 8/8`、边界测试 `5/5`；后端 domain/vertical 与 Agent governance/reasoning 套件全部通过，Ruff、strict mypy、TypeScript、ESLint、production build 和 `git diff --check` 通过。全仓精确结论扫描为零，核心源仅保留上述显式边界。
- Chromium 真实遍历 Demo 22 路由 `1/1`，并对 `/health`、`/predictive-maintenance`、`/digital-twin`、`/turbines/WT-023` 生成和人工检查 1440×900 全页截图；页面以异常、健康、告警和证据等级表达，没有未标注的精确寿命/失效概率。`UI-H-004` 标记 `DONE`，开始 `UI-H-005` 字号 token、全站可见文本与 200% reflow 整改。

#### UI-H-005 Completed / UI-H-006 Start (2026-09-04 19:25 +08:00)

- 在全局设计系统建立 `13px Body/Table`、`12px Secondary`、`11px Metadata` 及对应行高 token；626 处原 5.5–10.5px 声明按语义迁移，`small` 与 `strong` 重置分别守住元信息和关键值下限，状态 Badge、导航、分段控件、关键数值、操作标签及 DataTable 表头/正文使用正确层级。时间序列与知识图谱 canvas 标签也提升至不低于 11px。
- 新增静态 typography contract：扫描 `app/components` 全部 CSS，禁止任何 literal px 小于 11，并验证共享 token、Body、Button、StatusBadge、DataTable 和 canvas 配置；`4/4` 通过。新增 Chromium computed-style 审计真实遍历 22 路由，断言全部可见文本 ≥11px、关键/可操作文本 ≥12px、表格 cell 基线 13px，`1/1` 通过。
- 生成并人工对照 reference 检查 Dashboard 的 1440×900、1280×800、390×844 全页截图：首屏风险、六项 KPI、7/5 主区与 4/4/4 下层层级保留，字号和状态/单位/时间来源可读；未以裁剪必要信息换取密度。以 720 CSS px 验证 1440 视口 200% zoom 等效 reflow，对 Dashboard、Mission 详情、模型和数据页断言无页面级横向溢出、标题/按钮/状态/页面说明无裁切，并人工检查三张全页截图。
- 验证通过：Typography Chromium `3/3`、TypeScript、ESLint、production build、Prettier 与 `git diff --check`。`UI-H-005` 标记 `DONE`；开始最后一个 High `UI-H-006`，修复 tablet drawer、laptop 折叠记忆、移动触控目标与焦点约束。

#### UI-H-006 Completed / TECH-M002 Start (2026-09-04 19:39 +08:00)

- App Shell 的 overlay drawer 断点统一到 `1023px`：抽屉带遮罩、背景 inert、ARIA modal、首焦点、正反向 Tab 约束、Escape/关闭按钮关闭和菜单触发器焦点返回；打开时锁定 body 滚动，离开 overlay 断点自动清理状态。`1024–1439px` 默认折叠并用本地偏好记忆人工展开/收起，折叠只影响桌面侧栏，不会让平板抽屉丢失标签。
- `767px` 及以下将主要按钮、图标按钮、导航、表单控件、summary 和可点击业务行的两个维度统一守到至少 `44px`；焦点工具会过滤 CSS 隐藏、inert 和无布局框元素，避免把不可见的桌面控件纳入移动抽屉焦点环。
- Chromium 专项真实覆盖 900px drawer 与 720px（1440 视口 200% 等效）键盘路径、1024/1280px 侧栏默认/偏好持久化及主内容宽度，并以 390px 遍历 22 条路由全页交互目标、表格内滚动和 document overflow，另抽查 320/360/430px Dashboard；最终 `3/3`。人工检查更新后的 900/1024/1280 全页截图，首屏位置、抽屉遮罩、内容层级及桌面展开态均正确。
- 初次全路由触控审计真实发现 7 条路由存在 29–36px 控件，修正通用规则后才通过；没有弱化断言。最终 TypeScript、ESLint、production build、响应式/字号静态合同 `6/6` 与 `git diff --check` 通过。`UI-H-006` 标记 `DONE`，High 阶段全部完成；进入 Medium 并开始 `TECH-M002` release commit identity 校验。

#### TECH-M002 Completed / TECH-M003 Start (2026-09-04 19:43 +08:00)

- Sites Worker 的 production config 新增强制 `WINDOPS_BACKEND_EXPECTED_COMMIT_SHA`，只接受非全零的 40/64 位小写完整 SHA；生产缺失、占位或格式错误均在读取配置时失败关闭。`releaseMismatch()` 现精确比较 release ID、commit SHA 与 image digest 三元组，因此 `/readyz` 探针和每个代理业务响应不会再把 commit 仅解析后透传。
- `release-candidate` 的 `sites-release-bindings.env` 现把 `${GITHUB_SHA}` 与同候选的 `${RELEASE_ID}`、`${IMAGE_DIGEST}` 一起记录；Worker env、生产 E2E server、标准启动隔离变量、示例配置及发布 runbook 同步该字段。流水线测试精确断言三条发布绑定，避免以后静默删回 commit。
- 新增缺 commit、全零 commit、ready 错 commit、代理响应错 commit 的负向断言；Node production runtime `20/20`、backend release pipeline `31/31`、TypeScript、ESLint、production build、Ruff 与 `git diff --check` 全部通过。`TECH-M002` 标记 `DONE`；开始与 `UI-M-002` 共根的 `TECH-M003` UI 自动化验收矩阵建设。

#### UI-M-001 Completed inside TECH-M003 Matrix (2026-09-04 20:01 +08:00)

- 新验收矩阵首先复现详情 route 严格相等导致导航归属丢失。新增单一 route ownership：`/missions/:id` 归属 `/missions`；Demo 风机详情归属“风机”，Production 风机详情归属资产目录“风场”；查询参数/fragment 不影响归属。所有当前侧栏链接仅对唯一 owner 设置 `aria-current="page"`。
- `PageHeader` breadcrumb 向后兼容字符串并支持真实链接；Mission 详情的“Mission 中心”及风机详情的“风场”成为有明确返回名称的原生链接，不依赖浏览器后退。Mission 列表链接进入详情、读屏当前项、聚焦返回链接、Enter 返回列表的 Chromium 路径通过；route mapping 单元合同 `2/2`。
- axe 首轮同时发现 Progress 只有 `aria-label` 而无语义角色，现统一为带 min/max/now 的 `progressbar`；Mission 纵向时间线和移动横向阶段栏成为有名称的键盘可滚动区域。`UI-M-001` 标记 `DONE`；继续完成 `TECH-M003/UI-M-002` 共根矩阵。

#### TECH-M003 / UI-M-002 Completed / TECH-M004 Start (2026-09-04 20:17 +08:00)

- 新增单一 `routeAcceptanceMatrix`：22 个工作区按 critical/standard 分层，覆盖 1440×900、1280×800、900×900、390×844 四视口；每个组合验证主区、唯一 H1、唯一且正确的 `aria-current` 导航归属、致命错误、route fallback 与页面横向溢出，共 88 个 route×viewport 组合。Dashboard 三份稳定全页基线已纳入版本控制并逐张人工检查。
- 所有 10 个关键路由在 desktop/mobile 共 20 次 axe serious/critical 扫描通过；Mission 全键盘往返与 reduced-motion 通过；200% 等效验证扩展到 Dashboard、Mission 详情、Decision、Work Order、Models、Data。扫描首次发现的真实颜色对比度、Progress 语义、搜索名称、时间线/阶段栏键盘滚动和预测风险矩阵触点问题均已修复，没有 exclusion 或弱化断言。
- Decision Center 补齐 `initial-loading / refreshing / success-empty / permission / conflict / service / network / stale / disabled`：错误不再伪装为空队列，失败刷新保留旧数据但锁住审批；approve/reject/request-revision/escalate 分别绑定后端 capability。Manager/Approver/Reviewer/Field 四角色真实生产浏览器断言逐动作启禁。
- Playwright 默认排除只应在真实后端 job 运行的跨层 spec，browser 与 real-cross-layer 两个 required job 都启用自定义 fail-on-skip reporter；静态合同固定 22 route、4 viewport、4 role、生命周期、三份 baseline 与 CI 证据保留。回归还发现 Dashboard 任务入口的框架链接键盘 Enter 不导航，已改为原生锚点并保留严格键盘断言。
- 验证通过：TypeScript、ESLint、production build；UI 合同 Node `7/7`；四份核心 Playwright spec 最终 `22/22`、0 skip（含状态、角色、200%、WCAG、视觉基线）。`TECH-M003` 与同根 `UI-M-002` 同时标记 `DONE`；开始 `TECH-M004`。

#### TECH-M004 Completed / TECH-M005 Start (2026-09-04 20:40 +08:00)

- 所有业务 GET 在业务查询前把 `windops.read-access.v2` 最小化事件写入有界 Redis Stream；保留服务端 subject/role/method/endpoint/UTC 与 canonical query/scope SHA-256，仅保留参数和授权范围计数，不保留查询、租户、风场、风机或 data-scope 原值。Redis 超时/故障与队列满分别稳定返回 `READ_AUDIT_UNAVAILABLE` / `READ_AUDIT_BACKPRESSURE` 的 503，业务读不会执行。
- 独立 worker 以 consumer group 批量写 PostgreSQL，提交后才 XACK+XDEL；失败批次保持未确认并可 reclaim，重复投递由 `(accessed_at,id)` 幂等。`0028_read_audit_pipeline` 已把热表迁为月 RANGE 分区并创建默认/前月/本月/未来三月分区；日常维护把 30 天前完整最小化记录原子转为确定性 gzip JSONL，SHA-256 校验并保留至最后事件后 365 天。备份、Kubernetes worker/CronJob、release policy、配置和运维手册均已接通。
- 隔离 PostgreSQL 16.15 + TimescaleDB 2.29.2 + pgvector 0.8.6 的新库从 `0001` 全量升级至唯一 head `0028`；真实 1,000 条写入只产生 2 个 500 条事务，写放大 `0.0020`，批事务 p95 `47.298ms`，6 个分区与 3 条过期热记录的原子归档/解压/hash/删除全部通过。CI 的 `postgres-contract` 已纳入同一外部合同且 fail-on-skip。
- 定向 Ruff、mypy strict 5 个源文件、读审计/权限/部署/发布/备份回归 `88/88`、真实 PostgreSQL 合同 `1/1`、唯一 migration head、offline SQL 和 whitespace 检查通过；pytest 唯一告警仍是项目缓存目录 ACL。`TECH-M004` 标记 `DONE`；开始最后一个活动问题 `TECH-M005`。

#### TECH-M005 Completed / First Full Recheck Start (2026-09-04 20:43 +08:00)

- 从 Git 索引精确移除 `.codex_tmp` 的 7,852 个文件、334,332,149 bytes，其中 7,792 个是嵌套 `node_modules`、56 个是 `.dll/.node/.wasm` 原生或二进制制品；使用 `git rm --cached`，本地 scratch 未删除。根 `.gitignore` 已排除该目录，复验 tracked count 为 0 且 `git check-ignore` 命中。
- 新增版本化 artifact policy 和 `pnpm check:repository-artifacts`：直接审计 Git index，拒绝 `.codex_tmp`、构建缓存、嵌套依赖目录；任一超过 10 MiB 的受控例外必须同时登记稳定 source URI、license、内容 SHA-256 和 content-addressed scan evidence。当前剩余 519 个 tracked blob、20,485,844 bytes，无单文件超过 10 MiB，因此 allowlist 保持空，不伪造“必须保留”大制品证据。
- 主 frontend required CI 在安装依赖前运行该门禁；脚本、ESLint、Prettier、policy 输出和 whitespace 检查通过。`TECH-M005` 标记 `DONE`，本轮 24/24 Issue 首次全部完成；依照目标不结束，进入 First Full Recheck。

#### First Full Recheck — TECH-M004 Reopened (2026-09-04 21:12 +08:00)

- 第一轮完整前端门禁修复 3 个格式漂移后通过：artifact policy、TypeScript、ESLint、Prettier、production build、bundle budget、167 个 Node 测试、75.10% 后端覆盖率（397 passed / 27 外部环境 skip / 0 failed）、Ruff、Bandit、strict mypy 100 源文件、官方参考等价、lock/容器依赖和 startup smoke 均成立；Chromium 全矩阵 `29/29`、0 skip。
- 安全复查发现 `pypdf 6.16.0` 的 CVE-2026-84310/84311，已把最低版本提升至 6.16.1、实际锁定/容器清单更新为 6.17.0，重跑 `pip-audit` 为零已知漏洞；同时移除 CARE runtime 过期 `type: ignore`，全量 mypy 恢复通过。
- 真实 PostgreSQL required contract 首轮 21 项中 20 项通过、1 项失败：`alembic check` 把 `0028` 的物理月分区子表识别为 ORM 应删除对象，同时发现 archive ORM 漏声明迁移中的 3 个 check constraint。该失败属于当前修改而非环境问题，故 `TECH-M004` 立即重开为 `IN_PROGRESS`，修复并重跑前不得恢复 DONE。

#### First Full Recheck — TECH-M004 Revalidated (2026-09-04 21:32 +08:00)

- Alembic 环境现在只忽略由 `read_access_audit` 声明式分区产生的物理 child tables/objects，仍对 canonical parent、archive 表及普通 schema drift 失败；archive ORM 补齐 `row_count > 0`、period ordering、expiry 三个迁移约束。Ruff、strict mypy、精确迁移回归与 `alembic check` 均通过，输出 `No new upgrade operations detected.`。
- 在第二个 fresh PostgreSQL 库从 `0001` 升级至 `0028` 后，required contract `22/22`、0 skip、0 fail，含 6 个读审计分区；1,000 条真实写入 2 个事务，写放大 `0.0020`，批事务 p95 `271.687ms < 500ms`。一次复用旧本地 DB 的固定证据 ID 冲突被判定为无效 harness reuse，随后完整 fresh-DB job 排除了产品失败。
- CARE release 三个独立 fresh DB job 同样在最终迁移头通过：offline `1/1`、full-scale `1/1`、vertical `2/2`、全部 0 skip；release evidence verifier `4/4`，目录 overall p95 `16.832ms`、SQL p95 `8.766ms`，replay `940.168 rows/s`，full-scale 1,571 imports / 404 evaluations / 270 metrics。`TECH-M004` 恢复 `DONE`，活动问题为 0；继续跨报告验收扫描，尚未提前宣告 First Full Recheck PASS。

#### First Full Recheck Completed / Adversarial Review Start (2026-09-04 21:40 +08:00)

- 从两份报告重新解析出精确 `16 technical + 8 UI = 24` 个唯一 Issue，并与当前 Progress 登记逐项比较：`24/24 DONE`、0 missing、0 extra、Critical/High/Medium remaining 均为 0。逐项复读全部 Required Change / Acceptance Criteria 与 Suggested Validation，确认同根 `TECH-H001/UI-H-002/UI-H-003`、`TECH-M003/UI-M-002` 的实现和证据没有重复分叉。
- 当前产品源码、测试、迁移、脚本和 workflow 扫描无 TODO/FIXME/HACK/XXX；变更测试没有新增 skip/xfail/only、空断言或 coverage 弱化。命中的 `placeholder` 均为表单属性或对不可部署占位身份的失败关闭合同；外部 PostgreSQL 文件只保留显式 environment skipif，required jobs 和本轮 fresh-DB runs 均以 fail-on-skip 得到 0 skip。
- 补跑审计基线曾缺失的真实跨层链路：fresh PostgreSQL `0001→0028`、真实 FastAPI HTTPS、真实 Worker delegated JWT 与 Chromium；待轮换审计先使 `/readyz` 返回 503，经授权、幂等 Worker POST 确认后恢复 200 ready，Playwright `1/1`、0 skip。隔离 DB 已精确删除，证据保留于 ignored `.artifacts`。
- 两份 Audit 的 Issue index 已只更新最终状态：technical `16/16 DONE`，UI `8/8 DONE`；原 Problem、Impact、Required Change 和 Acceptance Criteria 保持不变，最终接受仍明确受后续三阶段约束。First Full Recheck 判定 `PASS`，不增加 Final Audit 计数；现在进入 Adversarial Review。

#### Adversarial Review — TECH-M004 Reopened and Fixed (2026-09-04 21:48 +08:00)

- 恢复/并发审查发现 read-audit retention 在事务外先读取待归档行；CronJob `concurrencyPolicy: Forbid` 不能约束手工启动、重试或第二调度器。首次无延迟并发探针偶然通过，未据此忽略；加入只作用于 fresh 测试库的 archive-insert delay 后，4 个并发实例稳定复现相同 SHA-256 archive 主键冲突，证明是产品竞态而非理论风险。
- `maintain_read_audit_retention()` 现对 PostgreSQL 在读取任何 live row 前取得 transaction-scoped advisory lock，并在同一事务内完成选择、确定性 gzip、archive insert、live delete 和 expiry purge；正常 K8s 调度约束保留为第一层。新增真实 PostgreSQL `4` 并发回归严格要求结果为 `[0,0,0,25]`、单一 archive、零 live row。
- 修复后真实 PostgreSQL 并发回归 + 本地 read-audit 套件 `9/9` 通过，Ruff lint、strict mypy 和 whitespace 检查通过；此前 deliberate pre-fix probe 的唯一约束失败已保存为根因证据。`TECH-M004` 再次恢复 `DONE`，Final Audit 仍为 `0 / 2`，继续其他 adversarial 类别。

#### Adversarial Review Completed / Final Global Validation Start (2026-09-04 21:50 +08:00)

- `invalid input / empty / repeated action / network / API / permission / stale / concurrency / restart / partial failure / production configuration` 全部按现有产品边界重验。后端 98 个定向合同、前端 64 个状态/身份/幂等合同、Chromium 18 个状态矩阵/角色/网络/响应式场景均 0 failure、0 skip；read-audit 的新 PostgreSQL 竞态是本阶段唯一新增真实发现，已修复并回归。
- repository artifact 门禁通过独立临时 Git index 注入一个 retained `.codex_tmp` 文件，稳定退出 1 并指出 forbidden cache path；真实 Git index SHA-256 前后相同。正常门禁仍为 519 blobs / 20,485,844 bytes / 0 governed large artifacts。CI/release 的外部 action 全部固定 40 位 commit，`continue-on-error/allow_failure=0`，只有 final verifier 能写 qualification。
- 高置信 credential scan 仅命中一个明确的 test fixture，非测试候选为 0；Git 跟踪的 CSV/Parquet/ZIP 原始 CARE 数据为 0；无产品 TODO/FIXME/HACK/XXX、无新 skip/xfail/only 或断言弱化。测试端口和临时 DB 已清理。
- Sites hosting 约束已核对：本任务只授权仓库整改/验证，没有授权保存版本或部署到外部 Site，因此不执行外部发布；后续最终验证仍会检查 `dist/server/index.js` 与 hosting metadata 的生产构建边界。Adversarial Review 判定 `PASS`，未发现新的 Critical/High；Final Audit 计数保持 `0 / 2`，进入当前最终代码状态的全局验证。

#### Final Global Validation Completed / Final Audit Pass #1 Start (2026-09-04 22:14 +08:00)

- Frontend required 门禁全部从当前树重跑：artifact policy、TypeScript、ESLint、Prettier、production build、standard start smoke、bundle budget 与 167 个 Node 测试通过；覆盖率为 lines `90.34% >= 89%`、branches `51.56% >= 49%`、functions `33.37% >= 32%`，90 chunks / 2,617,225 bytes，最大 chunk 645,003 bytes。
- Backend current-tree global suite JUnit：`425 tests / 397 passed / 28 external-environment skipped / 0 failures / 0 errors`，930.854s；全局覆盖率 `75.09% >= 68%`。28 个 skip 精确属于专用 PostgreSQL/CARE 外部 jobs，不作为通过证据；本阶段另在 fresh PostgreSQL 对主 contract `23/23`、0 skip、0 failure、99.875s，并验证唯一 `0028` head 与 `alembic check: No new upgrade operations detected.`。
- 当前树后端 Ruff 212 files、strict mypy 100 source files、Bandit、`pip-audit`（零已知漏洞）、frozen uv/container lock、CARE dependency closure、官方 reference equivalence 与 Alembic offline SQL 全部通过。最终 Chromium `29/29`、0 skip；另以当前代码 fresh DB 再跑真实 Worker→FastAPI→PostgreSQL HTTPS 为 `1/1`、0 skip。
- production `dist/server/index.js`、`dist/.openai/hosting.json`、`dist/.openai/drizzle` 均存在；未执行未授权外部发布。所有验证 DB/端口已清理，报告保存于 ignored `.artifacts/final-global`，`git diff --check` 退出 0。Final Global Validation 判定 `PASS`；进入独立 Final Audit Pass #1，计数暂保持 `0 / 2`。

#### Final Audit Pass #1 Completed (2026-09-04 22:18 +08:00)

- 控制面/覆盖审计重新解析 technical index `16/16 DONE`、UI index `8/8 DONE`、Progress current register `24/24 DONE`，集合精确相等；Critical/High/Medium remaining 均为 0。`AGENTS.md`、`PRODUCT_REQUIREMENTS.md`、`UI_UX_SPEC.md`、`ARCHITECTURE.md` 的 SHA-256 与本轮读取基线完全一致，证明未改动禁止修改的三份需求/架构文档。
- 当前三份 Dashboard 基线与最终 JUnit/coverage/CARE closure/reference evidence 全部存在并重新哈希；对照原始 reference 与 1440 基线，验证 incident-first 首条、6 KPI、7/5 trend/queue 和 4/4/4 下层结构保持，主题/具体数据差异不影响信息层级，也没有像素复制或伪数据耦合。根报告/进度/retention runbook 的 Prettier check 通过。
- 首个状态 parser 因未容忍 UI Markdown 表格的对齐空格而报 topology mismatch；修正只读 regex 后得到精确 `16+8`。随后一次保护文档比较因人工抄写 SHA-256 少一位而失败；从实际文件和先前 CARE source-of-truth evidence 双向核对后纠正常量，文件本身未变化。两项均为审计 harness 输入错误，不是产品失败，也未弱化最终断言。
- Pass #1 未发现新的 Critical 或 High，`Final Audit Pass` 增至 `1 / 2`。进入独立 Pass #2；在其通过前 Final State 仍为 `OPEN`。

#### Final Audit Pass #2 — TECH-M005 Reopened (2026-09-04 22:21 +08:00)

- 以真实索引副本和隔离 `GIT_INDEX_FILE` 执行全候选 `git add -A` 时，发现本轮验证生成的 `tmp/c005-postgres` 便携数据库会进入候选索引；继续盘点确认 `tmp/` 下还有官方数据工作副本、clean clone、wheel 与临时索引等多组未忽略 scratch。模拟在写入真实索引前已中止；真实索引中 `tmp/c005-postgres` 跟踪数仍为 0。
- 该发现属于 TECH-M005 同一仓库制品治理根因，按规则重新标为 `IN_PROGRESS`，Final Audit 计数保持 `1 / 2`。修复目标是默认忽略新的 `tmp/` 内容，并在 index policy 中禁止强制加入 `tmp/`，仅为既有受控 CARE PDF/render fixture 保留精确路径例外；完成候选索引正/负验证后才能恢复 `DONE` 并重跑 Pass #2。
- `.gitignore` 现默认排除新的 `tmp/*`；index policy 禁止整个 `tmp/`，仅放行 5 个既有 CARE PDF/render 文件和迁移中的旧 verifier 精确路径，submodule gitlink继续单独受固定 commit/tree 供应链门禁治理。真实索引门禁为 519 blobs / 20,485,844 bytes `PASS`。
- 隔离候选重新执行全量 `git add -A` 后只有 6 个既有 `tmp` 路径（固定 gitlink + 5 个受控参考文件），574 blobs / 23,611,578 bytes，门禁 `PASS`；再以现有 blob 强制注入非例外 `tmp/pdfs/forced-artifact.txt`，门禁按预期退出 1 并精确报告 forbidden path。真实 `.git/index` 前后 SHA-256 均为 `52904237...6E39`，候选索引已清理。TECH-M005 在修复与正/负验证后恢复 `DONE`，进入 Pass #2 全轮复核。

#### Final Audit Pass #2 — PASS / Completion (2026-09-04 22:29 +08:00)

- 重新解析技术、UI 与 Progress 活动索引，得到 `16/16 + 8/8 = 24/24 DONE` 且集合精确相等；Critical/High/Medium remaining 均为 0。保护文档 hash 仍为 AGENTS `25B10F39...AE06D`、PRD `319BF135...FEC02`、UI spec `9DC4C01A...AACB`、Architecture `498A332F...F955`，三份禁止修改的需求/架构文件没有漂移。
- 当前代码定向回归：后端 release/deployment/container/CARE closure/reference/read-audit `47/47`、前端 query/navigation/responsive/type/UI-matrix/lifetime-boundary `21/21`，均 0 skip；Final Global Validation 的 backend `425 tests / 397 passed / 28 dedicated external skips / 0 failed`、fresh PostgreSQL `23/23`、真实跨层 `1/1`、Chromium `29/29` 证据继续有效。
- 供应链/安全：36 个 workflow action 全部固定 40 位 commit，0 个 `continue-on-error`；CARE reference 仍是 mode `160000`、commit `a338b6e...` 的 gitlink；除 `test_platform_configuration_security.py` 的 4 条刻意假密钥 fixture 外无候选，0 个 TODO/FIXME/HACK/XXX，`.codex_tmp` tracked 0。首轮 secret regex 把 `task-...` URI 误识别为 `sk-`，收紧前置词边界并保留显式测试 fixture 例外后通过；这属于只读 harness 假阳性，产品文件未改变。
- hosting build 三个生产边界存在；reference 与 1440/1280/390 基线均存在并重哈希；工作区与 cached diff whitespace 检查通过。Pass #2 未发现新的 Critical/High；TECH-M005 的 Medium 发现已在本轮完整修复并复验，连续收敛计数达到 `2 / 2`，Gate A–H 全部 `PASS`，Final State 更新为 `COMPLETED`。

---

## 历史活动运行：CARE v6 数据集接入与验证（截至 2026-08-29）

本节是当前执行状态的唯一 Source of Truth。下方“历史执行记录”保留 2026-08-21 已完成审计的证据，不得用其中的 `COMPLETED` 或 `2 / 2` 覆盖本次 CARE 任务状态。

### Metadata

- Project：`OpenVigil / wind-agent`
- Requirement：`docs/care-v6-integration-development-plan.md`
- Active Issues：`AUDIT_REPORT.md` 顶部 `CARE-*` 登记
- Execution Rules：`EXECUTION_GOAL.md` 顶部 CARE 覆盖层 + 通用 Runbook
- Permanent Rules：`AGENTS.md`
- Read-only Dataset：`C:\coding\reference\CARE_To_Compare`
- Started：`2026-08-26 18:09 +08:00`
- Last Updated：`2026-08-29 21:48 +08:00`

### Overall Status

- Current Phase：`COMPLETED`
- Current Issue：`NONE`
- Next Issue：`NONE`
- Final State：`COMPLETED`

### Statistics

| State | Count |
|---|---:|
| Total | 14 |
| TODO | 0 |
| IN_PROGRESS | 0 |
| DONE | 14 |
| BLOCKED | 0 |
| NOT_APPLICABLE | 0 |

### Severity Remaining

| Severity | Count |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

### Active Issue Register

| ID | Severity | Status | Dependencies | Evidence / Next action |
|---|---|---|---|---|
| CARE-C001 | Critical | DONE | — | 两次真实全量扫描均为 101 CSV/95 事件/5,242,948 行，manifest hash `ccf14bf...f974b`；A/B/C 81/252/952 全列闭合，定向与相关回归 45/45 |
| CARE-C002 | Critical | DONE | C001 | 1,285 映射语义合同、A/B/C 真实事件质量摘要与独立 mask 通过；相关回归 49/49，原值与匿名时间语义保持 |
| CARE-C003 | Critical | DONE | C001,C002 | `care-score-v6` 协议/预测与评估制品/无泄漏边界完成；官方实现等价向量通过，黄金 18/18、相关回归 67/67 |
| CARE-C004 | Critical | DONE | C001 | `BenchmarkReplayRun`/合成时间/sequence/source-event/checkpoint 契约完成；15/15 黄金与真实 ingest/query 集成通过，相关回归 87/87 |
| CARE-C005 | Critical | DONE | C003,C004 | anomaly 注册/部署/推理、预测 provenance、告警状态机和服务端 capability 门槛完成；专项 8/8、相关回归 101/101 |
| CARE-H001 | High | DONE | C001,C002 | PyArrow 独立 CLI、分批宽表 Parquet、任务韧性与 CARE MinIO/备份边界完成；9/9 专项、121/121 相关回归、真实 C44 probe 及全量静态检查通过 |
| CARE-H002 | High | DONE | C004,C005 | 10 类实体、受约束 API schema、RegisteredModel ID/version 复用、anomaly/告警来源与 `0024` 迁移完成；相关 123/123、真实 PostgreSQL 14/14、0 skip |
| CARE-H003 | High | DONE | H001,H002 | A0 anomaly + A24 normal 真实双事件导入完成；109,989 行、81 映射/54 Avg、不可变制品、真值隔离、韧性及真实 PostgreSQL 88 条幂等登记通过 |
| CARE-H004 | High | DONE | C003,H003 | z-score 与随机投影双路径、真实 A0/A24 冻结评估、8 个不可变制品、2 模型/2 run/4 result/20 metric 的真实 PostgreSQL 幂等登记通过 |
| CARE-H005 | High | DONE | C004,C005,H004 | 两次独立空库真实 PostgreSQL 垂直切片均 1/1；378 样本、7 prediction、异常 1 Alarm/Mission/Decision、正常 0 告警，重启/重试/新 run/truth 隔离通过 |
| CARE-M001 | Medium | DONE | H002,H003 | 受治理 dataset/event/curve API、生产网关和数据中心真实链路完成；SQLite 5/5、真实 PostgreSQL 1/1、后端 339/339、前端 139/139 |
| CARE-M002 | Medium | DONE | H004,H005 | 有界模型评估/事件结果/诊断 API 与生产 UI 已复用 RegisteredModel→evaluation→prediction→Alarm→Mission 权威链；后端 343/343、前端 143/143、真实 PostgreSQL 1/1、0 skip |
| CARE-M003 | Medium | DONE | H001,H002 | 受控 JSON/CSV、必填请求头幂等、外部分发 ShareAlike 复核/拒绝审计、完整制品许可证、独立 bucket/prefix/scope 与精确清理意图/结果审计完成；后端 351/351、前端 143/143、真实 PostgreSQL 1/1、0 skip |
| CARE-M004 | Medium | DONE | H003,H004,H005,M001,M002,M003 | v5 全量导入与真实 MinIO 场内评估经当前 verifier/不可变重放通过：A22→C58→B15、95 事件、36 资产、45/50、5,242,948 行、281,249 prediction 点；import wall 7,846.50 s/693.52 rows/s/HWM 521,977,856/9.27 GB，evaluation 125.83 s/HWM 235,524,096/387.4 MB，36 fold 全核算且 cross-farm disabled；真实 PostgreSQL、API、权限、回放、PG16+五 bucket 隔离 DR、最终全局验证、完整/对抗复查与两轮独立审计全部通过；服务已停止 |

### Stage Gates

| Gate | Status | Required evidence |
|---|---|---|
| 0A — 真实数据契约 | PASS | C001/C002 DONE；真实全列闭合、固定样例、质量/单位/状态/缩放/时间规则与 mask 均有证据 |
| 0B — 评分协议 | PASS | C003 DONE；权威来源固定、`care-score-v6` 黄金测试、完全复算与无泄漏负向证据通过 |
| 0C — 平台兼容 | PASS | C004/C005 DONE；replay/anomaly/告警来源/策略状态/服务器激活门槛合同均有可执行证据 |
| 1 — 双事件最小导入 | PASS | H001、H002、H003 DONE；真实双事件、韧性、物理 Parquet、许可证和 PostgreSQL 幂等登记均有证据 |
| 2 — 离线基准 | PASS | H004 DONE；双模型同协议、真实双事件、不可变结果、失败计入与数据库登记均有证据 |
| 3 — 平台垂直切片 | PASS | H005 DONE；双事件真实 ingest/prediction/alert/Mission/诊断链、重启恢复、幂等和正常抑制均有 PostgreSQL 证据 |
| 4 — 受治理界面与许可证 | PASS | M001、M002、M003 DONE；API/UI、真值与租户隔离、许可证传播、受控导出及清理审计均有自动/真实 PostgreSQL 证据 |
| 5 — 全量与发布验收 | PASS | M004 DONE；全量导入/场内泛化、真实 95 事件资源、PostgreSQL/API/回放、PG16 + 五 bucket 隔离 DR、最终全局门禁、完整/对抗复查与两轮收敛审计均通过 |

### Convergence

- Full Requirement Recheck：`PASS`
- Adversarial Review：`PASS`
- Final Global Validation：`PASS`（当前稳定源码的 build/static/security/full backend coverage/真实 PostgreSQL/CARE 链/E2E/smoke/image/deployment 均通过）
- Final Audit Pass：`2 / 2`
- Completion Gates：`MET`

### Completion Continuation Re-audit (2026-08-28 12:21 +08:00)

- 恢复运行时重新完整读取 `AGENTS.md`、`EXECUTION_GOAL.md`、`AUDIT_REPORT.md`、本文件活动区、CARE 开发计划和评审意见；实际仓库已经完成 14 个 CARE Issue，因此按控制文件要求审计当前实现与证据，没有重置、覆盖或清理用户的大量既有未提交修改。
- Pass #1（功能、数据与需求追踪）通过：CARE 合约/质量/评分/回放/anomaly/pipeline/import/evaluation/online/metadata/catalog/governance/full-scale 专项套件退出 0；当前全量导入 verifier 在 `14.244 s` 内重新核验 95 个事件、`5,242,948` 行和全部引用制品，评估 verifier 在 `8.005 s` 内重新核验 36 个 fold、`281,249` 个 prediction 点；前端 CARE 数据中心/模型管理/诊断中心专项 `7/7` 通过。
- 对只读 `C:\coding\reference\CARE_To_Compare` 和 ZIP 再做一次真实全量扫描，新清单 `manifest-current-20260828.json` 为 101 CSV、95 事件、`5,242,948` 行，ZIP MD5 `2547b58c...f500c`、SHA-256 `ca61379e...d4194f1` 与既有合同完全一致。字段级 diff 证明全部数据、schema、行数和映射未漂移；清单身份从 `ccf14bf...f974b` 变为 `7d609d1...7fe6a` 的唯一语义原因是已审计的 PyArrow 安全升级使 generator `dependency_lock_sha256` 从 `279090...c2c3` 变为当前 `d6f55f...393de`。全量 Parquet manifest 自身记录实际 PyArrow `23.0.1`，没有伪报旧运行依赖。
- Pass #2（全局、对抗、安全与供应链）通过：生产前端 build、bundle budget（92 chunks / `2,598,335` bytes）和 Node `143/143`；后端当前 JUnit `393 tests / 369 passed / 24 controlled external skips / 0 failure / 0 error`，SHA-256 `AE0E3A89...96DAF`；覆盖率 `13,535 / 17,852 = 75.8178355366%`，预算通过，JSON SHA-256 `08769BFA...DF06`。
- 当前静态与供应链复核通过：TypeScript、ESLint、Prettier、Ruff lint/format（194 files）、strict mypy（92 source）、Bandit 0 finding、`uv lock --check`、container requirements lock、pip-audit、pnpm production audit、Compose config、唯一 Alembic head/声明 `0026_schema_contract_alignment`、完整 offline migration render、标准 `pnpm start` smoke 和 `git diff --check` 均退出 0。首次 `pip-audit --disable-pip` 探查因新版 CLI 要求同时传 `-r` 而在读取依赖前退出 1；随后按 CI 权威命令 `python -m pip_audit --skip-editable` 重跑并得到 `No known vulnerabilities found`，分类为验证命令错误而非产品失败。
- 今日 Docker Engine 客户端未响应，未擅自重启系统级 Docker 或触碰其他项目容器；当前全局套件按设计保留 24 个外部环境 skip。真实 PostgreSQL 证据仍对应当前稳定源码：最后源码修改 `2026-08-27 12:40:03`，其后 PostgreSQL 合同 `20/20`（JUnit SHA-256 `E29DE270...E961`）、CARE offline/full-scale/replay 各 `1/1`、全后端 JUnit `393 total / 369 passed / 24 controlled skips` 和对抗 CARE `177/177` 依次通过；今天源码未再变化，且当前无项目 runtime 进程或目标端口监听。
- 当前不可变全量 manifest 文件 SHA-256 保持：import `FFBD2451...ED5F`、evaluation `8BA1F187...7E34`。需求第 16 节 17 项门禁、第 17 节双事件垂直切片、第 18 节 15 项总体验收和 14 个 CARE Issue 经两轮独立复核仍全部为 `PASS`；`Final Audit Pass` 保持 `2 / 2`，`Completion Gates` 保持 `MET`。

### README 与当前状态复核（2026-08-29 21:48 +08:00）

- 重新读取 `AGENTS.md`、`AUDIT_REPORT.md`、当前活动进度区、根 README、CARE 计划/运行手册，并逐项对照当前源码、迁移、API、UI、测试与不可变制品；14 个 CARE Issue 的 Required Changes/Acceptance Criteria 仍有实际实现和有效测试支撑，未发现需重开的 Critical/High 或新的遗留问题。
- 修正根 README 的事实漂移：补入 CARE v6 真实规模、宽表 Parquet/选择性在线回放边界、场内留一资产协议、真值/权限/导出治理、受治理 API、可选依赖/CLI、目录结构、测试口径、CC BY-SA 4.0 与 DOI；同时明确本地候选证据不等于 registry 签名、SBOM、集群准入或生产上线。
- 首轮全量后端验证真实暴露 `test_root_readme_declares_current_migration_head_without_stale_baselines` 把旧 README 的 `201 项，189 passed` 等文案硬编码为成功条件。没有恢复旧文案或弱化门禁；测试已改为拒绝六类已知过期基线，并要求自动发现计数、外部 skip 不算发布通过、受保护门禁遇 skip 失败。定向测试与 Ruff 通过，修正后的第二轮全量为 JUnit `393 tests / 369 passed / 24 controlled external skips / 0 failure / 0 error`，覆盖率 `13,535 / 17,852 = 75.8178355366%`。
- 当前前端 `pnpm test:coverage`、生产 build/bundle、Node `143/143`、Chromium `6 passed + 1 controlled real-cross-layer skip`、标准启动 smoke、TypeScript/ESLint/Prettier、Ruff/mypy/Bandit、container lock、pip-audit、pnpm production audit、Compose config、唯一 head `0026_schema_contract_alignment`、完整 offline migration render 和 diff check 均退出 0。CARE 专项 `105/105`；当前 verifier 只读复核 95 events / 5,242,948 rows（11.357 s）与 36 folds / 281,249 prediction points（8.163 s），manifest 文件 SHA-256 仍为 `FFBD2451...ED5F` / `8BA1F187...7E34`。
- Docker context 可读取但 Engine 请求仍无响应，已终止只读探测，未重启系统服务或触碰任何容器；本轮没有把 PostgreSQL/MinIO/镜像/DR 外部门禁写成当日重跑通过。应用源码最近修改仍为 `2026-08-27 12:40:03`，当前项目目标端口均未监听；2026-08-27 的隔离依赖证据保持历史证据而非本轮替代执行。
- 根 README 本地链接、Prettier 和 whitespace 检查通过。当前没有仍需处理的问题，因此不重写 `AUDIT_REPORT.md` 的活动问题登记，CARE Overall Status / Final Audit Pass / Completion Gates 保持 `COMPLETED / 2 of 2 / MET`。

### Initialization Evidence

- 已完整读取四份控制文件和 CARE 需求文档。
- `AGENTS.md` 保持长期通用规则，不写入一次性 CARE 任务。
- `AUDIT_REPORT.md` 已建立 14 个 CARE 活动 Issue、依赖、Required Changes 和 Acceptance Criteria。
- `EXECUTION_GOAL.md` 已增加可直接启动的 CARE 提示词、强制顺序、专项禁止项和完成门槛。
- 本文件已初始化为 14 TODO；没有把提示词细化工作误记为功能实现完成。
- 尚未修改 CARE 功能代码、数据库 schema、迁移、依赖或原始数据。

### Progress Update Contract

执行 Agent 每次更新必须同步修改：

1. `Last Updated`；
2. Current Phase / Current Issue / Next Issue；
3. Statistics 和 Severity Remaining；
4. Active Issue Register 中的状态与证据；
5. 对应 Stage Gate；
6. 实际修改文件、测试命令、结果、失败分类和剩余工作；
7. 如进入最终阶段，更新 Recheck、Adversarial Review、Global Validation 和 Final Audit Pass。

状态只能按 `TODO -> IN_PROGRESS -> DONE/BLOCKED/NOT_APPLICABLE` 真实流转。不得在实现和验证前先标记 DONE。

### CARE Execution Log

#### CARE-C001 — Investigation (2026-08-26 18:13 +08:00)

- 完整读取 `AGENTS.md`、`EXECUTION_GOAL.md`、CARE 开发计划、方案评审、`AUDIT_REPORT.md` 和本文件顶部活动区；当前 14 个 CARE Issue 均未实现，依赖顺序从 C001 开始。
- `git status --short` 显示仓库存在大量既有未提交工作；后续只做 CARE 所需最小新增/关联修改，不覆盖或清理用户工作。
- 只读检查 `C:\coding\reference\CARE_To_Compare`：三个风场目录存在，事件数据文件 22/15/58，另有每场 `event_info.csv` 和 `feature_description.csv`，共 101 CSV；未对仓库外数据执行写操作。
- 真实事件样例表头固定以 `time_stamp;asset_id;id;train_test;status_type_id` 开始，A/B/C 总列数为 86/257/957；`event_id` 只来自文件名和元数据。A 场元数据使用 `asset`，B/C 使用 `asset_id`，真实字段为 `statistics_type`。
- A 场真实表头确认 `sensor_44` 至 `sensor_51` 为八个无统计后缀的 average 列；仓库当前没有 CARE/benchmark 实现文件，需要新增纯标准库数据合同后再验证全量清单。

#### CARE-C001 — DONE (2026-08-26 18:23 +08:00)

- 实现：新增 `windops_backend.benchmarks.care.contract` 与 `windops-care-contract` CLI。使用纯标准库对 ZIP 和事件 CSV 流式读取；单遍计算文件 SHA-256、行数、schema hash、split 计数、资产和 source row ID 范围，不把 C 场宽表整体装入内存。
- 合同：固定 CARE v6 ZIP 大小、MD5/SHA-256、101 CSV、事件 ID `0..94` 和 A/B/C 信号数；从文件名取得 event ID 并与 `event_info.csv` 双向校验，兼容 A `asset` 与 B/C `asset_id`，校验事件区间和真实文件资产。
- 映射：读取真实 `statistics_type` 并去重稳定排序；由 feature metadata + statistic suffix 生成映射，显式版本化 A 场 `sensor_44..51` 八个 bare average 别名；未知、缺失、重复、歧义列以及 schema 漂移全部失败关闭。
- 安全：原始目录只读，公开写入入口拒绝把 manifest 写到数据源目录或覆盖 ZIP；输出仅位于项目 `.artifacts/care-v6/contract/`。两次扫描得到完全相同的源文件哈希、JSON 字节和 manifest hash，未修改 `C:\coding\reference\CARE_To_Compare` 或 ZIP。
- 真实结果：ZIP MD5 `2547b58c21ac8c242d13232860cf500c`、SHA-256 `ca61379e...4194f1`；101 CSV、95 事件、36 资产、45 anomaly/50 normal、总/train/prediction `5,242,948 / 4,961,699 / 281,249`；A/B/C 映射 `81/252/952`，事件区间全部位于文件 ID 范围。
- 稳定性：两次真实扫描的 `manifest_sha256` 均为 `ccf14bf390f5a25a2143bf0d2de0b9c72c9b624e289692b5fae4468b838f974b`，格式化 JSON 文件 SHA-256 均为 `3DB92651DAC8489F482EAFB927C52BC22F6BC58F476875C6C7AC7A4DB46EE916`；主制品 `manifest.json` 为 582,503 bytes。
- 测试：A/B/C 固定样例、统计集合、八个别名、稳定 hash、unknown/missing/duplicate/ambiguous、event 双向匹配、事件区间、ZIP 身份和只读边界共 `9/9`；C001 + release pipeline + configuration 相关回归 `45/45`。Ruff format/check（122 files）、strict mypy（75 source）和相关 `git diff --check` 通过。
- 文件：`backend/src/windops_backend/benchmarks/__init__.py`、`benchmarks/care/{__init__.py,contract.py}`、`backend/tests/test_care_contract.py`、`backend/pyproject.toml`；证据：`.artifacts/care-v6/contract/{manifest.json,manifest-repeat.json}`。
- 剩余风险归属 C002：单位损坏修复、零段/状态质量规则、缩放和匿名时间语义尚未实现，因此阶段 0A 保持 `IN_PROGRESS`，未开始任何全量导入、模型上线或平台回放。

#### CARE-C002 — Investigation (2026-08-26 18:25 +08:00)

- 重新核对 Audit C002、需求 5.4–5.9、13.2 和阶段 0 门槛；C002 必须保留原值并输出独立、可追溯 mask，不能全局把 `0` 改成 null，也不能把 `status_type_id` 直接当平台质量。
- 从真实 C001 manifest 读取 1,285 个映射：A/B/C base feature 与默认 Avg 数分别为 `54/63/238`；其余 Min/Max/Std 必须默认禁用。真实单位包含 A/B `�C`、`�`，C `Celsius`、`deg`，A 另有空单位。
- 真实元数据确认 angle 映射数 A/B/C 为 `7/12/48`，B 有 16 个 counter statistic 映射；质量合同需包含 circular angle、counter regression/reset、Min≤Avg≤Max 和 Std≥0 检查。
- 功率缩放不能只按列名前缀判断：真实 metadata 同时存在 `power_*`、`reactive_power_*` 与 description 中的 active/reactive power。实现将结合 description、物理单位和 counter 标志，排除 Wh/kWh/VArh/kvarh 能量计数器及 `24VDC power pack` 等非功率描述误命中。
- C002 只建设并验证阶段 0A 的可执行质量/语义合同和小型固定样例；不会开始 Parquet 全量导入、模型上线或平台回放。

#### CARE-C002 — DONE / Stage 0A PASS (2026-08-26 18:34 +08:00)

- 实现：新增 `windops_backend.benchmarks.care.quality` 与 `windops-care-quality` CLI；从 C001 manifest 生成不可变 quality contract，并对指定事件逐行、单事件有界内存审计。质量结果不改写任何原值，疑似缺失仅写入独立 range mask。
- 质量摘要：每特征输出 zero count/ratio、最长连续零段、zero 与 status/缩放功率关联、null/NaN/±Infinity/解析失败、常量、finite min/max、Std 负值、Min≤Avg≤Max 违反和 counter regression/reset 计数。B/C 长零段 mask 含 rule ID/version、原因、置信度、source row 范围和 `raw_value_preserved=true`；A 场零段只汇总，不机械套用 B/C 缺失规则。
- 状态：版本化 `care-v6-status-rules-v1` 要求显式 trusted allowlist；A train 可按 allowlist 过滤，A prediction 固定使用 v6 例外保留；B/C 短暂不一致或未获信号佐证时保留，只有持续且佐证的不一致可进入 mask。`status_type_id` 明确不等于平台 quality。
- 单位/物理：修复 `�C→°C`、`�→°`、`Celsius→°C`、`deg→°`；空单位默认 `unknown`，仅明确无量纲时为 `1`。angle 标记 circular；counter 检测 reset/wrap 不改写。结合 description、物理单位和 counter 标志识别匿名额定功率缩放，禁止绝对功率解释，并排除能量计数器/电源包误命中。
- 特征/时间：quality contract 覆盖全部 1,285 映射，A/B/C 仅 `54/63/238` Avg 默认启用（合计 355），930 个 Min/Max/Std 默认禁用；保存 feature set/quality/status/unit/time 版本与 hash。时间规则保留 source timestamp、anonymous time 和 source row ID，标记 `independently-shifted-anonymized`，禁止跨事件排序或真实场站时间声明。
- 真实语义制品：`quality-contract.json` 为 922,235 bytes，contract SHA-256 `bd46caf32043f94185816913a67e702e2888361ca530c73cc850962724d92a40`，格式化制品 SHA-256 `315E228801BB083245634FE8DCBA0BFC2025AEF96E70638208BFEE2C9796937F`；重复生成字节一致。单位规则覆盖数：empty unknown 1、Celsius 308、deg 48、preserve 784、mojibake Celsius 125、mojibake degree 19；scaled-power mapping 92。
- 真实事件证据：A event 0 为 `54,986 rows / 81 features / 0 B/C mask`，report hash `442c208b...8baa1`；B event 2 为 `54,774 / 252 / 14,664 masks`，hash `2ca67918...180d1`；C event 1 为 `53,569 / 952 / 128,959 masks`，hash `7a6c1018...b5db4`。三份报告独立重算 hash 通过，source file SHA 与 C001 manifest 一致，source row ID 0 duplicate/0 non-monotonic；A 真实报告重复生成字节一致。
- 负向/边界：固定样例覆盖合法零值保留、长零 mask、status/power 关联、null/NaN/Infinity/坏数、constant、counter reset、Std<0、Min/Avg/Max 违反、angle circular、A prediction 例外、B/C 短通信差异、缺 allowlist 失败和 quality contract 篡改失败关闭。
- 验证：C001+C002 测试 `13/13`；加 release pipeline/configuration 相关回归 `49/49`。Ruff format/check（124 files）、strict mypy（76 source）及相关 `git diff --check` 通过；既有 `.pytest_cache` ACL 仅产生 warning，测试结果完整。
- 文件：`backend/src/windops_backend/benchmarks/care/quality.py`、`backend/tests/test_care_quality.py`、`contract.py` hash verifier、`care/__init__.py`、`backend/pyproject.toml`；证据位于 `.artifacts/care-v6/quality/`。
- 阶段门禁：0A 的不可变清单、全列映射、statistics/event 来源、零值/状态/单位/缩放/匿名时间、原值与 mask、Avg 默认集及许可证来源字段全部关闭。0B/0C 尚未通过，因此仍禁止全量导入、模型上线和平台回放。

#### CARE-C003 — Investigation (2026-08-26 18:42 +08:00)

- 阶段切换及上下文压缩后重新完整读取四份控制文件；SHA-256 为 AGENTS `25B10F39...AE06D`、Audit `53C7331B...5DA0F`、Goal `7310FF75...FBB2`、Progress `9A73EBD8...ABE3`，状态恢复为 0B、C001/C002 DONE、C003 TODO、Final Audit 0/2。
- 按 PDF 技能完整读取并渲染官方论文评分章节。论文固定点级/事件级 F0.5、criticality 72、权重 Coverage/Earliness/Reliability/Accuracy=`1/1/1/2`、无检测为 0、正常 Accuracy 低分支和无中间舍入；但论文文字/伪代码在 `72` 比较、正常状态布尔方向和 Earliness 下降起点上存在可见歧义，不能据此猜测。
- 固定 Fraunhofer IEE 官方 `AEFDI/EnergyFaultDetector` 发布 `v0.6.2`、commit `a338b6efb3a650536930c6e67247694071d2f63e` 作为权威参考实现。其 CARE 实现明确使用 `max_criticality >= 72`、仅在正常有效点 `+1/-1`（异常状态冻结）、Coverage/Reliability beta 0.5、Earliness 下降起点 `1/4`、Accuracy `<= 0.5` 特殊分支及浮点全精度聚合。
- C003 将冻结上述权威实现语义并显式记录与论文表述差异；同时增加 A prediction v6 状态例外、B/C 状态过滤、预测真值能力隔离、不可覆盖最终运行、单事件/场内协议与跨场失败关闭。当前仍未执行全量导入、模型上线或平台回放。

#### CARE-C003 — DONE / Stage 0B PASS (2026-08-26 19:04 +08:00)

- 权威依据：官方论文 PDF SHA-256 `6F90430A...24D3`；固定 Fraunhofer IEE `AEFDI/EnergyFaultDetector` release `v0.6.2`、commit `a338b6efb3a650536930c6e67247694071d2f63e`，评分/criticality 源文件 SHA-256 分别为 `122EAF43...5078`、`2D593EF0...558E`。协议明确以固定可执行参考实现消解论文排版/文字歧义。
- 评分协议：新增纯标准库 `care-score-v6`。点级 Coverage 与事件级 Reliability 均为 F0.5；正常事件使用 Accuracy；组件权重 Coverage/Accuracy/Reliability/Earliness=`1/2/1/1`；binary 比较严格为 `score > threshold`，criticality 事件比较为 `max >= 72`，无效状态点冻结，范围 `0..1000`；Earliness 精确复现参考实现 `1/4` 下降起点及采样顺序；全程不做中间/身份舍入。
- 特殊分支：无事件检测先返回 0；平均正常 Accuracy `<= 0.5` 返回 Accuracy；其余才按权重聚合。协议显式登记论文 `< 0.5`、超过 72、状态布尔方向和半程 Earliness 与权威实现的四处差异，禁止隐式选择。
- 制品：truth-free 事件 prediction artifact 同时保存 anomaly score、严格阈值策略/版本/hash、binary prediction、有效点/status 决策、source/anonymous time、criticality、模型/部署/feature/quality 身份；final evaluation artifact 保存受控真值、Earliness 权重/贡献、混淆矩阵、组成项、特殊分支、失败/不可评分事件和总分，并可从自身输入字节级完全复算。
- 无泄漏：`CalibrationInput` 不含标签；threshold provenance 拒绝 prediction；feature selection、early stopping、hyperparameter selection 各自只允许 train/train-validation/not-used 并进入 hash。prediction artifact 明确不含 event label/ground truth；真值 vault 没有公开 read API，只有 `FinalCareEvaluator` 获得 capability。development/tuning/final-holdout 身份分离，final-holdout 使用排他创建且不能原地覆盖。
- 协议：单事件 `care-event-train-prediction-v6` 与场内 `within-farm-leave-one-turbine-out-v1` 分开校验；场内协议强制单场和 held-out asset；`cross-farm-ontology-v1` 在 ontology 完成前失败关闭。
- 指标：保存 CARE 四分项、正常事件误报率、每 1000 有效正常小时、每正常 prediction event-day、事件检测率、提前量分位数、point Precision/Recall/F0.5/AP，以及 unscorable/data/model failure 计数；每风机年指标固定禁用并标记缺少去重暴露证明。
- 黄金/负向：all-normal、all-anomaly、无告警、criticality 71/72/73、正常持续误报、A v6 状态例外、B/C 状态过滤/冻结、Earliness 前/后/终点、Accuracy 0.4/0.5、无有效点、threshold 相等、truth 隔离、协议隔离、不可覆盖 final、hash/语义篡改和失败事件不丢弃共 `18/18`。
- 独立权威等价性：在临时 Python 3.12 + NumPy/Pandas/scikit-learn 环境直接加载固定官方源码，得到 criticality 71/72/73=`false/true/true`、状态冻结 `[1,1,1,2]`、四点 Earliness `[0.3488372093023256,0.21705426356589147,0.09302325581395347]`，与本地黄金输出完全一致；临时依赖未写入项目或全局环境。
- 验证：C001+C002+C003 为 `31/31`；加 release pipeline/configuration 相关回归为 `67/67`。Ruff format/check（126 files）、strict mypy（77 source）与相关 `git diff --check` 通过；`.pytest_cache` ACL warning 不影响测试结果。
- 文件：`backend/src/windops_backend/benchmarks/care/scoring.py`、`care/__init__.py`、`backend/tests/test_care_scoring.py`、`backend/pyproject.toml`；协议制品 `.artifacts/care-v6/scoring/care-score-v6-protocol{,-repeat}.json` 两次字节一致，protocol SHA-256 `697fa61399d2a4490ca6b91fdd6ca99186e27a2987f5591c4713aeb2bd30b926`，文件 SHA-256 `1A2164B6...FE7C5`，6,155 bytes。
- 阶段门禁：0B 已通过。0C 尚未通过，仍禁止全量导入、模型上线和平台回放；下一项按依赖顺序进入 C004。

#### CARE-C004 — Investigation (2026-08-26 19:08 +08:00)

- 上下文压缩后重新全文读取四份控制文件；SHA-256 为 AGENTS `25B10F39...AE06D`、Audit `53C7331B...5DA0F`、Goal `7310FF75...FBB2`、Progress `CAA5AB57...E6CB`。顶部活动状态恢复为 STAGE_0C、C001/C002/C003 DONE、C004 TODO、Final Audit 0/2、Final State OPEN；后部历史轮次的 COMPLETED/2 of 2 不覆盖本轮状态。
- 现有平台硬边界已确认：`Turbine.id` 最长 32、`IngestReceipt.source_event_id` 最长 128；SCADA 水位主键为 `source_id + stream_key`，其中 stream key 是 `turbine_id:variable`。因此必须用 run+event 唯一在线虚拟风机隔离，不能让多个事件或新 run 复用同一在线 ID。
- 现有 ingest 已提供 payload hash 幂等 receipt、同流 durable watermark/highest sequence、迟到/过期隔离和最多 1000 样本批次；history 按 turbine/time/variable 查询并支持 LIVE/24H/30D/custom。C004 将冻结 CARE source、短变量映射、原 row sequence、查询可达的合成时间及 checkpoint 规则，并用真实 ingest/query 集成测试证明重试、乱序、迟到、重启与 run 隔离。
- C004 只实现阶段 0C replay 合同和兼容性证明；正式数据库 benchmark 实体/迁移归属 H002，实际双事件平台回放归属 H005。当前仍未执行全量导入、模型上线或平台回放。

#### CARE-C004 — DONE (2026-08-26 19:21 +08:00)

- 正式合同：新增冻结的 `BenchmarkReplayRun`，记录 CARE v6 dataset/farm/event、逻辑资产、run+event 在线实例、mode/speed/status、不可变 anchor、三项规则版本、Avg 变量映射/窗口、模型/deployment/threshold 引用、操作人/时间/错误及逐变量 checkpoint。状态机、终态证据、连续确认 checkpoint 和恢复均失败关闭；正式持久化实体/迁移仍按依赖归属 H002。
- 身份隔离：逻辑资产固定为 `CARE-<farm>-<source_asset>`；在线实例将完整 8 字符 run ID、farm/asset token/event 编入不超过 32 字符的 ID。run registry 拒绝 run/online ID 复用；相同逻辑资产的重叠事件及新 run 均得到不同在线时序，适配现有 `source_id + turbine_id + variable` 水位而不修改全局 stream key。
- 时间/sequence：冻结 `care-v6-fixed-10m-window-relative-v1`，anchor 表示窗口首个原 row 的合成时间，后续为 `(row-window_start)*10m`；窗口保留原 row ID、不重编号，`source_sequence=source_row_id`。保存 source timestamp、anonymous observed time、原间隔、规则版本和明确的 `synthetic-replay-time-not-field-time` 声明；查询规划覆盖 LIVE/24H/30D/custom，并拒绝未来时间或超过平台 365 天 custom 上限的窗口。
- 幂等/来源：`care6:<run8>:<farm>:<event>:<row>:<variable-short-id>` 包含版本、run、event、row 和可由 run 变量表还原的 identity，远低于 128 字符。批次上限 1000；同 run 相同步骤生成相同 payload/source event，同 key 异 payload沿用平台 409 冲突，新 run 进入独立 receipt 和水位命名空间。确认 payload 的 sequence/variable/source-event 任一不一致均不能推进 checkpoint。
- 数据语义：只允许选择元数据确认的 Avg；raw value 保持，`status_type_id` 仅进入 attributes 且明确不等于 platform quality，quality rule/mask 可追溯。replay/model window 校验强制 dataset/farm/event/run/online instance 单一并交叉校验 source-event/row/variable，跨事件或跨 run 拼窗失败关闭。
- 真实平台验收：通过现有 `/api/v1/scada/ingest` 和 `/api/v1/scada/history` 的 SQLite 集成测试验证持久水位、乱序 late、超过 lateness 隔离、重复请求 duplicate、关闭/重开 session 后状态仍在、24H 可查询及新 run 独立；同 run 重试未新增样本、Alarm 或 Mission。另有 LIVE/30D/custom、断点序列化恢复、缺口拒绝、生命周期和身份篡改黄金测试，共 C004 `15/15`。
- 制品/验证：新增 `replay.py`、`test_care_replay.py`、CLI `windops-care-replay-contract` 并导出公共合同。`.artifacts/care-v6/replay/replay-contract{,-repeat}.json` 字节一致；contract SHA-256 `ceadcf8fb8ead7c7aae54f7fdfa94b8bbea90ba2551aa44536ab9917a14fca5b`，文件 SHA-256 `58AC9E3FDFFFD43705FCBEC92B91F62FC2F0FBFD2AF97CDF294BDB0EF57A72AB`，3,373 bytes。CARE 合同测试 `46/46`；加配置、发布及既有 ingest ordering 回归 `87/87`；Ruff format/check 128 files、C004 strict mypy 和 diff check 通过。
- 失败分类：全 backend strict mypy 的 78 source 运行仅在既有、C004 未修改的 `config.py:551` 报 `_env_file` 与 pydantic mypy plugin 的 call-arg 不一致；归类为本轮前已存在的非 C004 类型边界，未伪装成通过，将在最终全局验证前调查收敛。pytest 仅有既有 `.pytest_cache` Windows ACL warning，不影响结果。
- 阶段门禁：C004 已关闭；0C 仍需 C005，故继续禁止全量导入、模型上线和平台回放。

#### CARE-C005 — Investigation (2026-08-26 19:25 +08:00)

- 现有 `RegisteredModel.kind`/API literal 已容纳 `anomaly` 字符串，但 schema validator 只约束 predictive；因此 anomaly 可注册任意输入/输出 JSON，属于未实现合同。`create_deployment` 又只允许 predictive，且现有 inference 强制 RUL/30 天概率，不能满足 CARE。
- `ModelPrediction` 是可复用的通用不可变推理 ledger，可先保存受治理 anomaly input/output；但现有 active routing 未按 model kind 隔离，若直接允许 anomaly 会与 predictive 抢占同一 100% 流量池。C005 必须按 kind 隔离部署、激活和路由，同时保持 predictive 原行为。
- 现有 `Alarm.source_event_id` 非空且唯一外键到 ingest receipt；不能让模型告警直接关联 prediction。数据库 `model_prediction_id`、至少一个来源约束和 benchmark 实体/migration 明确归属依赖后的 H002；C005 先冻结可执行来源合同并禁止 fake receipt，H002 再落 ORM/migration，H005 才执行真实告警/Mission 闭环。
- 现有 `ModelDeployment.evaluation_gate` 只是任意 JSON，`activate_deployment` 不校验内容。C005 将要求 anomaly 激活只能携带由服务端完整复算不可变 C003 evaluation artifact、结构化 metric snapshot、版本矩阵、失败事件、审批和审计后签发的进程内 capability；API/前端任意 JSON 不能构造该 capability。H002 后续把同一证据关联到正式 BenchmarkEvaluationRun/MetricSnapshot。
- 连续 N、恢复、冷却、去重、缺失/质量不确定/乱序处理将实现为版本化、可序列化且幂等的状态机；本阶段冻结持久化文档合同，H002 将其写入数据库状态实体。当前仍不执行模型上线或平台回放。

#### CARE-C005 — DONE / Stage 0C PASS (2026-08-26 19:42 +08:00)

- anomaly 合同：新增 `care-v6-anomaly-runtime-v1`，对现有 `ModelRegisterRequest` 按 kind 条件校验。anomaly 输入强制 dataset/event/replay run 单一窗口、起止时间/sequence、signals、feature/quality 版本；输出强制 score、binary、component、model/deployment 版本、完整 threshold policy、feature window、feature set、证据和 replay run，明确禁止 RUL、30 天概率及真值占位。predictive 原 RUL/概率合同和回归保持不变。
- 部署/推理：复用 `RegisteredModel`、`ModelDeployment`、`ModelPrediction`，未创建第二套注册表。deployment staging 支持 anomaly；active peers 和 routing 按 model kind 隔离，predictive 与 anomaly 不争用同一 100% 流量池。`run_anomaly_inference` 校验同一 C004 replay window、输入 schema、外部原始 score/binary/component、严格 `score > threshold`、服务器写入 provenance 和输出 schema，并以 deployment+turbine+window end/input digest 幂等；同 key 异窗口冲突，不伪造 RUL。
- 预测溯源：受治理 output 保存 model/version、deployment/version（首版以不可变 deployment ID 作版本身份）、threshold 全文/version/hash/value、feature 时间与 sequence、feature/quality 版本、evidence URI+SHA、dataset/farm/event/replay run/online asset、合成时间声明及 truth absent，并有内容 hash/语义复核。外部模型若尝试写 model/deployment provenance、预测真值或 predictive 字段会失败关闭。
- 告警来源：`AlarmSourceReference` 冻结“source_event_id/model_prediction_id 至少一个、模型预测可为主来源、永不要求 synthetic receipt”的合同；现有 SCADA receipt 告警保持兼容。实际 nullable FK/check constraint 和既有数据迁移按 Audit 明确归属 H002，真实 prediction→Alarm→Mission 闭环归属 H005。
- 策略状态：版本化 `AnomalyAlertPolicy/State` 覆盖 trigger threshold、连续 N、recovery threshold/N、cooldown、稳定 dedup key、enable、缺失窗口 reset/hold、质量不确定 reset/hold 和乱序 reject；输入额外校验 model/version/deployment/version/component/asset scope。状态/策略文档带内容 hash，可序列化恢复；重复 prediction 不增 revision，恢复、冷却、正常低分抑制和新告警均确定。
- 服务器门槛：`evaluate_activation_gate` 完整复算 C003 不可变 evaluation artifact，重建并比对结构化 metric snapshot，核对 completed/not-invalidated、model/package/deployment、`care-score-v6`、CARE score、异常检测/正常误报、farm/protocol 覆盖、feature/quality/threshold 版本矩阵、requested=scored、零失败/不可评分、审批及审计。只有该函数可签发进程内 capability；现有 API 的任意 `evaluation_gate` JSON、前端状态或手填指标不能构造，anomaly 激活无 capability 时失败关闭。
- 验收：专项 `8/8` 覆盖 schema/RUL 负向、跨 run 窗口、provenance/threshold 篡改、trigger/recover/cooldown/dedup/missing/uncertain/out-of-order、来源约束、不可变 gate/版本错配/伪 capability，以及真实 API 注册/暂存→拒绝 JSON 绕过→服务器授权激活→ModelPrediction 推理/重试/冲突；确认 1 prediction、0 fake receipt、0 Alarm。既有 predictive runtime `6/6` 通过；CARE 总计 `54/54`，加 model/ingest/config/release 相关回归 `101/101`。
- 制品/静态验证：新增 `anomaly.py`、`test_care_anomaly.py`、CLI `windops-care-anomaly-contract`，关联修改 `schemas.py`、`services/models.py`、CARE exports/pyproject。两份 `.artifacts/care-v6/anomaly/anomaly-runtime-contract{,-repeat}.json` 字节一致；contract SHA-256 `fcfa73dd589ba3953725b49b165f23d5fb3a4989e5fa6864b8ffc48519544279`，文件 SHA-256 `B293162CF87560821CC7A9038467063B7E9EABCC8CA7AF54F845F0A4F3CCA79B`，3,345 bytes。Ruff format/check 130 files、相关 strict mypy 8 source 和 diff check 通过；全 backend mypy 的既有 `config.py:551` call-arg 仍保留到最终全局收敛前调查。
- 阶段切换：结束前再次全文读取四份控制文件，hash 为 AGENTS `25B10F39...AE06D`、Audit `53C7331B...5DA0F`、Goal `7310FF75...FBB2`、Progress `38BEA2D8...ED0F`，准确状态为 C004 DONE/C005 IN_PROGRESS/Final Audit 0/2/OPEN。C005 验证完成后 0C 全部门槛通过，进入 H001；仍未执行全量导入、模型真实上线或平台回放。

#### CARE-H001 — Investigation (2026-08-26 19:44 +08:00)

- 现有在线依赖不含 PyArrow/Polars/Pandas/scikit-learn；现有 Dramatiq worker 专注 outbox，ArtifactVerifier 面向 API 预签名/读取，没有 benchmark 分块任务、checkpoint 或 immutable publish。H001 必须新增独立模块并保持 FastAPI 默认 import 不加载大数据包。
- 列式 ADR 选择 PyArrow：原生 `open_csv` 分批读取分号宽表、ParquetWriter 固定 row group/ZSTD、按列读取和 native allocation 统计可同时满足 C 场有界内存与列裁剪；不再叠加 Pandas/Polars/DuckDB。scikit-learn 仅作为后续 H004 baseline 的 benchmark 可选依赖，同样不进入在线最小环境。
- 已在 `benchmark` optional extra 增加 PyArrow `>=21,<22` 和 scikit-learn `>=1.7,<2`，`uv.lock` 实际锁定 PyArrow `21.0.0`、scikit-learn `1.9.0` 及其传递依赖；普通 API 依赖列表未增加这些包。
- 设计采用 batch→内容校验 chunk→checkpoint→最终单一宽表 Parquet 的两阶段写入；取消保留已确认 chunk 供恢复，失败/对象存储不可用清理 partial，不发布 final；相同 run/content 重试返回同一 immutable artifact，不允许覆盖不同内容。H001 只用 fixture 和只读 C 场流式 probe 验证，不执行 H003 的真实双事件导入。

#### CARE-H001 — Implementation / Targeted Validation (2026-08-26 20:17 +08:00)

- 依赖/入口：`benchmark` extra 和 `uv.lock` 固定 PyArrow `21.0.0`、scikit-learn `1.9.0`；新增 `windops-care-pipeline`，重型包只由动态 worker/CLI 入口加载。独立子进程导入完整 FastAPI `windops_backend.main` 后确认 `pyarrow`/`sklearn` 均不在 `sys.modules`。
- 执行/恢复：新增带 SHA-256 的任务状态和 chunk checkpoint，覆盖四种 operation、心跳、进度、当前文件、资源统计、取消、portable job ID、最多 3 次重试、非重试错误立即终态、断点恢复以及 checkpoint 路径/连续索引/行数/hash 语义复核。
- Parquet：1 MiB CSV batch、宽表、`care/v6/standard/farm=<farm>/event=<id>`、ZSTD level 3、8,192 行 row group；时间字段在 chunk 边界前规范为 `timestamp[ms]`，保存/复核 source/schema/content hash、行数、row group、版本和物理压缩。对象键包含完整 content SHA，重试相同内容幂等，不同 source/content 失败关闭。
- 对象存储：新增 CARE bucket 与 raw/standard/quality/predictions/reports 五个配置 prefix；Compose 创建私有 bucket、启用 versioning 并导入确定性生命周期 JSON，worker policy 无 DeleteObject；CARE bucket 进入 production readiness 和标准备份/恢复精确 bucket 集合。ADR 记录 PyArrow 选择、替代方案、运行边界和物理布局。
- 韧性修复：首轮 4 个失败揭示 CSV `timestamp[s]` 经中间 Parquet 读回为 `timestamp[ms]`，已在物理 schema 前规范化；第二轮 4 个失败揭示 Windows Parquet 句柄阻止成功/失败清理，已显式关闭 chunk/final reader。随后专项 `9/9` 连续通过，未弱化测试。
- 真实大文件只读证据：对 manifest 中最大 C 场 event 44（`354,063,087 bytes / 63,003 rows / 957 columns`）完整扫描 `338` 个 batch；峰值 record batch `1,623,284 bytes`、Arrow allocation delta `1,653,952 bytes`、4.339 s，source SHA `ec71a502...ca100` 与 C001 manifest 一致。证据 `.artifacts/care-v6/pipeline/c-event-44-bounded-probe.json` 文件 SHA-256 `C277F903...98E7`；没有转换或修改原始文件。
- 验证：pipeline 专项 `9/9`；CARE、model runtime、ingest、configuration、backup、ops/release 相关回归 `121/121`；配置/备份复跑 `19/19`；Compose `config --quiet` 通过，固定 MinIO mc 镜像确认 `ilm import` 接受 JSON stdin。pipeline contract 两次字节一致，contract SHA `796f3cbf...1f00`、文件 SHA `14C7C496...AC72`、2,653 bytes。
- 当前剩余：执行全相关 Ruff/strict mypy/diff 静态复核并再次对照 H001 Required Changes/Acceptance Criteria；未完成前保持 `IN_PROGRESS`。

#### CARE-H001 — DONE (2026-08-26 20:20 +08:00)

- Required Changes 复核：benchmark extra/lock、独立四操作执行合同、FastAPI 非重型边界、任务心跳/进度/取消/恢复/有限重试/checkpoint、宽表分区 Parquet 固定物理参数及 CARE 五层 MinIO prefix/lifecycle 均有当前实现和自动合同。
- Acceptance 复核：真实最大 C 场文件以 338 个 batch 完整扫描，峰值 batch/Arrow delta 仅约 1.62/1.65 MiB；相同 source/job 重试只返回同一 immutable artifact，完成状态不能重开或改写 artifact；列裁剪、物理 schema、峰值、Windows 句柄清理、对象存储不可用、checkpoint 篡改和在线 import 隔离测试均通过。
- 最终验证：相关回归 `121/121`；Ruff format/check `167` files、strict mypy `80` source、`uv lock --check`、Compose config、Prettier 和相关 diff check 全部通过。此前 `config.py` 的 Pydantic `_env_file` mypy 插件边界以窄 `Callable[..., Settings]` 动态构造适配收敛，没有 `type: ignore`，运行时配置测试 `8/8` 通过。
- 文件：`pipeline.py`、CARE exports、`test_care_pipeline.py`、`pyproject.toml`/`uv.lock`、`config.py`、MinIO/backup/readiness/Compose 配置、两份 MinIO JSON、ADR 与部署文档；证据位于 `.artifacts/care-v6/pipeline/`。原始 CARE 目录/ZIP 未修改，未启动项目服务，未执行 H003 双事件导入。

#### CARE-H002 — Start (2026-08-26 20:20 +08:00)

- 已重新核对 Audit H002 与需求第 11 节：必须一次性对齐 ORM、API schema、Alembic 和真实 PostgreSQL，复用 `RegisteredModel`；并覆盖既有告警来源回填、约束上线顺序、索引、回滚和并发唯一性。
- 下一步先检查当前 `0023` 唯一 head、模型/告警/预测/迁移调用链和真实 PostgreSQL test harness，再冻结最小但完整的实体关系；尚未修改 H002 schema 或数据库。

#### CARE-H002 — DONE (2026-08-26 21:13 +08:00)

- 实体/复用：新增 DatasetVersion、File、Event、FeatureMap、QualityReport、EvaluationRun、EventResult、MetricSnapshot、ReplayRun 和 anomaly alert policy state 共 10 类 ORM；Evaluation/Replay 通过复合外键关联既有 `RegisteredModel.id/version`，没有第二套模型注册表。新增 idempotent dataset/file/event/feature/quality/evaluation/result/metric/replay/policy-state 服务，PostgreSQL 使用 transaction advisory lock，SQLite 使用进程内锁。
- 结构化合同：严格 Pydantic schema 全部 `extra=forbid`，限制标识、hash、范围、显式时区和 JSON 的 65,536 bytes/2,048 nodes/depth 8/finite 值。发布指标保存名称/协议/版本/value/分子分母/阈值方向/通过状态；evaluation 完成必须逐项计入 scored/failed/unscorable，终态和制品不可原地覆盖。
- anomaly/告警：ModelPrediction 增加 prediction kind、正式 replay/evaluation FK、窗口时间/sequence、score/binary/component、threshold/feature/quality/evidence 结构列；成功 anomaly 结构由数据库 check 失败关闭。Alarm 保持既有 receipt 来源兼容并增加唯一 model-prediction 来源，至少一个来源；策略状态按 deployment/turbine/component/policy 唯一并以严格 revision 持久化。Replay 的 deployment 必须同时引用并属于其 RegisteredModel。
- 迁移：新增唯一 head `0024_care_benchmark_metadata`。升级先建父表/复合唯一键，再加 nullable prediction 列和 FK，按现有 RegisteredModel kind 回填 predictive/anomaly；对可验证的 anomaly JSON 回填结构列，旧成功 anomaly 缺治理字段时拒绝上线约束；最后放宽 receipt nullable 并增加 Alarm 来源 check。降级若存在无 receipt 的 model-only Alarm 会失败关闭，否则按依赖逆序恢复旧 NOT NULL 和 `0023`。
- 真实 PostgreSQL：固定摘要 TimescaleDB/PostgreSQL 16 隔离实例执行空库全量升级、`0023→0024` 既有数据升级、model-only alarm 降级拒绝、合法 `0024→0023→0024`、source-less alarm/partial anomaly 负向约束、并发 evaluation/result 竞争及既有 concurrency/prediction-lock/10 万级合同，共 JUnit `14/14`、0 failure/error/skip、89.384 s；证据 `.artifacts/care-v6/h002/postgres-full-final.xml` SHA-256 `768251080D78383B2C4158AD790080F5F8D5CFEC0DAD2DFCDDC04E6BC9221D3B`。
- 一致性：真实迁移测试逐表精确比较 10 类 CARE ORM 与 PostgreSQL column 集，并核对 RegisteredModel 复合唯一、evaluation/replay 外键、run/result 唯一、prediction/alarm/replay check 和关键索引；唯一 head/声明校验及完整 offline render 通过。补充 `alembic check` 仍报告本轮前已存在的旧表 nullable/index/unique 声明差异，但没有任何 CARE 表或 H002 新增列差异；归类为非 H002 历史漂移，未将该命令伪记为通过。
- 回归/静态：H002/C005/model 定向 `17/17`；CARE 全部及 model/alarm/ingest/config/backup/release 相关回归 `123/123`。Ruff format/check `170` files、strict mypy `81` source、`git diff --check`、迁移 head 声明全部通过；唯一 warning 为既有 `.pytest_cache` Windows ACL。
- 文件：`models.py`、`schemas.py`、`services/{models,benchmark_metadata}.py`、`alembic/versions/0024_care_benchmark_metadata.py`、`test_care_metadata.py`、两个 PostgreSQL external tests、迁移 head 声明及 README/runbook 文档。隔离容器按 `windops.project=wind-agent`/`windops.audit.issue=CARE-H002` 核对后停止并由 `--rm` 删除，端口 `55442` 释放；未修改原始 CARE 目录或 ZIP。

#### CARE-H003 — Investigation (2026-08-26 21:13 +08:00)

- 阶段切换前再次核对四份控制文件 hash；AGENTS/Audit/Goal/Progress 仍分别为 `25B10F39...AE06D`、`53C7331B...5DA0F`、`7310FF75...FBB2`、`8BA8BA1...74261E`，顶部状态为 H002 IN_PROGRESS/OPEN/Final Audit 0/2；H002 客观验证完成后才执行本次原子状态流转。
- 最小事件固定选择同一 A 场 source asset `0` 的 event 0 anomaly 与 event 24 normal，便于后续比较且保持事件隔离。C001 manifest 证据：A0 `54,986 = 52,148 train + 2,838 prediction`、source SHA `f0a8365b...bb26b`；A24 `55,003 = 52,289 + 2,714`、source SHA `310c27ba...697e`，两者 schema SHA 均为 `e0365b7d...8f576`，各 81 个信号列。
- 当前独立 CLI 只有 contract/parquet/probe，H001 已提供单文件有界 Parquet/checkpoint/immutable publish，但尚无把两事件清单、批准 Avg 投影、质量 report/mask、许可证 metadata 和 H002 registry 原子编排为一个可恢复 import run 的入口；H003 将补齐该最小编排与重复、取消恢复、失败清理和真值隔离测试，不扩展 A22/C/B。

#### CARE-H003 — DONE / Stage 1 PASS (2026-08-26 21:55 +08:00)

- 编排/选择：新增独立 `windops-care-minimal-import` 和 `care.importer`，严格固定同一 A 场 asset `0` 的 event `0` anomaly 与 event `24` normal，拒绝其他事件、错误标签、非 81 映射、非 54 approved Avg、控制制品 hash 漂移和真值字段进入标准/模型输入；没有扩展到 A22/C/B。
- 不可变制品：每事件生成 5 个技术列 + 54 个批准 Avg 的宽表 Parquet、独立质量报告、独立质量 mask、受限真值和全 81 映射制品；JSON 与 Parquet 均带完整 CARE 归属、推荐引用、DOI、CC BY-SA 4.0、`changes_made`、转换版本、源 hash 和 ShareAlike 复核声明，项目 MIT 代码许可证保持分离。新增统一 `licensing.py`，并补充 Parquet source dataset hash/物理 schema 校验和 Local/MinIO content type。
- 真实导入：只读执行 A0/A24 得到 `109,989 = 104,437 train + 5,552 prediction`；A0/A24 分别 `54,986/55,003` 行，source SHA-256 `f0a8365b...bb26b` / `310c27ba...697e`，源 schema hash 均为 `e0365b7d...8f576`。import identity `d66d37a6...d35c`，第二次 CLI 返回 `replayed=true` 且 manifest file SHA-256 均为 `b18ca209...c883`；对象存储精确 9 个制品、零 `.partial`，原 CSV 与 5.5 GiB ZIP 在前后校验中保持不变。
- 物理/资源：两份 Parquet 均为 `59` 列、`36` row groups、全列 `ZSTD`，模型输入与 manifest 精确一致且 truth intersection 为空；data SHA 分别 `f50c7fa3...733f` / `7e323947...2d85`。实测总耗时 `69.955 s`、吞吐 `1,572.274 rows/s`、峰值测量 `3,874,393 bytes`，并保存逐事件 Parquet/quality elapsed、rows/s、peak record batch、Arrow/tracemalloc 指标。
- 韧性/幂等：自动测试覆盖重复导入无重复对象、chunk 边界取消不发布 aggregate/partial、checkpoint 恢复、对象存储不可用失败清理、manifest/truth/mapping 篡改失败关闭。真实固定摘要 PostgreSQL 16 空库升级到唯一 head `0024_care_benchmark_metadata` 后，第一次登记精确 `88 created / 0 replayed`，第二次 `0 / 88`；最终为 `1 dataset / 2 files / 2 events / 81 maps / 2 reports`，真值 scope 为 `benchmark-evaluation-truth` 且描述未进入登记 metadata。
- 测试/静态：importer 专项 `5/5`、pipeline `10/10`，CARE/模型/告警/ingest/config 全相关回归 `92/92`；Ruff lint、Ruff format `173 files`、mypy strict `83 source`、`uv lock --check`、`git diff --check` 全部通过。仅有既有 `.pytest_cache` Windows ACL warning。
- 失败分类：首次物理检查使用了错误的 aggregate key、首次相关回归写错 ingest 测试文件名、首次 PostgreSQL harness 误以为迁移不会预置默认租户；三项均为只读验证脚本/调用前置假设错误。纠正后原硬断言全部通过，数据库唯一约束在错误前置下正确回滚，未修改产品门槛或掩盖产品失败。
- 文件：`backend/src/windops_backend/benchmarks/care/{importer,licensing,pipeline}.py`、`backend/tests/{test_care_importer,test_care_pipeline}.py`、`backend/pyproject.toml`；真实证据位于 `.artifacts/care-v6/minimal-import/`。临时 PostgreSQL 容器经精确名称、项目/H003 标签和 AutoRemove 核对后停止并删除，端口 `55441` 释放；原始 CARE 目录和 ZIP 未修改。

#### CARE-H004 — Investigation (2026-08-26 21:55 +08:00)

- 阶段切换前再次读取四份控制文件并核对 hash 未漂移：AGENTS `25B10F39...AE06D`、Audit `53C7331B...5DA0F`、Goal `7310FF75...FBB2`、Progress（写入前）`45C8B008...941675`；H003 验证完成后才执行本次状态流转，Final Audit 仍为 `0 / 2`、Final State `OPEN`。
- H004 必须在同一冻结 `care-score-v6` 协议下实现至少一个简单基线和一个目标 anomaly 路径，复用 RegisteredModel 并保存 feature/quality/threshold/random seed/dependency identity；真实双事件的 prediction、EventResult、MetricSnapshot 和失败/不可评分计数必须不可变且可复现。
- 下一步检查 C003 scoring artifact API、H002 evaluation 服务与现有 model registry 的精确调用边界，设计只读取 H003 truth-free Parquet 的 train/calibration 路径和仅由最终评估器读取 restricted truth 的最小执行器；不会把 prediction 标签、事件区间或描述泄漏给训练/阈值选择。

#### CARE-H004 — DONE / Stage 2 PASS (2026-08-26 22:37 +08:00)

- 双模型/同协议：新增独立 `windops-care-offline-evaluate` 与 `care.evaluation`。简单路径为每事件 train-only 标准化后的 maximum-absolute-z-score，目标路径为固定种子 `20260826`、32 个投影的确定性 random-projection ensemble；两者都使用 `care-event-train-prediction-v6-suite-v1` 套件和组件协议 `care-event-train-prediction-v6`，明确 `generalization_claim=none-minimal-fixed-event-suite`，没有把同一资产 A0/A24 虚报为 leave-one-turbine-out。
- 无泄漏/模型身份：训练只使用 `split=train` 且 trusted status `0`，两处真实 null 仅以各事件 train median 填补并记录计数；共享 threshold 分别由 train score 的 0.95/0.975 quantile 校准。模型包保存 54 列 feature/hash、quality contract/version/hash、threshold policy/hash、model-selection provenance、随机种子、NumPy/PyArrow/Python 数值合同、每事件 profile 和 target 投影矩阵；prediction 制品在全部写完后才打开 restricted truth，且不含 label、区间或描述。
- 冻结评估/失败计入：公开复用 C003 `FinalCareEvaluator`，套件必须对请求的两个 event 各给出 prediction、data/model failure 或 evaluator 产生的 unscorable，集合不闭合立即失败，不能静默丢弃。自动负向覆盖 model failure、区间缺失 unscorable、事件遗漏、hash/语义篡改和本地制品漂移；C005 激活门槛现可完整复核 H004 suite schema 并重建结构化 snapshot。
- 不可变/可复现：清单对模型包、四份 truth-free prediction、两份 evaluation 共精确 8 个对象逐一校验文件/document hash、大小、完整 CC BY-SA 4.0 metadata 和 ShareAlike 复核字段；模型/预测/评估 document identity 在独立输出根重建完全一致，`result_identity_sha256=4fcc370b...b5d1d3`，同输出根重跑 `replayed=true`、对象数不变、任何内容漂移失败关闭。
- 真实 A0/A24：evaluation identity `ac56a194...00bec`，manifest file SHA-256 `0ac2bbd1...ad47c`，8 对象共 `14,958,610 bytes`、零 `.partial`。z-score/RP threshold 为 `4.506536091667749` / `3.6263890407068016`；两个模型均为 `2 scored / 0 failed / 0 unscorable`，正常事件 max criticality `6/1`、均未误报，异常事件 max criticality `24/23`、未达到官方事件阈值 72，因此 CARE score 与 event detection 均为 0。12 个结构化 release metrics 中 8 个通过、4 个（两模型 CARE score/事件检测）未通过；该事实被保留，未伪报为候选发布通过，最终全量发布门槛仍归属 M004。
- 平台登记：复用既有 `RegisteredModel`，并将 model/evaluation/event/metric 重放比较扩展为完整不可变身份，completed artifact URI/hash 不能漂移；event 表中 aggregate CARE/reliability 引用显式记录 scope，避免冒充单事件分数。固定摘要 TimescaleDB/PostgreSQL 16 空库升级至唯一 head `0024` 后，真实制品首轮精确 `28 created / 0 replayed`、第二轮 `0 / 28`，最终 `2 models / 2 completed runs / 4 results / 20 metrics`；JUnit `.artifacts/care-v6/h004/postgres-real-offline-evaluation-final.xml` SHA-256 `fc515628...47f7f`，0 skip。
- 验证：H004 专项 `4/4`；scoring/anomaly/importer/metadata/model runtime 相关回归合计 `44/44`，最终改动后的 evaluation+metadata `7/7`。`uv lock --check`、Ruff format/check `140 files`、strict mypy `84 source`、`git diff --check` 全部通过；唯一 warning 为既有 `.pytest_cache` Windows ACL。真实原 CSV/ZIP 的 size/mtime/SHA-256 前后完全一致。
- 失败分类：首次 Ruff 发现测试 import ordering、首次 format-check 发现一处可重排断言，均按原门槛修复；一次 PowerShell 汇总管道语法和一次 Docker inspect template 转义错误仅属只读验证命令，改用明确集合/JSON 后硬断言通过。早期 ad-hoc probe 把阳性总数误称为 criticality，官方冻结评分器复核后准确值为异常 `24/23`、正常 `6/1`，进度只记录后者。
- 文件：`evaluation.py`、`scoring.py`、`anomaly.py`、`services/{models,benchmark_metadata}.py`、`test_care_evaluation.py`、`external/test_postgres_care_offline_evaluation.py`、`pyproject.toml`；真实制品位于 `.artifacts/care-v6/offline-evaluation/`。隔离 PostgreSQL 按 `windops.project=wind-agent`/`windops.audit.issue=CARE-H004`/AutoRemove 核对后停止并删除，端口 `55443` 无 listener。

#### CARE-H005 — Investigation (2026-08-26 22:37 +08:00)

- 阶段切换前已重新完整读取四份控制文件；写入前 SHA-256 为 AGENTS `25B10F39...AE06D`、Audit `53C7331B...5DA0F`、Goal `7310FF75...FBB2`、Progress `BD7FB531...D7D345`。准确状态为 H004 已验证、H005 待执行、Final Audit `0 / 2`、Final State `OPEN`。
- H005 必须使用正式 `BenchmarkReplayRun`、`care-v6-replay` 受治理 source、真实 `/api/v1/scada/ingest` 批量边界、正式 `ModelPrediction`/`Alarm.model_prediction_id` 和现有 Mission/诊断/决策/审计服务，不能用 fixture、fake receipt、前端 mock 或全量 TimescaleDB 展开替代。
- H004 target 的真实 truth-free binary 序列在异常/正常事件中最大连续 criticality 为 `23/1`；C005 在 H004 之前已冻结 trigger `3` windows/recovery `2` windows 的通用策略，因此 H005 可在不根据 prediction 真值调参的前提下验证异常触发与正常抑制。下一步先检查 ingest source 配置、replay 注册服务、anomaly inference adapter、告警→Mission→诊断现有真实调用链和可复用的 E2E harness，再实施最小完整双 run。

#### CARE-H005 — DONE / Stage 3 PASS (2026-08-26 23:26 +08:00)

- 在线链路：新增 truth-free 窗口选择、真实 Parquet 行读取、模型包完整性复核/评分、在线 score 规范化和冻结 trigger-3/recovery-2 策略；真实 replay row 经 `/api/v1/scada/ingest` 的 1000 批次边界进入 PostgreSQL，再由正式 anomaly deployment 推理写入 `ModelPrediction`。输入窗口携带同一 dataset/event/run/online turbine 和 54 个 approved Avg 的证据，禁止 prediction truth 字段。
- 告警闭环：新增 replay DB 行到 `run_anomaly_inference` 的服务适配和持久化 `AnomalyAlertPolicyState`；第三个连续异常窗口由 `ModelPrediction` 直接创建 model-only Alarm（`source_event_id=null`，没有 fake receipt），再走既有 Mission/多 Agent 诊断/alternatives/Decision/审计链。正常 A24 三窗口不产生 Alarm/Mission；同一 A0 新 run 的相同 row 产生不同 prediction/状态且未继承旧 run 计数。
- 回放状态：强化 replay 注册和进度持久化，状态/检查点可单独推进并逐变量核对真实 ingest receipt；测试在首个异常窗口后关闭并重建完整 FastAPI/engine/session factory，随后从 PostgreSQL 恢复 revision 1 并在 revision 3 触发。相同 ingest、推理、告警命令重试返回稳定结果且不新增样本/预测/业务对象；3 个 run 均完成并可重复登记。
- 发布身份：H004 target 模型包通过公共 verifier 和安全 JSON package inference adapter 执行；activation 只由服务器复算不可变 evaluation/metric snapshot 并绑定 model/package/deployment/approval/audit。修复真实 PostgreSQL 暴露的两个产品缺陷：DB 特征样本缺 `turbine_id` 导致窗口身份校验失败，以及 replay/evaluation 的 dataset FK `care-v6` 被错误直接比较为语义 version `v6`；现改为读取权威 `BenchmarkDatasetVersion` 后分别核对 ID/version。PostgreSQL test 环境允许 deterministic embedding provider，production PostgreSQL 仍拒绝非生产 provider。
- 真实验收：固定摘要 TimescaleDB/PostgreSQL 16 每次从空库升级到唯一 head `0024_care_benchmark_metadata`。最终两次独立新容器均 `1 test / 0 failure / 0 error / 0 skip`；最终 JUnit 内嵌 `378` ScadaSample/receipt、`7` prediction、`1` Alarm/Mission/Decision、三种业务 Evidence、3 个完成 replay run、正常抑制、重启恢复、同 run 幂等、新 run 隔离及 `prediction_truth_used=false`。最终证据 `.artifacts/care-v6/h005/postgres-real-vertical-slice-final.xml` SHA-256 `DCAA8DD9...08ED3`，前一独立通过证据 SHA-256 `A3CE68F5...4458A`。
- 回归/静态：replay/anomaly/evaluation/online/metadata/model/ingest/alarm/domain/operational/durable/idempotency 相关回归 `79/79`、0 skip，JUnit SHA-256 `BB960CA2...01251`；Ruff format/check `180` files、strict mypy `86` source、migration head 声明、`uv lock --check` 和相关 diff check 全部通过。默认 `.pytest_cache` 仍只有既知 Windows ACL warning。
- 失败分类：首次实测使用非 source-bound principal 得到正确 403，修正测试身份；第二/三次分别暴露上述 `turbine_id` 与 dataset ID/version 产品 bug并修复；第四次测试误用既有集合响应键，第五次用无业务依据的 Evidence `>=4` 计数。后两项改为锁定真实 API `data/decisions` 合同和三种精确 Evidence 类型，没有弱化业务链断言。
- 原始只读性：H005 后再次完整扫描 101 CSV/95 事件/5,242,948 行；与 C001 manifest 的逐字段差异只有 H001 后更新的项目 `dependency_lock_sha256`，所有 ZIP、文件、行数、schema 和 mapping 字段完全一致。复扫文件 `.artifacts/care-v6/h005/source-manifest-repeat.json` SHA-256 `4B0E5D37...A4D4`；未修改原始 CARE 目录或 ZIP。
- 文件：`benchmarks/care/{evaluation,online,scoring}.py`、`services/{anomaly_alerts,benchmark_metadata,models}.py`、`agents/tools.py`、`api/model_registry.py`、`schemas.py`、`tests/{test_care_online,external/test_postgres_care_vertical_slice}.py`。最终容器精确核对 `windops.project=wind-agent`/`windops.audit.issue=CARE-H005`/AutoRemove 后停止并删除，端口 `55444` 释放。

#### CARE-M001 — Investigation (2026-08-26 23:26 +08:00)

- 重新核对 Audit M001 与需求 10.1/15/16：数据中心必须从权威 benchmark 数据库/制品读取版本、DOI/许可证/校验和、覆盖/映射/质量和 import/evaluation/replay 状态；列表分页/过滤、摘要和曲线点数必须有服务端硬上限，生产模式不得加载原 CSV 或回退 fixture。
- H002 已有严格 benchmark 请求 schema 和注册服务，但当前 API 主要是逐类登记命令，尚未提供数据目录所需的统一只读 overview/event/curve 合同；现有 `app/data` 仍需检查是否只展示通用 data-contract fixture。下一步先枚举后端 benchmark 路由、访问策略和 `data-center-page` 的 production adapter，再实现最小完整的分页 API、服务端 Parquet 列裁剪/降采样以及 loading/empty/error/disabled/stale/permission UI 状态。

#### CARE-M001 — DONE (2026-08-27 00:14 +08:00)

- 后端/API：新增独立 `api/benchmarks.py` 与 `services/benchmark_catalog.py`，提供 dataset 50 条、event 64 条、recent replay 5 条/事件、变量 64 条/run、curve 16..512 点的硬上限；全部列表使用稳定排序、offset/limit、过滤和显式 `has_more/next_offset/bounds`。曲线只查询已持久化 `ScadaSample`，按 endpoint-preserving stride 在 SQL 端降采样，响应固定声明 `raw_csv_loaded=false`、`truth_included=false`，FastAPI 请求不读取 CSV/Parquet。
- 权限/真值：新增 `benchmark`/`benchmark_truth` data scope 及生产端点分类；dataset 同时按 tenant 与 benchmark scope 过滤，跨租户表现为 404。普通读者的 event SQL 只选择安全列，不选择 `event_label`/区间；真值筛选或 reveal 缺 scope 时 403 `BENCHMARK_TRUTH_FORBIDDEN`。数据集 anomaly/normal 汇总同样只在 truth scope 下计算和返回。
- 有界权威摘要：dataset 页面批量聚合数据库中的文件、事件、映射、最新每事件质量报告、评估和 replay 状态，展示版本、DOI、CC BY-SA、citation/attribution、manifest/archive/content 校验和、覆盖、质量/mask、导入/评估/回放；通用 `/data-catalog` 增加 `benchmark` 类别和 64 条稳定分页。质量报告用每事件 `row_number=1` 的最新版本，最大加载为 page datasets × 95，而非无界历史。
- 前端/生产链：`data-center-page` 在 production 直接调用 `/api/backend/benchmarks/...`，生产 gateway 显式 allowlist dataset/event/curve 且继续拒绝 raw 路径。界面提供服务端 dataset/event 分页与筛选、哈希/许可证/覆盖/映射/质量/run 状态、truth-restricted 标记和 128 点 SVG 曲线；实现 loading、empty、API error、demo disabled、placeholder stale 和 403 permission 状态，并在客户端再次拒绝超界、raw CSV 或 truth-bearing 曲线响应。Demo 明确不以 fixture 冒充 CARE。
- 真实 PostgreSQL：固定摘要 `timescale/timescaledb-ha@sha256:df8eaa04...bb2be` 空库升级至唯一 head `0024`，重跑完整 A0/A24 垂直切片并在真实 API 断言 `1 dataset / 2 events / 109,989 time points / 81 maps / 54 enabled / 2 completed evaluations / 3 completed replays`；受限读者看不到 truth，曲线为 3 个已持久化点、上限 16、未读 raw CSV。JUnit `.artifacts/care-v6/m001/postgres-real-benchmark-api.xml`：`1/1`、0 skip，SHA-256 `CF7A4140...1CC0D`。精确容器/标签/AutoRemove 核对后删除，端口 `55445` 释放。
- 回归/静态：新增 `test_care_catalog.py` 5/5 与前端合同 3/3；最终非 external 后端全量 `339/339`、0 skip，JUnit SHA-256 `5CB0E826...BF7A9`；前端 `pnpm test` production build/bundle + `139/139`，TypeScript、ESLint、Prettier、Ruff format/lint、strict mypy（88 source）、`uv lock --check`、migration head 和 diff check 通过。
- 失败与修复：全量回归发现 H005 的在线服务顶层导入间接加载 PyArrow，拆出纯标准库 `online_contract.py` 后 `import windops_backend.main` 再次证明不含 PyArrow/sklearn；另发现 CARE bucket 未进入灾备目标环境隔离，已增加 `WINDOPS_DR_TARGET_CARE_BUCKET`、文档及负向测试。全局 lint 首次错误来自扫描项目生成的 291 MB Playwright `.artifacts`，现将项目/后端 artifacts 与 pytest 临时目录加入 ESLint global ignores，标准 `pnpm lint` 恢复通过；未删除任何制品或弱化源码规则。
- 文件：`api/{__init__,benchmarks,deps,operations}.py`、`access_control.py`、`services/{benchmark_catalog,operational_views,anomaly_alerts}.py`、`benchmarks/care/{online,online_contract}.py`、`operations/dr_drill.py`、`test_care_catalog.py`、`external/test_postgres_care_vertical_slice.py`、`test_dr_drill.py`、`data-center-page.{tsx,module.css}`、`app/api/data-catalog/route.ts`、`lib/{platform-admin-data,production-runtime}.ts`、`tests/{care-benchmark-catalog,platform-admin,production-runtime}.test.mjs`、`eslint.config.mjs`、CARE 计划文档和灾备 runbook。

#### CARE-M002 — Investigation (2026-08-27 00:17 +08:00)

- 重新读取 Audit M002、需求第 8、10.2、10.3、16–18 节和评审 P0-5/P1-3；验收要求是复用现有 RegisteredModel 并展示不可变评估、失败/不可评分事件、服务器发布门槛，以及预测→告警→Mission 闭环，不得建立第二套模型实体或给 anomaly 伪造 RUL/30 天概率。
- 当前 `/api/v1/models` 已返回模型、deployment 和全局预测监控，但没有受治理 CARE 评估运行、结构化指标、事件结果/失败原因和门槛证据；当前 `/api/v1/diagnoses` 以 Mission 为主，尚未暴露 replay 合成时间、原始匿名时间、质量 mask、anomaly prediction、threshold policy 与受控真值链。
- 拟在 benchmark 服务/API 中增加有界、作用域隔离的模型评估与诊断查询，并在现有模型管理/诊断页面仅于 production 模式调用；demo 保持明确 fixture 标识且不冒充 CARE。测试将覆盖权限、真值隐藏/揭示、空页、分页上限、缺制品、stale deployment、失败/不可评分事件和前端失败关闭/响应式合同。

#### CARE-M002 — DONE (2026-08-27 01:02 +08:00)

- 后端/API：`services/benchmark_catalog.py` 与 `api/benchmarks.py` 新增 evaluation 32 条、metric/result 64 条、model deployment 8 条、diagnosis replay 32 条、prediction/signal 64 条的硬上限和稳定分页；所有查询先按 dataset、tenant、turbine 和 benchmark scope 收敛。安全联接显式处理全局 RegisteredModel 的 ORM tenant criterion，避免数据集已授权但模型被静默过滤。
- 模型评估：生产模型管理页面直接读取 `/api/backend/benchmarks/evaluations` 与有界 event result API，展示 anomaly 类型、模型 ID/version、baseline/target 算法、评估/特征/质量/阈值/随机种子/依赖身份、CARE 组成分、正常误报、异常检测、失败/不可评分事件、不可变制品、服务器发布门槛及 deployment current/stale 状态；缺制品、失败计数或 release metric 不通过均由服务端 gate 拒绝。
- 诊断闭环：生产诊断页读取 `/api/backend/benchmarks/diagnoses`，展示 replay synthetic time、原始 anonymous time 证据、source row、质量摘要与 mask 引用、score/binary/threshold/window、模型/部署/制品，以及 prediction→Alarm→Mission→Decision 链。首次告警提前量明确为 source-row offset，固定声明不是经验证 RUL；响应不包含伪造 RUL、30 天概率、raw CSV 或原始信号值。
- 权限与 UI 状态：评估前/无 `benchmark_truth` scope 时真值和故障描述不进入 SQL 选择或响应；有权限并显式请求后才揭示。模型/诊断各自缺 scope 返回明确 403。生产 UI 覆盖 loading、empty、network/API error、permission、disabled、重复 refresh/truth 请求和响应式布局；demo 明示 fixture，不能冒充 CARE 生产链。
- 数据登记：离线评估登记将 `algorithm`、baseline/target `evaluation_role` 与 `dependency_identity` 从不可变 manifest 持久化到 RegisteredModel/evaluation 扩展字段，使 UI 可从数据库复建，不读取制品正文。
- PostgreSQL 证据：固定摘要 TimescaleDB 空库升级至唯一 head `0024_care_benchmark_metadata`，完整 H005 垂直切片后真实 API 得到 `1 target evaluation / 2 event results / 3 diagnosis replays / 7 predictions`；truth scope 失败关闭，异常产生 Alarm/Mission、正常无告警，1/1、0 skip。JUnit `.artifacts/care-v6/m002/postgres-real-model-diagnosis.xml` SHA-256 `286C6E13...F62228`；精确容器与 `55446` LISTEN 已核对清理。首个清理检查误把 TCP `TIME_WAIT` 当监听，改为精确 `LISTEN` + 容器存在性检查后通过，属于验证脚本分类错误。
- 回归与静态：M002 后端专项 `test_care_catalog.py` 9/9，CARE 合同/评估/流水线/回放安全复核 38/38；修改后非 external 后端全量 `343/343`、0 skip，JUnit `.artifacts/care-v6/m002/backend-nonexternal-final.xml` SHA-256 `E0A1B266...5ABC8C`。前端 `pnpm test` production build/bundle + `143/143`，M002 静态合同 4/4；ESLint、Prettier、TypeScript、Ruff format/lint、strict mypy（89 source）、Bandit（0 findings）、`uv lock --check`、migration unique head 与 `git diff --check` 通过。
- 失败分类：默认 `uv run alembic check` 因本机默认 PostgreSQL 未运行而 `ConnectionRefused`，属环境前置条件；本轮没有 schema 变更，真实隔离 PostgreSQL 已完成空库升级和运行链验证。此前 Bandit 发现 CARE 内 8 个低危项，已以纯文件读取 Git HEAD、显式阈值错误、可观测临时对象清理失败及非秘密 dataset prefix 常量消除，没有添加豁免或弱化扫描。
- 文件：`backend/src/windops_backend/{services/benchmark_catalog.py,api/benchmarks.py,benchmarks/care/{contract,evaluation,pipeline,replay}.py}`、`backend/tests/{test_care_catalog.py,external/test_postgres_care_vertical_slice.py}`、`components/pages/{model-management-page,diagnosis-center-page}.{tsx,module.css}`、`tests/care-model-diagnosis.test.mjs`。

#### CARE-M003 — Investigation (2026-08-27 01:05 +08:00)

- 重新核对 Audit M003、需求 2.2–2.3、5.1、7.3–7.4、12 阶段 4、14、16–18 与评审 P1-4。现有 `CareObjectStorageLayout` 已固定独立 bucket 和 raw/standard/quality/predictions/reports 私有 prefix、生命周期/备份边界；`benchmark`/`benchmark_truth` scope、dataset tenant 和 replay turbine scope 已保护目录/真值/诊断查询。
- 现有 `licensing.py` 已为标准 Parquet、映射、质量 mask/report、restricted truth、模型包、预测和评估报告生成并严格复核归属、推荐引用、Zenodo、DOI、CC BY-SA 4.0、`changes_made`、转换版本、源 dataset/artifact SHA、ShareAlike-required 和 MIT 分离声明；各制品 manifest/reference 另持有自身 content/file SHA。
- 实际缺口：阶段 4 要求的受控 CSV/JSON 报告导出尚不存在；`external_distribution_review=required` 目前只是元数据字符串，没有服务器端复核门槛、不可变审批/导出审计或重复/篡改保护；也没有可执行的精确 dataset version/run 清理合同。M003 将最小新增治理服务/API、持久化审计实体与迁移，并把现有访问隔离和许可证传播纳入正向、权限、跨租户、篡改、重复与越界清理测试；不会实际删除本地 CARE 原始数据或调用其他项目对象存储。

#### CARE-M003 — DONE / Stage 4 PASS (2026-08-27 02:00 +08:00)

- 受控导出：新增治理服务和 `POST /api/v1/benchmarks/evaluations/{evaluation_run_id}/exports`，只接受完成且未失效、dataset/tenant/model/evaluation 身份和 source artifact SHA 全部匹配的运行；结果/指标使用 `max+1` 硬上限并要求事件核算与实际行数完全一致，不能截断后伪装完整。JSON/CSV 均确定性生成并防 CSV formula injection；所有 POST 使用项目统一必填 `Idempotency-Key` 请求头、PostgreSQL advisory/local lock、不可变完成/拒绝审计，相同请求返回相同字节，不同内容复用 key 为 409。
- 权限与外部分发：导出要求 `benchmark + model + benchmark_export`，真值另需 `benchmark_truth`；普通导出 SQL 不选择真值列，跨租户为 404，源 SHA 漂移/不完整结果为 422。外部导出必须逐项确认 attribution、许可证链接、ShareAlike 和 legal/compliance reference；缺任一项先提交 `benchmark.export.denied` 再返回 403。生产 gateway 修复为只允许已声明 benchmark GET 和 export POST 路径，继续拒绝 raw/未知方法。
- 制品与许可证：每个宽表 Parquet schema 内嵌完整确定性许可证 JSON、归属、推荐引用、Zenodo DOI、CC BY-SA 4.0 链接、`changes_made`、转换版本和 content-hash sidecar/object-key 位置，并由读取器逐字段复核；所有派生 manifest/report/export 继续携带 source dataset/artifact hash 与自身 byte/content hash。`THIRD_PARTY_NOTICES.md` 和新 runbook 明确 CARE 数据/派生制品不受仓库 MIT 代码许可证覆盖。
- 存储/清理隔离：CARE bucket 现在强制不同于 field evidence、knowledge、model、twin bucket；normal worker policy 无 DeleteObject，独立 break-glass cleanup policy 仅允许 standard/quality/predictions/reports，raw 永不允许。清理 scope 必须精确绑定 CARE v6 dataset SHA 和 farm/event 或 model/run，最多 256 个经复核的 object-name/SHA 集合；prefix/list/stat/hash 任一漂移失败关闭。生产 orchestrator 在不可逆删除前提交 `benchmark.cleanup.started`，完成/失败/拒绝后再提交结果；成功重放不重复删除，中断/失败必须人工复核并使用新 ID，调用方无法靠漏写审计绕过。
- 全链审计：import、quality transform、evaluation、replay 注册均增加结构化 DomainEvent；真实 PostgreSQL 同时断言四类操作事件及 export completed/denied。审计只含身份、范围、版本、hash、计数、复核状态和原因，不含对象存储凭据；本轮未执行任何真实 CARE 源数据或对象存储删除。
- 真实 PostgreSQL：固定摘要 `timescale/timescaledb-ha@sha256:df8eaa04...bb2be` 从空库升级到唯一 head `0024_care_benchmark_metadata`，完整垂直切片验证真实 import/evaluation/replay/API、内部 JSON 导出字节幂等、外部 ShareAlike 拒绝和审计事件，`1/1`、0 failure/error/skip。JUnit `.artifacts/care-v6/m003/postgres-real-governance.xml` SHA-256 `82E194B1...D7E5B2`；精确容器/标签/AutoRemove 和 `55447` LISTEN 已核对清理。
- 回归/静态/安全：PyArrow `21.0.0` 被 `pip-audit` 识别为 `PYSEC-2026-113` 后升级并锁定 `23.0.1`（lock SHA-256 `D6F55FFA...393DE`），升级后的 pipeline/import/evaluation/quality 及全量非 external 后端 `351/351`、0 skip，JUnit SHA-256 `B50E674D...2A579`；前端 production build/bundle + `143/143`。Prettier、ESLint、TypeScript、Ruff format/check（186 files）、strict mypy（90 source）、Bandit 0 findings、`uv lock --check`、`pip-audit`、`pnpm audit --prod` 和 `git diff --check` 均通过。
- 失败分类：首次相关测试因 datetime JSON 序列化和类型收窄失败，修复为显式 ISO 时间/类型；全量回归发现 export POST 未声明必填幂等请求头，改用统一 Header 合同后通过；首次安全审计发现上述 PyArrow 漏洞并真实升级、未豁免。一次从仓库根运行 backend Ruff 因错误工作目录找不到工具，切换到 `backend` 项目环境后标准命令通过。隔离空库上的通用 `alembic check` 还报告一组早于 CARE、且与本轮无 schema 修改的全局 server-default/nullability/index autogenerate 漂移；CARE `0024` 空库升级、唯一 head、实体约束和真实链已通过专用迁移/PostgreSQL 门禁，该既有全局差异留待 M004 最终 migration 复查，未伪报为环境失败或静默忽略。
- 文件：`backend/src/windops_backend/{api/benchmarks.py,access_control.py,schemas.py,services/{benchmark_catalog,benchmark_governance,benchmark_metadata}.py,benchmarks/care/{pipeline,importer,evaluation}.py,config.py}`、`backend/deploy/{README,care-minio-cleanup-policy.json}`、`backend/tests/{test_care_catalog,test_care_governance,test_care_pipeline,test_configuration,external/test_postgres_care_vertical_slice}.py`、`lib/production-runtime.ts`、`tests/production-runtime.test.mjs`、`docs/runbooks/care-artifact-governance.md`、`THIRD_PARTY_NOTICES.md`、`backend/{pyproject.toml,uv.lock}` 和列式 ADR。

#### CARE-M004 — Investigation / Stage 5 Start (2026-08-27 02:00 +08:00)

- Audit M004 要求严格按 A 场 22 事件→C→B 扩展并最终证明 95 事件、按 farm 命名空间计算的 36 资产、45 anomaly、50 normal 和 5,242,948 时间点；还需场内泛化、资源门槛、权限/备份/故障/取消恢复、运行手册和最终全局门禁。跨场协议只有建立人工审核 ontology 后才能启用，当前 `cross-farm-ontology-v1` 仍应失败关闭，不能为追求全量声称伪造 ontology。
- 当前 C001 contract 已完整扫描全部 95 事件，H001 单事件流水线支持全信号宽表、有界 batch、checkpoint、心跳/取消/重试和不可变 publish；H003/H004 orchestration 则明确硬编码 A0/A24，不能把两事件 bundle 冒充全量。现有双事件评估会一次读入两份 Parquet，不能直接扩展到 C/B 大文件。
- 将新增独立 full-scale CLI/Worker 模块：按阶段顺序对每个事件生成全列宽表、质量/mask/真值隔离和事件级恢复摘要；用分批统计/推理完成每个 farm 的 leave-one-asset-out，不把 prediction truth 暴露给训练/阈值；产出不可变全量 manifest、场内评估/发布回归和资源证据。真实运行前先以 fixture/故障注入测试锁定状态、hash、恢复、内存/存储/时间硬门槛；不会把 5.24M×全信号展开到 TimescaleDB。

#### CARE-M004 — Implementation / A22 Milestone (2026-08-27 02:42 +08:00)

- 全量执行器：新增 `care.fullscale` 与 `windops-care-full-scale import/evaluate/status/cancel`。导入严格使用 contract 的 A→C→B 顺序，保存 metadata + 每场全部映射信号的宽表 Parquet，同时仅把批准 Avg 标为模型输入；逐事件质量 report/mask、restricted truth、全列 mapping 和可恢复 event summary 均为内容寻址不可变制品。aggregate manifest 只在全部事件与资源门槛通过后发布，TimescaleDB 全量展开计数硬编码并复核为 0。
- 场内泛化：评估器用两次 streaming pass 计算每场总矩与逐资产矩，再以“场总量减 held-out asset”生成 36 个 farm-namespaced leave-one-asset-out profile；逐事件分批预测，所有 95 份 truth-free prediction 先进入 freeze manifest，之后只有 `FinalCareEvaluator` 读取 restricted truth。阈值固定复用全量运行前 H004 A-minimal train-only 校准值，跨场 ontology/human review 保持 disabled/空集合。
- 明确门槛：版本化默认上限为 import 12h、evaluation 6h、batch 16 MiB、Arrow 512 MiB、Python 1 GiB、import/eval storage 64/8 GiB、吞吐至少 100 rows/s、prediction 281,249、Parquet row group 8,192、replay batch 1,000、catalog/curve 64/512、frontend 512 KiB、query p95 500 ms；超限为可观察的 terminal failure，不能靠前端或 JSON 绕过。
- 韧性与运维：fixture 覆盖 event-boundary cancel/new-job resume、对象存储故障 pending/同 job retry、资源超限 terminal/new job recovery、零 `.partial` publish、重复运行相同 SHA、篡改/缺事件/跨场启用失败关闭。新增运行手册记录权限、状态/取消命令、三次有限重试、损坏隔离、数据库/对象存储故障、CARE bucket 备份与隔离 DR、禁止 raw cleanup 及发布证据。
- 权威登记修复：调查发现 H003 把阶段性 minimal bundle SHA 当成 DatasetVersion manifest SHA，会让同一 CARE v6 在全量补齐时被数据库正确拒绝。现改为 dataset identity 永久绑定完整 source contract SHA/URI，阶段性 bundle 仅作为 import artifact；新增全量幂等登记覆盖 dataset、95 file/event/quality、1,285 mapping、3 farm model、36 fold、95 result 和结构化 release/failure metric。单类 fold 的事件点级结果可评分但总体 CARE score 按官方协议为空，新增 `0025_benchmark_event_score_scope` 仅放宽该准确语义，failed/unscorable 仍禁止携带 score，downgrade 明确转换不可表示的行。
- 迁移合同收敛：真实固定摘要 TimescaleDB 的 `alembic check` 客观暴露 16 个 ORM 必填时间戳仍为数据库 nullable，以及 Decision/FieldTaskEvidence 唯一约束、knowledge scope 复合索引、SCADA 降序索引与 Timescale 自动索引的声明差异。新增 `0026_schema_contract_alignment` 对遗留 null 先以数据库当前时间可追溯回填再设 NOT NULL，downgrade 仅恢复 nullable；ORM 显式匹配既有约束/索引，Alembic 仅精确忽略 Timescale 自管 `scada_samples_observed_at_idx`。专用数据库从 `0025→0026` 后 current 为唯一 head，`alembic check` 为 `No new upgrade operations detected`；完整真实 PostgreSQL migration/约束/10 万行性能套件 `6/6`、0 skip，JUnit SHA-256 `59B9D90D...63EBD`；完整 offline SQL 74,796 bytes、SHA-256 `1E12A3F8...D975`，未把原漂移误报为环境失败。
- 定向验证：`test_care_fullscale.py` 最终 `7/7`；与 importer/metadata 合并 `15/15`，Ruff 和相关 strict mypy 通过。测试硬断言 fixture 全量登记首轮 import/eval `25/45 created`、重放 `25/45 replayed`、`6 event/6 fold/30 metric`，所有单事件 fold 保持 `status=scored, scorable=true, care_score=null`，没有用伪 0 分掩盖协议不可聚合。
- 真实运行与性能根因：v1 完成 A22 后，C 场 952 列逐值质量审计被每分配 `tracemalloc` 探针放大到单事件约 8–10 分钟，外推会威胁 12 小时硬门槛。通过正式 cancel 接口请求事件边界停止；v1 在 25/95 后状态精确为 `cancelled`、error=null，CLI 明确抛出 `BenchmarkJobCancelled`，已完成对象均有 summary 且没有 aggregate manifest/partial publish。没有强杀或调大门槛。
- v2 计量修复：full-scale 专属资源策略升级为 v2，使用 OS whole-process resident high-water mark，覆盖 Python、Arrow 和 native allocation 且不插桩每次 Python 分配；H003 公共 minimal-import 的既有 traced-memory 合同保持原样。资源 helper 在 Windows 实测返回非零，Ruff/mypy 和 full-scale/importer `12/12` 回归通过；全新根的 `care-v6-full-import-real-v2` 约 80 秒完成 A 场前 9 个事件，首事件 Parquet 约 32,315 rows/s、质量约 11,954 rows/s、进程 HWM 约 161 MiB，继续按 A→C→B 执行。
- 资源对抗与 v3：v2 首两个 C 事件吞吐已改善，但 whole-process HWM 分别为 1.023/1.133 GiB，真实超过 1 GiB，因此再次经 durable boundary 在 25/95、error=null 取消，未放宽门槛。隔离探针证明 C1 Parquet 单独峰值 951,693,312 bytes、质量单独 184,954,880 bytes，问题是释放页未归还导致跨阶段驻留叠加；v3 在 Parquet/quality/training/prediction 边界执行 GC + OS working-set/malloc trim，trim 失败即失败关闭。同进程真实 C1 探针在 Parquet 后峰值 952,471,552 bytes，trim 后完成 128,959 masks 仍保持相同峰值，低于 1 GiB 121 MiB；full-scale `8/8`、Ruff/mypy 通过。
- 数据库运维入口：`windops-care-full-scale register` 现在从环境读取受控 PostgreSQL URL，在一个事务中复核并登记 import+evaluation manifest；数据库故障会整体回滚，同命令恢复后必须全部 replay 而不得重复。CLI 路由与真实 SQLite 权威登记定向 `2/2`，运行手册已加入命令与失败语义。完整非 external CARE 回归为 `101/101`、0 skip，JUnit SHA-256 `DDA74065...0FE91`。

#### CARE-M004 — Fixed Row-group / v5 Candidate (2026-08-27 07:46 +08:00)

- v3 在完成 `29/95`（A22+C7）后于正式 durable boundary 精确进入 `cancelled`，`error=null`、`cancel_requested=true`、checkpoint 为 C11，CLI 抛出预期 `BenchmarkJobCancelled`，没有 aggregate manifest；C4 的 whole-process HWM 为 `1,079,853,056` bytes，真实超过 1 GiB，未放宽门槛。
- 首次 v4 对抗把 CSV block 从 1 MiB 降为 256 KiB；真实 C4 虽保持 `56,449` 行和 `118,578` masks，但生成 `1,203` 个细碎 row group、Parquet `478,798,929` bytes、OS HWM `3,554,697,216` bytes，因此失败关闭，没有启动全量。
- 根因是旧 merge 把每个可恢复 CSV chunk 直接写成最终 Parquet row group，导致宽表的 writer metadata 随 chunk×column 数增长；旧 1 MiB C4 也有 `301` 个 row group，与治理声明的固定 8,192 行组不一致。
- pipeline/layout 升级为 v2：checkpoint 仍逐块可恢复，final merge 在有界 batches 上流式 coalesce，除末组外必须精确 8,192 行，manifest verifier 同时验证精确组数/每组行数。新增 64 KiB 碎片回归证明 18,000 行稳定得到 `8,192/8,192/1,616`；相关 pipeline/full-scale `19/19`、Ruff、strict mypy 和 runbook Prettier 通过。
- v5 恢复 1 MiB CSV block。全新真实 C4 探针得到 `56,449` 行、`7` 个 row group、Parquet `95,134,429` bytes、Parquet/quality `44.80/69.83 s`、whole-process HWM `375,762,944` bytes（低于 1 GiB `697,978,880` bytes），trim 成功，具备启动 fresh v5 全量候选的资源证据。
- fresh `care-v6-full-import-real-v5` 已完成 A `22/22` 和 C1（总 `23/95`），状态 `running`、`error=null`。真实 C1 为 `53,569` 行、`7` 个 row group、Parquet `92,809,652` bytes、Parquet/quality `42.43/61.43 s`、HWM `355,971,072` bytes，吞吐 `1,262/872 rows/s`，继续按 C→B 顺序推进。
- 备份边界复查发现通用 runbook 仍写旧的四 bucket；已按实际 `governed_buckets()` 修正为 PostgreSQL/TimescaleDB + 五个 bucket，显式包含 CARE `raw/standard/quality/predictions/reports`、版本控制、对象 SHA 和隔离恢复抽样。备份回归 `6/6`、Ruff 与两份 runbook Prettier 通过。
- 在精确容器 `windops-care-m004-pg-20260827` 中确认目标不存在后创建专用空库 `windops_m004_fullscale`；在线空库 upgrade 到唯一 `0026_schema_contract_alignment`，`alembic current` 精确为 head，`alembic check` 为 `No new upgrade operations detected`。没有修改基础验证库或其他项目数据库。
- 新增真实 PostgreSQL full-scale 外部门禁：验证首轮/重放登记、95 file/event/quality、1,285 mapping、3 model、36 fold、95 result 和动态 metric 精确计数，36 farm-namespaced assets、45/50 标签、5,242,948 行、CARE Timescale full-signal rows=0；同时实测 dataset/event/evaluation API 分页、权限、512 KiB 响应和 p95 500 ms。普通环境仅按既有 external marker 跳过，尚未把未完成的真实运行记为通过；将在 v5 evaluation 后以 `WINDOPS_FAIL_ON_SKIPPED=1` 执行。
- full-scale CLI 新增与 `--object-store-root` 互斥的 `--use-configured-minio`，生产 Worker 只从受控 settings 取得专用 CARE bucket，runbook 明确无 store 仅为未发布本地派生、不得冒充生产发布；MinIO 选择/互斥合同和 full-scale 回归 `9/9`、Ruff/mypy 通过。
- 备份/DR 复查进一步发现旧恢复器要求目标 bucket 名与源清单完全相同，而 DR 又强制源/目标五 bucket 不相交，导致真实隔离演练必然失败。备份格式升级为 v2 的稳定角色绑定（field evidence/knowledge/model/twin/CARE），restore 按角色映射到隔离目标并逐对象回读 hash；v1 继续只允许同名恢复。新增 CARE 对象从 `windops-care-benchmarks` 恢复到 `restore-care` 的可失败合同，backup+DR `9/9`、Ruff/mypy/Prettier 通过。
- 固定摘要 MinIO `d249d1fb...acbc0` 已以精确容器/项目标签和 loopback `55900/55901` 启动，源/隔离目标各五 bucket 已创建，两个 CARE bucket 启用 versioning/lifecycle。真实 policy create 首次揭示 worker/cleanup JSON 把 `s3:prefix` 错套到 `GetBucketLocation`，MinIO 拒绝；已拆为无条件 bucket-location + 受 prefix 限制的 list，两个策略现均由真实 MinIO 接受。受限 `care-worker` 对 content-addressed report 实测 Put 允许、Delete exit 1、对象仍可 stat；没有给予 normal worker DeleteObject。一次用 helper image `grep` 检查错误文本因镜像无 grep 退出，改为直接硬断言 delete 非零和对象仍存在后通过，未掩盖产品失败。
- v5 已完成 A `22/22`、C `58/58`、B `15/15`；最终 state 为 `completed / 95/95 / error=null`，顺序严格为 A→C→B，没有提前发布 aggregate。新 verifier 从不可变事件摘要重算并通过：`5,242,948` rows、`281,249` prediction points、`7,559.916 s` 累计操作耗时、`7,846.499 s` wall-clock、`693.519 rows/s`、HWM `521,977,856`、Arrow peak `12,294,528`、batch peak `2,227,511`、制品 `9,273,379,161 bytes`、0 violation；本地 store 为 383 files/`9,270,405,441 bytes`、0 partial/tmp。manifest document/file SHA-256 为 `a0c89223...d8f910` / `ffbd2451...8ded5f`，独立重放 `replayed=true` 且文件 SHA 完全一致。
- MinIO 生产发布缺口复核：真实 normal-worker policy 按 M003 设计不含 `DeleteObject`，但旧适配器在最终对象已成功 copy/stat 后仍把 `_tmp` 删除的 `AccessDenied` 当成 retryable failure，导致 `--use-configured-minio` 无法完成。现仅在最终对象大小与 SHA 已验证、且 cleanup 错误码精确为 `AccessDenied` 时交由强制 7 天生命周期清理；其他 cleanup 错误或发布阶段错误仍失败关闭。fake 正/负向测试、完整 pipeline `11/11`、Ruff format/lint（192 files）、strict mypy（92 source）、`uv lock --check`、Prettier 和 diff check 均通过。
- 真实 MinIO 适配器证据：在固定摘要、项目专用 MinIO 上重置隔离 `care-worker` 测试凭据并复用已验收的无删除 worker policy；实际 `MinioImmutableArtifactStore` 首次发布及第二次幂等读取均成功，最终对象 `660 bytes`、SHA-256 `7d283e16...d730`、metadata hash/size 一致。Worker 的删除被真实拒绝后 `_tmp` 精确保留 1 个私有对象，root 侧复核 `care/v6/_tmp/` 生命周期精确为 7 天；该对象不是 release evidence，runbook 已记录生命周期延迟清理边界。持久证据 `.artifacts/care-v6/m004/minio-restricted-worker-adapter-evidence.json` SHA-256 `0CDAA6B0...51EFA`。
- DR 前置复核发现通用备份原先遍历 CARE bucket 全部对象，会把合同声明 `backup=false` 的 `_tmp` 临时区一并备份。现备份只接受 `raw/standard/quality/predictions/reports` 五个治理前缀，显式跳过 `_tmp`，未知 CARE 前缀失败关闭；测试真实构造 final+temporary 后只登记 final。backup+DR `9/9`、Ruff/mypy、Prettier 和 diff check 通过，运行手册同步该恢复边界。
- PostgreSQL/API 外部门禁预审发现 evaluation endpoint 的生产硬上限是 32，但新测试误请求 `limit=64` 且假设单页包含 36 fold；旧测试会以 422 失败而不能提供 M004 证据。现改为 `32+4` 两页并合并精确 36 fold/95 event accounting；Ruff、py_compile 通过，普通环境仍按既有 external marker 预期 skip，未把该 skip 计为执行通过。
- 上述 MinIO/备份/API 修复后的 full-scale + pipeline + backup + DR 相关回归合并为 `29/29`、0 failure；既有 `.pytest_cache` Windows ACL warning 不影响独立 `--basetemp` 结果。
- DR 数据库不变量复核发现旧通用清单只检查 11 个业务表，未覆盖 CARE 权威元数据；即使 CARE 表恢复不完整，命令级验收也可能误判。现 snapshot 与 restore 后精确比较 dataset/file/event/feature/quality、evaluation run/event result/metric、replay run、anomaly policy state 等全部 CARE 表；新增合同逐表锁定查询，backup+DR 更新后 `10/10`、Ruff/mypy/Prettier/diff check 通过。
- DR 对象身份复核发现恢复上传虽逐对象回读内容 hash，却没有恢复 immutable adapter 所依赖的 MinIO SHA-256 metadata；恢复后的 CARE key 会被后续幂等 publish 误判为身份漂移。现 restore 将清单中重新计算且已验证的 SHA-256 写回对象 metadata，并由隔离 CARE bucket 映射测试锁定；更新后 backup+DR 仍为 `10/10`。
- 为真实 DR 演练预建最小权限边界：项目内证据 policy 分别只允许源五 bucket 的 List/Get 和隔离目标五 bucket 的 List/Get/Put，二者均无 Delete；SHA-256 为 `6FCDA592...4DD4B` / `B4D80CFD...24A1F`。固定摘要真实 MinIO 已实际接受并可读取两个 policy；首次将 PowerShell 数组作为一个 Prettier 参数导致 no-match，改用两个显式路径后原格式门槛通过，未把错误调用计为产品失败。
- 需求 13.6 要求回放限速/数据库写入速率证据；既有真实 H005 只记录 378 samples 而未量化耗时。full-scale operational policy 升级为 v4，预注册 batch `<=1000`、最低 `50 rows/s`；真实 H005 的七个 PostgreSQL ingest 批次分别测量首轮提交时间，低于即失败并写入 JUnit property。full-scale `9/9`、Ruff/mypy/py_compile/Prettier/diff check 通过；稍后将在独立 replay 数据库以 0 skip 执行，当前尚未把静态修改记为性能通过。
- 已创建且仅用于本项目 M004 的隔离数据库 `windops_m004_replay`，从空库在线升级到唯一 head `0026_schema_contract_alignment`。首轮真实回放在 v5 全量导入仍运行时精确写入 `378` samples，但实测 `42.3058 rows/s < 50 rows/s`，测试以 assertion 退出 `1`；该结果按真实性能失败记录，未降低门槛或记为通过。需等待资源竞争消失后在 fresh 隔离数据库复验；若仍失败则优化实际 ingest 路径。
- 回放外部门禁将 elapsed/rate 证据写在 assertion 之后，导致失败 JUnit 看不到关键测量值；已把 378 samples、总耗时、七批逐批耗时、实测速率和冻结门槛属性移到 assertion 前，保留同一硬失败条件。Ruff format/check 与 `py_compile` 通过；下一次失败或通过均可直接从 JUnit 复核性能边界。
- 对抗检查发现 full-scale verifier 原先只检查自报 `resource_actual.limits_passed=true`，未锁定 manifest `resource_policy`，也未从不可变事件摘要重算 elapsed/storage/throughput/peak；攻击者可提高门槛或重写 actual 后重算 manifest hash。现 import/evaluation verifier 接受调用方预注册的 `FullScaleResourceLimits`（生产默认冻结策略），要求策略逐字段一致；import 从 95 个事件和映射引用重算完整 actual，并校验 independent worker、95 checkpoints、event-boundary recovery、3 attempts 和正有限/不超限 wall-clock。可恢复新 job 的 wall-clock 与复用事件累计耗时分开验证，避免把合法 checkpoint reuse 拒绝。提高 import/evaluation policy 或把 wall-clock 改为 0 的重哈希负向均失败；full-scale `9/9`、Ruff、strict mypy 通过。
- evaluation verifier 进一步从 freeze 中逐一读取并复核全部 prediction 内容寻址引用、事件/farm/asset/model/point count 和 truth-free prediction artifact，要求 95 个引用与 import 事件双向闭合；从 model/prediction/freeze/fold 引用及 training/prediction resource evidence 重算 storage、281,249 点、batch/Arrow peak，并只接受正有限的 elapsed/OS peak。operational policy 必须逐字段等于冻结资源策略派生值，不能单独放宽查询/页面/回放门槛。篡改 evaluation storage actual 或重签放宽 operational policy 均失败；更新后 full-scale `9/9`、Ruff、strict mypy 通过。
- v5 完成后的第一条独立汇总脚本误假设 event summary 含 `event_label`，在产品 verifier 已成功后以 `KeyError` 退出；随后只读检查真实 schema，改从权威 `summary` 读取 45/50，并以同一当前 verifier 重跑全部硬断言通过。该项是证据汇总调用错误，不是产品导入/验证失败；未修改 manifest、数据或门槛。
- 已在同一固定摘要 MinIO 上以运行时随机测试凭据重置 `care-worker` 并附加真实 `care-m004-worker` 无删除策略，随后启动 `care-v6-full-evaluation-real-v5`，直接使用 `--use-configured-minio` 发布 prediction/report 制品。首次状态为 `running / 2/95 / error=null`，实际 worker 进程初始 HWM `229,752,832 bytes`；不会把进行中状态记为评估通过。
- 真实 evaluation 最终为 `completed / 95/95 / error=null`；当前 verifier 解析并验证所有 95 prediction 和 36 fold 后通过。manifest document/file SHA-256 为 `237adfcf...69f368` / `8ba1f187...957e34`；独立同命令重放 `replayed=true` 且文件 SHA 完全一致。summary 为 36 farm-namespaced folds、95 prediction events、281,249 points、全 95 事件核算、12 candidate pass/24 candidate fail；未把未达门槛候选伪报上线。资源为 `125.829 s`、`387,418,688 bytes`、batch peak `16,138,608`、Arrow peak `41,091,904`、OS HWM `235,524,096`、0 violation；训练 pass 扫描 5,242,948 行/4,433,004 trusted train 行。cross-farm 保持 disabled/无人工审核 ID，truth 只在 prediction freeze 后读取，frontend/JSON override=false。
- 受限 Worker 实际新增 135 个 evaluation final 对象；加既有 2 个 report 后源 CARE bucket 为 137 final/`388,001,851 bytes`，同时有 136 个 lifecycle-managed `_tmp`/`387,419,348 bytes`（135 次本轮发布 + 1 次 adapter 预检），均不进入备份。所有 top-level evaluation 引用均为 `minio://windops-care-benchmarks/...`。首个只读汇总误把 fold 的真实字段 `held_out_asset_id` 写成 `source_asset_id`，在产品 verifier 已通过后 `KeyError`；查看真实 schema 后纠正并复跑同一 verifier/硬断言通过，未改产品或证据。
- 通过同一真实 `care-m004-worker` 无删除身份把 local immutable store 的 383 个 import 对象全部镜像到 MinIO，累计 `9,270,405,441 bytes`、约 `277.88 s`；每个 key 都从内容寻址文件名取 declared SHA，并由适配器重新读取本地内容、发布、stat 最终 size/SHA metadata。之后 root 只读逐对象复核为 `383/383`。源 CARE bucket 合计 520 governed final/`9,658,407,292 bytes`，未知 final prefix 为 0；519 个 `_tmp`/`9,657,824,789 bytes` 由 7 天 lifecycle 管理且不进备份。五个隔离 DR 目标 bucket 仍精确 0 object，没有预污染恢复目标。
- 固定摘要 PostgreSQL 全量门禁首轮在 20 次/endpoint 正确 p95 采样下真实失败：dataset/event API 最大 p95 为 `621.984 ms > 500 ms`。逐请求 CPU/SQL 计量确认 SQL 仅约 14–23 ms，而全局 ORM access-control loader criteria 会为约 40 个模型在每个已显式 scope-bounded 查询上重复构造/编译；这是产品性能失败，不是数据库或环境噪音，门槛未下调。
- 仅对 `benchmark_dataset_page` 和 `benchmark_event_page` 中已经由 `benchmark_dataset_scope_clause`、已授权 `dataset_ids` 或已授权 `event_ids` 明确约束的查询设置 `skip_windops_access_control`，保留父级服务授权和所有公开 API 权限检查；数据目录/业务访问控制定向回归 `21/21`。随后全量门禁继续到内容断言时揭示跨 A/B/C 同名 `source_asset_id` 被错误合并，API 报 27 而非 36；改为统计已场域隔离的 `logical_asset_id`，并增加同 source ID、不同 farm 的可失败回归。
- 当前 PostgreSQL/API 门禁最终为 `1/1`、0 failure/error/skip：导入 `1,571` 与 evaluation `404` 条权威记录均幂等重放，数据库精确为 95 file/event/quality、1,285 mapping、3 model、36 evaluation、95 result、270 metric、36 logical asset、45/50 和 5,242,948 行，CARE Timescale signal rows=0；受限主体仍 403。5 个 endpoint 各 20 样本 p95 为 `42.656/35.941/33.621/98.068/344.998 ms`，最大 `344.998 < 500 ms`；最大响应 `127,879 < 524,288 bytes`。JUnit `.artifacts/care-v6/m004/postgres-fullscale-final.xml` SHA-256 `033F1E31...D266`。
- 对本任务专用 `windops_m004_replay` 先核对唯一业务外连接为 TimescaleDB scheduler，再精确 force-drop/recreate，空库在线升级至唯一 `0026` 且 `alembic check` 无漂移。fresh 真实回放门禁 `1/1`、0 skip：7 批共 378 samples 用时 `6.116893 s`，逐批 `1.109486/0.969865/0.723343/0.962890/0.807959/0.691058/0.852292 s`，实际 `61.796 > 50 rows/s`；7 prediction、异常事件 1 Alarm/Mission/Decision、正常 0 告警、重启/同 run 幂等/新 run 隔离/truth-free/UI/API/export 全链通过。先前 42.3058 是全量导入竞争下的真实失败，未被覆盖或降门槛；隔离结果表明无需产品 ingest 改写。JUnit `.artifacts/care-v6/m004/postgres-replay-final.xml` SHA-256 `5CDDBDC5...8BB76`。
- 真实 DR 的首个产品运行在导出 snapshot 后失败：`_snapshot_query` 未给 `psql` 加 `--quiet`，事务 command tag 被误计为多个 Alembic revision；增加 quiet 合同和可失败回归后 backup/DR `11/11`。下一轮生成完整 9.66 GB bundle 并通过清单验证，但 PostgreSQL 恢复在写 MinIO 前失败，真实错误为 PG17 客户端向 PG16.14 服务端发送 `SET transaction_timeout = 0`；目标单事务完整回滚、五个目标 bucket 保持 0，没有把失败演练记为通过。
- 根因收敛为镜像客户端主版本未与固定服务端供应链绑定。`backend/Dockerfile` 现从 release policy 固定的 `timescale/timescaledb-ha@sha256:df8eaa04...bb2be` 阶段复制 `pg_dump/pg_restore/psql` 16，policy/workflow/OCI labels/artifact verifier 同时锁定 client image digest 和 exact major `16`；部署与备份 runbook 明确禁止 PG17→PG16 恢复。backup/DR/container/deployment/release 回归 `51/51`，Ruff/strict mypy/Prettier 通过。最终镜像 content ID `sha256:d691cd01...0021e`，三个客户端均实测 `16.14`，UID/GID `10001:10001` 且标签绑定上述 digest/major。
- 最终真实演练使用源数据库只读角色、源五 bucket List/Get-only 用户、隔离目标数据库和目标五 bucket List/Get/Put-only 用户，双方均无 Delete；一次性身份只存活于演练进程并在 `finally` 清理。一次预启动误用入口不支持的 `postgresql+psycopg://` 方言，在任何 bundle/恢复写入前正确失败，凭据清理且目标仍空；改用标准 `postgresql://` 后原门槛执行，没有修改产品或放宽验收。
- 最终 DR `status=verified`，RTO `1,387.397 s`，schema `0026_schema_contract_alignment`，artifact `522 = 1 PostgreSQL + 1 safe config + 520 MinIO`；evidence `.artifacts/care-v6/m004/dr-real/dr-drill-evidence-20260827T033350Z.json` SHA-256 `C89E93D7...22211`，bundle `windops-backup-20260827T031043Z` manifest SHA-256 `6132AB37...61BD9`。21 个源/目标数据库行数不变量逐表完全一致，其中 dataset/file/event/feature/quality/evaluation/result/metric 为 `1/95/95/1285/95/36/95/270`。
- 独立 MinIO 复核不采信成功文本：源治理 final 精确 `520 / 9,658,407,292 bytes`，生命周期 `_tmp` 精确 `519 / 9,657,824,789 bytes` 且 0 个进入 bundle，未知前缀 0；目标 CARE 精确 `520 / 9,658,407,292 bytes`，其他四目标 bucket 均 0，520/520 对象 size 和恢复的 SHA-256 metadata 与 manifest 一致、目标 `_tmp` 为 0。源/目标 policy SHA-256 为 `6FCDA592...4DD4B` / `B4D80CFD...24A1F`，真实 DeleteObject 尝试 exit 1 且 660-byte 抽样对象仍存在。
- 当前剩余：对当前最终树执行 build/lint/typecheck/unit/integration/PostgreSQL/E2E/smoke/migration/security 全局验证；随后完整需求复查、对抗复查和连续两轮 Final Audit。
- 最终全局静态/供应链首批验证：Prettier、ESLint、TypeScript、Ruff format/lint（192 files）、strict mypy（92 source）、`uv lock --check`、container requirements lock、Compose config、唯一 head/声明 `0026` 和完整 Alembic offline render 均通过；pip-audit 与 pnpm production audit 均为 0 known vulnerability。
- Bandit 首轮真实发现 DR `current_database_invariants` 用 f-string 从内部 tuple 拼表名，报 B608 Medium/Low-confidence；没有加扫描豁免，而是改为显式静态 21 表 SQL 常量并让测试锁定完整 query/label/table。backup+DR `11/11`、Ruff/mypy 通过，Bandit 全 `src` 复跑 0 issue；该安全发现已修复，不把首轮失败覆盖成通过。
- 最终后端全量首轮业务测试为 `391 collected / 367 passed / 24 受控 external skips / 0 failure`，总覆盖 `75.7506%`，但覆盖预算真实拒绝 `api/model_registry.py 44.28% < 48%`；没有降低 floor。先补齐模型列表的空态、筛选和预测筛选行为后定向仍为 `47.761%`，确认还差真实路由覆盖；随后增加模型制品预签名的完整 API 行为，验证模型专用 bucket/prefix、content type、幂等回放头和响应完全稳定。最终 `test_model_runtime.py` 为 `8/8`，该模块定向覆盖 `101/201 = 50%`，Ruff format/lint 通过；下一步重跑完整后端 coverage/budget 生成当前树最终证据。
- 当前树完整后端 coverage 重跑通过：JUnit `393 collected = 369 passed + 24 受控 external skips`、0 failure/error，`1,108.097 s`；总行覆盖 `13,535/17,852 = 75.8178%`，`api/model_registry.py` 为 `101/201 = 50.2488%`，全部关键模块 floor 通过。机器生成的完整 `HEAD` tracked diff 加 26 个未跟踪 Python source 的零上下文 diff 后，changed executable coverage 为 `74.65% > 65.5%`；预算脚本退出 0。JUnit/coverage/diff SHA-256 分别为 `CC47543D...5E946E`、`07C8476B...98BDD`、`FCB00BEE...C204B2`。唯一 warning 仍是既知 `.pytest_cache` Windows ACL；独立 `--basetemp` 与证据写入完整，不影响结果。
- 最终真实 PostgreSQL CI 同构门禁首轮在空库 upgrade/current/check 全部通过后发现并发幂等回归：同一 evaluation input identity 或同一 run/event 结果、但重试携带不同建议 row ID 时，服务把 row ID 错误纳入 immutable provenance，第二请求得到 `ConflictError`，套件因此真实失败且未记为通过。修复仅从两处内容身份比较排除客户端建议 ID，仍逐字段比较 dataset/model/protocol/版本/阈值/subject 或完整事件结果内容；数据库唯一 logical identity 和 advisory lock 不变，真实内容变化仍 409。SQLite metadata 回归 `3/3`、原 PostgreSQL 并发复现 `1/1`、Ruff/mypy 通过；下一步从头重跑整个 PostgreSQL 门禁。
- 全新 `windops_m004_final_global_v2` 隔离数据库从空库升级后，当前代码的 CI 同构 PostgreSQL 门禁最终 `20/20`、0 failure/error/skip、`105.078 s`，并在套件后再次保持唯一 head `0026_schema_contract_alignment`、`alembic check` 无漂移。真实 10 万级 HTTP 场景固定 SQL `8/8/9/9`，最差 E2E p95/p99 `195.636/332.550 ms`、最大 `380.422 ms`，最大响应 `133,327 bytes`、最大 Python peak `1,653,498 bytes`，均低于既有门槛；JUnit SHA-256 `E29DE270...E961`。首轮失败保留为发现/修复证据；下一步继续 E2E/smoke/container，并在最终源码稳定后重跑全后端 coverage。
- 当前前端生产路径再次通过：`pnpm test:e2e` 完成生产构建并通过 Chromium `6/6`，mock 模式下 real-only 用例按合同精确 `1` skip；`pnpm test:start-smoke` 的 demo 启动与无合法生产配置 fail-closed 均通过。此前同一最终前端源码的 coverage 为 `143/143`，V8 line/branch/function `90.34% / 51.27% / 33.09%`，production bundle `92 chunks / 2,598,335 bytes / max 645,279 bytes`；后续 Python 修复未改变前端源码，E2E 已重新构建当前树。
- 按受保护发布策略以固定 PG16 客户端阶段重建 `windops-backend:care-m004-final-20260827`，当前 content ID `sha256:d497a1ab...122a84`，release/commit/source 标签绑定 `care-m004-final-20260827` / `e70788b8fe040603fb3be718568db9da44eacbb1` / `https://github.com/local/wind-agent`；linux/amd64、UID/GID `10001:10001`、六个入口、read-only/tmpfs/cap-drop/no-new-privileges、迁移/lock hash、`pip check`、无 pytest 及 `pg_dump/pg_restore/psql 16.14` 全部通过。容器本地证据 SHA-256 `3F487F73...527785`；没有伪造 registry push、签名、attestation 或 SBOM 外部证据。
- 当前镜像 release smoke 首次由本地验证 harness 错把无 Docker Healthcheck 的固定 Neo4j 镜像当成带 `.State.Health`，在应用启动前失败并完整清理临时容器/网络/端口；只读检查确认 `Healthcheck=null` 后，改用镜像内 `cypher-shell RETURN 1` 做依赖 readiness，未改变产品或验收门槛。全新 `windops_m004_image_smoke_v2` 空库上由当前镜像自身执行 Alembic `0001→0026`，随后在只读、非 root、cap-drop、no-new-privileges 环境通过 API health/readiness 和镜像 Docker healthcheck；临时 Neo4j/API/网络均清理且端口 `18027` 释放。证据 `release-image-smoke.json` 为 `status=passed`、镜像 ID 精确为 `sha256:d497a1ab...122a84`，SHA-256 `B1CF08D5...33809`。
- 为验证 PostgreSQL 并发幂等修复后的 CARE 权威链，创建三个新的本项目隔离库 `windops_m004_final_care_offline/replay/fullscale`，均从空库在线升级 `0001→0026`、`current=head` 且初始 `alembic check` 无漂移。当前代码的真实 offline/fullscale/replay 专项分别 `1/1`、`1/1`、`1/1`，全部 0 failure/error/skip；JUnit SHA-256 为 `8ABF3D16...FDBCA` / `859FE234...FB958` / `487AC2EB...DA052`。fullscale 精确新建 `1,571 + 404` 条记录、270 metrics，最大 API p95 `330.274 < 500 ms`、最大响应 `127,879 < 524,288 bytes`；replay 378 samples 用时 `6.220004 s`、`60.772 > 50 rows/s`，7 predictions、异常 1 Alarm/Mission/Decision、正常 0 告警，并再次通过 restart/幂等/新 run/truth/API/UI/export/ShareAlike 全链。三库套件后 revision 仍精确 `0026`，fullscale `alembic check` 仍无漂移。
- 当前最终静态/供应链复验通过：Prettier、ESLint、TypeScript、Ruff format/lint（192 files）、strict mypy（92 source）、Bandit（0 finding）、`uv lock --check`、container requirements 可重现检查、pip-audit、pnpm production audit、Compose config、唯一 Alembic head/四份声明 `0026`、完整 offline migration render 和 `git diff --check` 均退出 0；Bandit 仅报告现存且逐行有对应安全合同的 `nosec`/注释解析 warning，没有 finding。一次探查脚本帮助时误对无 argparse 的 `prepare_real_release_smoke.py` 传 `--help`，其在任何环境/制品写入前按合同因缺 `WINDOPS_RELEASE_SMOKE=1` 失败；分类为验证命令调用错误，未计为产品失败或 smoke 通过。
- 以当前镜像 content ID 作为本地不可变候选渲染最终 Kubernetes 清单，deployment policy 为 `status=passed`：14 resources、5 workloads（API/worker/outbox/migration/backup），镜像/annotations/env 全部绑定 `sha256:d497a1ab...122a84`、release ID 与完整 commit；受限 pod security、外部 Secret 引用、资源边界、探针/可用性、目标受限网络策略和 `windops-encrypted-backup` 均通过。base/rendered/report SHA-256 为 `BF955F25...7325A` / `FC6CF055...E6D33` / `A810FBAA...FFF9A`；该本地证据不替代 registry digest、集群 API dry-run、签名/attestation 或生产准入证据。
- 源码稳定后的最终完整后端 coverage 已以单次进程封口：`393 collected = 369 passed + 24 受控 external skips`、0 failure/error、`1,133.931 s`；总行覆盖精确 `13,535/17,852 = 75.8178355%`，`api/model_registry.py` 为 `101/201 = 50.2487562%`，全部关键模块 floor 与全局 68% floor 通过。完整 `HEAD` tracked diff 加 26 个未跟踪 Python source 生成 46,045 行机器 diff，changed executable coverage `74.65% > 65.5%`，预算脚本退出 0。最终 JUnit/coverage/diff SHA-256 为 `EF6DD48F...A0BF2` / `D3EF8FEA...5DA8A` / `97E46CA6...CBECB`。唯一 warning 仍为既知 `.pytest_cache` Windows ACL；独立 `--basetemp` 与两份最终证据均完整。首次 PowerShell 解析 coverage JSON 未使用 `-AsHashtable`，因 Coverage.py 含空键而正确报错；改为只读 hash-table 解析后取得上述精确机器计数，分类为证据解析命令错误，不是测试或覆盖失败。
- 最终全局验证已闭合：当前稳定源码的前后端构建、格式、lint、类型检查、安全/依赖审计、393 项后端全量覆盖门禁、20 项真实 PostgreSQL CI 同构门禁、3 项 fresh CARE PostgreSQL 链、Chromium 6/6、启动 smoke、当前不可变镜像 runtime/release smoke 和 14-resource deployment policy 均为 PASS；因此进入完整需求复查，但 M004 在收敛复查和两轮审计完成前保持 `IN_PROGRESS`。
- 阶段切换时再次完整读取 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md`、本文件与 1,067 行 CARE 需求；写入前行数/SHA-256 分别为 `459/25B10F39...AE06D`、`319/53C7331B...5DA0F`、`616/7310FF75...FBB2`、`2050/81B17B94...7EBA9`、`1067/5517AE5C...0C380`，准确状态仍为 13 DONE、M004 IN_PROGRESS、Final Audit `0 / 2`。
- First Full Recheck 直接以当前代码读取真实 v5 不可变制品：full import verifier 在 `16.7 s` 内重算 A22→C58→B15、95 events、36 assets、45/50、`5,242,948` rows，manifest hash `a0c89223f33ca55277f0635b654c7b1b292d3642065fa35e9c97eefd30d8f910`；evaluation verifier 重算 36 folds、95 predictions、`281,249` points、12 candidate pass/24 fail，manifest hash `237adfcf63a1d768653299f9dccd714c3b972f0457b0040ad581e2c8ae69f368`。
- 同轮当前 verifier 复核 contract/quality/scoring/replay/anomaly 制品均通过，但发现 `.artifacts/care-v6/pipeline/pipeline-contract.json` 仍是 row-group/layout v1 前的旧证据，不能把旧证据继续当当前合同。已用当前 `windops-care-pipeline contract` CLI 分别重新生成主/重复制品；两份均经当前 verifier 通过且字节完全一致，长度 `2,653` bytes、SHA-256 均为 `41A4AE4C15C3186FCF90A11CA6CB2D207A93BFF2A7B15363D037BA19AB362C9B`。这是证据漂移修复，没有源码变化；完整复查保持进行中并将再次联合验证全部核心合同。

#### First Full Requirement Recheck — PASS (2026-08-27 13:40 +08:00)

- 从 Audit 第一项到最后一项重新验收 14 个 CARE Issue：C001 的只读双 hash/101 CSV/全列闭合；C002 的原值与 mask、状态/单位/缩放/匿名时间；C003 的官方等价评分与真值隔离；C004 的 run/asset/time/sequence/watermark 隔离；C005 的正式 anomaly/预测来源/状态机/服务器门槛；H001 的独立 Worker、宽表 Parquet、row-group、MinIO/恢复；H002 的十类实体、RegisteredModel、`0026`、真实 PostgreSQL 并发；H003 的 A0/A24 双事件；H004 的双模型同协议不可变评估；H005 的异常触发/正常抑制真实回放；M001/M002 的有界真实 API/UI/诊断；M003 的权限/导出/ShareAlike/精确清理；M004 的 A22→C58→B15 全量、场内 36 folds、资源/性能/DR/发布门禁，全部存在当前实现与客观证据。M004 仅剩本 Goal 明确要求的对抗复查和两轮程序性收敛，因此仍不提前标记 DONE。
- 第 16 节 17 项阶段 0 门槛逐项关闭：`16-01` ZIP+101 文件不可变清单；`16-02` 81/252/952 唯一映射；`16-03` statistics/bare Avg/event ID；`16-04` B/C 零段与状态；`16-05` 缩放/匿名时间；`16-06` 原值/mask；`16-07` 冻结评分；`16-08` prediction truth 隔离；`16-09` 每风机年禁用；`16-10` replay 六维隔离；`16-11` anomaly 无伪 RUL；`16-12` prediction 告警与策略状态；`16-13` 服务器不可变发布门槛；`16-14` 独立宽表 Worker；`16-15` CARE MinIO/生命周期/ACL/备份；`16-16` RegisteredModel/ACL/catalog/migration；`16-17` SHA/来源/changes/CC BY-SA。
- 第 18 节 15 项总体验收逐项关闭：`18-01` 双校验/清单；`18-02` 95/36/45/50；`18-03` 全信号映射；`18-04` 六类显式语义；`18-05` 源只读/派生可追溯许可；`18-06` 特征与真值隔离；`18-07` 评分黄金可复现；`18-08` 正常/失败/不可评分全核算；`18-09` 宽表且 Timescale 全量行 0；`18-10` anomaly/predictive 兼容；`18-11` replay 隔离；`18-12` 告警预测/原证据；`18-13` 服务器策略/门槛；`18-14` 三处 UI 权威一致；`18-15` 对外归属/DOI/license/changes/ShareAlike。
- 当前六份核心合同联合复核全部 PASS，主/重复文件字节一致：contract `3DB92651...EE916`、quality `315E2288...6937F`、scoring `1A2164B6...FE7C5`、replay `58AC9E3F...7A72AB`、anomaly `B293162C...CCA79B`、pipeline `41A4AE4C...2C9B`。没有忽略旧 pipeline evidence；它已按当前 layout v2 真正再生并验证。
- 原始数据边界再验：ZIP 为 `5,503,439,673 bytes`，MD5 `2547B58C21AC8C242D13232860CF500C`、SHA-256 `CA61379E98956D891041AD45C885109BD8A14199FDE0688D0184A11C2D4194F1`；解压目录 `103 files / 19,987,485,991 bytes`，最新文件写时仍为 `2025-07-09T18:10:09.6999777+08:00`，早于本任务。未修改、移动、重命名或删除仓库外源数据。
- 假完成/边界机器扫描：相关源无 `pass`/ellipsis/NotImplemented stub；TODO/FIXME/HACK/placeholder 命中均为“拒绝 placeholder”的生产配置或负向测试语义；仅 3 个真实 PostgreSQL 文件有显式 environment `skipif`，且本轮均已以 `WINDOPS_FAIL_ON_SKIPPED=1` 在 fresh 数据库 0-skip 运行。CI 无 `continue-on-error/allow_failure`；Git 未跟踪 CARE raw/Parquet/CSV，`.artifacts` 被显式忽略；CARE 前端无原始目录或 Parquet 引用；每风机年指标仍明确 disabled。
- 完整复查发现并关闭一项文档遗漏：阶段 5 要求实际发布说明，旧 runbook 只有证据保留指令。现已在 `docs/runbooks/care-full-scale-operations.md` 增加 `Validated release candidate (2026-08-27)`，准确记录候选镜像身份、全量/评估性能、PostgreSQL/API/回放、DR、cross-farm 禁用及受保护 registry/signing/attestation/SBOM/cluster 门禁；Prettier 与 `git diff --check` 通过。没有用本地 content ID 冒充外部 registry 或生产准入证据。
- 复查结论：没有未登记的功能缺口、placeholder、stub、弱化断言、未接通前后端或遗漏 Required Changes/Acceptance Criteria；进入 Adversarial Review。此结论不增加 Final Audit 计数。

#### Adversarial Review — PASS (2026-08-27 13:47 +08:00)

- 以严格拒收视角执行 21 个后端专项文件，覆盖数据合同/质量/评分/回放/anomaly/Parquet/import/evaluation/online/metadata/catalog/governance/full-scale、幂等、访问控制、模型运行时、备份/DR 和生产安全配置；`177/177`、0 failure/error/skip、`261.438 s`。JUnit `.artifacts/care-v6/m004/adversarial-backend.xml` 为 `25,392 bytes`，SHA-256 `44712AB40FEB886FFEC2D0BD29C49E61823B38BB509E21113F5767C892D1CCF2`；唯一 warning 是既知 `.pytest_cache` Windows ACL，独立 basetemp/JUnit 均完整。
- 前端/网关对抗专项 `28/28`、0 failure/skip：POST 传输重试保持完全相同的 idempotency key/body；401/403/503/network 分型；CARE 页面只用有界生产 API、从不取 raw CSV；data/model/diagnosis 的 disabled/loading/empty/error/stale/permission/repeated/responsive 状态；生产 fixture/模拟 socket/客户端 capability spoofing/错误镜像 digest/弱配置全部失败关闭。
- `invalid input`：未知/缺失/重复/歧义映射、坏 hash/schema/state、越界资源策略、跨场开启、跨 run 窗口、缺 anomaly 字段、错误 threshold/protocol、非法 secret/host/body 均被拒绝；没有修改数据或放松上限。
- `empty/stale/repeated`：有界空页/空曲线/空诊断可观察；分页 cursor 和 durable watermark/heartbeat/lease 不混用旧状态；same-run、registration、prediction、export 和 POST retry 保持单一副作用，不同内容复用 identity 仍冲突。
- `network/API/permission`：对象存储/数据库失败保持 pending/rollback 或 terminal fail-closed；前端区分网络/认证/授权/后端故障；benchmark、truth、export、cleanup 和跨租户 scope 均由服务器控制，普通 Worker 无 DeleteObject。
- `concurrency/restart/partial failure`：真实 PostgreSQL 并发唯一身份已由最终 global 门禁 20/20 证明；专项再次覆盖断点、乱序、迟到、stale lease、同 run 重启、新 run 隔离、事件边界取消、三次有限重试、不可变 publish 和失败后无 aggregate/partial/错误指标。
- `production configuration`：生产必须 TLS、外部 secret、Sites delegation、真实后端 release identity 与 approved digest；demo/fixture 不能渗入 production。镜像/迁移/DR/MinIO 策略和 Kubernetes 清单在 Final Global Validation 已用固定身份验证。
- 对抗复查未发现新的 Critical/High/Medium。文档发布说明修复后 `git diff --check` 仍退出 0（仅 Windows autocrlf warning）；进入 Final Audit Pass #1，计数保持 `0 / 2`。

#### Final Audit Pass #1 — PASS (2026-08-27 13:51 +08:00)

- 独立从文件重新解析而非采信 Progress 文本：最终后端 JUnit `393 = 369 passed + 24 controlled external skips`、0 failure/error；fresh PostgreSQL CI `20/20`、fresh CARE offline/fullscale/replay 各 `1/1` 且均 0 skip。对应 SHA-256 为 `EF6DD48F...A0BF2`、`E29DE270...AE961`、`8ABF3D16...FDBCA`、`859FE234...FB958`、`487AC2EB...DA052`。
- coverage JSON 重新机器断言为 `13,535/17,852 = 75.8178355%`，`api/model_registry.py 101/201 = 50.2487562%`；SHA-256 `D3EF8FEA...5DA8A`。最终工作树机器 diff 证据 SHA-256 `97E46CA6...CBECB`；后续只有 Progress、pipeline evidence 和 runbook 文档变更，没有后端/前端源码漂移。
- 容器/runtime、release smoke、deployment policy 和 DR JSON 全部重新结构化断言：同一 image content ID `sha256:d497a1ab...122a84`、non-root `10001:10001`、PG clients 16、smoke `passed`；deployment `passed / 14 resources / 5 workloads`；DR `verified / 522 artifacts / schema 0026 / RTO 1,387.397 s / source-target isolated / overwrite=false`。综合 evidence parser 最终输出 `FINAL_AUDIT_EVIDENCE_PASS`。
- CI/release 工作流现有 `32` 个 `uses:` 全部是本地 action 或完整 40 位 SHA，0 unpinned、0 `continue-on-error/allow_failure`；存在 `production-release` protected environment 与两处 fail-on-skip 门禁。
- 唯一迁移 head verifier 为 `0026_schema_contract_alignment`；一次只读探针错误假设固定镜像含 `postgres` role 而得到 FATAL，改从容器声明读取非敏感用户名 `windops` 后，三个 fresh CARE 验收库均精确返回 `0026`。这是审计探针假设错误，不是产品、迁移或数据库失败。
- 运行态只存在有本项目精确 label 的 M004 PostgreSQL/MinIO 两个保留服务，无 release-smoke 临时容器或项目网络；二者仍供第二轮独立只读审计使用，最终按用户先前“停止服务”要求只 stop、不删除。`git diff --check` 退出 0。
- Pass #1 未发现新的 Critical 或 High，收敛计数从 `0 / 2` 增至 `1 / 2`。M004、Stage 5 和 Final State 继续保持未完成，进入侧重点不同的 Pass #2。

#### Final Audit Pass #2 — PASS / Completion (2026-08-27 14:00 +08:00)

- 以安全、供应链和不可变运行身份为独立侧重点复验当前树：项目 `pnpm format:check`、ESLint、TypeScript 全部通过；后端 Ruff format/check（192 files）、strict mypy（92 source）、Bandit 0 finding、`uv lock --check`、container requirements 重现、pip-audit 与 pnpm production audit 均通过，Compose config 有效。Bandit 仅打印已由对应安全合同锁定的注释/nosec 解析 warning，没有 finding。
- 首次直接执行 `prettier --check .` 因扫描到既知不可访问的 `backend/.pytest_cache` 得到 EPERM；立即改用仓库声明的 `pnpm format:check` 精确作用域后通过。该失败属于验证命令越过项目忽略边界，不是格式或产品失败，没有删除/改 ACL/忽略真实文件。
- scoped secret scan 只命中 3 个文件：两个安全/垂直切片测试的合成拒绝字符串，以及 `fixture://` 路径中单词 `task-` 的 `sk-` 子串；遮蔽复核确认没有真实 API key、云 access key、GitHub token 或私钥。本轮未输出或提交凭据。
- 当前不可变镜像在 fresh `docker run --rm --read-only --cap-drop ALL --no-new-privileges` 中再次通过 UID/GID `10001:10001`、`pg_dump/pg_restore/psql` 16 和六类入口存在性检查。首次把 `windops-api --help` 当无副作用帮助命令时，该入口按设计实际启动服务并因未注入数据库而失败；改为 `command -v` 后完整探针退出 0。此为审计 harness 误用，不是镜像/runtime 失败；容器 `--rm` 未留残留。
- 当前 full import/evaluation verifier 再次解析全部不可变引用并在 `15.106 s` 通过：95 events、`5,242,948` rows、36 folds、95 prediction artifacts，manifest hash 仍为 `a0c89223...d8f910` / `237adfcf...69f368`。前两次脚本把相对 `output_root` 直接传给要求已 resolve 路径的 verifier，因 harness path identity 失败；使用 `.resolve()` 后无源码或制品改动即通过，分类为调用错误而非产品失败。
- Pass #1 的后端/coverage/diff/PostgreSQL/container/smoke/deployment/DR 证据 SHA 全部保持不变；对抗 JUnit 仍为 `44712AB4...1CCF2`，新 pipeline contract 仍为 `41A4AE4C...2C9B`；实际镜像 ID 仍精确为 `sha256:d497a1ab...122a84`，`git diff --check` 为 0。
- Final Audit Pass #2 没有发现新的 Critical 或 High；连续收敛计数达到 `2 / 2`。`AUDIT_REPORT.md` 顶部结论和 14 项活动登记已在客观验收后更新为 COMPLETED/DONE，没有改写历史审计区。
- 按用户此前“停止服务”指令，在停止前逐一核对精确名称和 `windops.project=wind-agent` 标签，只执行 `docker stop windops-care-m004-minio-20260827 windops-care-m004-pg-20260827`。两容器的 Docker AutoRemove 配置使容器记录随 stop 自动消失；没有执行 `docker rm`、volume 删除或文件删除。项目内不可变证据和 `.artifacts/care-v6/m004/minio-source-data` 保留；项目运行容器为 0，`55448/55900/55901` LISTEN 均为 0，其他项目容器/卷未操作。

#### Completion Gates — MET

| Gate | Result | Final evidence |
|---|---|---|
| A — Coverage | PASS | Audit 顶部 14/14 为 DONE；0 TODO/IN_PROGRESS/未登记问题 |
| B — Critical / High | PASS | 5 Critical + 5 High 全部 DONE；剩余 0 |
| C — Medium | PASS | 4 Medium 全部 DONE；剩余 0、无外部 blocker |
| D — Evidence | PASS | 每项均有实现、自动测试、真实 PostgreSQL/MinIO/浏览器/制品证据和持久化日志 |
| E — Recheck | PASS | First Full Requirement Recheck 从 C001 至 M004、需求 16/18 逐项重验 |
| F — Global Validation | PASS | 当前稳定源码的 build/lint/typecheck/unit/integration/PostgreSQL/E2E/smoke/migration/security PASS |
| G — Convergence | PASS | Adversarial PASS；连续 Final Audit `2 / 2`，两轮均无新 Critical/High |
| H — Persistent State | PASS | Audit 与本文件顶部已同步为真实最终状态；服务停止事实已记录 |

最终结论：14 个 CARE Issue 全部完成；Stage 0A/0B/0C、1、2、3、4、5 全部 PASS；First Full Recheck、Adversarial Review、Final Global Validation 与 Final Audit `2 / 2` 全部 PASS。受保护 registry digest/signing/attestation/SBOM/cluster admission 仍按发布流程失败关闭，不被本地 content ID 伪装为已完成的外部证据，且不影响本任务定义的本地完成门槛。

---

# 历史执行记录：2026-08-21 已完成审计

## Historical Metadata

Project:  
`OpenVigil / wind-agent`

Audit Source:  
`AUDIT_REPORT.md`

Execution Rules:  
`EXECUTION_GOAL.md`

Started:  
`2026-08-19 11:14 +08:00`

Last Updated:  
`2026-08-21 11:47 +08:00`

---

# 1. Overall Status

Current Phase:  
`COMPLETED`

## Statistics

| State          | Count |
| -------------- | ----: |
| Total          |     0 |
| DONE           |     0 |
| IN_PROGRESS    |     0 |
| TODO           |     0 |
| BLOCKED        |     0 |
| NOT_APPLICABLE |     0 |

## Severity Remaining

| Severity | Count |
| -------- | ----: |
| Critical |     0 |
| High     |     0 |
| Medium   |     0 |
| Low      |     0 |

## Current Work

Current Issue:  
`NONE — 当前 AUDIT_REPORT.md 活动问题清单为空`

Current Objective:  
`独立重审已完成；没有仍需处理的 Critical / High / Medium / Low。`

Next:  
`NONE`

---

# 2. Convergence

Full Audit Recheck:  
`PASS (2026-08-21 11:44 +08:00；不采信 DONE，重新按当前代码完成 clean build、真实跨层、全量回归和专用 PostgreSQL 门禁)`

Adversarial Review:  
`PASS (2026-08-21 11:44 +08:00；删除 build/产物检查、缺钥、错钥、失败/取消/运行中/wrong-SHA 均有真实或合同负向证据)`

Final Global Validation:  
`PASS (2026-08-21 11:44 +08:00；当前树 build/coverage/unit/integration/真实 PostgreSQL/mock+real E2E/start smoke/format/lint/typecheck/migration/security 全通过)`

Final Audit Pass:  
`2 / 2`

Final State:  
`COMPLETED`

---

# 3. Current Independent Re-audit (2026-08-21 11:44 +08:00)

The regenerated `AUDIT_REPORT.md` supersedes every earlier completion claim and issue register. Current active issue count is exactly `0`; all sections below this one are retained only as historical implementation evidence and do not override the top-level status.

Independent evidence for this re-audit:

- H-003 was verified from a root with no `dist`: `pnpm run build` generated `dist/server/index.js`, then the newly generated production Worker completed real HTTPS FastAPI/PostgreSQL/Chromium `1/1` with `503 → 200 → 200` assertions.
- Release pipeline/gate tests `33/33`, Node production contracts `26/26`; deleting the build or artifact check fails the static contract, missing shared secret exits `1`, and a one-sided wrong secret produces real `401` responses.
- Full backend JUnit is `275 / 0 failures / 0 errors / 18 ordinary external skips`, coverage `73.03%`, changed executable coverage `70.48%`; the skipped PostgreSQL subset was separately executed under `WINDOPS_FAIL_ON_SKIPPED=1` as `17/17 / 0 skip`.
- Frontend coverage `135/135`, mock Playwright `6 passed + 1 expected real-mode skip`, real Playwright `1/1`, standard start smoke, TypeScript/ESLint/Prettier/Ruff/mypy/Bandit, dependency audits, migration and Compose validation all passed.
- The remaining external release-environment test was not counted as passed locally: it requires protected production Redis/MinIO/Neo4j/LiteLLM/model endpoints. The release workflow explicitly enables it under `WINDOPS_FAIL_ON_SKIPPED=1`, so release qualification remains fail-closed on that external gate.
- Evidence SHA-256: backend JUnit `8DEE0D1E...183BB`, coverage `24FC7611...ACCAE4`, PostgreSQL JUnit `986D6321...EE212`.
- The exact audit PostgreSQL container was stopped and auto-removed; audit FastAPI/Worker processes and ports were released; the pre-audit `dist` was restored. No unrelated service was touched.

## 3X. Historical H-003 Completion Gates A-H (2026-08-21 11:20 +08:00)

Status: `PASS — COMPLETED`

This historical section records the earlier H-003 completion review. The top-level fields and section 3 above are the current Source of Truth.

| Gate | Result | Current evidence |
| ---- | ------ | ---------------- |
| A — Coverage | PASS | 机器解析 `AUDIT_REPORT.md` 得到精确唯一 Issue `H-003`；Progress 活动表中它精确出现一次且为 `DONE`，统计为 `1 total / 1 DONE / 0 TODO / 0 IN_PROGRESS / 0 BLOCKED`，无未登记项。 |
| B — Critical / High | PASS | Critical remaining `0`、High remaining `0`；唯一 High H-003 已实现并验证。 |
| C — Medium | PASS | 当前报告无 Medium，remaining `0`，无外部 blocker。 |
| D — Evidence | PASS | clean no-dist 原生 build + artifact check + 真实 `503→200→200` 为 `1/1`；删除 build/删除 dist check 合同失败；缺钥两端失败关闭、错钥真实请求 `401`；release 同 SHA 仅 completed/success 通过。最终 backend `275/0/0/18`、PostgreSQL `17/17/0 skip`、coverage `73.03%` 与三份 SHA-256 证据无漂移。 |
| E — Recheck | PASS | First Full Recheck 已从 H-003 Required Changes 到全部 Acceptance Criteria 重新验收，过程中发现并修复 artifact existence 与 release status 两个缺口，之后回归通过。 |
| F — Global Validation | PASS | 当前最终树的 build、coverage、unit/integration、固定摘要 PostgreSQL、mock+real E2E、标准 start smoke、format/lint/typecheck、migration/security/container 均通过。 |
| G — Convergence | PASS | 两轮不同侧重点 Final Audit 均未发现新 Critical/High，计数 `2 / 2`。 |
| H — Persistent State | PASS | 本次原子更新已同步 Last Updated、Phase、Current Work、Convergence、活动 Issue、Gate 表和 Final State；状态为真实当前树的 `COMPLETED`。 |

Final stop state: ports `3000/4179/4180/8443/55432`、项目 runtime 进程、`windops.project=wind-agent` 运行容器、临时 TLS 均为 0。固定摘要 PostgreSQL 容器已按精确名称/标签停止并因 `--rm` 删除；本地验证镜像保留但不是服务。可恢复的旧 `dist` 审计备份位于被 Git/ESLint 忽略的 `.artifacts/h003-clean-runner/node_modules/preexisting-dist`，未删除用户数据。

## 3W. Final Audit Pass #2 (2026-08-21 11:15 +08:00)

Status: `PASS`

- 阶段切换后重新完整读取四份控制文件，持久化状态精确恢复为 H-003 `DONE`、Final Audit `1/2`、Final State `OPEN`；本轮采用与 Pass #1 不同侧重点。
- Node 生产 runtime + API client 幂等/transport retry `20/20`、0 fail/skip；生产模式失败关闭、后端 release mismatch、认证/授权/网络错误分类、轮换 method scope 和幂等 key/body 复用均通过。
- 后端生产配置与平台配置安全合同 `26/26`、0 fail/skip；Alembic 当前静态声明保持唯一 head `0023_bounded_weather_selection`，`verify_migration_head.py` 通过。
- 静态交叉复核确认活动 Audit register 仅 H-003、Progress 为 `1 DONE / 0 TODO / 0 IN_PROGRESS / 0 BLOCKED`；CI build/artifact/real 顺序、17 个 action 固定 SHA、无 `continue-on-error`、单一 `WINDOPS_GATEWAY_DELEGATION_SECRET`、两端缺钥失败关闭及 release completed/success 均成立。
- 三份最终全量证据哈希与 Pass #1 完全一致；覆盖率预算脚本重新读取当前 JSON 后 global `73.03%` 与全部 critical-module floor 通过，完整工作树 changed executable `70.48%` 的已存证据无漂移。
- 端口 `3000/4179/4180/8443/55432`、项目 runtime 进程和 `windops.project=wind-agent` 运行容器继续为 0。
- 未发现新的 Critical / High；连续两轮收敛成立，Final Audit Pass 更新为 `2 / 2`。Final State 暂保持 `OPEN`，进入 Completion Gates A-H 最终评审。

## 3V. Final Audit Pass #1 (2026-08-21 11:13 +08:00)

Status: `PASS`

- 上下文压缩后重新完整读取 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md`、`EXECUTION_PROGRESS.md`；四份 SHA-256 与压缩前一致，活动 Source of Truth 仍仅为 H-003，当前登记精确为 `1 DONE / 0 TODO / 0 IN_PROGRESS / 0 BLOCKED`。
- 独立重跑 `test_release_pipeline.py + test_release_gate.py` 为 `33/33`、0 skip；目标 SHA 的 `real-cross-layer-e2e` 只有 `status=completed / conclusion=success` 才可通过，missing、in-progress/success、failure、cancelled、wrong SHA 均失败关闭。
- 重新解析 CI：build → `test -f dist/server/index.js` → real E2E 顺序成立；删除 build 与删除 dist check 的负向合同均存在；17 个 action 引用全部固定 40 位 SHA，无 `continue-on-error`，真实 server 仍动态导入生产 `dist/server/index.js`，workflow 仅有一个共享 `WINDOPS_GATEWAY_DELEGATION_SECRET` 来源。
- 重新解析最终全量证据：backend JUnit `275 tests / 0 failures / 0 errors / 18 默认 external skips`，固定摘要 PostgreSQL JUnit `17/17 / 0 skip`，覆盖率 `7,458/10,212 = 73.03%`；三份证据 SHA-256 分别保持 `FBB280AC...75200`、`C4C1606E...1CC1`、`FC505DA9...7F3A`，changed executable coverage `70.48%` 仍通过。
- 相关文件无 TODO/FIXME/HACK/XXX/xfail；`git diff --check` 通过（仅现有 LF/CRLF 提示）。端口 `3000/4179/4180/8443/55432`、项目 runtime 进程、`windops.project=wind-agent` 运行容器和临时 TLS 均为 0。
- 未发现新的 Critical / High；连续收敛计数更新为 `1 / 2`，切换不同侧重点执行 Final Audit Pass #2。

## 3R. H-003 Clean-runner Remediation (2026-08-21 10:36 +08:00)

Status: `DONE`

- `.github/workflows/ci.yml` 的 `real-cross-layer-e2e` job 现在以独立根目录步骤执行 `pnpm run build`，且该步骤紧邻并早于 `pnpm test:e2e:real`；真实 Worker 启动前确定生成被 Git 忽略的 `dist/server/index.js` 与客户端产物。
- `test_release_pipeline.py` 解析实际 YAML 步骤并要求恰好一次 build、恰好一次 real E2E、build 紧邻在前且工作目录为仓库根；合成删除 build 步骤时合同明确抛出断言失败。合同同时锁定真实 server 对 `../dist/server/index.js` 的动态导入。
- 定向 release pipeline `21/21` 通过；Ruff format/lint 与 CI YAML Prettier 通过。`REQUIRED_CHECKS` 仍精确包含 `real-cross-layer-e2e`，既有同 SHA completed/success 失败关闭逻辑未改动。
- 干净 runner 复现先把现有 `dist` 移至仓库内隔离证据目录并确认根目录 `dist` 缺失；随后按新 job 顺序执行 `pnpm run build`，生成 Worker SHA-256 `3E16297876A049F3F614874B2CA1C65CC7771FF9F6C42A591AE892AD6F3C6011`。
- 固定摘要 TimescaleDB/PostgreSQL 空库升级到唯一 head `0023_bounded_weather_selection`，生成隔离 TLS 并启动真实 FastAPI 后，`CI=true` 的 Chromium Worker→HTTPS FastAPI→PostgreSQL 测试 `1/1` 通过；测试硬断言 readiness `503` → rotation confirm `200` → readiness `200`。
- 失败关闭实测：真实模式删除共享密钥时 Worker 启动 `exit 1` 并报告必需变量；保持 FastAPI 正确密钥、只给 Worker 同名错钥时，真实 rotation confirmation 返回 `401 Unauthorized`。
- FastAPI、正确密钥 Playwright Worker 与错钥 Worker 均已停止；端口 `4179/4180/8443` 已释放。隔离 PostgreSQL 暂保留用于即将执行的完整 PostgreSQL 全局回归，最终必须按精确名称/标签停止并确认 `--rm` 删除。

## 3S. First Full Recheck (2026-08-21 10:40 +08:00)

Status: `PASS`

- 从头重新读取四份控制文件，并只使用当前活动 H-003 作为 Source of Truth；活动集合、Progress 登记与严重级别精确一致，无遗漏 Issue、TODO、IN_PROGRESS 或 blocker。
- 逐项复核时发现原合同虽然锁定 build 顺序，却未让 job 在 Worker 启动前显式检查 `dist/server/index.js`。已把 `pnpm run build` 与 `test -f dist/server/index.js` 放在同一根目录步骤，并让该步骤紧邻 real E2E；删除完整 build 步骤或只删除 dist check 的合成负向合同均明确失败。
- 复查 release gate 时发现 `verify_release_checks.py` 只验证 `conclusion=success`，没有按审计文本同时要求 `status=completed`。已改为二者同时成立，并为 `real-cross-layer-e2e` 的 completed/success、in-progress/success、failure、cancelled、wrong SHA 与 missing 建立专门合同。
- 当前 release pipeline + release gate 定向回归 `33/33`，Ruff format/lint、workflow Prettier、YAML 解析、相关 `git diff --check` 通过。此前错误使用根 Python 解析 YAML 因缺 PyYAML 退出；改用项目 `uv` 环境后同一 YAML 硬断言通过，未修改门禁语义。
- 机器复核确认 build step index 10、real E2E step index 11；真实 server 仍无条件导入 dist Worker，真实模式只读共享密钥、缺钥失败关闭，mock fetch 仅在 `!REAL_BACKEND`；相关文件无 TODO/FIXME/HACK/XXX/xfail 或 `continue-on-error`。
- Required Changes 与四条 Acceptance Criteria 均有实现和客观证据；未发现 placeholder、stub、鉴权绕过或前后端假接通，进入 adversarial review。

## 3T. Adversarial Review (2026-08-21 10:41 +08:00)

Status: `PASS`

- `invalid / missing artifact`：合成删除完整 build 步骤与只删除 `test -f dist/server/index.js` 均使合同失败；真实 clean-runner 验证则从 `dist` 缺失开始生成并加载 Worker，无法用步骤名称或本地残留产物伪造通过。
- `production configuration / permission`：真实模式缺共享密钥启动 exit 1；单侧错钥真实确认请求 401。Worker mock backend 分支受 `!REAL_BACKEND` 硬边界约束，专用 job 明确设置 `WINDOPS_E2E_REAL_BACKEND=1`，未关闭委派签名鉴权。
- `stale / partial / restart`：build 与 artifact check 原子同一步且紧邻 real E2E；真实测试失败仍由 `if: always()` 上传 backend/browser 证据并停止 PID。重复 fixture 只清理固定 command type + 自有 audit target receipt，定向后端配置/平台安全回归继续通过。
- `release race / API failure`：机器构造 `in_progress/success`、completed/failure、completed/cancelled、wrong SHA 与 missing real check 均被拒绝；只有目标 SHA 的 completed/success 通过。未允许旧成功或其他 SHA 冒充当前 commit。
- 对抗组合后端 `59/59`、Node production runtime/idempotency `20/20`、机器 workflow/release assertions 全部通过，0 skip；唯一 warning 是既知 `.pytest_cache` ACL，独立 `--basetemp` 正常。
- 未发现新的 Critical / High / Medium，进入最终全局验证；Final Audit Pass 保持 `0 / 2`。

## 3U. Final Global Validation (2026-08-21 11:03 +08:00)

Status: `PASS`

- 前端当前最终树 `pnpm test:coverage` 通过：production build、bundle `92 chunks / 2,568,768 bytes / max 645,279`、Node `135/135`，V8 line/branch/function `90.34/51.29/33.13%`。TypeScript、ESLint、Prettier 与 pnpm production audit 全部通过。
- 普通后端当前 JUnit `275 tests / 0 failures / 0 errors / 18 external-release default skips`，即 `257 passed`；总行覆盖 `7,458 / 10,212 = 73.03%`，完整工作树 changed executable lines `70.48%`，全局、changed-line 与关键模块预算通过。证据：`backend/.artifacts/h003-final-global/backend-junit.xml`、`backend-coverage.json`。
- 固定摘要 TimescaleDB/PostgreSQL 专用门禁 `17/17`、0 failure/error/skip。四类真实大数据 HTTP 场景保持 SQL `8/8/9/9`；H-003 相关 weather limit=1 为 9 SQL、end-to-end p95/p99 `126.245/143.919 ms`、峰值 `1,178,418 bytes`、响应 `2,475 bytes`。证据：`backend/.artifacts/h003-final-global/postgres-junit.xml`。
- Mock Chromium `6/6` 通过且 real-only 1 项按模式预期 skip；标准 `pnpm build && pnpm test:start-smoke` 通过，Demo 正常、无效 production 失败关闭。最终 workflow 顺序再次 build、确认 Worker 产物后，真实 Worker→HTTPS FastAPI→PostgreSQL→Chromium `1/1` 通过，硬断言 503→200→200。
- Ruff format/lint（153 files）、mypy strict（72 source）、Bandit、pip-audit、container lock、Alembic heads/current/声明/offline render、15 个 Action SHA pins、YAML、`git diff --check` 全部通过；唯一 Alembic head 为 `0023_bounded_weather_selection`。
- 以 release policy 固定 Python/Trixie 摘要构建 `windops-h003-final-global:local`，镜像 ID `sha256:7827fffc79bd99120b78c013a5d666ab5c3bf3acaf65061b93bfb860caab0e3f`；hardened one-shot probe 验证 UID/GID 10001、默认命令、healthcheck、6 entrypoints、hash lock、pip check 与 pg_dump 17.11。可变本地 tag 被不可变 verifier 正确拒绝，未伪造 registry digest/signature。
- 最终证据 SHA-256：backend JUnit `FBB280ACDEE62EFCB5D316A2543D513677AD5DDAEA6538E98B1D0B59FBF75200`；coverage `C4C1606E864C8E683DB292EA8586DA81FD0ADB76ECA0271B51AF1BA70AE61CC1`；PostgreSQL JUnit `FC505DA9CB7C828767AF406D9565AAE1A96F921955E24F8C46255B130B557F3A`。
- 首轮前端静态批次因 clean-runner 复现保留的旧 `dist` 备份被 ESLint 扫描而失败；没有改规则，而是将已核对的 364 个生成文件非破坏性移动到仓库内 `.artifacts/h003-clean-runner/node_modules/preexisting-dist` 后原 `pnpm lint` 通过。递归删除被安全策略拒绝，备份仍可恢复且由 ESLint/Git 忽略。
- 最终清理：FastAPI、Playwright/Worker、标准 start 均停止；H-003 PostgreSQL 核对名称/标签/AutoRemove 后停止并删除；临时 TLS 已删除。端口 `3000/4179/4180/8443/55432`、项目 runtime 进程、`windops.project=wind-agent` 运行容器均为 0；本地镜像不是运行服务。
- 当前最终全局验证成立；进入两轮独立 Final Audit，计数保持 `0 / 2`。

The older sections below are retained only as historical evidence and must not be used as the active status.

# 3 (Historical). Re-audit started 2026-08-20 17:55 +08:00

The regenerated `AUDIT_REPORT.md` supersedes all earlier completion claims and the historical execution below. The active register is:

| ID | Severity | Status | Current evidence |
| -- | -------- | ------ | ---------------- |
| H-001 | High | DONE | SQL 每工单只返回 suitable-first/fallback Top-1 并披露额外候选；20,000 重叠窗口 limit=1/50 返回 1/50 行且 EXPLAIN 命中新索引。最终 limit=1 p95/p99 102.920/134.175 ms、峰值 1,177,778 bytes；limit=50 为 156.466/303.570 ms、1,621,017 bytes。真实 PostgreSQL 同时覆盖 suitable/fallback/unmatched/cross-farm/tenant/deterministic；迁移升降级、全量后端和 coverage 通过。 |
| H-002 | High | DONE | FastAPI 与 Worker 只读取 workflow 的 `WINDOPS_GATEWAY_DELEGATION_SECRET`，真实模式无默认值且不关闭签名鉴权。workflow 原生真实 E2E 1/1：ready 503→确认 200→ready 200；同名错钥返回 401，缺钥启动退出 1；静态/release gate 合同及全量回归通过。 |

Current sections `3K` through `3Q` supersede the older same-day completion claims. Sections beginning with the older `3H` below and the later historical execution records are retained only as historical evidence.

## 3K. Active Re-audit Remediation (2026-08-20 22:23 +08:00)

### H-001 — DONE

- `maintenance_plan_rows` 不再查询页面风场/时间跨度内全部 `WeatherWindow` 后 `.all()`；生产查询使用两个相关 Top-1 子查询，先取 suitable，再回退最早重叠窗口，外层每工单至多一行。
- 选择顺序固定为 `starts_at ASC, ends_at ASC, id ASC`；`related_data_boundaries.weather_windows` 公开每工单上限、策略、顺序和实际省略额外候选的工单数。
- 新增 `0023_bounded_weather_selection` 及模型复合索引；真实空库 upgrade、downgrade 到 `0022`、再 upgrade head 通过，EXPLAIN 实际使用 `ix_weather_farm_suitable_starts_ends_id`。
- 真实 PostgreSQL + ASGI 门禁在 100,000 主记录和 20,000 重叠窗口下验证 limit=1/50 的 1/50 行数据库结果、固定 9 SQL、响应大小、p95/p99、峰值及完整天气选择语义。

### H-002 — DONE

- 真实 FastAPI smoke 对缺失 `WINDOPS_GATEWAY_DELEGATION_SECRET` 失败关闭；Worker 真实模式读取同一个变量，移除 `WINDOPS_E2E_DELEGATION_SECRET` 和不同真实默认值，仅 mock 模式保留明确标记的本地 fixture 值。
- 静态合同解析 `real-cross-layer-e2e` job 和两个脚本，锁定 workflow-to-script 单一变量名、缺钥失败关闭及 release 必需检查。
- workflow 原生环境真实 Chromium 1/1 通过；保持 backend 正确密钥并只改 Worker 同名变量时确认接口真实返回 401，完全缺钥时 Worker 退出 1。

### Current-tree Validation

- Backend：`266 collected = 248 passed + 18 external-release default skips`；总行覆盖 `73.03%`，完整工作树 changed-line `70.48%`。
- PostgreSQL：完整固定摘要套件 `17/17`、0 skip；最终 H-001 高扇出/语义合同另行重跑通过。
- Frontend：production build、bundle `92 chunks / 2,568,768 bytes / max 645,279`、Node `135/135`、V8 line/branch/function `90.34/51.29/33.13%`、typecheck/lint/format、标准 start smoke 和 Chromium mock `6/6` 通过。
- Quality/Security：Ruff format/lint、mypy strict 72 source、Bandit、pip-audit、container lock、Alembic offline render/head、Prettier 与 `git diff --check` 通过。

## 3L. First Full Recheck (2026-08-20 22:25 +08:00)

Status: `PASS`

- `H-001`：复核生产调用链后确认 page query 先完成授权和 limit，再以内部 page work-order IDs 调用有界天气查询；没有用户可控 ID 绕过，cross-farm 由 turbine farm FK 约束。旧的 `planned_starts/latest_end` 跨页加载和天气 `.all()` 已不存在。
- `H-001`：策略、每工单 1、确定性顺序和 `truncated_work_order_count` 均进入响应元数据；SQLite 与真实 PostgreSQL 都覆盖 suitable-first/fallback/unmatched/cross-farm/tenant/deterministic，真实高扇出还验证 limit=1/50、SQL/response/p95/p99/heap。
- `H-001`：模型与 `0023` 迁移一致；唯一 head、声明、offline render、真实 upgrade/downgrade/re-upgrade 和 EXPLAIN 新索引使用均有硬断言。没有删除/skip/弱化原有 100k diagnosis/maintenance 门槛。
- `H-002`：CI job 只定义共享变量；FastAPI 和 Worker 真实路径只读取同一名称且缺失时失败关闭。Worker 的 mock-only fixture 不会进入 `WINDOPS_E2E_REAL_BACKEND=1` 路径。
- `H-002`：真实请求保持委托 HMAC/JWT 鉴权；正确共享值完成 503→200→200，单侧错值真实返回 401，缺值退出 1。release required-check 集仍包含 `real-cross-layer-e2e`，同 SHA 成功/缺失/失败状态合同继续通过。
- 相关实现和验收文件没有 TODO/FIXME/HACK/XXX、xfail、断言弱化或 `continue-on-error`；唯一 external `skipif` 由专用 job 的 `WINDOPS_FAIL_ON_SKIPPED=1` 约束。`git diff --check` 通过，仅有换行提示。
- 未发现遗漏、部分完成或新 Critical/High；进入 adversarial review，Final Audit Pass 保持 `0 / 2`。

## 3M. Adversarial Review (2026-08-20 22:27 +08:00)

Status: `PASS`

- `invalid/empty`：maintenance page 的空结果仍返回完整零边界；非法 limit 由现有 API schema 拒绝。有界 helper 对无匹配返回每工单一行/空 weather，不用 placeholder 补数据。
- `permission/cross-tenant`：内部 child 查询只接受授权 page IDs；SQLite 与真实 PostgreSQL 的错误 tenant 均返回空数据，另风场更早且 suitable 的窗口不会被选择。
- `high fanout/production database`：20,000 条全部重叠时 direct DB 结果精确 1/50；最终真实 HTTP limit=1 峰值 1,177,778 bytes，相比审计旧值 36,805,705 bytes 不再线性放大。EXPLAIN 选择约 0.976 ms 并使用新索引。
- `determinism/truncation`：20,000 个同起止 unsafe 窗口固定选择最小 ID；两个同起始 suitable 按 ends/id 稳定选择 A；额外候选工单数为 1，删除本风场窗口后为 0。
- `SLO failure`：两轮真实测试曾分别因无关 diagnosis/work-order 宿主抖动超过既有 500 ms p95 而失败，未修改阈值；原命令复跑通过。证明性能 gate 仍真实失败关闭。
- `constraint/partial fixture`：首次新增跨租户风场 fixture 未创建 Tenant 父记录，真实 FK 正确拒绝且事务回滚；补充合法 Tenant 后原跨风场/租户断言通过，没有禁用约束。
- `auth/production config`：正确共享密钥完成真实轮换；单侧错钥为 401，完全缺钥为启动退出 1；静态合同禁止旧变量进入 workflow/runtime，签名校验没有 mock 或 bypass。
- `restart/repeated action`：最终复跑首次暴露 fixture 重建同一 pending audit 时遗留旧 command receipt；固定幂等键重放旧 200 但新 audit 未更新，readiness 保持 503。仅在隔离 fixture 中按 command type + 自有 audit target 清除旧 receipt，不改生产幂等实现；同一数据库连续两轮 503→200→200 均通过，并新增静态回归合同。
- `release regression`：required checks 仍含 `real-cross-layer-e2e`；目标 SHA 只有 completed/success 才可通过，missing/failure/cancelled/in-progress/wrong SHA 均拒绝。
- 未发现新 Critical/High/Medium；进入当前最终树的全局证据重跑，Final Audit Pass 保持 `0 / 2`。

## 3N. Final Global Validation (2026-08-20 22:45 +08:00)

Status: `PASS`

- 最终普通后端 JUnit `266 tests / 0 failures / 0 errors / 18 external-release default skips`，即 `248 passed`；总行覆盖 `73.03%`，完整工作树 changed-line `70.48%`，所有关键模块 floor 继续通过。证据：`backend/.artifacts/final-remediation-backend-current.xml`、`backend/.artifacts/final-remediation-coverage-current.json`。
- 最终真实 PostgreSQL 固定摘要套件 `17/17`、0 failures/errors/skips；H-001 最终语义/高扇出测试另行通过。20,000 重叠窗口 limit=1/50 均保持 9 SQL；limit=1 p95/p99 `102.920/134.175 ms`、峰值 `1,177,778 bytes`，limit=50 为 `156.466/303.570 ms`、`1,621,017 bytes`。证据：`backend/.artifacts/final-remediation-postgres-current.xml`、`backend/.artifacts/final-h001-semantic-postgres-final.xml`。
- 前端最终 production build、bundle `92 chunks / 2,568,768 bytes / max 645,279`、Node `135/135`、V8 line/branch/function `90.34/51.29/33.13%`、typecheck、ESLint、Prettier、标准 `pnpm start` smoke 和 mock Chromium `6/6` 全部通过。
- workflow 原生真实 Worker → HTTPS FastAPI → PostgreSQL → Chromium 在同一隔离数据库连续两轮均 `1/1` 通过，均为 readiness `503` → rotation confirm `200` → readiness `200`；单侧错误共享密钥真实返回 `401`，缺失密钥时 Worker 启动退出 `1`。
- Ruff format/lint（153 files）、mypy strict（72 source files）、Bandit、pip-audit、pnpm production audit、container dependency lock、Alembic offline render/head/current、migration 声明、Prettier 与 `git diff --check` 全部通过；唯一 Alembic head 为 `0023_bounded_weather_selection`。
- 对抗复查后新增的可重复 fixture 回归已进入最终普通后端套件；同一数据库重复准备时只清除该 fixture 自有 command type + audit target receipt，不改变生产幂等实现。
- 最终清理确认：审计专用 `windops-h001-weather-postgres` 已停止并因 `AutoRemove` 删除；临时 FastAPI/Worker/Playwright 进程均停止；临时 TLS `key.pem/cert.pem` 已删除；目标端口 `3000/4179/4180/8443/18443/55432`、项目相关进程与项目标签容器均为空。只删除了可重建的隔离测试数据和临时证书，未操作其他项目服务。
- Final Global Validation 对当前最终树成立；进入两轮独立 Final Audit，计数仍为 `0 / 2`。

## 3O. Final Audit Pass #1 (2026-08-21 09:32 +08:00)

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Convergence: `1 / 2`

- 中断恢复后完整重读 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md` 和本文件；活动 Source of Truth 仍精确为两个 High，Progress 精确登记 `H-001,H-002` 且均为 `DONE`，TODO/IN_PROGRESS/BLOCKED 均为 0。
- 独立定向回归 `tests/test_operational_views.py + tests/test_release_pipeline.py + tests/test_backup_recovery.py` 为 `30/30`，0 failure/error/skip；唯一 warning 是既知 `.pytest_cache` ACL，独立 `--basetemp` 正常。
- 重新解析当前证据：普通后端 `266/0 failures/0 errors/18 default external skips`；真实 PostgreSQL `17/0/0/0`；H-001 最终语义测试 `1/0/0/0`；coverage `7,458/10,212 = 73.03%`。
- H-001 证据属性再次确认：weather selection SQL `0.976 ms`；limit=1 固定 9 SQL、p95/p99 `102.920/134.175 ms`、峰值 `1,177,778 bytes`、响应 `2,475 bytes`；limit=50 固定 9 SQL、p95/p99 `156.466/303.570 ms`、峰值 `1,621,017 bytes`、响应 `90,240 bytes`。
- 生产源码仍包含每工单上限 1、suitable-first/fallback 策略、稳定排序与截断元数据；模型和 `0023` 迁移均声明 `ix_weather_farm_suitable_starts_ends_id`。旧 `planned_starts/latest_planned_end` 跨页路径为 0 命中；相关实现/测试无 TODO/FIXME/HACK/XXX/xfail/`continue-on-error`。
- H-002 workflow、FastAPI 和 Worker 仍只使用 `WINDOPS_GATEWAY_DELEGATION_SECRET`；旧变量仅出现在静态拒绝断言中，未出现在 runtime/workflow。缺钥失败关闭和同 SHA `real-cross-layer-e2e` release check 合同由本轮回归通过。
- Alembic `heads` 与声明校验均精确为 `0023_bounded_weather_selection`；`git diff --check` 退出 0，仅 LF/CRLF 工作树提示。目标端口、项目进程和临时容器仍为空。
- 当前四份关键证据 SHA-256：backend JUnit `47B7E0861CF971AFD7F924A9BD5B6CC3FB7B568C73DA15E2D5367AF3AFB58020`；coverage `8C29D79EB7749FD99F1F6F07EE9F745233D62DAF84A63E244557AE68C0F8830B`；PostgreSQL JUnit `D21275C083F6D28C65BF36E7D48C49C8FCA62C141F4E48FA4E68FD765BE8C708`；H-001 semantic JUnit `F1F55C8CAE01268EFD21ABBDFA0210E08F60DAF9EED36A4B4E7FA250D10F1FE1`。
- 首次 coverage 只读解析因 Coverage.py 空文件键需要 `ConvertFrom-Json -AsHashtable` 而退出；按实际 JSON 结构重跑同一硬断言通过，未修改证据或产品代码。
- 本轮没有发现新的 Critical 或 High，Final Audit Pass 增至 `1 / 2`。

## 3P. Final Audit Pass #2 (2026-08-21 09:39 +08:00)

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Convergence: `2 / 2`

- 与 Pass #1 不同侧重点的后端负向/边界合同通过：bounded collections、business access control、coverage budget、replay/idempotency、production configuration 共 `35/35`，0 failure/error/skip；Node 生产 runtime + idempotency 合同 `20/20`，0 skip。
- 当前 coverage budget 脚本直接读取最终 coverage 与完整工作树 diff 后通过：global line `73.03%`、changed executable lines `70.48%`，没有调整门槛。
- 机器状态审计确认 `AUDIT_REPORT.md` 活动 Issue 精确为 `H-001,H-002`，活动表两项精确 `DONE`；CI 的共享委派密钥来源唯一，FastAPI/Worker/runtime/workflow 中 deprecated 变量为 0。
- 真实 PostgreSQL 压力测试源码仍由 `generate_series(1, 20000)` 生成天气高扇出，并对 `work_order_weather_limit_one` 保持 8 MiB 峰值硬断言；重复 real-E2E fixture 只按固定 command type + 自有 audit target 清理 receipt。
- CI 与 release workflow 共 `15` 个 `uses:` 均固定完整 40 位 SHA（允许行尾版本注释），两者均无 `continue-on-error`；release required check 合同仍由 Pass #1 的 release pipeline 回归保护。
- Pass #1 记录的四份当前证据 SHA-256 全部一致，Evidence Drift 为 0；迁移 head、JUnit/coverage/真实 E2E 结果在两轮间未被改写。
- 停止状态再次确认：目标 listener `0`、项目 runtime 进程 `0`、审计容器 `0`、临时 TLS 文件 `0`；没有操作其他项目服务。
- 只读机器审计前三次分别因 JS→PowerShell 反斜杠转义、源码使用 SQL `20000` 而非 Python `20_000`、JUnit 属性由动态名称生成而失败；第四次又因 Action 行尾版本注释的过严正则失败。逐项查看实际源码后只修正审计表达式，最终所有原语义硬断言通过，没有改产品、测试或证据。
- 本轮没有发现新的 Critical 或 High；连续两轮 Final Audit 收敛成立，计数增至 `2 / 2`。Final State 暂保持 `OPEN`，直到重新读取控制文件并完成 Gate A-H 的最终持久化。

## 3Q. Completion Gates A-H (2026-08-21 09:41 +08:00)

Status: `COMPLETED`

| Gate | Status | Final evidence |
| --- | --- | --- |
| A — Coverage | PASS | `AUDIT_REPORT.md` 活动集合精确为 `H-001,H-002`；Progress 活动表精确登记同两项且均 `DONE`，TODO/IN_PROGRESS/未登记为 0。 |
| B — Critical / High | PASS | Critical 为 0；两个可执行 High 均已实现、定向验证、全局回归并标记 `DONE`。 |
| C — Medium | PASS | 当前 `AUDIT_REPORT.md` 没有活动 Medium；不存在未完成或伪造 blocker。 |
| D — Evidence | PASS | 当前源码、`0023` migration、backend JUnit `266/0/0`、PostgreSQL JUnit `17/0/0/0`、H-001 semantic JUnit、coverage、真实/Mock E2E、负向 401/缺钥、迁移/索引/EXPLAIN/SLO/heap 和 release 合同均有客观证据；两轮间证据哈希无漂移。 |
| E — Recheck | PASS | `3L` 已从 H-001 到 H-002 逐项复验全部 Required Changes 与 Acceptance Criteria；无遗漏、部分实现或相关 TODO。 |
| F — Global Validation | PASS | `3N` 已对最终工作树重跑 build/format/lint/typecheck/unit/integration/API/E2E/production start/migration/security/coverage；全部通过。 |
| G — Convergence | PASS | `3O` 与 `3P` 两轮独立 Final Audit 均未发现新 Critical/High；计数为 `2 / 2`。 |
| H — Persistent State | PASS | 本次原子更新已同步 Metadata、Statistics、Current Work、Convergence、活动 Issue 表、Gate 表、Override 和 Final State 为真实最终状态。 |

- Gate A-G 在本次写入前经机器断言全部通过；Gate H 随本次进度持久化成立。
- 最终写入前快照：四份关键证据哈希与 Pass #1 一致，`git diff --check` PASS；目标 listener、项目 runtime 进程和审计容器均为 0。
- 当前没有 blocker 或剩余审核任务。服务保持停止；仅移除了可重建的隔离 PostgreSQL 测试数据和临时 TLS 文件，未操作其他项目服务。

## 3H. Final Audit Pass #1 (2026-08-20 13:50 +08:00)

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Convergence: `1 / 2`

- 按阶段规则完整重读 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md` 和本文件全部 1321 行；活动审核集合仍精确为 `H-001,H-002,M-001,M-002`，四项均 `DONE`，无 TODO/IN_PROGRESS/BLOCKED。
- 独立快速回归通过：H-001/H-002/M-002 后端图谱、有界集合、运营视图、持久事务、coverage 与 CI/ops 合同 `48/48`；M-001 及生产身份/幂等/SSE 前端合同 `26/26`、零 skip。唯一 warning 是既知 `.pytest_cache` ACL，独立 `--basetemp` 正常。
- 重新解析当前最终 JUnit：普通后端 `262/0 failures/0 errors/18 external skips`；H-001 峰值 `7,788,818 / 33,554,432` bytes、250 主实体；专用 PostgreSQL `17/0/0/0`，四场景 SQL、p95/p99、响应与 Python 峰值全部低于硬门限。
- 覆盖证据重新断言：总行 `73.03%`；Agent `54.18%`、Alarm `85.71%`、Operational Views `56.71%`、Platform `60.30%`、Workflow `61.90%`、Workorders `91.43%`，均高于提高后的 floor。
- release smoke 与 deployment policy 报告均仍为 `passed`；14 resources / 5 workloads，rendered manifest SHA-256 仍为 `5faf493332269ff2a5be4fe0c65cc00a88726a51d6e34fe8bf90d0831dc2a7e5`，无 placeholder。候选镜像 content ID、UID/GID、命令、commit label 未漂移。
- Alembic 唯一 head/声明仍为 `0022_diagnosis_priority_indexes`；`git diff --check` 退出 0，仅 LF/CRLF 提示。端口 3000/4179/8000/8443/18002/55438、项目运行时进程与带项目标签的容器均为空。
- 证据解析器前两次误读 JUnit 层级（根 `testsuites` vs 子 `testsuite`）而失败；查看原始 XML 后改用精确 XPath，同一硬断言全部通过。该项是审计脚本调用错误，未改写任何代码/证据，也未掩盖产品失败。
- 本轮没有发现新的 Critical 或 High，Final Audit Pass 增至 `1 / 2`。

## 3I. Final Audit Pass #2 (2026-08-20 13:58 +08:00)

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Convergence: `2 / 2`

- 上下文压缩后依规从头完整重读 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md` 和本文件全部 1,336 行，再以活动区而非历史记录恢复状态；Source of Truth 仍精确包含 `H-001,H-002,M-001,M-002`，四项均 `DONE`，无 TODO/IN_PROGRESS/BLOCKED。
- 与 Pass #1 不同侧重点的发布、容器、部署、release gate、备份/恢复合同回归 `52/52` 通过；唯一 warning 仍是既知 `.pytest_cache` ACL，独立 `--basetemp` 正常。
- 机器断言重新解析两个 workflow：CI 包含 frontend/backend/postgres-contract/browser-e2e/real-cross-layer-e2e，release 受 `production-release` environment 保护；共 `32` 个 Action `uses:` 引用全部固定为完整 40 位 SHA。backend 与 PostgreSQL JUnit 均被生成/上传，专用 PostgreSQL job 明确设置两个 opt-in 和 `WINDOPS_FAIL_ON_SKIPPED=1`，session hook 会把任一 skip 强制转换为失败；无 `continue-on-error`。
- 六份最终证据重新做语义断言并记录 SHA-256：coverage `63b228a502c4516bb2a58fb699cf4839f110e8a9caa5e0a7a2be95022f97e91d`；backend JUnit `cd779f580a75bc6df249a02de76351774ea222a1b1b43f5aefba0e08d309f3eb`；PostgreSQL JUnit `98814e3c73f227e17d2f9af5d48c134fcd96589b267d0473c1a54bcf0451db66`；release smoke `3ceff1e35e24de29174afcc3bae555d412e8dd60f7fdfc5c26279ffe455505f1`；deployment policy `01fe742c512b50b535c9e2c1a39902685036cb6115a60e3743b669b4c6307c54`；rendered manifest `5faf493332269ff2a5be4fe0c65cc00a88726a51d6e34fe8bf90d0831dc2a7e5`。
- 当前普通后端证据仍为 `262 tests / 0 failures / 0 errors / 18 external skips`，H-001 Python 峰值 `7,788,818 / 33,554,432` bytes、250 主实体；专用 PostgreSQL 仍为 `17/0/0/0`，SQL 固定 `8/8/9/9`，所有 p95/p99、响应和 Python 峰值均低于硬门限。
- coverage 仍为总行 `73.0252%`；Agent `54.1833%`、Alarm `85.7143%`、Operational Views `56.7059%`、Platform `60.2985%`、Workflow `61.9048%`、Workorders `91.4286%`，全部高于提高后的 floor。release smoke 与 deployment policy 均为 `passed`，资源/workload/check 为 `14/5/9`。
- 直接重查 H-001 的递归 deep-size/运行时 tracemalloc/Reservation 双遍/Neo4j 有界交接、H-002 的关联边界/orjson/真实 HTTP 指标、M-001 的 undefined env 归一化/图片 503/标准启动 CI，以及 M-002 的行锁后二次 receipt、savepoint/唯一冲突和六个 coverage floor；关键防线仍在当前源码且对应合同通过。
- 候选镜像当前 content ID 仍为 `sha256:4980e6e4fb7df3fe024a77a4f5437a17ab5ef1b55d70c7e04382297e052b3dc0`；linux/amd64、UID/GID `10001:10001`、默认 `windops-api`、healthcheck、release/commit/source/固定 base 标签均未漂移。保留本地候选供复核，未伪报 registry push/signature。
- Alembic 唯一 head 与声明均为 `0022_diagnosis_priority_indexes`；`git diff --check` 通过，相关源码 TODO/FIXME/HACK/XXX 为 0。高置信 secret 扫描只命中 `test_platform_configuration_security.py` 中两处明确的无效私钥拒绝 fixture；五个 external `skipif` 均由专用 fail-on-skip 门禁约束，唯一 `|| true` 是真实 E2E finally 的 PID 清理。
- Docker 精确标签及名称扫描均确认 OpenVigil 容器/网络为 0；仓库 Node/Python runtime 进程为 0；端口 `3000/4179/8000/8443/18002/55438` listener 为 0。端口 `5432` 当前属于另一仓库 `ai-hybrid-tower-inspection` 的 `aihti_h005_prod-postgres-1`，端口 `9000` 属于系统 `LemonadeServer.exe`，按工作边界未操作。
- 审计脚本有三次已纠正的只读调用错误：coverage 路径键使用 Windows 反斜杠、Docker Go template 假定可选 Entrypoint 键存在、从 backend 目录误写 workflow 相对路径；均在查看实际格式后用规范化/完整 JSON/正确路径重跑原硬断言通过，没有修改证据或掩盖产品失败。
- 本轮没有发现新的 Critical 或 High，连续两轮 Final Audit 收敛成立，计数增至 `2 / 2`。

## 3J. Completion Gates A-H (2026-08-20 14:01 +08:00)

Status: `COMPLETED`

| Gate | Status | Final evidence |
| --- | --- | --- |
| A — Coverage | PASS | `AUDIT_REPORT.md` 活动集合精确为 4 项；Progress 活动表精确登记同一 4 项，全部 `DONE`，TODO/IN_PROGRESS/未登记均为 0。 |
| B — Critical / High | PASS | Critical 为 0；可执行 High `H-001,H-002` 均为 `DONE`，并有实现、定向/全局测试及客观峰值/SLO 证据。 |
| C — Medium | PASS | 可执行 Medium `M-001,M-002` 均为 `DONE`，无 blocker 或未完成例外。 |
| D — Evidence | PASS | 最终代码锚点、普通 JUnit `262/0/0`、专用 PostgreSQL JUnit `17/0/0/0`、coverage、标准启动、真实跨层 E2E、镜像 smoke、部署 policy、迁移与安全扫描证据均重新解析或复验通过。 |
| E — Recheck | PASS | `3E` 已从 H-001 到 M-002 逐项重新验收并为 PASS；无遗漏、部分完成或相关 TODO。 |
| F — Global Validation | PASS | `3G` 已针对最终工作树重新执行 build/format/lint/typecheck/unit/integration/API/E2E/production start/Docker/migration/security/deployment，并为 PASS。 |
| G — Convergence | PASS | `3H` 与 `3I` 两次独立 Final Audit 均无新增 Critical/High；计数为 `2 / 2`。 |
| H — Persistent State | PASS | 本文件活动 Metadata、Statistics、Issue 表、Convergence、Gate 表、Next 和 Final State 已同步为真实最终状态。 |

- Gate A-G 先由形式化脚本精确解析 `AUDIT_REPORT.md`、本文件活动区、当前实现和最终证据后全部通过；Gate H 随本次原子进度更新成立。
- 最终紧邻写入快照：`git diff --check` PASS；项目标签容器、项目网络、OpenVigil 名称容器、仓库 Node/Python runtime 进程及端口 `3000/4179/8000/8443/18002/55438` listener 全部为 `0`。
- 当前没有 blocker 或剩余审核任务。候选镜像仅作为停止状态下的本地制品保留，不是运行服务；其他仓库/系统服务未操作。

## 3G. Final Global Validation (2026-08-20 13:27 +08:00)

Status: `PASS`

- 当前最终前端 `pnpm test:coverage` 通过：production build、bundle 预算、Node `135/135` 且零 skip；V8 line `90.34%` / branch `51.33%` / function `33.13%`，均高于 `89/49/32`。Prettier、ESLint、TypeScript、标准 `pnpm build && pnpm test:start-smoke` 和 mock Chromium `6/6` 通过，标准启动及 E2E 清理后端口 `3000/4179` 释放。
- 当前最终普通后端 JUnit：`262 tests / 0 failures / 0 errors / 18 external skips`，即 `244 passed`；总覆盖 `73.03%`，完整工作树 changed-line `70.28%`，六个提高后的关键模块 floor 全部通过。Ruff、mypy strict、Bandit、pip-audit、pnpm production audit 与 container requirements lock check 均通过。
- 当前最终固定摘要 PostgreSQL/TimescaleDB/pgvector 门禁：`17 tests / 0 failures / 0 errors / 0 skipped`；四个 10 万主记录真实 HTTP 场景固定为 `8/8/9/9` SQL，最差 p95 `269.464 ms`、p99 `288.026 ms`，最大最终响应 `133,327 bytes`、最大 Python 峰值 `1,639,597 bytes`。
- 当前最终 Alembic 空库升级、current/head、history、声明校验和完整 offline SQL 均通过，唯一 head 为 `0022_diagnosis_priority_indexes`。
- 真实 Worker → HTTPS FastAPI → PostgreSQL → Chromium 复验 `1/1` 通过：轮换前 readiness `503`，授权委托确认后恢复 `200`；数据库记录为 `rotation_required=false` / `quarantined_rotation_confirmed`。测试后 FastAPI/Playwright 会话已停止，端口 `8443/4179` 释放。
- 第一次 fixture 调用使用了超过 schema `varchar(36)` 的合成 revision ID，事务正确完整回滚；改用短 ID 后原路径通过。该项归类为验证参数错误，不是产品失败，也没有部分写入。
- 固定批准的 Python/Trixie 基础镜像摘要冷构建通过，当前候选 content ID 为 `sha256:4980e6e4fb7df3fe024a77a4f5437a17ab5ef1b55d70c7e04382297e052b3dc0`；OCI release/commit/source/base labels、amd64/Linux、UID/GID `10001:10001`、默认命令和 healthcheck 均与策略一致。
- 对实际 content-addressed 镜像执行 hardened runtime probe：6 个必需 entrypoint、迁移 payload、hash lock、`pip check`、无 pytest、`pg_dump 17.11` 全部通过。本地没有伪造已推送 registry/signature 证据。
- 实际 release image smoke 通过：镜像内 Alembic、read-only rootfs、non-root、cap-drop、no-new-privileges、API health/readiness、Docker health 与 release identity 注入均成功；临时固定摘要 Neo4j、API 容器和专用网络已精确清理。
- `kubectl kustomize v5.8.1` 真实渲染后 deployment policy 通过：`14` resources、`5` workloads/jobs、`9` 项策略检查；全部绑定同一 content digest/release/commit，清单 SHA-256 `5faf493332269ff2a5be4fe0c65cc00a88726a51d6e34fe8bf90d0831dc2a7e5`。
- `git diff --check` 退出 `0`，仅既有 LF/CRLF 提示。相关源码/测试无未完成 TODO/FIXME/HACK；CI 唯一 `|| true` 是 finally 清理，外部测试 `skipif` 受专用 job 的 `WINDOPS_FAIL_ON_SKIPPED=1` 约束；高置信 secret 扫描只命中两个明确的无效 `fixture` 私钥头字符串。
- 最终 PostgreSQL 在核对 `windops.project=wind-agent`、`windops.audit.issue=FINAL`、`--rm` 与端口 `55438` 后停止并确认删除；本轮 TLS 私钥/证书已删除。OpenVigil 无运行中容器、专用网络或仓库 Node/Python 进程。公共端口扫描中的 `5432` 属于另一仓库 `ai-hybrid-tower-inspection`，`9000` 属于系统 `LemonadeServer.exe`，按项目边界未操作。
- Remaining：`NONE`（进入两轮连续 Final Audit 收敛检查）。

## 3F. Adversarial Review (2026-08-20 13:10 +08:00)

Status: `PASS`

- 主动覆盖 invalid input、empty state、repeated action、network/API failure、permission、stale state、concurrency、restart、partial failure 和 production configuration；后端对抗组合 `72/72`、前端运行时/身份/幂等/SSE `26/26`、真实 PostgreSQL 韧性 `5/5` 且零 skip、Chromium mock production 场景 `6/6`。
- H-001 独立 JUnit 峰值重测：`8,009,771 / 33,554,432` bytes，250 个主实体及 1,000 Evidence、750 Task、500 Reservation 等组合；同一测试再次验证 128 KiB 上限连续失败且旧图保持。
- PostgreSQL 负向门禁故意不启用 opt-in：5 个外部测试被 skip 后，`WINDOPS_FAIL_ON_SKIPPED=1` 正确强制 pytest 退出 1；CI 无法用 skip 伪造通过。
- 发现一项直接相关的证据链缺口：压力测试使用 `record_testsuite_property`，但 backend CI 原先没有 `--junitxml`，与运行手册“CI 保存峰值/上限/实体数”声明不一致。已在 `.github/workflows/ci.yml` 生成并上传 `backend-tests-junit.xml`，更新 `docs/testing-quality-gates.md`，并在 `test_release_pipeline.py` 增加语义合同。
- 修复后单项合同、YAML、Prettier 通过，完整 release/ops CI 合同 `21/21`；相关实现/验收文件无 TODO/FIXME/HACK、skip/xfail、`continue-on-error` 或覆盖阈值弱化。唯一 `|| true` 位于真实 E2E 的 finally 清理，不影响门禁结果。
- 没有发现新的 Critical 或 High；对抗复查结束，进入最终全局验证。Final Audit Pass 保持 `0 / 2`。

## 3E. First Full Recheck (2026-08-20 13:02 +08:00)

Status: `PASS`

- `H-001` — 重新检查递归堆记账、1.50 安全系数、85% `tracemalloc` 门限、合并索引、有界 Reservation 双遍扫描和 snapshot/Neo4j 交接余量；当前完整图谱测试 `10/10`，生产形态多实体峰值断言和 128 KiB 连续两次失败且旧图不变均实际执行。
- `H-002` — 重新检查两个 production route、共享 query builder、64/50 page cap、Evidence/Execution 最新 1、Task aggregate-only、每 Mission/资源类型最新 1、截断元数据和 `orjson` 最终字节；真实 PostgreSQL JUnit `17/17`、零 skip，四场景固定 `8/9` SQL，最差 p95/p99、峰值与响应均低于门限，并验证 100,000 主记录及 24/24/80/每类 6 高扇出。
- `M-001` — 重新检查唯一 Worker 入口的 undefined-env 归一化、生产 boundary、图片 binding 503、Windows/POSIX 进程树清理以及 CI 直接命令；当前 production runtime 合同 `17/17`，真实标准启动将在最终全局验证重新构建后复跑。
- `M-002` — 重新检查告警行锁后 receipt 二次读取、平台首 revision savepoint/唯一约束冲突转换、六个提高后的模块 floor、CI 固定摘要和 fail-on-skip；当前 SQLite 持久事务/快速失败路径/coverage 合同 `15/15`，真实 PostgreSQL 新增韧性子集 `5/5`、总套件 `17/17`、零 skip。
- 相关实现与验收测试扫描没有 `TODO/FIXME/HACK`、pytest skip/xfail 或用 `AsyncMock` 替代新增事务证据；`git diff --check` 退出 0，仅有既有 LF/CRLF 提示。
- 未发现新的 Critical / High / Medium；四项仍保持 `DONE`，进入对抗性复查。

## 3D. M-002 Critical-service Failure-path Evidence (2026-08-20 12:57 +08:00)

Status: `DONE`

### Implementation

- 告警命令在等待 `Alarm FOR UPDATE` 行锁后再次读取 receipt；并发同一 key 的 loser 现在重放 winner 的已提交响应，不再把合法重试误报为 stale revision。
- 平台配置首版本创建被独立 savepoint 包围；由于不存在的 revision 无法被 `FOR UPDATE` 锁定，数据库 `(configuration_key, revision)` 唯一约束作为最终竞争仲裁，loser 被转换为可重试 `ConflictError`，且不会污染外层事务。
- 新增快速持久化事务测试，在真实 SQLite session 中把故障注入到数据库变更后的健康写入、投影入队、DomainEvent 与 EAM 入队边界，逐项证明工单、审批、平台配置、资源重分配、排程、告警和 Agent 控制失败后无部分写入，随后重试只提交一次。
- 新增固定摘要 PostgreSQL 服务韧性套件，使用确定性双事务 barrier 强制两个事务都先观察到“无 receipt/无首 revision”，而不是依赖概率竞争；覆盖 commit/rollback、唯一约束、并发更新、同键幂等重放、异键 stale conflict、副作用失败和租户权限隔离。
- CI `postgres-contract` 直接包含新增文件并保持 `WINDOPS_FAIL_ON_SKIPPED=1`；release/ops 合同测试锁定该文件不能从门禁移除。
- 覆盖预算回归测试锁定六个新 floor；质量门禁文档记录实测依据和 PostgreSQL 韧性范围，未降低全局 68% 或 changed-line 65.5% 两层门槛。

### Files Changed

- `backend/src/windops_backend/services/{alarms,platform_governance}.py`
- `backend/tests/test_critical_service_transactions.py`
- `backend/tests/external/test_postgres_service_resilience.py`
- `backend/scripts/check_coverage_budget.py`
- `backend/tests/{test_coverage_budget,test_release_pipeline,test_ops_configuration}.py`
- `.github/workflows/ci.yml`
- `docs/testing-quality-gates.md`

### Validation

- `PASS` — 完整普通后端套件 + coverage：总行覆盖 `73.03%`；Workorders `91.43%`、Workflow `61.90%`、Platform Governance `60.30%`、Operational Views `56.71%`、Alarms `85.71%`、Agent Governance `54.18%`，全部高于新 floor。
- `PASS` — 全局/关键模块预算脚本；完整工作树（含 6 个未跟踪 Python 源文件）changed executable lines `6,060 / 8,623 = 70.28%`，高于 `65.5%`。
- `PASS` — 新增快速持久化事务测试 6/6；M-002 定向服务/CI 合同回归 40+ tests 全部通过，既有 `AsyncMock` 快速分支测试保留。
- `PASS` — 固定摘要 PostgreSQL/TimescaleDB/pgvector CI 同构套件：`17 tests / 0 failures / 0 errors / 0 skipped`，79.554 s；JUnit：`backend/.artifacts/m002/postgres-contract-full.xml`。新增服务韧性子集 5/5。
- `PASS` — Ruff format/check 全 152 files、mypy strict 72 source files、相关 Prettier、`git diff --check`。
- 首轮运营视图测试因使用非允许 Host 得到正确的安全 400；改用既有受信测试 Host 后，进一步暴露并纠正了测试对 diagnosis 展示 ID (`DX-*`) 的错误假设以及维护计划必须有 `planned_start` 的 fixture 缺项，最终原范围 5/5 与总套件 17/17 均通过。

### Remaining

- [x] 风险导向提高六个关键服务 floor
- [x] 工单/审批/平台/告警/运营视图真实数据库失败路径
- [x] commit/rollback、唯一约束、并发、幂等、权限和副作用失败
- [x] 保留快速 mock 测试并增加会在旧竞争实现上失败的回归
- [x] 全局、关键模块、changed-line 三层覆盖门禁均保持且通过
- [x] M-002 隔离 PostgreSQL 已在最终全局复验后按精确标签停止，并确认 `--rm` 删除及端口 `55438` 释放

## 3B. H-002 Full Production-path SLO Evidence (2026-08-20 12:04 +08:00)

Status: `DONE`

### Implementation

- `/api/v1/diagnoses` 与 `/api/v1/maintenance-plans` 的真实生产 service/API 路径保留共享查询构造器，并对总数、过滤总数、分页、页内 hydration 和所有关联集合执行固定查询预算。
- diagnosis priority 按互斥风险分支分别取 top-N，再以 `updated_at, id` 合并稳定排序；新增迁移 `0022_diagnosis_priority_indexes`，并由真实 `EXPLAIN` 硬断言 `ix_alarms_severity_id` 实际进入默认查询计划。
- Evidence 与 AgentExecution 每 Mission 仅返回最新 1 条并带截断元数据；Task 只返回 aggregate；Reservation/Resource 每 Mission/类型仅返回最新 1 条并带截断组计数。由已授权 Mission/WorkOrder FK 派生的有界 child 查询跳过重复全局策略编译，但范围授权回归继续证明跨租户数据不泄漏。
- 两个列表路由用 `orjson` 直接生成最终响应字节；Worker adapter 透传 `relatedDataBoundaries`。性能门禁测量真实 HTTP body，不再把分页 ID 行冒充响应体。
- 真实性能样本采用 warm-up + 每场景 100 次请求 + 独立 `tracemalloc` 请求；P95/P99 使用标准线性插值，同时保留 max、数据库/应用阶段和最慢 SQL label。

### Files Changed

- `backend/src/windops_backend/services/operational_views.py`
- `backend/src/windops_backend/api/operations.py`
- `backend/src/windops_backend/models.py`
- `backend/alembic/versions/0022_diagnosis_priority_indexes.py`
- `backend/tests/external/test_postgres_migrations.py`
- `backend/tests/{test_operational_views,test_bounded_collections,test_business_access_control,test_backup_recovery}.py`
- `backend/{pyproject.toml,uv.lock,requirements.container.txt}`
- `lib/production-domain-adapter.ts`
- migration head declarations and `docs/runbooks/collection-performance.md`

### Validation

- `PASS` — 真实固定镜像 PostgreSQL/TimescaleDB/pgvector 全套：12 tests / 0 failures / 0 errors / 0 skipped，138.688 s；JUnit：`backend/.artifacts/h002/postgres-contract-fullpath-final4.xml`。
- `PASS` — 10 万 Mission + WorkOrder + AssetHealthEvent 及病态扇出真实 HTTP 场景：diagnosis/filtered SQL 8，maintenance/filtered SQL 9；最差 p95 `451.815 ms`、最差 p99 `630.727 ms`；最大响应 `133,327 bytes`；最大 Python 峰值 `1,634,064 bytes`。
- `PASS` — page plan：diagnosis `57.956 ms`、filtered diagnosis `14.312 ms`、maintenance `0.805 ms`、filtered maintenance `16.694 ms`；新 severity index 真实使用且所有允许 sort 均为内存 sort。
- `PASS` — 运营视图/有界集合/业务范围 14 tests；发布/备份/迁移声明 27 tests；Node 相关 adapter/runtime 26 tests；Ruff、mypy strict、TypeScript typecheck、Prettier、container requirements lock check。
- `PASS` — Alembic 唯一 head `0022_diagnosis_priority_indexes`，全量 PostgreSQL offline SQL render 与真实主库 upgrade/current。
- `CLEANUP` — 精确容器 `windops-h002-fullpath-20260820` 在核对 `windops.project=wind-agent`、`windops.audit.issue=H-002` 后停止；其 `--rm` 清理完成并确认不存在，未操作其他项目容器。

### Remaining

- [x] 完整 production service/API 与最终 JSON 字节门禁
- [x] 高扇出有界摘要及可见截断元数据
- [x] 查询数、DB/application/E2E、p95/p99、内存和响应大小证据
- [x] 共享 builder 与查询计划/索引回归保护
- [x] 完整 PostgreSQL 外部套件 0 skip、静态/范围/adapter 回归和容器清理

## 3C. M-001 Standard Local Production Start Evidence (2026-08-20 12:18 +08:00)

Status: `DONE`

### Implementation

- `worker/index.ts` 接受标准 vinext 本地适配器可能传入的 `undefined` env，并在唯一入口归一化后将同一个对象传给 AsyncLocalStorage、production boundary 与 app handler。
- production boundary 在文档身份处理前验证完整配置；任何非法/缺失配置都由现有安全 envelope 返回，避免根页面先进入未捕获异常。有效 production 仍执行 Sites 身份/capability 门禁；HTTPS HSTS 行为保持不变。
- 本地没有 Cloudflare image bindings 时，`/_vinext/image` 返回结构化 `IMAGE_BINDINGS_NOT_CONFIGURED` 503，而不是再次解引用缺失 binding。
- 新增 `scripts/standard-start-smoke.mjs`：真实运行文档声明的 `pnpm start`，分别使用独立 Demo 与无效 production 进程，请求 `/` 和 `/api/runtime`，并在 Windows 用精确 PID `taskkill /T`、POSIX 用进程组 SIGTERM/SIGKILL 可靠清理。
- package script、README、质量门禁文档和 CI frontend job 同步；Node 合同锁定 CI 必须直接执行 `pnpm build && pnpm test:start-smoke` 以及入口归一化源码。

### Files Changed

- `worker/index.ts`
- `scripts/standard-start-smoke.mjs`
- `tests/production-runtime.test.mjs`
- `package.json`
- `.github/workflows/ci.yml`
- `README.md`
- `docs/testing-quality-gates.md`

### Validation

- `PASS` — 真实 `pnpm build && pnpm test:start-smoke`：默认 Demo `/` 200 HTML、`/api/runtime` 200 JSON；显式 production 且清空所有后端/密钥/release 配置时两者均返回 500 JSON、`INVALID_DELEGATION_SECRET`、`fixtureFallback=false`，无未捕获异常或 stack。
- `PASS` — production runtime 17/17，包含 CI 标准启动合同、既有身份/capability、未迁移路由、HSTS、配置拒绝、release 身份、gateway 与 production shell 回归。
- `PASS` — `pnpm typecheck`、完整 `pnpm lint`、相关 Prettier 与 `git diff --check`。
- `CLEANUP` — 每轮真实烟测后端口 3000 均释放；最终核对 `PORT_3000_FREE`、`NO_NODE_PROCESSES`，没有遗留本项目服务。

### Remaining

- [x] 缺失 env 统一归一化
- [x] 默认 Demo 标准产物 `/` 与 `/api/runtime` 非 500
- [x] 无效 production 配置结构化失败关闭
- [x] CI 直接标准启动命令而非自定义 E2E server
- [x] Windows/POSIX 可靠进程树清理与文档同步

## 3A. Independent Re-audit Validation Evidence (2026-08-19 21:20 +08:00)

The following commands were executed against the current worktree without trusting the earlier DONE rows.
The isolated PostgreSQL container, HTTPS FastAPI process, temporary TLS material and temporary image created
for the re-audit were stopped or removed after use. Ports 3000, 4179, 8443 and 55434 were verified free.

| Area | Result | Evidence |
| --- | --- | --- |
| Frontend quality | PASS | `pnpm typecheck`, `pnpm lint`, `pnpm format:check`; `pnpm test:coverage` — 134/134 Node tests, line 90.35%, branch 51.29%, function 33.03%, bundle budget passed. |
| Browser E2E | PASS | `pnpm test:e2e` — Chromium 6 passed, 1 explicitly skipped real-only spec in mock mode. |
| Real cross-layer E2E | PASS | `WINDOPS_E2E_REAL_BACKEND=1 pnpm test:e2e:real` — real Worker → FastAPI → PostgreSQL rotation smoke 1/1 passed over local TLS. |
| Backend regression | PASS WITH TEST-QUALITY FINDING | 247 tests collected; 234 passed and 13 external-release tests skipped in the ordinary suite; coverage 69.65% and current budget script passed. Low critical-module floors remain M-002. |
| Backend static quality | PASS | Ruff check/format (149 files), mypy strict (72 source files), Bandit (no findings), pip-audit `--skip-editable` (no known vulnerabilities), pnpm production audit (no known vulnerabilities). |
| PostgreSQL contracts | PASS WITH PERFORMANCE-EVIDENCE FINDING | Pinned TimescaleDB/PostgreSQL external suite 12/12 passed across migration, concurrency and prediction-lock files. The 100k test times only page-ID SQL, so its endpoint SLO claim remains H-002. |
| Migration | PASS | Alembic unique head `0021_ingest_source_secret_audits`, offline full SQL render, real empty-database upgrade/current. |
| Production build/image | PASS | `pnpm build`; digest-pinned backend Docker image `windops-reaudit2:local` built successfully with non-root runtime and was removed after inspection. |
| Release/workflow | PASS | Release pipeline tests, same-SHA required-check assertions, `git diff --check`, dependency audits and high-confidence tracked secret scan passed. |
| Standard local production start | FAIL | `pnpm start` listened on port 3000, but `/` and `/api/runtime` both returned 500 because `worker/index.ts` dereferenced an undefined `env`; tracked as M-001. |
| Knowledge-graph memory bound | FAIL | 50,000-Mission controlled `tracemalloc` probe measured 52,489,346 bytes against 27,216,670 accounted bytes (1.929x); tracked as H-001. |

### Independent Recheck and Adversarial Review

- Re-read `AGENTS.md`, the previous `AUDIT_REPORT.md`, `EXECUTION_GOAL.md` and this progress file, then mapped every earlier issue to current implementation and tests.
- Secret-reference validation, rotation gateway access, same-SHA release checks and real cross-layer E2E were independently reproduced and no longer remain in the active report.
- The knowledge-graph change is only partial: source rows are paged, but the configured memory ceiling undercounts current allocations by 1.929x in a production-shaped probe.
- The PostgreSQL performance test genuinely uses shared page-query builders, but still omits the rest of each production endpoint and serializes only ID rows; the prior endpoint-SLO completion claim was false.
- Standard `pnpm start` exposed a new 500 regression that build, Node tests and the custom E2E server do not cover.

### Current Audit Result (2026-08-19 21:20 +08:00)

- No current Critical was confirmed; 2 High and 2 Medium issues remain.
- Frontend/backend static gates, 134 Node tests, 234 ordinary backend tests, 12 real PostgreSQL tests, 6 mock-browser tests, 1 real cross-layer browser test, dependency audits and the approved-base container build passed.
- Passing tests do not override the two direct failed probes or the observed test-design gaps.
- Completion Gates are not satisfied. The next execution cycle must start from the regenerated `AUDIT_REPORT.md` and must not reuse the superseded DONE rows as completion evidence.
- Project and re-audit services remain stopped.

Historical issue records below are retained only as evidence of earlier execution. They are not current completion evidence.

---

# 4. Historical Issue Execution

## C-001 — 核心业务 API 未执行租户与资产范围授权

Severity: `Critical`  
Status: `DONE`

### Requirements

- 在 SQL 查询边界强制租户、风场、机组和实体范围，避免 Python/前端事后过滤。
- 单实体和全部写命令验证直接及关联对象归属，防止部分写入与事件残留。
- 范围规则覆盖列表、详情、聚合、count/cursor、事件/SSE、报告、资源、模型及跨域关系。
- 机器主体使用最小职责 allowlist，普通业务读取默认拒绝。
- 生产非全局人类主体必须具有显式 scope；global 必须显式、可审计。
- 增加至少两租户、两风场、多机组及人类/机器主体的正反向授权测试。

### Investigation

- 确认 `Principal` 已解析可信范围，但此前未传播到普通业务 ORM 查询或写命令。
- 确认请求路由和服务复用同一 `AsyncSession`，可在依赖层绑定服务端策略并用 ORM 查询事件统一下推。
- 逐类建立 Tenant/Farm/Turbine、Mission、Alarm、WorkOrder、Resource、Knowledge、Model、Report、Agent 与 DomainEvent 的归属规则。
- 发现 SQLite legacy transaction mode 下混合范围 mission batch 的第一项 SAVEPOINT 会在第二项失败前被提交；已在批量边界修复。

### Root Cause

- 身份范围解析、知识域授权和普通业务查询是三套分离路径；`require_read_access` 仅审计，不把范围绑定到 SQL。
- 机器角色与人类读取共用认证依赖，缺少业务读取 deny-by-default。
- DomainEvent 使用全局整数 sequence，过滤 payload 后仍会通过 cursor 间隙形成侧信道。
- 批量命令依赖外层会话回滚，但 SQLite SELECT 不显式 BEGIN，导致已释放 SAVEPOINT 形成部分提交。

### Changes

- 新增统一 `GraphAccessPolicy` -> SQLAlchemy ORM loader criteria，将租户/风场/机组/实体范围应用于核心模型查询、详情、count 和关联查询。
- 依赖层按端点强制 data-scope；未知受保护端点对受限 scope 失败关闭。
- 人类主体必须拥有显式业务范围；生产启动验证每个人类 identity mapping 都有 asset/entity/global grant。
- `scada_ingestor`、`eam_integrator` 普通业务读稳定返回 403，专用 role 端点保持可用。
- 全局控制面写命令使用显式、无限制 global grant；普通 scoped manager 不能写平台/模型/报告/Agent 全局对象。
- DomainEvent 在 SQL 层按 aggregate 归属过滤；受限用户使用绑定 subject + scope 的认证加密 opaque cursor，前端 SSE 客户端已支持持久化/恢复。
- dashboard 对受限主体不再暴露全局 sequence；读取审计记录服务端生效的 scope 快照。
- mission batch 在 SQLite 显式开启外层事务并在任何异常时回滚，保证越权混合批次零部分写入。

### Files Changed

- `backend/src/windops_backend/access_control.py`
- `backend/src/windops_backend/api/deps.py`
- `backend/src/windops_backend/api/{agents,assets,missions,model_registry,operations,system}.py`
- `backend/src/windops_backend/knowledge_graph/api.py`
- `backend/src/windops_backend/services/{dashboard,events}.py`
- `backend/src/windops_backend/config.py`
- `backend/example.env`
- `lib/{production-events,use-production-events}.ts`
- `backend/tests/test_business_access_control.py`
- `backend/tests/{test_configuration,test_security}.py`
- `tests/production-events.test.mjs`

### Tests Added / Changed

- 新增两租户、两风场、多机组列表/详情/聚合/count 与范围审计矩阵。
- 新增机器主体普通业务读取拒绝和 data-scope 跨域拒绝。
- 新增越界单写入、混合范围批量原子回滚、global 控制面写拒绝。
- 新增事件 payload 过滤、opaque cursor、主体/scope 绑定、raw sequence 拒绝与前端恢复解析测试。
- 新增生产 identity scope 启动失败关闭测试。

### Validation

Commands:

```bash
cd backend
uv run pytest tests -q --basetemp=.pytest-tmp/c001-full-2
uv run pytest tests/test_business_access_control.py tests/test_knowledge_graph_access.py tests/test_knowledge_ingestion.py tests/test_operational_hardening.py tests/test_security.py -q --basetemp=.pytest-tmp/c001-final
uv run ruff check src tests
uv run mypy src
uv run ruff format --check <C-001 changed Python files>
cd ..
pnpm test
pnpm run typecheck
pnpm run lint
pnpm exec prettier --check lib/production-events.ts lib/use-production-events.ts tests/production-events.test.mjs
```

Result:

- `PASS` — 后端完整收集 158 tests；156 passed / 2 个既有真实外部环境测试 skipped。
- `PASS` — C-001/knowledge graph/knowledge ingestion/operational hardening/security 定向回归。
- `PASS` — Ruff、mypy strict、C-001 Python format check。
- `PASS` — 前端 production build + 122 Node tests、typecheck、lint、相关 Prettier check。
- 环境说明：项目 `.pytest_cache` ACL 仍产生非功能性写缓存 warning；仓库内 `--basetemp` 验证正常。

### Remaining

- [x] 完成调用关系与数据归属调查
- [x] 实现统一范围策略与 SQL/命令传播
- [x] 添加两租户及机器主体测试
- [x] 针对性验证与完整回归

---

## H-001 — 平台配置可持久化并回显任意秘密值

Severity: `High`  
Status: `DONE`

### Requirements

- 为所有 configuration key 定义严格、版本化且拒绝未知字段的 schema。
- 递归、大小写不敏感地拒绝敏感键和疑似原始凭据，并限制配置大小。
- 只允许经过验证的 Secret Manager reference；配置、事件、审计、日志和响应不得含秘密。
- 完整配置仅管理角色可读；提供必要的脱敏运行状态。
- 扫描并可审计地处置历史 revision；修正硬编码 `secret_values_exposed` 声明。

### Investigation

- 确认请求 `value` 原为任意 JSON，服务只检查少量字段并原样持久化/回显。
- 确认完整配置 GET 同时暴露给所有人类业务角色，且固定声明未暴露秘密。
- 确认原始 PostgreSQL 备份会包含普通配置表，因此历史修订必须在新备份前完成脱敏与凭据轮换。

### Changes

- 为五个 configuration key 建立 schema version 1 严格 Pydantic 模型；未知字段、错误类型、非法组合、超大/过深/过多节点均失败关闭。
- 新增递归、NFKC/大小写/分隔符归一化的敏感键扫描，并识别私钥、JWT、Bearer/Basic、云连接凭据、带密码 URL 与常见凭据前缀。
- Secret Manager reference 仅接受四类外部 scheme，拒绝 userinfo、query、fragment、路径穿越、空路径与疑似原始凭据。
- 请求校验错误改为无输入回显 envelope，POST/GET/DomainEvent 不返回 secret reference 或提交值。
- 完整配置读取同时要求持久化读取归因与显式 global `operations_manager`；普通人类角色使用独立脱敏状态端点。
- 新增 `0018_platform_configuration_security`：数据库升级时先隔离明显历史秘密，并建立无秘密审计表；应用启动继续用严格 Python 扫描处理所有剩余历史修订。
- 历史疑似凭据修订被清空、停用并标记待轮换；生产 readiness 在轮换完成前返回 503。轮换确认只接受外部 reference 和非秘密变更证据。
- 删除硬编码 `secret_values_exposed`，响应只在严格安全序列化后声明 `secrets_redacted`，并报告隔离/轮换状态。
- 设置页使用各 key 的版本化合法模板并显示脱敏状态；新增凭据轮换、旧备份/导出处置 runbook。

### Files Changed

- `backend/src/windops_backend/platform_configuration.py`
- `backend/src/windops_backend/{schemas,models,main,access_control}.py`
- `backend/src/windops_backend/api/{operations,system}.py`
- `backend/src/windops_backend/services/platform_governance.py`
- `backend/alembic/versions/0018_platform_configuration_security.py`
- `backend/tests/test_platform_configuration_security.py`
- `backend/tests/{test_platform_governance,test_backup_recovery}.py`
- `backend/scripts/verify_migration_head.py`
- `components/pages/system-settings-page.tsx`
- `docs/runbooks/platform-configuration-secret-remediation.md`
- migration declaration/readiness documentation

### Tests Added / Changed

- 顶层/嵌套、大小写/Unicode/分隔符敏感键与原始凭据拒绝且响应不回显。
- 五类合法 schema、model governance 嵌套、未知字段、strict type、非法 reference、大小上限。
- 管理/非管理/global scope 读取矩阵与脱敏状态。
- 历史值隔离、无秘密审计、readiness 阻断、外部 reference 轮换确认、事件无秘密。
- 迁移 head、离线 SQL、备份 schema revision 与既有平台治理回归。

### Validation

Commands:

```bash
cd backend
uv run pytest tests -q --basetemp=.pytest-tmp/h001-full-final
uv run ruff check src tests alembic scripts
uv run ruff format --check <H-001 changed Python files>
uv run mypy src
uv run bandit -q -r src
uv run alembic heads
uv run alembic history
uv run alembic upgrade head --sql
uv run python scripts/verify_migration_head.py
cd ..
pnpm test
pnpm run typecheck
pnpm run lint
pnpm exec prettier --check <H-001 changed frontend/docs files>
```

Result:

- `PASS` — 后端收集 165 tests；163 passed / 2 个真实 PostgreSQL/发布环境测试仍按 H-002/H-003 跟踪为 skipped。
- `PASS` — 前端 production build + 122 Node tests、typecheck、lint、相关 Prettier。
- `PASS` — Ruff、mypy strict（68 source files）、Bandit。
- `PASS` — 唯一 Alembic head `0018_platform_configuration_security`、完整 history、全量 PostgreSQL 离线 SQL 与声明校验。
- 环境说明：项目 `.pytest_cache` ACL warning 不影响仓库内 `--basetemp` 测试执行。

### Remaining

- [x] 严格版本化 schema 与递归秘密拒绝
- [x] 安全持久化、事件与响应序列化
- [x] 管理读取权限与脱敏状态
- [x] 历史扫描、脱敏、审计、轮换 gate 与操作手册
- [x] 定向和完整回归

---

## H-002 — 生产 PostgreSQL 迁移与并发路径没有非跳过 CI 门禁

Severity: `High`  
Status: `DONE`

### Requirements

- CI 启动版本固定、生产兼容的 PostgreSQL/TimescaleDB/pgvector。
- 在真实数据库验证空库和上一受支持 revision 到 head 的升级、数据兼容、扩展/约束/索引。
- PostgreSQL prediction lock、关键事务、Outbox 并发与唯一性测试成为非跳过门禁。
- 保留 SQLite 快速测试但不以其替代生产数据库门禁，并验证迁移失败/重试 runbook。

### Investigation

- 确认原 CI 仅运行 SQLite 测试，两个 PostgreSQL 外部测试默认 skip，且没有 TimescaleDB/pgvector 服务。
- 核实选定镜像的 PostgreSQL 16.14、TimescaleDB 2.29.1 和 pgvector 0.8.6 实际版本，并将镜像锁定到不可变 digest。
- 在真实 PostgreSQL 中发现第二连接建立约需四秒；测试改为先同步确认连接就绪，再测量 advisory lock 阻塞，避免把连接延迟误判为锁失效。
- 用受控冲突对象验证 Alembic DDL 失败会事务回滚，revision 与新列均保持在上一版本，清除受控冲突后可安全重试。

### Changes

- 新增独立 `postgres-contract` CI job，固定 TimescaleDB HA 镜像 digest，并对任何 skip 失败关闭。
- 在隔离数据库验证空库升级，以及从受支持 revision `0015_alarm_command_state` 经 `0017`、受控失败/回滚/重试到 head。
- 验证 PostgreSQL 16、TimescaleDB、pgvector、SCADA hypertable、`vector(1536)`、HNSW、关键约束与代表性历史数据兼容。
- 将 Outbox 原子 claim、命令回执唯一约束、mission 审批并发冲突和 prediction advisory lock 三次重复纳入真实数据库门禁。
- 保留默认 SQLite 快速套件；专用 PostgreSQL job 生成 JUnit 并上传证据，0 skip 才能通过。
- 新增迁移失败/事务确认/恢复/重试 runbook，并由测试检查 CI 固定镜像、门禁环境和 runbook 失败关闭要求。

### Files Changed

- `.github/workflows/ci.yml`
- `backend/docker-compose.yml`
- `backend/tests/conftest.py`
- `backend/tests/external/test_postgres_migrations.py`
- `backend/tests/external/test_postgres_concurrency.py`
- `backend/tests/external/test_postgres_prediction_lock.py`
- `backend/tests/test_ops_configuration.py`
- `docs/runbooks/postgresql-migration-recovery.md`
- `docs/runbooks/release-acceptance.md`

### Tests Added / Changed

- 空库、上一受支持 revision、历史数据、扩展、hypertable、vector/HNSW、约束与索引合同测试。
- 迁移受控失败后的原子回滚、仅清理受控冲突并重试到 head。
- Outbox、CommandReceipt 唯一性、mission approval 事务和三轮 prediction lock 真实并发测试。
- pytest session 级 fail-on-skip 门禁及 CI/runbook 静态合同测试。

### Validation

Commands:

```bash
docker run --rm -d --name windops-h002-postgres -p 127.0.0.1:55432:5432 <fixed-digest-image>
cd backend
uv run alembic upgrade head
uv run pytest tests/external/test_postgres_migrations.py tests/external/test_postgres_concurrency.py tests/external/test_postgres_prediction_lock.py -m external_release -q --junitxml=.pytest-tmp/postgres-contract-junit-final2.xml --basetemp=.pytest-tmp/h002-postgres-final2
uv run pytest tests -q --basetemp=.pytest-tmp/h002-full
uv run pytest tests/external/test_postgres_migrations.py -m external_release -q --basetemp=.pytest-tmp/h002-skip-negative  # with WINDOPS_FAIL_ON_SKIPPED=1 and contract opt-in absent; expected exit 1
uv run ruff check src tests alembic scripts
uv run ruff format --check <H-002 changed Python files>
uv run mypy src
uv run python scripts/verify_migration_head.py
pnpm exec prettier --check <H-002 changed YAML/Markdown files>
```

Result:

- `PASS` — 固定 digest 的临时真实数据库完成主库迁移；服务实际报告 PostgreSQL `16.14`、TimescaleDB `2.29.1`、pgvector `0.8.6`。
- `PASS` — 专用 PostgreSQL JUnit：8 tests / 0 failures / 0 errors / 0 skipped；包含空库、上一版本、失败回滚/重试和全部并发合同。
- `PASS` — 默认快速后端套件完整收集 173 tests；其中 9 个外部测试只在默认无服务模式 skip，强制专用 job 已证明 0 skip。
- `PASS` — 负向门禁确认任一 external-release skip 强制 pytest 退出 1。
- `PASS` — Ruff、H-002 Python format、mypy strict（68 source files）、Prettier、git diff check、唯一 Alembic head `0018_platform_configuration_security`。
- 临时容器以 `--rm` 启动，验证后已停止并确认删除；未操作其他容器。

### Remaining

- [x] 固定生产兼容的 PostgreSQL/TimescaleDB/pgvector 服务
- [x] 空库、旧 revision、历史数据、扩展与索引验证
- [x] prediction lock、关键事务、Outbox 和唯一性非跳过门禁
- [x] 迁移失败、回滚确认和安全重试 runbook
- [x] 完整快速回归与真实数据库 JUnit 证据

---

## H-003 — CI 不产出或验证可部署、可追溯的生产制品

Severity: `High`  
Status: `DONE`

### Requirements

- 受保护 release pipeline 使用批准的固定基础镜像 digest，从同一 commit 构建所需镜像。
- 生成并验证不可变 digest、SBOM、签名/attestation、commit/release labels。
- 验证非 root、入口点、健康/ready、迁移、依赖 lock 和最小启动 smoke。
- 用真实 digest 渲染/校验所有 Kubernetes workload/job，并运行隔离发布环境验收。
- 保存 commit 到镜像、清单、环境的证据；release gate 对缺失证据失败关闭。

### Investigation

- 确认原 CI 没有制品构建，Docker/Kubernetes 默认全零 digest 只承担失败关闭占位作用。
- 复核既有 release evidence 与 deployment policy：内容寻址和缺项失败关闭已有良好基础，但没有流水线产生真实报告。
- 本机构建发现 Bookworm 只安装 `pg_dump` 15，不能备份 PostgreSQL 16；批准基础镜像调整为固定 digest 的 Python 3.12.11/Trixie，实测提供 PostgreSQL client 17。
- 第一次最小 smoke 误要求 development 响应暴露仅 production 才有的 release headers；保留真实 production external test 的逐字段身份校验，最小 smoke 专注迁移/启动/health/ready。
- 第一次真实 `kubectl kustomize` 暴露 `commonLabels` 会污染 NetworkPolicy peer selector；改用 `labels.includeSelectors=false`，避免依赖 egress 被意外阻断。

### Changes

- 新增受 `production-release` environment 保护的 release workflow；只允许 `main` 同一 commit，且要求 frontend/backend/postgres-contract prior checks 全部成功。
- 所有 release workflow Action 固定到完整 commit；基础镜像、Dockerfile frontend 和隔离依赖镜像固定到不可变 digest。
- 从同一镜像支持 API、Dramatiq worker、outbox relay、migration 与 backup，构建并推送后只使用 registry digest。
- 流水线生成 GitHub provenance，执行 Cosign keyless sign/verify、Trivy CRITICAL/HIGH 阻断扫描、SPDX SBOM attestation/verify。
- 新增容器制品验证器，强制 OCI source/release/commit/base labels、UID/GID 10001、默认命令、HEALTHCHECK、所有入口点、迁移文件、hash lock、pip check、无 pytest 与 PG16+ 客户端。
- 新增镜像迁移和 hardened smoke：read-only rootfs、drop all capabilities、no-new-privileges、镜像内 Alembic、health/readiness 与 Docker health。
- 新增确定性清单 renderer，将 5 个 workload/job 绑定同一 image digest、release ID 和 commit；deployment policy 同时验证 annotations 和 server-owned runtime env。
- 修复 Kustomize 标签对 NetworkPolicy selector 的副作用；真实渲染结果保持 default-deny、runtime egress 与 dependency selector 语义。
- 受保护的隔离 production 配置严格 base64/UTF-8/allowlist 导入；external release 测试任何 skip 失败，候选镜像执行 verified backup subset。
- 保存 commit -> image -> rendered manifest -> isolated environment JUnit 的摘要链及 Sites expected release bindings；既有最终 release gate 继续对十一类缺失/篡改证据失败关闭。

### Files Changed

- `.github/workflows/release.yml`
- `backend/Dockerfile`
- `backend/docker-compose.yml`
- `backend/deploy/release-policy.json`
- `backend/deploy/kubernetes/kustomization.yaml`
- `backend/src/windops_backend/operations/{container_artifact,release_smoke,deployment_policy}.py`
- `backend/scripts/{render_release_manifests,load_release_environment}.py`
- `backend/pyproject.toml`
- `backend/tests/{test_container_artifact,test_release_pipeline,test_deployment_policy,test_deployment_manifests}.py`
- `backend/deploy/README.md`
- `docs/runbooks/release-acceptance.md`

### Tests Added / Changed

- 固定 release policy、镜像 inspect 正反向、root/command/health/label/digest drift 拒绝测试。
- protected workflow 权限、Action SHA、prior checks、build/provenance/sign/scan/SBOM/smoke/render/external/backup/evidence 合同测试。
- protected environment 严格解析、缺项/非 production/非 WINDOPS/重复项拒绝测试。
- 所有 workload release identity 一致及任一 annotation/env drift 失败测试。
- Dockerfile、依赖 compose、Kustomize selector-safe 标签与既有 manifest/release gate 回归。

### Validation

Commands:

```bash
docker build --build-arg PYTHON_BASE_IMAGE=python:3.12.11-slim-trixie@sha256:47ae... --build-arg WINDOPS_RELEASE_ID=windops-h003-local --build-arg WINDOPS_COMMIT_SHA=<HEAD> --build-arg WINDOPS_SOURCE_URL=https://github.com/local/wind-agent -t windops-h003:trixie backend
cd backend
uv run pytest tests/test_container_artifact.py tests/test_release_pipeline.py tests/test_deployment_policy.py tests/test_deployment_manifests.py tests/test_release_gate.py -q --basetemp=.pytest-tmp/h003-final
uv run pytest tests -q --basetemp=.pytest-tmp/h003-full
uv run ruff check src tests alembic scripts
uv run ruff format --check <H-003 Python files>
uv run mypy src
uv run bandit -q -r src
uv run python scripts/export_container_requirements.py --check
uv run windops-release-smoke <local candidate and isolated digest-pinned PostgreSQL/Neo4j>
kubectl kustomize deploy/kubernetes
uv run python scripts/render_release_manifests.py <release identity and local digest>
uv run windops-deployment-policy <rendered manifest and release identity>
pnpm exec prettier --check <H-003 YAML/JSON/Markdown files>
```

Result:

- `PASS` — 固定 Trixie digest 候选镜像构建成功；镜像 ID `sha256:a6f8096d...`，OCI commit/source/release/base labels 与输入一致。
- `PASS` — 容器 UID/GID 10001、默认 API、HEALTHCHECK、六个所需 entrypoint、hash lock、pip check、无 pytest，`pg_dump 17.11`。
- `PASS` — 临时隔离 PostgreSQL/Neo4j 中镜像内迁移到 `0018`，read-only/non-root/cap-drop/no-new-privileges API health、ready 与 Docker health 全部通过。
- `PASS` — 真实 Kustomize 14 resources / 5 workloads 全部使用同一非占位 digest/release/commit；deployment policy 通过且无 `registry.invalid`、零 digest、unreleased/unknown。
- `PASS` — H-003 定向 37 tests；后端完整收集 188 tests，179 passed / 默认模式下 9 个真实外部门禁 skipped。
- `PASS` — Ruff、mypy strict（70 source files）、Bandit、container lock reproducibility、Prettier 与 git diff check。
- Registry push、keyless signature、attestation、Trivy 与受保护真实 provider 环境由新增 protected workflow 在每次候选发布中执行；缺少 registry/environment secret 或任何证据时流水线失败关闭。本地无权伪造这些外部证据。
- 临时 `windops-h003-smoke` containers、network 和 volumes 已按项目标签核对后删除；未操作其他容器。

### Remaining

- [x] 批准且固定 digest 的基础镜像与受保护 release pipeline
- [x] 同 commit 镜像、SBOM、签名/attestation、扫描和 OCI metadata
- [x] 非 root、入口点、health/ready、迁移、lock 与启动 smoke
- [x] 五类 workload/job 真实 digest render 与策略校验
- [x] 隔离 production acceptance、backup subset 与证据链门禁

---

## H-004 — 核心集合全表加载并被 Worker 多页汇聚

Severity: `High`  
Status: `DONE`

### Requirements

- 将权限、筛选、排序、计数和稳定分页下推 SQL，关联查询仅与当前页规模相关。
- 资源、健康、事件等集合提供有界 limit/cursor；健康查询只取所需最新/聚合数据。
- Worker 透传分页且不自动汇聚 100 页；全量导出改为异步/流式流程。
- 知识图谱投影分批、增量或可恢复，并设置内存/批次/运行时上限。
- 核对索引与查询计划，建立响应大小、查询数、P95/P99 和内存门槛。

### Investigation

- 确认诊断和维护视图此前先加载全量主记录与关联对象，再在 Python 过滤、排序和分页；资源及健康接口也会读取全量关联历史。
- 确认 Worker `backendCollection` 最多顺序拉取 100 页并聚合到单个响应，抵消后端分页边界。
- 确认知识图谱一次性 `.all()` 读取十三类领域表，缺少源记录、节点、关系、估算内存和运行时上限。
- 在真实 PostgreSQL 10 万级数据上检查查询计划；首次健康查询计划未使用复合索引，据此把索引修正为 `(turbine_id, recorded_at DESC, id DESC)` 并采用分页机组的 `LATERAL` top-2 查询。
- 确认现有报告导出使用持久化快照/摘要，不需要为原始全量集合保留同步 fan-in。

### Root Cause

- 生产集合沿用了演示视图的“先构造完整数据集”模式，分页只发生在响应层。
- Worker 为满足完整集合契约主动遍历游标，放大了数据库、网络和内存成本。
- 图投影没有资源预算，且关键筛选/排序缺少与访问模式一致的复合索引和执行计划门禁。

### Changes

- 将诊断/维护的搜索、状态、风险、团队、天气、权限、排序、计数和分页统一下推 SQL；稳定排序且 offset 有上限，仅为当前页批量读取关联记录。
- 资源与天气分别提供有界 cursor/limit；只加载当前页资源的 reservation/work-order。健康历史使用复合 keyset，健康评估使用 SQL 状态/风险过滤、当前页 latest-two 和 active-alarm 聚合。
- Worker 每个集合请求只代理一页，保留 backend total/cursor/has-more；删除 100 页循环和调用端聚合选项。
- 知识图谱源读取改为 `yield_per` 分批流式处理，并设置 source rows、nodes、relationships、估算 JSON 内存和 runtime 硬上限；超限失败不安装部分 snapshot，Outbox 租约/重试保持恢复能力。
- 新增 `0019_bounded_collection_indexes`，覆盖 mission/work-order/health/resource/reservation/weather 的生产查询路径，并同步模型索引声明和 migration head 文档。
- 新增集合性能 runbook，明确无隐式全量导出、治理报告使用持久化产物，以及响应、查询计划、延迟和图投影预算。

### Files Changed

- `backend/src/windops_backend/services/operational_views.py`
- `backend/src/windops_backend/api/{operations,resources,assets}.py`
- `backend/src/windops_backend/knowledge_graph/{projection,service,api}.py`
- `backend/src/windops_backend/{config,main,models,outbox,workers}.py`
- `backend/src/windops_backend/api/deps.py`
- `backend/alembic/versions/0019_bounded_collection_indexes.py`
- `backend/tests/test_bounded_collections.py`
- `backend/tests/external/test_postgres_migrations.py`
- `backend/tests/{test_business_access_control,test_knowledge_graph,test_backup_recovery,test_ops_configuration}.py`
- `lib/production-domain-adapter.ts`
- `tests/production-runtime.test.mjs`
- `.github/workflows/ci.yml`
- `backend/example.env`
- `docs/runbooks/collection-performance.md`
- migration/release declaration documentation

### Tests Added / Changed

- SQL statement capture 证明主查询含 limit、页关联使用 page mission IDs、查询数固定且响应小于 512 KiB。
- 精确筛选重复请求验证 diagnosis/maintenance 的 SQL count、status/risk/team/window/query 语义。
- 资源/天气独立 cursor、健康历史复合 cursor、健康评估 SQL 状态/风险和 latest-two 回归。
- Worker 单页代理测试断言只调用一次后端并保留 total/cursor/has-more。
- 图投影 batch-size 1 正常，source cap 超限后旧 snapshot 仍可读且未安装部分结果。
- 真实 PostgreSQL 生成 100 个机组和 10 万级领域记录，验证三个关键计划的指定索引、无意外 Sort，并输出 P95/P99/响应字节 JUnit 属性。

### Validation

Commands:

```bash
cd backend
uv run pytest tests/test_business_access_control.py tests/test_bounded_collections.py tests/test_knowledge_graph.py tests/test_operational_views.py -q --basetemp=.pytest-tmp/h004-target
uv run pytest tests -q --basetemp=.pytest-tmp/h004-full
WINDOPS_DATABASE_URL=<isolated-postgres> uv run alembic upgrade head
WINDOPS_RUN_POSTGRES_CONCURRENCY_TESTS=1 WINDOPS_FAIL_ON_SKIPPED=1 uv run pytest tests/external/test_postgres_migrations.py tests/external/test_postgres_concurrency.py tests/external/test_postgres_prediction_lock.py -m external_release -q --junitxml=.pytest-tmp/h004-postgres-contract-final2.xml --basetemp=.pytest-tmp/h004-postgres-final2
uv run ruff check src tests alembic scripts
uv run ruff format --check <H-004 changed Python files>
uv run mypy src
uv run bandit -q -r src
uv run alembic upgrade head --sql
uv run python scripts/verify_migration_head.py
cd ..
pnpm test
pnpm run typecheck
pnpm run lint
pnpm exec prettier --check <H-004 changed frontend/docs files>
```

Result:

- `PASS` — H-004 定向 19 tests；后端完整测试套件退出 0。
- `PASS` — 真实 PostgreSQL 合同 9 tests / 0 failures / 0 errors / 0 skipped；唯一 head `0019_bounded_collection_indexes`。
- `PASS` — 10 万级数据计划使用 `ix_missions_updated_id`、`ix_work_orders_planned_id`、`ix_asset_health_turbine_recorded_id` 且无额外 Sort。
- `PASS` — diagnosis P95 `1.016 ms` / P99 `1.552 ms` / `10294 bytes`；work-order P95 `0.951 ms` / P99 `1.334 ms` / `7950 bytes`，均低于 500 ms / 1000 ms / 512 KiB 门槛。
- `PASS` — 前端 production build + 122 Node tests、typecheck、lint；Worker 单页分页合同通过。
- `PASS` — Ruff、H-004 Python format、mypy strict（70 source files）、Bandit、migration offline render、Prettier 与 git diff check。
- 首次全 external 调用因本地主数据库未先执行 CI 中的 Alembic step 而失败；补齐与 CI 相同的 `upgrade head` 后原命令 9/9 通过，归类为调用环境顺序错误而非代码失败。
- 临时 `windops-h004-postgres` 容器使用精确项目标签和 `--rm`，停止后确认删除；未操作已有其他容器。

### Remaining

- [x] SQL 下推、稳定分页和页级关联加载
- [x] 资源、天气、健康有界 cursor 与聚合
- [x] Worker 单页透传和无同步全量 fan-in
- [x] 图投影分批、资源预算、原子失败与恢复路径
- [x] 生产索引、10 万级 EXPLAIN、P95/P99/响应预算
- [x] 定向、真实 PostgreSQL和完整前后端回归

---

## M-001 — 委托 JWT 的 jti 未防重放，部分副作用 POST 无幂等保护

Severity: `Medium`  
Status: `DONE`

### Requirements

- 原子消费写请求委托 `jti` 并按 token 到期设置 TTL；生产 replay store 故障时失败关闭。
- 对可重试副作用 POST 统一持久化 Idempotency-Key 结果，相同 key 不同 payload 冲突。
- comment 与外部副作用返回稳定重放结果，审计区分首次、幂等重放和恶意重放。
- 覆盖并发、过期、时钟偏差、清理和多实例行为。

### Investigation

- 确认委托 JWT 已绑定签名、issuer/audience、method、target、body hash 和短 `exp`，但后端只校验 `jti` 存在，未持久化或消费。
- 枚举 OpenAPI 的全部副作用 POST；除已有 `source_event_id` 唯一传输键的 SCADA ingest 外，comment、审批、资源、配置、报告、模型、EAM callback、Agent、知识与图谱等路径原先没有统一 header/receipt 边界。
- 确认旧 `CommandReceipt` 唯一键只有 command type + key，不能按主体和目标正确隔离；报告与 Agent Tool 的旧实现还会在执行副作用后才碰唯一约束，存在并发重复执行窗口。
- 确认 Worker 已能绑定每次请求生成的新委托 JWT；因此安全网络重试应复用命令 key、由 Worker 重新签发一次性 `jti`，而不是重用已消费 bearer。

### Root Cause

- 委托认证只实现了无状态请求绑定，没有共享实例间的原子 nonce 状态和故障关闭策略。
- 幂等能力按端点零散实现，scope、请求规范化、稳定响应、并发预留与审计语义不一致；前端网络错误也没有保留同一 key 的重试契约。

### Changes

- `VerifiedIdentity` 严格解析非空/限长 `jti` 和有限数值 `exp`；所有委托 `POST/PUT/PATCH/DELETE` 在业务事务前用独立 PostgreSQL 事务原子插入 SHA-256 nonce，读请求明确允许重放。
- 新增 nonce 与 replay audit 表、过期索引和 migration `0020`；nonce 保留到 `exp + clock skew + 1s`，每次消费有界清理 500 条过期记录。唯一冲突返回 401，store SQL 故障返回 503，并记录固定 label Prometheus 指标和无 token/jti 日志。
- 将 command receipt 唯一 scope 扩展为 subject + command type/endpoint + target + key，保存规范化请求 hash、稳定响应、replay count 与最后重放时间；统一 helper 在任何领域/外部副作用前预留 receipt，同 payload 稳定重放、不同 payload 409。
- 所有 OpenAPI POST 除 SCADA 明确例外外均要求 `Idempotency-Key`；comment、审批、工单、EAM callback、资源、配置、报告、模型、知识、图谱、Agent 和 presign 等路径均纳入相同事务边界。mission batch 增加父命令 receipt，防止同 key 追加/替换批次内容。
- 报告和 Agent Tool 修复“副作用后插入唯一记录”的并发窗口；首次/重放返回体完全一致，真实重放只通过 `Idempotency-Replayed` header 和 receipt 审计表示。
- EAM Outbox 继续向下游发送稳定 `windops:{work_order_id}`；在线模型调用使用稳定 deployment/turbine/input digest key，批处理逐位置派生子键并支持部分进度安全恢复。
- 前端每个 POST 自动生成 key，传输失败只使用同一 body/key 重试一次；comment 改用统一 client，生产网关双向透传 `Idempotency-Key` 与 `Idempotency-Replayed`。
- 新增运行手册，明确写 nonce、可重放读取、清理/保留、故障关闭、响应丢失、下游边界和事故调查契约。

### Files Changed

- `backend/src/windops_backend/{identity,models,observability}.py`
- `backend/src/windops_backend/api/{deps,agents,alarms,assets,knowledge,missions,model_registry,operations,resources,work_orders}.py`
- `backend/src/windops_backend/knowledge_graph/api.py`
- `backend/src/windops_backend/services/{idempotency,missions,alarms,reports}.py`
- `backend/alembic/versions/0020_delegated_replay_and_idempotency.py`
- migration head declarations、backup/release documentation
- `lib/{api-client,production-runtime}.ts`
- `components/pages/mission-detail-page.tsx`
- `backend/tests/test_replay_and_idempotency.py`
- `backend/tests/external/{test_postgres_concurrency,test_postgres_migrations}.py`
- 相关端点/身份/EAM/模型/图谱/知识/平台回归测试
- `tests/{api-client-idempotency,production-runtime}.test.mjs`
- `docs/runbooks/delegated-replay-and-command-idempotency.md`

### Tests Added / Changed

- 相同委托 JWT 串行/并发仅一次写入；相同读 JWT 可重复读取；accepted/replayed 审计与行数精确断言。
- replay store 故障 503、指标增长；过期 nonce 有界清理、`exp` 宽限窗口内仍不可重放。
- comment、mission/batch、alarm、report、Agent Tool、EAM、knowledge 等同 key/同 payload 完全稳定响应；同 key/不同 payload 明确冲突。
- OpenAPI 契约测试保证所有副作用 POST 都有 required header，SCADA 仅以持久唯一 source event 明确豁免。
- 浏览器 client 模拟“后端已提交但响应丢失”，验证自动/显式 key 的两次请求 URL、body 和 key 完全相同。
- 真实 PostgreSQL 两个独立 FastAPI 实例同时消费同一 JWT，精确得到一次 accepted/一次 replayed；两个 session 同时执行命令，精确得到一个 receipt、一个领域事件和相同响应。

### Validation

Commands:

```bash
cd backend
uv run pytest tests/test_replay_and_idempotency.py tests/test_agent_governance.py tests/test_generic_business_api.py tests/test_alarm_commands.py tests/test_platform_governance.py tests/test_operational_views.py tests/test_eam_integration.py tests/test_model_runtime.py tests/test_knowledge_ingestion.py tests/test_knowledge_graph_access.py -q --basetemp=.pytest-tmp-m001-targeted
uv run pytest tests -q --basetemp=.pytest-tmp-m001-full
WINDOPS_DATABASE_URL=<isolated-postgres> uv run alembic upgrade head
WINDOPS_RUN_POSTGRES_CONTRACT_TESTS=1 WINDOPS_RUN_POSTGRES_CONCURRENCY_TESTS=1 WINDOPS_FAIL_ON_SKIPPED=1 uv run pytest tests/external/test_postgres_migrations.py tests/external/test_postgres_concurrency.py tests/external/test_postgres_prediction_lock.py -m external_release -q --junitxml=.artifacts/m001/postgres-contract.xml --basetemp=.pytest-tmp-m001-postgres-2
uv run alembic current
uv run python scripts/verify_migration_head.py
uv run ruff check src tests alembic scripts
uv run ruff format --check src tests alembic scripts
uv run mypy src
uv run bandit -q -r src
cd ..
pnpm test
pnpm run typecheck
pnpm run lint
pnpm exec prettier --check <M-001 frontend/docs files>
```

Result:

- `PASS` — M-001 定向 43 tests；新增 replay/idempotency 套件 6/6；后端完整收集 200 tests，188 passed / 默认模式下 12 个真实外部门禁 skipped。
- `PASS` — 固定 digest TimescaleDB/PostgreSQL 16 隔离实例执行 `upgrade head` 到 `0020`；真实迁移、Outbox、审批、预测锁、两实例 nonce/command 并发共 11 tests / 0 skipped，JUnit 保存在 `.artifacts/m001/postgres-contract.xml`。
- `PASS` — 前端 production build + 124 Node tests；响应丢失复用 key 和 gateway replay header 透传通过。
- `PASS` — Ruff lint/全量 format、mypy strict（71 source files）、Bandit、typecheck、ESLint、M-001 Prettier 与 `git diff --check`。
- `.pytest_cache` 仍只有既有 ACL 写缓存 warning；所有功能测试使用仓库内独立 `--basetemp` 正常通过。
- 临时 `windops-m001-postgres` 使用固定镜像摘要、精确名称与 `windops.audit.issue=M-001` 标签；停止后再次查询确认已自动删除，未操作其他容器。

### Remaining

- [x] 写委托 nonce 原子消费、TTL/时钟偏差与 store 故障关闭
- [x] subject/endpoint/target/hash 统一持久幂等契约
- [x] comment、batch、报告、Agent 与外部 EAM/模型等副作用稳定重放
- [x] 首次、幂等重放、恶意 token 重放的可观测审计
- [x] 串行、并发、过期、清理、响应丢失和真实 PostgreSQL 多实例测试
- [x] 完整前后端、安全、迁移和格式回归

---

## M-002 — 覆盖率只记录不门禁，关键服务与浏览器流程测试不足

Severity: `Medium`  
Status: `DONE`

### Requirements

- 全局覆盖率不低于当前基线，并为高风险模块设置更高门槛/差异覆盖。
- 为授权、回滚、并发、幂等、外部失败、超时、游标和 side-channel 补行为测试。
- 建立桌面和 390 px 真实浏览器 E2E，覆盖角色、关键流程及错误/重试/SSE。
- 纳入非跳过 PostgreSQL 门禁并建立前端 bundle 预算。

### Investigation

- 重算前端 V8 基线为 line `90.18%` / branch `50.98%` / function `33.33%`；生产客户端基线为 91 chunks / 2,558,782 bytes，最大 digital-twin chunk 645,279 bytes。
- 重算当前完整后端为 9,724 statements / 3,042 missed / `68.72%`；完整工作树 7,498 条变更可执行行命中 4,936 条，差异覆盖率 `65.83%`。
- 确认既有 CI 只记录 coverage、真实浏览器套件不存在；另发现初版 CI 的 `--cov-report=json=...` 与当前 pytest-cov 不兼容并修正为冒号语法。
- Chromium 首轮真实交互发现移动用户菜单零尺寸、审批双击产生两个不同幂等键、320 px 顶栏溢出；均作为真实回归修复后再复跑。

### Root Cause

- coverage 与大 chunk 仅输出报告/警告，没有可执行预算；关键低覆盖模块可继续下降。
- Node/SSR 契约无法验证 hydration、点击竞态、Sites 身份流程、EventSource 重连或真实 CSS 几何。
- CI 没有独立浏览器 job 和浏览器失败证据制品。

### Changes

- 新增后端全局 68%、完整工作树差异 65.5%、高保证模块 80/90% 与审计点名风险模块 measured-floor 门禁；解析零上下文 diff 并只统计 Coverage.py 可执行行。
- 前端 V8 门槛设为 line 89 / branch 49 / function 32；bundle 门槛为 total 2,700 KiB、single 675 KiB、最多一个 >500 KiB chunk。
- 引入 Playwright 1.62.1、production Worker/后端合同测试 harness、桌面/移动 Chromium 套件和 390 px 截图基线。
- 浏览器覆盖匿名/机器拒绝、四个人类角色、刷新/登出、告警→Mission→审批→工单、双击、401/403/503/network、loading/empty/success/retry、SSE cursor resume、320/360/390/430 px 几何和键盘激活。
- CI 新增 immutable-action browser job，安装隔离 Chromium，保存 HTML report、截图、trace 和失败视频；真实 PostgreSQL job 保持 digest 固定且 `WINDOPS_FAIL_ON_SKIPPED=1`。

### Files Changed

- `.github/workflows/ci.yml`
- `package.json`, `pnpm-lock.yaml`, `playwright.config.ts`
- `scripts/check-bundle-budget.mjs`, `scripts/e2e-production-server.mjs`
- `tests/{bundle-budget,identity-capability,api-client-idempotency,production-runtime}.test.mjs`
- `tests/e2e/identity-and-mobile.spec.ts`, `tests/e2e/__screenshots__/dashboard-p1-incident-390.png`
- `backend/scripts/check_coverage_budget.py`
- `backend/tests/{test_coverage_budget,test_replay_and_idempotency,test_release_pipeline}.py`
- `docs/testing-quality-gates.md`

### Validation

- `PASS` — 后端完整 200 collected：188 passed / 默认模式 12 external-release skipped；总覆盖率 `68.72%`，模块 floor 通过。
- `PASS` — 当前完整工作树 diff coverage `65.83%`，高于 65.5% 真实 no-regression 门槛。
- `PASS` — Playwright Chromium 6/6；production build、bundle budget、typecheck 和定向 Node/后端门禁测试通过。
- `PASS` — CI YAML 解析、immutable action 与 browser/coverage/PostgreSQL 结构契约通过。
- `PASS` — `pnpm test:coverage`：production build、bundle budget、133 Node tests / 0 skip；V8 line `90.35%` / branch `51.29%` / function `33.00%`，均高于门槛。
- `.pytest_cache` 仅保留已知 Windows ACL warning；功能测试使用独立 `--basetemp` 正常。

Validation: `PASS`

---

## M-003 — 生产前端不感知登录身份与角色能力

Severity: `Medium`  
Status: `DONE`

### Requirements

- production shell 在读取业务数据前执行服务端身份门禁，demo 保持本地可用。
- 由可信服务端返回最小 capability 集合；导航和动作按 capability 表达但不替代后端授权。
- 区分并可恢复地处理 401、403、后端未就绪与普通网络失败。
- 对设置、告警、mission、工单、资源和模型建立角色/能力矩阵与桌面/移动 E2E。

### Investigation

- 确认 Sites 身份此前仅用于 API 委托，shell/layout 不调用现有 ChatGPT user helper，角色与 capability 不进入可信 UI 合同。
- 枚举设置、告警、Mission、工单、资源和模型所有生产动作；确认机器角色不得进入业务 shell。
- 真实浏览器首轮发现移动 CSS 同时隐藏头像与身份文案，登出链接变成零尺寸；审批双击也可在 pending 渲染前进入两次。

### Root Cause

- 缺少服务端 session bootstrap 和内存 capability context；页面只能等 mutation 后端返回 403。
- 移动选择器 `.user-menu > span` 把 Avatar 也隐藏；mutation 只依赖异步 React pending 状态阻止重复点击。

### Changes

- FastAPI 新增 `/api/v1/session` 和 server-owned 最小 capability 计算；机器身份失败关闭，范围继续决定 view capability。
- production Worker 在任何业务 document render 前验证 Sites user 和 backend session，删除伪造 trusted/capability header；匿名跳转安全 return path，403/503 使用无业务内容 gate。
- layout 只接受 Worker 内部 session header，IdentityProvider 仅内存持有 session；导航、command palette 和设置/告警/Mission/工单/资源/模型动作按 capability 隐藏或禁用，后端授权保持最终边界。
- 401/403/503/network 事件显示不同恢复 UI；生产告警→Mission 使用完整 document 导航重新执行身份门禁。
- 审批增加同步 in-flight lock；移动端保留可点击头像登出入口且压缩顶栏上下文。
- 新增身份/能力运行手册和四角色矩阵。

### Files Changed

- `backend/src/windops_backend/{capabilities.py,api/system.py,api/deps.py}`
- `backend/tests/test_identity_capabilities.py`
- `app/{chatgpt-auth.ts,layout.tsx,globals.css}`
- `worker/index.ts`
- `lib/{auth-paths,identity-session,api-access-events,production-shell-auth,production-runtime,api-client}.ts`
- `components/providers/identity-provider.tsx`
- `components/layout/app-shell.tsx`
- `components/pages/{system-settings,alarm-center,mission-detail,work-order,resource-center,model-management}-page.tsx`
- `tests/{identity-capability,api-client-idempotency,production-runtime}.test.mjs`
- `tests/e2e/identity-and-mobile.spec.ts`
- `docs/runbooks/production-identity-and-capabilities.md`

### Validation

- `PASS` — 后端身份/能力矩阵 14 tests，含四个人类角色、两个机器角色合同及客户端 capability 伪造仍为 backend 403。
- `PASS` — production Worker 15/15，覆盖匿名先登录、403 gate、session 主体匹配、伪造头丢弃与 release fail-closed。
- `PASS` — session/auth/error unit 6/6；typecheck 与 production build 通过。
- `PASS` — Chromium 6/6 覆盖桌面/390 px identity/nav/refresh/logout、四角色动作、401/403/503/network 与不安全存储检查。

Validation: `PASS`

---

## M-004 — 390 px 首页 P1 事件标题被压缩为逐字竖排

Severity: `Medium`  
Status: `DONE`

### Requirements

- 在 <=740 px 使用稳定 grid/flex 布局给予标题可读宽度，移除固定左边距定位。
- 覆盖长中英文、无空格文本、200% 缩放、键盘焦点、触摸目标与桌面回归。
- 在 320/360/390/430 px 真实浏览器中断言宽度、可见性、无覆盖与无横向溢出。

### Investigation

- 复现 <=740 px flex-wrap 下 P1 badge、标题、progress 和 link 竞争同一行；`.incident-link` 固定 `margin-left: 43px`，标题可被压缩到逐字竖排。
- Chromium 加载 hydration 后进一步发现 320 px 顶栏保留过多 live context，页面总宽 357 px。

### Root Cause

- 移动事件条仍沿用桌面 flex 的自由收缩和固定偏移；没有给标题一条 `minmax(0,1fr)` 稳定轨道。
- 320 px 顶栏只隐藏最后一个状态 span，时间和运行说明仍与四个动作竞争宽度。

### Changes

- <=740 px 改为 `30px minmax(0,1fr)` 两列 grid；P1 独占第一列，copy/progress/link 顺序进入第二列，删除 43px 偏移。
- 长文本使用 `overflow-wrap:anywhere`，Mission link 高度至少 44 px。
- <=460 px 顶栏只保留首要运行 badge，缩小 padding/gap，同时保留可点击身份头像。
- 增加 390 px screenshot baseline 和元素级 overflow/overlap 几何诊断。

### Files Changed

- `app/globals.css`
- `tests/e2e/identity-and-mobile.spec.ts`
- `tests/e2e/__screenshots__/dashboard-p1-incident-390.png`

### Validation

- `PASS` — Chromium 在 320/360/390/430 px 对长中文、长英文、无断点字符串及 200% title 逐项断言：标题宽度 >180px、无 P1/progress/link 覆盖、link >=44px、document 无横向溢出。
- `PASS` — Mission link 获得焦点后 Enter 导航成功；390 px 像素基线通过；桌面 production flow 同套件通过。

Validation: `PASS`

---

## M-005 — 当前工作树无法通过已声明的格式化门禁

Severity: `Medium`  
Status: `DONE`

### Requirements

- 仅格式化 Ruff 报告文件并复核语义 diff。
- 明确控制文档的 Prettier 策略且配置唯一、可重复。
- 重跑 format、lint、typecheck、mypy、迁移检查和相关测试，不弱化 CI 门禁。

### Investigation

- 复跑确认 Ruff 的完整 `src/tests/alembic/scripts` 范围可由统一命令稳定检查，共 143 个文件。
- Prettier 除应用与普通文档外会匹配根目录控制记录；这些记录是人工维护的权威状态输入，自动改写其结构会与长期任务持久化约束冲突。
- 完整 ESLint 在新增身份/E2E 代码中进一步发现空链接、未声明 `this` 语义的 callback 类型与 JSON `any` 返回；这些是当前变更的真实质量问题而非格式噪音。
- 工作树在任务开始前已包含大量用户改动；语义复核只检查本项的格式策略、审计点名文件和本轮关联修复，没有重置或覆盖既有内容。

### Root Cause

- 审计点名 Python 文件未在修改后运行与 CI 完全相同的 Ruff format 范围。
- 根级 Markdown 没有区分普通工程文档与 `AGENTS/AUDIT/EXECUTION` 权威控制输入。
- 新增身份和浏览器测试在局部验证后尚未经过完整仓库 ESLint。

### Changes

- 仅用 Ruff 格式化审计报告的 Python/迁移文件，并用完整检查证明其余文件没有被机械改写。
- `.prettierignore` 唯一、显式排除 `AGENTS.md`、`AUDIT_REPORT.md`、`EXECUTION_GOAL.md`、`EXECUTION_PROGRESS.md`；应用、测试、runbook、workflow 与 release 文档继续受门禁。
- `docs/testing-quality-gates.md` 记录与 CI 一致的两条格式命令和控制文档治理边界。
- 格式化新增的 production identity runbook；未修改其业务语义。
- 修复完整 ESLint 揭示的三个关联问题：会话恢复使用 Next `Link`、callback 使用函数属性类型、E2E state 使用显式合同类型。

### Files Changed

- `.prettierignore`
- 审计点名的 Ruff Python/迁移文件
- `docs/testing-quality-gates.md`
- `docs/runbooks/production-identity-and-capabilities.md`
- `app/layout.tsx`
- `components/providers/identity-provider.tsx`
- `tests/e2e/identity-and-mobile.spec.ts`

### Validation

- `PASS` — `pnpm format:check`：全部匹配文件符合 Prettier。
- `PASS` — `uv run ruff format --check src tests alembic scripts`：143 files already formatted。
- `PASS` — `pnpm lint`、`pnpm typecheck`、`uv run ruff check src tests alembic scripts`。
- `PASS` — `uv run mypy --no-incremental src`：72 source files，strict 无问题。
- `PASS` — Alembic 唯一 head `0020_delegated_replay_and_idempotency`、声明检查和完整离线 SQL render。
- `PASS` — coverage/capability/release pipeline 定向 18 tests；仅有已知 `.pytest_cache` Windows ACL warning。
- `PASS` — `git diff --check`；仅报告 Git 的 LF/CRLF 工作树提示，无 whitespace error。

Validation: `PASS`

---

## L-001 — README 的迁移与测试基线已过期

Severity: `Low`  
Status: `DONE`

### Requirements

- README 与最终 Alembic head、CI 测试结果和真实环境验证状态一致。
- 避免易漂移硬编码，或扩展自动检查以发现文档 head 漂移。
- 准确说明仍未运行的真实发布测试，不把它们描述为已通过。

### Investigation

- 根 README 仍声明十六个 Alembic 迁移、`0001→0016`、Node `118/118`、Python `119/120` 和唯一一个外部 skip；均与最终工作树不符。
- 后端 README 已列出到 `0020` 的迁移链，但 `verify_migration_head.py` 只校验三份 release 文档，不包含根 README。
- 当前最终默认后端套件在新增 README 漂移合同后为 201 collected / 189 passed / 12 `external_release` skipped；其中 11 个 PostgreSQL 合同已在专用固定 digest 数据库中 0 skip 通过，另一个真实供应商联合合同属于受保护 release workflow，不能伪报为本地通过。

### Root Cause

- README 将会随测试和迁移自然变化的总数写成无日期“当前事实”，却未纳入自动声明校验。
- 快速 SQLite 套件的预期 skip 与专用 PostgreSQL/release 非跳过门禁没有分开描述，容易把 default skip 误读为发布验证缺失或通过。

### Changes

- README 声明单一连续 Alembic head `0020_delegated_replay_and_idempotency`，并概述授权、秘密治理、有界索引和重放/幂等迁移边界。
- Node 日常说明不再维护易漂移总数；日期化收敛证据准确记录 133 Node / 0 skip、Chromium 6/6、后端 201 collected / 189 passed / 12 external-release skips。
- 明确 11 个 PostgreSQL 合同已在固定 digest 环境 0 skip 通过并进入 PR CI；真实供应商联合合同只由受保护 release workflow 执行，任何 skip 失败关闭，未把本地未运行外部服务描述为通过。
- Python 质量命令与 CI 的 Ruff 范围同步包含 `scripts`，技术栈补充 coverage/bundle、Playwright 与真实 PostgreSQL 门禁。
- 将根 README 加入 `verify_migration_head.py` 声明文件，并新增合同测试拒绝原审核中的旧 head/旧计数文本。

### Files Changed

- `README.md`
- `backend/scripts/verify_migration_head.py`
- `backend/tests/test_release_pipeline.py`

### Validation

- `PASS` — release pipeline 定向 9 tests，含根 README head/旧基线漂移合同。
- `PASS` — `verify_migration_head.py` 同时验证真实唯一 head 和四份声明，结果为 `0020_delegated_replay_and_idempotency`。
- `PASS` — README Prettier、相关 Python Ruff lint/format。
- `PASS` — 搜索确认根 README 不再出现 `Python 119/120`、`0001→0016`、`118/118`、十六个迁移或旧 `0017` head。
- 完整测试计数和全部发布事实将在 Final Global Validation 再次复核；若实际结果变化将重新打开本项。

Validation: `PASS`

---

# 4. Blockers

Current Blockers:  
`NONE`

---

# 5. Final Validation

| Area              | Status | Evidence |
| ----------------- | ------ | -------- |
| Build             | PASS   | `pnpm test:coverage` 与 `pnpm test:e2e` 均重新 production build；固定 Trixie digest Docker 候选 `sha256:df4f6773...` 构建成功。 |
| Format            | PASS   | Prettier 全范围；Ruff format 143 files；`git diff --check` 0，只有 Windows LF/CRLF 提示。 |
| Lint              | PASS   | ESLint、Ruff 全 `src/tests/alembic/scripts` 均 0。 |
| Typecheck         | PASS   | TypeScript `tsc --noEmit`；mypy strict 72 source files。 |
| Unit Tests        | PASS   | 前端 133 / 0 skip；后端默认 201 collected = 189 passed + 12 external-release 预期 skips。 |
| Integration Tests | PASS   | 固定 digest PostgreSQL/TimescaleDB/pgvector 11 tests，0 failures/errors/skips；包含真实迁移、10 万级 plan、并发、nonce 与 receipt。 |
| E2E               | PASS   | 正式 `pnpm test:e2e` production build + Chromium 6/6，桌面、320/360/390/430 px、身份/能力/错误/SSE/重复点击。 |
| Production Build  | PASS   | Bundle 92 chunks / 2,568,768 bytes / max 645,279；当前源码 Docker 镜像 non-root/hash-locked 构建。 |
| Smoke Test        | PASS   | 镜像内 Alembic、read-only rootfs、UID/GID 10001、cap-drop、no-new-privileges、health/ready/Docker health；6 entrypoints、pip check、PG17、无 pytest。 |
| Migration         | PASS   | 离线完整 render；真实空库 upgrade/current 精确 `0020_delegated_replay_and_idempotency`；README/release declarations 同步。 |
| Security Scans    | PASS   | Bandit、pip-audit、pnpm production audit 无已知漏洞；container lock check 通过。 |

Additional final evidence:

- 后端总覆盖 `68.72%`；完整工作树 changed-executable-lines `65.83%`；所有关键模块 floor 通过。
- 前端 V8 line `90.35%` / branch `51.29%` / function `33.02%`；Bundle 全部门槛通过。
- Kubernetes 真正 kustomize 14 resources，5 个 workload/job 绑定同一候选 digest/release/commit；deployment policy 9 项检查通过，manifest SHA-256 `cc0ad825...`。
- 本地可变 tag 传给 immutable artifact verifier 时被正确拒绝；未弱化该策略。随后以本地内容寻址 image ID 完成等价 runtime 检查和 release smoke；真实 pushed digest/signature/SBOM 仍由受保护 workflow 强制。
- 证据保存在 `backend/.artifacts/final/`；PostgreSQL JUnit 为 11/0/0/0，临时容器和网络已按标签核对后删除。本地候选镜像标签保留供复核。
- `.gitignore` 现统一忽略 `.artifacts` 和仓库内 `.pytest-tmp*`，不删除证据或用户文件，避免误提交本地验证输出。

---

# 6. Recheck

Status: `PASS`

- Missing Issues: `NONE` — 重新读取 `AUDIT_REPORT.md` 并从 C-001 到 L-001 对照全部 11 项、75 条 Acceptance Criteria。
- Partial Implementations: `NONE` — 资产范围、秘密治理、真实 PostgreSQL、制品链、有界查询、重放、coverage/E2E、capability、移动布局、格式与 README 均有实现和自动合同。
- Regression: `NONE` — 核心安全/质量合同 54 tests、知识/部署/运维合同 53 tests、前端 production/identity/idempotency/events 24 tests 全部通过且 0 test skip。
- TODO / Stub / Placeholder: `NONE RELATED` — 扫描无 TODO/FIXME/HACK；命中的空类体是自定义异常/SQLAlchemy Base，测试 fake 的无操作 close，placeholder 命中为表单属性或失败关闭断言。
- Acceptance Criteria Failures: `NONE`。

Review Evidence:

- C-001：SQL scope、机器 allowlist、opaque cursor、批量原子性和知识细粒度合同通过。
- H-001：严格 schema、递归 secret 拒绝、脱敏/轮换/readiness 与权限合同通过。
- H-002/H-003/H-004：CI fail-on-skip、固定 digest、容器/清单失败关闭、真实 PG 证据和有界集合/图投影预算重新对照，无缺项。
- M-001..M-005：nonce/幂等、coverage/browser、server capability、移动几何、格式与完整 lint 证据对照通过。
- L-001：根 README 现在由 head 校验脚本保护；旧 head/旧测试基线合同通过。
- CI 扫描未发现 `continue-on-error`、`|| true`、零覆盖阈值、测试 skip/断言弱化或关闭 lint/type/security 的绕过。

---

# 7. Adversarial Review

Status: `PASS`

- [x] invalid input
- [x] empty state
- [x] repeated action
- [x] network failure
- [x] API failure
- [x] permission failure
- [x] stale state
- [x] concurrency
- [x] restart
- [x] partial failure
- [x] production configuration

Findings:  
`NONE`

Evidence:

- `invalid input` / `production configuration`：security/configuration/model output 测试验证弱密钥、SQLite 冒充 production、缺 scope、非 TLS、错误推理输出均失败关闭。
- `empty state`：Chromium 告警筛选真实显示空状态，未用 fixture 假数据填充。
- `repeated action`：浏览器审批双击仅一次调用；nonce/receipt、告警、EAM、预测重放合同验证相同请求稳定且不同 payload 冲突。
- `network/API/permission failure`：Chromium 明确区分 401、403、503 与浏览器网络故障并提供对应恢复路径；机器 shell 403。
- `stale state`：EventSource 用非敏感 opaque cursor 重连；stale outbox lease 可回收，旧 worker fencing 不能覆盖新终态。
- `concurrency`：委托 nonce、command receipt、预测和 ingest 首包并发均精确单副作用；真实 PostgreSQL 多实例证据在 M-001/H-002 保存并将在最终门禁重跑。
- `restart`：durable execution 覆盖 lease 到期、redelivery、回滚后重新 claim 与审计存活。
- `partial failure`：mixed-scope batch 零部分写、graph/EAM/model 失败保留正确审计且不提交错误领域状态。
- 对抗定向后端 42 tests、浏览器 6/6；此前本阶段 replay/access 核心合同亦通过，未发现新 Critical/High/Medium。

---

# 8. Final Audit Pass #1

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Result: `PASS`

Evidence:

- 直接解析最终 coverage、PostgreSQL JUnit、release smoke 与 deployment policy：coverage `68.7166%`，PG `11/0/0/0`，smoke/policy 均 `passed`，14 resources / 5 workloads。
- 最终 rendered manifest 无 `registry.invalid`、零 digest、`latest`、`unreleased` 或 `unknown`。
- Git 状态虽保留任务开始前的大量用户工作，但 `.artifacts/.pytest-tmp*` 已正确忽略，无本轮验证垃圾候选；`git diff --check` 仍为 0。
- 无相关 TODO/FIXME，无运行中的 `windops.project=wind-agent` 临时容器。
- 秘密扫描无 AKIA/OpenAI-key 候选；唯一私钥头命中是平台配置拒绝测试中的 `fixture` 合成字符串，不是有效 PEM 或凭据。
- 首次 PowerShell coverage 解析因 Coverage.py 空键需 `-AsHashtable`，首次私钥 `rg` pattern 需 `--`；两项均为审计脚本调用问题，纠正后原检查通过，没有掩盖产品失败。

---

# 9. Final Audit Pass #2

Status: `PASS`  
New Critical: `0`  
New High: `0`  
Result: `PASS`

Evidence:

- Gate-state parser 重新确认 11 Issue / 11 DONE / 0 非终态；5 个 Critical/High 与 5 个 Medium 全部完成，Recheck、Adversarial、Final Global Validation 和 Pass #1 的正式 regex 断言通过。
- CI + release workflow 共 14 个 `uses:` 全部锁定完整 40 位 SHA；browser/PostgreSQL jobs、`production-release` environment 与 fail-on-skip 存在，无 `continue-on-error`。
- coverage、PostgreSQL JUnit、release smoke、deployment policy 和 rendered manifest 五份证据与 Pass #1 记录的 SHA-256 完全一致，未在两轮间被修改。
- 唯一 Alembic head 与四份声明仍为 `0020_delegated_replay_and_idempotency`。
- `git diff --check` 仍为 0；无运行中的项目临时容器；候选镜像仍绑定 content ID、UID/GID、release ID 和 commit SHA。
- 第二轮没有发现新 Critical 或 High；连续两轮收敛成立。

---

# 10. Final Completion Checklist

## Coverage

- [x] 所有审核 Issue 已登记
- [x] 无 TODO
- [x] 无 IN_PROGRESS

## Severity

- [x] Critical 全部处理
- [x] High 全部处理
- [x] 合理可执行 Medium 全部处理

## Quality

- [x] 无 placeholder 假完成
- [x] 无弱化测试
- [x] 无相关 TODO / stub
- [x] 前后端真实接通

## Validation

- [x] Build
- [x] Format
- [x] Lint
- [x] Typecheck
- [x] Unit
- [x] Integration
- [x] E2E
- [x] Production build
- [x] Smoke test
- [x] Migration
- [x] Security scans

## Convergence

- [x] 完成完整审核报告二次对照
- [x] 完成 adversarial review
- [x] Final Audit Pass = 2 / 2

---

# 11. Final Summary

Total Issues: `11`  
DONE: `11`  
BLOCKED: `0`  
NOT_APPLICABLE: `0`  
Critical Remaining: `0`  
High Remaining: `0`  
Final Validation: `PASS`  
Final Audit Pass: `2 / 2`  

Known Remaining Risks:

- 审核 Issue 无剩余风险项。真实 registry push、keyless signature/attestation、Trivy 与供应商联合环境仍是受保护 release-time 门禁；本地没有伪造其外部证据，任一缺失或 skip 都会失败关闭。

External Blockers:

- `NONE`

Final State:  
`COMPLETED`

---

# 12. Independent Re-audit Resolution (2026-08-21 09:41 +08:00)

The active register and current sections `3K` through `3Q` supersede the historical final summary immediately above.

- Active issues: `H-001, H-002`
- Severity: `2 High`
- Status: `DONE`
- Current final state: `COMPLETED`
- Source of truth: regenerated `AUDIT_REPORT.md`

---

# 13. OpenVigil Brand Migration (2026-09-05)

Status: `VALIDATED`
Brand Audit Pass: `2 / 2`
Second Pass: `PASS`

Scope completed:

- 用户可见品牌、页面元数据、错误/权限文案、类型与组件命名、导出文件名、README 与规范/审核文档统一为 `OpenVigil`。
- 品牌含义按 `Open + Vigil` 写入 README；保留开放架构/接口/模型生态/数据接入与持续守望异常信号的产品语义。
- `openvigil-theme` 与 `openvigil-sidebar-collapsed` 成为新浏览器键，并保留一次性读取旧键的兼容迁移。
- README 截图、设计概念图、OG 图、桌面视觉参考、真实浏览器基线及 10 页项目介绍演示稿完成视觉品牌替换。
- `windops_backend`、`WINDOPS_*`、`x-windops-*`、Drizzle/Neo4j 对象、bucket/指标/告警规则与实时协议保留为兼容命名空间，未引入破坏性迁移。

Validation completed:

- `pnpm test`: `167 / 167` passed.
- `uv run pytest`: `397 passed, 28 skipped`；skip 均为显式外部环境测试。
- `pnpm test:e2e`: `29 / 29` passed；含 22 路由、响应式、WCAG、200% 放大和真实截图基线。
- `pnpm run typecheck`, `pnpm run lint`, `pnpm run format:check`, Ruff 与 strict mypy 全部通过。
- `pnpm run test:start-smoke`: demo 启动与非法 production 配置 fail-closed 通过。
- 演示稿 10 页完整导入，package integrity、字体、模板覆盖率和版式 validator 通过；最终文件中旧展示品牌命中为 0。
- Brand Audit Pass #1：用户可见旧品牌 0、旧可见资产名 0、非白名单技术改名 0、缺失 OpenVigil 交付物 0。
- Brand Audit Pass #2：在进度持久化后重新执行同一审计，结果保持 0 / 0 / 0 / 0，旧名演示稿不存在。
