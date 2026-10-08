# 文档维护记录：八语言 README 同步（2026-10-08）

状态：**DONE_DOCUMENTATION_VERIFIED**。按当前 HEAD `11847e5`、代码/配置及最新软件验收核对英语、简体中文、德语、西班牙语、法语、日语、韩语、意大利语八份 README；本轮只更新 README 与此进度记录。

- 内容：统一陆上混塔阶段与本地软件/现场/正式发布边界；补齐六份译文缺失的混塔章节；新增独立 Docling PDF/中文 OCR、表格/页面来源、数值人工复核、异步状态/租约/三次尝试、原生 v1 重放兼容与权限重验说明；同步结构队列手动启动、托管启动的结构 worker、解析部署入口、工作区/API/架构/技术栈与新增文档镜像的发布资格要求。源码 AST 确认后端目录 18 工具，纠正旧译文的 11 工具；Demo 保持 16 工具。
- 验证：八语言 32 个二/三级章节、每份 17 个可执行命令/配置块、配置标识符及外部 URL 一致；208 处本地文件/图片/锚点与双向语言导航通过。八份 Prettier、架构事实、仓库制品策略、`git diff --check` 通过；发布流程文档契约测试 46/46、0失败/错误/跳过，唯一迁移头 `0032_structural_workflow` 通过。证据：`.artifacts/readme-update-20261008/documentation-validation.json`、`release-pipeline.xml`。
- 边界：本轮验证仅覆盖文档及相关契约，没有重跑应用构建、业务服务、OCR/模型或现场/正式发布验收；2026-10-07 解析和此前混塔验收保留各自源码快照，不把历史软件验证改写为生产资格。未提交、推送或发布；未修改业务代码、依赖、数据库、凭据、服务与历史收据。

---

# 当前活动任务：文档解析增量（2026-10-07）

**兼容性收尾 COMPLETE_LOCAL_SOFTWARE_VERIFIED（2026-10-07）**：保留原生v1请求哈希，省略/显式native都可用旧键重放；换parser拒绝旧键，原生/Docling均在读取收据或原件前复核当前权限，撤权不增加replay_count。专项13/13（包含在当前八模块80/80中，不重复相加）；208源码strict mypy、相关Ruff通过。最终实际服务20261007104442-70218e与Linuximage-20261007104429-756032重新验证当前源码，204安装源/结果SHA/对象/图/审计、cleanup与.env/index/HEAD/五个参考源SHA全部核对。最终收据：`.artifacts/document-parser-20261007/software-verification-receipt-v2.json`；下述v1收据保留为首轮快照。

状态：**COMPLETE_LOCAL_SOFTWARE_VERIFIED**。按原混塔技术方案在既有平台上补齐独立 PDF/OCR 软件链路。起点 HEAD `6c5721b`，工作树干净；未重做历史首版闭环或重构。任务：[本次实施任务](docs/design/document-parser-implementation-2026-10-07.md)；运行说明：[DOCUMENT_PARSER.md](backend/DOCUMENT_PARSER.md)；验收：[本次软件验收](docs/reports/document-parser-software-acceptance-2026-10-07.md)。

- D07-01：DONE_LOCAL_VERIFIED。已读取规则/目标/当前验收/技术方案/源码与本地 Docling 参考；当前知识段落/入库、结构子进程、结构工作流与真实 FDD 模态闭环五模块42项回归正常 exit0；收集数量与输出/进程退出对应，首轮未请求 JUnit，不冒充已有 XML。`d07-01-receipt.json` 保存范围/退出状态及 `.env`/index/HEAD 保护核对。
- D07-02：DONE_WINDOWS_LINUX_VERIFIED。通用CPU哈希锁/Windows87包、pip check、预取模型来源/许可证/commit与字节清单核对。七执行模块/12核心包在子进程实际观察；actual-runtime-v5.xml六项真实离线转换全通过：两页中文、正负数/单位、15段/9表格单元格、空白第一页及坏PDF/空白/加密/超尺寸/错模型拒绝。Linux当前镜像无网络/只读/UID10001探针通过，204已安装源码逐字节一致；主环境不安装OCR依赖。SQLite/内存对象接口夹具与实际服务分别说明；领域OCR精度UNVERIFIED。
- D07-03：DONE_LOCAL_SOFTWARE_VERIFIED。显式入口、独立actor/relay、租约恢复、三次尝试终态、原件前后重验、解析/段落/索引事件事务发布接通。十项声明协议状态挑战及真实服务终态通过；当前知识/权限/图/解析/哈希八模块77项、运行器/结果/隔离broker21项通过（不同轮次与重叠不累加）。待解析/失败正文不产生向量或#body引用；旧租约不能成功或失败写入。
- D07-04：DONE_LOCAL_SOFTWARE_VERIFIED。知识工作台接通真实状态/页码/区域、配置读取重试与数值复核提示；7项浏览器fixture全通过，236项前端单测、构建/包体/类型/ESLint/Prettier通过。未知响应冻结文件/文档ID/幂等键，503→403→202只一次PUT；真实服务最终保留三次上传授权超时，原键核验后取得真实200/202并完成索引。表格框明确table_region，不伪造精确单元格框。
- D07-05：DONE_CURRENT_SOURCE_LOCAL_VERIFIED。最终真实服务20261007102500-1a5b57的browser1/1、PG/Redis/MinIO/Neo4j/专用worker、两原件SHA、15段/9单元格/1536维向量、JSONB回读结果SHA、持久读审计、三次坏PDF失败及越权拒绝全部核对；最终Linuximage-20261007102459-8e6ac0通过。服务与镜像源码运行期间不变，自有服务/registry/volume/进程清理；208源码strict mypy、26文件Ruff lint/format与架构检查通过。总收据：`.artifacts/document-parser-20261007/software-verification-receipt.json`。
- 失败与修复：原始坐标/CPU索引/HOME/调用参数/浏览器定位与所有服务超时失败保留。Linux发现Windows锁未带平台条件、API site-packages污染独立NumPy、OpenCV缺实际动态库，分别由通用锁、-I显式包加载与专用镜像动态库修复，并重新验证。四旧文件仅统一混合换行，归一化字节与AST一致；最终服务/镜像在格式后的精确源码重跑。旧首版/重构/D07早轮收据保留为原快照，不冒充当前源码。
- 保护：原 `.env`、Git index/HEAD、历史收据与其他项目服务保持；独立临时依赖/模型/证据使用 `.artifacts/document-parser-20261007/`。不提交、推送、发布或上线。真实试点、领域精度和正式发布资格继续 UNVERIFIED。

