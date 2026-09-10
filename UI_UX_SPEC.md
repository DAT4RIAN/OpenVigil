# OpenVigil UI / UX Specification

本文件定义 OpenVigil 界面与交互层面的 Source of Truth。它把 `PRODUCT_REQUIREMENTS.md` 的产品要求翻译为可实现、可验证的页面结构与交互规则。

Image2 图片只是视觉意图，不是像素级真值；当图片、现有实现与本文件冲突时，优先级为：

`PRODUCT_REQUIREMENTS.md` → `UI_UX_SPEC.md` → `docs/ui/reference/*` → 当前实现

## 1. 文档信息

| 字段                | 内容                                                                    |
| ------------------- | ----------------------------------------------------------------------- |
| Product             | OpenVigil Multi-Agent Platform                                          |
| Spec Version        | 1.0                                                                     |
| Status              | Selected direction / implementation specification                       |
| Owner               | Design                                                                  |
| Last Updated        | 2026-09-03                                                              |
| Product Baseline    | `PRODUCT_REQUIREMENTS.md` 1.0                                           |
| Primary Viewport    | Desktop `1440 × 900`                                                    |
| Supported Web Width | `320px` 及以上；正式浏览器版本以 PRD Open Question 6 的业务确认结果为准 |

## 2. 设计方向与原则

选定方向名称：**事件优先的运营指挥（Incident-first Operations）**。

选择理由：

1. 延续当前深色工业侧栏、低饱和中性色与青绿色主色，不要求重建现有设计系统。
2. 把最高优先级事件、数据新鲜度和受控下一步动作放在首屏最强层级，直接服务 Journey P-001。
3. 将详细的事实、模型输出、假设和反证留在 Mission / 诊断页面，避免首页承担过多诊断职责。
4. 使用现有 `AppShell`、`PageHeader`、`Card`、`MetricCard`、图表、表格、状态标记和进度组件即可实现。
5. 信息密度接近工业运行台，但不依赖微小字号、霓虹、高光或装饰性可视化制造“专业感”。

所有页面遵循以下产品特有原则：

- **先回答风险，再展示总量。** 首屏先说明“哪里需要处理、为什么、下一步是什么”，KPI 只提供上下文。
- **权威性可见。** 运行模式、数据来源、快照时间、新鲜度、覆盖率和陈旧状态必须可扫描。
- **证据与结论分离。** 事实、模型输出、假设、反证、人工结果使用明确标签，不用位置或颜色暗示它们等价。
- **状态与动作相邻。** 主操作必须紧邻被操作的对象、当前 revision 和门禁原因。
- **人是高风险动作的授权者。** AI 活动以公开事件、工具结果和摘要呈现；不显示隐藏 Chain-of-Thought，不出现“AI 自动批准”。
- **失败可恢复。** 空态、失败、陈旧、冲突和结果未知均给出下一步，不用空白、无限加载或 Demo 数据兜底。
- **高密度不牺牲可读性。** 通过网格、分组、对齐和渐进披露容纳信息；关键业务正文不小于 `12px`。
- **一致优于页面特效。** 优先复用组件和语义 token，不为匹配参考图复制另一套控件。

## 3. Reference Image 规则

### 3.1 已选参考图

| Asset                                     | Page         | Native Canvas | Target Viewport         | Role         |
| ----------------------------------------- | ------------ | ------------- | ----------------------- | ------------ |
| `docs/ui/reference/dashboard-desktop.png` | 运营指挥中心 | `1536 × 1024` | `1440 × 900` 及更宽桌面 | 主要视觉方向 |

该图用于指导：

- overall composition；
- layout 与栅格比例；
- visual hierarchy；
- spacing 与 component proportion；
- 信息密度；
- 深色工业 visual tone 与语义色用法。

该图不是以下内容的真值：

- 业务逻辑、字段、API、权限和状态机；
- 数据值、时间、资产 ID、角色、计数或文案；
- Loading / Empty / Error / Disabled 等完整状态；
- 响应式重排；
- 精确字号、颜色、像素、图表坐标或组件尺寸；
- visual regression baseline。

非首页页面可以引用同一图片作为 **App Shell、密度、间距、组件比例和视觉语气** 的系统级参考，但必须按本文件的页面规格组织内容，不能照搬首页面板。

## 4. 信息架构

### 4.1 全局导航

一级导航保留现有七组，不新增无 PRD 数据源或权限模型的入口：

1. 概览：运营指挥中心。
2. 资产与监测：风场、风机、实时监测、设备健康。
3. 智能运维：告警中心、智能诊断、预测性维护。
4. AI 运营：Agent 控制中心、Mission 中心、决策中心。
5. 运维执行：工单中心、维护计划、运维资源。
6. 知识与数据：知识库、数字孪生、故障知识图谱、数据中心、运维报告。
7. 系统：模型管理、系统设置。

