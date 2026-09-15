# 前端视觉优化方案

日期：2026-09-15  
状态：`DONE / LOCAL_UI_VALIDATED`，已实施并完成本地前端验证。

## 设计依据

- 延续 `UI_UX_SPEC.md` 的事件优先方向、深色侧栏、青绿色主色与浅色正文。
- 以 `PRODUCT_REQUIREMENTS.md` 为业务依据，保留 Demo / Production、风险等级、数据新鲜度和授权动作语义。
- 使用 finesse-ui 的产品界面流程；项目暂无 `.finesse/log.json` 或前端 CSS 设计记录。
- 本轮无需新增图片或依赖，复用现有图标与图表。

## 实施范围

| 范围           | 具体调整                                                                     | 对应文件                                                         |
| -------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 基础视觉       | 灰底与卡片形成更清晰的明度层次；柔化边框与阴影；保持正文对比度；同步深色主题 | `app/styles/01-foundations.css`                                  |
| 全局导航与页头 | 优化品牌、导航分组和当前选中项；减少页头无效空白；统一按钮与搜索框比例       | `app/styles/02-shell-and-shared.css`                             |
| 指标与共享组件 | 突出指标数值，减轻单位和说明字重；使用有语义的图标底色；统一表格与控件状态   | `app/styles/02-shell-and-shared.css`、`components/data-display/` |
| 首页           | 突出风险标题和进入 Mission 动作；统一图表与处置队列的标题、分隔线和间距      | `app/styles/03-dashboard.css`                                    |
| 手机布局       | 缩短事件卡的纵向占用；重排信号指标；保持导航抽屉和至少 44px 的触控区域       | `app/styles/11-overlays-and-responsive.css`                      |

动效仅服务悬停、按下、切换等反馈，并支持减少动态效果的系统设置。

## 基线证据

- 已记录现有工作区改动，包含 `.gitignore`、`EXECUTION_PROGRESS.md`、暂存删除、gitlink 与未跟踪文件；必须保护。
- `node node_modules/vinext/dist/cli.js build`：通过，存在大于 500kB 的分块警告。
- `node node_modules/typescript/bin/tsc --noEmit`：通过。
- 现有构建在本地端口 3001 成功启动并显示 Demo 首页；该预览不是生产后端验收。
- 浏览器检查 1440px 桌面与 390px 手机页面；对应文档宽度分别为 1440px 和 390px。手机事件卡过长，后续指标被推到首屏下方。
- 截图：`.artifacts/finesse/before-desktop.png`、`.artifacts/finesse/before-mobile.png`；属于修改前预览，拍摄时使用仓库已有构建。
- 开发服务出现 Cloudflare `Request.cf` 获取超时且未监听端口，已结束本次启动。未因此修改项目配置。

## 实施与验证顺序

1. 确认上述视觉方向后，先调整共享 token、导航与控件，再处理首页与窄屏比例。
2. 运行相关格式、类型、构建与响应式测试，检查浅色和深色主题。
3. 在桌面、平板、手机检查首页及代表性的列表、详情页面；核实键盘焦点、导航、主题切换与数据状态。
4. 记录最终截图和实际检查结果，再更新执行进度及 finesse 设计记录。需要更新视觉基线时，必须先人工审视差异；不能以替换截图代替验证。

## 方向确认

用户已回复“按此方向实施”，采用上述浅色正文方案。共享 token、导航、指标、首页和表格样式已完成，实际数据、运行模式与授权行为保持既有契约。

## 最终验证与交付

| 检查              | 结果                                                      |
| ----------------- | --------------------------------------------------------- |
| vinext build      | 通过；保留既有 >500kB 分块提示                            |
| bundle budget     | 通过，94 chunks / 2,614,910 bytes；最大分块 645,072 bytes |
| TypeScript        | `tsc --noEmit` 通过                                       |
| ESLint / Prettier | 本次修改的前端源码与测试通过；未执行无关文件的批量格式化  |
| Node tests        | `184/184` 通过，0 skip                                    |
| Playwright        | `32/32` 通过，0 skip；完整回归耗时约 2 分钟               |
| finesse detector  | P0 = 0；已人工核查其提示，详见下文                        |
| git diff --check  | 通过                                                      |

- 手机 P1 卡片截图高度从 398px 降到 294px；保留四项信号、完整风险标题和进入 Mission 动作，KPI 改为两列。
- 新增 `tests/e2e/frontend-polish.spec.ts`：深浅主题与持久化、关键页面 WCAG、320/375/390/414/768px 首屏内容、Mission 列内防遮挡。
- 查看实际 Mission 详情时发现原有嵌套网格的内容最小宽度超出左列，遮挡时间线。`app/styles/08-missions.css` 使用 `minmax(0, 1fr)` 和最小宽度约束修复；测试已验证修复前失败、修复后通过，左列内容宽度与列宽均为 302px（1440px 视口）。
- 审视后更新四张 `tests/e2e/__screenshots__/dashboard-*.png`；原有截图差异阈值与行为断言均保留。
- `tests/css-module-boundaries.test.mjs` 的旧重构摘要固定修改前 CSS，本次按审视后的新规则流更新为 `fcdff4b5e098fe4627f71a776dda9dfe1a603b15eeab51251ddb52e25f2673c7`。仍精确验证完整规则流和导入顺序。
- 一次 Node 测试与重新构建并发时读取不到 `dist/server/__vite_rsc_assets_manifest.js`，属于本次执行顺序问题；等待构建完整结束后重跑全套，通过 184/184。

### 视觉与静态检查说明

- 浅色/深色首页、手机首页、1280px 紧凑桌面、告警列表和 Mission 详情均已实际打开和查看截图。
- 保留既有 Geist / 中文系统字体；使用产品规范的 6 个 KPI 与 7/5 主区，未引入装饰动画或新图片。
- detector 提示的双 `sticky top:0` 对应左右并列的侧栏和顶栏，并不彼此遮挡；原有 query-state 色条承担错误/陈旧反馈语义，予以保留。
- 设计 stamp 位于基础样式首行；其它分片缺少独立 stamp 的提示由共享设计记录覆盖。项目本地记录写入被忽略的 `.finesse/log.json`。

### 本地证据

- `.artifacts/finesse/build.log`
- `.artifacts/finesse/node-tests.log`
- `.artifacts/finesse/e2e-tests.log`
- `.artifacts/finesse/detector.json`
- `.artifacts/finesse/after-desktop.png`、`after-dark.png`、`after-mobile.png`、`after-alarms.png`、`after-mission.png`
- 完整浏览器报告：`.artifacts/playwright/report/index.html`

本次验证限定本地 Demo 和隔离的生产界面测试场景；真实生产后端、外部 CARE、签名与发布门禁不在此次美化验收范围内。
