"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  BrainCircuit,
  ExternalLink,
  FileText,
  HeartPulse,
  Search,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  PLATFORM_SNAPSHOT_AT,
  modelKinds,
  modelRegistry,
  modelStatuses,
  type ModelKind,
  type ModelRegistryEntry,
  type ModelStatus,
} from "@/lib/platform-admin-data";
import styles from "./model-management-page.module.css";

type ModelEnvelope = {
  data: readonly ModelRegistryEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: true;
    readOnly: true;
    snapshotAt: string;
    realInferenceCount: number;
    embeddingBackedCount: number;
    disclosure: string;
  };
};

const initialEnvelope: ModelEnvelope = {
  data: modelRegistry,
  meta: {
    count: modelRegistry.length,
    total: modelRegistry.length,
    deterministic: true,
    readOnly: true,
    snapshotAt: PLATFORM_SNAPSHOT_AT,
    realInferenceCount: 0,
    embeddingBackedCount: 0,
    disclosure:
      "Registry availability describes demo capability, not the presence of trained weights or hosted inference.",
  },
};

const kindLabels: Readonly<Record<ModelKind, string>> = {
  anomaly: "异常检测",
  predictive: "预测维护",
  health: "健康评分",
  retrieval: "知识检索",
  report: "报告生成",
};

const kindIcons = {
  anomaly: Activity,
  predictive: BarChart3,
  health: HeartPulse,
  retrieval: BrainCircuit,
  report: FileText,
} as const;

