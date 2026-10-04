# EXECUTION_PROGRESS.md

# Long-running Execution Progress

## 本地开发栈部署：2026-10-04

- 用户授权：部署当前项目到本地。当前状态：`LOCAL_SERVICES_VALIDATED`，服务保持运行。
- 使用 `scripts/Start-Local.ps1` 重新构建当前工作树并启动保存的隔离项目 `openvigil-dev-e3beaa2d44`；启动及 `scripts/Status-Local.ps1` 均退出 0。工作台为 `http://127.0.0.1:3180/`，登录页为 `/login`，独立 Python API 文档为 `http://127.0.0.1:8180/docs`。
- 五个应用进程（frontend、API、Dramatiq、outbox relay、read-audit）归属核验通过，PostgreSQL、Redis、MinIO、Neo4j 四个依赖健康。当前迁移头、API 鉴权及未鉴权 401、五个 MinIO 桶、Neo4j 连接和新请求的读审计落库验证通过；登录页、API health 和 API 文档 HTTP 200。浏览器已从演示入口进入运营指挥中心，并保留工作台标签页。
- 本隔离栈前端为 `demo`，运行时明确返回 `productionReady=false`、`BACKEND_NOT_CONFIGURED`；独立 Python 为 `development / deterministic / static_tokens`。本次证明本地开发服务可用，不代表生产网关、真实模型或正式发布验收。
- 原四个开发数据卷、根 `.env` 和已有工作树改动保留，既有候选九服务继续运行。部署报告、状态输出和工作台截图位于忽略目录 `.artifacts/local-stack/` 的 `deployment-20261004.json`、`status-20261004.log`、`dashboard-20261004.jpg`；项目改进的 BLOCKED 和正式发布边界继续沿用下方记录。

## 仓库清理：2026-10-04

- 用户授权：按 `docs/reports/repository-clutter-audit-2026-10-04.md` 执行清理和归档。当前状态：DONE_LOCAL_VALIDATED（本地清理完成），操作明细及边界见本地 `docs/reports/repository-cleanup-result-2026-10-04.md`。
- 已完成缓存清理：26 个白名单路径、805,086,215 字节；PPT 工具目录的仓外 junction 仅移除链接，共享运行时保留。此前目录扫描计入了链接目标及重复遍历，实际按不遍历 reparse point 的清单计量。
- 已完成重复数据库处理：三份 Trivy 数据库 SHA-256 相同，保留三个原路径并共享一份 NTFS 硬链接数据，去除 2,915,106,816 字节重复占用；元数据、工具、镜像及扫描报告保持。
- 已完成素材归档：13 组路径、157 个文件已搬迁并逐文件核对大小及 SHA-256；旧登录图、架构图和 PPT 制作/参考资料在本地 `docs/history/repository-cleanup-2026-10-04/`，旧重构任务在 `history/refactor/REFACTOR_PROMPT.md`。
- 进度历史：[阅读版](history/execution/EXECUTION_PROGRESS-through-2026-10-03.md) 保留完整记录，仅将旧 Markdown 尾随双空格改为等价换行；[原始 ZIP](history/execution/EXECUTION_PROGRESS-through-2026-10-03.original.zip) 内的原文件保留 532,215 字节与原 SHA-256。根文件保留当前状态、近期独立完成记录和归档索引。
- 保留与验证：17,704 个受保护文件的大小及 SHA-256 均保持；当前候选九服务及六项 health、全部原容器身份/挂载/端口、Git 实际索引和 CARE 子模块未变。主依赖环境、环境配置、验收证据与 Docker 卷保留；旧构建 393 文件已封存，新构建产物保留供本地启动使用。
- 回归结果：前端定向测试 10/10、后端边界/CARE 供应链测试 8/8、Chromium 登录页测试 5/5，失败和跳过均为 0；生产构建、包体预算、TypeScript、架构及制品门禁通过。相关文档的本地链接及格式、归档 157 文件和原始 ZIP 复核通过。浏览器测试使用测试身份，不代表真实外部提供商或上线验收。
- 本项不改变七项改进 BLOCKED、整体未完成或暂不上线状态，不调用付费模型、不清理容器或卷、不提交或推送。

## README 韩语与意大利语版本：2026-10-03

