# AGENTS.md

# Project Agent Instructions

本文件定义本项目中所有 AI Agent 必须遵守的长期规则。

本文件优先用于约束：
- 工作目录
- 项目架构
- 修改边界
- 开发规范
- 测试规范
- Git 规范
- 安全规则
- 长任务行为

具体某一次开发任务不得写入本文件。
具体任务以对应的审核报告、任务文件或 Goal 文件为准。

---

# 1. Working Scope

默认工作范围仅限：

当前 Git 仓库及其子目录。

除非任务明确要求，否则禁止：

- 修改仓库外文件
- 修改其他项目
- 修改系统级配置
- 修改其他项目的数据库
- 操作其他项目的 Docker 容器
- 操作其他项目的进程
- 删除用户文件
- 修改全局 Git 配置
- 修改全局 Python / Node 环境
- 修改操作系统安全设置
- 执行不可逆系统操作

需要临时文件时，优先使用项目内部临时目录。

---

# 2. Source of Truth

开始工作前优先读取：

1. AGENTS.md
2. 当前任务文件
3. 当前审核报告
4. 当前执行状态文件
5. README / docs
6. 项目实际代码和配置

当文档与代码冲突：

- 先调查实际情况
- 不得盲目相信旧文档
- 不得静默忽略冲突
- 必要时同步更新文档

当任务要求与本文件冲突时：

安全限制和明确的禁止项优先。

---

# 3. Understand Before Editing

禁止在不了解上下文的情况下直接大规模修改。

修改前应根据任务需要理解：

- 项目目录结构
- 前后端入口
- 数据模型
- API 调用关系
- 状态管理
- 配置加载
- 数据库迁移
- 测试体系
- 构建和部署流程

对于复杂问题：

优先定位根因，而不是修补表面症状。

---

# 4. Minimal Necessary Change

默认原则：

> 在完整解决问题的前提下，选择最小且清晰的改动范围。

不要因为发现局部问题而无边界重写整个项目。

除非任务明确要求，不进行：

- 与当前任务无关的大规模架构迁移
- 无收益的大面积格式化
- 无关重命名
- 无关依赖升级
- 无关代码风格重构

但是，如果局部修改必然导致明显技术债或错误，可以进行必要的关联修改。

---

# 5. Code Quality

所有新增和修改代码应满足：

- 逻辑清晰
- 命名明确
- 控制复杂度
- 避免无意义抽象
- 避免重复实现
- 避免隐藏副作用
- 保持接口一致性
- 对异常路径有合理处理
- 对边界条件有合理处理

禁止使用“以后再修”的方式掩盖当前任务应解决的问题。

---

# 6. No Fake Completion

禁止通过以下方式制造“任务已完成”的假象：

- 删除失败测试
- skip 测试
- 弱化断言
- hardcode 返回值
- hardcode 测试数据以绕过问题
- catch 后静默吞掉异常
- 使用无意义 mock
- 注释掉失败代码
- 临时关闭类型检查
- 临时关闭 lint
- 临时绕过鉴权
- 将真实功能替换为 placeholder
- 用 TODO 代替应完成的实现

如果确实需要暂时保留兼容措施，必须明确说明原因。

---

# 7. Existing Behavior

修复和重构时默认保持现有正确行为。

修改前需要考虑：

- 是否破坏已有 API
- 是否破坏数据格式
- 是否破坏数据库兼容性
- 是否破坏已有 UI 行为
- 是否破坏 CLI / 配置接口
- 是否影响现有测试
- 是否影响部署

发生 intentional breaking change 时必须有明确任务依据。

---

# 8. Dependencies

新增依赖前先判断是否确有必要。

优先：

1. 使用现有依赖
2. 使用语言/框架标准能力
3. 最后才新增第三方依赖

新增依赖必须：

- 与项目技术栈兼容
- 有明确用途
- 不引入明显安全风险
- 不为一个极小功能引入巨大依赖

禁止为了绕过代码问题随意降级关键依赖。

---

# 9. Database Rules

涉及数据库时必须考虑：

