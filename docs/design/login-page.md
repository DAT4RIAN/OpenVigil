# OpenVigil 登录页

当前版本：2026-09-16 更新风场图片，文案统一为“风电智能运维平台”，见 [登录页更新](login-onshore-update.md)。以下为 2026-09-15 初版的历史设计、素材和验证记录。

日期：2026-09-15。任务：增加登录页面，并使用生成图片作为视觉素材。

## 页面与身份边界

- 路由：`/login`，独立于 22 个业务工作区页面。
- 桌面为海上风场图片与登录操作区的双栏布局，沿用雾灰、青绿色与已有字体；手机为单栏入口，支持深浅主题。
- 生产环境：未登录访问业务页面时跳转到登录页，保留安全的 `return_to`；点击登录后进入已有 `/signin-with-chatgpt` 托管身份流程。
- 演示环境：显示“进入演示工作台”和演示说明；工作台用户头像区域可返回登录页。该入口不授予生产权限。
- 页面不新增账号密码系统。现有后端角色和能力校验继续控制业务页面与 API；公开登录页会剥离客户端伪造的能力会话。
- 外部网址、反斜杠、控制字符与登录/回调循环目标回退到 `/`。断网时显示可重试提示，跳转中禁用重复点击；浏览器恢复页面时重置等待状态。

## 图片来源

- 生成方式：内置 `image_gen` 工具，2026-09-15 新生成。
- 用户要求 Image 2.5；当前工具不提供模型选择参数或可核验的型号信息，因此无法确认使用的具体型号为 Image 2.5。
- 项目素材：[login-wind-farm.png](../../public/images/login-wind-farm.png)，1122 × 1402，PNG，约 1.78 MB。
- 这是 AI 生成的视觉素材，不代表真实风场照片或业务数据。图片说明直接显示在桌面画面中。
- 未增加图像处理依赖，当前保留生成 PNG 原图。

### 实际生成提示词

```text
Use case: photorealistic-natural. Asset type: portrait hero photograph for the login page of OpenVigil, an offshore wind operations application. Create a refined cinematic editorial aerial photograph of a real-looking offshore wind farm at blue hour just before sunrise. Composition: portrait 4:5, several elegant physically plausible three-bladed white offshore wind turbines receding diagonally into a misty horizon, one hero turbine in the upper-middle-right of the image, ocean filling the lower third with spacious calm dark water for text that will be overlaid later in HTML. Moody deep petroleum teal sea, slate blue haze, restrained pale warm dawn glow at the distant horizon; natural white turbine blades and fine atmospheric detail. The sea has subtle believable wave texture and turbine reflections; quiet, precise, industrial, premium. Photographic realism, not science fiction. Low visual clutter and clear shapes visible at small sizes. Keep lower 35 percent relatively dark and calm for readable white interface text, upper-left also uncluttered for a small brand mark. No lettering, no logos, no watermark, no dashboard UI, no glowing telemetry, no borders, no floating holograms. Output a high-resolution image suitable for a full-height left-side login hero.
```

## 验证记录

- 构建、bundle budget、TypeScript、修改源码和浏览器测试的 ESLint 通过。
- 登录定向验证：生产跳转、伪造会话隔离、离线恢复、图片加载、320/390/768/1440px 深浅主题与 WCAG 检查已通过；演示入口返回链接首轮失败后改为完整文档导航，完整回归通过。
- finesse 静态检测无 P0；实际截图已审视，保存在 `.artifacts/login/login-{light,dark}-{1440,390}.png`。
- 完整回归：Node 185/185、Playwright 37/37，无 skip；Prettier 与 `git diff --check` 通过。证据日志：`.artifacts/login/node-tests.log`、`.artifacts/login/e2e-tests.log`、`.artifacts/login/build.log`。
- 实际本地 Demo：`http://localhost:3001/login` 返回 200，进入工作台和返回登录页均通过，页面运行错误为 0；截图 `.artifacts/login/local-demo-login.png`。现有 >500kB 构建分块提示保留，bundle budget 通过。
- 验证边界：本地 Demo 与生产界面隔离测试。测试中的托管身份入口是 fixture，真实外部身份登录与生产后端部署未验证。
