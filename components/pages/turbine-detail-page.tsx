"use client";

import { useState } from "react";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  Bot,
  CalendarClock,
  ClipboardCheck,
  FileText,
  Gauge,
  Play,
  Radio,
  Settings2,
  ShieldAlert,
  Thermometer,
  TowerControl,
  TrendingDown,
  Wind,
  Wrench,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, KeyValue, Progress } from "@/components/ui/primitives";
import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import {
  alarms,
  featuredMission,
  getFeaturedMissionNarrative,
  getTurbine,
  knowledgeDocuments,
  scadaSeries,
  subsystemHealth,
  turbine023,
  workOrders,
} from "@/lib";
import type { SubsystemHealth, WindTurbine, WorkOrderStatus } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

const tabs = [
  "Overview",
  "SCADA",
  "Health",
  "Alarms",
  "Missions",
  "Maintenance",
  "Documents",
] as const;
type Tab = (typeof tabs)[number];

function stateLabel(state: SubsystemHealth["state"]) {
  const labels: Record<SubsystemHealth["state"], string> = {
    healthy: "健康",
    watch: "关注",
    degraded: "退化",
    critical: "严重",
    maintenance: "维护",
    offline: "离线",
  };
  return labels[state];
}

function series(metric: string): TimeSeriesPoint[] {
  const match = scadaSeries.find((item) => item.metric === metric);
  return (
    match?.points.map((point) => ({
      timestamp: new Date(point.timestamp).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
      value: point.value,
      anomaly: point.isAnomaly,
      aiEvent: Boolean(point.aiEvent),
    })) ?? []
  );
}