导航规则：

- 当前页面必须具有唯一选中项；详情页沿用所属列表入口的选中语义。
- Production 只显示当前身份具有 `view.*` capability 的入口；直接访问仍由服务器授权。
- 侧栏顶部固定显示当前风场 / 资产范围；切换范围后刷新所有相关查询，不能保留旧范围数字。
- 全局搜索仅返回授权范围内对象；按资产、告警、Mission、工单分类呈现，不泄露越界对象。
- 面包屑用于详情页，至少包含列表入口与当前对象 ID；返回列表时保留安全可复用的筛选状态。
- “创建工单”不是全局捷径；只能从已批准 Mission 的受控入口进入。

### 4.2 22 个现有工作区与 PRD 映射

| 页面模式                   | Routes                                                               | Primary Requirement       | Reference Image                                                        |
| -------------------------- | -------------------------------------------------------------------- | ------------------------- | ---------------------------------------------------------------------- |
| UI-001 运营指挥中心        | `/`                                                                  | PRD-001、PRD-002          | `docs/ui/reference/dashboard-desktop.png`                              |
| UI-002 资产与监测上下文    | `/wind-farms`、`/turbines/:id`、`/scada`、`/health`、`/digital-twin` | PRD-001                   | `docs/ui/reference/dashboard-desktop.png`（系统级视觉参考）            |
| UI-003 告警处置            | `/alarms`                                                            | PRD-001、PRD-002          | `docs/ui/reference/dashboard-desktop.png`（队列与状态语义参考）        |
| UI-004 Mission、诊断与决策 | `/missions`、`/missions/:id`、`/diagnosis`、`/decisions`             | PRD-002、PRD-003、PRD-005 | `docs/ui/reference/dashboard-desktop.png`（Shell、密度与层级参考）     |
| UI-005 工单与执行准备      | `/work-orders`、`/maintenance`、`/resources`                         | PRD-003                   | `docs/ui/reference/dashboard-desktop.png`（Shell、卡片与队列参考）     |
| UI-006 CARE 与模型治理     | `/data`、`/models`、`/predictive-maintenance`                        | PRD-004、PRD-005、PRD-006 | `docs/ui/reference/dashboard-desktop.png`（Shell、表格与状态语义参考） |
| UI-007 支持与治理工作区    | `/agents`、`/knowledge`、`/knowledge-graph`、`/reports`、`/settings` | PRD-006                   | `docs/ui/reference/dashboard-desktop.png`（系统级视觉参考）            |

## 5. 设计系统

### 5.1 App Shell 与栅格

- 展开侧栏宽度 `250px`；桌面折叠后 `74px`；窄屏变为覆盖式 Drawer，不挤压正文。
- 顶栏高度 `58px`，保持单行；显示运行模式、连接 / 陈旧状态、快照时间、搜索、通知与当前身份。
- 桌面内容边距 `22px`；笔记本 `18px`；窄屏 `14px`。
- 页面区块主间距 `12px`，卡片内边距通常 `16–20px`，紧凑表格单元格纵向 `10–12px`。
- 标准桌面栅格为 12 列；仪表盘主区采用 `7 / 5`，详情页可采用 `3 / 5 / 4`，列表详情可采用 `7 / 5`。
- 页面不设置装饰性超宽空白；大屏内容可在 `1920px` 后限制阅读列宽，但运行台图表与表格可使用剩余宽度。

### 5.2 Typography

| Role          | Desktop                 | Mobile    | Rule                          |
| ------------- | ----------------------- | --------- | ----------------------------- |
| Page title    | `26px / 1.2`, 650–700   | `22px`    | 每页一个 `h1`                 |
| Section title | `14–16px`, 600–650      | `14px`    | 使用 `h2` / `h3` 语义层级     |
| KPI value     | `24–30px`, tabular nums | `22–26px` | 单位降一级，不与数值等粗      |
| Body / table  | `13px / 1.5`            | `13px`    | 关键业务正文不得更小          |
| Secondary     | `12px / 1.45`           | `12px`    | 可用于说明、时间与状态补充    |
| Metadata      | `11px`                  | `11px`    | 仅用于非关键辅助信息          |
| Identifier    | `12px` monospace        | `12px`    | 资产、Mission、revision、hash |

禁止使用小于 `11px` 的可见文字承载业务信息。图表轴标签在空间不足时优先减少刻度或允许查看数据表，不继续缩小字号。

### 5.3 Spacing、Radius 与 Elevation

