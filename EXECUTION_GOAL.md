# EXECUTION_GOAL.md

# Long-running Execution Runbook

## 当前任务覆盖层：CARE v6 功能实施

本覆盖层将通用执行规则绑定到当前 CARE v6 任务。它不修改 `AGENTS.md` 的长期规则；当前任务结束后，可由下一份明确任务覆盖层替换。

### 可直接使用的启动提示词

```text
请完整执行 C:\coding\project\wind-agent\EXECUTION_GOAL.md。

以 AGENTS.md 为长期规则，以 docs/care-v6-integration-development-plan.md 为需求与验收依据，以 AUDIT_REPORT.md 中 CARE-* 活动 Issue 为可执行任务清单，以 EXECUTION_PROGRESS.md 顶部 CARE 活动区为唯一当前状态。

从阶段 0A 开始，严格按依赖顺序持续实现、测试、验证和更新进度。未关闭全部阶段 0 强制门槛前，不得开始全量导入、模型上线或平台回放。不得修改 C:\coding\reference\CARE_To_Compare 或其 ZIP，只允许只读核验。不得伪造 RUL、把任意信号改名为主轴承振动、用 prediction 真值调参、全量展开 CARE 到 TimescaleDB，或用前端/fixture/placeholder 制造完成。

每完成一个 Issue，立即把实现文件、迁移、测试命令、结果和剩余风险写入 EXECUTION_PROGRESS.md。持续处理所有可执行项；只有全部 Completion Gates 通过并完成两轮独立最终审计，或所有剩余工作都依赖真实外部 blocker，才停止。
```

### 当前 Source of Truth 顺序

1. `AGENTS.md`：项目长期安全、工程、测试和 Git 规则；
2. 本文件：长任务执行、验证与收敛规则；
3. `docs/care-v6-integration-development-plan.md`：CARE 功能、架构边界和验收标准；
4. `AUDIT_REPORT.md` 顶部 CARE 活动区：当前 14 个可执行 Issue；
5. `EXECUTION_PROGRESS.md` 顶部 CARE 活动区：唯一当前执行状态；
6. `docs/care-v6-integration-plan-review.md`：需求计划的评审依据；
7. 实际代码、迁移、配置和测试：文档冲突时必须调查并记录。

历史审计和历史 Progress 只作为证据，不得覆盖顶部 CARE 活动状态。

### 当前任务范围

- 实现需求文档第 5 至 18 节定义的数据契约、评分器、独立执行进程、数据模型、anomaly 运行时、回放隔离、告警链路、API、前端、许可证和全量验证。
- 允许只读访问 `C:\coding\reference\CARE_To_Compare` 和 `C:\coding\reference\CARE_To_Compare.zip`。
- 禁止修改、重命名、移动或删除上述仓库外原始数据。
- 所有代码、测试、迁移、文档和项目内制品配置修改仅限当前仓库。
- 不操作其他项目的数据库、容器、进程或配置。

### 强制实施顺序

依赖关系优先于单纯严重级别，默认顺序为：

1. `CARE-C001`：真实文件和全列映射；
2. `CARE-C002`：质量、状态、单位、缩放和时间语义；
3. `CARE-C003`：`care-score-v6` 和无泄漏评分协议；
4. `CARE-C004`：replay run、水位、sequence、时间和幂等隔离；
5. `CARE-C005`：anomaly 运行时、预测告警和服务器发布门槛；
6. `CARE-H001`、`CARE-H002`：Worker/Parquet/MinIO 与数据库/迁移基础；
7. `CARE-H003`：A 场异常/正常双事件最小导入；
8. `CARE-H004`：离线基线和评估制品；
9. `CARE-H005`：平台回放垂直切片；
10. `CARE-M001`、`CARE-M002`、`CARE-M003`：受治理 API/UI、诊断和许可证；
11. `CARE-M004`：A22、C、B、全量 95 事件与最终运行验收。

可以在依赖已满足时并行处理相互独立的实现，但不得越过阶段 0 门禁。

