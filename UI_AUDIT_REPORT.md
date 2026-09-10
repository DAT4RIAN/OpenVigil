# OpenVigil UI / UX Audit Report

本报告只记录用户可见、可操作、可理解层面的 UI/UX 问题。API、数据、后端和架构根因不在此重复建主 Issue；如存在已知技术根因，仅通过 `Related Technical Issue` 关联。

---

## 1. Metadata

| Field          | Value                                                                                                                                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Project        | OpenVigil (`wind-agent`)                                                                                                                                                                                      |
| Audit Scope    | UI / UX；22 个现有工作区；当前 Demo 页面；Production UI 分支；前端实现；UI/E2E 测试                                                                                                                           |
| Audit Date     | 2026-09-03                                                                                                                                                                                                    |
| Reviewer Role  | UI/UX Reviewer                                                                                                                                                                                                |
| Overall Result | **Audit baseline: Not Accepted. Remediation implementation (2026-09-04): 8 / 8 `DONE`; final project status: `ACCEPTED` after Full Recheck, Adversarial Review, Global Validation, and Final Audit `2 / 2`.** |

## 2. Audit Inputs And Method

完整审核了：

- `AGENTS.md`
- `PRODUCT_REQUIREMENTS.md`
- `UI_UX_SPEC.md`
- `docs/ui/reference/README.md`
- `docs/ui/reference/dashboard-desktop.png`
- 当前前端的 22 个路由（Demo 模式逐页浏览）
- App Shell、首页、Mission、工单、预测、模型治理、全局状态、数据表格和全局样式实现
- `tests/e2e/identity-and-mobile.spec.ts`
- `tests/e2e/real-cross-layer.spec.ts`
- `tests/frontend-p1-contract.test.mjs`
- `tests/rendered-html.test.mjs`
- Playwright 配置与当前唯一的 UI 截图基线

浏览器审核覆盖：

- Desktop：`1440 × 900`
- Tablet / Narrow Web 抽查：`900px` 宽
- Mobile：`390 × 844`，并抽查 44px 触控目标与页面整体高度
- Demo 模式 22 个路由的标题、导航状态、页面结构、文案、空态、错误态、禁用态和横向溢出

说明：reference image 只用于判断构图、层级、密度和工业运营语义，不作为像素级复制目标；本报告没有要求为了匹配图片而破坏产品逻辑、响应式或可访问性。

本次复验结果：`pnpm test:e2e` 构建成功，Playwright 为 **6 passed / 1 skipped**；`pnpm exec prettier --check UI_AUDIT_REPORT.md` 通过。测试通过不改变本报告结论，原因见 `UI-M-002`。

---

## 3. Issue Index

| ID       | Severity | Status | Page / Component           | Title                                                  | Related Technical Issue |
| -------- | -------- | ------ | -------------------------- | ------------------------------------------------------ | ----------------------- |
| UI-H-001 | High     | DONE   | `/` 运营指挥中心           | 首页没有形成 Incident-first 的首屏决策层级             | N/A                     |
| UI-H-002 | High     | DONE   | App Shell、Production 首页 | 全局“运行正常”与页面失败状态相互矛盾                   | TECH-H001               |
| UI-H-003 | High     | DONE   | Mission、工单、预测、首页  | Loading / Empty / Error 被合并为零值或“暂无数据”       | TECH-H001               |
| UI-H-004 | High     | DONE   | 多个核心工作区             | 未经产品验证的 RUL / 失效概率仍被展示成业务结论        | N/A                     |
| UI-H-005 | High     | DONE   | 全局设计系统               | 大量业务文本低于规范最小字号，信息密度建立在不可读之上 | N/A                     |
| UI-H-006 | High     | DONE   | App Shell、全站响应式      | Tablet 导航不收起且移动触控目标普遍小于 44px           | N/A                     |
| UI-M-001 | Medium   | DONE   | `/missions/:id`            | 详情页没有继承所属导航选中态                           | N/A                     |
| UI-M-002 | Medium   | DONE   | UI 验收测试                | 当前视觉与无障碍测试不足以证明 UI 规范已满足           | TECH-M003               |

---

## 4. Findings

### UI-H-001 — 首页没有形成 Incident-first 的首屏决策层级

**Page / Component:** `/`、Dashboard、Command Strip、KPI、Priority Queue  
**Related Requirement:** `PRD-001`、`PRD-002`、`UI-001`  
**Reference Image:** `docs/ui/reference/dashboard-desktop.png`  
**Related Technical Issue:** N/A