- 基础 spacing scale：`4, 8, 12, 16, 20, 24, 32px`。
- 控件间最小间距 `8px`；语义组内 `8–12px`；组间 `16–24px`。
- Radius：按钮 / 输入 `6px`，卡片 `9px`，重点容器最大 `12px`；不使用大面积胶囊卡片。
- 默认卡片使用 `1px` 边框和 `shadow-sm`；Drawer / Dialog 才使用 `shadow-md`。
- 不使用玻璃拟态、霓虹描边、发光阴影、3D 透视或与信息无关的渐变。

### 5.4 Color Tokens

沿用当前 token，不在页面内硬编码第二套语义色：

| Meaning     | Light     | Dark      | Usage                      |
| ----------- | --------- | --------- | -------------------------- |
| Background  | `#f5f7f8` | `#10181c` | 页面画布                   |
| Surface     | `#ffffff` | `#172126` | 卡片 / 表格                |
| Primary     | `#176b75` | `#54a9ab` | 主操作、当前选中、关键链接 |
| Success     | `#138568` | `#45b894` | 已验证、完成、健康         |
| Warning     | `#b8790b` | `#e1a53e` | 待审、陈旧、注意           |
| Critical    | `#c84545` | `#eb7373` | P1、失败、阻断             |
| Info        | `#3978b9` | `#6aa6e3` | 模型输出、信息状态         |
| Maintenance | `#795ca7` | `#aa88dc` | 维护 / 计划语义            |

规则：

- 状态必须同时有文字或图标标签，不只依赖颜色。
- Critical 只用于错误、P1/P2 风险和不可继续的门禁，不用于普通强调。
- Primary 每个可视区域最多承担一个主操作；次操作使用 secondary / ghost。
- 图表同一语义跨页面保持同色；真实值、预测值、阈值、异常、数据缺口必须有可区分线型或纹理。

### 5.5 组件与复用规则

#### Button

- 使用现有 `Button` 的 primary、secondary、ghost、danger 与 sm / md / icon 变体。
- 主按钮动词明确，包含对象或结果，例如“进入 Mission”“提交审批”“排程工单”。
- 提交中显示进行状态并禁用重复点击；结果未知时不立即恢复成可再次新建的状态。
- 破坏性或高风险操作必须使用确认 Dialog；不能只靠红色区分。

#### Input / Form

- 可见 label 不得由 placeholder 代替；必填、单位、格式和帮助信息靠近字段。
- 校验错误与字段关联，错误后保留输入和选择。
- revision、idempotency key、actor 等服务器字段不作为可编辑输入。
- 表单宽度遵循内容，不把短 ID、日期或枚举拉满整页。

#### Card / MetricCard

- Card 表达一个有标题的语义组，不把每个单值都拆成卡片。
- KPI 首屏最多六项，按业务结果优先；不同时展示健康度、风险、RUL、异常分数的混合标签。
- 卡片标题、刷新状态和局部错误位于同一 header；局部重试不刷新整页。

#### StatusBadge / Progress

- Badge 文案使用业务语言，例如“待人工审批”“数据陈旧”，避免只显示内部枚举。
- Progress 只表达可计算的过程；未知进度使用阶段、心跳和已耗时，不伪造百分比。
- 健康、异常强度、发布门槛和任务进度不得共用同一视觉控件而不写标签。

#### DataTable / List

- 复用现有 `DataTable` 的搜索、筛选、排序、分页、列显示、选择与 CSV 导出。
- 首列固定对象身份，右侧固定状态 / 行操作；重要列在窄屏优先保留。
- 行可点击时支持 `Enter` / `Space`，行内按钮不得触发行跳转。
- 批量操作仅在业务允许且具备权限时出现；禁用时说明原因。

#### Chart

- 图表标题注明指标、单位、时间范围、时区、来源与最后更新时间。
- Tooltip 键盘可达或提供等价数据表；异常、AI 事件、阈值和缺口使用不同形状 / 线型。
- 图表无数据是 Empty，不是零值；数据陈旧保留最后曲线并叠加明确状态。

#### Drawer / Dialog

- 列表详情优先使用右侧 Drawer；需要比较多列或执行复杂任务时进入独立详情页。
- Drawer 宽度桌面 `420–520px`；窄屏占满宽度；打开后焦点进入，关闭后返回触发点。
- Dialog 只用于需要阻断背景交互的确认 / 表单；必须有标题、对象、后果、主次操作与显式关闭。

#### Banner / Inline State

- 全局运行模式、整页失败和离线使用页面级 Banner。
- 单面板失败、权限不足或空态在原位置显示，不抹去其他成功区域。
- Success 只有在权威服务器确认后出现，并携带新 revision / 状态或可追踪 ID。

## 6. 关键页面规格

### UI-001 — 运营指挥中心

**Routes:** `/`  
**Related Requirements:** PRD-001、PRD-002  
**Primary Reference:** `docs/ui/reference/dashboard-desktop.png`

