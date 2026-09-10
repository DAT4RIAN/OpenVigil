# Code Review Report

## 1. 总体评价

本次提交已修复此前的权限、并发和生产路由问题，但仍存在网关超时错配、RAG 无界处理、Outbox 消息滞留及高数据量全表加载风险，需要修改后合并。

---

## 2. Critical Issues（必须修复）

### [P1] 预测接口的后端超时超过网关默认超时

文件：

- [model_registry.py](../backend/src/windops_backend/api/model_registry.py)
- [config.py](../backend/src/windops_backend/config.py)
- [production-runtime.ts](../lib/production-runtime.ts)
- [predictive-maintenance-page.tsx](../components/pages/predictive-maintenance-page.tsx)

代码位置：

- 后端批量超时：55、240–276
- 单次推理默认超时：101
- 网关默认超时：9、143–160、612–614
- 前端调用：439–441

问题：

后端将预测批次超时设置为 25 秒，并假设网关超时是 30 秒；但网关实际默认值是 8 秒。模型推理目标的默认超时又是 15 秒。

因此一次正常但耗时超过 8 秒的模型调用，会先被网关中止，而后端仍可能继续处理到 25 秒。

影响：

- 正常推理被前端报告为超时失败
- 后端已经生成结果，但调用方无法收到
- 用户重复触发预测，增加锁竞争和模型成本
- 前后端状态短时间不一致

修复建议：

为 `/api/v1/predictive-assessments/run` 设置明确的路径级网关超时，并确保：

```text
模型单次超时 < 后端批次超时 < 网关超时
```

不要在后端硬编码假设网关始终为 30 秒。增加覆盖默认配置的超时契约测试。

---

### [P1] RAG 将超大文档作为单个、无明确超时的 Embedding 请求

文件：

- [knowledge.py](../backend/src/windops_backend/services/knowledge.py)
- [tools.py](../backend/src/windops_backend/agents/tools.py)

代码位置：

- 允许最多 400 万字符：39、63–68
- 整篇文档单次向量化：194–196
- Embedding 调用无超时：101–104
- 同步批量向量化全部缺失文档：458–474、498–510

问题：

文档提取允许最多 400 万字符，但索引时把标题和完整正文作为一个 Embedding 输入，没有分块或模型输入上限检查。

此外，重新索引和 Agent 检索路径会一次加载全部可见文档，并将所有未向量化文档放进同一个 Embedding 请求。该请求没有代码级超时控制。

影响：

- 大文档超过模型上下文限制后永久索引失败
- Worker 可能长时间卡在外部 Embedding 调用
- Agent 查询可能意外触发大批量模型请求
- 内存、Token 和调用成本不可控
- 单一整篇向量会明显降低长文档检索准确率

修复建议：

按模型 Token 上限对文档进行有重叠的受控分块，分批生成段落向量，并为 Embedding 调用增加明确的超时、重试和批量上限。

至少应禁止在同步查询路径中自动向量化整个待处理语料库；在完成分块前，应按模型限制拒绝无法安全向量化的文档。

---

### [P1] Outbox 的 `dispatched` 事件可能永久失去重投机会

文件：

- [outbox.py](../backend/src/windops_backend/outbox.py)
- [workers.py](../backend/src/windops_backend/workers.py)

代码位置：

- Relay 只查询 `pending`：289–329
- 发送后标记 `dispatched`：332–342
- Relay 派发流程：151–179

问题：

Relay 将消息发送到 Redis 后，把数据库事件改为 `dispatched`；但后续扫描只选择 `pending` 状态。

如果 Redis 在消息被消费前重启、丢失消息，或者消息未成功交付 Worker，数据库中的事件会一直停留在 `dispatched`，Relay 永远不会再次发送。Outbox 虽然保留了权威记录，却失去了故障恢复能力。

影响：

- Mission 分析可能永远不执行
- 知识文档可能永久不索引
- 知识图谱投影持续过期
- 已批准工单可能无法发送到 EAM
- 系统出现无自动恢复的业务状态停滞

修复建议：

Relay 应同时扫描超过可见性期限的 `dispatched` 事件并安全重投，直至事件进入 `processing` 或 `succeeded`。利用现有 claim token 和幂等处理抵御重复投递，并增加“消息发送后丢失”的恢复测试。

---

### [P1] 高数据量接口将完整账本加载到应用内存

文件：

- [model_registry.py](../backend/src/windops_backend/api/model_registry.py)
- [scada.py](../backend/src/windops_backend/api/scada.py)

代码位置：