#### Problem

规范要求用户先看到最高风险事件和唯一的 Mission 入口，再看到 6 个关键 KPI、主趋势和右侧优先队列。当前 Demo 首页虽然有事件条，但其视觉权重较弱，随后展示 9 个 KPI；Production 首页甚至没有事件条。两种模式都没有形成 reference image 所表达的“风险 → 优先队列 → 趋势 → KPI → 辅助信息”决策顺序。

在 `1440 × 900` 下，`max-width: 1500px` 的断点把 9 个 KPI 排成 `4 + 4 + 1`，产生明显空洞并把主图表推到首屏以下；首页主体也不是规范要求的 `7 / 5` 主趋势与优先队列布局。

#### Evidence

- 浏览器：Demo 首页首屏为紧凑事件条 + 9 个 KPI；主趋势、告警、Mission、Agent 活动和天气继续纵向堆叠。
- 浏览器：`1440 × 900` 下关键趋势和处置队列无法在首屏共同建立判断上下文。
- Reference：目标图以 P1 事件为第一视觉层，6 个 KPI 单行，主趋势与优先队列并列，三块辅助信息位于下方。
- Production 实现只从指标区开始，没有事件条：`components/pages/dashboard-page.tsx:247`、`:308`、`:314`。
- Demo 事件条和指标区：`components/pages/dashboard-page.tsx:642`、`:687`。
- 9 列指标与 1500px 下 4 列断点：`app/globals.css:1852`、`:2325`。

#### User Impact

值班人员进入系统后需要先扫描大量同权重数据，才能判断“现在最重要的问题是什么、该进入哪个 Mission”。这削弱了指挥中心作为工作入口的作用，也使 reference image 的核心视觉意图没有落地。

#### Recommended Change

以事件处置为首屏主线统一 Demo 与 Production：保留一个明确的最高优先级事件区和一个主操作；严格收敛为规范定义的 6 个 KPI；将主趋势与优先队列构成稳定的 `7 / 5` 双栏；其他列表进入下一级视觉层。没有高优先级事件时展示明确的稳定态，而不是删除整个事件层。

#### Acceptance Criteria

- [ ] Demo 与 Production 都保留同构的事件决策区，只替换真实数据和可用操作。
- [ ] 首页只展示规范定义的 6 个核心 KPI，未知值使用 `—`，不补零。
- [ ] `1440 × 900` 下可同时识别最高风险事件、6 个 KPI、主趋势和优先队列。
- [ ] `1280 × 800` 下 KPI 为 `3 × 2`，没有 `4 + 4 + 1` 的孤立卡片或大块空洞。
- [ ] 无高优先级事件时有明确的“当前稳定”状态和更新时间。

#### Suggested Validation

- `1440 × 900`、`1280 × 800` 全页截图对比
- Demo / Production 同构检查
- 无事件、单一 P1、多条高优事件状态检查
- 键盘进入 Mission 的完整路径

---

### UI-H-002 — 全局“运行正常”与页面失败状态相互矛盾

**Page / Component:** App Shell、Top Bar、Production Dashboard  
**Related Requirement:** `G-004`、`PRD-001`、`PRD-006`、全局状态规范  
**Reference Image:** N/A  
**Related Technical Issue:** `TECH-H001`

#### Problem

Production Shell 固定显示绿色“生产运行模式”和绿色“持久事件账本”，侧栏也用绿色脉冲表达服务健康；这些状态没有随页面依赖或查询结果变化。与此同时，首页可以显示“生产快照不可用”，知识图谱等工作区也可展示服务未配置或失败。用户会同时看到“系统正常”和“当前核心数据不可用”。

Production 首页错误态只有失败提示，没有规范要求的关联 ID、可理解的影响范围和就地重试；失败提示下方仍继续显示零值 KPI 与空面板，使“真实为未知”看起来像“业务值为零”。

#### Evidence

- Shell 固定生产文案和成功色状态：`components/layout/app-shell.tsx:741`、`:773`、`:785`。
- Dashboard 查询失败只切换局部徽标与错误提示：`components/pages/dashboard-page.tsx:284`、`:308`。
- 错误提示后仍渲染指标区：`components/pages/dashboard-page.tsx:314`。
- 浏览器：当前 Demo 对未配置服务能给出显式说明，说明页面级错误语义已有基础；Production Shell 仍缺少与依赖健康一致的全局语义。