#### User Goal

值班人员在一个视口内判断数据是否可信、当前最高风险、哪些对象待处理，并进入正确的告警、资产或 Mission 上下文。

#### Layout

- Header：页面名、风场和资产数；右侧最多两个操作“运行日历”“生成报告”。
- Command strip：首屏第一内容块。包含严重度、事件标题、关联资产 / 告警、公开 AI 状态、健康值、异常强度、数据新鲜度与唯一主按钮“进入 Mission”。
- KPI：六列；`当前功率`、`24h 电量`、`运行机组`、`平均健康度`、`活跃告警`、`活跃 Missions`。总装机容量、离线 / 故障细分进入状态分布或 tooltip，不增加同级卡片。
- Main：12 列 `7 / 5`。左侧 SCADA 24H 主趋势；右侧优先处置队列。
- Lower：`4 / 4 / 4` 展示活跃 Mission、Agent 公开活动、海上作业窗口。
- 内容宽度不足时按“事件 → 队列 → 趋势 → Missions → Agent → 作业窗口”顺序纵向排列。

#### Visual Hierarchy

1. P1 / P2 事件与“进入 Mission”。
2. 优先处置队列及其负责人、持续时间、就绪度。
3. 数据新鲜度、覆盖率和 SCADA 异常上下文。
4. 运行结果 KPI。
5. Agent 活动和天气 / 资源背景。

#### Components and Reuse

- `AppShell`、`PageHeader`、`Card`、`CardHeader`、`MetricCard`、`StatusBadge`、`Progress`、`TimeSeriesChart`。
- 优先队列使用紧凑列表或 `DataTable`，不新增首页专用表格基础组件。
- Command strip 可扩展现有 `.command-strip`；必须复用语义 token。

#### Interaction

- 点击事件标题打开告警 / Mission 关联上下文；“进入 Mission”始终指向唯一关联 Mission。
- 时间范围切换保持图表焦点与数据来源标签；切换时局部加载。
- 队列排序默认严重度 → 持续时间；用户调整后在当前会话保持。
- 实时更新不得打断键盘焦点、重置滚动或突然重排正在操作的列表；新事件通过 `aria-live="polite"` 摘要提示。
- 数据陈旧或 revision 非最新时，所有依赖实时状态的写操作禁用并提供“刷新权威状态”。

#### Page-specific States

- Production 首页 API 失败：保留 Shell 与运行模式，显示失败关闭说明、correlation ID 和重试；不得展示 Demo 指标。
- 无高优事件：Command strip 显示“当前没有需要立即处置的事件”，主操作改为“查看全部告警”，不伪造 P1。
- 部分指标不可用：卡片显示 `—` 与原因；其他卡片保持。

### UI-002 — 资产与监测上下文

**Routes:** `/wind-farms`、`/turbines/:id`、`/scada`、`/health`、`/digital-twin`  
**Related Requirement:** PRD-001  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（只指导 Shell、密度、间距与 visual tone）

#### User Goal

在同一资产上下文中从风场下钻到风机、信号、健康和结构节点，并核对对象 ID、时间窗和状态是否一致。

#### Layout and Hierarchy

- 顶部 Context header 固定呈现风场、资产 ID、状态、最后更新时间、时区和数据窗口。
- 风场页：KPI / 状态分布在上，资产表或矩阵为主体；筛选结果数量靠近筛选器。
- 风机详情：首屏为资产身份与当前状态；第二层为关键遥测与健康；第三层为告警、Mission、工单、知识关联。
- SCADA：主趋势占 `8 / 4`，右侧为测点选择、质量与阈值；相关信号置于下方，不与主趋势争夺高度。
- 健康：矩阵 / 风险分布为主，选择资产后打开详情面板；健康度、异常分数、失效概率和 RUL 使用不同字段名。
- 数字孪生：资产结构与状态热点为主，节点检查器为辅；明确标注“运行上下文视图”，不出现物理仿真或控制暗示。

#### Interaction and Reuse

- 资产选择在相关工作区间保留；URL 包含可分享的非敏感对象身份。
- 图表缩放、测点切换和矩阵选择都提供键盘路径与“重置视图”。
- 复用 `DataTable`、`TimeSeriesChart`、健康语义、详情 Drawer 与 `StatusBadge`。
- 点击关联对象打开真实详情；不存在关联时使用解释性 Disabled，不提供无响应按钮。

#### Page-specific States

- 越界资产按不泄露存在性的结果处理；普通未知 ID 显示 Not Found 和返回列表。
- 实时流断开时保留最后成功数据并显示时间、`STALE/OFFLINE`；不把曲线清零。
- 测点缺失或质量不足时解释为什么不能计算相关性 / 健康指标。