---

# 历史活动任务：代码重构（2026-10-06）

状态：**COMPLETE_LOCAL_VERIFIED**。授权：用户要求重构当前项目，并选择按现状确定重点；基线 1183102af943fdb922d10eb1c07a344f9b940221，起点工作树干净。计划与完整记录：docs/refactor/REFACTOR_PLAN-2026-10-06.md、docs/refactor/REFACTOR_REPORT-2026-10-06.md；不可覆盖总收据：.artifacts/refactor-20261006/verification-receipt.json。

- R26-01 / R26-02：DONE_LOCAL_VERIFIED。Agent工具协议/目录/参数校验与五类处理器、共享辅助函数拆分，执行主文件1934→201行；旧导出同对象、序列/100条内存历史由一处维护。82/82原声明token等价，233前端单测、完整构建/包体、覆盖门槛（91.52%/51.56%/32.90%）、typecheck/ESLint/Prettier与63/63浏览器通过。
- R26-03：DONE_LOCAL_VERIFIED。图预算/SQL分页/构建/稳定序列化独立，主文件1361→866行；共享Outbox写入、推理schema、知识制品常量与窄配置Protocol解除三组旧SCC。52/52函数/类AST等价，无环/可达性/27 CLI、权限/图/审核/知识/事务/结构FDD及闭环回归完成；196源码strict mypy、Ruff、318 Python文件格式通过。
- R26-04：DONE_LOCAL_VERIFIED。结构页精确路径哈希和实际Docker/子进程/CI/验证入口补齐；架构/0032唯一迁移头一致。模拟browser上传origin配置修复，真实后端仍需显式配置；八语言README Demo工具数纠正为实际16。旧告警替身改用真实Alarm、WT-023后端18工具精确集合同步，原断言保留。
- 后端原始全量：913 passed / 2旧测试failed / 40外部门禁skipped；核心原始轮次787 passed / 相同2旧测试failed / 126 deselected。两轮在修正前已收集旧fixture。当前两个模块14/14复测通过，覆盖并解决这2项；去重915个非外部case有通过证据，不冒充一次零失败全量运行。所有原始XML/失败/trace保留，40外部条件保持UNVERIFIED。
- 失败修正证据：旧SimpleNamespace缺已有Alarm.code，create_mission函数AST与HEAD一致；HEAD已包含query_structural_context而旧断言仅17项，保留精确18项集合。CARE进程PATH复测3/3、模拟上传10/10与完整63/63通过。首轮构建/类型基线、漏页/SCC/可达性、重叠源码的失效模态轮次、PATH/旧fixture/旧目录及harness失败均保留。
- 保护与边界：513源/config最终快照一致；三处import格式、Dramatiq精确类型及两处旧缩进delta明确，后两者整文件AST一致，结构计算版本文件在最终回归期间保持。原.env/HEAD/index意图与历史进度后缀保留，无迁移、依赖升级、付费模型请求、提交、推送或上线。正式联合、镜像/安全发布和现场资格仍UNVERIFIED；以下首版验收属于其原源码快照。

---

# EXECUTION_PROGRESS.md

# Long-running Execution Progress

## 当前活动目标：混塔风电运维智能体平台（2026-10-05）

### 当前验收结论（2026-10-06）

状态：**FIRST_RELEASE_SOFTWARE_LOCAL_VERIFIED**。用户“先实现软件，试点资料后续提供”的首版软件范围已实现并验证；技术方案的现场影子运行、正式发布和条件性 P4 不在此软件结论中宣称通过。

- P0/P1：软件契约/11个参考身份、构件/索束/校准/原件/质量门禁、独立异步 pyOMA2 FDD、直接索力与环境基线完成。
- P2：原生段落与原文、工程证据/独立声明审核、结构 Mission、审批/复测/健康/案例、工作台实际 API 和受权图投影完成。
- P3 软件：当前同源码三场景（索力、30窗模态、范围/依赖故障/队列恢复）真实服务 browser 各1/1，分别2/2/32个队列结果、3/7/34个原件、9/17/18表与持久审计/Neo4j核对。207源码/构建SHA一致，每场声明fixture bundle独立，不冒充正式同镜像evidence_set。
- 最终回归：332/332、0失败/错误/跳过，正常exit0；架构/0032迁移头、12产品源和5harness源strict mypy、21文件Ruff/格式、新增结构Bandit通过，重叠测试不累加。
- 最终镜像：images-20261005192608-c43290 API/结构实际Linux构建/两探针通过；exact API父层、专用命令、线程限制核对。234构建源保持、两个已安装包各191源与当前代码逐字节一致；FDD0.5Hz/flat-line拒绝、非root/只读/无网络、完整131锁中130适用包及pip check通过。
- 真实缺陷修复：Neo4j投影交错读取有界版本/数量/逐行检查；新结构结果JSONB数值等价哈希，保持精度/类型与旧幂等规则；每次分析冻结声明部署及实际执行版本。所有旧失败/trace与不可变阶段收据保留。
- 总收据：[p3-final-software-verification-receipt.json](.artifacts/hybrid-tower-20261005/p3-final-software-verification-receipt.json)；可读记录：[软件验收](docs/reports/hybrid-tower-software-acceptance-2026-10-06.md)；当前语义：[软件契约](docs/design/hybrid-tower-software-contract.md)。
- 保护：原.env/HEAD/Git index、历史进度后缀保持；验证服务/registry/volume/进程已清理，保留本地镜像；无提交/推送/发布/上线或付费模型评测。
- **UNVERIFIED**：真实试点输入/校准/规程/阈值/独立测量/责任人、影子运行和领域精度；正式签名/CVE/独立双镜像联合资格及旧发布阻断保留。Docling/OCR/bbox、SSI/阻尼资格、标定绝对索力和OpenFAST/Kratos按实际前提另行推进。

