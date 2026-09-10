import {
  SCADA_ARCHIVE_METRICS,
  SCADA_ARCHIVE_TOTAL,
  alarmArchive,
  failureCases,
  historicalWorkOrders,
} from "./archive-data";
import { turbines, windFarm } from "./farm-data";
import { healthAssessments } from "./health-data";
import { knowledgeDocuments } from "./knowledge-data";
import { activityEvents, alarms, missions, workOrders } from "./operations-data";
import { scadaSeries, subsystemHealth } from "./telemetry-data";

export const PLATFORM_SNAPSHOT_AT = "2026-08-13T10:30:00+08:00";

export const dataCatalogCategories = ["live", "archive", "api", "schema", "benchmark"] as const;
export const dataCatalogStatuses = ["ready", "demo", "read-only"] as const;

export type DataCatalogCategory = (typeof dataCatalogCategories)[number];
export type DataCatalogStatus = (typeof dataCatalogStatuses)[number];

export interface DataCatalogEntry {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly category: DataCatalogCategory;
  readonly status: DataCatalogStatus;
  readonly recordCount: number;
  readonly schemaObjectCount: number;
  readonly freshness: string;
  readonly quality: string;
  readonly retention: string;
  readonly source: string;
  readonly queryHref: string;
  readonly queryLabel: string;
  readonly deterministic: boolean;
  readonly readOnly: boolean;
}

export interface CatalogSensor {
  readonly id: string;
  readonly metric: string;
  readonly unit: string;
  readonly source: "live-and-archive" | "schema-only";
  readonly queryHref: string | null;
}

const sensorsBySubsystem: Readonly<Record<string, readonly Omit<CatalogSensor, "id">[]>> = {
  blades: [
    {
      metric: "blade-pitch",
      unit: "°",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=blade-pitch&limit=32",
    },
  ],
  hub: [
    {
      metric: "hub-temperature",
      unit: "°C",
      source: "schema-only",
      queryHref: null,
    },
  ],
  "main-shaft": [
    {
      metric: "rotor-speed",
      unit: "rpm",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=rotor-speed&limit=32",
    },
  ],
  "main-bearing": [
    {
      metric: "main-bearing-temperature",
      unit: "°C",
      source: "live-and-archive",
      queryHref:
        "/api/scada-measurements?turbineId=WT-023&metric=main-bearing-temperature&limit=32",
    },
    {
      metric: "main-bearing-vibration-rms",
      unit: "mm/s",
      source: "live-and-archive",
      queryHref:
        "/api/scada-measurements?turbineId=WT-023&metric=main-bearing-vibration-rms&limit=32",
    },
  ],
  gearbox: [
    {
      metric: "gearbox-oil-temperature",
      unit: "°C",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=gearbox-oil-temperature&limit=32",
    },
  ],
  generator: [
    {
      metric: "generator-speed",
      unit: "rpm",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=generator-speed&limit=32",
    },
    {
      metric: "generator-temperature",
      unit: "°C",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=generator-temperature&limit=32",
    },
  ],
  converter: [
    {
      metric: "active-power",
      unit: "MW",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=active-power&limit=32",
    },
    {
      metric: "reactive-power",
      unit: "Mvar",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=reactive-power&limit=32",
    },
  ],
  yaw: [
    {
      metric: "yaw-error",
      unit: "°",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=yaw-error&limit=32",
    },
    {
      metric: "wind-direction",
      unit: "°",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=wind-direction&limit=32",
    },
  ],
  pitch: [
    {
      metric: "pitch-hydraulic-pressure",
      unit: "bar",
      source: "schema-only",
      queryHref: null,
    },
  ],
  tower: [
    {
      metric: "tower-acceleration",
      unit: "m/s²",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=tower-acceleration&limit=32",
    },
    {
      metric: "nacelle-temperature",
      unit: "°C",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=nacelle-temperature&limit=32",
    },
  ],
  foundation: [
    {
      metric: "foundation-inclination",
      unit: "°",
      source: "schema-only",
      queryHref: null,
    },
  ],
  electrical: [
    {
      metric: "grid-voltage",
      unit: "kV",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=grid-voltage&limit=32",
    },
    {
      metric: "grid-frequency",
      unit: "Hz",
      source: "live-and-archive",
      queryHref: "/api/scada-measurements?turbineId=WT-023&metric=grid-frequency&limit=32",
    },
  ],
};