### UI-003 — 告警处置

**Route:** `/alarms`  
**Related Requirements:** PRD-001、PRD-002  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（优先队列、状态和密度参考）

#### User Goal

按严重度和持续时间分诊告警，核对证据与关联对象，完成确认 / 指派，并在无 Mission 时安全创建唯一 Mission。

#### Layout and Hierarchy

- 顶部 summary 只保留待处理、P1/P2、未指派、陈旧四类可操作计数。
- 主体为 `7 / 5` 列表详情：左侧告警表，右侧 Drawer / 固定详情显示身份、时间、测点、健康变化、证据、负责人、revision 和关联 Mission。
- 详情页第一层是严重度、状态、持续时间与资产；第二层是证据与影响；第三层是审计和次要元数据。
- 主操作随状态唯一变化：确认、指派给我或创建 Mission；已有 Mission 时显示“进入 Mission”。

#### Interaction

- 筛选、排序、分页和选中行写入 URL 的非敏感 query，返回时恢复。
- 确认 / 指派提交携带 idempotency key 与 expected revision；提交中锁定同一对象动作。
- 创建 Mission 的确认面板明确告警、资产、当前 revision 和结果；超时显示“结果未知”，先查询权威状态。
- 权限不足时说明需要的 capability；不调用写 API。

#### States

- 告警列表为空与筛选为空分别处理。
- 行更新冲突：保留用户上下文，显示新旧状态摘要并要求复核。
- 详情局部失败不移除列表；可单独重试详情。

### UI-004 — Mission、诊断与人工决策

**Routes:** `/missions`、`/missions/:id`、`/diagnosis`、`/decisions`  
**Related Requirements:** PRD-002、PRD-003、PRD-005  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（Shell、面板比例、状态语义参考）

#### User Goal

审阅公开诊断与证据，理解候选方案和反证，在职责分离和 revision 门禁下提交人工结果。

#### Layout

- Mission 列表：summary + 搜索 / 状态 / 优先级 / 资产筛选 + 表格或 Kanban；两种视图共享同一状态语义。
- Mission 详情顶部：breadcrumb、Mission ID、来源资产 / 告警 / prediction、状态、revision、最后更新时间和阶段条。
- `≥1400px`：三列 `3 / 5 / 4`，依次为上下文 / 团队、公开事件与证据、决策 / 门禁。
- `1000–1399px`：两列，决策区移至第二行；`<1000px`：单列，阶段与主操作在内容前。
- 诊断内容按固定结构分区：事实、模型输出、假设、支持证据、反证、限制、建议动作。
- 决策中心在左侧列出候选方案，中部比较安全 / 成本 / 停机 / 天气 / 资源，右侧显示已选方案和人工结果。

#### Visual Hierarchy

1. 当前阶段、阻断原因和有权限用户的下一步动作。
2. 事实、支持证据与反证。
3. 候选方案及 trade-off。
4. Agent / Tool 公开事件、版本和失败上下文。
5. 审计元数据。

#### Interaction

- Timeline 只展示结构化公开事件；事件可展开查看工具名、输入 / 输出摘要、来源和 correlation，不出现隐藏推理文案。
- 证据点击打开可追溯来源；外部制品先显示 URI、hash、验证状态，再允许下载。
- `approve`、`reject`、`request revision`、`escalate` 为四个独立业务结果，不使用单个切换控件。
- 提交前显示当前方案、对象、revision 和影响；理由必填且失败后保留。
- request revision 成功后显示新 revision 与重新分析状态；reject / escalate 不出现工单授权 CTA。
- Agent 长任务显示阶段、最近心跳、开始时间和可恢复状态；失败显示非敏感失败上下文与允许的重试 / 升级入口。

#### Components and Reuse

- 复用 `StatusBadge`、`Progress`、`KeyValue`、时间线、`Card`、`Button`、`DataTable`、Dialog。
- 事实 / 模型输出 / 假设 / 反证使用统一 EvidenceItem 结构；不能用四套视觉风格。
- 审批表单与所有高风险写入复用同一 revision / idempotency / result-unknown 行为。

#### States

- 没有诊断或证据时明确显示门禁原因，不显示“已证实”。
- Agent 失败时 Mission 不无限停留“运行中”；显示失败阶段和可执行下一步。
- 无审批权限时仍可查看公开证据，但审批区显示只读职责说明。
- prediction 来源在无 `benchmark_truth` scope 时不显示或暗示真值。

### UI-005 — 工单、维护计划与资源

**Routes:** `/work-orders`、`/maintenance`、`/resources`  
**Related Requirement:** PRD-003  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（Shell、卡片、队列与作业窗口参考）

#### User Goal

运维经理判断工单是否具备排程条件，现场人员按序提交证据，并从资源、天气和 EAM 状态确认真实执行结果。