### 阶段执行记录（以下为当时快照，当前状态以上述验收结论为准）



- P3 最终相关回归：CURRENT_SOURCE_REGRESSION_LOCAL_VERIFIED。provenance-final-regression-v1.xml 332/332、0fail/error/skip，测试进程正常exit0；结构/科学/结果哈希/基线/知识工程审核/图一致性/工作流/配置/API/旧发布/双镜像治理26模块。先前139/1失败与3/3专项保留，没有弱化断言。架构、0032唯一迁移头、12源码严格mypy、21文件Ruff/格式、Bandit/diff、README CN/EN格式通过。Linux最终源码双镜像v5构建中，整体Goal仍IN_PROGRESS；正式与field UNVERIFIED。
- P3 当前源码三场景：CURRENT_SOURCE_THREE_SERVICE_SCENARIOS_VERIFIED，整体IN_PROGRESS。scope 20261005185320-ba2fe6 / force 20261005185707-3f8d5d / modal 20261005190140-6d5db9均完整passed/cleanup/env/index=true，每场browser1/1，207源码/构建同一哈希快照。分别2/2/32个真实队列计算，全部算法/执行代码/声明部署与PG回读数值结果SHA核对；3/7/34个原件SHA，9/17/18表精确计数与实际持久读审计、Neo4j核对。modal真实256秒墙钟窗/30窗24train6holdout/健康/案例闭环通过，305审计、图126/196；force64审计图42/55、scope79审计图30/35。每场release/bundle是独立synthetic fixture，不冒充同一个正式evidence_set。收据p3-current-closures-verification-receipt.json不可覆盖。最终相关回归运行中，最后Linux当前镜像待执行；正式签名/CVE/独立联合与field UNVERIFIED。
- P3 当前版本索力闭环：CURRENT_PROVENANCE_FORCE_SERVICE_LOCAL_VERIFIED。20261005185707-3f8d5d完整passed/cleanup/env/index=true，browser1/1；实际FDD与flat-line共2结果的声明部署/执行代码/算法/PG回读新SHA核对，17表精确计数、7原件SHA、64读审计、Neo4j完整闭环/撤回排除验证。源码与scope v4同一快照，未更改算法/工单门禁。当前30窗modal验证进行中，广回归与Linux当前镜像待完成，Goal IN_PROGRESS，正式/field UNVERIFIED。
- P3 版本归属真实范围/恢复：RUN_ATTRIBUTION_SCOPE_REAL_SOFTWARE_VERIFIED，整体IN_PROGRESS。scope v4 20261005185320-ba2fe6完整passed/cleanup/env/index=true，浏览器1/1；2个真实队列FDD结果在PG回读后逐条部署声明/执行代码/库身份与新数值JSON结果SHA全部一致，3个MinIO原件SHA、9表精确计数、79持久读审计、Neo4j30/35以及越权/三依赖故障/停止重启恢复核对。207源码/构建SHA保持；收据p3-provenance-service-verification-receipt.json不可覆盖。前三次真实失败及cleanup保留，已修复投影交错读取和JSONB数字哈希差异；当前force/modal、更广回归与最后Linux镜像仍待验证。正式release/field保持UNVERIFIED。
- P3 每次分析版本归属：VERSION_BINDING_IN_PROGRESS。可信双digest/bundle与执行代码/哈希规则SHA冻结进分析身份，参与去重并核对；错版本零观察终态，legacy明确unbound/null。旧Python序列化结果SHA被真实PG JSONB规范化负零/数字写法改变，已实际复现并实现openvigil.structural-result-json.v1，仅新结构结果使用，保留精度/JSON类型并拒绝NaN/Inf；jsonb-20261005185158-b2ce6a真实PG/FDD回读PASS且自有服务清理。新30项、12源码strictmypy、21文件Ruff/格式/diff通过。首轮service v1/v2因真实Neo4j重建交错读悬空关系失败，通过before/after版本+数量+逐行版本与最多3次重读修复；7一致性/诊断测试与3并发专项通过。v3浏览器1/1故障/worker恢复PASS但SQL结果SHA校验失败，整体FAILED/cleanup/env/index=true，所有失败保留。旧广回归139pass/1barrier超时未忽略，待独立完整重跑；格式失败修复有AST一致证据。当前service v4重新验证全链路，最终Linux镜像/完整当前源码闭环仍待完成。整体IN_PROGRESS；正式联合/现场UNVERIFIED，无提交/推送/上线。