- schema 兼容
- migration
- transaction
- constraint
- index
- nullability
- default value
- rollback 风险
- 并发
- 数据一致性

禁止：

- 无依据删除生产数据
- 随意 drop table
- 修改数据库结构但不处理 migration
- 仅修改 ORM 而不考虑真实数据库状态

危险数据操作必须格外谨慎。

---

# 10. Frontend Rules

前端修改至少考虑：

- loading
- empty state
- error state
- disabled state
- success state
- repeated click
- network failure
- stale state
- responsive behavior

涉及前后端联动时：

不得只确认 UI 出现。

必须确认真实 API / 状态 / 数据流已经接通。

---

# 11. Backend Rules

后端修改至少考虑：

- 输入校验
- 权限
- 异常
- transaction
- concurrency
- idempotency
- logging
- API compatibility

不能只覆盖 happy path。

---

# 12. Security

不得：

- 提交真实密码
- 提交 API Key
- 提交 Token
- 将 secret 写死在代码中
- 输出不必要的敏感信息
- 为方便测试永久关闭安全控制

如果发现已有 secret 泄漏风险，应记录并处理。

---

# 13. Validation Philosophy

“代码看起来正确”不等于完成。

修改后必须尽可能使用客观验证。

根据项目实际情况执行：

- build
- lint
- formatter check
- typecheck
- unit tests
- integration tests
- API tests
- E2E tests
- smoke tests
- application startup
- Docker build
- database migration validation

优先运行：

修改相关的小范围测试

然后再运行：

更大范围回归测试。

---

# 14. Testing Rules

修复 bug 时：

如果合理，应增加能够复现该 bug 的测试。

新增功能时：

如果项目已有测试体系，应补充对应测试。

测试必须验证真实行为，而不是单纯追求覆盖率数字。

---

# 15. Failed Validation

任何验证失败：

不得直接忽略。

首先判断失败属于：

A. 当前修改导致  
B. 项目原有问题  
C. 环境问题  
D. 外部依赖问题

对于 A：

必须修复。

对于 B：

如果和当前任务有关，应修复。
如果无关，应记录。

对于 C / D：

保存证据并说明。

禁止把真实代码失败轻易解释成“环境问题”。

---

# 16. Long-running Agent Rules

长任务不能只依赖聊天上下文保存状态。

必须优先依赖项目中的持久化文件。

如果存在：

- EXECUTION_GOAL.md
- AUDIT_REPORT.md
- EXECUTION_PROGRESS.md

则长任务期间应周期性重新读取。

尤其是在：

- 上下文压缩后
- 完成一个大阶段后
- 不确定当前进度时
- 准备宣布完成时

重新读取这些文件。

---

# 17. Progress Persistence

执行长任务时：

每完成一个独立任务项，应尽快更新：

`EXECUTION_PROGRESS.md`

不要等到全部工作完成后才一次性回忆并填写。

状态文件必须反映真实代码状态。

禁止：

先标记 DONE，再去实现。

正确顺序：

实现
→ 验证
→ DONE

---

# 18. Git Rules

修改前建议确认：

`git status`

不要假定仓库是 clean。

不得：

- 删除用户未提交代码
- 覆盖用户修改
- reset --hard 用户工作
- clean 掉未知文件
- force push
- 修改其他 branch 的工作

除非任务明确授权。

如果存在用户已有未提交修改：

必须保护它们。

---

# 19. Commit Rules

如果任务要求 commit：

每个 commit 应：

- 逻辑完整
- 范围清晰
- 不混入无关修改

不要提交：

- secret
- 临时日志
- 大型无关文件
- 本地缓存
- node_modules
- venv

---

# 20. Completion Philosophy

Agent 不得优化：

“最快宣布完成”。

Agent 应优化：

> 真实完成度 × 正确性 × 可维护性 × 验证可信度

如果仍然存在合理、具体、与任务有关的不确定性：

继续调查。

如果已经具备充分客观证据：

可以收敛。

不得为了延长任务而制造无意义工作。