#### Layout and Hierarchy

- 工单中心采用列表 + 详情；详情顶部突出 Mission / Decision 授权、排程状态和下一项允许任务。
- 任务清单是主内容；安全约束、资源、天气、EAM 和证据验证作为紧邻的上下文，不藏在独立深层页面。
- 维护计划使用日历 / 列表双视图；时间窗、冲突与资源占用同时可读。
- 资源中心按备件、班组、船舶、工具、天气窗口分 Tab；每条预留显示工单关联。

#### Interaction

- 未批准、未排程、前序任务未完成或资源 / 天气不满足时，主操作 Disabled 并列出阻断原因。
- 现场任务表单显示任务版本、必需测量、单位、阈值来源、制品 URI 与 SHA-256；不在 UI 硬编码另一套阈值。
- 提交后只在服务器验证对象、hash、schema、测量与顺序通过时标记完成。
- 最后一项任务完成不等于关单；最终健康门槛独立显示和确认。
- EAM 本地交付、外部已接收、失败待重试使用不同状态，不能合并为“成功”。

#### States

- 离线时可以查看最后成功任务清单，但不能显示现场证据“已保存”。
- 重复提交使用同一幂等键安全重放；不同内容复用键显示不可重试冲突。
- 资源或天气局部失败时保留工单，不把就绪度显示为 100%。

### UI-006 — CARE 数据、模型治理与预测

**Routes:** `/data`、`/models`、`/predictive-maintenance`  
**Related Requirements:** PRD-004、PRD-005、PRD-006  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（Shell、表格、状态与数据密度参考）

#### User Goal

可靠性 / 模型工程师核对 CARE 根、质量与制品血缘，查看完整评估结果，并只激活服务器门禁允许的 anomaly 部署。

#### Layout and Hierarchy

- 数据中心：资产 / 数据集目录在左，检查器在右；CARE 区块独立呈现版本、许可、根、映射、质量、运行和制品。
- 模型管理：能力注册表与详情采用 `5 / 7` master-detail；详情依次显示身份、输入 / 输出、制品、评估、服务器 gate、部署。
- 事件级评估表不隐藏 failed / unscorable；发布指标与观察指标分组。
- 预测性维护只展示来自已通过治理门禁部署的在线结果；没有权威结果时保持空态。

#### Interaction

- 评估选择更新 URL 或稳定选中态；刷新不自动跳回第一项。
- “揭示真值”只在服务器返回允许时可用；默认隐藏，并明确这是评估后信息。
- 激活 / 回滚是危险操作：确认模型、版本、制品 hash、评估 run、当前 / 目标部署、一次性服务器授权和预期 revision。
- 客户端不能编辑 gate 指标或提交“已通过”字段；按钮 Disabled 文案展示服务器阻断原因。
- 长运行任务显示事件总数、已处理、失败 / 不可评分、checkpoint、最近心跳和取消后果。

#### States

- 根、映射、mask、制品或许可不一致时使用 Critical gate，所有写入 Disabled。
- 评估 API 失败不显示 Demo 模型卡；事件级子查询失败只影响对应面板。
- 无 `benchmark_truth` scope 时，界面不渲染标签、故障描述、真值区间占位或暗示性统计。

### UI-007 — Agent、知识、报告与系统治理

**Routes:** `/agents`、`/knowledge`、`/knowledge-graph`、`/reports`、`/settings`  
**Related Requirement:** PRD-006  
**Reference:** `docs/ui/reference/dashboard-desktop.png`（系统级 Shell、密度和 visual tone 参考）

#### User Goal

在不脱离权限、来源和运行边界的情况下查看或管理支持工作区。

#### Shared Layout Pattern

- 列表 / 注册表 / 搜索结果为左或主列，检查器 / 预览 / 设置表单为右或次列。
- 全局高权限动作只出现在 Header 或详情的固定 action 区，不散落在统计卡片。
- 知识回答的引用与原文片段紧邻；图谱实体展示 PostgreSQL 来源与投影新鲜度。
- 报告预览显示数据窗口、摘要、生成状态和 hash；只有已就绪制品允许下载。
- 系统设置按身份与访问、平台配置、运行时 / 依赖、审计分组；Secret 只显示引用和健康状态。

#### Interaction and States

- Knowledge / Graph 一个子系统失败不抹去另一个成功结果；Neo4j 降级明确可见。
- 报告生成提交后显示持久化任务；导出失败不下载空文件。
- Agent / 模型 / 平台写入需要 Operations Manager 与对应全局 scope；只读用户看到说明，不看到假可用按钮。
- 设置变更显示影响范围、revision、审计原因和结果；敏感值不回显。

## 7. 全局 UI 状态

