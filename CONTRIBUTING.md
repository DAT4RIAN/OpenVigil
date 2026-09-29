# 贡献指南

欢迎为 OpenVigil 提交问题报告、文档、测试和代码改进。开始前请阅读 [README](./README.md)、[产品需求](./PRODUCT_REQUIREMENTS.md)、[UI/UX 规范](./UI_UX_SPEC.md) 和 [架构说明](./ARCHITECTURE.md)，了解业务闭环及 Demo / Production 的边界。使用 AI Agent 时，还须遵守 [AGENTS.md](./AGENTS.md)。

**疑似安全漏洞请按 [安全政策](./SECURITY.md) 报告，不要在公开 Issue 或 Pull Request 中发布漏洞细节、密钥或用户数据。**

## 1. 提交问题与讨论方案

普通缺陷、功能建议和文档问题可以通过 [GitHub Issues](https://github.com/DAT4RIAN/OpenVigil/issues) 提交。

- 缺陷报告：说明实际结果、预期结果、复现步骤、Git commit、运行模式、系统和依赖版本，并提供经过脱敏的错误或截图。
- 功能建议：说明业务场景、数据来源、权限边界和可验证的验收条件。
- 架构迁移、破坏性 API 变更和较大依赖调整：先讨论范围及兼容方案，再开始实现。

请将一个 PR 聚焦于一个完整问题，避免混入无关重命名、依赖升级或大面积格式化。

## 2. 准备开发环境

### 代码与 Web 依赖

使用 Node.js `>= 22.13.0` 和 `pnpm 11.21.0`；准确版本以 [package.json](./package.json) 为准。外部贡献者可先 Fork 仓库，再克隆自己的 Fork。

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil
corepack enable
pnpm install --frozen-lockfile
```

已有克隆可用 `git submodule update --init --recursive` 初始化固定版本的参考实现。从 `main` 建立目的明确的工作分支；AI Agent 创建的分支默认使用 `codex/` 前缀。修改前运行 `git status`，保留已有未提交工作。

Web 开发预览使用 `pnpm dev`；构建产物使用 `pnpm build` 后再运行 `pnpm start`。两者默认都是 Demo，不代表真实后端或模型已接通。

### Python 依赖

后端使用 Python `3.12.x` 和 uv。以下命令在 `backend/` 中执行，与后端 CI 的完整依赖安装方式一致：

```bash
cd backend
uv sync --frozen --all-extras --all-groups
```

在后端目录使用 `uv run` 执行命令，避免修改全局 Python 环境。详细入口和依赖定义见 [backend/pyproject.toml](./backend/pyproject.toml)。

### 配置与运行模式

普通手动启动的本地配置统一使用仓库根目录 `.env`，不要在 `backend/` 创建第二份配置。仅在文件不存在时，从 [.env.example](./.env.example) 创建，例如在仓库根目录的 PowerShell 中执行：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

| 运行方式           | 配置和验证边界                                                                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 默认 Web Demo      | 确定性演示和 UI 回归；不能作为真实 API、身份或模型验收。                                                                                                          |
| 手动 Python 后端   | 读取根 `.env`；生产连接、身份、模型与依赖必须分别配置并验证。                                                                                                     |
| Windows 隔离开发栈 | 根目录运行 `./scripts/Start-Local.ps1`、`Status-Local.ps1`、`Stop-Local.ps1`；专用配置在 `.artifacts/local-stack/`，不读取或覆盖用户 `.env`，使用确定性测试推理。 |

启动细节见 [README 的快速开始](./README.md#快速开始)。真实模型调用可能产生费用；在授权的账号和预算内运行，记录模型、案例、调用次数、失败与费用，勿把付费评测加入默认离线单元测试。

## 3. 实现要求

- 保持已有正确行为、API 和配置兼容性；有意破坏兼容时说明依据、迁移办法和影响。
- 修复真实根因，补充能够复现问题的测试。不要删除失败测试、弱化断言、静默吞错或用 fixture 回退制造成功。
- 前端覆盖 loading、empty、error、disabled、success、重复点击、网络失败和响应式行为；涉及联动时验证真实 API、状态和数据流。
- 后端检查输入、身份、RBAC、数据范围、事务、并发、幂等和异常；权限修复应包含拒绝访问与跨范围测试。
- 数据库结构变更提交 Alembic migration，检查现有数据、约束、索引、升级及恢复风险；只改 ORM 不算完成迁移。
- 优先使用现有依赖和标准库。新增依赖说明用途及许可证，并同步相应锁文件。Web 只维护 `pnpm-lock.yaml`，不要引入 `package-lock.json`。
- Python 依赖调整需同步 `uv.lock`；在 `backend/` 运行 `uv run python scripts/export_container_requirements.py` 更新生成的容器依赖，再用 `--check` 核对一致性。
- 修改样式入口或迁移声明后，用 `pnpm check:architecture --write` 更新生成的架构事实并审阅差异，再执行 `pnpm check:architecture`。
- 密钥、私钥、真实业务数据、本地日志、缓存和运行制品不进入提交。截图、trace 和评测报告在分享前同样需要脱敏。
- `docs/` 仅供本地使用，不上传或纳入提交。CI 配置保存在 `scripts/repository-artifact-policy.json`；公共文档引用本地资料时使用标明“本地文档”的路径，不添加依赖这些资料的仓库链接。

## 4. 按改动范围验证

先运行相关小范围检查，再执行受影响部分的回归。命令和结果必须对应当前改动；CI 门禁以 [.github/workflows/ci.yml](./.github/workflows/ci.yml) 为准，不固定或夸大测试数量。

### 文档

在仓库根目录执行格式检查，核对相对链接、命令路径和描述与代码是否一致：

```bash
pnpm exec prettier --check CONTRIBUTING.md SECURITY.md README.md
git diff --check
```

其他文档改动应将上述文件名替换为本次修改的文件。纯文档变更通常不需要启动完整依赖栈。

### Web

在仓库根目录执行：

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm check:architecture
pnpm check:repository-artifacts
pnpm test
```

`pnpm test` 包含生产构建、Bundle 预算及 Node 合同测试。CI 还通过 `pnpm test:coverage` 检查覆盖率预算；启动路径变更运行 `pnpm test:start-smoke`，UI 或交互变更运行相关 Playwright 用例，并在 PR 中提供实际页面截图和状态验证。

首次运行浏览器测试可用 `pnpm exec playwright install chromium` 安装运行时。`pnpm test:e2e` 与真实依赖的 `pnpm test:e2e:business` 有不同的环境和数据边界，详见 [README 的开发说明](./README.md#开发)。

### Python

在 `backend/` 中执行相关测试，例如 `uv run python -m pytest tests/test_configuration.py -q`；完整后端检查为：

```bash
uv run python -m pytest tests -q
uv run python -m ruff format --check src tests alembic scripts
uv run python -m ruff check src tests alembic scripts
uv run python -m mypy --no-incremental src
uv run python scripts/verify_migration_head.py
uv run alembic upgrade head --sql
```

安全或依赖相关改动还应执行 `uv run python -m bandit -q -r src`、`uv run python -m pip_audit --skip-editable`，以及根目录的 `pnpm audit --prod`。迁移变更必须进一步在隔离 PostgreSQL 上验证真实升级和约束，离线 SQL 或 SQLite 测试不能代替它。

外部资源不足、供应商失败、未执行或跳过的检查，应如实写为 `UNVERIFIED`、失败或未执行，并注明原因。外部验收环境设置 `WINDOPS_FAIL_ON_SKIPPED=1`，skip 即失败。不得将 Demo、确定性模型或测试替身的成功描述为生产验收。

## 5. Pull Request 检查清单

- 说明问题、改动原因、涉及范围和行为变化，关联 Issue（如有）。
- 提供复现及验证命令、实际结果、环境、剩余风险；区分本地验证、真实外部验证与尚未验证项。
- UI 变更提供脱敏截图；API、schema、权限或配置变更同步相关文档与测试。
- 检查 tracked、staged 和 unstaged 差异，确认没有混入密钥、未知文件或其他任务改动。
- 提交范围清晰、逻辑完整；建议使用 `fix:`、`feat:`、`docs:`、`test:` 等可读的提交前缀。
- 等待相关 CI 与审阅完成；不要为了绿色结果削弱质量或发布门禁。

生产发布有独立的审批、镜像和同版本证据要求，见 [发布工作流](./.github/workflows/release.yml)。合并 PR、本地通过或 Sites 发布成功都不等于生产发布资格。

## 6. 许可证与数据来源

提交贡献前确认有权提供这些内容，并使 OpenVigil 自有源码的贡献与 [Apache License 2.0](./LICENSE) 兼容。第三方代码、素材和数据必须注明来源、版本、许可证及变更，参见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。

CARE 数据及受其许可证约束的派生分发制品不由本仓库的 Apache License 覆盖。不要将外部原始数据、个人信息或客户数据加入仓库；数据许可和分发边界以 [README 的许可证说明](./README.md#许可证) 为准。