#### User Impact

运维产品的状态颜色承担信任语义。互相矛盾的绿色成功状态会让用户无法判断数据是否可信，也可能把后端不可用误读成“当前没有告警 / 数值为零”。

#### Recommended Change

把全局模式标签与运行健康拆开：模式标签只表达 Demo / Production，不使用“健康成功”语义；健康徽标必须来自同一份可解释的 readiness / freshness 状态。页面失败时明确展示受影响模块、最后成功更新时间、关联 ID 和重试入口，并阻止未知数据被渲染成零值。

#### Acceptance Criteria

- [ ] “Production”只表示运行模式，不隐含服务健康。
- [ ] Shell 与页面使用同一套 Ready / Degraded / Stale / Offline 语义且不会互相矛盾。
- [ ] Dashboard 全错误态包含关联 ID、影响范围、最后成功时间和重试操作。
- [ ] 失败或尚未返回的指标显示 `—` 或骨架，不显示伪零值。
- [ ] 部分失败能指出失败模块，健康模块继续显示并保留各自更新时间。

#### Suggested Validation

- 依赖 Ready / Degraded / Offline / Stale 状态矩阵
- Dashboard 503、网络断开、部分接口失败、恢复后刷新 E2E
- 状态色和读屏文本一致性检查

---

### UI-H-003 — Loading / Empty / Error 被合并为零值或“暂无数据”

**Page / Component:** `/missions`、`/work-orders`、`/predictive-maintenance`、Production `/`、全局 Loading  
**Related Requirement:** `PRD-001`、`PRD-002`、`PRD-003`、Product-Level State Requirements、`UI-004`、`UI-005`、`UI-006`  
**Reference Image:** N/A  
**Related Technical Issue:** `TECH-H001`

#### Problem

多个核心工作区直接把未返回或失败的查询折叠为 `[]`。因此首次加载、真实空数据、权限/网络错误会表现为同一个“暂无 Mission / 暂无工单”或零值统计。预测页在初始请求期间也会先显示“尚无成功的在线预测”，而不是加载状态。

全局 `loading.tsx` 虽有 `aria-busy`，但使用独立的假 Shell 和固定 8 个 KPI 骨架，与最终 App Shell 和各页面真实布局不一致，切换时会产生结构跳变。规范要求的 Refreshing、Filtered Empty、Partial Failure、Permission、Stale、Conflict、Long Running 和 Result Unknown 也没有形成可验证的统一组件体系。

#### Evidence

- Mission 将未返回数据直接变为空数组，并渲染“暂无 Mission”：`components/pages/mission-center-page.tsx:521`、`:548`、`:875`。
- 告警选择器同样使用空数组，加载与无告警无法区分：`components/pages/mission-center-page.tsx:526`、`:890`。
- 工单列表将未返回数据直接变为空数组：`components/pages/work-order-page.tsx:837`、`:859`。
- 预测页无选中结果时仅区分 query error 和“暂无成功结果”，未建立首屏加载态：`components/pages/predictive-maintenance-page.tsx:461`。
- 全局 Loading 使用独立 Shell 和固定指标骨架：`app/loading.tsx:5`、`:26`。
- Production Dashboard 的同类问题见 `UI-H-002`。
- 现有 E2E 对 401 / 403 / 503 / network error 有局部覆盖，但未覆盖这些核心工作区的状态区分。

#### User Impact

用户无法判断“真的没有任务”还是“数据还没回来 / 已失败”，刷新时也可能看到内容闪空。对 Mission 和工单这类核心闭环对象，这会直接影响是否继续等待、重试、上报或采取行动。

#### Recommended Change

建立共享且可组合的状态模型：保留上次成功内容用于 Refreshing；初始加载使用布局一致的骨架；Full Error、Partial Failure、Permission、Stale、Conflict 和 Result Unknown 使用不同文案、动作和颜色；只有成功响应且列表确实为空时才展示 Empty。

#### Acceptance Criteria

- [ ] Mission、工单、预测和首页都明确区分 Initial Loading、Refreshing、Empty、Filtered Empty、Full Error 和 Partial Failure。
- [ ] 权限、离线/过期、冲突、长任务和结果未知有符合规范的用户文案与下一步操作。
- [ ] Refreshing 保留上次成功内容，不闪成空列表。
- [ ] Empty 只能由成功且已知为空的数据触发。
- [ ] 全局骨架保留真实 App Shell，且与目标页面主要布局同构。

