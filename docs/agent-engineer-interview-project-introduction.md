# Agent 工程师面试项目介绍：OpenVigil 风电智能运维多智能体平台

> 本文用于 Agent 工程师岗位的项目介绍、面试话术和追问准备。默认采用“候选人主导项目”的第一人称表达；如果项目由团队协作完成，请把“我负责”调整为自己的真实职责，避免扩大个人贡献。

## 一句话介绍

OpenVigil 是一个面向风电运维场景的 AI-Native 多智能体平台候选实现。它不是简单的聊天界面，而是把 SCADA 数据、工业告警、故障诊断、Agent 协作、人工审批、工单执行和知识反馈组织成一条可追踪、可恢复、可审计的业务闭环。

## 30 秒介绍

我做的项目叫 OpenVigil，是一个风电智能运维多智能体平台。它解决的核心问题是：当风机出现异常时，如何让多个专业 Agent 基于真实工具和结构化证据协作完成诊断、方案评审和工单执行，同时确保高风险动作必须经过人工批准。

项目采用 React/Cloudflare Worker 前端网关和 Python FastAPI 后端，Agent 编排使用 LangGraph，工具访问 PostgreSQL、TimescaleDB、pgvector、MinIO 等生产形态组件。系统特别强调状态机、幂等、权限、证据链和离线评估，而不是只展示模型生成的一段文本。

## 2 分钟介绍

OpenVigil 的业务主线是风机异常处置。例如 SCADA 检测到主轴承振动和温度异常后，系统会创建 Alarm 和 Mission，通过 transactional outbox 把任务可靠地交给 Agent 工作流。不同角色分别完成 SCADA 分析、振动诊断、相似案例检索、健康度计算和维护方案生成。

Agent 不直接自由操作数据库或现场设备，而是只能调用经过 Schema 校验和权限控制的工具。诊断结果会形成结构化 Evidence 和三个候选 Decision，之后进入工程、安全、资源等评审以及 Human-in-the-loop 审批。只有审批通过，系统才能创建工单和预留资源；现场任务还必须按顺序提交带 URI、SHA-256 和 measurement 的证据，全部满足门禁后才能关闭告警、回写健康度并生成知识案例。

技术上，我重点解决了五类 Agent 工程问题：

1. 用显式状态图和领域状态机约束 Agent，而不是依赖 Prompt 猜测流程。
2. 用类型化工具、最小权限和服务端校验控制 Agent 的行动边界。
3. 用 outbox、幂等键、revision、租约和 fencing token 处理重试、并发和 worker 崩溃。
4. 用公开的工具调用、证据、决策摘要和指标实现可观测性，不保存或伪造隐藏 Chain-of-Thought。
5. 接入 CARE v6 风机故障检测数据集，建设独立的数据合同、质量规则、离线评估、模型门禁和在线回放闭环，避免只用手写 Demo 数据评价 Agent。

当前项目是通过本地和隔离环境验证的生产候选实现，不宣称已经在真实风场上线。这个边界也是我在设计中主动保留的：本地测试通过不等于生产身份、真实模型供应商、现场数据和集群发布已经验收。

## 项目背景与目标

传统风电运维系统通常存在几个问题：

- SCADA、告警、维护记录和知识文档相互割裂。
- 告警很多，但缺少从异常到诊断、决策和执行的闭环。
- 大模型可以生成建议，却很难证明它读了什么数据、调用了什么工具、为什么允许执行。
- Agent 失败、重试或并发运行时，容易产生重复任务、重复工单和状态不一致。
- 离线模型指标与在线业务告警之间缺少可追溯的发布门禁。

OpenVigil 的目标不是“让多个 Agent 聊天”，而是建立一套可执行的 Agent 工程框架：

```text
感知数据 → 结构化异常 → Mission → Agent 工具调用 → Evidence
→ Decision → 多角色评审 → 人工审批 → Work Order
→ 现场证据 → 结果验证 → 知识沉淀
```

## 系统架构

