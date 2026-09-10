# WindOps 知识图谱技术选型建议

## 结论

结合 WindOps 现有的 PostgreSQL、TimescaleDB 和 pgvector 技术栈，推荐采用以下方案：

> 使用 Neo4j 作为派生知识图谱查询库，PostgreSQL 继续作为权威业务数据库，pgvector 继续负责文档向量检索。

不建议把 SCADA、工单、知识文档等数据全部迁入 Neo4j，也不建议让 PostgreSQL 和 Neo4j 由业务代码直接双写。

## 当前实现状态（2026-08-14）

本文第一、二阶段及第三阶段的核心可靠性能力已经落地为可运行代码，不再只是静态演示页：

- PostgreSQL 领域表仍是权威数据源；
- `knowledge_graph/projection.py` 从业务表确定性构建带内容哈希修订号的图快照；
- `knowledge_graph/store.py` 提供 Neo4j 生产适配器和仅限测试使用的内存适配器；
- 告警生成、Mission 分析、人工审批和现场任务完成都会在原业务事务中写入 Graph Projector Outbox 事件；
- Dramatiq Worker 使用租约和 fencing token 消费事件，按当前 PostgreSQL 状态幂等重建 Neo4j 投影；
- Neo4j 投影元数据使用 Outbox 事件时间与事件 ID 组成单调序列，并在元数据节点上获取写锁，过期 Worker 不能覆盖更新的投影；
- FastAPI 已提供汇总、实体子图、故障溯源、告警影响、相似案例、Passage 支撑/反证、混合检索、观测、向量重建索引、对账和受控重建接口；
- 混合检索使用 pgvector（SQLite 测试中为显式确定性替身）召回候选，再用 Neo4j 最多 4 跳扩展失效模式、证据与闭环案例，返回向量分、图结构分、融合分和关系路径；
- 前端 `/knowledge-graph` 工作台通过服务端代理读取 FastAPI，支持实体图探索与混合检索，不使用 fixture 冒充图数据库；
- 本地依赖栈已经加入 Neo4j Community，生产配置强制使用 `neo4j+s://` 和非示例凭据。

当前自动化验证覆盖快照唯一性、无悬空关系、不写入原始 SCADA 节点、Outbox 成功消费、旧 Worker 写入隔离、重建幂等、投影对账、Neo4j 批量 Cypher 形状、向量召回与图扩展融合、支持/反证区分、完整工单闭环路径、API 契约及前端无 fixture 降级。真实 PostgreSQL、Redis、MinIO 和 Neo4j 的联合发布测试仍属于部署环境验收项，不能由 SQLite/内存测试替代。

## 推荐架构

```text
PostgreSQL / TimescaleDB
  业务实体、状态、SCADA、审计、Outbox
              │
              ▼
       Graph Projector
     幂等消费 Outbox 事件
              │
              ▼
           Neo4j
  实体关系、多跳查询、影响分析、解释路径

MinIO / PostgreSQL / pgvector
  文档正文、Passage、Embedding
```

FastAPI 对外提供统一的 `/api/v1/knowledge-graph/**` 接口，前端不直接连接 Neo4j。

### 为什么选择 Neo4j

WindOps 的核心关系属于典型属性图：

- 风机 → 子系统 → 传感器；
- 告警 → 异常特征 → 候选故障模式；
- 故障模式 → 证据 → 历史案例；
- 工单 → 维护措施 → 备件 → 班组；
- 文档 Passage → 支撑诊断 → 关联设备。

Neo4j 的 Cypher 对多跳路径、影响范围、最短路径和可解释关系查询较为自然，也提供节点/关系约束、全文索引和向量索引。当前版本的向量索引可以用于节点或关系，并支持 Cypher `SEARCH`。不过 WindOps 已经使用 pgvector，第一阶段没有必要在 Neo4j 中重复存储 embedding。

参考资料：

- [Neo4j Vector Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Neo4j Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)

## 图模型建议

### 首批节点类型

```text
WindFarm
Turbine
Subsystem
Sensor
Alarm
Anomaly
FailureMode
Evidence
Mission
Decision
WorkOrder
Procedure
Part
KnowledgeDocument
KnowledgePassage
```

### 首批关系类型

```text
HAS_TURBINE
HAS_SUBSYSTEM
MONITORED_BY
TRIGGERED
INDICATES
AFFECTS
SUPPORTED_BY
DERIVED_FROM
RESOLVED_BY
REQUIRES_PART
EXECUTED_BY
SIMILAR_TO
```

