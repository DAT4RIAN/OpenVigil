# WindOps SLO 事件响应

Prometheus 规则位于 `backend/ops/prometheus-alerts.yaml`，目标值由应用运行时指标 `windops_slo_target` 提供。值班人员不得通过临时放宽 SLO 来消除告警；阈值变更必须经过配置 revision 审批。

## HTTP error budget

1. 通过 trace ID 和 `X-Request-ID` 定位失败请求，确认是应用 5xx、依赖超时还是发布回归。
2. 查看 `/api/v1/readyz` 的 PostgreSQL、Redis、MinIO 和 Neo4j 状态；不要把 `/healthz` 成功当作依赖就绪。
3. 若告警紧随发布，回滚应用版本；若是单个外部提供方故障，保持失败关闭并通知业务值班。
4. 记录影响窗口、请求量、错误预算消耗、处置和后续行动。快燃尽为 page，慢燃尽进入有负责人和截止时间的缺陷单。

## Latency

1. 按稳定路由模板拆分 `windops_http_request_duration_seconds`，禁止按动态资产 ID 聚合。
2. 使用 OTLP trace 检查数据库、HTTP 推理、MinIO 和 Neo4j span；确认队列等待与处理时间。
3. 达到容量上限时先保护写入和审批链路，再扩容；不得用去掉超时或关闭评测门禁来换取表面延迟下降。

## Agent failure

1. 检查 `windops_agent_executions{window="30d"}` 与 AgentExecution 的 `error_code`、评测结果、降级策略。
2. 确认失败是模型提供方、schema、证据 grounding、置信度还是安全评审门禁导致。
3. 生产推理保持 fail-closed；禁止切换为确定性演示推理。必要时暂停新 Mission 分析并转人工复核。

## Telemetry stale

1. 查看数据源心跳、IngestStreamState 水位、乱序/隔离计数和连接器日志。
2. 核对 OPC UA/MQTT/HTTP 源序列、设备时钟和质量码，不对陈旧测点补演示值。
3. 恢复连接后按幂等键重放，验证游标连续且隔离样本有明确处置记录。

## Metrics absent

1. 验证 Prometheus 使用专用 bearer token 抓取 `/metrics`，且 token 未进入浏览器、日志或普通服务身份。
2. 确认网络策略、证书和服务发现；再检查应用进程。
3. 指标缺失期间使用结构化日志和 OTLP trace 辅助，但不能将“无数据”解释为“无故障”。