```mermaid
flowchart TB
  browser["React 19 Web UI"] --> gateway["Cloudflare Sites Worker\n身份网关与路由白名单"]
  gateway --> api["FastAPI / Pydantic / SQLAlchemy async"]

  api --> pg["PostgreSQL / TimescaleDB / pgvector"]
  api --> outbox["Transactional Outbox"]
  outbox --> queue["Redis / Dramatiq"]
  queue --> graph["LangGraph Agent Workflow"]
  graph --> tools["11 个类型化业务工具"]
  graph --> llm["LiteLLM reasoning / embedding adapter"]
  tools --> pg
  tools --> objectStore["MinIO 可验证制品"]
  tools --> graphStore["Neo4j 知识图谱适配器"]

  care["CARE v6 只读数据源"] --> contract["数据合同 / 质量规则 / 真值隔离"]
  contract --> parquet["PyArrow 宽表 Parquet"]
  parquet --> evaluation["场内留一资产离线评估"]
  evaluation --> objectStore
  evaluation --> api
  evaluation --> replay["有界在线回放"]
  replay --> pg
  replay --> graph
```

### 双运行形态

项目刻意区分两套运行边界：

- `demo`：Worker/D1 上的确定性产品演示，包含 64 台模拟资产、WT-023 闭环、17 个确定性工具和本地 passage 检索，适合 UI 演示和稳定回归。
- `production`：Sites Worker 作为每用户身份网关，访问独立部署的 Python API/worker；生产模式禁止 fixture 回退，并校验后端 release ID、完整 commit SHA 和镜像摘要。

这两套运行时不能混为一谈。Demo 工具执行不能被描述成真实生产 Agent 调用，Sites 发布成功也不能代表 Python 后端和现场依赖已经上线。

## Agent 工程设计

### 1. Agent 不是自由对话，而是受约束的状态图

LangGraph 中只保存公开、可审计的状态，例如：

- Mission、资产和告警引用；
- 当前工作流节点和状态；
- 工具调用输入、结构化输出和错误；
- Evidence、Decision 和审批结果；
- 延迟、token、模型和版本信息。

领域状态转换仍由服务端状态机校验。Agent 不能通过生成一段“已经批准”的文本绕过审批，也不能直接把 Mission 标记为完成。

### 2. 工具层采用类型化合同和最小权限

Python Agent 工具目录包含 11 个有真实业务语义的工具：

| 类型       | 工具示例                                                                     | 设计要点                                                |
| ---------- | ---------------------------------------------------------------------------- | ------------------------------------------------------- |
| 资产与时序 | `get_turbine_status`、`query_scada`、`query_vibration`                       | 查询范围、变量和返回数量有上限                          |
| 历史与知识 | `query_alarm_history`、`query_maintenance_history`、`query_similar_failures` | 受租户/资产范围约束，返回来源引用                       |
| 环境与资源 | `query_weather`                                                              | 不把缺失天气数据包装成安全作业窗口                      |
| 确定性计算 | `calculate_health_score`、`predict_rul`                                      | 输出模型/规则版本，不直接修改资产状态                   |
| 受控写入   | `create_decision`、`create_work_order`                                       | 只允许合法 Mission 状态；工单要求真实审批和原子资源预留 |

每个工具都经过 Pydantic/JSON Schema 校验、权限检查、范围限制和审计记录。高风险操作没有“万能 execute SQL”或“执行任意 shell”入口。

### 3. Human-in-the-loop 是服务端硬门禁

系统支持批准、拒绝、退修和升级四类人工结果。审批身份来自服务端认证主体，请求体中的 `approver` 不能覆盖真实身份。

工单执行还包含第二层门禁：

- 只有已批准的 Decision 能创建工单；
- 工单任务必须按治理计划顺序完成；
- 每项任务必须提供可验证制品 URI、SHA-256 和结构化 measurement；
- 生产路径只接受批准的 MinIO 对象；
- 全部任务和最终测量满足要求后才能关闭业务闭环。