### 阶段 0 规则

阶段 0 不是只写设计文档。标记对应 Issue 为 DONE 前必须同时具备：

- 可执行的数据/接口契约；
- 小型固定样例；
- 正向和负向自动化测试；
- 与当前代码和数据库约束相容的实现证据；
- 需求文档第 16 节对应检查项的客观证据。

`care-score-v6` 的精确公式、权重、边界和状态规则必须来自官方论文或权威参考实现。无法从权威来源确认的细节不得猜测；记录为当前 Issue 内的未决项，并继续处理不依赖它的工作。

### 每个 Issue 的执行模板

1. 重新阅读 Audit 中该 Issue 的 Required Changes 和 Acceptance Criteria；
2. 阅读需求文档对应章节；
3. 检查当前实现、迁移、测试和调用链；
4. 在 Progress 中把该 Issue 从 TODO 改为 IN_PROGRESS；
5. 记录调查结论、根因和拟修改范围；
6. 实现最小但完整的后端、前端、迁移和配置改动；
7. 添加能失败的正向、负向、边界和回归测试；
8. 先运行定向验证，再运行相关子系统回归；
9. 将真实命令、结果、修改文件和剩余风险写入 Progress；
10. 只有全部验收条件有证据时标记 DONE，然后继续下一个依赖已满足的 Issue。

### CARE 专项禁止项

- 不得修改原始 CARE 数据来让导入器通过；
- 不得静默忽略未知列、坏映射、失败事件或不可评分事件；
- 不得全局把零值改成 null；
- 不得默认使用 Min/Max/Std；
- 不得用 prediction 标签、事件区间或故障描述调参；
- 不得把不同事件/回放运行拼成一个在线时间序列；
- 不得把匿名时间当真实场站时间或跨事件先后；
- 不得为 anomaly 模型填充伪造 RUL/30 天故障概率；
- 不得把模型分数只塞进 SCADA attributes 而缺少正式预测记录；
- 不得用假 ingest receipt 规避告警来源约束；
- 不得依赖前端状态决定模型是否通过评估门槛；
- 不得在 FastAPI 请求事务中解析全量 CSV 或训练模型；
- 不得将全量 CARE 宽表展开进 TimescaleDB；
- 不得把 CARE 派生数据许可证与项目 MIT 代码许可证混为一体。

### 分层验证要求

每个阶段采用由小到大的验证顺序：

1. 数据合同和纯函数单元测试；
2. 小型 CARE fixture 导入与黄金评分测试；
3. SQLite/本地服务测试（仅适用部分）；
4. Alembic 声明、空库升级和真实 PostgreSQL 约束测试；
5. Worker/MinIO/任务恢复集成测试；
6. API 授权、分页、有界查询和失败路径；
7. 前端 typecheck、lint、单测和 production build；
8. 双事件真实垂直切片 E2E；
9. 全量 95 事件的有界性能与恢复测试；
10. 当前最终树的完整全局回归、安全、迁移和 smoke 验证。

外部环境未提供时，必须区分“本地已验证”和“受保护环境待验证”，不得把 skip 当作通过。

### 当前任务完成条件

除下方通用 Completion Gates 外，还必须满足：

- `AUDIT_REPORT.md` 顶部 14 个 CARE Issue 全部为 DONE，或仅有具备真实外部证据的 BLOCKED；
- 需求文档第 16 节阶段 0 检查项全部关闭；
- 需求文档第 18 节总体验收标准逐项有证据；
- A 场双事件垂直切片真实贯通；
- 全量范围按 `CARE-M004` 的最终验收完成；
- 当前最终代码重新运行全局验证；
- First Full Recheck 和 Adversarial Review 完成；
- 连续两轮 Final Audit 未发现新的 Critical/High，计数为 `2 / 2`；
- `EXECUTION_PROGRESS.md` 已更新为真实最终状态。

---

本文件定义执行 Agent 处理项目审核报告时必须遵守的工作方式、验证方式和收敛条件。

主要任务来源：

`AUDIT_REPORT.md`