- P3 软件服务挑战首场景：FIRST_REAL_SERVICE_SCENARIO_LOCAL_VERIFIED，整体目标仍 IN_PROGRESS。第 10 次 `.artifacts/business-e2e/20261005154715-8e6f84` 浏览器 1/1、0 fail/error/skip，真实独立结构队列 FDD 与 flat-line 拒绝、TLS API/通用 worker/relay/读审计、实际上传/索力复测/独立审核/工单/案例/Neo4j 工作台/原件篡改拒绝和恢复/撤回清空已贯通。SQL 精确 17 表计数验证（1 completed Mission、1 completed order、2 tasks）；MinIO 7 原件 SHA 回读、2 analyses 的适配代码/数值版本及处理事件、66 条持久读审计、Neo4j 42 nodes / 55 relationships（1 复测测量与 1 闭环复核、撤回声明排除）核对。195 个源码/构建文件哈希运行期间不变，原 .env / index 未改、隔离服务已清理。第 1–9 次失败及各自 cleanup 证据保留；250 ms 审计接纳超时仍 503 无业务数据，严格有界恢复后要求真实终态，本次记录 1 次拒绝。实际图谱 GET 读取预算 15 s（后端证明 10 s）、水合前控件禁用及刷新期间旧结论清空修复，浏览器回归 2/2、前端 30 项、broker/隔离 4 项、构建/包体/类型/ESLint/mypy/Ruff 通过。收据 `p3-first-service-verification-receipt.json`。30-window 实际服务模态闭环、构件/测点/混合通道范围与服务故障恢复、结构镜像/多镜像发布仍待完成；合成信号/身份/release 和确定性推理不构成现场或正式发布资格，无提交/推送/上线。
- P3 实际服务模态场景：MODAL_REAL_SERVICE_SOFTWARE_LOCAL_VERIFIED（北京时间 2026-10-06），整体目标仍 IN_PROGRESS。第 2 次 .artifacts/business-e2e/20261005160439-030f0f 浏览器 1/1、0 fail/error/skip，真实 30-window 基线与 2 个独立分析窗（32 队列 FDD 全部 succeeded、attempts/event=1、适配/数值版本一致）通过。实际发布 24 train / 6 holdout 基线、漂移复核/独立审核/浏览器审批，先过早交接 422，再按未修改服务器墙钟等待完整 256 秒窗末；复测/独立健康审核/独立案例批准完成。精确 18 表 SQL（1 completed Mission/order、2 tasks、1 baseline）、34 MinIO 原件 SHA、实际审计和 Neo4j 基线验证/闭环投影核对。窗口 2026-10-05T16:09:55.688Z–16:14:11.688Z，维持损伤概率 null、未知不确定性、现场资格 unverified 与无作业授权。197 源码/构建哈希运行中不变；.env/index 未改、隔离服务已清理。第 1 次错误上传路由的失败/cleanup/trace 保留，网关门禁未扩大。类型/ESLint/Ruff/格式/严格 mypy 与 runner/broker 4/4 通过；收据 p3-modal-service-verification-receipt.json。首个索力场景收据保持历史快照；下一步授权粒度/服务故障及结构镜像/多镜像，旧正式发布与现场仍未验证。
- P3 结构镜像：LOCAL_IMAGES_AND_LINUX_FDD_VERIFIED（2026-10-06），整体 IN_PROGRESS。第三轮 images-20261005170745-ad9251 当前 API 与 exact API RepoDigest 派生结构镜像完成，实际 Linux/amd64 非 root UID/GID 10001、无网络/只读/tmpfs/全部 capability drop 数值探针 FDD 0.5 Hz、flat-line 拒绝、阻尼空值/不确定性未知/绝对索力 unavailable 通过。完整 131 个固定锁条目、Linux 适用的 130 包版本和 pip check 核对；pyOMA_2 1.4.3 / numpy 2.5.2 / scipy 1.18.1 与适配 SHA 一致，不包含 pytest，专用单进程单线程 structural-analysis 命令核对。全部构建源 SHA 运行中不变，.env/index 未改、自有 loopback registry/volume 清理通过。收据 p3-local-images-verification-receipt.json；两个失败构建/索引与哈希下载诊断保留。revision 明确 worktree-sha256 / local-only，未获取签名/CVE/独立多镜像或现场资格，没有提交/推送/上线。
- P3 实体范围与故障挑战：SCOPE_RECOVERY_REAL_SERVICE_SOFTWARE_LOCAL_VERIFIED，整体 IN_PROGRESS。第 6 次 20261005173840-ceafac 浏览器 1/1、0 fail/error/skip，实际构件/测点与混合原件 22 次越权拒绝、窄范围 SQL/API/UI/Neo4j 一致。暂停 MinIO 10.017 s / Neo4j 网关 15.033 s / Redis 审计 0.291 s 均 503 无业务数据，恢复后来源修订/声明身份不变；停止结构 worker 时 pending 与同键同 run 重放保持，重启后实际 FDD0.5Hz、attempts/event=1 与投影成功。9 表精确计数（2 components/3 sensors/3 records/2 runs/2 modal/1 Mission/1 claim+review/0 order）、3 原件 SHA 回读、81 持久读审计、Neo4j30/35核对。204 源码/构建哈希运行中不变，.env/index/cleanup=true，收据 p3-scope-recovery-service-verification-receipt.json。第1–5次失败/cleanup保留；v5 Windows Dramatiq CLI重启WinError6，v6本地测试用实际单进程单线程Worker API/生产actor，Linux镜像专用CLI不改。核心24/24、旧权限21/21、锁16/16、harness9/9、类型/ESLint/Ruff通过；新bootstrap上游无类型边界的严格类型检查待完成，多镜像治理待实现，不构成正式发布或现场验收。
- P3 双镜像发布软件：HYBRID_GOVERNANCE_LOCAL_VERIFIED，整体 IN_PROGRESS。exact API父层/UID/queue/完整锁/Linux FDD容器校验、双digest/bundle增量overlay、独立服务账号/配置/资源/网络和额外策略扩大访问拒绝已接通。CI保留完整11项API门禁，新增结构独立provenance/签名/CVE/SBOM/探针/双镜像清单和最后联合资格；受保护独立archive必须附同bundle结构报告，核对原件SHA/非跳过JUnit/时窗、fresh Cosign+SPDX内容身份。扩大102、完整治理165、新增43与安全delta35各自0fail/error/skip（重叠不累加）；8源码strictmypy、Ruff/格式、真实kubectl+策略CLI通过。CARE CI旧0030改读取当前0032常量，actual DB head比较保留，两轮失败留证。Bandit新assert改显式错误，受限pod /tmp精确说明，v2零finding；相关35项复测通过。第四轮images-20261005180427-230e80实际API/结构镜像与打包后Linux探针PASS，231源码构建期保持、两探针结果完全一致、.env/index/owned registry-volume cleanup=true；镜像是worktree未签名历史快照，之后仅deployment-policy安全helper修正有源差异，收据记录旧/新SHA，不伪称当前同镜像或正式资格。收据p3-hybrid-governance-verification-receipt.json。下一步每个AnalysisRun/result绑定声明部署与实际计算版本并复验，正式发布与现场仍UNVERIFIED，无提交/推送/上线。
- P2 结构图谱与声明保护：STRUCTURAL_GRAPH_LOCAL_VERIFIED，整体目标仍 IN_PROGRESS。增加构件/索束/测点、原始记录/分析/观察、基线、工程声明、初次及追加复测/独立健康复核的业务摘要与关系，不投影波形样本。声明独立标识为 reviewed_engineering_statement，保留修订/冻结 SHA/适用域/用途与 authorizesWork=false；待审/拒绝/撤回/过期/漂移均不可消费。图读取核对当前 SQL/来源权限、原件 SHA/MIME，并在对象 I/O 后以新身份映射重新读取当前声明与来源；共享原连接且不提交/回滚调用方事务。读取限时 10 秒，基础设施失败返回 503，不返回部分证明或沿用缓存；内部未验证读取不能消费声明。结构业务事件同事务生成图 Outbox，重放/回滚保护、现有顺序 fencing 与资源预算保留；重试耗尽也发布终态。
- P2 图谱验证：最新 graph-regression-v2.xml 49/49、legacy-policy-v2.xml 11/11、postgres-graph-v2.xml 4/4、graph-modal-closure-v1.xml 1/1、graph-browser-v1.xml 1/1、graph-frontend.xml 34/34，全部 0 fail/error/skip，重叠用例不累加。PostgreSQL 验证实际并发撤回/内容/测点变化与调用方事务保持；原件校验仍为内存实现，图存储仍为测试内存实现。模态用例实际 32 次 FDD，图中保留 30 窗基线/域/留出验证与复测关系。发现并修复旧 0007 迁移来源策略的分列/JSON 兼容问题，采用实际名称/类型/启用列补充缺项，保留并验证全部既有 JSON 约束；禁止以宽松默认策略绕过。初始失败日志/XML 保留且临时数据库凭据已脱敏。122 API/旧 95 签名、旧模型/外观契约、固定八节点与唯一迁移头 0032 保持；18 个源码严格 mypy、相关 Ruff/格式、前端类型/构建/包体/ESLint 与架构校验通过。收据为 p2-graph-verification-receipt.json；两个隔离 PostgreSQL 项目均已移除，浏览器进程已回收，无提交/推送/上线。实际 MinIO/Redis/Neo4j、同版本服务联合、结构镜像/多镜像发布安全和现场资格仍待验证。