export const schemaObjects = Object.freeze([
  "wind_farms",
  "wind_turbines",
  "subsystems",
  "sensors",
  "scada_measurements",
  "alarms",
  "health_assessments",
  "agents",
  "agent_skills",
  "agent_tools",
  "missions",
  "mission_tasks",
  "evidence",
  "decisions",
  "approvals",
  "work_orders",
  "spare_parts",
  "work_order_parts",
  "inventory_reservations",
  "crews",
  "vessels",
  "maintenance_tools",
  "resource_assignments",
  "maintenance_records",
  "knowledge_documents",
  "knowledge_passages",
  "failure_cases",
  "agent_executions",
  "activity_events",
  "workflow_instances",
  "workflow_tasks",
  "workflow_audit_events",
  "workflow_idempotency",
] as const);

export const assetCatalogHierarchy = Object.freeze({
  farm: {
    id: windFarm.id,
    name: windFarm.name,
    turbineCount: turbines.length,
    capacityMW: windFarm.totalCapacityMW,
  },
  focusTurbine: {
    id: "WT-023",
    model: turbines[22]?.model ?? "GW165-6.0MW",
    healthScore: turbines[22]?.healthScore ?? 68,
  },
  subsystems: Object.freeze(
    subsystemHealth.map((subsystem) =>
      Object.freeze({
        id: subsystem.id,
        key: subsystem.key,
        name: subsystem.name,
        healthScore: subsystem.healthScore,
        state: subsystem.state,
        sensors: Object.freeze(
          (sensorsBySubsystem[subsystem.key] ?? []).map((sensor, index) =>
            Object.freeze({
              ...sensor,
              id: `SENSOR-WT-023-${subsystem.key.toUpperCase()}-${String(index + 1).padStart(2, "0")}`,
            }),
          ),
        ),
      }),
    ),
  ),
});