export function ModelManagementPage() {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | ModelKind>("all");
  const [status, setStatus] = useState<"all" | ModelStatus>("all");
  const [selectedId, setSelectedId] = useState(modelRegistry[0]?.id ?? "");

  const endpoint = useMemo(() => {
    const parameters = new URLSearchParams();
    if (query.trim()) parameters.set("q", query.trim());
    if (kind !== "all") parameters.set("kind", kind);
    if (status !== "all") parameters.set("status", status);
    const suffix = parameters.toString();
    return `/api/model-registry${suffix ? `?${suffix}` : ""}`;
  }, [kind, query, status]);

  const registryQuery = useQuery({
    queryKey: ["model-registry", endpoint],
    queryFn: ({ signal }) => apiGet<ModelEnvelope>(endpoint, signal),
    initialData: endpoint === "/api/model-registry" ? initialEnvelope : undefined,
    initialDataUpdatedAt: 0,
    placeholderData: (previous) => previous,
  });

  const models = registryQuery.data?.data ?? [];
  const selected = models.find((model) => model.id === selectedId) ?? models[0] ?? null;

  return (
    <AppShell activePath="/models">
      <PageHeader
        eyebrow="MODEL GOVERNANCE"
        title="模型管理"
        description="审阅 WindOps 当前确定性评分、检索与文档生成能力，以及它们真实的运行边界。"
        breadcrumb={["平台管理", "模型管理"]}
        meta={
          <>
            <StatusBadge value="transparent" label="CAPABILITY DISCLOSURE" tone="warning" />
            <span className="page-meta-text">无训练权重 · 无托管推理 · 无真实 embedding</span>
          </>
        }
      />

      <section className={styles.disclosure} aria-label="模型能力披露">
        <ShieldAlert size={19} />
        <div>
          <strong>这是能力注册表，不是生产 ML 模型仓库</strong>
          <p>
            当前 5 项能力均可复现并有实际
            API/页面消费者，但没有训练模型、权重制品或外部推理调用；知识检索也没有连接向量数据库。
          </p>
        </div>
        <span>
          REAL INFERENCE <b>{registryQuery.data?.meta.realInferenceCount ?? 0}</b>
        </span>
        <span>
          EMBEDDING BACKED <b>{registryQuery.data?.meta.embeddingBackedCount ?? 0}</b>
        </span>
      </section>

      <section className={styles.kpis} aria-label="模型注册表摘要">
        <Card>
          <small>REGISTERED ENGINES</small>
          <strong>{registryQuery.data?.meta.total ?? modelRegistry.length}</strong>
          <em>确定性能力</em>
        </Card>
        <Card>
          <small>DEMO ONLY</small>
          <strong>{modelRegistry.filter((model) => model.status === "demo-only").length}</strong>
          <em>不可用于真实决策</em>
        </Card>
        <Card>
          <small>REAL INFERENCE</small>
          <strong>0</strong>
          <em>未配置模型服务</em>
        </Card>
        <Card>
          <small>MODEL ARTIFACTS</small>
          <strong>0</strong>
          <em>无权重与校准包</em>
        </Card>
      </section>

      <Card className={styles.toolbar}>
        <label className={styles.searchField}>
          <Search size={15} />
          <span className="sr-only">搜索模型能力</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={100}
            placeholder="搜索模型、输入或输出…"
          />
        </label>
        <label>
          <span>能力类型</span>
          <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
            <option value="all">全部类型</option>
            {modelKinds.map((value) => (
              <option value={value} key={value}>
                {kindLabels[value]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>状态</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as typeof status)}
          >
            <option value="all">全部状态</option>
            {modelStatuses.map((value) => (
              <option value={value} key={value}>
                {value === "available" ? "AVAILABLE" : "DEMO ONLY"}
              </option>
            ))}
          </select>
        </label>
        <span className={styles.resultCount}>
          {registryQuery.isFetching
            ? "同步中…"
            : `${models.length} / ${registryQuery.data?.meta.total ?? modelRegistry.length}`}
        </span>
      </Card>

      {registryQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          API 同步失败；继续显示最后一次确定性注册表快照。
        </div>
      ) : null}

      <section className={styles.workspace}>
        <Card className={styles.registryList}>
          <CardHeader
            eyebrow="REGISTRY"
            title="能力与版本"
            description="选择条目查看输入、输出、指标与限制。"
          />
          {registryQuery.isLoading ? (
            <div className={styles.loadingState}>正在读取模型注册表…</div>
          ) : models.length ? (
            <div className={styles.modelList}>
              {models.map((model) => {
                const Icon = kindIcons[model.kind];
                return (
                  <button
                    type="button"
                    data-selected={selected?.id === model.id}
                    onClick={() => setSelectedId(model.id)}
                    key={model.id}
                  >
                    <span className={styles.modelIcon}>
                      <Icon size={17} />
                    </span>
                    <span>
                      <strong>{model.name}</strong>
                      <small>
                        {model.id} · v{model.version}
                      </small>
                      <em>{model.runtime}</em>
                    </span>
                    <span className={styles.modelState}>
                      <StatusBadge
                        value={model.status}
                        label={model.status === "available" ? "AVAILABLE" : "DEMO ONLY"}
                        tone={model.status === "available" ? "success" : "warning"}
                        compact
                      />
                      <small>{kindLabels[model.kind]}</small>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配的能力"
              description="调整搜索词、能力类型或状态过滤后重试。"
            />
          )}
        </Card>

        <Card className={styles.detailPanel}>
          {selected ? (
            <>
              <CardHeader
                eyebrow={`${kindLabels[selected.kind]} · v${selected.version}`}
                title={selected.name}
                description={selected.runtime}
                action={<StatusBadge value="deterministic" label="DETERMINISTIC" tone="info" />}
              />

              <div className={styles.boundaries}>
                <span data-enabled={selected.realInference}>
                  <Sparkles size={14} />
                  <span>
                    <small>真实推理</small>
                    <strong>{selected.realInference ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.usesEmbeddings}>
                  <BrainCircuit size={14} />
                  <span>
                    <small>Embedding</small>
                    <strong>{selected.usesEmbeddings ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.artifactBacked}>
                  <FileText size={14} />
                  <span>
                    <small>模型制品</small>
                    <strong>{selected.artifactBacked ? "已登记" : "无"}</strong>
                  </span>
                </span>
              </div>

              <div className={styles.ioGrid}>
                <section>
                  <h3>输入</h3>
                  <ul>
                    {selected.inputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h3>输出</h3>
                  <ul>
                    {selected.outputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
              </div>

              <section className={styles.metrics}>
                <h3>指标与证据</h3>
                <div>
                  {selected.metrics.map((metric) => (
                    <span key={metric.label}>
                      <small>{metric.label}</small>
                      <strong>{metric.value}</strong>
                    </span>
                  ))}
                </div>
              </section>

              <section className={styles.limitation}>
                <ShieldAlert size={16} />
                <div>
                  <strong>能力边界</strong>
                  <p>{selected.limitation}</p>
                </div>
              </section>

              <Link className={styles.endpointLink} href={selected.endpoint}>
                打开只读接口 <ExternalLink size={13} />
              </Link>
            </>
          ) : (
            <EmptyState
              icon={<BrainCircuit size={20} />}
              title="选择一项能力"
              description="从左侧注册表选择能力以查看详情。"
            />
          )}
        </Card>
      </section>
    </AppShell>
  );
}