| State                    | Visual Treatment                                                | Required Behavior                                 |
| ------------------------ | --------------------------------------------------------------- | ------------------------------------------------- |
| Initial Loading          | 保留 Shell；内容区使用与最终布局一致的 skeleton                 | 宣布加载目标；关联动作 Disabled；不得显示 fixture |
| Refreshing               | 内容保留，header / panel 显示“刷新中”和上次成功时间             | 不清空页面；高风险写入使用最新 revision           |
| Empty                    | 中性图标、明确标题、范围说明、允许的下一步                      | 区分“真实无记录”与加载失败                        |
| Filtered Empty           | 保留筛选器和结果数，提供“清除筛选”                              | 不误报系统无业务数据                              |
| Success                  | 就地更新状态、revision、时间和关联数量                          | 只有权威服务确认后出现；toast 只作补充            |
| Full Error               | 页面级 alert / banner、用户语言、error code / correlation、重试 | Production 失败关闭，不回退 Demo                  |
| Partial Failure          | 失败区域 inline alert，其他区域保留                             | 提供局部重试；不把未知值显示为 0                  |
| Permission Denied        | 解释需要的 capability / scope，不展示受限数据                   | 不调用写 API；服务器仍为最终裁决                  |
| Out of Scope / Not Found | 通用不存在文案与返回列表                                        | 越界对象不显示名称、状态或关联计数                |
| Offline / Stale          | Warning banner + 最后成功时间；数据区水印 / badge               | 保留最后有效读结果；阻断依赖实时状态的写入        |
| Conflict                 | 冲突摘要、刷新权威状态、重新复核 CTA                            | 不自动覆盖，不自动重放旧理由                      |
| Result Unknown           | 明确“请求结果未知”，显示查询 / 安全重放入口                     | 不假设失败或成功，不生成新幂等键                  |
| Long Running             | 阶段、进度或计数、最近心跳、可恢复状态                          | 未知进度不伪造百分比；允许取消时说明后果          |
| Disabled                 | 降低强调但保持可读；tooltip / inline reason                     | Disabled 不是权限控制；必须解释阻断条件           |
| Dangerous Action         | 确认 Dialog 显示目标、当前 / 预期状态、理由与后果               | 提交中防重复；取消为安全默认焦点                  |

状态文案模板优先使用：`发生了什么` + `影响什么` + `用户现在能做什么`。不得只显示“出错了”“暂无数据”或内部堆栈。

## 8. Forms 与写操作

- 每个表单有可见标题、对象上下文、字段 label、必填标记、格式 / 单位和提交结果。
- 表单错误摘要链接到第一个错误字段；字段使用 `aria-describedby` 关联错误。
- 提交失败保留用户输入；成功后焦点移动到结果摘要或对象新状态。
- 提交中禁用同一业务意图的重复操作，但允许阅读上下文和取消尚未发送的流程。
- 网络超时进入 Result Unknown；客户端查询权威状态或使用同一 idempotency key、目标、revision 和 payload 重放。
- 高风险操作理由不得由 placeholder 预填；actor 从服务器身份展示为只读。

## 9. 数据密集型 UI

- 默认排序必须与用户任务相关：告警按严重度 / 持续时间，Mission 按优先级 / 更新时间，工单按可执行性 / 排程时间，评估按时间 / 角色。
- 表格顶部包含搜索、关键筛选、结果数量；低频筛选进入 popover / drawer。
- 选择、批量操作、列显示和导出遵循 `DataTable` 一致行为。
- 长 ID 显示前后有意义片段并支持复制；完整值通过 tooltip / detail 查看。
- 长文本默认两行截断，展开不改变相邻行的操作位置。
- 分页使用服务器总数时明确当前范围；无限滚动不用于需要审计定位的表格。
- 图表必须有单位、时区、来源、刷新时间、图例、异常 / 缺口说明与等价摘要。

## 10. 响应式规则

### Desktop — `≥1440px`

- 侧栏默认展开 `250px`，允许折叠为 `74px`。
- 指挥中心维持六 KPI、`7 / 5` 主区和 `4 / 4 / 4` 次区。
- Mission 详情使用三列；列表详情可并排。
- 关键内容在 `1440 × 900` 首屏可见；允许页面滚动，但主操作不应被无关卡片推到首屏以下。

### Laptop — `1024–1439px`

- 侧栏默认折叠或记忆用户选择；正文不得小于 `760px`。
- KPI 为 `3 × 2`；首页主图与处置队列可 `7 / 5`，空间不足时队列置于主图之前纵向排列。
- Mission 详情两列后换行；复杂表格隐藏低优先列，保留列显示控制。

### Tablet / Narrow Web — `768–1023px`

