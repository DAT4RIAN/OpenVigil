# Code Review Report

## 1. 总体评价

本次提交完善了生产数据接入与权限隔离，但预测任务的事务边界、取消处理及知识权限规则仍存在稳定性和数据一致性风险，需要修改后合并。

---

## 2. Critical Issues（必须修复）

### [P1] 批量推理在单个长事务中持有 PostgreSQL 事务锁

文件：

- [models.py](../backend/src/windops_backend/services/models.py)
- [model_registry.py](../backend/src/windops_backend/api/model_registry.py)
- [schemas.py](../backend/src/windops_backend/schemas.py)

代码位置：

- `pg_advisory_xact_lock`：372–380
- 批量循环及最终提交：237–258
- 批量上限：355

问题：

`pg_advisory_xact_lock` 只能在事务结束时释放，但接口使用同一个 Session 串行处理最多 64 台风机，并在整个循环完成后才提交。

因此第一台风机的锁、未提交记录和数据库连接会一直保留到最后一次外部推理结束。单次推理允许最长 60 秒，而网关请求超时最多只有 30 秒。

影响：

- 同一预测键的并发请求长时间阻塞
- 批量请求可能在网关超时后继续占用数据库资源
- 长事务累积，可能导致连接池耗尽和接口级联超时
- 预测结果已执行但调用方收到超时，容易触发重复请求

修复建议：

每台风机使用独立事务，并在该项完成后立即提交或回滚，确保事务锁及时释放。同时为同步批量接口设置不超过网关限制的总超时；若必须支持大批量，应改为异步任务并返回任务标识。

---

### [P1] 推理代码捕获 `BaseException`，导致取消和停机信号被吞掉

文件：

[models.py](../backend/src/windops_backend/services/models.py)

代码位置：

448–467

问题：

外部推理调用使用 `except BaseException`，并将所有异常转换为普通失败结果。该范围包括 `asyncio.CancelledError`、`KeyboardInterrupt` 和 `SystemExit`。

任务被取消或服务关闭时，代码会记录失败并正常返回，批量接口随后可能继续处理其他风机并提交事务。

影响：

- 服务无法及时取消推理任务
- 优雅停机被延迟
- 已取消请求仍可能继续写入预测和事件记录
- 加剧前述长事务及锁阻塞问题

修复建议：

显式重新抛出取消异常，再捕获普通业务异常：

```python
except asyncio.CancelledError:
    raise
except Exception as exc:
    ...
```

同时确保取消路径由 Session 依赖执行回滚。

---

### [P1] 知识权限别名在写入授权与读取 SQL 中含义不一致

文件：

[knowledge_access.py](../backend/src/windops_backend/services/knowledge_access.py)

代码位置：

- SQL 权限条件：51–58
- 写入授权判断：89–107

问题：

代码声明 `knowledge_documents`、`knowledge_document` 等均为 `knowledge` 的合法别名。

写入时，只要策略包含任一别名便允许创建文档，文档实际保存的 `data_scope` 固定为 `knowledge`；读取时却直接生成：

```sql
data_scope IN ('knowledge_documents')
```

因此使用受支持别名的用户可以成功写入文档，但无法随后通过列表、详情或 RAG 检索读取该文档。

影响：

- 写入成功后数据不可见
- RAG 检索遗漏合法文档
- 相同权限策略在知识图谱、写入接口和读取接口中产生不同结果

修复建议：

在构造 SQL 条件前将所有合法别名归一化为 `KNOWLEDGE_DATA_SCOPE`，读取条件统一比较 `data_scope == "knowledge"`。增加每个别名的“写入后列表、详情及向量检索”测试。

---

### [P1] 生产 SCADA 查询缺少风机参数时静默读取固定资产

文件：

- [production-domain-adapter.ts](../lib/production-domain-adapter.ts)
- [route.ts](../app/api/scada-history/route.ts)

代码位置：

- 固定回退：988
- 生产路由直接转发：8–9

问题：

生产模式下，如果请求没有 `turbineId`，适配器会静默使用 `WT-023`。但后端接口明确要求提供 `turbine_id`，说明生产接口不存在默认风机语义。

影响：

- 参数缺失时返回另一台风机的真实数据，而不是参数错误
- 监控页面或第三方调用可能把 `WT-023` 数据错误归属给当前资产
- 需要确认 `WT-023` 是否还受独立资产权限控制；否则存在跨资产数据暴露风险

修复建议：

生产模式下要求 `turbineId` 为非空参数，缺失时返回 400/422。固定默认值只能保留在演示数据路径中。

---

## 3. Bug检查结果

### 数据库

- 事务问题：批量推理在外部网络调用期间持续持有同一事务。
- 数据一致性：知识权限别名导致写入成功但读取失败；SCADA 缺参返回固定资产数据。
- 并发问题：事务级 advisory lock 直到整个批次提交后才释放。

### 异常处理

- 异常捕获：`BaseException` 会吞掉任务取消及进程退出异常。
- 错误处理：生产 SCADA 缺少必填资产参数时未返回参数错误。

### 安全

- 漏洞风险：未发现确定性的 SQL 注入、命令注入或路径穿越。需要确认固定 `WT-023` 回退前是否存在资产级授权检查。

### 性能

- 性能风险：最多 64 次外部推理被串行放在一个数据库事务中，可能造成长时间锁等待和连接池压力。

---

## 4. AI系统专项检查

- Agent安全：未发现新增的无限循环或 Tool 调用失控；模型推理取消机制存在缺陷。
- Prompt安全：未发现本次 diff 引入的直接系统提示词覆盖问题。
- RAG安全：权限过滤已前置到检索阶段，但数据范围别名错误会导致合法文档被遗漏。
- Token成本：未发现无上限上下文增长或明显重复 LLM 调用。

---

## 5. Improvement Suggestions

1. 增加 PostgreSQL 双 Session 并发测试，验证每台风机完成后事务锁立即释放。
2. 增加推理任务取消测试，确保 `CancelledError` 被重新抛出且事务回滚。
3. 参数化测试所有知识数据范围别名，覆盖写入、列表、详情和向量检索。
4. 增加生产 SCADA 缺少 `turbineId` 时返回 422 的契约测试。

---

## 6. 最终结论

REQUEST CHANGES

必须修改：

1. 缩小批量推理事务边界，避免跨整个批次持有事务锁。
2. 不得吞掉 `CancelledError` 等 `BaseException`。
3. 统一知识权限别名的写入与读取语义。
4. 移除生产 SCADA 的固定风机回退。