export const dataCatalog: readonly DataCatalogEntry[] = Object.freeze([
  {
    id: "DATA-LIVE-SCADA",
    name: "WT-023 实时 SCADA 快照",
    description: "16 条测点序列；WebSocket 发送可复现的演示帧。",
    category: "live",
    status: "demo",
    recordCount: scadaSeries.reduce((total, series) => total + series.points.length, 0),
    schemaObjectCount: 2,
    freshness: "5 秒演示帧",
    quality: "良好 / 不确定标记；非生产遥测",
    retention: "客户端会话窗口",
    source: "telemetry-data 演示数据",
    queryHref: "/api/scada-history?turbineId=WT-023&range=24h",
    queryLabel: "查询历史",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-LIVE-ALARMS",
    name: "实时告警工作集",
    description: "当前运营告警、AI 处理状态与 Mission 关联。",
    category: "live",
    status: "demo",
    recordCount: alarms.length,
    schemaObjectCount: 2,
    freshness: "确定性事件流",
    quality: "跨域引用完整性校验",
    retention: "演示快照",
    source: "operations-data 演示数据",
    queryHref: "/api/alarms",
    queryLabel: "查询告警",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-LIVE-AGENT-EVENTS",
    name: "Agent 活动事件",
    description: "Mission 执行时间线与工具调用可观测事件。",
    category: "live",
    status: "demo",
    recordCount: activityEvents.length,
    schemaObjectCount: 2,
    freshness: "确定性事件流",
    quality: "事件 ID 与 Mission 链接校验",
    retention: "演示快照",
    source: "operations-data 演示数据",
    queryHref: "/api/agent-events",
    queryLabel: "查询事件",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-ARCHIVE-SCADA",
    name: "SCADA 逻辑归档",
    description: "64 台机组 × 16 指标 × 128 个采样点，按页确定性生成。",
    category: "archive",
    status: "ready",
    recordCount: SCADA_ARCHIVE_TOTAL,
    schemaObjectCount: 3,
    freshness: "2026-08-13 10:30 快照",
    quality: "良好 / 不确定 / 异常质量标记",
    retention: "128 × 15 分钟演示窗口",
    source: "archive-data 逻辑归档",
    queryHref: "/api/scada-measurements?limit=100",
    queryLabel: "分页查询",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-ARCHIVE-ALARMS",
    name: "告警历史归档",
    description: "跨机组历史告警与处置结果。",
    category: "archive",
    status: "ready",
    recordCount: alarmArchive.length,
    schemaObjectCount: 1,
    freshness: "2026-08-13 快照",
    quality: "机组与 Mission 引用校验",
    retention: "演示历史全集",
    source: "archive-data 演示数据",
    queryHref: "/api/alarms?includeArchived=true",
    queryLabel: "查询归档",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-ARCHIVE-WORK-ORDERS",
    name: "历史维护工单",
    description: "已完成维护、停机与成本记录。",
    category: "archive",
    status: "ready",
    recordCount: historicalWorkOrders.length,
    schemaObjectCount: 4,
    freshness: "2026-08-13 快照",
    quality: "资产与失败案例引用校验",
    retention: "演示历史全集",
    source: "archive-data 演示数据",
    queryHref: "/api/work-orders?includeHistorical=true",
    queryLabel: "查询工单",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-ARCHIVE-FAILURES",
    name: "闭环故障案例",
    description: "症状、根因、措施、损失和关联工单案例。",
    category: "archive",
    status: "ready",
    recordCount: failureCases.length,
    schemaObjectCount: 2,
    freshness: "2026-08-13 快照",
    quality: "关联工单完整性校验",
    retention: "演示历史全集",
    source: "archive-data 演示数据",
    queryHref: "/api/failure-cases",
    queryLabel: "查询案例",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-API-ASSETS",
    name: "资产目录 API",
    description: "风场、64 台风机和机组详情读取接口。",
    category: "api",
    status: "ready",
    recordCount: turbines.length + 1,
    schemaObjectCount: 4,
    freshness: "请求时读取快照",
    quality: "严格资产 ID 校验",
    retention: "不缓存",
    source: "同源 Worker API",
    queryHref: "/api/turbines",
    queryLabel: "打开接口",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-API-MISSIONS",
    name: "Mission 与执行 API",
    description: "Mission、人工审批工作流和关联工单视图。",
    category: "api",
    status: "ready",
    recordCount: missions.length + workOrders.length,
    schemaObjectCount: 10,
    freshness: "请求时叠加工作流状态",
    quality: "修订号与审计事件约束",
    retention: "响应不缓存；D1 保留审计",
    source: "同源 Worker API",
    queryHref: "/api/missions",
    queryLabel: "打开接口",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-API-HEALTH",
    name: "健康评估 API",
    description: "64 台机组的健康、风险、RUL 与趋势读取接口。",
    category: "api",
    status: "demo",
    recordCount: healthAssessments.length,
    schemaObjectCount: 2,
    freshness: "2026-08-13 快照",
    quality: "确定性公式；非真实 ML 推理",
    retention: "演示快照",
    source: "health-data 确定性演示数据",
    queryHref: "/api/health-assessments",
    queryLabel: "打开接口",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-API-KNOWLEDGE",
    name: "知识文档 API",
    description: "手册、程序、标准、报告与引用元数据。",
    category: "api",
    status: "demo",
    recordCount: knowledgeDocuments.length,
    schemaObjectCount: 2,
    freshness: "2026-08-13 快照",
    quality: "词法匹配与人工策展加权；无向量检索",
    retention: "演示快照",
    source: "knowledge-data 演示数据",
    queryHref: "/api/knowledge-documents",
    queryLabel: "打开接口",
    deterministic: true,
    readOnly: true,
  },
  {
    id: "DATA-SCHEMA-REGISTRY",
    name: "D1 运营数据模型注册表",
    description: "资产、遥测、Agent、工作流、资源与知识域逻辑对象。",
    category: "schema",
    status: "read-only",
    recordCount: schemaObjects.length,
    schemaObjectCount: schemaObjects.length,
    freshness: "随版本构建",
    quality: "Drizzle 声明与迁移约束",
    retention: "版本控制",
    source: "db/schema.ts 声明",
    queryHref: "/api/data-catalog?category=schema",
    queryLabel: "查看对象",
    deterministic: true,
    readOnly: true,
  },
] as const);

export interface DataCatalogQuery {
  readonly query?: string;
  readonly category?: DataCatalogCategory | null;
  readonly status?: DataCatalogStatus | null;
}