### 4. 幂等、并发和故障恢复

Agent 系统不能假设一次请求只执行一次。项目在不同层级处理重复和竞争：

- 写请求携带 `Idempotency-Key`、`correlationId` 和 `expectedRevision`；
- 数据库保存幂等 receipt，重复请求返回相同结果；
- revision/CAS 拒绝陈旧客户端覆盖新状态；
- SCADA、Alarm、Mission 和 outbox event 在同一事务中提交；
- Dramatiq worker 使用可恢复租约和 fencing token；
- 过期 worker 不能覆盖新 worker 已提交的终态；
- CARE 导入/评估使用检查点、心跳、取消、有限重试和不可变发布。

### 5. 可观测性与解释边界

系统展示的是可以核验的内容：

- 哪个 Agent 调用了哪个工具；
- 输入引用、结构化输出和错误类型；
- 使用的模型、部署、阈值和特征版本；
- 形成了哪些 Evidence、Decision 和审批记录；
- 延迟、成功率、失败率、节点和 token 指标。

项目不保存或展示模型隐藏 Chain-of-Thought。所谓“可解释”来自证据、工具结果、规则、来源和决策摘要，而不是伪造一段模型内心推理。

## CARE v6 数据与模型评估

为了避免 Agent 和异常检测只依赖手工 fixture，项目接入了 CARE v6 风机故障检测数据集。

### 数据规模

| 项目             |           规模 |
| ---------------- | -------------: |
| CSV 文件         |            101 |
| 事件             |             95 |
| 场内命名空间资产 |             36 |
| 时间点           |      5,242,948 |
| 异常 / 正常事件  |        45 / 50 |
| A/B/C 信号映射   | 81 / 252 / 952 |
| 预测点           |        281,249 |

### 关键设计

- 原始数据只读，不进入 Git 仓库。
- 使用元数据驱动的全列映射，未知、缺失、重复或歧义列失败关闭。
- 合法零值保留，疑似缺失写入独立质量 mask，不修改原始值。
- 全信号保存为分区宽表 Parquet，避免把约 8.77 亿个标量值展开写入 TimescaleDB。
- 默认只启用经元数据批准的 Avg 特征，Min/Max/Std 默认关闭。
- prediction 先冻结，最终 evaluator 才能读取 truth，训练和在线推理没有真值权限。
- 使用场内 leave-one-asset-out 协议；跨场 ontology 未完成前，跨场评估失败关闭。
- 失败和不可评分事件必须进入汇总，不能通过删除失败样本提高指标。

### 全量验证结果

本地候选完成了 95 个事件的全量导入和 36 个场内 fold：

- 导入 5,242,948 行，实测约 693.52 rows/s；
- 导入进程峰值约 522 MB；
- 评估耗时约 125.83 秒，进程峰值约 236 MB；
- 12 个候选满足门禁，24 个候选不满足门禁；
- 失败候选仍然完整登记，没有伪报上线；
- 只有精选的有界窗口进入在线回放和告警链路。

这些结果是本地候选证据，不等于模型已经在真实风场生产运行。

## 一个完整业务案例：WT-023 主轴承异常

面试时可以按以下顺序介绍：

1. SCADA 发现主轴承振动 RMS、温度和多变量异常分数超过阈值。
2. 服务端在同一事务内写入样本、Alarm、Mission 和 outbox event。
3. Agent 通过工具查询 SCADA 窗口、振动特征、历史告警、维护记录和相似案例。
4. 系统形成结构化证据和差异诊断，不把相似性结果当作确定故障结论。
5. Decision Agent 生成三个受约束方案，Review Agent 检查安全、工程、资源和经济性。
6. 人工审批后才能创建工单和预留班组、船舶、备件。
7. 现场人员按顺序提交五项带哈希证据的任务结果。
8. 最终健康测量达到闭环阈值后，系统关闭告警和 Mission，并生成知识案例。

这个案例的价值在于：它展示的不是单次 LLM 回复，而是一条包含数据、工具、状态、权限、人工决策和执行证据的端到端 Agent 工作流。

