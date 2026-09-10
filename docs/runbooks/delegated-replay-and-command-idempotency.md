# 委托重放防护与命令幂等运行手册

## 安全边界

Sites 委托 JWT 的 `jti` 是一次性写入凭据。后端对 `POST`、`PUT`、`PATCH` 和
`DELETE` 在执行业务事务前，通过共享 PostgreSQL 表
`delegated_request_nonces` 原子消费 `jti` 的 SHA-256。第二个串行或并发请求返回
`401 DELEGATED_IDENTITY_REPLAYED`，不会进入业务写入。`GET` 等只读请求允许在令牌
有效期内重放；签名、issuer、audience、subject、method、target、body hash 和过期时间
仍按每次请求验证。

nonce 保留至 JWT `exp + delegation_clock_skew_seconds + 1 秒`，确保整个允许的时钟偏差
窗口都不能重放。每次消费最多清理 500 条已过期 nonce；不能为了释放存储而删除尚在
验证宽限期内的记录。首次接受和恶意重放分别写入
`delegated_request_audits` 的 `accepted`、`replayed` 结果。

若 replay store 查询、插入或事务失败，写请求以
`503 DELEGATION_REPLAY_STORE_UNAVAILABLE` 失败关闭。应用记录异常日志，并增加：

```text
windops_delegated_write_security_events_total{outcome="store_failure"}
```

`accepted` 和 `replayed` 使用同一指标的相应 label。生产告警应关注
`store_failure > 0` 和异常增长的 `replayed`，并关联 `X-Request-ID`、subject、method 和
target 调查；日志和审计不保存原始 JWT 或 `jti`。

## Idempotency-Key 契约

除 SCADA ingest 外，所有可重试副作用 `POST` 都要求 8–128 字符的
`Idempotency-Key`。SCADA 使用每条源消息必需且持久化唯一的 `source_event_id`，不混用
HTTP 命令键。普通命令在 `command_receipts` 中按以下完整范围唯一：

```text
authenticated subject + command type/endpoint + target + Idempotency-Key
```

请求 JSON 先做稳定规范化并计算 SHA-256。首次调用在与领域副作用相同的数据库事务中
预留 receipt、执行命令并持久化响应；同 key、同 payload 返回完全相同的响应体，并以
`Idempotency-Replayed: true` 标识。同 key、不同 payload 返回
`409 IDEMPOTENCY_KEY_REUSED`。receipt 的 `replay_count` 和 `last_replayed_at` 区分正常
网络重试与首次执行；恶意 JWT 重放则由独立委托审计记录区分。

Sites 网关会透传 `Idempotency-Replayed`。前端为每次用户命令生成一个 key；若传输失败，
只使用同一个 key 自动重试一次，以覆盖“后端已提交但响应丢失”。不得在重试时生成新 key。

EAM 投递继续通过事务 Outbox 发出，并以 `windops:{work_order_id}` 作为下游稳定键；模型
批处理为每个位置派生稳定子键，使部分成功后的重试不会重复在线推理。报告、资源、配置、
知识、Agent 和图谱命令都使用相同 receipt 边界。

## 运行检查与故障处置

1. 查询 `delegated_request_audits`，按 subject、时间、target 核对 `accepted` 与
   `replayed`；不要把正常 `Idempotency-Replayed` 当作恶意 token 重放。
2. 查询 `command_receipts` 的 scope、`request_hash`、`replay_count` 和
   `last_replayed_at`，确认网络重试只产生一条领域记录和一个领域事件。
3. replay store 故障时先保持写流量失败关闭，修复 PostgreSQL 连接/事务后验证指标恢复；
   禁止临时关闭 nonce 检查或延长 JWT 生命周期。
4. 大量过期 nonce 可由正常写流量分批回收。需要计划性清理时，只删除
   `expires_at < database current time` 的行，并在事务中限定批次；不得清理未过期 nonce。
5. `command_receipts` 是业务重放与审计证据，不使用 nonce TTL 自动删除。任何保留期清理
   必须由数据治理政策批准，并覆盖客户端最大重试窗口、调查和合规要求。

发布前必须在真实 PostgreSQL 上验证两个独立应用实例同时消费同一 JWT、同时使用同一命令
key：结果应分别为一次接受/一次拒绝，以及一次执行/一次稳定重放；数据库副作用和领域事件
均只能为一条。