- 用户授权：按照 `docs/design/hybrid-tower-operations-agent-technical-plan.md` 开发当前平台；用户确认先实现软件，试点资料后续提供。
- 状态：IN_PROGRESS。已读取全部 893 行技术方案、仓库规则、历史目标/审核与活动进度，核对主干代码及本地参考目录；本轮起点仅进度文件有未提交修改，原文件已封存至 `.artifacts/hybrid-tower-20261005/EXECUTION_PROGRESS.baseline.md`。
- P0 软件契约与参考身份：DONE_LOCAL_VERIFIED。`docs/design/hybrid-tower-software-contract.md` 明确已实现/待实现、质量/适用域/不确定性和现场边界；`backend/structural-reference-manifest.json` 冻结 11 个源码下载身份及所选文件 SHA-256。Git 元数据已删除，commit 仅引用此前收据；已安装 pyOMA_2 1.4.3 的 FDD 文件在统一换行后与本地参考一致。
- P1 首批后端：CORE_BACKEND_LOCAL_VERIFIED，整体目标仍 IN_PROGRESS。八个结构业务表、静态迁移 `0029_hybrid_tower_structural` 和 13 条增量 API 已接通权限/读审计/幂等/独立 Outbox 队列。实现原始波形与校准/同步/单位门禁、真实 pyOMA2 FDD、1P/3P 标识、直接 N/kN 测量及按测点/校准/来源分组的本页趋势、健康确认和环境 OLS 基线；保持未量化不确定性、无数据和失败状态，未实现或宣称 SSI/阻尼资格、频率法绝对索力或损伤概率。
- 计算与基线验证：`p1-final.xml` 55/55、0 fail/error/skip，包含真实 30 窗 FDD → 基线发布、UTC、谐波、过期/失配、恢复/fencing/重试耗尽、子进程超时/取消回收与数值回归。排队时保存适配代码 SHA-256 和固定数值库版本并参与去重；worker 版本失配保留 `StructuralAlgorithmVersionMismatch`，不提交观察。新增趋势及角色门禁另以 `prestress-final.xml`（5/5）和 `role-prestress.xml`（2/2）通过，重复用例不累加为唯一数量。
- 权限与兼容回归：`security-final.xml` 84/84、0 fail/error/skip，SAWarning 视为失败；修复实体权限在相关子查询内造成别名冗余笛卡尔积的问题，新增同资产不同构件的别名授权/拒绝验证。结构事件按独立 `structural` 域过滤，`structural-permissions-final.xml` 2/2；原有 95 条 API 签名保留。网关路径/HTTP 方法回归 24/24，TypeScript、修改前端文件 ESLint、12 个新增源码严格 mypy、对应 Ruff lint/格式、冻结依赖/唯一迁移头与架构校验通过。
- PostgreSQL 最新版本：`postgres-identity-final.xml` 4/4、0 fail/error/skip，覆盖空库/历史升级/ORM 对齐、组合外键跨资产拒绝、并发版本唯一性、降回 0028 后旧资产保留及重新升级。测试仅使用新建隔离项目，已停止并移除。最初版本失败 XML 和修正后的结果全部保留在 `.artifacts/hybrid-tower-20261005/`；2 次字段/错误类型失败属于本轮代码问题，未删测试或弱化断言。
- P2 原生段落证据后端：BACKEND_LOCAL_VERIFIED，整体 P2 仍 IN_PROGRESS。新增不可变 `KnowledgePassage`、静态迁移 `0030_knowledge_passages` 和三条权限/读审计保护的段落与源文件读取 API；TXT/Markdown 行号、PDF 实际页码、DOCX 段落/表格单元格、正文偏移和原文/段落哈希独立保存。逐段 embedding 接入现有受控批处理、pgvector 和业务图投影；历史正文保留且不虚构页码，旧 `#body` 链接兼容。修复知识实体授权大小写与全局实体过滤，并保护失去租约的 worker 成功和失败两条写入路径。Docling/OCR/bbox 未实现，扫描 PDF 明确拒绝无文本索引。
- P2 段落验证：最新 `passages-ui-contract.xml` 62/62、0 fail/error/skip，SAWarning 视为失败，覆盖新定位、SHA 漂移、跨租户/文档/实体读取、向量版本、坏文档、审计背压、fencing 和原有知识/图谱/外观契约；`postgres-passages-v2.xml` 5/5、0 fail/error/skip，包含原升级/ORM 对齐、真实 pgvector 段落权限检索、唯一约束、保留旧文档的降级/重新升级。隔离 PostgreSQL 测试项目已停止并移除；最初失败 XML/日志保留（旧链接兼容、测试 HTTP 状态和 nullable 索引时间契约已修正）。当前 111 条 API 中旧 95 条签名及 57 个旧业务模型源码哈希保持；TypeScript/ESLint、12 个相关源码严格 mypy、Ruff 与唯一迁移头通过。
- P2 原文界面：NATIVE_READER_FIXTURE_UI_LOCAL_VERIFIED。生产阅读抽屉通过真实段落 API 展示正文、原生位置、版本与哈希，获取校验后的短时源文件链接；未知页码保留空值。PDF 总页数由服务端解析覆盖客户端元数据；前端 37/37（含网关 26 项）和浏览器 `knowledge-browser.xml` 3/3、0 fail/error/skip，覆盖引用定位、打开原件、失败重试与 ordinal=0 分页。构建/包体/TypeScript/ESLint 通过，截图和 `p2-passages-verification-receipt.json` 已保存。浏览器使用明确的界面测试资料与传输 fixture，浏览器 → 实际 API/MinIO 联合链路仍 UNVERIFIED；没有将它计作现场或完整业务验收。
- P2 工程证据与结论后端：ENGINEERING_CLAIMS_CORE_BACKEND_LOCAL_VERIFIED。新增 `EngineeringClaim` / 独立审核历史、静态迁移 `0031_engineering_claims` 和三条增量 API；服务端从实际模态/分析、直接预应力、基线或知识原文生成 EvidenceCard，保存租户/风场/构件版本、窗口、原始哈希、方法/校准、单位、质量与不确定性。结论冻结支持/反证/缺失/适用域与期限，默认待审；作者不能自审，审核重新校验源字节，采用修订比较与数据库锁/原子条件，过期/内容或来源漂移不能用于推理。缺失或不可用数据只可供明确的复测建议审核，保留缺失项且不授权作业。
- P2 结论验证：最新 `claims-verified-v2.xml` 43/43、0 fail/error/skip（含知识/图谱/权限与旧外观契约回归），`postgres-claims-v2.xml` 6/6、0 fail/error/skip（实际 PostgreSQL 迁移/ORM/pgvector、两名并发审核人只落审一次、跨资产外键、审核修订唯一性、降级保留原文和 Mission）；后者源字节验证器为内存实现，不作为实际 MinIO 联合验收。当前 114 条 API 中旧 95 条签名和旧 57 模型哈希保留，模型外观导出的业务表共 68（不代表整个数据库表总数）；前端 38/38、构建/包体/类型/网关 ESLint、四个新增源码严格 mypy、对应 Ruff/格式/唯一迁移头通过。失败报告保留（测试任务未初始化、错误测试配置键、通道失败标签和直接制品字段契约已修正），未跳过或弱化断言。收据为 `p2-claims-verification-receipt.json`，两个隔离 PostgreSQL 项目均已停止并移除。
- P2 结构复测闭环后端：STRUCTURAL_WORKFLOW_CORE_BACKEND_LOCAL_VERIFIED，整体 P2 仍 IN_PROGRESS。静态迁移 `0032_structural_workflow` 新增四个侧表和八条 API；以实际模态/直接索力、可选已确认基线或责任人审核的规程范围冻结结构 Mission，继续复用固定八节点与受控模型/审批/资源门禁。结构来源不制造 SCADA 或默认健康分；未量化概率、费用/能量保持空值。确切工程结论必须独立审核并重新核验原始字节才可审批；失败审核不能被人工批准静默覆盖。陆上复测后保留待健康复核，独立责任人核对实际新增测量、作业后窗口、方法/校准/质量/适用域；异常结果保持未闭环，后续实测通过不可变侧表追加，原现场证据与复核历史保留。
- P2 健康复核与案例：实际复核关单同步更新工单、Mission 和告警，保留原风机健康分/状态及无恢复运行权限。新案例默认待审，独立案例审核前不进入 SQL 检索或图投影。目录 2026.10.1 共 18 工具（旧 17 保留），新增只读结构上下文；目录升级保留操作员停用和自定义治理发布。当前 122 API 的旧 95 签名、57 旧 ORM 模型源码与两个旧模板 SHA 保持；模型外观导出 72 个业务表，不代表全数据库；70 schema 导出项中 63 个模型，五个有依据的契约调整、其余 58 个 JSON schema 哈希冻结。
- P2 当前验证：`structural-workflow-regression-v12.xml` 39/ 39、`structural-legacy-regression-v5.xml` 30/30、`postgres-workflow-v3.xml` 7/7，全为 0 fail/error/skip；用例重叠不累加唯一数量。覆盖新来源/权限/冻结范围/撤权重放、实际复测及异常追加、审核责任人与案例门禁；隔离 PostgreSQL 覆盖迁移/ORM/pgvector、并发健康与案例审核只落审一次、跨资产外键、降级保留原工单/证据后重新升级。PostgreSQL 的源字节验证器为内存实现；所有该阶段隔离测试项目已停止并移除，原开发栈与候选保留。失败 XML/日志保留，已修复结论适用域类型、候选数量、不可变证据唯一约束处理和过时测试契约，没有 skip 或弱化断言。
- P2 结构审核界面：STRUCTURAL_REVIEW_FIXTURE_UI_LOCAL_VERIFIED。`/structural` 连接资产/拓扑/实际观测、冻结 Mission、逐条 EvidenceCards/原文定位、工程结论审核、独立健康复核和案例审核 API；生产 Mission 详情也接入。工单新增“待健康复核”，未知金额/置信度保留“未评估/未量化”。前端 `frontend-workflow-final.xml` 32/32，Chromium `structural-browser-v4.xml` 3/3，均 0 fail/error/skip；后者为明确的 UI 资料与传输 fixture，含错误重试、修订变化和窄屏布局。构建/包体/TypeScript/修改前端 ESLint/Prettier、八个相关源码严格 mypy、76 个修改 Python 的 Ruff lint/格式、唯一迁移头与架构校验通过；图片已检查。收据 `p2-workflow-verification-receipt.json` 保存哈希与验收边界。
- P2 追加复测操作：STRUCTURAL_FOLLOWUP_FIXTURE_UI_LOCAL_VERIFIED。专用表单读取实际已登记观测，按最新异常复核提交；短时 presign → 原文件 PUT → SHA-256 与 Mission 修订绑定的幂等提交，展示不可变追加历史。上传失败不执行交付，响应丢失/截断/成功响应字段不完整时保留原制品、观测、修订和幂等键，冻结切换机组/任务与健康复核直到核验；授权过期可更新尚未使用的上传授权。GET 工单响应增量返回 handoff 历史，跨资产读取仍拒绝；保留首次任务证据唯一约束。
- P2 模态完整软件闭环：MODAL_RETEST_SYNTHETIC_SOFTWARE_LOCAL_VERIFIED。实际数值进程计算 30 个独立健康窗与异常/复测两个窗口，共 32 个 FDD 记录；确认环境基线、原始异常复核、固定八节点、结论独立审核、受控审批、新窗口交付、独立健康复核、待审案例独立批准全部接通。显式测试时钟只推进采集窗口完成时间，未结束窗口仍被 422 拒绝；方法/校准/MAC/适用域门禁不修改。基线内容与风机原健康分/状态保持，损伤概率缺失且无恢复运行许可。合成信号及内存制品验证器不代表现场或实际 MinIO 验收。
- 本阶段证据：`retest-workflow-api-v2.xml` 9/9、`modal-closure-v1.xml` 1/1、`retest-compatibility.xml` 12/12、`retest-frontend-final.xml` 39/39、`structural-retest-browser-v4.xml` 4/4，全部 0 fail/error/skip，重叠不累加。最新构建/包体/TypeScript/修改前端 ESLint/Prettier、相关三个 Python Ruff lint/格式、增量 API 严格 mypy、唯一迁移头/架构校验通过。最初测试 SHA 期望错误改为独立 Node crypto 字节摘要校验；浏览器 CSP 失败通过既有显式上传来源白名单配置修正，测试未关闭 CSP；测试变量命名遮蔽 document 的类型错误已修正。失败 XML/trace 保留，窄屏图片检查通过。收据 `p2-retest-verification-receipt.json` 保存范围、报告与源码身份。
- P2 结构采集操作界面：STRUCTURAL_ACQUISITION_FIXTURE_UI_LOCAL_VERIFIED。生产工作台接通构件/索束/测点校准版本建档、原始波形及直接索力登记、独立后台分析和健康基线发布。原文件短时 presign → PUT → SHA-256 绑定登记，来源分类明确；微秒时间和原字节保留，可选环境值缺失不填零，已提供的真实零保留。分析展示真实排队/运行/失败、质量原因与模态 ID；基线要求 30–256 个独立引用、健康确认责任和所选环境特征，服务端既有 MAC/适用域/校准/留出验证门禁保持。
- P2 采集重放与分页：未知命令结果锁定原输入和资产范围，以同幂等键核验；不同输入不能生成新命令绕过未核验结果。机组/任务、三类拓扑、分析与索力各自提供首页/上页/下页；选择保留同机组已读取的实际 ID，换机组清空关联选择与采集草稿。角色按建档负责人/采集人员/工程复核人限制入口，后台权限继续作为权威。桌面两列表单及 390px 窄屏图片已检查。
- 采集阶段证据：`acquisition-frontend-final.xml` 48/48、`acquisition-browser-v3.xml` 10/10，0 fail/error/skip，重叠不累加。构建/包体/TypeScript/修改前端 ESLint/Prettier、架构/唯一迁移头及 diff 检查通过；没有新增 API/schema/migration 或修改算法门禁。初次 BigInt 字面量与编译目标冲突已改为标准构造；浏览器原生 option 的禁用断言改为直接检查 disabled 属性，首次格式失败已修正，失败报告保留。新收据 `p2-acquisition-verification-receipt.json` 保存当次源码身份；旧阶段收据为历史快照，不冒充当前哈希。
- P2 其余结构软件与 P3：IN_PROGRESS。结构图投影已本地验证；实际 Redis/MinIO/Neo4j 队列联合与同版本浏览器验收进行中。独立结构镜像冻结锁/构建文件及六进程管理已添加，实际镜像构建与多镜像发布治理待验证；后续交接为 `.artifacts/hybrid-tower-20261005/next-structural-software.md`。没有启动历史已停止栈，没有提交/推送/上线。
- 真实 SHM、混塔结构/索束参数、校准、健康基线、授权规程与现场负责人：后续提供，现场与工程资格 UNVERIFIED。研究仿真、自动损伤定位及跨风场泛化不计入第一版已实现能力。
- 旧七项改进目标全文封存至 `history/execution/EXECUTION_GOAL-improvements-20260927.md`；其 BLOCKED、正式/现场 UNVERIFIED、Final Audit 0/2 与暂不上线边界继续保留。