诊断类关系必须携带证据、来源、版本和时态属性，例如：

```text
INDICATES {
  confidence,
  evidenceId,
  source,
  observedAt,
  validFrom,
  validTo,
  modelVersion,
  revision
}
```

不要把原始 SCADA 数据点写入图数据库。TimescaleDB 保存原始时序数据，图中只保存异常事件、统计特征、诊断结论及其关系。

## 知识检索流程

建议实现为“向量召回 + 图扩展”，而不是只进行图检索或把向量检索直接称为知识图谱：

1. pgvector 根据问题召回相关 Passage。
2. 通过 Passage 关联到设备、故障模式和历史案例。
3. Neo4j 扩展 1–2 跳关系。
4. 根据关系类型、时间和证据等级重新排序。
5. 返回答案、引用 Passage 和完整解释路径。

示例解释路径：

```text
主轴承温升
 → SUPPORTED_BY → SCADA Evidence
 → INDICATES → Lubrication Degradation
 → SIMILAR_TO → Historical Failure Case
 → RESOLVED_BY → Grease Sampling Procedure
```

LLM 可以参与实体抽取和候选关系生成，但不能直接成为权威写入源；新增关系应经过规则校验或人工审核。

## 数据同步原则

PostgreSQL 应继续作为权威数据源，Neo4j 作为可重建的查询投影：

- 业务事务只写 PostgreSQL，并在同一事务中写入 Outbox 事件；
- Graph Projector 幂等消费 Outbox，更新 Neo4j；
- 每个图节点保留权威实体 ID、来源、revision 和更新时间；
- 支持删除 Neo4j 数据后从 PostgreSQL 全量重建；
- 图同步失败不能影响 SCADA 入库、告警生成和工单事务；
- 对账任务应检测孤立节点、缺失关系和 revision 落后。

## 其他技术选项

| 方案                       | 适用情况                                          | 建议       |
| -------------------------- | ------------------------------------------------- | ---------- |
| Neo4j                      | 多跳查询、影响分析、路径解释是核心能力            | 推荐       |
| Apache AGE                 | 强制只维护一个 PostgreSQL，规模较小且可以自管扩展 | 可选       |
| PostgreSQL 边表 + 递归 CTE | 只需要树形设备层级、简单 1–3 跳查询               | 适合 PoC   |
| RDF/SPARQL/SHACL           | 需要行业本体、跨组织语义交换和严格推理            | 当前不建议 |

### Apache AGE

Apache AGE 是 PostgreSQL 图扩展，支持 openCypher 和 SQL/Cypher 混合查询，已有对应 PostgreSQL 16–18 的稳定版本。它可以减少数据库种类，但会将图能力与主业务数据库的扩展兼容性、版本升级和故障域绑定在一起。

参考资料：

