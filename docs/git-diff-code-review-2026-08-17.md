# Code Review Report

> 审查日期：2026-08-17
> 审查范围：当前工作区相对 HEAD 的未暂存 Git Diff
> 审查边界：仅分析本次差异及理解变更所需的必要上下文

## 1. 总体评价

按当前工作区相对 HEAD 的未暂存 git diff 审查，本次提交前端门禁通过，但补丁不自包含，并存在生产数据作用域、遥测并发和工单排程一致性风险，需要修改后合并。

## 2. Critical Issues（必须修复）

### [P1] Git Diff 不包含新增依赖，补丁无法独立构建

文件：

- [backend/src/windops_backend/main.py](../backend/src/windops_backend/main.py)
- [backend/src/windops_backend/api.py](../backend/src/windops_backend/api.py)

代码位置：

main.py 第 14–32 行；api.py 整文件删除。

问题：

当前 diff 删除了原有 api.py，并开始导入新的 api/ 包、identity.py、security.py、知识图谱模块和生产运行时模块，但这些文件仍是 untracked，不在普通 git diff 中。数据库模型变化对应的 Alembic 迁移也未包含在 diff 中。

当前工作区能够构建，是因为本机仍存在这些未跟踪文件；将该 diff 单独应用到干净工作区后，后端会在导入阶段失败，前端也会缺少生产运行时模块。

影响：

- CI 构建失败
- 后端无法启动
- 数据库模型与迁移不一致
- 发布制品不完整

修复建议：

将本次提交依赖的新增 API 包、服务、生产运行时、迁移、测试和部署文件全部纳入提交，然后在干净工作区重新执行构建和迁移验证。若它们不属于本次提交，则必须撤回对这些模块的导入和模型变更。

### [P1] 生产知识检索会默认使用 Demo 的 WT-023/Mission 作用域

文件：

[app/api/knowledge-assistant/route.ts](../app/api/knowledge-assistant/route.ts)

代码位置：

第 98–106 行。

问题：

在判断 Production 模式之前，缺省 turbineId 和 missionId 已被替换为 featuredMission 中的固定 Demo 标识。生产调用只提交 question 时，会自动向后端发送 entityId=WT-023，返回结果也会声称属于固定 Demo Mission。

这使“未指定作用域”被错误解释成“查询 WT-023”，而不是全局检索、无作用域检索或者请求校验失败。

影响：

- 查询错误资产的数据
- 生产回答携带虚构 Mission 关联
- 在后端权限过滤不完整时扩大数据暴露风险
- 无 WT-023 的生产环境持续返回空结果

修复建议：

在 Production 分支中单独解析作用域：未提供时保留 null/空值，或明确要求客户端提供真实资产范围。featuredMission 默认值只能在 Demo 分支使用。后端仍需独立执行资产和知识文档权限过滤。

### [P1] 新遥测流首次并发写入存在唯一键竞争

文件：

[backend/src/windops_backend/services/ingest.py](../backend/src/windops_backend/services/ingest.py)

代码位置：

第 80–94 行。

问题：

_stream_state() 先通过 SELECT ... FOR UPDATE 查询流状态；记录不存在时直接插入。PostgreSQL 的 FOR UPDATE 不会锁住不存在的键，因此两个并发首包可以同时观察到空记录并插入相同的 (source_id, stream_key) 主键。

其中一个 flush() 会抛出未处理的 IntegrityError。

影响：

- 并发遥测接入返回 500
- 数据接入出现短暂丢包或反复重试
- 首次启动或新增测点时故障概率较高

修复建议：

使用 PostgreSQL INSERT ... ON CONFLICT DO NOTHING 初始化状态，再重新 SELECT ... FOR UPDATE；或者使用基于 source_id + stream_key 的事务级 advisory lock。还应增加两个不同事件同时初始化同一流的并发测试。

### [P1] 工单排程没有遵守已审批方案的天气窗口

文件：

[backend/src/windops_backend/agents/tools.py](../backend/src/windops_backend/agents/tools.py)

代码位置：

第 809–821 行、第 854–889 行。

问题：

