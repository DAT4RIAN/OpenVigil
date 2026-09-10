# WindOps 未实现模块审计

> 审计日期：2026-08-17
> 审计范围：当前工作区源码及现有项目审计文档
> 审计口径：区分“仓库内尚未实现”“Demo 模式的显式能力边界”和“代码已实现但尚未完成真实环境验收”

## 结论

当前仓库没有整块空白页面、`TODO`、`FIXME` 或直接抛出 `NotImplemented` 的核心业务模块。主要业务页面和生产后端接口已经具备实现。

严格按仓库状态判断，当前缺口主要分为三类：

1. 尚未完成的生产功能；
2. Demo 模式有意保留的能力边界；
3. 已有代码、但尚未接入真实依赖或完成外部发布验收的生产模块。

## 尚未完成或受限的功能模块

| 类型      | 尚未完成内容                         | 当前状态                                                                                                                     | 主要证据                                                                                                                                                                                                    |
| --------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 功能实现  | 知识图谱的租户、风场和数据级权限过滤 | 已实现：后端主体作用域映射、风场租户归属、图投影作用域元数据，以及摘要/子图/检索/对账/可观测性过滤；未配置生产授权时失败关闭 | [`knowledge-graph-technology-selection.md`](./knowledge-graph-technology-selection.md#第三阶段生产化)、[`0016_tenant_asset_access_scope.py`](../backend/alembic/versions/0016_tenant_asset_access_scope.py) |
| Demo 能力 | Demo 模式下的本地知识图谱            | 不使用 fixture 冒充图数据库，必须连接 Python/Neo4j 服务；未配置时返回明确错误                                                | [`app/api/knowledge-graph/route.ts`](../app/api/knowledge-graph/route.ts)                                                                                                                                   |
| Demo 能力 | 真实 AI 推理和在线预测模型           | Demo 预测与诊断使用确定性数据，不调用真实模型，也不能用于现场控制或维护决策                                                  | [`app/api/predictive-assessments/fixtures.ts`](../app/api/predictive-assessments/fixtures.ts)                                                                                                               |
| Demo 能力 | Agent 写操作                         | Worker 中的创建决策、创建工单和更新工单只生成 dry-run 草稿，不修改业务状态                                                   | [`lib/agent-tool-runtime.ts`](../lib/agent-tool-runtime.ts)                                                                                                                                                 |
| Demo 能力 | 通用 Mission 创建                    | Demo 模式不连接通用 Mission 写入后端；Production 页面和 FastAPI 写接口已经实现                                               | [`components/pages/mission-center-page.tsx`](../components/pages/mission-center-page.tsx)                                                                                                                   |
| 实时模块  | 生产 WebSocket 事件总线              | Demo WebSocket 是确定性模拟；Production 使用带持久游标的 SSE，生产模式禁用模拟 WebSocket                                     | [`README.md`](../README.md#worker-api-与确定性数据接口)                                                                                                                                                     |
| 数字孪生  | 物理仿真和设备控制                   | 当前是只读运营数字孪生，可聚合资产、SCADA、告警、RUL、工作流状态并展示几何制品，但不执行物理仿真或控制指令                   | [`components/pages/digital-twin-page.tsx`](../components/pages/digital-twin-page.tsx)                                                                                                                       |

## 已实现但尚未完成真实环境验收

以下模块在仓库内已经存在适配器、服务、配置或发布门禁代码，但尚不能视为生产可用：

- PostgreSQL、TimescaleDB、pgvector、Redis、MinIO、Neo4j、LiteLLM、embedding 和在线模型的联合运行；
- 现场 OPC UA、MQTT、IEC、CMS、气象、ERP/EAM 端点及真实数据契约联调；
- 生产数据库迁移、受控主数据导入、活动模型部署和回滚演练；
- 镜像构建、漏洞扫描、SBOM 生成、制品签名及 Kubernetes 集群部署；
- 独立目标上的备份恢复和灾难恢复演练；
- Cloudflare Sites 生产变量、密钥、部署、发布后验证和回滚；
- DAST、人工渗透、WCAG、视觉回归、支持终端、负载、SLO 和告警路由验收。

完整的验收项、完成标准和发布阻断规则见 [`demo-gap-audit.md`](./demo-gap-audit.md#仍未完成的外部发布验收) 和 [`runbooks/release-acceptance.md`](./runbooks/release-acceptance.md)。

真实发布联合测试位于 [`backend/tests/external/test_release_environment.py`](../backend/tests/external/test_release_environment.py)。该测试仅在显式设置 `WINDOPS_RUN_EXTERNAL_RELEASE_TESTS=1` 且生产依赖齐备时运行；当前环境不满足条件时会按设计跳过。

## 工程层面的未完成事项

以下事项属于工程维护欠账，不代表业务模块缺失：

- 拆分前端超大页面组件和大型工具运行时文件；
- 由用户决定如何拆分并提交当前工作区的大量在途改动。

本轮已补齐本地 pre-commit 钩子和容器依赖锁生成/漂移校验；前端大文件拆分保留为行为无变化的后续重构，避免与当前在途业务改动混合。

详细状态见 [`engineering-improvement-audit.md`](./engineering-improvement-audit.md#四改进执行状态)。

## 判定

当前项目更准确的状态是：

> 核心业务模块和生产候选代码已经具备；知识图谱细粒度权限已补齐，Demo 模式保留若干只读和确定性边界，真实依赖接入及外部发布验收尚未完成。

因此，在真实依赖联合测试、现场系统联调和发布验收全部完成前，不应将项目标记为“生产已上线”。
