import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";
const FONT_LATIN = "Arial";

const C = {
  ink: "#101820",
  muted: "#5B6670",
  faint: "#8A949D",
  panel: "#F1F3F4",
  panel2: "#E8EEF0",
  line: "#C7CDD2",
  accent: "#1AA7A1",
  accentDark: "#0D6F6C",
  accentSoft: "#DDF4F2",
  navy: "#0B1D26",
  navy2: "#14313C",
  warning: "#D48A12",
  warningSoft: "#FFF1D5",
  alert: "#D94C57",
  alertSoft: "#FBE6E8",
  success: "#2D8B69",
  successSoft: "#E1F3EB",
  white: "#FFFFFF",
};

const BUILD_DIR = "C:\\coding\\project\\wind-agent\\.codex_tmp\\windops-ppt-20260831";
const RENDER_DIR = path.join(BUILD_DIR, "artifact-renders");
const FINAL_DIR = "C:\\coding\\project\\wind-agent\\deliverables";
const FINAL_PPTX = path.join(FINAL_DIR, "WindOps_风电运维智能体_项目介绍_10页.pptx");

const ASSETS = {
  dashboard: "C:\\coding\\project\\wind-agent\\public\\windops-command-center.png",
  commandCenter: "C:\\coding\\project\\wind-agent\\docs\\design\\windops-operations-command-center-concept-v2.png",
  incident: "C:\\coding\\project\\wind-agent\\tests\\e2e\\__screenshots__\\dashboard-p1-incident-390.png",
  overview: "C:\\coding\\project\\wind-agent\\public\\og.png",
};

function addShape(slide, geometry, position, fill = "none", lineFill = "none", lineWidth = 0, name = undefined, radius = undefined) {
  const shape = slide.shapes.add({
    geometry,
    name,
    position,
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
    ...(radius !== undefined ? { borderRadius: radius } : {}),
  });
  return shape;
}

function addText(slide, text, position, options = {}) {
  const shape = addShape(
    slide,
    "textbox",
    position,
    options.fill ?? "none",
    options.lineFill ?? "none",
    options.lineWidth ?? 0,
    options.name,
    options.radius,
  );
  shape.text = text;
  shape.text.style = {
    fontSize: options.fontSize ?? 20,
    typeface: options.typeface ?? FONT,
    color: options.color ?? C.ink,
    bold: options.bold ?? false,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
  };
  return shape;
}

function addRule(slide, left, top, width, color = C.line, height = 2) {
  return addShape(slide, "rect", { left, top, width, height }, color, "none", 0);
}

function addSlideTitle(slide, title, section, page) {
  addText(slide, section.toUpperCase(), { left: 58, top: 34, width: 480, height: 25 }, {
    fontSize: 15,
    bold: true,
    color: C.accentDark,
    typeface: FONT_LATIN,
  });
  addText(slide, title, { left: 58, top: 67, width: 1164, height: 72 }, {
    fontSize: 47,
    bold: true,
    color: C.ink,
    name: `slide-${page}-title`,
  });
  addRule(slide, 58, 142, 1164, C.line, 1);
}

function addFooter(slide, page, label = "WindOps · 风电运维智能体") {
  addText(slide, label, { left: 58, top: 675, width: 500, height: 22 }, {
    fontSize: 13,
    color: C.faint,
  });
  addText(slide, String(page).padStart(2, "0"), { left: 1150, top: 673, width: 72, height: 22 }, {
    fontSize: 14,
    bold: true,
    color: C.ink,
    alignment: "right",
    typeface: FONT_LATIN,
  });
}

function addNotes(slide, lines, sources) {
  const noteText = [
    ...lines,
    "",
    "[Sources]",
    ...sources.map((source) => `- ${source}`),
  ].join("\n");
  slide.speakerNotes.textFrame.setText(noteText);
  slide.speakerNotes.setVisible(true);
}

function addNumberCircle(slide, number, left, top, fill = C.accent) {
  addShape(slide, "ellipse", { left, top, width: 40, height: 40 }, fill, "none", 0);
  addText(slide, number, { left, top: top + 2, width: 40, height: 34 }, {
    fontSize: 18,
    bold: true,
    color: C.white,
    alignment: "center",
    verticalAlignment: "middle",
    typeface: FONT_LATIN,
  });
}

function addListRow(slide, number, heading, body, top, options = {}) {
  const left = options.left ?? 535;
  const width = options.width ?? 687;
  addNumberCircle(slide, number, left, top + 3, options.fill ?? C.accent);
  addText(slide, heading, { left: left + 58, top, width: width - 58, height: 30 }, {
    fontSize: 23,
    bold: true,
    color: C.ink,
  });
  addText(slide, body, { left: left + 58, top: top + 36, width: width - 58, height: 43 }, {
    fontSize: 17,
    color: C.muted,
  });
  if (options.rule !== false) addRule(slide, left + 58, top + 86, width - 58, C.line, 1);
}

