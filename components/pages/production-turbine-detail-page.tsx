"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  CalendarClock,
  ClipboardCheck,
  FileText,
  MapPin,
  Radio,
  TowerControl,
} from "lucide-react";

import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardHeader, KeyValue } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";

type AssetDetailEnvelope = {
  readonly data: {
    readonly asset: {
      readonly id: string;
      readonly model: string;
      readonly manufacturer: string;
      readonly status: string;
      readonly healthScore: number;
      readonly latitude: number | null;
      readonly longitude: number | null;
      readonly windFarmId: string;
      readonly windFarmName: string | null;
      readonly updatedAt: string;
    };
    readonly telemetry: readonly {
      readonly metric: string;
      readonly label: string;
      readonly value: number;
      readonly unit: string;
      readonly quality: string;
      readonly isAnomaly: boolean;
      readonly observedAt: string;
      readonly sourceId: string;
    }[];
    readonly healthEvents: readonly {
      readonly id: string;
      readonly score: number;
      readonly status: string;
      readonly reason: string;
      readonly missionId: string | null;
      readonly recordedAt: string;
    }[];
    readonly alarms: readonly {
      readonly id: string;
      readonly code: string;
      readonly subsystem: string;
      readonly title: string;
      readonly severity: string;
      readonly status: string;
      readonly triggeredAt: string;
    }[];
    readonly missions: readonly {
      readonly id: string;
      readonly title: string;
      readonly status: string;
      readonly revision: number;
      readonly updatedAt: string;
    }[];
    readonly workOrders: readonly {
      readonly id: string;
      readonly title: string;
      readonly status: string;
      readonly priority: string;
      readonly assignedTeam: string | null;
      readonly plannedStart: string | null;
      readonly deadline: string | null;
      readonly updatedAt: string;
    }[];
    readonly documents: readonly {
      readonly id: string;
      readonly title: string;
      readonly type: string;
      readonly version: string;
      readonly citationUri: string;
      readonly artifactSha256: string | null;
      readonly vectorized: boolean;
      readonly updatedAt: string;
    }[];
    readonly context: {
      readonly activeAlarmCount: number;
      readonly missionId: string | null;
      readonly missionStatus: string | null;
      readonly workOrderId: string | null;
      readonly workOrderStatus: string | null;
      readonly nextWeatherWindowId: string | null;
      readonly nextWeatherWindowSuitability: string | null;
    };
    readonly twinProfile: {
      readonly geometryConfigured: boolean;
      readonly geometryUri: string | null;
      readonly geometrySha256: string | null;
      readonly gisConfigured: boolean;
      readonly coordinateReferenceSystem: string | null;
      readonly profileUpdatedAt: string | null;
    };
    readonly snapshotAt: string;
  };
};

const dateTime = (value: string | null): string =>
  value ? new Date(value).toLocaleString("zh-CN") : "未记录";