#### Suggested Validation

- 各工作区查询状态组件测试
- 延迟响应、失败后重试、刷新中断、过期数据 E2E
- 状态切换录像或截图序列
- `aria-live`、焦点落点和读屏文案检查

---

### UI-H-004 — 未经产品验证的 RUL / 失效概率仍被展示成业务结论

**Page / Component:** 首页、风机详情、健康、数字孪生、诊断、预测性维护、Agent、Mission、数据、报告、模型  
**Related Requirement:** `G-002`、`G-004`、`PRD-002`、`PRD-004`、`PRD-005`、`UI-002`、`UI-004`、`UI-006`  
**Reference Image:** N/A  
**Related Technical Issue:** N/A

#### Problem

PRD 明确不应把 CARE 尚未验证的 RUL、30 天失效概率等能力包装成真实结论，但当前 Demo 将这些数字广泛嵌入核心业务内容。部分页面有“演示公式 / 不能用于真实决策”的说明，然而首页活动流、任务上下文和资产卡片仍以“34%”“预计 RUL 47 天”等精确值展示，免责声明与结论不在同一阅读层级。

这不是“Demo 标签是否存在”的问题，而是用户在跨页面阅读时会反复遇到格式完整、来源具体、精度明确的业务结论，其视觉可信度高于边界提示。

#### Evidence

- 首页活动流：“30 日失效概率 34%，预计 RUL 47 天”：`lib/operations-data.ts:1613`。
- 风机详情展示预计 RUL、12 个子系统的失效概率和 RUL：`components/pages/turbine-detail-page.tsx:196`、`:281`、`:717`。
- 健康与数字孪生展示 30 天/30D 失效概率和 RUL：`components/pages/asset-health-page.tsx:349`、`components/pages/digital-twin-page.tsx:588`。
- 诊断证据以模型版本、区间和精确天数呈现：`lib/operations-data.ts:184`、`:189`。
- 预测性维护以“失效概率、剩余寿命”作为排序和风险判断依据：`components/pages/predictive-maintenance-page.tsx:477`、`:640`、`:809`。
- Agent 角色和任务把 RUL 估算当作运行能力：`lib/agent-data.ts:184`、`:187`。
- 模型数据虽有演示限制说明，但仍定义“30 天失效概率 / 剩余寿命天数”为输出：`lib/platform-admin-data.ts:538`、`:544`、`:554`。

#### User Impact

用户容易把精确数字误认为已验证的模型输出，并据此形成检修时机或风险判断。它也破坏了 Demo / Production 的诚实边界，使“可解释、可追溯、可否决”的产品目标变成对虚构精度的解释。

#### Recommended Change

在产品验证完成前，从主业务结论、风险排序、Mission 证据和首页活动中移除这些精确 RUL / 失效概率；改用已被证据支持的异常分数、健康评分、告警事实、趋势和“提前量（非 RUL）”。若必须保留研发演示，应隔离在明确的 Sandbox / 方法展示区，并在数字旁就地标注“合成示例，不参与业务决策”。

#### Acceptance Criteria

- [ ] 核心运维流程不再把 RUL 或 30 天失效概率作为真实风险事实或排序依据。
- [ ] Demo 中任何合成预测都与 Production 数据、Mission 证据和业务操作隔离。
- [ ] 边界说明与数值同屏、同组件、可被读屏读取，不能只放在页面远端免责声明。
- [ ] “提前量”文案明确为事件评分项，不与 RUL 混用。
- [ ] 全仓文案扫描与 22 路由浏览不再出现未标明边界的精确 RUL / 失效概率结论。

#### Suggested Validation

- 全仓术语扫描
- 22 路由逐页内容审核
- Demo / Production 内容边界测试
- 运维用户可用性访谈：让用户解释这些数字是否可用于真实决策

---

### UI-H-005 — 大量业务文本低于规范最小字号，信息密度建立在不可读之上

**Page / Component:** App Shell、状态徽标、KPI、表格、Mission、Agent、资源、模型等  
**Related Requirement:** `UI_UX_SPEC.md` 5.2、5.5、9、11；`G-005`  
**Reference Image:** `docs/ui/reference/dashboard-desktop.png`（密度与层级参考）  
**Related Technical Issue:** N/A

#### Problem

