"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Box, Database, Network, RefreshCw, Search, Unplug } from "lucide-react";

import {
  KnowledgeGraphChart,
  type KnowledgeGraphChartNode,
  type KnowledgeGraphChartRelationship,
} from "@/components/charts/knowledge-graph-chart";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { apiGet, OpenVigilApiError } from "@/lib/api-client";

import styles from "./knowledge-graph-page.module.css";

type GraphSummary = {
  readonly backend: string;
  readonly projectionId: string;
  readonly sourceRevision: string | null;
  readonly generatedAt: string | null;
  readonly nodeCount: number;
  readonly relationshipCount: number;
  readonly orphanNodeCount: number;
  readonly nodeTypeCounts: Record<string, number>;
};

type GraphSubgraph = {
  readonly rootUid: string;
  readonly nodes: readonly KnowledgeGraphChartNode[];
  readonly relationships: readonly KnowledgeGraphChartRelationship[];
};

type KnowledgeGraphWorkspaceResponse = {
  readonly data: { readonly summary: GraphSummary; readonly graph: GraphSubgraph };
  readonly meta: {
    readonly authoritativeSource: string;
    readonly projectionBackend: string;
    readonly consistency: string;
    readonly entityId: string;
    readonly depth: number;
  };
};

type HybridKnowledgeMatch = {
  readonly title?: string;
  readonly case_id?: string;
  readonly document_id?: string;
  readonly retrieval_method: string;
  readonly vectorScore: number;
  readonly graphScore: number;
  readonly fusedScore: number;
  readonly scopeMatched: boolean;
  readonly graphExpansion: {
    readonly failureModeIds: readonly string[];
    readonly evidenceIds: readonly string[];
    readonly caseIds: readonly string[];
    readonly paths: readonly unknown[];
  };
};

type HybridKnowledgeSearchResponse = {
  readonly data: {
    readonly query: string;
    readonly scopeEntityId: string | null;
    readonly answer: string;
    readonly answerMode: string;
    readonly matches: readonly HybridKnowledgeMatch[];
    readonly retrieval: {
      readonly vector: readonly string[];
      readonly graph: string;
      readonly fusion: string;
      readonly graphDepth: number;
    };
  };
};

function displayProperty(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value) ?? "—";
}

