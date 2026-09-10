# OpenVigil Operations Command Center — Selected Image2 Prompt

- Mode: built-in image generation
- Use case: `ui-mockup`
- Selected direction: `Incident-first Operations / 事件优先的运营指挥`
- Output: `docs/ui/reference/dashboard-desktop.png`
- Input image 1: `public/openvigil-command-center.png` — current implementation and information architecture reference
- Input image 2: `docs/design/openvigil-operations-command-center-concept-v2.png` — prior industrial visual direction reference

```text
Use case: ui-mockup
Asset type: high-fidelity desktop web application dashboard reference for the current OpenVigil repository
Input images: Image 1 is the current implemented dashboard screenshot and defines existing product information architecture; Image 2 is an earlier refined concept and defines the restrained industrial visual language. Generate a new design reference, not a pixel-for-pixel copy.
Primary request: 为 OpenVigil 风电运维多智能体平台设计“运营指挥中心”桌面页面。方案 A：事件优先的运营指挥。页面要让值班人员在 3 秒内识别当前最高优先级风险、数据是否新鲜、下一步受控动作是什么，并能进入 Mission。
Product truth: 64 台海上风机；核心链路是监测 → 告警 → Mission → 诊断 → 人工决策 → 工单 → 现场证据 → 健康复核。AI 只组织公开证据和推动流程，不自主批准，不展示隐藏推理。
Style/medium: realistic shippable enterprise SaaS / industrial operations UI, mature production software, crisp vector-like interface, restrained data-dense layout, no concept-art styling.
Composition/framing: straight-on full-screen web application canvas, no browser chrome, 16:10 desktop at 1440×900 intent.
Layout:
- 240px fixed dark graphite sidebar with OpenVigil mark, current wind farm selector, grouped navigation, active “运营指挥中心”.
- 56px top bar with production/demo runtime badge, live/stale status, last snapshot time, search, notifications, scoped operator identity.
- Main header “运营指挥中心”, subtitle “华东海上风电场 · 64 台机组”, actions “运行日历” and “生成报告”.
- Directly below header, one dominant P1 incident command strip: “WT-023 主轴承振动异常”, public AI status, health 62/100, anomaly severity, data freshness, and primary button “进入 Mission”.
- One concise row of six KPI cards only: current power, 24h energy, operating turbines, average health, active alarms, active Missions. Clearly label authoritative snapshot time.
- Main workspace uses a 7/5 column split: left large SCADA 24H chart with anomaly and AI event markers; right prioritized alarm / Mission queue with owner, age and next action.
- Lower row: active Mission progress, public Agent activity timeline, offshore work window. Keep all panels visible above fold with realistic density.
Visual hierarchy: incident strip is first; current risk queue second; trend context third; background metrics last. Primary action appears once.
Color palette: deep graphite/navy sidebar and restrained dark content surfaces, cool teal primary accent, emerald success, amber warning, coral red critical, warm off-white typography. High contrast, not neon.
Typography: modern Chinese sans-serif, 13–14px body, large tabular numbers, excellent legibility.
Materials/textures: matte flat surfaces, 1px borders, subtle grid lines, minimal shadows, 8px radius, no glossy effects.
Text (verbatim where visible): “OpenVigil”, “运营指挥中心”, “华东海上风电场 · 64 台机组”, “PRODUCTION CANDIDATE”, “数据新鲜”, “快照 10:30”, “运行日历”, “生成报告”, “P1”, “WT-023 主轴承振动异常”, “AI 正在分析”, “进入 Mission”, “当前功率”, “24h 电量”, “运行机组”, “平均健康度”, “活跃告警”, “活跃 Missions”, “SCADA · 24H”, “优先处置队列”, “Agent 公开活动”, “海上作业窗口”.
Constraints: production-feasible with existing AppShell, Card, MetricCard, chart, table/list, status badge and progress components; readable Chinese labels; show status with text plus color; realistic aligned data; no fabricated chat assistant; no autonomous approval; no RUL; no physical control-room scene; no 3D perspective; no floating holograms; no stock photos; no unrelated logos; no watermark.
Avoid: generic crypto dashboard, sci-fi HUD, excessive glow, glassmorphism, giant empty hero area, nine equal-priority KPI cards, tiny text, random English filler, duplicated actions, decorative gradients.
```

## Reference Boundary

图片用于视觉意图，不是像素级真值。实现必须以 `PRODUCT_REQUIREMENTS.md` 与 `UI_UX_SPEC.md` 定义的字段、权限、状态、响应式和 accessibility 规则为准。