执行状态：

`EXECUTION_PROGRESS.md`

项目永久规则：

`AGENTS.md`

---

# 1. Mission

完整执行：

`AUDIT_REPORT.md`

中的所有合理可执行任务。

目标不是：

“尽快宣布完成”。

目标是：

> 最大化审核报告真实完成率、实现质量和验证可信度。

不得自行降低审核报告中的验收标准。

---

# 2. Startup

开始工作时依次读取：

1. `AGENTS.md`
2. `AUDIT_REPORT.md`
3. `EXECUTION_GOAL.md`
4. `EXECUTION_PROGRESS.md`（若存在）
5. 当前相关代码

如果：

`EXECUTION_PROGRESS.md`

不存在，则创建它。

首先确保审核报告中的所有 Issue 都登记进入 Progress。

不得只选择容易完成的任务。

---

# 3. Priority

默认执行顺序：

Critical
→ High
→ Medium
→ Low

如果存在明确依赖关系：

按照依赖关系调整顺序。

完成 Critical / High 后不得因此直接结束任务。

---

# 4. Issue Execution Loop

处理每个 Issue 时执行：

1. 阅读原始审核项
2. 检查实际代码
3. 确认问题状态
4. 定位根因
5. 实施 Required Changes
6. 添加或修改必要测试
7. 执行验证
8. 检查 regression
9. 更新 EXECUTION_PROGRESS.md
10. 继续下一项

允许状态：

- TODO
- IN_PROGRESS
- DONE
- BLOCKED
- NOT_APPLICABLE

---

# 5. DONE Definition

只有实际完成修改并通过合理验证后：

才能标记：

`DONE`

以下情况不得标记 DONE：

- 只完成部分要求
- 仅通过代码阅读认为正确
- 对应测试仍失败
- 使用 TODO 代替实现
- 使用 placeholder 代替实现
- 使用 stub 代替实现
- 只处理表面症状
- 前端存在但后端未真正接通
- 后端存在但前端没有实际调用

---

# 6. NOT_APPLICABLE

如果认为审核报告中的某项已经不适用于当前代码：

必须重新检查实际实现。

只有存在明确证据时才能标记：

`NOT_APPLICABLE`

必须记录：

- 为什么不适用
- 检查了哪些内容
- 具体证据

不得因为：

- 优先级低
- 工作量大
- 认为没有必要

而标记 NOT_APPLICABLE。

---

# 7. BLOCKED

只有无法由当前执行环境自行解决的真正外部依赖才能算 blocker，例如：

- 缺少密钥
- 缺少账户权限
- 必需外部服务不可用
- 必需用户数据不存在
- 必须人工操作
- 环境缺少不可替代资源

以下不属于 blocker：

- 实现困难
- 修改复杂
- 工作量较大
- 已经工作很久
- 上下文很长

遇到 blocker 后：

记录 blocker，并继续处理所有不依赖该 blocker 的任务。

---

# 8. Newly Discovered Problems

实施期间如果发现：

- 当前修改引起的新 bug
- 与审核项直接相关的遗漏
- 测试暴露的真实错误
- 阻碍当前审核项完成的关联问题

应一并解决。

但是不得无边界扩展为与审核报告无关的大规模项目重写。

原则：

> 解决完成当前审核任务所必需的关联问题。

---

# 9. Validation

不得仅依赖模型自身判断宣布完成。

根据项目实际情况执行：

- build
- lint
- typecheck
- unit tests
- integration tests
- API tests
- E2E tests
- smoke tests
- application startup
- Docker build
- production build
- database migration validation

每个 Issue 优先执行针对性验证。

最终阶段必须重新进行全局验证。

---

# 10. Progress Persistence

`EXECUTION_PROGRESS.md`

是长任务执行状态的 Source of Truth。

每完成一个重要 Issue：

立即更新。

至少记录：

- 当前状态
- 实际修改
- 修改文件
- 测试或验证方式
- 验证结果
- 剩余工作

不要依赖聊天上下文长期保存这些状态。