## 参考项目 Git 元数据删除：2026-10-05

- 用户范围：删除 `C:\coding\reference` 下的 `.git` 文件夹。
- 当前状态：DONE_GIT_METADATA_REMOVED。已删除 24 个 `.git` 目录，复查剩余 0 个；删除前核实目标绝对路径均位于授权目录内，未发现重解析点或该目录的活动 Git 进程。
- 保留验证：其余 59,858 个文件的路径、大小和修改时间均与删除前一致，源码目录无缺失；此前下载的参考项目现为普通源码目录。前后清单、删除目标及完成收据保存在 `.artifacts/reference-git-cleanup-20261005/`。

## 参考开源项目下载：2026-10-05

- 用户范围：列出混塔技术方案中提到的全部仓库和逐行 clone 命令，检查 `C:\coding\reference`，仅下载缺少项目的远端默认分支。
- 当前状态：DONE_REFERENCE_REPOSITORIES_VERIFIED。目标目录已存在，原有 7 个目录与 1 个 ZIP 保留；初次检查时方案中的 11 个仓库均缺少，现已全部补齐并验证。已逐一通过 `git ls-remote --symref <url> HEAD` 核实默认分支，9 个为 main，Kratos/OpenSees 为 master。
- 下载策略：`--depth 1 --single-branch --no-tags --branch <默认分支>`；只下载当前默认分支的浅历史，不初始化子模块、不执行项目安装或代码。
- 已完成并验证 11/11：EnergyFaultDetector、LangGraph、OpenFAST、LightRAG、GraphRAG、Ragas、OpenTelemetry Python、Docling、pyOMA2（main）和 Kratos、OpenSees（master）。本次新建 9 个浅克隆；检测到其他进程已开始下载 Docling/pyOMA2，待其结束后只读复用验证，保留两者默认分支完整历史，没有覆盖目录或历史。Docling 的重复 clone 被 Git 拒绝，随后通过既有目录验证解决，未删除或重建该目录。
- 验证：11 个 origin、默认分支、单分支 fetch 配置、无额外分支/标签、工作树零改动和 Git 对象连通性检查通过；9 个本次浅克隆均只含 1 个提交。来源仓库与 11 行命令一一对应；技术方案 SHA-256 未变，既有进度正文和原目录项目保留。逐项收据位于 `.artifacts/reference-clone-20261005/`，本项仅下载源代码。
- 命令、默认分支及目录初始清单保存在 `.artifacts/reference-clone-20261005/`；完成后核验 origin、当前分支、远端引用、shallow 状态与工作树完整性。