规范限定 Body / Table 为 13px、Secondary 为 12px、Metadata 最低 11px，关键业务信息不得低于 12px。当前全局样式中存在大量 7–10.5px 字号，涉及导航组名、状态徽标、KPI 标签、卡片元数据以及多个页面的业务数值，而不只是装饰性文字。

页面因此显得“内容很多”，但阅读依赖近距离辨认；状态、单位、时间和来源等本应建立可信度的元信息反而最难读。Mission 详情和模型管理在构图上已较成熟，但被过小字号削弱了层级和可扫描性。

#### Evidence

- 全局样式存在广泛的 `7px`、`8px`、`8.5px`、`9px` 和 `10px` 定义；例如导航标记 `app/globals.css:710`、`:823`，状态徽标 `:1280`、`:1289`，KPI 辅助信息 `:1396`、`:1428`。
- 资源、Agent、模型和数据密集页面继续使用 7–9px 的业务文本，例如 `app/globals.css:4784`、`:5182`、`:5425`、`:6885`。
- 浏览器：22 个路由都能观察到低于 11px 的可见文字；侧栏组名约 9px、多个 Badge 约 8px。
- Reference：目标图同样高密度，但风险、指标、队列标题和状态保持稳定可读，并通过留白和对比建立层级，而不是继续缩小字号。

#### User Impact

在值班大屏、普通笔记本、200% 缩放和视力差异场景下，用户更容易漏读状态、单位、更新时间和风险含义。过小字体也会导致缩放后布局突然崩塌，因为现有密度没有为正常字号预留空间。

#### Recommended Change

按语义层级重建字号，而不是逐个放大：业务主体和表格统一 13px；辅助说明 12px；仅时间、来源等元信息使用 11px；重要风险、数值和操作不低于 12px。通过信息裁剪、渐进披露、紧凑但足够的行高和更清晰的分组维持密度。

#### Acceptance Criteria

- [ ] 可见业务信息不低于 11px；关键业务信息和可操作标签不低于 12px。
- [ ] Body / Table / Secondary / Metadata 与规范字号和行高一致。
- [ ] 200% 缩放时无文字遮挡、截断或功能丢失。
- [ ] 状态、单位、时区、来源和更新时间无需放大即可辨认。
- [ ] 不通过省略必要信息来换取视觉整洁。

#### Suggested Validation

- CSS token / style lint
- `1440 × 900`、`1280 × 800`、`390 × 844` 人工可读性检查
- 浏览器 200% 缩放全页审核
- 对比度和字号自动检查 + 人工抽查

---

### UI-H-006 — Tablet 导航不收起且移动触控目标普遍小于 44px

**Page / Component:** App Shell、Sidebar、全局 Button / Icon Button、全站响应式  
**Related Requirement:** `UI_UX_SPEC.md` 10、11；`PRD-001`；`G-005`  
**Reference Image:** N/A  
**Related Technical Issue:** N/A

#### Problem

规范要求 `768–1023px` 使用覆盖式抽屉导航，内容单列；当前移动抽屉断点是 `860px`。在 `900px` 宽的真实页面中，218px 固定侧栏仍占据横向空间，主内容只剩约 667px，未达到规范所需的内容宽度。

移动端虽未发现 document 级横向溢出，但主要按钮、图标按钮和侧栏导航高度通常为 34–36px。对 `390px` 首页抽查时，48 个可见交互目标中有 38 个至少一个维度小于 44px；该问题在其他页面也重复出现。

#### Evidence

- 浏览器 `900px`：页面网格约为 `218px + 667px`，侧栏仍为 sticky，移动菜单入口未出现。
- 移动抽屉断点：`app/globals.css:7561`（`max-width: 860px`）。
- 中号按钮、导航项和图标按钮使用约 34–36px 高度：`app/globals.css:546`、`:793`。
- 浏览器 `390 × 844`：页面可重排但首页约 3919px 高，侧栏导航和顶部图标等大量目标小于 44px。
- 现有 E2E 只验证 P1 事件条在 320/360/390/430px 的几何与文字，没有验证全页触控目标和 tablet shell。

#### User Impact

平板和窄窗口用户得到的不是移动友好的单列工作区，而是被桌面侧栏压缩的内容。现场触控使用时，小目标增加误触概率；极长页面也让用户难以维持对象和任务上下文。

#### Recommended Change