## 我重点解决的技术难点

### 难点一：如何防止 Agent 绕过业务规则

解决方式是把 Prompt 与权限分离。Prompt 负责引导推理，真正的状态转换由服务端状态机、认证主体、数据库约束和工具合同控制。即使模型输出恶意或错误内容，也不能直接改变审批和执行状态。

### 难点二：如何让重试安全

网络、模型和 worker 都可能失败。项目使用幂等键、数据库 receipt、唯一约束、revision、事务 outbox、租约和 fencing token，让“至少一次投递”不会演变成重复工单或旧 worker 覆盖新结果。

### 难点三：如何评价 Agent 和模型是否真的有效

测试不仅断言接口返回 200，还覆盖负向路径：权限不足、陈旧 revision、重复请求、对象哈希错误、模型门禁失败、真值泄漏、失败事件遗漏、worker 重启和数据库并发。CARE v6 则提供真实数据合同、离线指标和在线回放证据。

### 难点四：如何处理大规模宽表数据

CARE C 场单行接近千列。如果整体加载到内存或把每个标量拆成时序行，资源成本会失控。项目选择 PyArrow 分块读取、固定 row group 的宽表 Parquet、列裁剪和内容寻址制品，只把在线需要的窗口写入 TimescaleDB。

### 难点五：如何保持“可解释”但不暴露 Chain-of-Thought

项目只保存工具输入输出、证据引用、公开决策摘要、阈值、特征版本和指标。这样既能审计结果，又不会依赖或伪造模型隐藏推理。

## 工程质量与验证

截至 2026-08-29 的本地复核结果：

| 验证项            | 结果                                                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 前端 Node 测试    | 143/143                                                                                                                           |
| Chromium 本地合同 | 6 passed；1 个真实跨层外部环境用例按条件 skip                                                                                     |
| CARE 专项         | 105/105                                                                                                                           |
| Python 全量       | 393 collected；369 passed；24 个受控外部环境 skip；0 failure/error                                                                |
| Python 覆盖率     | 75.82%                                                                                                                            |
| 其他门禁          | build、bundle、启动 smoke、TypeScript、ESLint、Prettier、Ruff、mypy、Bandit、依赖审计、Compose 配置和 Alembic offline render 通过 |

测试有效性方面，项目明确禁止：

- 删除失败测试或使用 skip 掩盖问题；
- 弱化断言；
- hardcode 返回值绕过实现；
- 使用无意义 mock 代替前后端真实链路；
- 关闭鉴权、类型检查或安全门禁；
- 把外部环境 skip 写成发布通过。

隔离 PostgreSQL/TimescaleDB、MinIO、CARE 回放和 DR 已有历史候选证据，但正式发布仍要求在受保护环境以 `skip = failure` 的方式重新执行。

## 技术选型说明

| 领域     | 技术                                                         | 选择原因                                               |
| -------- | ------------------------------------------------------------ | ------------------------------------------------------ |
| 前端     | React 19、TypeScript、TanStack Query/Table、Zustand、ECharts | 适合复杂运营工作台、服务端数据和高密度时序展示         |
| 网关     | Cloudflare Sites Worker                                      | 隔离浏览器凭据，签发短期委托身份并执行路由白名单       |
| API      | FastAPI、Pydantic 2、SQLAlchemy async                        | 类型化接口、异步 I/O 和清晰的领域/事务边界             |
| Agent    | LangGraph、LiteLLM                                           | 显式状态图和多供应商模型适配，避免把流程埋在 Prompt 中 |
| 任务     | Redis、Dramatiq、transactional outbox                        | 支持可靠异步执行、重试和 worker 故障恢复               |
| 数据     | PostgreSQL、TimescaleDB、pgvector                            | 事务业务数据、时序数据和向量检索统一治理               |
| 制品     | MinIO                                                        | 内容寻址、哈希校验、分层权限和不可变派生制品           |
| 图谱     | Neo4j 适配器                                                 | 表达设备、部件、故障、证据和案例关系                   |
| 离线数据 | PyArrow、Parquet、scikit-learn                               | 有界内存宽表处理、列裁剪和可复现基线                   |