---

# 11. Context Recovery

出现以下情况时：

- 上下文发生压缩
- 工作时间已经较长
- 不确定当前任务
- 不确定当前完成状态
- 进入新的执行阶段
- 即将进入最终验收
- 准备宣布完成

重新读取：

1. `AGENTS.md`
2. `AUDIT_REPORT.md`
3. `EXECUTION_GOAL.md`
4. `EXECUTION_PROGRESS.md`

然后根据文件中的持久化状态继续。

---

# 12. First Full Pass

第一次处理完成所有审核项后：

禁止立即结束。

重新从头读取：

`AUDIT_REPORT.md`

逐条验证：

- 是否遗漏
- 是否部分完成
- 是否漏掉 Required Changes
- 是否满足 Acceptance Criteria
- 是否留下相关 TODO
- 是否存在 placeholder
- 是否存在 stub
- 是否前后端真正接通
- 是否处理异常路径
- 是否覆盖必要边界条件
- 是否产生 regression

发现问题：

重新进入执行循环。

---

# 13. Adversarial Review

完成第一次完整复查后：

以严格验收者的立场进行 adversarial review。

目标不是证明：

“已经完成”。

而是主动寻找：

> 为什么当前实现仍然不应该通过验收。

根据项目实际范围检查：

- invalid input
- empty state
- repeated action
- network failure
- API failure
- permission failure
- stale state
- concurrency
- restart
- partial failure
- production configuration

发现真实问题：

修复并重新验证。

---

# 14. Final Global Validation

准备完成之前：

针对当前最终代码状态重新运行完整验证。

不得只引用此前运行过的结果。

根据项目实际情况包括：

- build
- lint
- typecheck
- unit tests
- integration tests
- E2E tests
- production build
- startup smoke test

结果必须写入：

`EXECUTION_PROGRESS.md`

---

# 15. Convergence Counter

在：

`EXECUTION_PROGRESS.md`

中维护：

`Final Audit Pass: X / 2`

初始：

`0 / 2`

每次执行完整最终检查：

如果没有发现新的 Critical / High：

`+1`

只有连续两次通过：

`2 / 2`

才满足收敛条件。

如果任意一次发现新的 Critical / High：

执行：

修复
→ 验证
→ Final Audit Pass 重置为 0 / 2
→ 重新执行最终检查

一次没有发现重大问题不得立即结束。

---

# 16. Completion Gates

只有以下条件全部满足才能完成。

## Gate A — Coverage

AUDIT_REPORT.md 中所有 Issue 都有最终状态：

- DONE
- BLOCKED
- NOT_APPLICABLE

不存在：

- TODO
- IN_PROGRESS
- 未登记问题

## Gate B — Critical / High

所有可执行：

Critical = DONE

High = DONE

## Gate C — Medium

所有合理可执行 Medium 已完成。

未完成项必须有真实外部 blocker。

## Gate D — Evidence

所有 DONE 均有实际实现和验证证据。

## Gate E — Recheck

至少完成一次：

AUDIT_REPORT.md 从第一项到最后一项的重新验收。

## Gate F — Global Validation

项目适用的最终 build / test / typecheck 等验证已经执行。

## Gate G — Convergence

Final Audit Pass：

`2 / 2`

## Gate H — Persistent State

EXECUTION_PROGRESS.md 已更新为真实最终状态。

---

# 17. Forbidden Early-stop Reasons

不得因为以下原因完成任务：

- 已经执行很久
- 已经修改很多代码
- 核心问题已经解决
- 主要功能已经完成
- 项目基本可用
- 大部分测试通过
- 剩余内容看起来不重要
- 上下文已经很长
- 已经取得明显改善

以上都不是 Completion Gate。

---

# 18. Legal Stop Conditions

只有两种合法停止状态。

## COMPLETED

全部 Completion Gates 满足。

## BLOCKED

所有剩余工作都依赖真正无法自行解决的外部 blocker，
并且其他所有可执行工作已经完成。

否则：

继续执行。