## 混塔运维智能体技术方案：2026-10-05

- 用户范围：了解当前平台现状，搜索 GitHub 项目和论文，借鉴写作智能体参考文档的方案结构，保存独立 Markdown 技术方案；不实施组件集成或恢复历史改进目标。
- 当前状态：DONE_DOCUMENT_VERIFIED（方案文档完成并验证，不表示建设实施或项目验收完成）。已核查当前源码、任务/审核/进度文件，并只读检查现有候选；9 容器运行，其中 TLS 代理因证书过期 unhealthy，底层 API health 200。开发栈 3180/8180 未监听；数据库为 1 篇已索引文档/201 字符、3 案例、6 Mission（3 completed）、3 工单（3 completed）。
- 输出：`docs/design/hybrid-tower-operations-agent-technical-plan.md`，包含 18 个主体章节、10 组核心 GitHub 项目选型及 12 篇论文依据；区分已有实现、新组件候选、研究对照、拟议数据/API、MVP、现场资源和验收门槛。现有 `/docs/` 本地保存策略保持。
- 文档验证：Prettier、33 处本地链接、UTF-8/20 组围栏及原有进度正文保留检查通过，27 个不同外部来源 URL 已列入文档；未进行全部链接的 HTTP 复测，未重跑历史软件或现场验收。收据为 `.artifacts/technical-plan-20261005/document-validation.json`。
- 核查快照与源码哈希保存在 `.artifacts/technical-plan-20261005/`；原有未提交进度内容已逐字节封存，不改写历史验收结果。本项不调用付费模型、不产生业务写入、不修复/启动服务、不提交或推送；七项改进 BLOCKED、正式验收 UNVERIFIED 和暂不上线边界保持。

## 停止本次本地开发栈：2026-10-04

- 用户授权：停止刚部署的本地服务。当前状态：`STOPPED`；`scripts/Stop-Local.ps1` 退出 0。
- 已按仓库路径、PID、创建时间和命令行核验并停止 frontend、API、Dramatiq、outbox relay、read-audit 及其子进程；五个原进程均已退出，管理状态清空。隔离项目 `openvigil-dev-e3beaa2d44` 的依赖容器均停止，3180、8180、25432、26379、29000、29001、27474、27687 八个端口已释放。
- 四个原开发数据卷及容器、凭据保留。既有候选九服务继续运行；本次停止范围为本轮启动的开发栈。验证报告和停止输出位于 `.artifacts/local-stack/stopped-20261004.json`、`stop-20261004.log`。

## 本地开发栈部署：2026-10-04

- 用户授权：部署当前项目到本地。部署完成时状态：`LOCAL_SERVICES_VALIDATED`；随后已按用户指令停止，当前状态见上方停止记录。
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