## 项目的诚实边界

面试时应主动说明以下限制：

- 当前是经过本地和隔离环境验证的生产候选，不是已在真实风场上线的系统。
- Demo 的 64 台资产和 17 个 Worker 工具是确定性数据/逻辑，不等同于生产 Agent。
- LiteLLM、Neo4j、Redis、现场 SCADA/CMS/气象/EAM 等仍需在批准环境完成联合验收。
- CARE 已完成场内泛化验证，但没有跨场 ontology，因此不声称跨场泛化。
- 本地镜像内容 ID 不等于注册表摘要、签名、SBOM 或集群准入证据。
- Agent 输出不能直接用于真实设备控制、安全判断或维护决策。

主动讲清边界通常比把项目包装成“已经生产落地”更能体现工程判断力。

## 常见面试追问

### 1. 为什么要使用 Multi-Agent，而不是一个大 Agent？

因为场景包含诊断、工程、安全、资源、经济和执行等不同职责，它们拥有不同工具、权限和验收标准。多 Agent 的价值不是角色名称多，而是能形成职责隔离、独立评审和清晰审计。如果所有角色共用相同工具和权限，多 Agent 只会增加复杂度。

### 2. Agent 发生幻觉怎么办？

模型文本不能直接改变业务状态。事实必须来自工具和数据库，关键输出使用 Schema 校验，引用必须指向 Evidence，高风险状态转换由服务端重新校验。没有证据时返回不确定或失败，不补造结论。

### 3. 如何处理 Agent memory？

我区分工作流状态、业务长期状态和知识检索：

- LangGraph 保存当前任务的公开状态；
- PostgreSQL 保存 Mission、工具账本、审批、工单和审计等权威状态；
- pgvector/知识图谱用于检索历史知识；
- 不把全部聊天历史无边界塞回模型上下文。

### 4. 如何保证工具调用安全？

使用明确工具目录、类型化参数、服务器身份、租户/资产范围、数量上限、幂等键和审计。写工具只暴露受控领域命令，不提供任意 SQL、shell 或任意 URL 请求。

### 5. 为什么需要 transactional outbox？

如果先提交数据库、再发消息，进程可能在两步之间崩溃；如果先发消息、再提交数据库，worker 又可能读不到业务状态。Outbox 让业务数据和待发送事件在同一事务提交，再由 relay 可靠分发。

### 6. 如何防止重复创建工单？

通过 `Idempotency-Key`、数据库唯一约束、幂等 receipt、Mission 状态校验和事务内创建。相同输入重试返回相同结果，不同输入复用同一键则返回冲突。

### 7. 如何评估 Agent？

分为三个层次：工具和状态机单元测试、跨服务业务链集成测试、真实数据离线评估与选择性在线回放。除成功率外，还关注证据完整度、权限违规、失败事件遗漏、延迟、重试一致性和人工门禁是否可绕过。

### 8. 项目中最难的部分是什么？

可以重点回答“让 Agent 的非确定性推理进入确定性的业务系统”。难点不在调用 LLM，而在状态、工具、权限、并发、失败恢复和评估之间建立一致合同。

### 9. 如果继续迭代，优先做什么？

优先级建议：

1. 在受保护环境完成真实模型供应商、PostgreSQL/Redis/MinIO/Neo4j 联合门禁。
2. 接入真实 OPC UA/MQTT/SCADA、CMS、气象和 EAM 数据契约。
3. 增加 Agent 离线评测集、在线 shadow evaluation 和 prompt/model version 对比。
4. 完成镜像签名、SBOM、集群准入、SLO、告警和灾难恢复演练。
5. 在建立跨场 ontology 和人工复核流程后，再评估 CARE 跨场泛化。

## STAR 表达模板

### 案例一：Agent 工作流可靠性