- 模型监控加载全部预测记录：65–90
- 预测列表加载全部成功记录后在 Python 中去重：304–318
- SCADA 计数加载全部主键：581

问题：

`/models` 为计算监控指标读取完整 `ModelPrediction` 实体，包括输入快照和输出 JSON。

`/predictive-assessments` 先加载全部成功预测，再在 Python 中选出每台风机的最新记录。`/scada/sample-count` 为返回一个计数，实际把全部 SCADA 主键加载到内存。

这些表都会持续增长，接口参数中的 `limit` 并没有限制预测账本的数据库读取量。

影响：

- 数据规模增长后接口延迟持续恶化
- 大量无效数据库传输和 ORM 对象创建
- API 进程可能因内存峰值被终止
- 模型管理和运维探测请求可能拖垮数据库

修复建议：

- 使用 SQL 聚合计算预测数量、成功率、最后时间和延迟分位数。
- 使用窗口函数或 PostgreSQL `DISTINCT ON` 在数据库中选择每台风机的最新预测。
- 在数据库层应用筛选和分页。
- SCADA 数量使用 `SELECT COUNT(*)`，不得加载全部主键。

---

### [P1] 发布文档仍将旧迁移 `0016` 声明为当前数据库 Head

文件：

- [release-acceptance.md](./runbooks/release-acceptance.md)
- [deploy README](../backend/deploy/README.md)
- [demo-gap-audit.md](./demo-gap-audit.md)
- [0017 migration](../backend/alembic/versions/0017_knowledge_document_access_scope.py)

代码位置：

- 发布验收期望 Head：10–11
- 部署顺序期望 Head：98
- 审计文档声称唯一 Head 为 `0016`：63
- 实际最新迁移：`0017_knowledge_document_access_scope`

问题：

当前提交新增了 `0017`，但发布验收、部署说明和审计结论仍将 `0016` 声明为唯一迁移 Head。

`0017` 新增的知识文档权限字段已被运行时代码直接查询。若运维人员依据文档只确认或升级到 `0016`，知识文档和 RAG 接口会因缺少字段而失败。

影响：

- 发布验收可能错误通过未完成迁移的环境
- 生产知识接口出现数据库字段不存在异常
- 发布证据记录与真实数据库版本不一致
- 回滚和恢复流程可能使用错误的 Schema 基线

修复建议：

将所有发布和部署文档的预期 Head 更新为 `0017_knowledge_document_access_scope`。CI 应自动执行 `alembic heads`，并验证发布文档声明的版本与唯一 Head 一致。

---

## 3. Bug检查结果

### 数据库

- 事务问题：此前预测批次长事务问题已修复。
- 数据一致性：Outbox 的 `dispatched` 事件缺少丢失消息后的恢复路径。
- 并发问题：事务锁已按单台风机提交释放；未发现新的重复推理竞态。

### 异常处理

- 异常捕获：`CancelledError` 已正确重新抛出。
- 错误处理：Embedding 外部调用缺少明确超时；网关与后端预测超时不一致。

### 安全

- 漏洞风险：未发现本次 diff 中确定性的 SQL 注入、命令注入、路径穿越或新增权限绕过。

### 性能

- 性能风险：预测账本、SCADA 主键及未向量化知识语料存在无界加载或批量处理。

---

## 4. AI系统专项检查

- Agent安全：未发现无限循环或失控 Tool 调用；Embedding 调用缺少受控超时。
- Prompt安全：未发现直接允许用户覆盖系统提示词的新增路径。
- RAG安全：租户权限过滤已修复，但缺少文档分块、输入上限和受控批处理。
- Token成本：同步向量化全部待处理文档会造成不可控的 Embedding 输入和成本。

---

## 5. Improvement Suggestions

1. 增加网关、模型目标和后端批次三层超时的自动契约测试。
2. 增加 Redis 消息丢失后重投 `dispatched` Outbox 事件的故障测试。
3. 增加大文档、超模型上下文和多文档批量索引测试。
4. 对预测和 SCADA 高数据量接口增加 SQL 查询计划或查询数量断言。
5. 在 CI 中自动校验 Alembic 唯一 Head 与发布文档版本一致。

---

## 6. 最终结论

REQUEST CHANGES

必须修改：

1. 对齐预测接口的网关与后端超时。
2. 为 RAG 增加分块、输入上限、批量限制和 Embedding 超时。
3. 为长期停留在 `dispatched` 的 Outbox 事件提供自动重投。
4. 移除预测和 SCADA 接口的无界全表加载。
5. 将发布基线更新到 `0017_knowledge_document_access_scope`。
