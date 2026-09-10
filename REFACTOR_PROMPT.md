# OpenVigil 项目代码重构提示词

你是 OpenVigil 项目的代码重构负责人。请在当前仓库中完成一次以“结构清晰、职责明确、行为不变、可持续维护”为目标的系统性重构。

工作目录：

`C:\Users\jy\Documents\GitHub\OpenVigil`

## 一、核心目标

1. 梳理前端、Worker 网关、D1 Demo 数据层、Python 后端、CARE 基准子系统、部署和测试之间的真实边界。
2. 拆分职责过多、体积过大、依赖混乱的模块。
3. 统一重复实现、错误处理、类型、命名和目录组织。
4. 减少跨层耦合、循环依赖、隐式副作用和过宽 export barrel。
5. 保持现有功能、API、数据格式、权限、安全门禁和用户体验不变。
6. 删除代码前必须证明它没有运行时、测试、CLI、CI、迁移、文档或动态加载引用。
7. 不进行与可维护性无关的视觉改版、功能扩张或依赖升级。

## 二、开始前必须执行

完整读取并严格执行：

1. `AGENTS.md`
2. `PRODUCT_REQUIREMENTS.md`
3. `ARCHITECTURE.md`
4. `UI_UX_SPEC.md`
5. `AUDIT_REPORT.md`
6. `UI_AUDIT_REPORT.md`
7. `EXECUTION_GOAL.md`
8. `EXECUTION_PROGRESS.md`
9. `README.md`
10. `package.json`、`backend/pyproject.toml`、CI、部署配置及实际代码

先执行并记录：

- `git status --short --branch`
- 当前目录与模块清单
- 前端 TypeScript import graph
- Python import graph 和所有 CLI 入口
- API、Worker、数据库、迁移和测试之间的调用关系
- 大文件、大模块、重复工具函数和兼容代码清单
- 当前 build、typecheck、lint、unit test 基线

当前工作树可能包含用户尚未提交的清理改动。不得 reset、checkout、覆盖、丢弃或擅自提交这些改动。

在 `docs/refactor/` 下创建：

- `REFACTOR_PLAN.md`
- `REFACTOR_PROGRESS.md`

记录每个重构项的根因、涉及文件、风险、验证结果和状态。只能在实现并验证通过后标记 `DONE`。

## 三、必须保持的架构边界

1. Demo 与 Production 必须继续严格隔离。
2. Production 失败时不得回退到 fixture、D1、WT-023 固定数据或模拟事件。
3. Cloudflare Sites Worker 仍是前端托管和生产 API 网关，不得把 Python 后端伪装成 Sites 内置服务。
4. PostgreSQL 继续是生产权威数据源；Neo4j 只能作为可重建投影。
5. 业务写入、outbox、幂等、revision、lease 和 fencing 语义不得弱化。
6. 人工审批、RBAC、capability 和高风险操作门禁不得绕过。
7. 不得修改已发布 Drizzle/Alembic 迁移历史；结构变化必须新增 migration。
8. `windops_backend`、`WINDOPS_*`、`x-windops-*` 等兼容命名空间必须保留，除非有明确迁移方案和兼容期。
9. CARE 数据真值隔离、质量 mask、签名根、模型追溯和发布门禁不得简化。
10. 不得删除 `.gitmodules`。当前 CARE 参考目录的 gitlink/干净克隆可复现性需要单独核验，不能被本机 `tmp/external` 掩盖。

## 四、优先重构方向

### 前端

- 保持 `app/**/page.tsx` 和 API route 为薄入口。
- 将过大的 `components/pages/*.tsx` 拆成 feature 级容器、展示组件、hooks、类型和状态转换模块。
- 梳理 `lib/index.ts`，避免无关页面通过总 barrel 加载全部 Demo 数据。
- 按业务域整理 fixture、API adapter、query state、workflow overlay 和类型。
- 将超大的 `app/globals.css` 分离为 tokens、base、shell、shared components 和页面局部样式；不改变现有视觉验收基线。
- 保持 loading、refreshing、empty、filtered-empty、error、partial、stale、conflict 和 result-unknown 状态完整。
- 不因拆分组件破坏响应式、键盘操作、焦点管理和无障碍语义。

### Worker 与 D1