export function KnowledgeGraphPage({
  runtimeMode,
}: {
  readonly runtimeMode: "demo" | "production";
}) {
  const [entityId, setEntityId] = useState(runtimeMode === "production" ? "" : "WT-023");
  const [draftEntityId, setDraftEntityId] = useState(runtimeMode === "production" ? "" : "WT-023");
  const [depth, setDepth] = useState(4);
  const [selectedUid, setSelectedUid] = useState<string>();
  const [draftQuestion, setDraftQuestion] = useState(
    "主轴承振动和温升持续上升时，应检查哪些证据和历史案例？",
  );
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const graphQuery = useQuery({
    queryKey: ["knowledge-graph", entityId, depth],
    queryFn: ({ signal }) =>
      apiGet<KnowledgeGraphWorkspaceResponse>(
        `/api/knowledge-graph?entityId=${encodeURIComponent(entityId)}&depth=${depth}`,
        signal,
      ),
    enabled: entityId.length > 0,
    retry: false,
  });
  const searchQuery = useQuery({
    queryKey: ["knowledge-graph-search", entityId, submittedQuestion],
    queryFn: ({ signal }) =>
      apiGet<HybridKnowledgeSearchResponse>(
        `/api/knowledge-graph?mode=search&entityId=${encodeURIComponent(entityId)}&query=${encodeURIComponent(submittedQuestion)}`,
        signal,
      ),
    enabled: submittedQuestion.length >= 3,
    retry: false,
  });
  const response = graphQuery.data;
  const graph = response?.data.graph;
  const summary = response?.data.summary;

  useEffect(() => {
    if (!graph) return;
    const timer = window.setTimeout(() => setSelectedUid(graph.rootUid), 0);
    return () => window.clearTimeout(timer);
  }, [graph]);

  const selectedNode = useMemo(
    () => graph?.nodes.find((node) => node.uid === selectedUid),
    [graph, selectedUid],
  );
  const categories = useMemo(
    () => [...new Set(graph?.nodes.map((node) => node.type) ?? [])].sort(),
    [graph],
  );
  const handleSelect = useCallback((uid: string) => setSelectedUid(uid), []);
  const error = graphQuery.error instanceof OpenVigilApiError ? graphQuery.error : null;
  const searchError = searchQuery.error instanceof OpenVigilApiError ? searchQuery.error : null;

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/knowledge-graph">
      <PageHeader
        eyebrow="知识与数据"
        title="故障知识图谱"
        description="从 PostgreSQL 权威业务数据构建 Neo4j 可重建投影，追踪设备、异常、失效模式、证据、决策与工单闭环。"
        breadcrumb={["知识与数据", "故障知识图谱", entityId || "未选择实体"]}
        meta={
          <>
            <StatusBadge
              value={response?.meta.projectionBackend ?? "unavailable"}
              label={response?.meta.projectionBackend ?? "服务未连接"}
              tone={response ? "success" : graphQuery.isPending ? "info" : "critical"}
              pulse={Boolean(response)}
            />
            <StatusBadge value="postgresql" label="PostgreSQL 权威源" tone="neutral" />
            <span className="page-meta-text">不投影原始 SCADA，仅保留语义异常与证据</span>
          </>
        }
        actions={
          <form
            className={styles.controls}
            onSubmit={(event) => {
              event.preventDefault();
              const normalized = draftEntityId.trim();
              if (normalized) setEntityId(normalized);
            }}
          >
            <input
              aria-label="图谱实体 ID"
              value={draftEntityId}
              onChange={(event) => setDraftEntityId(event.target.value)}
              placeholder="WT-023 / ALARM-... / MISSION-..."
            />
            <select
              aria-label="关系深度"
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            >
              <option value={1}>1 跳</option>
              <option value={2}>2 跳</option>
              <option value={3}>3 跳</option>
              <option value={4}>4 跳</option>
            </select>
            <Button type="submit" variant="primary">
              <Search size={14} /> 查询
            </Button>
          </form>
        }
      />

      {error ? (
        <div className={styles.error} role="alert">
          <div>
            <strong>
              {error.code === "KNOWLEDGE_GRAPH_NOT_CONFIGURED"
                ? "图谱服务尚未配置"
                : "图谱服务不可用"}
            </strong>
            <small>{error.message}</small>
          </div>
          <Button onClick={() => void graphQuery.refetch()}>
            <RefreshCw size={14} /> 重试
          </Button>
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="图谱投影指标">
        <Card className={styles.metric}>
          <span>
            <Box size={14} /> 实体节点
          </span>
          <strong>{summary?.nodeCount ?? "—"}</strong>
          <small>
            {summary ? `${Object.keys(summary.nodeTypeCounts).length} 种节点类型` : "等待服务响应"}
          </small>
        </Card>
        <Card className={styles.metric}>
          <span>
            <Network size={14} /> 语义关系
          </span>
          <strong>{summary?.relationshipCount ?? "—"}</strong>
          <small>带来源、时间与版本属性</small>
        </Card>
        <Card className={styles.metric}>
          <span>
            <Unplug size={14} /> 孤立节点
          </span>
          <strong>{summary?.orphanNodeCount ?? "—"}</strong>
          <small>{summary?.orphanNodeCount === 0 ? "结构完整" : "需要对账检查"}</small>
        </Card>
        <Card className={styles.metric}>
          <span>
            <Database size={14} /> 投影修订
          </span>
          <strong>{summary?.sourceRevision?.slice(0, 8) ?? "—"}</strong>
          <small>
            {summary?.generatedAt
              ? new Date(summary.generatedAt).toLocaleString("zh-CN")
              : "未生成"}
          </small>
        </Card>
      </section>

      <Card className={styles.retrieval}>
        <CardHeader
          eyebrow="混合检索"
          title="向量召回 + 图关系扩展"
          description="先从 PostgreSQL/pgvector 召回文档与案例，再在 Neo4j 中沿失效模式、证据和闭环记录扩展并融合排序。"
        />
        <form
          className={styles.retrievalForm}
          onSubmit={(event) => {
            event.preventDefault();
            const normalized = draftQuestion.trim();
            if (normalized.length >= 3) setSubmittedQuestion(normalized);
          }}
        >
          <input
            aria-label="知识图谱混合检索问题"
            value={draftQuestion}
            onChange={(event) => setDraftQuestion(event.target.value)}
            placeholder="描述故障现象、设备范围或要复核的诊断……"
          />
          <Button type="submit" variant="primary" loading={searchQuery.isFetching}>
            <Search size={14} /> 检索并扩图
          </Button>
        </form>
        {searchError ? (
          <p className={styles.retrievalError} role="alert">
            {searchError.message}
          </p>
        ) : null}
        {searchQuery.data ? (
          <div className={styles.retrievalResult}>
            <p>{searchQuery.data.data.answer}</p>
            <div className={styles.matchGrid}>
              {searchQuery.data.data.matches.slice(0, 3).map((match, index) => (
                <article key={`${match.document_id ?? match.case_id ?? "match"}-${index}`}>
                  <span>
                    #{index + 1} · 融合 {match.fusedScore.toFixed(3)}
                  </span>
                  <strong>{match.title ?? match.case_id ?? "未命名证据"}</strong>
                  <small>
                    向量 {match.vectorScore.toFixed(3)} · 图 {match.graphScore.toFixed(3)} ·
                    {match.scopeMatched ? ` 命中 ${entityId}` : " 跨设备证据"}
                  </small>
                  <small>
                    {match.graphExpansion.failureModeIds.length} 个失效模式 ·
                    {match.graphExpansion.evidenceIds.length} 条证据 ·
                    {match.graphExpansion.paths.length} 条可解释路径
                  </small>
                </article>
              ))}
            </div>
            <small className={styles.retrievalMeta}>
              {searchQuery.data.data.retrieval.vector.join(" + ")} →
              {searchQuery.data.data.retrieval.graph} · {searchQuery.data.data.retrieval.fusion}
            </small>
          </div>
        ) : (
          <p className={styles.retrievalHint}>
            查询结果会显示向量分、图结构分、设备范围命中情况及可复核路径，不生成无证据结论。
          </p>
        )}
      </Card>

      <section className={styles.workspace}>
        <Card className={styles.canvas}>
          <CardHeader
            eyebrow="关系探索"
            title={entityId ? `${entityId} · ${depth} 跳子图` : "实体子图"}
            description={
              graph
                ? `${graph.nodes.length} 个实体 · ${graph.relationships.length} 条关系，可缩放、拖拽并点击检查。`
                : "等待图谱服务返回可视化数据。"
            }
            action={
              <Button
                size="sm"
                loading={graphQuery.isFetching}
                onClick={() => void graphQuery.refetch()}
              >
                <RefreshCw size={13} /> 刷新
              </Button>
            }
          />
          <div className={styles.canvasBody}>
            {graph?.nodes.length ? (
              <KnowledgeGraphChart
                nodes={graph.nodes}
                relationships={graph.relationships}
                rootUid={graph.rootUid}
                selectedUid={selectedUid}
                onSelect={handleSelect}
              />
            ) : (
              <EmptyState
                icon={<Network size={22} />}
                title={
                  entityId
                    ? graphQuery.isPending
                      ? "正在读取图谱"
                      : "暂无可展示的关系"
                    : "尚未选择实体"
                }
                description={
                  entityId
                    ? "启动 FastAPI、Neo4j 与 outbox worker 后，此处展示真实业务投影。"
                    : "在上方输入机组、告警或任务 ID，查询真实业务投影。"
                }
              />
            )}
          </div>
        </Card>

        <Card className={styles.inspector}>
          <CardHeader
            eyebrow="实体检查器"
            title={selectedNode?.entityId ?? "选择一个节点"}
            description="查看实体类型与可审计投影属性。"
          />
          <div className={styles.inspectorBody}>
            {selectedNode ? (
              <>
                <span className={styles.entityType}>{selectedNode.type}</span>
                <strong className={styles.entityId}>{selectedNode.uid}</strong>
                <dl className={styles.properties}>
                  {Object.entries(selectedNode.properties).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{displayProperty(value)}</dd>
                    </div>
                  ))}
                </dl>
                <div className={styles.legend} aria-label="当前子图节点类型">
                  {categories.map((category) => (
                    <span key={category}>
                      <i /> {category}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                icon={<Search size={20} />}
                title="尚未选择实体"
                description="点击图中的节点后查看属性。"
              />
            )}
          </div>
        </Card>
      </section>
    </AppShell>
  );
}