- **Situation**：异常诊断会触发多个 Agent、数据库写入和异步任务，网络重试可能导致重复 Mission 或工单。
- **Task**：保证至少一次消息投递下的业务结果仍然唯一、可恢复、可审计。
- **Action**：设计事务 outbox、幂等 receipt、revision/CAS、worker 租约和 fencing token，并增加重复、并发、过期 worker 和重启测试。
- **Result**：同一请求可安全重放，陈旧 worker 无法覆盖新状态，失败执行会留下结构化审计而不是静默丢失。

### 案例二：真实宽表数据接入

- **Situation**：CARE v6 包含 5,242,948 行，C 场接近千列，直接整体加载或展开写入时序库会造成资源风险。
- **Task**：在有界内存内完成全列保存、质量审计、离线评估和在线回放。
- **Action**：采用 PyArrow 分块处理、宽表 Parquet、固定 row group、列裁剪、检查点和不可变内容寻址制品，并将在线写入限制为精选窗口。
- **Result**：完成 95 个事件全量导入，吞吐约 693.52 rows/s，进程峰值约 522 MB；36-fold 评估覆盖全部事件且失败候选未被遗漏。

### 案例三：测试假完成治理

- **Situation**：文档门禁曾硬编码旧测试总数，README 更新为真实现状后反而导致全量测试失败。
- **Task**：修复测试，同时避免通过恢复旧文案或删除断言制造通过。
- **Action**：将测试从“必须出现某个历史数字”改为“拒绝已知过期基线，并要求自动发现计数、外部 skip 不算发布通过、受保护门禁遇 skip 失败”。
- **Result**：定向和全量回归通过，测试验证长期不变量，不再把文档锁死在某次快照。

## 简历项目描述参考

可以根据自己的真实参与范围选择 3–5 条：

- 设计并实现风电智能运维多 Agent 工作流，将 SCADA 异常、诊断证据、方案评审、人工审批、工单执行和知识反馈串成可审计闭环。
- 基于 LangGraph、FastAPI 和类型化工具合同构建受约束 Agent Runtime，通过 RBAC、HITL、JSON Schema 和服务端状态机防止模型绕过高风险业务门禁。
- 使用 transactional outbox、幂等 receipt、revision/CAS、租约与 fencing token 解决异步 Agent 重试、并发写入和 worker 崩溃恢复问题。
- 接入 CARE v6 的 95 个事件、5,242,948 行宽表数据，使用 PyArrow/Parquet 实现有界内存导入、质量 mask、真值隔离和 36-fold 场内评估。
- 建立从模型评估、不可变 prediction 制品到在线回放、Alarm/Mission 的可追溯发布链，保留失败候选并阻止前端状态绕过服务端门禁。
- 建设前后端、数据库、浏览器、迁移、安全和供应链测试体系；当前本地复核后端 369 passed、前端 143 passed，关键外部测试在受保护环境采用 skip 即失败策略。

## 面试表达建议

- 先讲业务问题和闭环，再讲框架名称。
- 强调“如何约束 Agent”，不要只强调“用了 LangGraph”。
- 用一个具体失败场景说明幂等、outbox 或 fencing 的价值。
- 主动区分 Demo、生产候选和真实上线。
- 讲指标时同时说明数据范围、协议和限制。
- 不展示或声称拥有模型隐藏 Chain-of-Thought。
- 对个人贡献只描述自己实际完成或主导的部分。

## 相关项目文档

- [项目 README](../README.md)
- [CARE v6 接入开发计划](care-v6-integration-development-plan.md)
- [CARE 列式流水线 ADR](adr/0001-care-v6-columnar-pipeline.md)
- [CARE 全量运行手册](runbooks/care-full-scale-operations.md)
- [CARE 制品治理手册](runbooks/care-artifact-governance.md)
- [测试与质量门禁](testing-quality-gates.md)
- [生产发布验收](runbooks/release-acceptance.md)
- [Demo 与生产差距审计](demo-gap-audit.md)
