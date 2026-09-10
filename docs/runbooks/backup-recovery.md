# OpenVigil 备份、恢复与灾难演练

## 目标与边界

OpenVigil 的恢复单元包含 PostgreSQL/TimescaleDB 权威账本，以及现场证据、知识文档、模型制品、孪生制品和 CARE benchmark 派生制品五个 MinIO bucket。Neo4j 是可重建投影，Redis/Dramatiq 是执行基础设施，均不作为恢复权威源。

备份命令生成一个不可覆盖的时间戳目录，内容包括：

- `pg_dump` custom-format 数据库转储；
- 五个受治理 MinIO bucket 中的当前对象，包括 CARE `raw/standard/quality/predictions/reports` 层；
- 不含口令、令牌和数据库连接串的配置快照；
- Alembic revision、关键表行数不变量、逐文件大小和 SHA-256；
- 自身带 SHA-256 sidecar 的完整清单。

格式 v2 为五类 bucket 保存稳定角色（field evidence、knowledge、model、
twin、CARE）与源 bucket 名。普通原地恢复仍使用同名 bucket；隔离 DR 则按
角色映射到五个不同名称的目标 bucket，绝不因改名写回源 bucket。旧格式
v1 只支持同名恢复，不能用于隔离 bucket 的 DR 演练。

数据库不变量显式覆盖 CARE dataset/file/event/feature/quality、evaluation
run/event result/metric snapshot、replay run 和 anomaly policy state 表；恢复后任一
CARE 权威表行数不一致都会令演练失败，而不是只检查通用业务表。

跨 PostgreSQL 和 MinIO 无法建立单一数据库事务。生产执行备份时必须进入变更冻结窗口，或确认对象存储已启用版本控制并记录冻结起止时间。`.incomplete` 目录表示备份未完成，不得用于恢复。

## 备份

前置条件：运行身份只能读取数据库和五个 bucket；`pg_dump`、`pg_restore`、`psql` 必须与服务端 PostgreSQL 主版本精确一致（当前固定为 16，不能用 17 客户端向 16 恢复）；环境变量由密钥管理系统注入。CARE bucket 必须启用版本控制，恢复证据必须覆盖对象名、大小和 SHA-256；不得把只备份数据库描述为 CARE 已恢复。

CARE 备份只接受 `raw/standard/quality/predictions/reports` 五个受治理前缀。
`care/v6/_tmp/` 是生命周期管理的非发布临时区，明确不进入备份；其他未知
CARE 前缀会令备份失败关闭，不能被静默遗漏或伪装成已恢复制品。

```powershell
windops-backup --output-dir D:\windops-recovery
```

成功条件：命令退出码为 0，输出目录名称不是 `.incomplete`，`manifest.json` 和 `manifest.sha256` 同时存在。将完整目录复制到启用不可变保留策略的异地存储；不要只复制数据库文件。

建议策略：每日完整备份、保留 35 天，每周复制到第二故障域；每次 Alembic 迁移前额外创建一份备份。实际频率应由业务 RPO 决定。

## 恢复

恢复会清理并重建目标数据库对象。先创建隔离数据库和空的目标 bucket，确认流量没有指向目标环境。命令只有在以下预检全部通过后才开始写入：

- manifest sidecar、全部文件大小与 SHA-256 一致；
- `--confirm-target` 与连接串中的数据库名完全相同；
- manifest 的 bucket 集合与目标配置完全一致；
- 默认情况下目标 bucket 不包含同名对象。

```powershell
windops-restore `
  --bundle D:\windops-recovery\windops-backup-20260814T120000Z `
  --confirm-target windops_restore
```

只有经过变更审批的原地恢复才可使用 `--allow-object-overwrite`。恢复到不同名称的隔离数据库时需要额外使用 `--allow-database-rename`；它不减弱数据库名精确确认门禁。

恢复完成后，命令会重新查询 Alembic revision 和关键表行数，并从 MinIO 回读每个对象验证 SHA-256。任一不变量失败都视为恢复失败，不得切换流量。
恢复上传同时把清单中经内容复算的 SHA-256 写回对象 metadata，确保恢复后的
content-addressed CARE 对象仍能由普通不可变发布/重放适配器验证。

## 隔离灾难演练

演练目标必须使用不同数据库名和与源环境完全不相交的五个 bucket。以下目标变量只在演练进程中由密钥管理系统注入：

- `WINDOPS_DR_TARGET_DATABASE_URL`
- `WINDOPS_DR_TARGET_MINIO_ENDPOINT`
- `WINDOPS_DR_TARGET_MINIO_ACCESS_KEY`
- `WINDOPS_DR_TARGET_MINIO_SECRET_KEY`
- `WINDOPS_DR_TARGET_MINIO_SECURE`
- `WINDOPS_DR_TARGET_FIELD_EVIDENCE_BUCKET`
- `WINDOPS_DR_TARGET_KNOWLEDGE_BUCKET`
- `WINDOPS_DR_TARGET_MODEL_BUCKET`
- `WINDOPS_DR_TARGET_TWIN_BUCKET`
- `WINDOPS_DR_TARGET_CARE_BUCKET`

```powershell
windops-dr-drill `
  --output-dir D:\windops-drills\2026-Q3 `
  --confirm-target windops_drill_2026q3
```

命令依次执行新备份、完整清单验证、隔离恢复、数据库/对象不变量验证，并输出 `dr-drill-evidence-*.json`。该证据包含实际 RTO、恢复点、schema revision、行数不变量和 manifest 摘要，不包含凭据。

演练完成后人工验证：

1. 在隔离环境启动 API，确认 `/api/v1/readyz` 全部依赖就绪；
2. 抽样读取 Mission、Decision、工单、报告、知识文档、孪生制品，以及 CARE manifest/Parquet/quality/prediction/report 的内容哈希；
3. 执行一条只读业务查询和一次经批准的测试 Mission 闭环；
4. 保存指标、日志、trace 和演练证据；
5. 按变更流程销毁隔离资源，不复用演练 bucket。

季度至少执行一次。没有真实 `dr-drill-evidence-*.json` 和人工验收记录，不能宣称灾难演练已通过。