export function queryDataCatalog(options: DataCatalogQuery = {}): readonly DataCatalogEntry[] {
  const query = options.query?.trim().toLocaleLowerCase("zh-CN") ?? "";
  return dataCatalog.filter(
    (entry) =>
      (!options.category || entry.category === options.category) &&
      (!options.status || entry.status === options.status) &&
      (!query ||
        `${entry.id} ${entry.name} ${entry.description} ${entry.source}`
          .toLocaleLowerCase("zh-CN")
          .includes(query)),
  );
}

export const modelKinds = ["anomaly", "predictive", "health", "retrieval", "report"] as const;
export const modelStatuses = ["available", "demo-only"] as const;
export type ModelKind = (typeof modelKinds)[number];
export type ModelStatus = (typeof modelStatuses)[number];

export interface ModelRegistryEntry {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly kind: ModelKind;
  readonly status: ModelStatus;
  readonly runtime: string;
  readonly inputs: readonly string[];
  readonly outputs: readonly string[];
  readonly metrics: readonly { readonly label: string; readonly value: string }[];
  readonly realInference: boolean;
  readonly usesEmbeddings: boolean;
  readonly artifactBacked: boolean;
  readonly endpoint: string;
  readonly limitation: string;
  readonly deterministic: boolean;
  readonly updatedAt: string;
  readonly lifecycleStatus?: string;
  readonly artifactSha256?: string;
  readonly deployments?: readonly {
    readonly id: string;
    readonly status: string;
    readonly targetId: string;
    readonly trafficPercent: number;
    readonly activatedAt: string | null;
  }[];
}

export const modelRegistry: readonly ModelRegistryEntry[] = Object.freeze([
  {
    id: "MODEL-ANOMALY-DETERMINISTIC",
    name: "SCADA 多变量异常评分器",
    version: "demo-1.3.0",
    kind: "anomaly",
    status: "demo-only",
    runtime: "TypeScript 确定性信号生成与阈值标记",
    inputs: ["16 个 SCADA 指标", "机组编号", "采样序号"],
    outputs: ["异常标记", "质量标记", "趋势事件"],
    metrics: [
      { label: "指标覆盖", value: `${SCADA_ARCHIVE_METRICS.length}` },
      { label: "可复现", value: "100%" },
      { label: "验证集性能", value: "未评估" },
    ],
    realInference: false,
    usesEmbeddings: false,
    artifactBacked: false,
    endpoint: "/api/scada-measurements?limit=100",
    limitation: "没有训练模型、权重文件或线上推理服务；异常由固定公式与阈值生成。",
    deterministic: true,
    updatedAt: PLATFORM_SNAPSHOT_AT,
  },
  {
    id: "MODEL-PREDICTIVE-RISK",
    name: "失效概率与 RUL 评估器",
    version: "demo-1.1.0",
    kind: "predictive",
    status: "demo-only",
    runtime: "TypeScript 资产状态惩罚公式",
    inputs: ["健康分", "告警数", "机组状态", "资产序号"],
    outputs: ["30 天失效概率", "剩余寿命天数", "风险等级"],
    metrics: [
      { label: "资产覆盖", value: `${healthAssessments.length}` },
      { label: "输出范围", value: "受显式边界约束" },
      { label: "真实预测误差", value: "未评估" },
    ],
    realInference: false,
    usesEmbeddings: false,
    artifactBacked: false,
    endpoint: "/api/predictive-assessments",
    limitation: "RUL 与概率是演示公式结果，不能用于真实检修或安全决策。",
    deterministic: true,
    updatedAt: PLATFORM_SNAPSHOT_AT,
  },
  {
    id: "MODEL-HEALTH-SCORE",
    name: "风机健康度评分器",
    version: "demo-2.0.0",
    kind: "health",
    status: "demo-only",
    runtime: "TypeScript 固定权重与状态映射",
    inputs: ["资产快照", "告警计数", "子系统状态"],
    outputs: ["健康分", "健康状态", "趋势", "主要发现"],
    metrics: [
      { label: "资产覆盖", value: `${turbines.length}` },
      { label: "分值范围", value: "0–100" },
      { label: "校准数据", value: "无" },
    ],
    realInference: false,
    usesEmbeddings: false,
    artifactBacked: false,
    endpoint: "/api/health-assessments",
    limitation: "评分来自确定性夹具，不代表经过现场数据校准的健康模型。",
    deterministic: true,
    updatedAt: PLATFORM_SNAPSHOT_AT,
  },
  {
    id: "MODEL-KNOWLEDGE-PASSAGE",
    name: "知识段落检索与引用排序",
    version: "demo-1.2.0",
    kind: "retrieval",
    status: "demo-only",
    runtime: "正文词项、领域短语与确定性 CJK n-gram 排序",
    inputs: ["问题文本", "机组 ID", "Mission ID", "passage 正文"],
    outputs: ["排序 passage", "页码引用", "证据 ID", "回答摘要"],
    metrics: [
      { label: "文档数", value: `${knowledgeDocuments.length}` },
      { label: "检索模式", value: "deterministic-keyword-demo" },
      { label: "向量索引", value: "未连接" },
    ],
    realInference: false,
    usesEmbeddings: false,
    artifactBacked: false,
    endpoint: "/api/knowledge-assistant",
    limitation:
      "文档的 vectorized 元数据不会触发真实 embedding；当前实现没有向量数据库或生成式模型调用。",
    deterministic: true,
    updatedAt: PLATFORM_SNAPSHOT_AT,
  },
  {
    id: "MODEL-REPORT-COMPOSER",
    name: "运营报告组合器",
    version: "1.0.0",
    kind: "report",
    status: "available",
    runtime: "TypeScript 模板与工作流快照组合",
    inputs: ["运营夹具", "工作流 revision", "审计事件"],
    outputs: ["报告预览", "PDF", "DOCX"],
    metrics: [
      { label: "生成模式", value: "模板化" },
      { label: "审计关联", value: "revision-guarded" },
      { label: "语言模型", value: "未调用" },
    ],
    realInference: false,
    usesEmbeddings: false,
    artifactBacked: false,
    endpoint: "/api/reports",
    limitation: "报告是可用的确定性文档生成能力，但不是大模型生成或总结服务。",
    deterministic: true,
    updatedAt: PLATFORM_SNAPSHOT_AT,
  },
]);

