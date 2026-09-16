# 登录页：风场图片与文案更新

日期：2026-09-16。

## 当前定位与设计

- 最终对外文案统一为“风电智能运维平台”，不刻意强调陆上或海上；保留生成的草地、山脊风场图片。
- 桌面保留双栏登录布局，使用晨光、草地、山脊、检修道路与白色风机的新图片；保持雾灰/青绿色操作区及既有字体。
- 图片区域使用偏绿的深色遮罩保证文字可读。手机保留单栏登录，直接展示“风电智能运维平台”。
- 保留已实现的身份跳转、安全返回路径、演示入口、离线提示、等待状态、键盘交互与减少动态效果。

## 图片来源

- 内置 `image_gen` 工具于本次任务生成 1 张图片。
- 用户指定 Image 2.5；当前工具没有模型选择或型号核验参数，因此不声明具体型号已确认。
- 当前素材：[login-onshore-wind-farm.png](../../public/images/login-onshore-wind-farm.png)，1122 × 1402，PNG，2,197,022 字节。
- AI 生成的场景图，不对应某个真实风场；页面保留 AI 生成标识。原海上图片保留为历史素材，登录页改用新路径。
- 完整提示词：[login-onshore-wind-farm.prompt.md](login-onshore-wind-farm.prompt.md)。

## 验证

- 最终文案统一为“风电”后，重新构建、TypeScript、差异检查与登录测试 `5/5` 通过，并刷新本地 3001 预览核验。
- 构建与 bundle budget 通过；现有 >500kB 分块提示保留，未增加依赖。
- TypeScript、修改代码 ESLint/Prettier、`git diff --check` 通过。
- Node `185/185`，证据日志：`.artifacts/login/onshore-node-tests.log`。
- `pnpm exec playwright test tests/e2e/login-page.spec.ts`：`5/5`，覆盖身份路径、安全返回地址、伪造会话隔离、演示入口与断网恢复；图片、定位文案、320/375/390/414/768/1440px 深浅主题与 WCAG 均通过。
- `pnpm exec playwright test tests/e2e/motion.spec.ts --grep login`：`2/2`，覆盖登录入场终态与减少动态效果；所有本次测试无 skip。
- 已审视实际桌面深浅主题与手机截图：`.artifacts/login/login-{light,dark}-{1440,390}.png`。图片中的陆上场景清晰，文字与操作区布局完整。
- finesse 检测无 P0；TSX 单文件扫描的 missing-stamp P2 对应独立 CSS 文件，CSS 已有 stamp，CSS 扫描无 findings。
- 实际本地 Demo：`http://localhost:3001/login`，通过应用内浏览器完成“登录页 → 演示工作台 → 返回登录页”，预览保留。
- 验证边界：本次只验证本地 UI 与隔离生产入口，不声称真实外部身份服务或生产发布通过。项目介绍文件受现有 Git 忽略规则影响，仅本地同步。