- 保持 Worker 安全头、生产代理边界、身份传播和路径 allowlist。
- 将路由解析、错误 envelope、鉴权和代理逻辑中的重复实现抽成小型共享模块。
- 保持 D1 Demo 初始化、CAS、幂等和审计语义。
- 兼容分支只有在证明已无数据或客户端依赖后才能退休。

### Python 后端

- 优先拆分超过约 800–1000 行且承担多类职责的模块。
- 按 api、service、domain、repository、contract、serialization、CLI orchestration 分离职责。
- 将 CARE 大模块按数据合同、I/O、质量、训练、预测、评分、制品验证和执行编排拆分。
- `models.py`、`schemas.py` 可按 bounded context 拆分，但必须保留稳定 re-export，避免一次性破坏所有 import。
- 合并多个 release/CARE 模块中重复的原子 JSON 写入、摘要校验和安全路径处理代码。
- 保持 FastAPI 路由、HTTP 状态码、错误结构、权限、事务和 CLI entry point 兼容。
- 不把真实功能替换成抽象接口、空壳 adapter 或无意义 mock。

## 五、执行方式

按小批次进行，每批只解决一个清晰问题：

```text
调查根因
→ 写重构计划
→ 增加或确认行为保护测试
→ 实施最小改动
→ 运行定向测试
→ 运行相关回归
→ 更新 REFACTOR_PROGRESS.md
→ 检查 diff
→ 再进入下一批
```

禁止一次性移动整个仓库、全局重命名或大面积格式化。目录移动与逻辑修改尽量分开，保证 diff 可审查。

## 六、禁止事项

不得通过以下方式制造重构完成：

- 删除、跳过或弱化失败测试
- catch 后静默吞错
- hardcode 返回值
- 用 TODO、stub、placeholder 替代现有功能
- 关闭 lint、类型检查、权限或安全门禁
- 把 Production 改为 Demo fallback
- 删除数据库迁移
- 为减少代码量合并不同业务语义
- 无依据删除兼容代码
- 修改全局 Git、Node、Python 或系统配置
- 擅自 commit、push 或操作其他项目

新增依赖前必须证明现有依赖和标准库无法合理实现。

## 七、验证要求

每批至少运行定向验证；阶段完成后运行：

### 前端

- `pnpm run build`
- `pnpm run check:bundle`
- `pnpm run typecheck`
- `pnpm run lint`
- `pnpm run format:check`
- `pnpm run test`
- 涉及 UI、路由或状态管理时运行 Playwright

### 后端

- `uv sync --frozen --all-extras --all-groups`
- `uv run pytest`
- Ruff
- strict mypy
- migration head 和 migration chain 验证
- 涉及事务、并发或 PostgreSQL 语义时运行真实 PostgreSQL 测试

### 仓库

- `pnpm run check:repository-artifacts`
- Markdown 本地链接检查
- 未使用依赖和孤儿模块检查
- `git diff --check`
- `git status --short --branch`

如果出现 `ERR_PNPM_IGNORED_BUILDS`，应在仓库级明确处理 `esbuild`、`sharp`、`workerd` 的构建许可，不能修改全局配置或绕过后宣称验证通过。

外部服务、容器、真实数据或凭据不可用时，必须将结果标记为 `UNVERIFIED`，并保存失败证据；不得把未运行、skip 或旧版本结果写成 `PASS`。

## 八、完成标准

只有满足以下条件才可以结束：

1. 所有计划中的重构项均已实现并验证。
2. 没有改变公开路由、API、错误结构、权限和数据语义。
3. 没有新增 Production fixture fallback。
4. 没有新增循环依赖、孤儿模块或重复基础设施。
5. 文档和实际同步实际目录结构。
6. 完整回归通过，或对无法执行的门禁明确标记 `UNVERIFIED`。
7. 完成一次全量复查和一次 adversarial review。
8. 连续两次最终审核没有发现新的 Critical/High 问题。
9. `REFACTOR_PROGRESS.md` 与真实 Git 状态一致。
10. 最终报告列出：
    - 重构前后的结构变化
    - 删除、拆分和保留内容
    - 兼容性处理
    - 验证命令及结果
    - 未验证范围和剩余风险

现在开始执行。不要先大规模修改；先完成基线调查、依赖图和分阶段重构计划。
