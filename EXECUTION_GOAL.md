# OpenVigil 混塔风电运维智能体平台执行目标

开始日期：2026-10-05（北京时间）。当前用户 `/goal` 授权按照本地 `docs/design/hybrid-tower-operations-agent-technical-plan.md` 开发；参考源码在 `C:\coding\reference`，只读使用。用户确认先实现软件，试点资料后续提供。

## 执行范围

在现有双运行时、权威 PostgreSQL、MinIO、Outbox、LangGraph、权限、审批与工单主干上增量实现。第一版面向陆上混塔；公开样本或合成测试不算现场数据；塔筒模态不用于估算未标定索力。

1. P0：冻结软件契约、参考源码身份、验证计划及现场资料缺口。
2. P1：构件、索束、测点、波形制品与可重放输入；独立异步计算、质量/校准/同步门禁、pyOMA2 模态对照、直接预应力测量与环境基线。
3. P2：逐段/逐页知识证据、原文定位、图投影、EvidenceCard、结构 Mission、受控复核/审批/复测工单、健康复核与待审案例；前端真实数据流及状态。
4. P3：软件挑战集、同版本 API/浏览器/数据库/对象存储验证；真实试点与影子运行等待实际资料和现场责任人，明确 UNVERIFIED。
5. P4：OpenFAST/Kratos 与跨风场/视觉研究仅在输入、标定和收益具备时推进，不将所有参考仓库加入第一版依赖。

## 完成与验证

每个独立项先实现、验证，再更新 `EXECUTION_PROGRESS.md`。覆盖跨资产访问、错误单位、坏道、缺失、过期校准、方法失配、幂等、租约/恢复、失败与无数据。算法输出保存输入 SHA-256、算法/配置/校准版本、适用域与不确定性。同步 HTTP 不执行长计算；原安全/发布门禁保持。

临时制品在 `.artifacts/hybrid-tower-20261005/`。保护原工作树、根 `.env`、历史候选服务与数据；不自动提交、推送或上线。付费模型评测单独冻结有限范围后执行，不从软件授权推导无限调用预算。

## 既有项目改进的历史边界

此前七项改进目标全文封存至 [历史执行目标](history/execution/EXECUTION_GOAL-improvements-20260927.md)。其 BLOCKED、Final Audit 0/2、安全门禁失败、正式联合和真实现场 UNVERIFIED 保留，不被新软件开发覆盖；历史状态不阻止本次独立软件实现。


## 本次首版软件验收（2026-10-06）

FIRST_RELEASE_SOFTWARE_LOCAL_VERIFIED：本文件的 P0/P1/P2 软件及 P3 软件挑战完成，最终相关回归332/332、三个当前同源码真实服务场景、最终Linux双镜像及已安装执行源码核对通过。不可变总收据为 `.artifacts/hybrid-tower-20261005/p3-final-software-verification-receipt.json`，当前状态与证据见 `EXECUTION_PROGRESS.md` 及 `docs/reports/hybrid-tower-software-acceptance-2026-10-06.md`。

用户资料后续提供，因此现场影子运行、阈值/校准/领域精度与作业许可保持UNVERIFIED；正式签名/CVE/独立双镜像联合资格及既有历史发布阻断保留。P4、OCR/SSI与标定绝对索力按实际输入和收益推进。本次未提交、推送、发布或上线，未开展付费模型领域评测。