function addMetricBlock(slide, left, top, width, number, label, detail, accent = C.accent) {
  addRule(slide, left, top, width, accent, 5);
  addText(slide, number, { left, top: top + 25, width, height: 78 }, {
    fontSize: 52,
    bold: true,
    color: C.ink,
    typeface: FONT_LATIN,
  });
  addText(slide, label, { left, top: top + 105, width, height: 34 }, {
    fontSize: 23,
    bold: true,
    color: C.ink,
  });
  addText(slide, detail, { left, top: top + 148, width, height: 62 }, {
    fontSize: 17,
    color: C.muted,
  });
}

function addLane(slide, index, title, subtitle, lines, left, accent) {
  const width = 350;
  addText(slide, String(index).padStart(2, "0"), { left, top: 168, width: 80, height: 60 }, {
    fontSize: 43,
    bold: true,
    color: accent,
    typeface: FONT_LATIN,
  });
  addText(slide, title, { left, top: 232, width, height: 34 }, {
    fontSize: 26,
    bold: true,
    color: C.ink,
  });
  addText(slide, subtitle, { left, top: 274, width, height: 52 }, {
    fontSize: 17,
    color: C.muted,
  });
  addRule(slide, left, 339, width, accent, 3);
  lines.forEach((item, i) => {
    addShape(slide, "ellipse", { left, top: 373 + i * 58, width: 10, height: 10 }, accent, "none", 0);
    addText(slide, item, { left: left + 24, top: 360 + i * 58, width: width - 24, height: 47 }, {
      fontSize: 17,
      color: C.ink,
      verticalAlignment: "middle",
    });
  });
}

function addArchitectureNode(slide, text, left, top, width, fill, border, options = {}) {
  addShape(slide, "roundRect", { left, top, width, height: options.height ?? 56 }, fill, border, 1, undefined, 8);
  addText(slide, text, { left: left + 12, top: top + 9, width: width - 24, height: (options.height ?? 56) - 16 }, {
    fontSize: options.fontSize ?? 18,
    bold: options.bold ?? false,
    color: options.color ?? C.ink,
    alignment: options.alignment ?? "center",
    verticalAlignment: "middle",
  });
}