按规范在 1023px 及以下切换覆盖式抽屉，并在 1024–1439px 使用可记忆的折叠侧栏。将移动端主要交互目标统一提升到至少 `44 × 44px`，通过分组、折叠和渐进披露降低长页面滚动，而不是缩小文字和控件。

#### Acceptance Criteria

- [ ] `768–1023px` 使用覆盖式抽屉，打开时有遮罩、焦点约束、Esc 关闭和返回焦点。
- [ ] `1024–1439px` 使用折叠侧栏并记住用户选择，主内容宽度不低于规范要求。
- [ ] `320–767px` 的主要按钮、图标按钮、导航和可点击行达到至少 `44 × 44px`。
- [ ] `390 × 844` 下没有页面级横向滚动，必要的宽表只在自身容器内滚动并有可发现提示。
- [ ] 200% 缩放和键盘操作不会造成焦点丢失或内容遮挡。

#### Suggested Validation

- 900px tablet shell E2E
- 1024 / 1280px 折叠侧栏 E2E
- 320 / 360 / 390 / 430px 全页触控目标检查
- 键盘、触屏和 200% 缩放检查

---

### UI-M-001 — Mission 详情页没有继承所属导航选中态

**Page / Component:** `/missions/:id`、Sidebar Navigation  
**Related Requirement:** `UI-004`、`UI_UX_SPEC.md` 4.1  
**Reference Image:** N/A  
**Related Technical Issue:** N/A

#### Problem

Mission 详情页打开后，“Mission 中心”导航不再保持选中。当前导航只做严格 URL 相等判断；详情路由因此失去所属工作区上下文。规范明确要求详情页继承列表项的导航选中态。

#### Evidence

- 浏览器：`/missions/MISSION-2026-0823` 有正确页面标题，但侧栏没有 active nav item。
- 实现只比较精确路径：`components/layout/app-shell.tsx:687`。

#### User Impact

用户从列表进入复杂详情页后，难以快速确认自己仍处于 Mission 工作区，也增加返回列表的理解成本。

#### Recommended Change

为分层路由建立 route ownership：`/missions/:id` 继承 `/missions`，`/turbines/:id` 继承资产工作区。详情页同时提供明确的返回列表或面包屑，不依赖浏览器后退。

#### Acceptance Criteria

- [ ] `/missions/:id` 始终选中“Mission 中心”。
- [ ] 详情页提供可访问的所属工作区返回路径。
- [ ] 键盘和读屏能识别当前导航项。
- [ ] 其他详情路由采用同一映射规则。

#### Suggested Validation

- 路由映射单元测试
- Mission 列表 → 详情 → 返回的键盘 E2E
- `aria-current="page"` 检查

---

### UI-M-002 — 当前视觉与无障碍测试不足以证明 UI 规范已满足

**Page / Component:** Playwright、截图基线、UI Acceptance  
**Related Requirement:** `G-005`、`UI_UX_SPEC.md` 11、12、13；Release Acceptance  
**Reference Image:** `docs/ui/reference/dashboard-desktop.png`  
**Related Technical Issue:** `TECH-M003`

#### Problem

当前 Playwright UI 规格包含 6 个主要测试，重点是鉴权、能力导航、服务错误、SSE 重连和 P1 事件条。唯一视觉基线只是 `390px` 下的事件条局部截图，不是首页或工作区全页。没有 `1280 × 800`、900px tablet、22 个工作区、全局状态族、整页 200% 缩放、自动无障碍、对比度、读屏和完整键盘路径的验证证据。

源码正则与服务端渲染测试能锁定数据契约，但不能证明视觉层级、文本可读性、焦点行为、触控目标或响应式重排正确。跨层测试还依赖外部环境并默认跳过。

#### Evidence

- UI E2E 测试定义位于 `tests/e2e/identity-and-mobile.spec.ts:38` 至 `:292`。
- 事件条只在 `320/360/390/430px` 验证，局部截图在 `:227`、`:291`。
- 200% 测试只临时放大事件条标题，不是浏览器整页 200% zoom：`:248`。
- 跨层测试默认 `test.skip`：`tests/e2e/real-cross-layer.spec.ts:8`。
- Playwright 默认 viewport 为桌面，但没有相应的全页视觉基线。

#### User Impact

当前测试可以通过，同时仍保留本报告发现的 1440px 首页断点、900px 侧栏、全站小字号和移动小触控目标。发布团队会得到错误的 UI 完成度信号。

#### Recommended Change