function OverviewTab({
  turbineHealthScore,
  mainBearingHealthScore,
  closed,
}: {
  turbineHealthScore: number;
  mainBearingHealthScore: number;
  closed: boolean;
}) {
  const bearing = subsystemHealth.find((item) => item.key === "main-bearing");
  return (
    <div className="asset-overview-grid">
      <Card className="asset-hero-card">
        <div className="asset-hero-card__visual">
          <span className="asset-hero-grid" />
          <TowerControl size={88} strokeWidth={1.2} />
          <span className="asset-hero-card__tag">DIGITAL ASSET</span>
        </div>
        <div className="asset-hero-card__content">
          <span className="eyebrow">ASSET PROFILE</span>
          <h2>{turbine023.id}</h2>
          <p>
            {turbine023.manufacturer} {turbine023.model}
          </p>
          <div className="asset-profile-list">
            <KeyValue label="额定功率" value={`${turbine023.ratedPowerMW.toFixed(1)} MW`} />
            <KeyValue label="序列号" value={turbine023.serialNumber} mono />
            <KeyValue label="投运年限" value="4.7 年" />
            <KeyValue label="全周期可利用率" value="97.2%" />
          </div>
        </div>
      </Card>

      <Card className="asset-live-card">
        <CardHeader
          eyebrow="LIVE SNAPSHOT"
          title="实时运行参数"
          description="数据质量良好 · 12 秒前更新"
        />
        <div className="live-metric-grid">
          <div>
            <span>
              <Zap size={14} /> 有功功率
            </span>
            <strong>
              5.34 <small>MW</small>
            </strong>
            <em>89% 额定功率</em>
          </div>
          <div>
            <span>
              <Wind size={14} /> 风速
            </span>
            <strong>
              9.7 <small>m/s</small>
            </strong>
            <em>东南风 128°</em>
          </div>
          <div>
            <span>
              <Gauge size={14} /> 转子转速
            </span>
            <strong>
              11.6 <small>rpm</small>
            </strong>
            <em>稳定</em>
          </div>
          <div className="live-metric--warning">
            <span>
              <Thermometer size={14} /> 主轴承温度
            </span>
            <strong>
              76.4 <small>°C</small>
            </strong>
            <em>+8.4°C 基线偏差</em>
          </div>
        </div>
        <div className="asset-mini-chart">
          <div>
            <span className="eyebrow">ACTIVE POWER · 6H</span>
            <strong>稳定输出，存在 6% 功率波动</strong>
          </div>
          <TimeSeriesChart data={series("active-power")} height={108} unit="MW" compact />
        </div>
      </Card>

      <Card className="bearing-focus-card">
        <div className="bearing-focus-card__header">
          <span className="bearing-focus-icon">
            <ShieldAlert size={19} />
          </span>
          <span>
            <span className="eyebrow">PRIMARY RISK</span>
            <h2>主轴承早期退化</h2>
          </span>
          <StatusBadge value="high" label="HIGH RISK" tone="critical" />
        </div>
        <p>
          {closed
            ? "现场检查与复测已经完成，振动及温升回落；结果已回写健康评估并形成知识案例。"
            : "振动 RMS 持续升高并与温升、功率波动呈相关性。故障诊断 Agent 给出 87% 置信度。"}
        </p>
        <div className="risk-stat-grid">
          <div>
            <small>当前健康度</small>
            <strong>
              {mainBearingHealthScore}
              <span>/100</span>
            </strong>
            <Progress
              value={mainBearingHealthScore}
              tone={mainBearingHealthScore >= 75 ? "warning" : "critical"}
            />
          </div>
          <div>
            <small>整机健康度</small>
            <strong>
              {turbineHealthScore}
              <span>/100</span>
            </strong>
            <Progress
              value={turbineHealthScore}
              tone={turbineHealthScore >= 80 ? "success" : "warning"}
            />
          </div>
          <div>
            <small>预计 RUL</small>
            <strong>
              {closed ? 126 : (bearing?.remainingUsefulLifeDays ?? 47)}
              <span>天</span>
            </strong>
            <span className="trend-label">
              <TrendingDown size={12} /> {closed ? "复测后上调" : "持续下降"}
            </span>
          </div>
          <div>
            <small>异常得分</small>
            <strong>{closed ? "0.42" : (bearing?.anomalyScore.toFixed(2) ?? "0.86")}</strong>
            <span className={cn("trend-label", !closed && "warning-text")}>
              <Activity size={12} /> {closed ? "回落至关注区" : "高于阈值"}
            </span>
          </div>
        </div>
        <div className="bearing-focus-card__action">
          <span>
            <Bot size={15} />
            <strong>
              {closed
                ? "Knowledge Agent：闭环案例已完成向量化"
                : "AI 建议：降载运行并在 72 小时内检查"}
            </strong>
          </span>
          <a href={`/missions/${featuredMission.id}`}>
            {closed ? "查看闭环" : "查看决策"} <ArrowRight size={13} />
          </a>
        </div>
      </Card>

      <Card className="subsystem-panel">
        <CardHeader
          eyebrow="COMPONENT HEALTH"
          title="子系统健康状态"
          description="基于 SCADA、振动和维护数据的综合评估"
          action={
            <a className="text-link" href="/scada">
              查看监测 <ArrowRight size={12} />
            </a>
          }
        />
        <div className="subsystem-grid">
          {subsystemHealth.map((item) => (
            <div
              className={cn(
                "subsystem-item",
                item.key === "main-bearing" && "subsystem-item--focus",
              )}
              key={item.id}
            >
              <div className="subsystem-item__top">
                <span>
                  <Settings2 size={14} />
                  <strong>{item.name}</strong>
                </span>
                <StatusBadge
                  value={item.state}
                  label={stateLabel(item.state)}
                  tone={
                    item.healthScore >= 90
                      ? "success"
                      : item.healthScore >= 75
                        ? "warning"
                        : "critical"
                  }
                  compact
                />
              </div>
              <div className="subsystem-score">
                <strong>{item.healthScore}</strong>
                <span>/ 100</span>
              </div>
              <Progress
                value={item.healthScore}
                tone={
                  item.healthScore >= 90
                    ? "success"
                    : item.healthScore >= 75
                      ? "warning"
                      : "critical"
                }
              />
              <div className="subsystem-item__footer">
                <span>失效概率 {item.failureProbability30d}%</span>
                <span>RUL {item.remainingUsefulLifeDays ?? "—"}d</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="asset-history-card">
        <CardHeader
          eyebrow="ASSET HISTORY"
          title="最近事件"
          description="维护、告警与 AI 分析记录"
        />
        <div className="asset-history-list">
          <div>
            <span className="history-icon history-icon--critical">
              <AlarmTriangle size={14} />
            </span>
            <span>
              <strong>主轴承振动告警升级</strong>
              <small>ALM-2026-0031 · 今天 09:42</small>
            </span>
          </div>
          <div>
            <span className="history-icon history-icon--info">
              <Bot size={14} />
            </span>
            <span>
              <strong>多 Agent 诊断完成</strong>
              <small>退化概率 87% · 今天 09:31</small>
            </span>
          </div>
          <div>
            <span className="history-icon history-icon--maintenance">
              <Wrench size={14} />
            </span>
            <span>
              <strong>季度润滑系统巡检</strong>
              <small>WO-20260702-008 · 2026/07/02</small>
            </span>
          </div>
          <div>
            <span className="history-icon">
              <Radio size={14} />
            </span>
            <span>
              <strong>振动传感器校准</strong>
              <small>结果正常 · 2026/06/18</small>
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}

function ScadaTab() {
  return (
    <div className="two-column-content">
      <Card>
        <CardHeader
          eyebrow="SCADA · 24H"
          title="主轴承振动 RMS"
          description="阈值、异常点与 AI 事件联动"
        />
        <TimeSeriesChart
          data={series("main-bearing-vibration-rms")}
          height={300}
          unit="mm/s"
          threshold={4.5}
          primaryName="振动 RMS"
        />
      </Card>
      <Card>
        <CardHeader
          eyebrow="CORRELATED SIGNAL"
          title="主轴承温度"
          description="与振动异常存在 0.79 相关度"
        />
        <TimeSeriesChart
          data={series("main-bearing-temperature")}
          height={300}
          unit="°C"
          threshold={75}
          primaryName="轴承温度"
        />
      </Card>
    </div>
  );
}

function HealthTab() {
  return (
    <div className="health-detail-layout">
      <Card className="health-matrix-card">
        <CardHeader
          eyebrow="ASSET HEALTH"
          title="子系统风险矩阵"
          description="概率 × 后果的综合风险排序"
        />
        <div className="risk-matrix">
          <div className="risk-axis risk-axis--y">失效概率 ↑</div>
          {[5, 4, 3, 2, 1].flatMap((row) =>
            [1, 2, 3, 4, 5].map((column) => {
              const level =
                row * column >= 16
                  ? "critical"
                  : row * column >= 10
                    ? "high"
                    : row * column >= 5
                      ? "medium"
                      : "low";
              const bearing = row === 4 && column === 4;
              return (
                <div key={`${row}-${column}`} className={cn("risk-cell", `risk-cell--${level}`)}>
                  {bearing ? <span>主轴承</span> : null}
                </div>
              );
            }),
          )}
          <div className="risk-axis risk-axis--x">后果严重度 →</div>
        </div>
      </Card>
      <Card>
        <CardHeader eyebrow="DEGRADATION" title="健康趋势" description="过去 90 天持续下降" />
        <TimeSeriesChart
          data={series("anomaly-score")}
          height={290}
          unit="score"
          threshold={0.7}
          primaryName="异常得分"
        />
      </Card>
    </div>
  );
}

function RelatedList({
  type,
  knowledgeCaseId,
  workflowWorkOrderStatus,
}: {
  type: "alarms" | "maintenance" | "documents";
  knowledgeCaseId?: string | null;
  workflowWorkOrderStatus?: WorkOrderStatus;
}) {
  const items =
    type === "alarms"
      ? alarms
          .filter((item) => item.turbineId === turbine023.id)
          .map((item) => ({
            id: item.id,
            title: item.title,
            meta: `${item.code} · ${item.severity.toUpperCase()}`,
            status: item.status,
          }))
      : type === "maintenance"
        ? workOrders
            .filter((item) => item.turbineId === turbine023.id)
            .map((item) => ({
              id: item.id,
              title: item.issue,
              meta: `${item.assignedTeam} · ${new Date(item.plannedStart).toLocaleDateString("zh-CN")}`,
              status:
                item.id === "WO-20260823-017" && workflowWorkOrderStatus
                  ? workflowWorkOrderStatus
                  : item.status,
            }))
        : knowledgeDocuments
            .filter((item) => item.relatedTurbineIds.includes(turbine023.id))
            .map((item) => ({
              id: item.id,
              title: item.title,
              meta: `${item.type} · ${item.version}`,
              status: item.vectorized ? "vectorized" : "pending",
            }));
  const displayItems =
    knowledgeCaseId && type === "documents"
      ? [
          {
            id: knowledgeCaseId,
            title: "WT-023 主轴承退化诊断与现场复测闭环案例",
            meta: "failure-case · Closed-loop v1.0",
            status: "vectorized",
          },
          ...items,
        ]
      : items;
  return (
    <Card className="related-records">
      <CardHeader
        eyebrow="RELATED RECORDS"
        title={type === "alarms" ? "相关告警" : type === "maintenance" ? "维护记录" : "关联文档"}
        description={`与 ${turbine023.id} 资产关联的可追溯记录`}
      />
      <div className="related-list">
        {displayItems.map((item) => (
          <div key={item.id}>
            <span className="related-list__icon">
              {type === "alarms" ? (
                <AlarmTriangle size={15} />
              ) : type === "maintenance" ? (
                <ClipboardCheck size={15} />
              ) : (
                <FileText size={15} />
              )}
            </span>
            <span>
              <strong>{item.title}</strong>
              <small>
                {item.id} · {item.meta}
              </small>
            </span>
            <StatusBadge value={item.status} compact />
          </div>
        ))}
      </div>
    </Card>
  );
}

function GenericTurbineDetailPage({ turbine }: { turbine: WindTurbine }) {
  const relatedAlarms = alarms.filter((item) => item.turbineId === turbine.id);
  const relatedWorkOrders = workOrders.filter((item) => item.turbineId === turbine.id);
  const componentNames = ["叶片", "主轴承", "齿轮箱", "发电机", "塔架", "电气系统"];

  return (
    <AppShell activePath={`/turbines/${turbine.id}`}>
      <PageHeader
        eyebrow="数字资产"
        title={`${turbine.id} · ${turbine.model}`}
        description="机组实时状态、健康评估、告警与维护记录"
        breadcrumb={["资产与监测", "风场", "华东海上风电场", turbine.id]}
        meta={
          <>
            <StatusBadge
              value={turbine.status}
              label={turbine.status.replaceAll("-", " ").toUpperCase()}
              pulse={turbine.status === "running"}
            />
            <HealthBadge score={turbine.healthScore} />
            <span className="page-meta-text">资产记录 {turbine.serialNumber}</span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/work-orders?turbineId=${turbine.id}`}
            >
              <CalendarClock size={15} /> 维护计划
            </a>
            <a
              className="button button--secondary button--md"
              href={`/api/turbines/${turbine.id}/scada`}
            >
              <Activity size={15} /> 数据接口
            </a>
            {turbine.currentMissionId ? (
              <a
                className="button button--primary button--md"
                href={`/missions/${turbine.currentMissionId}`}
              >
                <Play size={15} /> 打开 AI 诊断
              </a>
            ) : (
              <Button variant="primary" disabled title="当前机组没有可打开的诊断 Mission">
                <Play size={15} /> 暂无诊断 Mission
              </Button>
            )}
          </>
        }
      />
      <nav className="detail-tabs" aria-label="机组详情标签页">
        <button className="active">Overview</button>
        <a href={`/scada?turbineId=${turbine.id}`}>SCADA</a>
        <a href={`/alarms?turbineId=${turbine.id}`}>
          Alarms <span>{relatedAlarms.length}</span>
        </a>
        <a href={`/work-orders?turbineId=${turbine.id}`}>
          Maintenance <span>{relatedWorkOrders.length}</span>
        </a>
      </nav>
      <div className="asset-overview-grid">
        <Card className="asset-hero-card">
          <div className="asset-hero-card__visual">
            <span className="asset-hero-grid" />
            <TowerControl size={88} strokeWidth={1.2} />
            <span className="asset-hero-card__tag">DIGITAL ASSET</span>
          </div>
          <div className="asset-hero-card__content">
            <span className="eyebrow">ASSET PROFILE</span>
            <h2>{turbine.id}</h2>
            <p>
              {turbine.manufacturer} {turbine.model}
            </p>
            <div className="asset-profile-list">
              <KeyValue label="额定功率" value={`${turbine.ratedPowerMW.toFixed(1)} MW`} />
              <KeyValue label="序列号" value={turbine.serialNumber} mono />
              <KeyValue label="可利用率" value={`${turbine.availabilityPercent.toFixed(1)}%`} />
              <KeyValue label="当前 Mission" value={turbine.currentMissionId ?? "—"} mono />
            </div>
          </div>
        </Card>
        <Card className="asset-live-card">
          <CardHeader
            eyebrow="LIVE SNAPSHOT"
            title="实时运行参数"
            description="确定性场站快照 · 数据质量良好"
          />
          <div className="live-metric-grid">
            <div>
              <span>
                <Zap size={14} /> 有功功率
              </span>
              <strong>
                {turbine.powerMW.toFixed(2)} <small>MW</small>
              </strong>
              <em>{Math.round((turbine.powerMW / turbine.ratedPowerMW) * 100)}% 额定功率</em>
            </div>
            <div>
              <span>
                <Wind size={14} /> 风速
              </span>
              <strong>
                {turbine.windSpeedMps.toFixed(1)} <small>m/s</small>
              </strong>
              <em>机舱方向 {turbine.nacelleDirectionDeg}°</em>
            </div>
            <div>
              <span>
                <Gauge size={14} /> 转子转速
              </span>
              <strong>
                {turbine.rotorSpeedRpm.toFixed(1)} <small>rpm</small>
              </strong>
              <em>稳定</em>
            </div>
            <div>
              <span>
                <Activity size={14} /> 活跃告警
              </span>
              <strong>{turbine.activeAlarmCount}</strong>
              <em>{relatedAlarms.length} 条关联记录</em>
            </div>
          </div>
        </Card>
        <Card className="bearing-focus-card">
          <div className="bearing-focus-card__header">
            <span className="bearing-focus-icon">
              <ShieldAlert size={19} />
            </span>
            <span>
              <span className="eyebrow">ASSET ASSESSMENT</span>
              <h2>
                {turbine.healthScore >= 90
                  ? "运行状态健康"
                  : turbine.healthScore >= 75
                    ? "建议持续关注"
                    : "需要优先处置"}
              </h2>
            </span>
            <StatusBadge value={turbine.status} label={turbine.status.toUpperCase()} />
          </div>
          <p>综合 SCADA 运行状态、活跃告警和最近维护记录形成当前健康快照。</p>
          <div className="risk-stat-grid">
            <div>
              <small>健康度</small>
              <strong>
                {turbine.healthScore}
                <span>/100</span>
              </strong>
              <Progress
                value={turbine.healthScore}
                tone={
                  turbine.healthScore >= 90
                    ? "success"
                    : turbine.healthScore >= 75
                      ? "warning"
                      : "critical"
                }
              />
            </div>
            <div>
              <small>可利用率</small>
              <strong>
                {turbine.availabilityPercent.toFixed(1)}
                <span>%</span>
              </strong>
              <Progress value={turbine.availabilityPercent} tone="success" />
            </div>
            <div>
              <small>活跃告警</small>
              <strong>{turbine.activeAlarmCount}</strong>
              <span className="trend-label">
                <AlarmTriangle size={12} /> linked records
              </span>
            </div>
            <div>
              <small>维护记录</small>
              <strong>{relatedWorkOrders.length}</strong>
              <span className="trend-label">
                <Wrench size={12} /> work orders
              </span>
            </div>
          </div>
        </Card>
        <Card className="subsystem-panel">
          <CardHeader
            eyebrow="COMPONENT HEALTH"
            title="子系统健康状态"
            description="由整机健康评分派生的演示快照"
          />
          <div className="subsystem-grid">
            {componentNames.map((name, index) => {
              const score = Math.max(
                45,
                Math.min(99, turbine.healthScore + [3, -4, 2, 5, 1, 6][index]),
              );
              return (
                <div className="subsystem-item" key={name}>
                  <div className="subsystem-item__top">
                    <span>
                      <Settings2 size={14} />
                      <strong>{name}</strong>
                    </span>
                    <StatusBadge
                      value={score >= 90 ? "healthy" : score >= 75 ? "watch" : "degraded"}
                      label={score >= 90 ? "健康" : score >= 75 ? "关注" : "退化"}
                      tone={score >= 90 ? "success" : score >= 75 ? "warning" : "critical"}
                      compact
                    />
                  </div>
                  <div className="subsystem-score">
                    <strong>{score}</strong>
                    <span>/ 100</span>
                  </div>
                  <Progress
                    value={score}
                    tone={score >= 90 ? "success" : score >= 75 ? "warning" : "critical"}
                  />
                  <div className="subsystem-item__footer">
                    <span>状态已评估</span>
                    <span>{turbine.id}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
        <Card className="asset-history-card">
          <CardHeader
            eyebrow="MAINTENANCE HISTORY"
            title="关联工单"
            description={`与 ${turbine.id} 关联的可追溯维护记录`}
          />
          <div className="asset-history-list">
            {relatedWorkOrders.length ? (
              relatedWorkOrders.map((item) => (
                <div key={item.id}>
                  <span className="history-icon history-icon--maintenance">
                    <Wrench size={14} />
                  </span>
                  <span>
                    <strong>{item.issue}</strong>
                    <small>
                      {item.id} · {item.assignedTeam}
                    </small>
                  </span>
                  <StatusBadge value={item.status} compact />
                </div>
              ))
            ) : (
              <div>
                <span className="history-icon">
                  <ClipboardCheck size={14} />
                </span>
                <span>
                  <strong>暂无维护工单</strong>
                  <small>可从工单中心创建新的计划任务</small>
                </span>
              </div>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}

function FeaturedTurbineDetailPage() {
  const [tab, setTab] = useState<Tab>("Overview");
  const workflow = useDemoWorkflow();
  const closed = workflow.missionStatus === "completed";
  const featuredNarrative = getFeaturedMissionNarrative(workflow);
  return (
    <AppShell activePath="/turbines/WT-023">
      <PageHeader
        eyebrow="数字资产"
        title={`${turbine023.id} · ${turbine023.model}`}
        description={
          closed
            ? "现场执行、结果验证和知识沉淀均已完成"
            : "主轴承异常已进入多 Agent 协同诊断与人工审批流程"
        }
        breadcrumb={["资产与监测", "风场", "华东海上风电场", turbine023.id]}
        meta={
          <>
            <StatusBadge
              value={closed ? "verified" : turbine023.status}
              label={closed ? "已验证运行" : "预警运行"}
              tone={closed ? "success" : "warning"}
              pulse={!closed}
            />
            <HealthBadge score={workflow.turbineHealthScore} />
            <span className="page-meta-text">闭环状态跨页面同步</span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/work-orders?turbineId=${turbine023.id}`}
            >
              <CalendarClock size={15} /> 维护计划
            </a>
            <a
              className="button button--secondary button--md"
              href={`/scada?turbineId=${turbine023.id}&metric=main-bearing-vibration-rms`}
            >
              <Activity size={15} /> 历史趋势
            </a>
            <a
              className="button button--primary button--md"
              href={`/missions/${featuredMission.id}`}
            >
              <Play size={15} /> 打开 AI 诊断
            </a>
          </>
        }
      />
      <nav className="detail-tabs" aria-label="机组详情标签页">
        {tabs.map((item) => (
          <button key={item} className={cn(tab === item && "active")} onClick={() => setTab(item)}>
            {item}
            {item === "Alarms" ? <span>3</span> : null}
            {item === "Missions" ? <span>1</span> : null}
          </button>
        ))}
      </nav>
      {tab === "Overview" ? (
        <OverviewTab
          turbineHealthScore={workflow.turbineHealthScore}
          mainBearingHealthScore={workflow.mainBearingHealthScore}
          closed={closed}
        />
      ) : null}
      {tab === "SCADA" ? <ScadaTab /> : null}
      {tab === "Health" ? <HealthTab /> : null}
      {tab === "Alarms" ? <RelatedList type="alarms" /> : null}
      {tab === "Missions" ? (
        <Card className="mission-callout">
          <span className="mission-callout__icon">
            <Bot size={24} />
          </span>
          <span>
            <span className="eyebrow">{closed ? "CLOSED MISSION" : "ACTIVE MISSION"}</span>
            <h2>{featuredMission.title}</h2>
            <p>{featuredNarrative.summary}</p>
            <div>
              <StatusBadge
                value={workflow.missionStatus}
                label={workflow.missionStatus.replaceAll("-", " ").toUpperCase()}
                tone={closed ? "success" : "info"}
                pulse={!closed}
              />
              <strong>{workflow.missionProgress}%</strong>
            </div>
          </span>
          <a className="button button--primary button--md" href={`/missions/${featuredMission.id}`}>
            打开 Mission <ArrowRight size={14} />
          </a>
        </Card>
      ) : null}
      {tab === "Maintenance" ? (
        <RelatedList type="maintenance" workflowWorkOrderStatus={workflow.workOrderStatus} />
      ) : null}
      {tab === "Documents" ? (
        <RelatedList type="documents" knowledgeCaseId={workflow.knowledgeCaseId} />
      ) : null}
    </AppShell>
  );
}

export function TurbineDetailPage({ turbineId = "WT-023" }: { turbineId?: string }) {
  const turbine = getTurbine(turbineId);
  if (!turbine) return null;
  return turbine.id === turbine023.id ? (
    <FeaturedTurbineDetailPage />
  ) : (
    <GenericTurbineDetailPage turbine={turbine} />
  );
}