export interface ModelRegistryQuery {
  readonly query?: string;
  readonly kind?: ModelKind | null;
  readonly status?: ModelStatus | null;
}

export function queryModelRegistry(
  options: ModelRegistryQuery = {},
): readonly ModelRegistryEntry[] {
  const query = options.query?.trim().toLocaleLowerCase("zh-CN") ?? "";
  return modelRegistry.filter(
    (model) =>
      (!options.kind || model.kind === options.kind) &&
      (!options.status || model.status === options.status) &&
      (!query ||
        `${model.id} ${model.name} ${model.runtime} ${model.inputs.join(" ")} ${model.outputs.join(" ")}`
          .toLocaleLowerCase("zh-CN")
          .includes(query)),
  );
}

export interface SystemStatusSnapshot {
  readonly runtime: {
    readonly application: "WindOps";
    readonly framework: "vinext / React Server Components";
    readonly execution: "Cloudflare Worker-compatible ESM";
    readonly apiCachePolicy: "no-store";
  };
  readonly persistence: {
    readonly d1Binding: "bound" | "not-bound";
    readonly workflowStore: "d1" | "ephemeral";
    readonly workflowWritable: boolean;
    readonly workflowRevision: number;
    readonly fixtureCatalog: "read-only";
  };
  readonly connections: readonly {
    readonly id: string;
    readonly label: string;
    readonly state: "pass" | "limited";
    readonly check: string;
    readonly detail: string;
  }[];
  readonly websockets: readonly {
    readonly endpoint: string;
    readonly channel: string;
    readonly mode: "deterministic-demo-stream";
  }[];
  readonly identity: {
    readonly mode: "server-demo-principal";
    readonly authenticated: false;
    readonly authorization: "server allow-list by action";
    readonly productionSso: "not-configured";
  };
  readonly theme: {
    readonly options: readonly ["light", "dark", "system"];
    readonly persistence: "browser-local windops-theme";
    readonly serverWrite: false;
  };
  readonly dataPolicies: readonly {
    readonly id: string;
    readonly scope: string;
    readonly policy: string;
    readonly enforcement: string;
  }[];
  readonly security: {
    readonly environmentValuesExposed: false;
    readonly secretNamesExposed: false;
    readonly diagnosticDetail: "status-only";
  };
  readonly integrity: {
    readonly valid: boolean;
    readonly errorCount: number;
  };
}

