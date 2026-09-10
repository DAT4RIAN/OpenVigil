"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  CalendarDays,
  ClipboardPlus,
  Grid2X2,
  HeartPulse,
  List,
  Map,
  Network,
  Search,
  SlidersHorizontal,
  Thermometer,
  TowerControl,
  Wind,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-display/data-table";
import { Button, Card, KeyValue, Progress } from "@/components/ui/primitives";
import { HealthBadge, StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { agents } from "@/lib/agent-data";
import { turbines, windFarm } from "@/lib/farm-data";
import { alarms, missions } from "@/lib/operations-data";
import type { TurbineStatus, WindTurbine } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import {
  deriveWorkflowKpis,
  overlayClientAgents,
  overlayClientAlarms,
  overlayClientMissions,
  overlayClientTurbines,
} from "@/lib/client-workflow-overlays";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { apiGet } from "@/lib/api-client";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

type ViewMode = "cards" | "list" | "topology" | "map";

type FleetTurbine = WindTurbine & {
  readonly updatedAt?: string;
  readonly telemetryObservedAt?: string | null;
  readonly telemetryAvailable?: boolean;
  readonly availabilityAvailable?: boolean;
  readonly coordinatesConfigured?: boolean;
  readonly lastMaintenanceRecorded?: boolean;
  readonly nextInspectionRecorded?: boolean;
};

type FleetResponse = {
  readonly data: readonly FleetTurbine[];
  readonly meta: {
    readonly snapshotAt: string;
    readonly farms: readonly {
      readonly id: string;
      readonly name: string;
      readonly capacityMW: number;
    }[];
    readonly fleet: {
      readonly currentPowerMW: number;
      readonly averageHealthScore: number;
      readonly activeAlarmCount: number;
      readonly activeMissionCount: number;
      readonly generationAvailable: boolean;
      readonly averageAvailabilityPercent: number | null;
      readonly telemetryAssetCount: number;
    };
  };
};

const statusMeta: Record<TurbineStatus, { label: string; tone: StatusTone }> = {
  running: { label: "运行", tone: "success" },
  warning: { label: "预警", tone: "warning" },
  critical: { label: "故障", tone: "critical" },
  maintenance: { label: "维护", tone: "maintenance" },
  offline: { label: "离线", tone: "offline" },
  "communication-lost": { label: "通信中断", tone: "offline" },
};

function TurbineDrawer({
  turbine,
  onClose,
  demo,
}: {
  turbine: FleetTurbine;
  onClose: () => void;
  demo: boolean;
}) {
  const anomaly = demo && turbine.id === "WT-023";
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭机组概览" />
      <aside
        ref={dialogRef}
        tabIndex={-1}
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${turbine.id} 快速概览`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">风力发电机组</span>
            <h2>{turbine.id}</h2>
            <p>
              {turbine.manufacturer} · {turbine.model}
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="detail-drawer__status">
          <StatusBadge
            value={turbine.status}
            label={statusMeta[turbine.status].label}
            tone={statusMeta[turbine.status].tone}
            pulse={turbine.status === "running"}
          />
          <HealthBadge score={turbine.healthScore} />
          <span>
            {demo
              ? "演示快照"
              : turbine.updatedAt
                ? `更新于 ${new Date(turbine.updatedAt).toLocaleString("zh-CN")}`
                : "更新时间未记录"}
          </span>
        </div>

        {anomaly ? (
          <div className="drawer-alert">
            <span className="drawer-alert__icon">
              <Activity size={16} />
            </span>
            <span>
              <strong>AI 检测到主轴承早期退化</strong>
              <small>置信度 87% · 建议 72 小时内检查</small>
            </span>
            <Link href="/missions/MISSION-2026-0823">查看</Link>
          </div>
        ) : null}

        <section className="drawer-section">
          <h3>实时运行</h3>
          <div className="drawer-metrics">
            <div>
              <span>
                <Zap size={14} /> 有功功率
              </span>
              <strong>
                {demo || turbine.telemetryAvailable ? turbine.powerMW.toFixed(2) : "—"}{" "}
                <small>MW</small>
              </strong>
            </div>
            <div>
              <span>
                <Wind size={14} /> 风速
              </span>
              <strong>
                {demo || turbine.telemetryAvailable ? turbine.windSpeedMps.toFixed(1) : "—"}{" "}
                <small>m/s</small>
              </strong>
            </div>
            <div>
              <span>
                <Activity size={14} /> 转子转速
              </span>
              <strong>
                {demo || turbine.telemetryAvailable ? turbine.rotorSpeedRpm.toFixed(1) : "—"}{" "}
                <small>rpm</small>
              </strong>
            </div>
            <div>
              <span>
                <TowerControl size={14} /> 可利用率
              </span>
              <strong>
                {demo || turbine.availabilityAvailable
                  ? turbine.availabilityPercent.toFixed(1)
                  : "—"}{" "}
                <small>%</small>
              </strong>
            </div>
            <div>
              <span>
                <Activity size={14} /> 轴承振动
              </span>
              <strong>
                {demo
                  ? anomaly
                    ? "4.81"
                    : (2.1 + (turbine.gridPosition.column % 5) * 0.18).toFixed(2)
                  : "—"}{" "}
                <small>mm/s</small>
              </strong>
            </div>
            <div>
              <span>
                <Thermometer size={14} /> 轴承温度
              </span>
              <strong>
                {demo ? (anomaly ? "76.4" : (59 + turbine.gridPosition.row * 0.8).toFixed(1)) : "—"}{" "}
                <small>°C</small>
              </strong>
            </div>
          </div>
        </section>

        <section className="drawer-section">
          <div className="drawer-section__title">
            <h3>健康状态</h3>
            <strong>{turbine.healthScore}/100</strong>
          </div>
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
          <div className="key-value-list">
            <KeyValue
              label="主轴承"
              value={
                demo
                  ? anomaly
                    ? "63 · 退化"
                    : `${Math.min(98, turbine.healthScore + 1)} · 正常`
                  : "未配置部件健康数据"
              }
            />
            <KeyValue
              label="齿轮箱"
              value={
                demo ? `${Math.min(98, turbine.healthScore + 10)} · 正常` : "未配置部件健康数据"
              }
            />
            <KeyValue
              label="发电机"
              value={
                demo ? `${Math.min(99, turbine.healthScore + 12)} · 正常` : "未配置部件健康数据"
              }
            />
            <KeyValue label="活跃告警" value={`${turbine.activeAlarmCount} 条`} />
          </div>
        </section>

        <section className="drawer-section">
          <h3>维护信息</h3>
          <div className="key-value-list">
            <KeyValue
              label="上次维护"
              value={
                demo || turbine.lastMaintenanceRecorded
                  ? new Date(turbine.lastMaintenanceAt).toLocaleDateString("zh-CN")
                  : "未记录"
              }
            />
            <KeyValue
              label="下次巡检"
              value={
                demo || turbine.nextInspectionRecorded
                  ? new Date(turbine.nextInspectionAt).toLocaleDateString("zh-CN")
                  : "未排期"
              }
            />
            <KeyValue label="当前 Mission" value={turbine.currentMissionId ?? "—"} mono />
          </div>
        </section>

        <footer className="detail-drawer__footer">
          <Link
            className="button button--secondary button--md"
            href={`/diagnosis?turbineId=${turbine.id}`}
            title="打开该资产的诊断工作台；创建新 Mission 仍受服务器写入与人工门禁约束"
          >
            <BrainCircuit size={15} /> AI 诊断入口
          </Link>
          <Link
            className="button button--secondary button--md"
            href={`/work-orders?turbineId=${turbine.id}&intent=create`}
            title={
              demo
                ? "打开该资产的工单工作台；演示状态机管理 WT-023 主工单"
                : "打开该资产的生产工单工作台"
            }
          >
            <ClipboardPlus size={15} /> 工单创建入口
          </Link>
          <Link
            className="button button--secondary button--md"
            href={`/scada?turbineId=${turbine.id}&metric=main-bearing-vibration-rms`}
          >
            <Activity size={15} /> 查看该机组趋势
          </Link>
          <Link
            className="button button--secondary button--md"
            href={turbine.currentMissionId ? `/missions/${turbine.currentMissionId}` : "/missions"}
          >
            <Bot size={15} /> {turbine.currentMissionId ? "查看关联 Mission" : "查看 Mission 队列"}
          </Link>
          <Link
            className="button button--secondary button--md"
            href={`/work-orders?turbineId=${turbine.id}`}
          >
            <Wrench size={15} /> 查看相关工单
          </Link>
          <Link className="button button--primary button--md" href={`/turbines/${turbine.id}`}>
            进入机组详情 <ArrowRight size={15} />
          </Link>
        </footer>
      </aside>
    </>
  );
}

export function WindFarmPage({ runtimeMode }: { readonly runtimeMode: OpenVigilRuntimeMode }) {
  const workflow = useDemoWorkflow();
  const isProduction = runtimeMode === "production";
  const [view, setView] = useState<ViewMode>("cards");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | TurbineStatus>("all");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [minimumHealth, setMinimumHealth] = useState("0");
  const [maximumHealth, setMaximumHealth] = useState("100");
  const [alarmOnly, setAlarmOnly] = useState(false);
  const [missionOnly, setMissionOnly] = useState(false);
  const [geolocatedOnly, setGeolocatedOnly] = useState(false);
  const [selected, setSelected] = useState<FleetTurbine | null>(null);
  const fleetQuery = useQuery({
    queryKey: ["production-fleet"],
    queryFn: ({ signal }) => apiGet<FleetResponse>("/api/turbines", signal),
    enabled: isProduction,
    retry: false,
  });
  const displayTurbines = useMemo<readonly FleetTurbine[]>(
    () =>
      isProduction ? [...(fleetQuery.data?.data ?? [])] : overlayClientTurbines(turbines, workflow),
    [fleetQuery.data?.data, isProduction, workflow],
  );
  const displayAlarms = useMemo(
    () => (isProduction ? [] : overlayClientAlarms(alarms, workflow)),
    [isProduction, workflow],
  );
  const displayMissions = useMemo(
    () => (isProduction ? [] : overlayClientMissions(missions, workflow)),
    [isProduction, workflow],
  );
  const displayAgents = useMemo(
    () => (isProduction ? [] : overlayClientAgents(agents, workflow)),
    [isProduction, workflow],
  );
  const workflowKpis = useMemo(() => {
    if (isProduction && fleetQuery.data) {
      return {
        averageHealth: fleetQuery.data.meta.fleet.averageHealthScore,
        activeAlarmCount: fleetQuery.data.meta.fleet.activeAlarmCount,
        activeMissionCount: fleetQuery.data.meta.fleet.activeMissionCount,
        activeAgentCount: 0,
        onlineAgentCount: 0,
      };
    }
    return deriveWorkflowKpis(displayTurbines, displayAlarms, displayMissions, displayAgents);
  }, [
    displayAgents,
    displayAlarms,
    displayMissions,
    displayTurbines,
    fleetQuery.data,
    isProduction,
  ]);
  const productionFarm = fleetQuery.data?.meta.farms[0];
  const farmName = isProduction ? productionFarm?.name || "生产风场" : windFarm.name;
  const farmCode = isProduction ? productionFarm?.id || "未配置" : windFarm.code;
  const farmCapacityMW = isProduction ? productionFarm?.capacityMW : windFarm.totalCapacityMW;
  const turbineCount = displayTurbines.length;
  const productionFleet = fleetQuery.data?.meta.fleet;
  const filtered = useMemo(
    () =>
      displayTurbines.filter((turbine) => {
        const matchesQuery = turbine.id.toLowerCase().includes(query.trim().toLowerCase());
        const matchesStatus = status === "all" || turbine.status === status;
        const matchesHealth =
          turbine.healthScore >= Number(minimumHealth || 0) &&
          turbine.healthScore <= Number(maximumHealth || 100);
        const matchesAlarm = !alarmOnly || turbine.activeAlarmCount > 0;
        const matchesMission = !missionOnly || Boolean(turbine.currentMissionId);
        const matchesGeo = !geolocatedOnly || turbine.coordinatesConfigured === true;
        return (
          matchesQuery &&
          matchesStatus &&
          matchesHealth &&
          matchesAlarm &&
          matchesMission &&
          matchesGeo
        );
      }),
    [
      alarmOnly,
      displayTurbines,
      geolocatedOnly,
      maximumHealth,
      minimumHealth,
      missionOnly,
      query,
      status,
    ],
  );
  const positionedMapTurbines = useMemo(() => {
    const candidates = isProduction
      ? filtered.filter((turbine) => turbine.coordinatesConfigured)
      : filtered;
    if (!isProduction) {
      return candidates.map((turbine) => ({
        turbine,
        left: 7 + turbine.gridPosition.column * 10.7,
        top: 9 + turbine.gridPosition.row * 10.3,
      }));
    }
    const latitudes = candidates.map((turbine) => turbine.coordinates.latitude);
    const longitudes = candidates.map((turbine) => turbine.coordinates.longitude);
    const minimumLatitude = Math.min(...latitudes);
    const maximumLatitude = Math.max(...latitudes);
    const minimumLongitude = Math.min(...longitudes);
    const maximumLongitude = Math.max(...longitudes);
    const latitudeSpan = maximumLatitude - minimumLatitude || 1;
    const longitudeSpan = maximumLongitude - minimumLongitude || 1;
    return candidates.map((turbine) => ({
      turbine,
      left: 8 + ((turbine.coordinates.longitude - minimumLongitude) / longitudeSpan) * 84,
      top: 8 + ((maximumLatitude - turbine.coordinates.latitude) / latitudeSpan) * 84,
    }));
  }, [filtered, isProduction]);
  const columns = useMemo<LegacyColumnDef<FleetTurbine, unknown>[]>(
    () => [
      {
        accessorKey: "id",
        header: "机组",
        cell: ({ row }) => (
          <span className="asset-cell">
            <span className="asset-icon">
              <TowerControl size={15} />
            </span>
            <span>
              <strong>{row.original.id}</strong>
              <small>{row.original.model}</small>
            </span>
          </span>
        ),
      },
      {
        accessorKey: "status",
        header: "状态",
        cell: ({ row }) => (
          <StatusBadge
            value={row.original.status}
            label={statusMeta[row.original.status].label}
            tone={statusMeta[row.original.status].tone}
            compact
          />
        ),
      },
      {
        accessorKey: "powerMW",
        header: "有功功率",
        cell: ({ row }) => (
          <strong>
            {!isProduction || row.original.telemetryAvailable
              ? `${row.original.powerMW.toFixed(2)} MW`
              : "—"}
          </strong>
        ),
      },
      {
        accessorKey: "windSpeedMps",
        header: "风速",
        cell: ({ row }) =>
          !isProduction || row.original.telemetryAvailable
            ? `${row.original.windSpeedMps.toFixed(1)} m/s`
            : "—",
      },
      {
        accessorKey: "rotorSpeedRpm",
        header: "转子转速",
        cell: ({ row }) =>
          !isProduction || row.original.telemetryAvailable
            ? `${row.original.rotorSpeedRpm.toFixed(1)} rpm`
            : "—",
      },
      {
        accessorKey: "healthScore",
        header: "健康度",
        cell: ({ row }) => <HealthBadge score={row.original.healthScore} />,
      },
      { accessorKey: "activeAlarmCount", header: "告警" },
      {
        accessorKey: "currentMissionId",
        header: "当前 Mission",
        cell: ({ row }) => <span className="mono">{row.original.currentMissionId ?? "—"}</span>,
      },
      {
        accessorKey: "lastMaintenanceAt",
        header: "最近维护",
        cell: ({ row }) =>
          !isProduction || row.original.lastMaintenanceRecorded
            ? new Date(row.original.lastMaintenanceAt).toLocaleDateString("zh-CN")
            : "未记录",
      },
    ],
    [isProduction],
  );

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/wind-farms">
      <PageHeader
        eyebrow="资产与监测"
        title={farmName}
        description={`${farmCapacityMW ?? "—"} MW · ${turbineCount} 台风电机组的运行状态与健康概览`}
        breadcrumb={["资产与监测", "风场", farmCode]}
        meta={
          <>
            <StatusBadge
              value={isProduction && fleetQuery.isError ? "degraded" : "running"}
              label={isProduction && fleetQuery.isError ? "生产数据不可用" : "场站资产已连接"}
              tone={isProduction && fleetQuery.isError ? "critical" : "success"}
              pulse={!fleetQuery.isError}
            />
            <span className="page-meta-text">
              {isProduction
                ? productionFleet?.averageAvailabilityPercent == null
                  ? `遥测资产 ${productionFleet?.telemetryAssetCount ?? 0}/${turbineCount} · 可利用率未接入`
                  : `平均可利用率 ${productionFleet.averageAvailabilityPercent.toFixed(1)}% · 遥测资产 ${productionFleet.telemetryAssetCount}/${turbineCount}`
                : "场站可利用率 96.8% · 数据延迟 12s"}
            </span>
          </>
        }
        actions={
          <>
            <Link className="button button--secondary button--md" href="/health">
              <HeartPulse size={15} /> 设备健康矩阵
            </Link>
            <Link className="button button--primary button--md" href="/maintenance">
              <CalendarDays size={15} /> 查看维护计划
            </Link>
          </>
        }
      />

      {isProduction && fleetQuery.isLoading ? (
        <Card className="view-empty-state" role="status">
          正在读取生产资产、遥测、告警和任务快照…
        </Card>
      ) : null}

      {isProduction && fleetQuery.isError ? (
        <Card className="view-empty-state" role="alert">
          生产风场数据读取失败；页面已失败关闭，不会回退到演示资产。
        </Card>
      ) : null}

      <section className="farm-summary-bar">
        <div>
          <small>当前功率</small>
          <strong>
            {(isProduction
              ? (productionFleet?.currentPowerMW ?? 0)
              : windFarm.currentPowerMW
            ).toFixed(1)}{" "}
            <span>MW</span>
          </strong>
        </div>
        <div>
          <small>今日发电</small>
          <strong>
            {isProduction && !productionFleet?.generationAvailable
              ? "未接入"
              : windFarm.todayGenerationGWh.toFixed(2)}{" "}
            {isProduction && !productionFleet?.generationAvailable ? null : <span>GWh</span>}
          </strong>
        </div>
        <div>
          <small>并网机组</small>
          <strong>
            {
              displayTurbines.filter(
                (item) => !["maintenance", "offline", "communication-lost"].includes(item.status),
              ).length
            }{" "}
            <span>/ {turbineCount}</span>
          </strong>
        </div>
        <div>
          <small>平均健康度</small>
          <strong>
            {workflowKpis.averageHealth.toFixed(1)} <span>%</span>
          </strong>
        </div>
        <div>
          <small>活跃告警</small>
          <strong className="critical-text">{workflowKpis.activeAlarmCount}</strong>
        </div>
        <div>
          <small>AI Mission</small>
          <strong className="info-text">{workflowKpis.activeMissionCount}</strong>
        </div>
      </section>

      <section className="data-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索机组编号…"
            aria-label="搜索机组"
          />
        </div>
        <select
          className="select-field"
          value={status}
          onChange={(event) => setStatus(event.target.value as "all" | TurbineStatus)}
          aria-label="按状态筛选"
        >
          <option value="all">全部状态</option>
          <option value="running">运行</option>
          <option value="warning">预警</option>
          <option value="critical">故障</option>
          <option value="maintenance">维护</option>
          <option value="offline">离线</option>
          <option value="communication-lost">通信中断</option>
        </select>
        <Button
          variant="secondary"
          onClick={() => setAdvancedOpen((open) => !open)}
          aria-expanded={advancedOpen}
          aria-controls="wind-farm-advanced-filters"
        >
          <SlidersHorizontal size={14} /> 更多筛选
        </Button>
        <span className="toolbar-result">
          显示 {filtered.length} / {displayTurbines.length} 台机组
        </span>
        <div className="view-switcher" aria-label="视图切换">
          <button
            className={cn(view === "cards" && "active")}
            onClick={() => setView("cards")}
            aria-label="卡片视图"
          >
            <Grid2X2 size={15} />
          </button>
          <button
            className={cn(view === "list" && "active")}
            onClick={() => setView("list")}
            aria-label="列表视图"
          >
            <List size={15} />
          </button>
          <button
            className={cn(view === "topology" && "active")}
            onClick={() => setView("topology")}
            aria-label="拓扑视图"
          >
            <Network size={15} />
          </button>
          <button
            className={cn(view === "map" && "active")}
            onClick={() => setView("map")}
            aria-label="地图视图"
          >
            <Map size={15} />
          </button>
        </div>
      </section>

      {advancedOpen ? (
        <section
          id="wind-farm-advanced-filters"
          className="advanced-filter-panel"
          aria-label="风场高级筛选"
        >
          <label>
            <span>最低健康度</span>
            <input
              type="number"
              min="0"
              max="100"
              value={minimumHealth}
              onChange={(event) => setMinimumHealth(event.target.value)}
            />
          </label>
          <label>
            <span>最高健康度</span>
            <input
              type="number"
              min="0"
              max="100"
              value={maximumHealth}
              onChange={(event) => setMaximumHealth(event.target.value)}
            />
          </label>
          <label className="advanced-filter-panel__check">
            <input
              type="checkbox"
              checked={alarmOnly}
              onChange={(event) => setAlarmOnly(event.target.checked)}
            />
            <span>仅活跃告警</span>
          </label>
          <label className="advanced-filter-panel__check">
            <input
              type="checkbox"
              checked={missionOnly}
              onChange={(event) => setMissionOnly(event.target.checked)}
            />
            <span>仅活跃 Mission</span>
          </label>
          {isProduction ? (
            <label className="advanced-filter-panel__check">
              <input
                type="checkbox"
                checked={geolocatedOnly}
                onChange={(event) => setGeolocatedOnly(event.target.checked)}
              />
              <span>仅已配置坐标</span>
            </label>
          ) : null}
          <Button
            variant="ghost"
            onClick={() => {
              setMinimumHealth("0");
              setMaximumHealth("100");
              setAlarmOnly(false);
              setMissionOnly(false);
              setGeolocatedOnly(false);
            }}
          >
            清除高级筛选
          </Button>
        </section>
      ) : null}

      {view === "cards" ? (
        filtered.length ? (
          <section className="turbine-card-grid">
            {filtered.map((turbine) => (
              <button
                className={cn(
                  "turbine-card",
                  !isProduction && turbine.id === "WT-023" && "turbine-card--featured",
                )}
                onClick={() => setSelected(turbine)}
                key={turbine.id}
              >
                <span className="turbine-card__header">
                  <span>
                    <TowerControl size={15} />
                    <strong>{turbine.id}</strong>
                  </span>
                  <StatusBadge
                    value={turbine.status}
                    label={statusMeta[turbine.status].label}
                    tone={statusMeta[turbine.status].tone}
                    compact
                  />
                </span>
                <span className="turbine-card__power">
                  <strong>
                    {!isProduction || turbine.telemetryAvailable ? turbine.powerMW.toFixed(2) : "—"}
                  </strong>
                  <small>MW</small>
                </span>
                <span className="turbine-card__metrics">
                  <span>
                    <small>风速</small>
                    <strong>
                      {!isProduction || turbine.telemetryAvailable
                        ? `${turbine.windSpeedMps.toFixed(1)} m/s`
                        : "—"}
                    </strong>
                  </span>
                  <span>
                    <small>健康度</small>
                    <strong className={turbine.healthScore < 75 ? "critical-text" : ""}>
                      {turbine.healthScore}
                    </strong>
                  </span>
                  <span>
                    <small>告警</small>
                    <strong>{turbine.activeAlarmCount}</strong>
                  </span>
                </span>
                <span className="turbine-card__footer">
                  <span>
                    {turbine.currentMissionId
                      ? "AI Mission 进行中"
                      : isProduction
                        ? "无活跃 Mission"
                        : "运行稳定"}
                  </span>
                  <ArrowRight size={13} />
                </span>
              </button>
            ))}
          </section>
        ) : (
          <Card className="view-empty-state" role="status">
            当前筛选下没有机组卡片，请清除筛选后重试。
          </Card>
        )
      ) : null}

      {view === "list" ? (
        <Card className="data-table-card">
          <DataTable
            bulkActions={[
              {
                label: "复制资产 ID",
                onActivate: async (rows) =>
                  navigator.clipboard.writeText(rows.map((row) => row.id).join(", ")),
              },
            ]}
            columns={columns}
            csvExport={{
              filename: "openvigil-turbines.csv",
              columns: [
                { label: "风机", value: (row) => row.id },
                { label: "状态", value: (row) => statusMeta[row.status].label },
                { label: "功率 MW", value: (row) => row.powerMW },
                { label: "风速 m/s", value: (row) => row.windSpeedMps },
                { label: "健康度", value: (row) => row.healthScore },
                { label: "告警数", value: (row) => row.activeAlarmCount },
                { label: "Mission", value: (row) => row.currentMissionId },
                { label: "最近维护", value: (row) => row.lastMaintenanceAt },
              ],
            }}
            data={filtered}
            emptyMessage="没有符合当前状态筛选的机组"
            getRowId={(turbine) => turbine.id}
            initialSorting={[{ id: "id", desc: false }]}
            pageSize={8}
            searchPlaceholder="在当前结果中搜索机组、状态或 Mission…"
            searchTextForRow={(turbine) =>
              [turbine.id, turbine.status, turbine.model, turbine.currentMissionId ?? ""].join(" ")
            }
            selectedRowId={selected?.id}
            onRowActivate={setSelected}
          />
        </Card>
      ) : null}

      {view === "topology" ? (
        <Card className="topology-panel">
          <div className="topology-header">
            <span>
              <Network size={16} />
              <strong>风场阵列拓扑</strong>
            </span>
            <span className="topology-legend">
              <i className="summary-dot summary-dot--success" /> 运行{" "}
              <i className="summary-dot summary-dot--warning" /> 预警{" "}
              <i className="summary-dot summary-dot--critical" /> 故障
            </span>
          </div>
          {filtered.length ? (
            <div className="topology-grid">
              {filtered.map((turbine) => (
                <button
                  className={cn(
                    "topology-node",
                    `topology-node--${statusMeta[turbine.status].tone}`,
                    turbine.id === "WT-023" && "topology-node--selected",
                  )}
                  key={turbine.id}
                  onClick={() => setSelected(turbine)}
                >
                  <TowerControl size={14} />
                  <strong>{turbine.id}</strong>
                  <small>
                    {turbine.powerMW.toFixed(1)} MW · H{turbine.healthScore}
                  </small>
                </button>
              ))}
            </div>
          ) : (
            <div className="view-empty-state" role="status">
              当前筛选下没有可绘制的拓扑节点。
            </div>
          )}
        </Card>
      ) : null}

      {view === "map" ? (
        <Card className="farm-map">
          <div className="farm-map__labels">
            <span>
              <Map size={15} /> {isProduction ? `${farmName} · GIS 资产位置` : "近海阵列 A 区"}
            </span>
            <small>
              {isProduction
                ? `${positionedMapTurbines.length}/${filtered.length} 台资产已配置经纬度`
                : "121.3°E · 31.0°N · 示意视图"}
            </small>
          </div>
          <div className="farm-map__watermark">东海</div>
          {positionedMapTurbines.length ? (
            positionedMapTurbines.map(({ turbine, left, top }) => (
              <button
                key={turbine.id}
                onClick={() => setSelected(turbine)}
                className={cn("map-node", `map-node--${statusMeta[turbine.status].tone}`)}
                style={{
                  left: `${left}%`,
                  top: `${top}%`,
                }}
                title={`${turbine.id} · ${statusMeta[turbine.status].label}`}
              >
                <TowerControl size={12} />
                <span>{turbine.id}</span>
              </button>
            ))
          ) : (
            <div className="view-empty-state" role="status">
              当前筛选下没有可定位的地图资产。
            </div>
          )}
        </Card>
      ) : null}

      {selected ? (
        <TurbineDrawer
          turbine={selected}
          demo={runtimeMode === "demo"}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </AppShell>
  );
}