按 `UI_UX_SPEC.md` 建立小而有代表性的验收矩阵：首页和关键闭环页面在三个目标 viewport 的全页视觉回归；全局状态族的组件/E2E；自动 a11y 加人工键盘、读屏、200% 缩放；对所有 22 个路由做基础 smoke 与导航归属检查。

#### Acceptance Criteria

- [ ] 首页至少有 `1440 × 900`、`1280 × 800`、`390 × 844` 的全页视觉基线。
- [ ] 增加 900px tablet shell、44px 目标和页面级横向溢出检查。
- [ ] Mission / Decision / Work Order 核心闭环覆盖 Loading、Refreshing、Empty、Error、Disabled、Conflict、Result Unknown。
- [ ] 至少对关键路径执行自动 a11y、完整键盘、200% zoom 和 reduced-motion 验证。
- [ ] 22 个路由都验证唯一 H1、当前导航归属、无致命错误和无页面级横向溢出。

#### Suggested Validation

- Playwright screenshot projects
- axe / 等价自动无障碍扫描
- 人工 NVDA / 屏幕阅读器检查
- CI 保存失败截图、DOM 快照和 trace

---

## 5. Reference Image Comparison

| Dimension             | Reference Intent                                  | Current Result                                                | Assessment             |
| --------------------- | ------------------------------------------------- | ------------------------------------------------------------- | ---------------------- |
| Overall composition   | Incident-first、6 KPI、7/5 主区、三块下层辅助信息 | 事件条后有 9 KPI，主图与列表纵向扩展；Production 无事件条     | **Major gap**          |
| Visual hierarchy      | P1 事件和处置入口最强，队列次之，趋势与 KPI 支撑  | 大量卡片同权重，风险事件不稳定，关键内容被推到首屏下          | **Major gap**          |
| Information density   | 高密度但风险、状态、单位和表格仍可读              | 密度大量依赖 7–10px 字号                                      | **Major gap**          |
| Layout / spacing      | 紧凑、对齐稳定、首屏完成态势判断                  | 1440px KPI 出现 `4 + 4 + 1` 和空洞；页面偏长                  | **Major gap**          |
| Component proportions | 事件条、KPI、队列和图表比例服务决策顺序           | KPI 数量和卡片比例挤占主任务区域                              | **Moderate–major gap** |
| Color / tone          | 克制的工业运营语义，红/橙只表达风险               | 语义色体系基本存在；Light/Dark 双主题合理，不要求强制复制暗色 | **Partial match**      |
| Product logic         | 一个风险入口，事实与建议边界明确                  | 有明确 Demo 标识，但 RUL 合成结论跨核心流程扩散               | **Major gap**          |

结论：当前实现不需要像素级复制目标图，也不必强制默认暗色主题；需要继承的是目标图的风险优先构图、首屏决策效率、可读密度和状态可信度。

---

## 6. Cross-cutting UI Review

### Information Architecture

全局导航分组基本清晰，22 个工作区均可达，页面普遍有唯一 H1。主要问题是首页没有把“风险 → Mission”设为稳定首层，以及详情路由没有统一继承所属导航。

### Visual Hierarchy

多数页面已有卡片、表格、侧栏和主次列基础，Mission 详情的三列结构尤其接近成熟运维工作台。首页和跨页面字号体系仍使过多内容处于同一视觉权重。

### Layout & Spacing

组件间距总体一致，但 1500px 首页断点、900px 固定侧栏和长移动页破坏了关键 viewport 的效率。应先修正栅格和内容优先级，再做局部 polish。

### Typography

这是全站系统性问题。小字号不是少量 metadata 例外，而是大量业务标签、状态和数值的默认手段，详见 `UI-H-005`。

### Color & Consistency

语义 token、明暗主题和风险色基础较完整。主要缺陷不是色值本身，而是绿色成功状态与真实依赖状态脱节；同一颜色在此传达了错误的可信度。

### Components

`DataTable` 已具备搜索、筛选、排序、分页、CSV、键盘行激活和内部横向滚动，是良好的复用基础。Button、StatusBadge、MetricCard 和状态组件需要统一尺寸、字号与状态语义，避免每个页面独立实现。

### Interaction

表格、筛选和部分详情操作有明确反馈。当前 Demo 中 Mission / 工单创建被禁用且提供了原因，没有发现“看似成功但实际无作用”的活动按钮；但核心工作流的状态反馈仍受 `UI-H-002` 和 `UI-H-003` 影响。