export interface SystemStatusInput {
  readonly d1Bound: boolean;
  readonly workflowStore: "d1" | "ephemeral";
  readonly workflowWritable: boolean;
  readonly workflowRevision: number;
  readonly integrityErrorCount: number;
}

export function buildSystemStatusSnapshot(input: SystemStatusInput): SystemStatusSnapshot {
  const snapshot: SystemStatusSnapshot = {
    runtime: {
      application: "WindOps",
      framework: "vinext / React Server Components",
      execution: "Cloudflare Worker-compatible ESM",
      apiCachePolicy: "no-store",
    },
    persistence: {
      d1Binding: input.d1Bound ? "bound" : "not-bound",
      workflowStore: input.workflowStore,
      workflowWritable: input.workflowWritable,
      workflowRevision: input.workflowRevision,
      fixtureCatalog: "read-only",
    },
    connections: [
      {
        id: "worker-runtime",
        label: "Worker API 运行时",
        state: "pass",
        check: "进程内路由执行",
        detail: "系统诊断路由已在当前 Worker 请求中执行。",
      },
      {
        id: "d1-workflow",
        label: "D1 工作流存储",
        state: input.d1Bound && input.workflowWritable ? "pass" : "limited",
        check: "绑定与工作流存储能力",
        detail:
          input.d1Bound && input.workflowWritable
            ? "D1 绑定可用，工作流支持持久化写入。"
            : "当前未绑定可写 D1；工作流使用临时只读基线。",
      },
      {
        id: "websocket-contracts",
        label: "WebSocket 路由",
        state: "pass",
        check: "已声明同源路由契约",
        detail: "三条演示流路由已声明；此诊断不伪造浏览器握手或外部网络探测。",
      },
      {
        id: "domain-integrity",
        label: "领域演示数据完整性",
        state: input.integrityErrorCount === 0 ? "pass" : "limited",
        check: "引用完整性审计",
        detail:
          input.integrityErrorCount === 0
            ? "资产、Mission、告警、工单和知识引用校验通过。"
            : `检测到 ${input.integrityErrorCount} 个引用完整性问题。`,
      },
    ],
    websockets: [
      { endpoint: "/ws/scada", channel: "SCADA 测量值", mode: "deterministic-demo-stream" },
      { endpoint: "/ws/alarms", channel: "告警事件", mode: "deterministic-demo-stream" },
      {
        endpoint: "/ws/agent-events",
        channel: "Agent 执行事件",
        mode: "deterministic-demo-stream",
      },
    ],
    identity: {
      mode: "server-demo-principal",
      authenticated: false,
      authorization: "server allow-list by action",
      productionSso: "not-configured",
    },
    theme: {
      options: ["light", "dark", "system"],
      persistence: "browser-local windops-theme",
      serverWrite: false,
    },
    dataPolicies: [
      {
        id: "POLICY-API-CACHE",
        scope: "所有 JSON API",
        policy: "不缓存响应",
        enforcement: "cache-control: no-store",
      },
      {
        id: "POLICY-FIXTURE",
        scope: "资产与历史演示目录",
        policy: "只读、确定性、版本随构建",
        enforcement: "无写接口",
      },
      {
        id: "POLICY-WORKFLOW",
        scope: "WT-023 审批与工单工作流",
        policy: "revision、幂等键和审计事件约束",
        enforcement: input.d1Bound ? "D1 事务存储" : "临时只读降级基线",
      },
      {
        id: "POLICY-THEME",
        scope: "显示主题",
        policy: "仅保存在当前浏览器",
        enforcement: "localStorage: windops-theme",
      },
    ],
    security: {
      environmentValuesExposed: false,
      secretNamesExposed: false,
      diagnosticDetail: "status-only",
    },
    integrity: {
      valid: input.integrityErrorCount === 0,
      errorCount: input.integrityErrorCount,
    },
  };
  return Object.freeze(snapshot);
}

export const systemStatusFallback = buildSystemStatusSnapshot({
  d1Bound: false,
  workflowStore: "ephemeral",
  workflowWritable: false,
  workflowRevision: 0,
  integrityErrorCount: 0,
});