async function buildDeck() {
  await fs.mkdir(RENDER_DIR, { recursive: true });
  await fs.mkdir(FINAL_DIR, { recursive: true });

  const assetBytes = {};
  for (const [key, assetPath] of Object.entries(ASSETS)) {
    assetBytes[key] = new Uint8Array(await fs.readFile(assetPath));
  }

  const deck = Presentation.create({ slideSize: { width: W, height: H } });

  // 01 — Cover: Codex Grid cover-image-field silhouette.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addText(slide, "WINDOPS · AI-NATIVE WIND OPERATIONS", { left: 58, top: 48, width: 520, height: 28 }, {
      fontSize: 15,
      bold: true,
      color: C.accentDark,
      typeface: FONT_LATIN,
    });
    addText(slide, "风电运维智能体", { left: 58, top: 142, width: 560, height: 96 }, {
      fontSize: 68,
      bold: true,
      color: C.ink,
      name: "cover-title",
    });
    addText(slide, "把异常感知、协同诊断、人工审批与工单执行\n连成一条可追踪、可恢复、可审计的业务闭环", { left: 58, top: 266, width: 520, height: 110 }, {
      fontSize: 25,
      color: C.muted,
    });
    addRule(slide, 58, 414, 82, C.accent, 5);
    addText(slide, "项目介绍 · 10 页", { left: 58, top: 440, width: 260, height: 28 }, {
      fontSize: 18,
      bold: true,
      color: C.ink,
    });
    addText(slide, "多智能体协作  ·  类型化工具  ·  Human-in-the-loop", { left: 58, top: 492, width: 535, height: 32 }, {
      fontSize: 17,
      color: C.accentDark,
    });
    addShape(slide, "roundRect", { left: 654, top: 38, width: 568, height: 600 }, C.panel2, C.line, 1, "cover-image-frame", 14);
    slide.images.add({
      blob: assetBytes.dashboard,
      contentType: "image/png",
      alt: "WindOps 运营指挥中心界面",
      fit: "cover",
      position: { left: 654, top: 38, width: 568, height: 600 },
      crop: { left: 0.20, top: 0, right: 0.04, bottom: 0.02 },
      geometry: "roundRect",
      borderRadius: 14,
    });
    addText(slide, "01", { left: 1150, top: 667, width: 72, height: 22 }, {
      fontSize: 14,
      bold: true,
      alignment: "right",
      color: C.ink,
      typeface: FONT_LATIN,
    });
    addNotes(slide,
      ["开场用一句话定义项目：WindOps 不是聊天界面，而是面向风电异常处置的受治理智能体闭环。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\public\\windops-command-center.png",
      ],
    );
  }

  // 02 — Problem framing.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "问题不是告警不足，而是处置链路断裂", "01 / 项目背景", 2);
    addText(slide, "数据在，告警在，\n经验也在。", { left: 58, top: 193, width: 390, height: 115 }, {
      fontSize: 42,
      bold: true,
      color: C.ink,
    });
    addText(slide, "缺的是一条能跨越系统、角色与现场执行的可信闭环。", { left: 58, top: 330, width: 410, height: 85 }, {
      fontSize: 24,
      color: C.accentDark,
    });
    addRule(slide, 58, 449, 370, C.ink, 2);
    addText(slide, "项目目标", { left: 58, top: 472, width: 160, height: 30 }, {
      fontSize: 20,
      bold: true,
      color: C.ink,
    });
    addText(slide, "让每一次异常都有证据、责任、审批和结果。", { left: 58, top: 512, width: 390, height: 60 }, {
      fontSize: 20,
      color: C.muted,
    });

    addListRow(slide, "1", "数据孤岛", "SCADA、告警、维护记录与知识文档彼此割裂。", 174, { fill: C.alert });
    addListRow(slide, "2", "决策断点", "从异常到诊断、方案、审批和工单缺少统一状态。", 284, { fill: C.warning });
    addListRow(slide, "3", "Agent 难以约束", "模型能给建议，但来源、权限与行动边界往往不透明。", 394, { fill: C.accent });
    addListRow(slide, "4", "执行难以追溯", "重试和并发可能造成重复工单，现场证据难以核验。", 504, { fill: C.ink, rule: false });
    addFooter(slide, 2);
    addNotes(slide,
      ["这一页把技术工作转译为业务问题：WindOps 的核心目标是闭环，而不是增加一个告警列表或聊天框。"],
      ["C:\\coding\\project\\wind-agent\\docs\\agent-engineer-interview-project-introduction.md"],
    );
  }

  // 03 — Closed-loop operating model.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "WindOps 把一次异常处置变成受治理的 Agent 闭环", "02 / 解决方案", 3);
    addText(slide, "每个阶段都产生结构化状态，并为下一步提供可验证输入。", { left: 58, top: 162, width: 800, height: 32 }, {
      fontSize: 20,
      color: C.muted,
    });

    const nodeLeft = 58;
    const nodeTop = 240;
    const nodeW = 126;
    const nodeH = 104;
    const gap = 22;
    const stages = [
      ["01", "感知", "SCADA / CMS"],
      ["02", "触发", "Alarm + Mission"],
      ["03", "协作", "专业 Agent"],
      ["04", "取证", "Evidence"],
      ["05", "决策", "候选方案"],
      ["06", "把关", "评审 + 审批"],
      ["07", "执行", "Work Order"],
      ["08", "沉淀", "Knowledge"],
    ];
    // Connectors first so arrows sit behind the nodes.
    for (let i = 0; i < stages.length - 1; i += 1) {
      const x = nodeLeft + i * (nodeW + gap) + nodeW + 2;
      addShape(slide, "rightArrow", { left: x, top: nodeTop + 43, width: gap - 4, height: 18 }, C.accent, "none", 0);
    }
    stages.forEach((stage, i) => {
      const x = nodeLeft + i * (nodeW + gap);
      addShape(slide, "roundRect", { left: x, top: nodeTop, width: nodeW, height: nodeH }, i === 7 ? C.accentSoft : C.panel, i === 7 ? C.accent : C.line, 1, undefined, 9);
      addText(slide, stage[0], { left: x + 13, top: nodeTop + 10, width: 44, height: 25 }, {
        fontSize: 14,
        bold: true,
        color: C.accentDark,
        typeface: FONT_LATIN,
      });
      addText(slide, stage[1], { left: x + 13, top: nodeTop + 40, width: nodeW - 26, height: 28 }, {
        fontSize: 22,
        bold: true,
        color: C.ink,
      });
      addText(slide, stage[2], { left: x + 13, top: nodeTop + 73, width: nodeW - 26, height: 22 }, {
        fontSize: 14,
        color: C.muted,
        typeface: FONT_LATIN,
      });
    });

    const calloutTop = 442;
    const calloutW = 350;
    const callouts = [
      ["类型化工具", "事实来自受限查询与确定性计算，写入动作只暴露领域命令。"],
      ["人工硬门禁", "方案必须经过多角色评审；高风险动作只有审批后才能执行。"],
      ["全链路审计", "工具输入输出、证据、决策、版本、耗时和错误都可追踪。"],
    ];
    callouts.forEach((item, i) => {
      const x = 58 + i * 405;
      addRule(slide, x, calloutTop, calloutW, i === 1 ? C.warning : C.accent, 4);
      addText(slide, item[0], { left: x, top: calloutTop + 22, width: calloutW, height: 34 }, {
        fontSize: 24,
        bold: true,
        color: C.ink,
      });
      addText(slide, item[1], { left: x, top: calloutTop + 70, width: calloutW, height: 82 }, {
        fontSize: 17,
        color: C.muted,
      });
    });
    addFooter(slide, 3);
    addNotes(slide,
      ["沿着箭头讲清主线：数据触发 Mission，多 Agent 产生证据和方案，人类批准后才进入工单，现场结果再沉淀为知识。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\docs\\agent-engineer-interview-project-introduction.md",
      ],
    );
  }

  // 04 — Product workspace.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "一个运营工作台覆盖从风场态势到现场闭环", "03 / 产品体验", 4);
    addText(slide, "首页同时回答：整个风场正在发生什么？AI 正在处理什么？", { left: 58, top: 162, width: 830, height: 34 }, {
      fontSize: 21,
      color: C.muted,
    });
    addShape(slide, "roundRect", { left: 58, top: 212, width: 830, height: 428 }, C.panel2, C.line, 1, undefined, 10);
    slide.images.add({
      blob: assetBytes.commandCenter,
      contentType: "image/png",
      alt: "WindOps 运营指挥中心概念界面",
      fit: "cover",
      position: { left: 58, top: 212, width: 830, height: 428 },
      crop: { left: 0.00, top: 0.02, right: 0.00, bottom: 0.02 },
      geometry: "roundRect",
      borderRadius: 10,
    });
    addMetricBlock(slide, 930, 212, 292, "10", "核心闭环页面", "运营中心、风场、风机、SCADA、告警、Agent、Mission、决策与工单", C.accent);
    addMetricBlock(slide, 930, 421, 292, "11", "专业 / 平台工作区", "健康、预测维护、资源、知识、报告、数字孪生、数据、模型与设置", C.warning);
    addText(slide, "统一主故事：WT-023", { left: 930, top: 603, width: 292, height: 34 }, {
      fontSize: 22,
      bold: true,
      color: C.accentDark,
    });
    addFooter(slide, 4);
    addNotes(slide,
      ["强调页面并非孤立展示：Dashboard、Mission、Decision、Work Order、Health 与 Knowledge 读取同一业务故事和服务器状态。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\docs\\design\\windops-operations-command-center-concept-v2.png",
      ],
    );
  }

  // 05 — Multi-agent design.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "多智能体的价值是职责隔离，而不是角色堆叠", "04 / AGENT 设计", 5);
    addText(slide, "演示工作区组织 22 个 Agent；生产候选以 11 个类型化业务工具约束真实行动。", { left: 58, top: 151, width: 990, height: 34 }, {
      fontSize: 20,
      color: C.muted,
    });
    addLane(slide, 1, "Decision Layer", "读取数据、形成证据、提出受约束方案", [
      "SCADA / 振动 / 历史案例分析",
      "健康度与 RUL 确定性计算",
      "生成 3 个候选维护方案",
      "输出 Evidence 与 Decision",
    ], 58, C.accent);
    addLane(slide, 2, "Review Layer", "工程、安全、资源与经济性独立评审", [
      "不同角色拥有不同权限",
      "每个结论必须引用公开证据",
      "不确定信息明确失败或升级",
      "人工批准 / 拒绝 / 退修 / 升级",
    ], 465, C.warning);
    addLane(slide, 3, "Execution Layer", "审批后执行，并以现场证据完成闭环", [
      "原子预留班组、船舶与备件",
      "按治理顺序完成现场任务",
      "URI + SHA-256 + measurement",
      "回写健康度并生成知识案例",
    ], 872, C.alert);
    addShape(slide, "roundRect", { left: 58, top: 620, width: 1164, height: 42 }, C.navy, C.navy, 1, undefined, 6);
    addText(slide, "工程价值 = 独立权限 + 独立验收标准 + 可追踪交接", { left: 78, top: 628, width: 1124, height: 26 }, {
      fontSize: 20,
      bold: true,
      color: C.white,
      alignment: "center",
    });
    addFooter(slide, 5);
    addNotes(slide,
      ["区分 UI 中的 Agent 组织与生产工具合同：多 Agent 不是为了增加角色名，而是为了把职责、权限和验收拆开。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\backend\\src\\windops_backend\\services\\seed.py",
        "C:\\coding\\project\\wind-agent\\backend\\src\\windops_backend\\agents\\tools.py",
      ],
    );
  }

  // 06 — Dual runtime architecture.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "双运行架构兼顾稳定演示与生产候选", "05 / 系统架构", 6);
    addText(slide, "共享前端领域契约，但数据来源、身份边界与执行可信度严格隔离。", { left: 58, top: 151, width: 980, height: 32 }, {
      fontSize: 20,
      color: C.muted,
    });

    // Directional arrows are laid down before the nodes.
    for (const x of [337, 945]) {
      addShape(slide, "downArrow", { left: x, top: 284, width: 28, height: 26 }, C.accent, "none", 0);
      addShape(slide, "downArrow", { left: x, top: 360, width: 28, height: 26 }, C.accent, "none", 0);
      addShape(slide, "downArrow", { left: x, top: 436, width: 28, height: 26 }, C.accent, "none", 0);
    }

    addShape(slide, "roundRect", { left: 58, top: 201, width: 560, height: 345 }, C.accentSoft, C.accent, 1, undefined, 10);
    addShape(slide, "roundRect", { left: 662, top: 201, width: 560, height: 345 }, C.panel, C.line, 1, undefined, 10);
    addText(slide, "DEMO · 可重复演示", { left: 82, top: 220, width: 510, height: 34 }, {
      fontSize: 25,
      bold: true,
      color: C.accentDark,
      typeface: FONT_LATIN,
    });
    addText(slide, "PRODUCTION CANDIDATE · 受治理执行", { left: 686, top: 220, width: 510, height: 34 }, {
      fontSize: 25,
      bold: true,
      color: C.ink,
      typeface: FONT_LATIN,
    });
    addArchitectureNode(slide, "React 19 运营工作区", 92, 265, 492, C.white, C.line, { bold: true });
    addArchitectureNode(slide, "Sites Worker API + D1", 92, 341, 492, C.white, C.line);
    addArchitectureNode(slide, "17-tool 确定性运行时", 92, 417, 492, C.white, C.line);
    addArchitectureNode(slide, "用途：稳定演示、截图与回归测试", 92, 493, 492, C.navy, C.navy, { color: C.white, bold: true });

    addArchitectureNode(slide, "Sites 身份网关 + 路由白名单", 696, 265, 492, C.white, C.line, { bold: true });
    addArchitectureNode(slide, "FastAPI + LangGraph + LiteLLM", 696, 341, 492, C.white, C.line);
    addArchitectureNode(slide, "PostgreSQL / TimescaleDB / pgvector", 696, 417, 238, C.white, C.line, { fontSize: 15 });
    addArchitectureNode(slide, "Redis / MinIO / Neo4j", 950, 417, 238, C.white, C.line, { fontSize: 15 });
    addArchitectureNode(slide, "用途：真实依赖下的可靠、可审计执行", 696, 493, 492, C.navy, C.navy, { color: C.white, bold: true });

    addShape(slide, "roundRect", { left: 58, top: 574, width: 1164, height: 78 }, C.warningSoft, C.warning, 1, undefined, 7);
    addText(slide, "运行边界", { left: 82, top: 593, width: 120, height: 30 }, {
      fontSize: 21,
      bold: true,
      color: C.warning,
    });
    addText(slide, "Demo 结果不等于生产 Agent 调用；生产候选仍需真实身份、模型供应商、现场系统与发布环境联合验收。", { left: 198, top: 590, width: 1000, height: 42 }, {
      fontSize: 18,
      color: C.ink,
      verticalAlignment: "middle",
    });
    addFooter(slide, 6);
    addNotes(slide,
      ["这一页主动说明诚实边界：双运行形态是架构选择，不应把 Demo 结果包装成生产执行。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\backend\\README.md",
      ],
    );
  }

  // 07 — Governance and reliability.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "关键动作由四道工程门禁共同约束", "06 / 工程治理", 7);
    addText(slide, "Prompt 负责推理引导；真正的权限、状态与提交由服务端控制。", { left: 58, top: 151, width: 900, height: 34 }, {
      fontSize: 20,
      color: C.muted,
    });

    const rows = [
      ["01", "状态机", "Mission、Decision、Approval、Work Order 的转换由服务端校验，模型文本不能伪造“已批准”。", C.accent],
      ["02", "工具与权限", "Pydantic / JSON Schema、租户与资产范围、最小权限工具；不提供任意 SQL、Shell 或万能写接口。", C.warning],
      ["03", "可靠执行", "Idempotency-Key、revision / CAS、transactional outbox、可恢复租约与 fencing token 共同处理重试和并发。", C.alert],
      ["04", "证据与人工", "Evidence → Decision → 多角色评审 → HITL；现场任务必须提交 URI、SHA-256 与结构化 measurement。", C.success],
    ];
    rows.forEach((row, i) => {
      const top = 208 + i * 103;
      addText(slide, row[0], { left: 58, top: top + 4, width: 70, height: 42 }, {
        fontSize: 31,
        bold: true,
        color: row[3],
        typeface: FONT_LATIN,
      });
      addText(slide, row[1], { left: 146, top, width: 190, height: 36 }, {
        fontSize: 24,
        bold: true,
        color: C.ink,
      });
      addText(slide, row[2], { left: 335, top, width: 600, height: 68 }, {
        fontSize: 17,
        color: C.muted,
      });
      addRule(slide, 146, top + 83, 790, C.line, 1);
    });

    addShape(slide, "roundRect", { left: 973, top: 207, width: 249, height: 410 }, C.navy, C.navy, 1, undefined, 9);
    addText(slide, "审计可见", { left: 999, top: 235, width: 197, height: 42 }, {
      fontSize: 28,
      bold: true,
      color: C.white,
    });
    addRule(slide, 999, 292, 58, C.accent, 4);
    const auditItems = ["工具输入 / 输出", "证据与来源引用", "模型与版本", "延迟、token 与错误", "审批与现场凭证"];
    auditItems.forEach((item, i) => {
      addShape(slide, "ellipse", { left: 1002, top: 330 + i * 46, width: 9, height: 9 }, C.accent, "none", 0);
      addText(slide, item, { left: 1022, top: 318 + i * 46, width: 170, height: 34 }, {
        fontSize: 16,
        color: C.white,
        verticalAlignment: "middle",
      });
    });
    addText(slide, "不保存或伪造\n隐藏 Chain-of-Thought", { left: 999, top: 553, width: 197, height: 52 }, {
      fontSize: 16,
      bold: true,
      color: C.warning,
    });
    addFooter(slide, 7);
    addNotes(slide,
      ["技术亮点不是模型会说什么，而是模型不能越过什么：状态机、工具合同、权限、幂等和证据门禁共同构成行动边界。"],
      [
        "C:\\coding\\project\\wind-agent\\docs\\agent-engineer-interview-project-introduction.md",
        "C:\\coding\\project\\wind-agent\\backend\\src\\windops_backend\\agents\\graph.py",
        "C:\\coding\\project\\wind-agent\\backend\\src\\windops_backend\\services\\agent_governance.py",
      ],
    );
  }

  // 08 — CARE v6 evidence.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "真实数据评估把模型效果纳入可发布的工程门禁", "07 / 数据与评估", 8);
    addText(slide, "CARE v6 路径覆盖数据合同、质量、真值隔离、离线评估与有界在线回放。", { left: 58, top: 151, width: 1000, height: 34 }, {
      fontSize: 20,
      color: C.muted,
    });
    addMetricBlock(slide, 58, 213, 350, "5,242,948", "数据行", "101 个 CSV，95 个事件；原始数据只读，不进入仓库。", C.accent);
    addMetricBlock(slide, 465, 213, 350, "36", "场内留一资产 fold", "覆盖 95 个事件；失败与不可评分也计入汇总。", C.warning);
    addMetricBlock(slide, 872, 213, 350, "281,249", "预测点", "预测先冻结，最终 evaluator 才能读取真值。", C.alert);

    addText(slide, "候选门禁结果", { left: 58, top: 470, width: 220, height: 34 }, {
      fontSize: 23,
      bold: true,
      color: C.ink,
    });
    addText(slide, "12 通过", { left: 58, top: 518, width: 160, height: 44 }, {
      fontSize: 31,
      bold: true,
      color: C.success,
    });
    addText(slide, "24 未通过", { left: 228, top: 518, width: 190, height: 44 }, {
      fontSize: 31,
      bold: true,
      color: C.alert,
    });
    addShape(slide, "rect", { left: 58, top: 571, width: 120, height: 18 }, C.success, "none", 0);
    addShape(slide, "rect", { left: 178, top: 571, width: 240, height: 18 }, C.alertSoft, "none", 0);
    addText(slide, "失败候选完整登记，不用删除样本换取更好指标。", { left: 58, top: 602, width: 400, height: 36 }, {
      fontSize: 16,
      color: C.muted,
    });

    const pipeline = [
      ["只读源数据", "授权位置"],
      ["合同与质量", "unknown / missing 失败关闭"],
      ["宽表 Parquet", "分块、列裁剪、有界内存"],
      ["LOAO 评估", "场内泛化，不宣称跨场"],
      ["有界回放", "prediction → Alarm → Mission"],
    ];
    pipeline.forEach((item, i) => {
      const left = 500 + i * 145;
      if (i < pipeline.length - 1) {
        addShape(slide, "rightArrow", { left: left + 117, top: 555, width: 24, height: 16 }, C.accent, "none", 0);
      }
    });
    pipeline.forEach((item, i) => {
      const left = 500 + i * 145;
      addShape(slide, "roundRect", { left, top: 493, width: 120, height: 126 }, i === 4 ? C.accentSoft : C.panel, i === 4 ? C.accent : C.line, 1, undefined, 8);
      addText(slide, item[0], { left: left + 10, top: 514, width: 100, height: 28 }, {
        fontSize: 18,
        bold: true,
        color: C.ink,
        alignment: "center",
      });
      addText(slide, item[1], { left: left + 10, top: 552, width: 100, height: 52 }, {
        fontSize: 13,
        color: C.muted,
        alignment: "center",
      });
    });
    addText(slide, "数据口径：仓库记录的 2026-08-27/29 本地候选与只读复核证据，不等同于生产上线。", { left: 500, top: 631, width: 722, height: 24 }, {
      fontSize: 13,
      color: C.faint,
      alignment: "right",
    });
    addFooter(slide, 8);
    addNotes(slide,
      ["CARE v6 让 Agent 与异常检测不只依赖手写 fixture；同时用真值隔离、失败关闭和版本化制品控制评估可信度。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\docs\\agent-engineer-interview-project-introduction.md",
      ],
    );
  }

  // 09 — WT-023 case.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    addSlideTitle(slide, "WT-023 展示从异常到闭环的完整业务价值", "08 / 业务案例", 9);
    addText(slide, "主轴承振动、温度与多变量异常共同触发 P1 事件。", { left: 58, top: 151, width: 750, height: 32 }, {
      fontSize: 20,
      color: C.muted,
    });
    addShape(slide, "roundRect", { left: 58, top: 210, width: 390, height: 164 }, C.panel, C.line, 1, undefined, 10);
    slide.images.add({
      blob: assetBytes.incident,
      contentType: "image/png",
      alt: "WT-023 P1 主轴承振动异常移动端事件卡片",
      fit: "contain",
      position: { left: 76, top: 225, width: 354, height: 134 },
      geometry: "roundRect",
      borderRadius: 7,
    });

    const signals = [
      ["振动 RMS", "4.81 mm/s", "阈值 4.5", C.alert],
      ["主轴承温度", "76.4°C", "阈值 75°C", C.warning],
      ["异常分数", "0.86", "阈值 0.65", C.accent],
    ];
    signals.forEach((item, i) => {
      const top = 406 + i * 66;
      addText(slide, item[0], { left: 58, top, width: 135, height: 28 }, {
        fontSize: 16,
        bold: true,
        color: C.ink,
      });
      addText(slide, item[1], { left: 192, top: top - 4, width: 135, height: 34 }, {
        fontSize: 22,
        bold: true,
        color: item[3],
        typeface: FONT_LATIN,
      });
      addText(slide, item[2], { left: 332, top, width: 116, height: 28 }, {
        fontSize: 14,
        color: C.faint,
        alignment: "right",
      });
      addRule(slide, 58, top + 37, 390, C.line, 1);
    });

    addShape(slide, "rect", { left: 523, top: 221, width: 3, height: 385 }, C.line, "none", 0);
    const steps = [
      ["A", "异常触发", "SCADA 样本、Alarm、Mission 与 outbox event 在同一事务提交。", C.alert],
      ["B", "协同诊断", "Agent 查询时序、振动、历史维护与相似案例，形成结构化 Evidence。", C.accent],
      ["C", "方案与审批", "生成 A / B / C 三个方案，多角色评审后由人工批准或退修。", C.warning],
      ["D", "现场闭环", "5 项任务逐项提交证据；健康度回写至 82，并生成知识案例。", C.success],
    ];
    steps.forEach((item, i) => {
      const top = 202 + i * 108;
      addShape(slide, "ellipse", { left: 506, top: top + 18, width: 36, height: 36 }, item[3], C.white, 3);
      addText(slide, item[0], { left: 506, top: top + 23, width: 36, height: 24 }, {
        fontSize: 16,
        bold: true,
        color: C.white,
        alignment: "center",
        typeface: FONT_LATIN,
      });
      addText(slide, item[1], { left: 566, top, width: 230, height: 32 }, {
        fontSize: 23,
        bold: true,
        color: C.ink,
      });
      addText(slide, item[2], { left: 566, top: top + 39, width: 635, height: 52 }, {
        fontSize: 17,
        color: C.muted,
      });
    });
    addShape(slide, "roundRect", { left: 506, top: 622, width: 696, height: 39 }, C.navy, C.navy, 1, undefined, 6);
    addText(slide, "展示的不是一次 LLM 回复，而是一条完整、可审计的业务状态变化。", { left: 526, top: 630, width: 656, height: 24 }, {
      fontSize: 18,
      bold: true,
      color: C.white,
      alignment: "center",
    });
    addFooter(slide, 9);
    addNotes(slide,
      ["WT-023 是贯穿页面的主故事。重点不是故障结论本身，而是从证据到审批、执行和知识沉淀的完整状态闭环。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\tests\\e2e\\__screenshots__\\dashboard-p1-incident-390.png",
      ],
    );
  }

  // 10 — Close and roadmap: two-column composition with image field.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.white;
    slide.images.add({
      blob: assetBytes.overview,
      contentType: "image/png",
      alt: "WindOps AI-Native 风电运维平台总览视觉",
      fit: "cover",
      position: { left: 662, top: 0, width: 618, height: 720 },
      crop: { left: 0.28, top: 0.03, right: 0.02, bottom: 0.03 },
    });
    addText(slide, "09 / 总结与下一步", { left: 58, top: 42, width: 300, height: 24 }, {
      fontSize: 15,
      bold: true,
      color: C.accentDark,
    });
    addText(slide, "从“可演示”\n走向“可验收”", { left: 58, top: 103, width: 540, height: 128 }, {
      fontSize: 52,
      bold: true,
      color: C.ink,
      name: "closing-title",
    });
    addText(slide, "当前已具备", { left: 58, top: 272, width: 210, height: 32 }, {
      fontSize: 23,
      bold: true,
      color: C.accentDark,
    });
    const ready = [
      "端到端异常处置闭环与统一业务状态",
      "受约束多 Agent、类型化工具与人工门禁",
      "Demo / Production Candidate 双运行边界",
      "CARE v6 数据评估与工程质量门禁",
    ];
    ready.forEach((item, i) => {
      addShape(slide, "ellipse", { left: 62, top: 326 + i * 45, width: 9, height: 9 }, C.success, "none", 0);
      addText(slide, item, { left: 83, top: 313 + i * 45, width: 510, height: 35 }, {
        fontSize: 17,
        color: C.ink,
        verticalAlignment: "middle",
      });
    });
    addRule(slide, 58, 508, 540, C.line, 1);
    addText(slide, "下一阶段", { left: 58, top: 531, width: 210, height: 32 }, {
      fontSize: 23,
      bold: true,
      color: C.warning,
    });
    addText(slide, "真实身份与模型供应商联调 · 现场 SCADA/CMS/EAM 接入 · 签名制品与集群准入 · 风场试点指标与 SOP 验收", { left: 58, top: 573, width: 540, height: 68 }, {
      fontSize: 17,
      color: C.muted,
    });
    addText(slide, "让 Agent 在工业现场可用、可控、可追责。", { left: 58, top: 655, width: 540, height: 34 }, {
      fontSize: 22,
      bold: true,
      color: C.accentDark,
    });
    addText(slide, "10", { left: 1150, top: 674, width: 72, height: 22 }, {
      fontSize: 14,
      bold: true,
      alignment: "right",
      color: C.white,
      typeface: FONT_LATIN,
    });
    addNotes(slide,
      ["结尾明确项目成熟度和下一步：当前是生产候选而非已上线系统，后续价值取决于真实依赖、现场系统与发布环境的联合验收。"],
      [
        "C:\\coding\\project\\wind-agent\\README.md",
        "C:\\coding\\project\\wind-agent\\docs\\demo-gap-audit.md",
        "C:\\coding\\project\\wind-agent\\public\\og.png",
      ],
    );
  }

  // Render every slide and preserve structural inspection artifacts.
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await deck.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(path.join(RENDER_DIR, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(RENDER_DIR, `${stem}.layout.json`), await layout.text(), "utf8");
  }
  const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
  await fs.writeFile(path.join(RENDER_DIR, "deck-montage.webp"), new Uint8Array(await montage.arrayBuffer()));
  const inspect = await deck.inspect({ kind: "slide,textbox,shape,image,notes", maxChars: 50000 });
  await fs.writeFile(path.join(RENDER_DIR, "inspect.ndjson"), inspect.ndjson, "utf8");

  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(FINAL_PPTX);
  console.log(JSON.stringify({ final: FINAL_PPTX, slideCount: deck.slides.items.length, renderDir: RENDER_DIR }));
}

buildDeck().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