- 用户授权：新增完整韩语、意大利语 README，沿用现有语言文件结构，并将全部八种语言的导航与相关校验同步更新。
- 当前状态：DONE（文档本地验证）。新增 `README-KO.md`、`README-IT.md` 完整译文，包含翻译后的图示与说明；保留原文的 29 个章节、16 个命令/配置代码块、技术标识符和外部来源 URL。原有六份 README 仅更新语言导航，全部八种语言均可互相切换。
- 防漂移：迁移声明校验及既有发布说明参数化测试已覆盖八份 README，保留测试数量来源、跳过不算发布通过、指定环境跳过即失败的说明。
- 已验证：八份 README 的 Prettier 检查、184 处本地链接/图片/章节锚点、技术内容一致性、唯一迁移头 `0028_read_audit_pipeline`、发布流程测试 46/46（失败/错误/跳过均为 0）、修改 Python 文件的 Ruff lint/格式及 `git diff --check` 均通过。测试报告位于忽略目录 `.artifacts/readme-add-ko-it-20261003.xml`。未运行应用构建、服务启动或现场/生产验收。
- 本项仅涉及文档及一致性校验，既有项目改进和生产/现场验收状态继续沿用原记录。

## README 多语言版本：2026-10-03

- 用户授权：为当前项目增加德语、西班牙语、法语、日语 README，沿用根目录独立语言文件并在六个版本之间提供导航。
- 当前状态：DONE（文档本地验证）。新增 `README-DE.md`、`README-ES.md`、`README-FR.md`、`README-JA.md` 完整译文；中英文原正文保持，六个版本顶部均可切换语言。四份译文保留原文的 29 个章节、16 个命令/配置代码块、技术标识符和外部来源 URL，图示及说明文字已翻译。
- 防漂移：`backend/scripts/verify_migration_head.py` 和既有 `backend/tests/test_release_pipeline.py` 参数化测试覆盖全部六份 README，保留测试数量、跳过不算发布通过、指定环境跳过即失败的说明。
- 已验证：六份 README 的 Prettier 检查、126 处本地链接/图片/章节锚点、技术内容一致性、当前唯一迁移头 `0028_read_audit_pipeline`、发布流程测试 44/44、修改 Python 文件的 Ruff lint/格式及 `git diff --check` 均通过。未运行应用构建、服务启动或现场/生产验收；本项仅修改文档与相关校验范围。
- 验收范围仅为文档及其一致性校验；既有项目改进、生产发布门禁及现场验收状态沿用下方原记录。

## 文档仅保留本地：2026-09-29

- 用户授权：从 GitHub 当前 `main` 版本撤下 `docs/`，保留本地目录与全部原文件；本项不重写历史提交。
- 已实施：取消 12 个文档文件的 Git 跟踪；整目录忽略且无放行规则。制品策略迁至 `scripts/repository-artifact-policy.json`，保留既有大小、缓存路径与来源门禁，增加禁止跟踪 `docs/`；格式命令不依赖本地文档目录。
- 引用处理：根目录中的 33 个本地文档链接改为明确标注的本地资料路径，保留原始报告内容、结论和未完成状态。
- 本地实现与验证：DONE。65 个本地文件的路径、字节数及 SHA-256 与操作前完全一致；不含 `docs/` 的干净导出通过 4 项链接/架构测试、架构检查、制品门禁及完整格式检查。隔离索引负向验证确认 CI 拒绝强制跟踪 `docs/`，未改变实际索引。
- Git 交付边界：本项使用独立提交正常推送 `main`，不重写历史；远端交付结果以推送后 Git 引用核对为准。

## 当前活动运行：2026-09-27 项目改进

- 2026-10-01 当前终态：目标已由工具正式更新为BLOCKED，整体未完成/Final Audit0/2，原七项不缩减。A1/A2及当前A3连续三回合no progress，同一阻塞条件未变：可支持的补丁镜像组件及当前同身份正式联合/真实现场证据缺失；本次blocked审核已验证三次分类/计数/条件和全部七项。实际rc16最终CLI再次退出1、清单/摘要/qualification缺失；rc14正式配置/活动部署0保持，本机九服务与CA验证API health/登录页200。285后端/229前端/393冻结产物、原制品与四卷/角色/八表/main/index/.env保持；官方稳定acl仍vulnerable，原候选0Critical/47High/8CVE及backports20候选零保留，本轮未重扫/查询索引或改代码/装包。前轮相关进程清单为空，本轮25499终态退出0，无待完成核查；没有新增测试、模型、业务写入、激活或上线，累计119/保守0.9274252元保持。缺口需要可用修复版本或正式/现场资源发生变化，重复确认不能代替证据；既有自动确认授权保留。主证据remaining-acceptance-audit-20261001-a3/{remaining-gate-audit-3,blocked-audit-ready,goal-status-update}.json；报告docs/reports/remaining-acceptance-audit-2026-10-01-a3.md。较早阶段见历史归档，不代表当前状态。

详细实施、失败和复核记录见上方完整历史归档；当前清理结果见本地 `docs/reports/repository-cleanup-result-2026-10-04.md`。
