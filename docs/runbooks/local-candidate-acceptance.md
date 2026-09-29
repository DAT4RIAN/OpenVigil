# 本机候选环境：openvigil-2026-09-27-rc.1

> **本页以下为旧 snapshot1 阶段的历史记录。** 2026-09-28 用户已补充模型预算及本机身份授权，当前操作与状态请以[本机登录与权限验收](local-identity-acceptance.md)及 `EXECUTION_PROGRESS.md` 顶部为准。下方旧的待授权、运行地址、阻塞复核次数和未验证结论不代表最新状态。

用户指定本机隔离环境，范围为准备并验收、暂不上线。当前修订为 **snapshot1**，使用真实镜像及隔离依赖，运行配置为 development。

**已完成隔离源码提交、同提交镜像构建、真实知识链路与本机基础设施/恢复验收；完整业务验收尚未通过。** 模型质量和历史超时发现保留，本次没有新建模型任务、审批或生成工单。

## 当前环境

| 项目 | 配置 |
| --- | --- |
| Compose 项目 | `openvigil-candidate-20260927-rc1-snapshot1` |
| API 文档 | <http://127.0.0.1:52034/docs> |
| HTTPS API 文档 | <https://127.0.0.1:56281/docs> |
| 本地快照分支 | `codex/local-acceptance-20260927-rc1` |
| 完整 commit | `8443ac0ec3d5ffeae0dbc12abcbf32851f42b138` |
| 镜像标签 | `openvigil-local:openvigil-2026-09-27-rc.1-snapshot1` |
| Manifest digest | `sha256:dbd48d39fb24340827543e5ea5f17c2b1bddbc06fc7faf9b85df0b05ef7e24f4` |
| Config digest | `sha256:e5da915059cf5157fc2176e1a667548ad441a9c64307d47cba7bf17b5f759886` |
| 189 文件源码摘要 | `75130ec5a128f71cfd1aee2cae2dea2d60d167642520f0161333c9d41acf6533` |
| 证据目录 | `.artifacts/local-candidate/openvigil-2026-09-27-rc.1-snapshot1/` |

用户明确允许创建隔离本地快照。提交保存已测工作树的原始字节，未应用 Git 换行过滤，因此可能包含相对普通检出的换行差异；构建直接读取提交 blob。当前 main 分支与原索引未改变，私有配置、证书、依赖和测试输出未提交，没有推送。

九个容器为 API、TLS API、worker、relay、read-audit、PostgreSQL/TimescaleDB/pgvector、Redis、MinIO、Neo4j。五个应用容器使用同一镜像、非 root 与只读根文件系统，发布三元身份在实际容器配置及 Settings 中精确匹配。四个专用卷，端口仅绑定回环地址。

## HTTPS 与身份边界

项目 CA 为 `.artifacts/local-candidate/openvigil-2026-09-27-rc.1-snapshot1/tls/ca.pem`，证书到期 `2026-10-04T16:00:49+00:00`。未改系统或浏览器信任库；浏览器默认不信任该证书。显式 CA 下健康/就绪 200、无身份 catalog 401、有效本机身份 200；默认信任拒绝。重复 up 同时验证 HTTP/HTTPS，不替换服务或再次迁移。

```powershell
curl.exe --cacert "C:\Users\jy\Documents\GitHub\OpenVigil\.artifacts\local-candidate\openvigil-2026-09-27-rc.1-snapshot1\tls\ca.pem" https://127.0.0.1:56281/api/v1/readyz
```

当前仍为 development/static_tokens。产品仅在 production 输出发布响应头，development 不输出；Sites 委托登录和生产配置尚未提供，前端 production gateway 未验收。没有注入伪造身份、响应头或调整产品安全校验。

## 验证证据

- 构建 95658、镜像探针 40956 实际退出 0：入口、锁定依赖闭包、pip check、PG16 客户端以及只读真实 CARE A/22 的 53,036 行断点恢复/幂等重放通过。
- `qualification-binding.json`：271 后端测试输入与快照一致；本轮 3 个前端源文件及 393 个本地构建产物与原验证摘要匹配。复用已完成的 520 后端、201 Node、47 浏览器结果，未声称重跑全量；浏览器原测试使用合成 fixture。
- `infrastructure-report-2.json`：实际迁移 0028、四依赖、MinIO 往返、鉴权、metrics、异步读审计和八个基础容器通过；`tls-report.json` 与 `summary.json` 补充第九容器、TLS、完整 commit/release/image、源文件和原索引核对。
- 首次基础检查 51697 退出 1：本机验证脚本误要求 development 返回生产专用响应头。原脚本和 `infrastructure-report.json` 保留；按实际代码修正验证范围，不改产品。生产网关仍明确未验收。