代码读取了已审批 alternative，但只保留 action，忽略其中的 weather_window_id。随后选择任意第一条 suitable 且尚未结束的天气窗口。

此外，查询没有验证：

- 窗口是否已经开始；
- 剩余窗口是否覆盖工单预计时长；
- 所选窗口是否就是人工审批的窗口。

因此可能生成 planned_start 已经过期，或者 deadline 早于预计完工时间的工单。

影响：

- 工单与人工审批结果不一致
- 排程落入错误或即将关闭的海况窗口
- 现场安全和资源调度风险
- 审计链无法证明执行计划与批准方案一致

修复建议：

从 selected_alternative 读取并校验 weather_window_id；以 max(now, starts_at) 作为候选开始时间，并要求 ends_at >= planned_start + estimated_duration。无法满足已批准窗口时应拒绝创建工单并重新进入审批或排程流程。

### [P1] 生产报告导出只能在默认集合页中查找报告

文件：

[app/api/reports/[id]/export/route.ts](../app/api/reports/%5Bid%5D/export/route.ts)

代码位置：

第 88–104 行。

问题：

导出接口请求未过滤、未指定分页参数的 /api/v1/reports 集合，然后只在当前响应数组中执行 .find(id)。

当生产报告数量超过后端默认页大小，或用户从搜索、类型、时间过滤结果中打开较旧报告时，该报告可能不在默认集合页中，导出接口会错误返回 404。

影响：

- 历史报告无法导出
- 前端能够预览但不能导出同一报告
- 数据量增长后出现稳定性回归
- 每次导出不必要地传输整页报告内容

修复建议：

增加并调用按 ID 获取不可变报告快照的接口，例如 /api/v1/reports/{id}。若暂时只能使用集合接口，应传递精确 ID 过滤条件并验证唯一结果，不能依赖默认分页。

## 3. Bug检查结果

### 数据库

- 事务问题：未发现明确的事务提交后再回滚问题。
- 数据一致性：工单天气窗口可能与已审批 alternative 不一致。
- 并发问题：遥测流状态首次创建存在唯一键竞争。

### 异常处理

- 异常捕获：_stream_state() 的并发插入 IntegrityError 未处理。
- 错误处理：生产报告导出会把“未出现在默认分页”误报为“报告不存在”。

### 安全

- 漏洞风险：未发现新增 SQL 注入、命令注入或路径穿越；但生产 RAG 使用 Demo 默认资产作用域，必须修复并确认后端始终执行文档与实体权限过滤。

### 性能

- 性能风险：报告导出读取集合页而非单个报告，报告体积和数量增加后会产生不必要的数据传输。

## 4. AI系统专项检查

- Agent安全：模型调用增加了超时、有限重试、严格 Schema 和失败关闭，未发现无限循环或无界 Tool 调用。
- Prompt安全：输出限制了结构和证据引用，但仍需确保检索文档只能作为非可信数据处理；本次 diff 未提供完整的 Prompt Injection 回归证据。
- RAG安全：生产默认 WT-023 作用域是明确问题；新增权限实现位于未跟踪文件中，不在本次 git diff，无法确认完整的文档权限隔离。
- Token成本：调用次数和重试次数有上限，未发现无限上下文增长；需要继续保留 provider usage 审计。

## 5. Improvement Suggestions

1. 增加“只应用已提交 diff”的干净工作区 CI 构建，防止依赖本地 untracked 文件。
2. 增加两个首包并发初始化同一遥测流的 PostgreSQL 集成测试。
3. 增加 Production 知识助手省略作用域时不得出现 WT-023 或 Demo Mission 的测试。
4. 增加工单天气窗口已过期、剩余时间不足及审批窗口不匹配的测试。
5. 增加导出非默认分页历史报告的测试。

## 6. 最终结论

**REQUEST CHANGES**

必须修改：

- 将所有被引用的新增文件和数据库迁移纳入提交，保证 diff 自包含。
- 移除 Production 知识检索中的 Demo 默认作用域。
- 消除遥测流状态首次创建的并发竞争。
- 强制工单使用已审批且时长充足的天气窗口。
- 将生产报告导出改为按 ID 获取不可变快照。
