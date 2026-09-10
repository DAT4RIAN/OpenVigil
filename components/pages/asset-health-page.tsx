"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  CircleGauge,
  Filter,
  HeartPulse,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { Button, Card, CardHeader, EmptyState, Progress } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import { turbines, windFarm } from "@/lib/farm-data";
import { healthAssessments } from "@/lib/health-data";
import { subsystemHealth } from "@/lib/telemetry-data";
import type { HealthAssessment } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { localizedStatusLabel } from "@/lib/ui-localization";

type HealthResponse = {
  data: readonly HealthAssessment[];
  meta: {
    count: number;
    total: number;
    snapshotAt: string;
    predictionProvider?: string | null;
    deterministic?: boolean;
  };
};

const trendLabel = {
  improving: "改善",
  stable: "稳定",
  declining: "下降",
} as const;

const stateLabel = {
  healthy: "健康",
  watch: "关注",
  degraded: "退化",
  critical: "严重",
  maintenance: "维护",
  offline: "离线",
} as const;

export function AssetHealthPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const workflow = useDemoWorkflow();
  const [selectedId, setSelectedId] = useState(runtimeMode === "demo" ? "WT-023" : "");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "at-risk" | "declining">("all");
  const healthQuery = useQuery({
    queryKey: ["health-assessments", runtimeMode],
    queryFn: ({ signal }) => apiGet<HealthResponse>("/api/health-assessments", signal),
    initialData:
      runtimeMode === "demo"
        ? {
            data: healthAssessments,
            meta: {
              count: healthAssessments.length,
              total: healthAssessments.length,
              snapshotAt: windFarm.lastUpdatedAt,
            },
          }
        : undefined,
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    const available = healthQuery.data?.data ?? [];
    const nextId =
      turbineId && available.some((item) => item.turbineId === turbineId)
        ? turbineId
        : available[0]?.turbineId;
    if (!nextId) return;
    const timer = window.setTimeout(() => setSelectedId(nextId), 0);
    return () => window.clearTimeout(timer);
  }, [healthQuery.data]);

  const assessments = useMemo(
    () =>
      (healthQuery.data?.data ?? []).map((assessment) =>
        runtimeMode === "demo" &&
        assessment.turbineId === "WT-023" &&
        workflow.workOrderStatus === "completed"
          ? {
              ...assessment,
              healthScore: workflow.turbineHealthScore,
              state: "watch" as const,
              trend: "improving" as const,
              riskLevel: "medium" as const,
              anomalyScore: 0.42,
              primaryFinding: "现场复测后振动与温升回落，继续趋势观察",
            }
          : assessment,
      ),
    [healthQuery.data, runtimeMode, workflow.turbineHealthScore, workflow.workOrderStatus],
  );

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return assessments.filter(
      (assessment) =>
        (!normalized ||
          `${assessment.turbineId} ${assessment.primaryFinding}`
            .toLowerCase()
            .includes(normalized)) &&
        (filter === "all" ||
          (filter === "at-risk" && ["critical", "high"].includes(assessment.riskLevel)) ||
          (filter === "declining" && assessment.trend === "declining")),
    );
  }, [assessments, filter, query]);

  const selected =
    assessments.find((assessment) => assessment.turbineId === selectedId) ?? assessments[0];
  if (!selected) {
    return (
      <AppShell runtimeMode={runtimeMode} activePath="/health">
        <EmptyState
          icon={<HeartPulse size={24} />}
          title={healthQuery.isLoading ? "正在读取设备健康" : "设备健康数据不可用"}
          description={
            healthQuery.isError
              ? "权威健康服务当前不可用，生产模式不会回退到演示评估。"
              : "当前资产台账没有可展示的健康评估。"
          }
        />
      </AppShell>
    );
  }
  const selectedTurbine =
    runtimeMode === "demo" ? turbines.find((turbine) => turbine.id === selected.turbineId) : null;
  const selectedModel = selected.turbineModel ?? selectedTurbine?.model ?? "型号未登记";
  const activeAlarmCount = selected.activeAlarmCount ?? selectedTurbine?.activeAlarmCount ?? 0;
  const average =
    assessments.reduce((sum, assessment) => sum + assessment.healthScore, 0) / assessments.length;
  const highRisk = assessments.filter((assessment) =>
    ["critical", "high"].includes(assessment.riskLevel),
  ).length;
  const declining = assessments.filter((assessment) => assessment.trend === "declining").length;
  const anomalyCoverage = assessments.filter(
    (assessment) => assessment.predictionAvailable !== false,
  ).length;

  const riskCounts = (["critical", "high", "medium", "low"] as const).map((risk) => ({
    risk,
    count: assessments.filter((assessment) => assessment.riskLevel === risk).length,
  }));

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/health">
      <PageHeader
        eyebrow="资产与监测"
        title="设备健康"
        description={`${assessments.length} 台机组健康矩阵、告警风险与现场核验状态`}
        breadcrumb={["资产与监测", "设备健康"]}
        meta={
          <>
            <StatusBadge
              value={healthQuery.isError ? "degraded" : "healthy"}
              label={
                healthQuery.isError
                  ? runtimeMode === "production"
                    ? "权威健康服务不可用"
                    : "降级快照"
                  : "评估数据已更新"
              }
            />
            <span className="page-meta-text">
              评估于{" "}
              {new Date(healthQuery.data?.meta.snapshotAt ?? selected.assessedAt).toLocaleString(
                "zh-CN",
              )}
            </span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => void healthQuery.refetch()}>
              <Activity size={15} /> 刷新评估
            </Button>
            <Link className="button button--primary button--md" href="/predictive-maintenance">
              <CircleGauge size={15} /> 预测性维护
            </Link>
          </>
        }
      />

      <section className="health-kpi-grid" aria-label="健康评估摘要">
        <Card>
          <span className="health-kpi__icon health-kpi__icon--good">
            <HeartPulse size={17} />
          </span>
          <small>全场健康度</small>
          <strong>{average.toFixed(1)}</strong>
          <em>全场平均 / 100</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--risk">
            <ShieldAlert size={17} />
          </span>
          <small>高风险</small>
          <strong>{highRisk}</strong>
          <em>需要优先处置</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--trend">
            <TrendingDown size={17} />
          </span>
          <small>健康下降</small>
          <strong>{declining}</strong>
          <em>趋势持续下降</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--ai">
            <Sparkles size={17} />
          </span>
          <small>异常证据覆盖</small>
          <strong>
            {anomalyCoverage} / {assessments.length}
          </strong>
          <em>{runtimeMode === "production" ? "已接通状态评估" : "Demo 状态证据"}</em>
        </Card>
      </section>

      <section className="data-toolbar health-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            aria-label="搜索健康评估"
            placeholder="搜索机组或健康发现…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="agent-filter-tabs">
          <button className={cn(filter === "all" && "active")} onClick={() => setFilter("all")}>
            全部 <span>{assessments.length}</span>
          </button>
          <button
            className={cn(filter === "at-risk" && "active")}
            onClick={() => setFilter("at-risk")}
          >
            高风险 <span>{highRisk}</span>
          </button>
          <button
            className={cn(filter === "declining" && "active")}
            onClick={() => setFilter("declining")}
          >
            下降趋势 <span>{declining}</span>
          </button>
        </div>
        <span className="toolbar-result">{visible.length} 台风机</span>
        <Button
          variant="secondary"
          disabled={filter === "all" && !query}
          onClick={() => {
            setFilter("all");
            setQuery("");
          }}
        >
          <Filter size={14} /> 重置筛选
        </Button>
      </section>

      <section className="health-dashboard-grid">
        <Card className="fleet-health-map">
          <CardHeader
            eyebrow="全场热力图"
            title={`${assessments.length} 台风机健康矩阵`}
            description="颜色与评分使用全平台统一健康语义；点击机组查看评估"
            action={
              <span className="health-map-legend">
                <i className="good" />
                健康 <i className="watch" />
                关注 <i className="risk" />
                风险
              </span>
            }
          />
          {visible.length ? (
            <div className="health-turbine-grid">
              {visible.map((assessment) => (
                <button
                  key={assessment.turbineId}
                  className={cn(
                    "health-turbine-cell",
                    `health-turbine-cell--${assessment.state}`,
                    selected.turbineId === assessment.turbineId && "health-turbine-cell--selected",
                  )}
                  onClick={() => setSelectedId(assessment.turbineId)}
                  aria-label={`${assessment.turbineId} 健康度 ${assessment.healthScore}`}
                >
                  <span>{assessment.turbineId.replace("WT-", "")}</span>
                  <strong>{assessment.healthScore}</strong>
                  <small>
                    {assessment.predictionAvailable === false
                      ? "无异常证据"
                      : `异常 ${assessment.anomalyScore.toFixed(2)}`}
                  </small>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配的健康评估"
              description="调整搜索或筛选条件后重试。"
            />
          )}
        </Card>

        <Card className="health-selected-panel">
          <CardHeader
            eyebrow="已选资产"
            title={selected.turbineId}
            description={`${selectedModel} · ${selected.primaryFinding}`}
            action={<HealthBadge score={selected.healthScore} />}
          />
          <div className="health-selected-status">
            <StatusBadge value={selected.state} label={stateLabel[selected.state]} />
            <StatusBadge
              value={selected.riskLevel}
              label={`${selected.riskLevel === "critical" ? "严重" : selected.riskLevel === "high" ? "高" : selected.riskLevel === "medium" ? "中" : "低"}风险`}
            />
            <span className={cn("health-trend", `health-trend--${selected.trend}`)}>
              {selected.trend === "improving" ? (
                <TrendingUp size={13} />
              ) : (
                <TrendingDown size={13} />
              )}
              {trendLabel[selected.trend]}
            </span>
          </div>
          <div className="health-selected-metrics">
            <div>
              <small>异常分数</small>
              <strong>
                {selected.predictionAvailable === false ? "—" : selected.anomalyScore.toFixed(2)}
              </strong>
              {selected.predictionAvailable === false ? (
                <em>未接通状态评估</em>
              ) : (
                <Progress
                  value={selected.anomalyScore * 100}
                  tone={selected.anomalyScore >= 0.65 ? "critical" : "warning"}
                />
              )}
            </div>
            <div>
              <small>健康评分</small>
              <strong>{selected.healthScore}</strong>
              <em>可追溯健康评估 / 100</em>
            </div>
            <div>
              <small>评估状态</small>
              <strong>{stateLabel[selected.state]}</strong>
              <em>{trendLabel[selected.trend]}趋势</em>
            </div>
            <div>
              <small>活动告警</small>
              <strong>{activeAlarmCount}</strong>
              <em>
                {runtimeMode === "demo" && selectedTurbine
                  ? localizedStatusLabel(selectedTurbine.status)
                  : stateLabel[selected.state]}
              </em>
            </div>
          </div>
          {runtimeMode === "demo" && selected.turbineId === "WT-023" ? (
            <div className="health-subsystem-list">
              {subsystemHealth.slice(0, 6).map((subsystem) => {
                const score =
                  workflow.workOrderStatus === "completed" && subsystem.key === "main-bearing"
                    ? workflow.mainBearingHealthScore
                    : subsystem.healthScore;
                return (
                  <div key={subsystem.id}>
                    <span>
                      <strong>{subsystem.name}</strong>
                      <small>{subsystem.primaryFinding}</small>
                    </span>
                    <HealthBadge score={score} />
                  </div>
                );
              })}
            </div>
          ) : null}
          <Link className="health-detail-link" href={`/turbines/${selected.turbineId}`}>
            打开数字资产 <ArrowRight size={14} />
          </Link>
        </Card>
      </section>

      <section className="health-secondary-grid">
        <Card>
          <CardHeader
            eyebrow="风险分布"
            title="全场风险分布"
            description="证据等级 × 运营后果综合等级"
          />
          <div className="health-risk-bars">
            {riskCounts.map(({ risk, count }) => (
              <div key={risk}>
                <span>
                  <StatusBadge value={risk} compact />
                  <strong>{count}</strong>
                </span>
                <Progress
                  value={(count / assessments.length) * 100}
                  tone={
                    risk === "critical" || risk === "high"
                      ? "critical"
                      : risk === "medium"
                        ? "warning"
                        : "success"
                  }
                />
              </div>
            ))}
          </div>
        </Card>
        {runtimeMode === "demo" ? (
          <Card className="health-featured-story">
            <CardHeader
              eyebrow="闭环案例"
              title="WT-023 主轴承退化"
              description="同一事件贯穿 SCADA、告警、Mission、审批、工单与知识沉淀"
            />
            <div className="health-story-flow">
              <span>0.86 异常</span>
              <ArrowRight size={13} />
              <span>87% 诊断</span>
              <ArrowRight size={13} />
              <span>方案 B</span>
              <ArrowRight size={13} />
              <span>{workflow.workOrderStatus === "completed" ? "已闭环" : "待执行"}</span>
            </div>
            <p>
              {workflow.workOrderStatus === "completed"
                ? `健康度已恢复至 ${workflow.turbineHealthScore}，${workflow.knowledgeCaseId} 已形成。`
                : "审批后由 WO-20260823-017 执行五项现场任务并回写评估。"}
            </p>
            <Link href="/missions/MISSION-2026-0823">
              查看完整 Mission <ArrowRight size={14} />
            </Link>
          </Card>
        ) : (
          <Card className="health-featured-story">
            <CardHeader
              eyebrow="权威健康记录"
              title={selected.turbineId}
              description="健康评分来自资产状态与已验证现场闭环；预测指标未接通时明确留空。"
            />
            <p>{selected.primaryFinding}</p>
            {selected.missionId ? (
              <Link href={`/missions/${selected.missionId}`}>
                查看关联 Mission <ArrowRight size={14} />
              </Link>
            ) : null}
          </Card>
        )}
      </section>
    </AppShell>
  );
}