后端 520 测试排除 28 项 external；全局行覆盖 76.50%、变更行 88.51%，预算通过。原 80437 中断无最终结果，历史失败报告保留。

## 当前镜像知识与恢复验收

固定序列 **28667 退出 0**，`knowledge-resilience-verification.json` 绑定五份证据报告和同一 commit/release/image：

- 两份明确合成维护文档经真实 API 签名上传到 MinIO；幂等接入，异步 worker 调用现有 `Qwen/Qwen3-Embedding-4B`，各 1536 维有限向量持久化至 PostgreSQL，投影至 Neo4j。联合检索返回正确首位文档与引用；事务内旧向量空间排除检查后回滚。
- Redis 中断时鉴权读取 503，恢复后 200；只操作本候选依赖。
- 九服务停止、重启、重复启动通过，四个原卷保留；两份文档的内容摘要、向量化状态及重启后真实检索保持正确。
- 最终 HTTPS readyz 200、九容器运行、189 文件未变。数据库只读核对：任务/决策/审批/工单均 0，知识文档 2。输入和本机身份为明确合成范围；未执行推理模型或业务审批，未将未知供应商费用算为零。

## 当前树工程业务回归

独立临时栈的现有业务 E2E **65349 退出 0、1/1**：真实依赖与异步 worker 完成浏览器审批、单一工单、五任务/现场证据及健康复核；数据库唯一性、八条现场读审计和五个 MinIO 对象哈希通过。675 源码/构建摘要未变，282 源文件匹配隔离提交；`.artifacts/improvements/business-final-tree/verification.json` 绑定报告。该运行使用主机源码、原冻结前端构建、合成身份/遥测和确定性模型，临时项目已清理；没有使用 snapshot1 后端镜像，因此仍不能替代当前镜像的真实模型闭环验收。

## 未通过项

当前总体目标状态为 **BLOCKED**：三轮复核确认模型质量/超时、未回答的模型比较选择、真实委托身份及其服务配置仍未解决。工程/知识/恢复检查已完成，无活跃测试；不重复调用未变模型或以合成身份替代真实验收。环境继续保留运行，等待明确输入或外部条件改变。

- 真实模型质量与超时：review1 原任务一次人工发起、最终六次执行超时，无决策、审批或工单。此前第三次 failed 为中间快照，已更正；未手动重试到通过。
- 固定六案例受控复核 5/6，质量与历史延迟门槛失败；16 请求候选提示词实验未采用。两次流式计时诊断约 38–40 秒完成不能证明稳定性。详见[模型诊断报告](../reports/reasoning-observability-2026-09-27.md)。当前模型、提示词、超时、重试保持原配置。
- snapshot1 的真实 embedding/知识摄入与恢复已通过；推理模型、浏览器上传和现场业务闭环尚未完成。旧镜像成功不能替代当前镜像的剩余验收。
- 真实 CARE 全量历史 95 事件证据保留，候选门槛 8 pass / 28 fail，不声明全部模型可发布。
- 正式发布的生产身份、EAM、OTLP、远程 CI、签名及受保护审批未验证，本次不执行上线。

## 生命周期

```powershell
$candidateRoot = 'C:\Users\jy\Documents\GitHub\OpenVigil'
$candidatePython = Join-Path $candidateRoot 'backend\.venv\Scripts\python.exe'
$candidateManager = Join-Path $candidateRoot '.artifacts\local-candidate\openvigil-2026-09-27-rc.1-snapshot1\manage_candidate.py'
& $candidatePython $candidateManager status
& $candidatePython $candidateManager up
& $candidatePython $candidateManager stop
```

stop 保留四个数据卷；不要使用 down -v。manager 的 verify 含真实模型请求，不是只读健康检查。候选私有 `.env.runtime` 含凭据，不要分享整个制品目录。

旧 audit1 已停止（53252 退出 0，零运行容器、四卷保留），其旧 runbook 为 `audit1/runbook-before-snapshot1.md`。review1 同样已停止并保留四卷及六次失败证据。未操作其他项目或原开发环境。
