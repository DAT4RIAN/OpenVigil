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
import { healthAssessments, subsystemHealth, turbines, windFarm } from "@/lib";
import type { HealthAssessment } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";

type HealthResponse = {
  data: readonly HealthAssessment[];
  meta: { count: number; total: number; snapshotAt: string };
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

export function AssetHealthPage() {
  const workflow = useDemoWorkflow();
  const [selectedId, setSelectedId] = useState("WT-023");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "at-risk" | "declining">("all");
  const healthQuery = useQuery({
    queryKey: ["health-assessments"],
    queryFn: ({ signal }) => apiGet<HealthResponse>("/api/health-assessments", signal),
    initialData: {
      data: healthAssessments,
      meta: {
        count: healthAssessments.length,
        total: healthAssessments.length,
        snapshotAt: windFarm.lastUpdatedAt,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!turbineId || !healthAssessments.some((item) => item.turbineId === turbineId)) return;
    const timer = window.setTimeout(() => setSelectedId(turbineId), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const assessments = useMemo(
    () =>
      healthQuery.data.data.map((assessment) =>
        assessment.turbineId === "WT-023" && workflow.workOrderStatus === "completed"
          ? {
              ...assessment,
              healthScore: workflow.turbineHealthScore,
              state: "watch" as const,
              trend: "improving" as const,
              riskLevel: "medium" as const,
              failureProbability30d: 12,
              remainingUsefulLifeDays: 126,
              anomalyScore: 0.42,
              primaryFinding: "现场复测后振动与温升回落，继续趋势观察",
            }
          : assessment,
      ),
    [healthQuery.data.data, workflow.turbineHealthScore, workflow.workOrderStatus],
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
    assessments.find((assessment) => assessment.turbineId === selectedId) ??
    assessments[0] ??
    healthAssessments[22]!;
  const selectedTurbine = turbines.find((turbine) => turbine.id === selected.turbineId)!;
  const average =
    assessments.reduce((sum, assessment) => sum + assessment.healthScore, 0) / assessments.length;
  const highRisk = assessments.filter((assessment) =>
    ["critical", "high"].includes(assessment.riskLevel),
  ).length;
  const declining = assessments.filter((assessment) => assessment.trend === "declining").length;

  const riskCounts = (["critical", "high", "medium", "low"] as const).map((risk) => ({
    risk,
    count: assessments.filter((assessment) => assessment.riskLevel === risk).length,
  }));

  return (
    <AppShell activePath="/health">
      <PageHeader
        eyebrow="资产与监测"
        title="设备健康"
        description="64 台机组健康矩阵、失效风险与剩余寿命的统一评估视图"
        breadcrumb={["资产与监测", "设备健康"]}
        meta={
          <>
            <StatusBadge
              value={healthQuery.isError ? "degraded" : "healthy"}
              label={healthQuery.isError ? "FALLBACK SNAPSHOT" : "ASSESSMENTS CURRENT"}
            />
            <span className="page-meta-text">评估于 2026-08-13 10:30</span>
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
          <small>FLEET HEALTH</small>
          <strong>{average.toFixed(1)}</strong>
          <em>全场平均 / 100</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--risk">
            <ShieldAlert size={17} />
          </span>
          <small>HIGH RISK</small>
          <strong>{highRisk}</strong>
          <em>需要优先处置</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--trend">
            <TrendingDown size={17} />
          </span>
          <small>DECLINING</small>
          <strong>{declining}</strong>
          <em>趋势持续下降</em>
        </Card>
        <Card>
          <span className="health-kpi__icon health-kpi__icon--ai">
            <Sparkles size={17} />
          </span>
          <small>AI COVERAGE</small>
          <strong>64 / 64</strong>
          <em>在线健康评估</em>
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
        <span className="toolbar-result">{visible.length} Turbines</span>
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
            eyebrow="FLEET HEATMAP"
            title="64 台风机健康矩阵"
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
                  <small>{assessment.failureProbability30d}%</small>
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
            eyebrow="SELECTED ASSET"
            title={selected.turbineId}
            description={`${selectedTurbine.model} · ${selected.primaryFinding}`}
            action={<HealthBadge score={selected.healthScore} />}
          />
          <div className="health-selected-status">
            <StatusBadge value={selected.state} label={stateLabel[selected.state]} />
            <StatusBadge
              value={selected.riskLevel}
              label={`${selected.riskLevel.toUpperCase()} RISK`}
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
              <small>30 DAY FAILURE</small>
              <strong>{selected.failureProbability30d}%</strong>
              <Progress
                value={selected.failureProbability30d}
                tone={selected.failureProbability30d >= 25 ? "critical" : "warning"}
              />
            </div>
            <div>
              <small>ESTIMATED RUL</small>
              <strong>{selected.remainingUsefulLifeDays} d</strong>
              <em>模型区间 ±12 天</em>
            </div>
            <div>
              <small>ANOMALY SCORE</small>
              <strong>{selected.anomalyScore.toFixed(2)}</strong>
              <em>阈值 0.65</em>
            </div>
            <div>
              <small>ACTIVE ALARMS</small>
              <strong>{selectedTurbine.activeAlarmCount}</strong>
              <em>{selectedTurbine.status}</em>
            </div>
          </div>
          {selected.turbineId === "WT-023" ? (
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
            eyebrow="RISK DISTRIBUTION"
            title="全场风险分布"
            description="Probability × Consequence 综合等级"
          />
          <div className="health-risk-bars">
            {riskCounts.map(({ risk, count }) => (
              <div key={risk}>
                <span>
                  <StatusBadge value={risk} label={risk.toUpperCase()} compact />
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
        <Card className="health-featured-story">
          <CardHeader
            eyebrow="CLOSED-LOOP CASE"
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
      </section>
    </AppShell>
  );
}