- [Apache AGE Overview](https://age.apache.org/overview/)
- [Apache AGE Downloads](https://age.apache.org/download/)

### PostgreSQL 递归查询

PostgreSQL 支持递归遍历、深度或广度排序以及循环检测，适合在引入独立图数据库前验证图模型。当复杂路径查询成为产品核心能力后，再迁移到 Neo4j。

- [PostgreSQL Recursive Queries](https://www.postgresql.org/docs/current/queries-with.html)

### RDF、SPARQL 与 SHACL

只有在明确需要 RDF 互操作、行业本体、形式化语义约束或跨组织数据交换时，才建议采用 RDF 图数据库、SPARQL 和 SHACL。其建模和运维成本高于当前 WindOps 所需的属性图方案。

参考资料：

- [SPARQL 1.1](https://www.w3.org/TR/sparql11-overview/)
- [SHACL](https://www.w3.org/TR/shacl/)

## 建议实施步骤

### 第一阶段：WT-023 PoC

- 选取 15–20 类节点，关系类型控制在 20 类以内；
- 从现有 PostgreSQL/演示领域对象生成初始图；
- 通过 Outbox 建立可重复执行的图投影；
- 提供设备关系、故障溯源和历史案例三个查询接口；
- 为节点唯一性、引用完整性和查询路径增加自动化测试。

### 第二阶段：混合检索

- [x] pgvector 召回 Knowledge Passage；
- [x] Neo4j 扩展设备、故障模式、证据和历史闭环关系；
- [x] 对图路径与文档证据进行融合排序；
- [x] 所有检索摘要返回 Passage/案例引用、分项得分和关系路径。

### 第三阶段：生产化

- [x] 增加全量重建、增量同步、对账和 Outbox 失败重放基础；
- [x] 建立图模型版本、确定性身份和可重建投影机制；
- [x] 增加租户、风场和数据权限过滤：Sites 主体由后端作用域映射到租户、风场、机组、实体和数据域，图投影及所有读取接口统一过滤；
- [x] 监控同步延迟、投影年龄、孤立节点、查询延迟和无证据关系；
- [x] 模型输出只能生成候选诊断，权威图关系来自 PostgreSQL 已持久化、规则校验或人工审核数据；
- [ ] 在发布环境完成 PostgreSQL/Timescale/pgvector、Redis、MinIO、Neo4j 与模型供应商的联合故障演练。

## PoC 验收查询

至少验证以下查询：

1. WT-023 的主轴承异常由哪些传感器、告警和证据支持？
2. 某个告警可能影响哪些子系统、Mission、工单和备件？
3. 当前故障模式与哪些历史闭环案例相似，历史上采用了什么处理方案？
4. 某个知识 Passage 支撑了哪些诊断结论，结论是否存在相反证据？
5. 删除并重建 Neo4j 后，关键查询结果是否与重建前一致？

只有这些查询确实比普通关系查询更清晰、更稳定，并且图投影能够可靠重建时，才建议将 Neo4j 纳入正式生产架构。

## 已实现 API

所有接口都位于 `/api/v1`，业务读取需要 Bearer 身份，重建要求 `operations_manager`：

| Method | Endpoint                                             | 用途                                                 |
| ------ | ---------------------------------------------------- | ---------------------------------------------------- |
| `GET`  | `/knowledge-graph/summary`                           | 投影修订、节点/关系数量、孤立节点和类型分布          |
| `GET`  | `/knowledge-graph/entities/{id}/subgraph?depth=1..4` | 通用实体多跳子图                                     |
| `GET`  | `/knowledge-graph/search?query=...&entityId=...`     | pgvector 召回、Neo4j 扩图与融合排序                  |
| `GET`  | `/knowledge-graph/turbines/{id}/fault-trace`         | 设备故障溯源                                         |
| `GET`  | `/knowledge-graph/alarms/{id}/impact`                | 告警影响范围                                         |
| `GET`  | `/knowledge-graph/failure-modes/{id}/similar-cases`  | 失效模式与历史闭环案例                               |
| `GET`  | `/knowledge-graph/passages/{id}/support`             | Passage 支撑/反证关系与结构化分析                    |
| `GET`  | `/knowledge-graph/observability`                     | 投影年龄/同步耗时、查询延迟、Outbox、孤立/无证据指标 |
| `GET`  | `/knowledge-graph/reconcile`                         | PostgreSQL 快照与图投影对账                          |
| `POST` | `/knowledge-graph/rebuild`                           | 通过 Outbox 触发受控全量重建                         |
| `POST` | `/knowledge-graph/reindex`                           | 重建知识文档向量并触发图投影                         |

## 验收覆盖矩阵

| 验收问题                                | 实现接口                              | 自动化证据                                                                 |
| --------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------- |
| WT-023 异常由哪些传感器、告警和证据支持 | `turbines/{id}/fault-trace`、`search` | `test_alarm_workflow_updates_fault_trace_and_reconciles`                   |
| 告警影响哪些子系统、Mission、工单和备件 | `alarms/{id}/impact`                  | `test_closed_workflow_projects_case_resources_and_stable_acceptance_paths` |
| 故障模式对应哪些历史案例和处理方案      | `failure-modes/{id}/similar-cases`    | 同上，验证 `SIMILAR_TO` 与 `RESOLVED_BY`                                   |
| Passage 支撑哪些诊断、是否存在反证      | `passages/{id}/support`               | `test_passage_support_distinguishes_contradicting_evidence`                |
| 重建后关键查询是否一致                  | `rebuild`、`reconcile`                | 闭环测试比较重建前后节点与关系 UID 集合                                    |

## 本地运行

```powershell
cd C:\coding\project\wind-agent\backend
Copy-Item example.env .env
docker compose up -d postgres redis minio neo4j
python -m pip install -e ".[test,dev]"
alembic upgrade head
dramatiq windops_backend.workers
windops-outbox-relay
uvicorn windops_backend.main:app --host 0.0.0.0 --port 8000
```

前端 Worker/Sites 代理还需要配置两个仅服务端可见的变量，可参考仓库根目录 `.dev.vars.example`：

```text
WINDOPS_BACKEND_BASE_URL=http://127.0.0.1:8000
WINDOPS_BACKEND_API_TOKEN=<已配置的 WindOps 角色令牌>
```