- 侧栏变为覆盖式 Drawer；顶栏保留运行状态、搜索入口和身份。
- 所有主布局单列；summary 可两列。
- 列表选择后详情以全宽 Drawer 或独立页面呈现。
- 表格优先保留对象、状态、时间、主操作；可横向滚动但页面本身不得双向滚动。

### Mobile / Narrow Web — `320–767px`

- 不建设原生 App；提供可完成 PRD 核心查看与角色允许的写链路的响应式 Web。
- Header 操作最多保留一个主按钮，其余进入可访问菜单；标题和状态不与操作挤在同一行。
- KPI 单列（`≥480px` 可两列）；Command strip 单列，严重度、标题、进度、主动作按阅读顺序排列。
- 图表提供横向安全缩放或摘要 / 数据表；禁止把轴标签压到不可读。
- Mission 阶段条可水平滚动且有文本摘要；Timeline 隐藏独立时间列但在事件正文中保留时间。
- 点击目标至少 `44 × 44px`；底部固定操作不得遮挡内容和系统手势区域。

### Zoom / Reflow

- `200%` 浏览器缩放下不丢内容、不重叠、不出现页面级双向滚动；数据表自身可横向滚动。
- 高度不足时允许纵向滚动，不通过缩小字体压入单屏。

## 11. Accessibility 最低要求

目标为 WCAG 2.2 AA；至少满足：

- 所有功能可由键盘完成；Tab 顺序与视觉顺序一致，无键盘陷阱。
- 交互元素使用原生 `button`、`a`、`input`、`table` 等；不把普通 `div` 仅靠点击变成交互控件。
- 可见焦点对比清晰，不能被 sticky header、Drawer 或遮罩覆盖。
- 正文 / 控件文字对比度至少 `4.5:1`，大字号至少 `3:1`；图标、焦点和图形对象至少 `3:1`。
- 状态、严重度、选中和图表系列不只靠颜色；使用文字、图标、形状、线型或纹理。
- 页面一个 `h1`，标题层级不跳跃；landmark、面包屑和表格 caption / accessible name 完整。
- 图标按钮有可访问名称；状态图标对屏幕阅读器隐藏或提供等价文字，避免重复朗读。
- 加载、成功、失败、实时更新使用适当 live region；高频实时值不逐点播报。
- Dialog / Drawer 管理焦点，支持 `Escape`（危险提交过程中除外），关闭后返回触发点。
- 表单 label、帮助和错误关联；错误不只靠颜色，提交后焦点到错误摘要。
- 图表提供文本摘要和可访问数据；Tooltip 不是获取关键数据的唯一方式。
- 尊重 `prefers-reduced-motion`；无自动闪烁、视差或不可关闭动画。
- 关键业务正文不小于 `12px`，辅助文字不小于 `11px`；允许用户字体放大和系统高对比模式。

## 12. Screenshot Review 与实现验收

实现阶段每个关键页面应执行：

1. 在 `1440 × 900`、`1280 × 800`、`390 × 844` 打开真实页面。
2. 分别验证 Demo 与 Production；Production 依赖失败必须失败关闭。
3. 截取真实浏览器 screenshot，与 reference image 比较 composition、layout、spacing、hierarchy、typography、component proportion、density 和 visual tone。
4. 验证 Loading、Empty、Filtered Empty、Error、Partial Failure、Permission、Stale、Conflict、Result Unknown 和 Disabled。
5. 使用键盘、屏幕阅读器、200% 缩放和 reduced motion 检查关键流程。
6. 修复与本规格冲突的偏差后再次截图。

Image2 参考图不能直接成为 visual regression baseline。只有 Reviewer 批准的真实浏览器截图才能进入 baseline。

## 13. UI Acceptance Checklist

- [ ] UI-001 至 UI-007 均能追溯到对应 PRD Requirement。
- [ ] 22 个既有工作区没有新增无来源、无权限或无闭环价值的入口。
- [ ] 首页最高风险、数据新鲜度和下一步动作具有明确首屏层级，KPI 不超过六项。
- [ ] 诊断明确区分事实、模型输出、假设、支持证据和反证，不展示隐藏推理。
- [ ] 审批、工单、现场证据、模型激活 / 回滚遵守权限、revision、幂等和结果未知语义。
- [ ] Production 失败不回退 Demo；所有关键状态有可操作的恢复路径。
- [ ] 组件、语义色、表格、Drawer、Dialog、图表和表单遵循统一复用规则。
- [ ] `1440 × 900`、`1280 × 800`、`390 × 844` 的核心查看和允许写链路可完成。
- [ ] 键盘、焦点、对比度、文本替代、表单错误、200% 缩放和 reduced motion 无 blocker。
- [ ] 实现遵循视觉意图，但未把参考图当作像素级真值或业务真值。