### Loading / Empty / Error / Disabled

Disabled 的解释通常比 Loading / Empty / Error 完整。后者在多个核心页面被合并；Partial Failure、Stale、Conflict、Result Unknown 等规范状态尚未形成一致、可测试的表现。

### Forms

Production 工单证据表单有可见标签、必填标记、结构化测量和文件输入，基础较好。后续重点应验证字段错误、提交中、重复提交、冲突和提交结果未知，而不是增加更多字段。

### Tables / Data-heavy UI

表格能力较成熟，并使用自身容器处理宽内容。需要补齐单位、时区、来源、更新时间的可读字号，以及移动端“此处可横向滚动”的可发现性。

### Responsive

未发现 390px 下的 document 级全页横向溢出，但 tablet breakpoint 和触控目标明显不符合规范。移动端页面可以重排，却常以极长纵向堆叠换取“不溢出”。

### Accessibility

已有 `aria-live`、`aria-busy`、sr-only label、表格键盘激活和 reduced-motion 基础。阻塞项是过小字体/目标、tablet drawer、200% 全页 reflow、状态不能只靠颜色，以及缺少系统性自动与人工验证。

### Product Completion / Demo Feel

Demo / Production 标签明确，多数禁用操作有原因，没有发现用 mock 成功反馈冒充真实写入的行为。Demo 感主要来自精确的合成 RUL 结论、客户端固定日报、部分服务未配置和核心工作区状态被简化；其中 UI 主问题已收敛到 `UI-H-003`、`UI-H-004`，服务/API 根因不在本报告重复建 Issue。

---

## 7. Duplicate / Cross-report References

- 本报告没有为 API、数据库、权限执行、事件账本或部署根因重复创建主 Issue。
- 模型激活/回滚的 Production 技术链路已有 `AUDIT_REPORT.md` 的 `CARE-C005`；本报告不再创建同根因 UI Issue。若后续修复模型治理页面，应由该技术 Issue 提供真实状态，再按本报告的全局状态语义验收。
- RUL / 失效概率问题在本报告中的主根因是**用户理解与产品边界**，因此归入 `UI-H-004`；模型算法是否具备该能力仍由产品/技术报告治理。

---

## 8. Final Assessment

| Dimension           |    Score | Summary                                                          |
| ------------------- | -------: | ---------------------------------------------------------------- |
| Visual Quality      | 5.5 / 10 | 已有一致的卡片与数据工作台基础，但首页构图和字号体系未达标。     |
| Interaction Quality | 5.0 / 10 | 基本导航、筛选和表格可用；核心状态与恢复反馈不可信。             |
| Consistency         | 5.0 / 10 | 组件外观有复用，运行状态、字号和页面状态语义不一致。             |
| Completeness        | 4.0 / 10 | 22 个工作区已存在，但关键状态族和首屏决策闭环不完整。            |
| Responsive Quality  | 4.0 / 10 | Mobile 可重排，但 tablet shell、触控目标和长页面不符合规范。     |
| Accessibility       | 3.5 / 10 | 有语义基础，仍被字号、目标尺寸、zoom/reflow 和验证缺口阻塞。     |
| Reference Fidelity  | 4.0 / 10 | 继承了工业数据面板语汇，尚未继承 Incident-first 的核心视觉意图。 |

### Top Risks

1. 首页不能在首屏稳定回答“当前最高风险是什么、下一步进入哪个 Mission”。
2. Production 的绿色健康状态、失败提示、零值和空态互相矛盾，削弱用户对数据的信任。
3. 合成 RUL / 失效概率以精确业务结论呈现，可能误导真实运维判断。
4. 7–10px 字号、900px 固定侧栏和小触控目标使可访问性与现场使用不达标。
5. 当前测试通过不足以阻止上述问题回归。

### Recommended Remediation Order

1. 先修复 `UI-H-004` 的产品诚实边界，以及 `UI-H-002` / `UI-H-003` 的状态真实性。
2. 重构 `UI-H-001` 首页首屏信息架构。
3. 统一字号、触控尺寸和响应式断点（`UI-H-005`、`UI-H-006`）。
4. 修复导航归属并建立 UI 验收矩阵（`UI-M-001`、`UI-M-002`）。

在上述 High 问题关闭并通过目标 viewport、状态矩阵和可访问性验证前，不建议将 UI 标记为 release-ready。