export function ProductionTurbineDetailPage({ turbineId }: { readonly turbineId: string }) {
  const detailQuery = useQuery({
    queryKey: ["production-turbine-detail", turbineId],
    queryFn: ({ signal }) =>
      apiGet<AssetDetailEnvelope>(`/api/backend/turbines/${encodeURIComponent(turbineId)}`, signal),
    retry: false,
  });
  const snapshot = detailQuery.data?.data;
  const asset = snapshot?.asset;

  return (
    <AppShell runtimeMode="production" activePath={`/turbines/${turbineId}`}>
      <PageHeader
        eyebrow="数字资产"
        title={asset ? `${asset.id} · ${asset.model}` : turbineId}
        description="生产资产主数据、最新遥测、健康、告警、Mission、工单与文档关联"
        breadcrumb={["资产与监测", "风场", asset?.windFarmName ?? "生产风场", turbineId]}
        meta={
          <>
            <StatusBadge
              value={detailQuery.isError ? "degraded" : (asset?.status ?? "loading")}
              label={detailQuery.isError ? "资产读取失败" : (asset?.status ?? "读取中")}
              tone={detailQuery.isError ? "critical" : undefined}
              pulse={!detailQuery.isError && asset?.status === "running"}
            />
            {asset ? <HealthBadge score={asset.healthScore} /> : null}
            <span className="page-meta-text">
              {snapshot ? `快照 ${dateTime(snapshot.snapshotAt)}` : "不回退到演示资产"}
            </span>
          </>
        }
        actions={
          <>
            <Link
              className="button button--secondary button--md"
              href={`/scada?turbineId=${encodeURIComponent(turbineId)}`}
            >
              <Activity size={15} /> 历史趋势
            </Link>
            <Link
              className="button button--secondary button--md"
              href={`/work-orders?turbineId=${encodeURIComponent(turbineId)}`}
            >
              <CalendarClock size={15} /> 维护计划
            </Link>
            <Link
              className="button button--primary button--md"
              href={
                snapshot?.context.missionId
                  ? `/missions/${snapshot.context.missionId}`
                  : "/missions"
              }
            >
              <Bot size={15} /> {snapshot?.context.missionId ? "打开关联 Mission" : "Mission 中心"}
            </Link>
          </>
        }
      />

      {detailQuery.isPending ? (
        <Card className="view-empty-state" role="status">
          正在读取生产资产快照…
        </Card>
      ) : null}
      {detailQuery.isError ? (
        <Card className="view-empty-state" role="alert">
          资产不存在或生产后端不可用；页面已失败关闭，不会显示同编号演示机组。
        </Card>
      ) : null}

      {snapshot && asset ? (
        <>
          <nav className="detail-tabs" aria-label="机组详情标签页">
            <a className="active" href="#overview">
              概览
            </a>
            <a href="#telemetry">
              遥测 <span>{snapshot.telemetry.length}</span>
            </a>
            <a href="#health">
              健康 <span>{snapshot.healthEvents.length}</span>
            </a>
            <a href="#alarms">
              告警 <span>{snapshot.alarms.length}</span>
            </a>
            <a href="#missions">
              Mission <span>{snapshot.missions.length}</span>
            </a>
            <a href="#maintenance">
              维护 <span>{snapshot.workOrders.length}</span>
            </a>
            <a href="#documents">
              文档 <span>{snapshot.documents.length}</span>
            </a>
          </nav>

          <div className="asset-overview-grid" id="overview">
            <Card className="asset-hero-card">
              <div className="asset-hero-card__visual">
                <span className="asset-hero-grid" />
                <TowerControl size={88} strokeWidth={1.2} />
                <span className="asset-hero-card__tag">生产资产</span>
              </div>
              <div className="asset-hero-card__content">
                <span className="eyebrow">资产档案</span>
                <h2>{asset.id}</h2>
                <p>
                  {asset.manufacturer === "unconfigured" ? "制造商未配置" : asset.manufacturer} ·{" "}
                  {asset.model}
                </p>
                <div className="asset-profile-list">
                  <KeyValue label="风场" value={asset.windFarmName ?? asset.windFarmId} />
                  <KeyValue label="资产状态" value={asset.status} />
                  <KeyValue label="健康度" value={`${asset.healthScore}/100`} />
                  <KeyValue label="主数据更新" value={dateTime(asset.updatedAt)} />
                </div>
              </div>
            </Card>

            <Card className="asset-live-card" id="telemetry">
              <CardHeader
                eyebrow="最新遥测"
                title="质量感知运行参数"
                description={`${snapshot.telemetry.length} 个真实变量；缺失变量不会补演示值`}
              />
              <div className="live-metric-grid">
                {snapshot.telemetry.slice(0, 8).map((signal) => (
                  <div
                    className={signal.isAnomaly ? "live-metric--warning" : undefined}
                    key={signal.metric}
                  >
                    <span>
                      <Radio size={14} /> {signal.label}
                    </span>
                    <strong>
                      {signal.value} <small>{signal.unit}</small>
                    </strong>
                    <em>
                      {signal.sourceId} · {signal.quality} · {dateTime(signal.observedAt)}
                    </em>
                  </div>
                ))}
              </div>
              {!snapshot.telemetry.length ? (
                <div className="view-empty-state">尚无质量合格遥测。</div>
              ) : null}
            </Card>

            <Card id="health">
              <CardHeader eyebrow="健康台账" title="健康评估事件" description="按记录时间倒序" />
              <div className="asset-history-list">
                {snapshot.healthEvents.map((event) => (
                  <div key={event.id}>
                    <span className="history-icon">
                      <Activity size={14} />
                    </span>
                    <span>
                      <strong>{event.reason}</strong>
                      <small>
                        {event.id} · {dateTime(event.recordedAt)} ·{" "}
                        {event.missionId ?? "无 Mission"}
                      </small>
                    </span>
                    <HealthBadge score={event.score} />
                  </div>
                ))}
                {!snapshot.healthEvents.length ? (
                  <div className="view-empty-state">尚无健康事件。</div>
                ) : null}
              </div>
            </Card>

            <Card>
              <CardHeader
                eyebrow="GIS / 3D"
                title="受治理孪生档案"
                description="经哈希校验的模型与坐标配置"
              />
              <div className="key-value-list">
                <KeyValue
                  label="坐标"
                  value={
                    asset.latitude == null || asset.longitude == null
                      ? "未配置"
                      : `${asset.latitude}, ${asset.longitude}`
                  }
                />
                <KeyValue
                  label="坐标系"
                  value={snapshot.twinProfile.coordinateReferenceSystem ?? "未配置"}
                />
                <KeyValue
                  label="3D 制品"
                  value={snapshot.twinProfile.geometryConfigured ? "已验证" : "未配置"}
                />
                <KeyValue label="SHA-256" value={snapshot.twinProfile.geometrySha256 ?? "—"} mono />
              </div>
            </Card>
          </div>

          <section className="dashboard-grid">
            <Card className="panel panel--alerts" id="alarms">
              <CardHeader eyebrow="告警" title="资产告警历史" description="权威告警台账" />
              <div className="compact-list">
                {snapshot.alarms.map((alarm) => (
                  <Link
                    className="compact-row alarm-row"
                    href={`/alarms?turbineId=${encodeURIComponent(turbineId)}`}
                    key={alarm.id}
                  >
                    <span className={`severity-rail severity-rail--${alarm.severity}`} />
                    <span className="compact-row__main">
                      <strong>{alarm.title}</strong>
                      <small>
                        {alarm.code} · {alarm.subsystem} · {dateTime(alarm.triggeredAt)}
                      </small>
                    </span>
                    <StatusBadge value={alarm.status} compact />
                  </Link>
                ))}
                {!snapshot.alarms.length ? (
                  <div className="view-empty-state">没有告警记录。</div>
                ) : null}
              </div>
            </Card>

            <Card className="panel panel--missions" id="missions">
              <CardHeader eyebrow="Mission" title="诊断与决策流程" description="全部关联 Mission" />
              <div className="mission-list">
                {snapshot.missions.map((mission) => (
                  <Link
                    className="mission-list-row"
                    href={`/missions/${mission.id}`}
                    key={mission.id}
                  >
                    <span>
                      <strong>{mission.title}</strong>
                      <small>
                        {mission.id} · REV {mission.revision} · {dateTime(mission.updatedAt)}
                      </small>
                    </span>
                    <StatusBadge value={mission.status} compact />
                  </Link>
                ))}
                {!snapshot.missions.length ? (
                  <div className="view-empty-state">没有关联 Mission。</div>
                ) : null}
              </div>
            </Card>

            <Card className="panel" id="maintenance">
              <CardHeader eyebrow="维护" title="工单历史" description="计划、执行与闭环记录" />
              <div className="asset-history-list">
                {snapshot.workOrders.map((order) => (
                  <Link
                    href={`/work-orders?turbineId=${encodeURIComponent(turbineId)}`}
                    key={order.id}
                  >
                    <span className="history-icon">
                      <ClipboardCheck size={14} />
                    </span>
                    <span>
                      <strong>{order.title}</strong>
                      <small>
                        {order.id} · {order.assignedTeam ?? "未分配"} ·{" "}
                        {dateTime(order.plannedStart)}
                      </small>
                    </span>
                    <StatusBadge value={order.status} compact />
                  </Link>
                ))}
                {!snapshot.workOrders.length ? (
                  <div className="view-empty-state">没有工单记录。</div>
                ) : null}
              </div>
            </Card>

            <Card className="panel" id="documents">
              <CardHeader
                eyebrow="知识"
                title="关联受控文档"
                description="仅显示明确关联该资产的已就绪文档"
              />
              <div className="asset-history-list">
                {snapshot.documents.map((document) => (
                  <Link
                    href={`/knowledge?document=${encodeURIComponent(document.id)}`}
                    key={document.id}
                  >
                    <span className="history-icon">
                      <FileText size={14} />
                    </span>
                    <span>
                      <strong>{document.title}</strong>
                      <small>
                        {document.id} · {document.type} · v{document.version}
                      </small>
                    </span>
                    <StatusBadge value={document.vectorized ? "vectorized" : "indexed"} compact />
                  </Link>
                ))}
                {!snapshot.documents.length ? (
                  <div className="view-empty-state">没有明确关联的已就绪文档。</div>
                ) : null}
              </div>
            </Card>
          </section>

          <Card className="resource-check">
            <MapPin size={14} />
            <span>
              <strong>数据来源：PostgreSQL / TimescaleDB</strong>
              <small>对象、遥测、业务状态和关联记录均为持久化生产数据。</small>
            </span>
          </Card>
        </>
      ) : null}
    </AppShell>
  );
}
