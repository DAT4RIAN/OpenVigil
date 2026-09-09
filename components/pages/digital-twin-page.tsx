"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Box,
  CircleGauge,
  CloudSun,
  Database,
  GitBranch,
  Radio,
  RefreshCw,
  ShieldAlert,
  TowerControl,
  Wrench,
  Zap,
} from "lucide-react";

import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState, Progress } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import { buildDigitalTwinSnapshot, type DigitalTwinSnapshot } from "@/lib/digital-twin-data";
import { turbines } from "@/lib/farm-data";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";

import styles from "./digital-twin-page.module.css";

type DigitalTwinResponse = {
  readonly data: DigitalTwinSnapshot;
  readonly meta: {
    readonly turbineId: string;
    readonly snapshotAt: string;
    readonly deterministic: true;
    readonly readOnly: true;
    readonly workflowPersistence: "d1" | "ephemeral" | null;
    readonly workflowRevision: number;
  };
};

const stateTone = (state: string) =>
  state === "critical" || state === "degraded"
    ? "critical"
    : state === "watch" || state === "maintenance"
      ? "warning"
      : state === "offline"
        ? "neutral"
        : "success";

const stateLabel: Record<string, string> = {
  healthy: "健康",
  watch: "关注",
  degraded: "退化",
  critical: "严重",
  maintenance: "维护",
  offline: "离线",
};

function realtimeSignalValues(frame: ReturnType<typeof useRealtimeChannel>["frame"]) {
  if (!frame || frame.channel !== "scada" || frame.data.turbineId !== "WT-023") return new Map();
  const values = Array.isArray(frame.data.values) ? frame.data.values : [];
  return new Map(
    values.flatMap((candidate) => {
      if (!candidate || typeof candidate !== "object") return [];
      const value = candidate as Record<string, unknown>;
      return typeof value.metric === "string" && typeof value.value === "number"
        ? [[value.metric, value.value] as const]
        : [];
    }),
  );
}

function TurbineSchematic({
  selectedKey,
  healthScore,
}: {
  selectedKey: string;
  healthScore: number;
}) {
  return (
    <div className={styles.schematic} aria-label="风机数字孪生二维结构模型">
      <div className={styles.schematicGrid} />
      <svg viewBox="0 0 520 520" role="img" aria-label="海上风机侧视结构">
        <defs>
          <linearGradient id="tower-fill" x1="0" x2="1">
            <stop offset="0" stopColor="var(--surface-elevated)" />
            <stop offset="0.55" stopColor="var(--border-strong)" />
            <stop offset="1" stopColor="var(--surface-elevated)" />
          </linearGradient>
          <filter id="twin-glow">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path className={styles.sea} d="M25 470 Q85 453 145 470 T265 470 T385 470 T505 470" />
        <path className={styles.foundation} d="M231 443 L291 443 L310 486 L211 486 Z" />
        <path className={styles.tower} d="M245 425 L278 425 L270 198 L253 198 Z" />
        <rect className={styles.nacelle} x="244" y="175" width="108" height="37" rx="8" />
        <circle className={styles.hub} cx="238" cy="194" r="21" />
        <g className={styles.blades} transform="translate(238 194)">
          <path d="M0 -14 C-21 -92 -39 -142 -30 -151 C-14 -148 -2 -87 6 -15 Z" />
          <path d="M12 8 C85 34 137 58 138 71 C128 82 74 52 6 19 Z" />
          <path d="M-12 8 C-60 70 -96 112 -110 107 C-118 94 -77 48 -5 -2 Z" />
        </g>
        <circle className={styles.rotorAxis} cx="238" cy="194" r="7" />
        <g className={styles.signalArcs} filter="url(#twin-glow)">
          <path d="M370 210 Q420 246 394 304" />
          <path d="M388 191 Q459 242 420 323" />
          <path d="M405 171 Q496 239 446 342" />
        </g>
      </svg>
      <span className={styles.modelTag}>OPERATIONAL TWIN · 2D</span>
      <span className={styles.modelHealth}>
        <small>ASSET HEALTH</small>
        <strong>{healthScore}</strong>
      </span>
      <span
        className={`${styles.hotspot} ${styles.hotspotRotor}`}
        data-active={selectedKey === "main-bearing"}
      >
        主轴承
      </span>
      <span
        className={`${styles.hotspot} ${styles.hotspotBlade}`}
        data-active={selectedKey === "blades"}
      >
        叶片
      </span>
      <span
        className={`${styles.hotspot} ${styles.hotspotGenerator}`}
        data-active={selectedKey === "generator"}
      >
        传动链
      </span>
      <span
        className={`${styles.hotspot} ${styles.hotspotTower}`}
        data-active={selectedKey.includes("tower")}
      >
        塔架
      </span>
    </div>
  );
}

export function DigitalTwinPage() {
  const [turbineId, setTurbineId] = useState("WT-023");
  const [selectedKey, setSelectedKey] = useState("main-bearing");
  const realtime = useRealtimeChannel("scada", turbineId === "WT-023");
  const fallbackResponse = useMemo<DigitalTwinResponse>(() => {
    const snapshot = buildDigitalTwinSnapshot(turbineId)!;
    return {
      data: snapshot,
      meta: {
        turbineId,
        snapshotAt: snapshot.snapshotAt,
        deterministic: true,
        readOnly: true,
        workflowPersistence: null,
        workflowRevision: 0,
      },
    };
  }, [turbineId]);
  const twinQuery = useQuery({
    queryKey: ["digital-twin", turbineId],
    queryFn: ({ signal }) =>
      apiGet<DigitalTwinResponse>(`/api/digital-twin?turbineId=${turbineId}`, signal),
    staleTime: 0,
  });
  const response = twinQuery.data ?? fallbackResponse;
  const snapshot = response.data;

  useEffect(() => {
    const deepLinked = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!deepLinked || !turbines.some((turbine) => turbine.id === deepLinked)) return;
    const timer = window.setTimeout(() => setTurbineId(deepLinked), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const subsystems = snapshot.subsystems;
    if (subsystems.some((subsystem) => subsystem.key === selectedKey)) return;
    const timer = window.setTimeout(() => setSelectedKey(subsystems[0]?.key ?? ""), 0);
    return () => window.clearTimeout(timer);
  }, [selectedKey, snapshot.subsystems]);

  const selected =
    snapshot.subsystems.find((subsystem) => subsystem.key === selectedKey) ??
    snapshot.subsystems[0];
  const liveValues = useMemo(() => realtimeSignalValues(realtime.frame), [realtime.frame]);
  const signals = snapshot.signals.map((signal) => ({
    ...signal,
    value: liveValues.get(signal.metric) ?? signal.value,
  }));
  const sourceLabel = !twinQuery.data
    ? "LOCAL"
    : snapshot.model.source === "fixture"
      ? "FIXTURE"
      : response.meta.workflowPersistence === "d1"
        ? "D1"
        : "EPHEMERAL";
  const sourceDetail = !twinQuery.data
    ? `${snapshot.turbine.id} · same-asset fallback`
    : snapshot.model.source === "fixture"
      ? `${snapshot.turbine.id} · deterministic fixture`
      : `${response.meta.workflowPersistence} · revision ${response.meta.workflowRevision}`;

  return (
    <AppShell activePath="/digital-twin">
      <PageHeader
        eyebrow="ASSET INTELLIGENCE"
        title="数字孪生"
        description="把资产结构、SCADA、健康评估、告警与执行上下文汇聚到同一可追溯视图。"
        breadcrumb={["知识与数据", "数字孪生", turbineId]}
        meta={
          <>
            <StatusBadge
              value={realtime.status}
              label={turbineId === "WT-023" ? `WS · ${realtime.status.toUpperCase()}` : "FIXTURE"}
              tone={realtime.status === "connected" ? "success" : "warning"}
              pulse={realtime.status === "connected"}
            />
            <StatusBadge value="read-only" label="READ ONLY" tone="neutral" />
            <span className="page-meta-text">非物理仿真 · 确定性运营孪生</span>
          </>
        }
        actions={
          <>
            <label className={styles.assetSelector}>
              <span>资产</span>
              <select value={turbineId} onChange={(event) => setTurbineId(event.target.value)}>
                {turbines.map((turbine) => (
                  <option value={turbine.id} key={turbine.id}>
                    {turbine.id} · {turbine.status}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="secondary"
              loading={twinQuery.isFetching}
              onClick={() => void twinQuery.refetch()}
            >
              <RefreshCw size={15} /> 刷新孪生
            </Button>
          </>
        }
      />

      {twinQuery.isError ? (
        <div className={styles.errorState}>
          <EmptyState
            icon={<Database size={21} />}
            title="数字孪生同步失败"
            description="当前显示所选资产的本地确定性快照。可重试 API 同步。"
          />
          <Button onClick={() => void twinQuery.refetch()}>重试同步</Button>
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="数字孪生关键指标">
        <Card>
          <span>
            <Zap size={16} /> 当前功率
          </span>
          <strong>
            {snapshot.turbine.powerMW.toFixed(2)} <small>MW</small>
          </strong>
          <em>{snapshot.turbine.model}</em>
        </Card>
        <Card>
          <span>
            <CircleGauge size={16} /> 整机健康
          </span>
          <strong>
            {snapshot.turbine.healthScore} <small>/ 100</small>
          </strong>
          <HealthBadge score={snapshot.turbine.healthScore} />
        </Card>
        <Card>
          <span>
            <ShieldAlert size={16} /> 活跃告警
          </span>
          <strong>{snapshot.context.activeAlarmCount}</strong>
          <Link href={`/alarms?turbineId=${turbineId}`}>
            查看告警 <ArrowRight size={12} />
          </Link>
        </Card>
        <Card>
          <span>
            <Radio size={16} /> 同步源
          </span>
          <strong>{sourceLabel}</strong>
          <em>{sourceDetail}</em>
        </Card>
      </section>

      <section className={styles.workspace}>
        <Card className={styles.modelPanel}>
          <CardHeader
            eyebrow={`${snapshot.turbine.id} · ${snapshot.turbine.manufacturer}`}
            title="资产结构与状态热点"
            description="选择右侧子系统，联动查看健康、风险和传感器上下文。"
          />
          <TurbineSchematic
            selectedKey={selected?.key ?? ""}
            healthScore={snapshot.turbine.healthScore}
          />
        </Card>

        <Card className={styles.subsystemPanel}>
          <CardHeader
            eyebrow="12 SUBSYSTEMS"
            title="子系统状态"
            description="健康评分、告警与预测信号"
          />
          <div className={styles.subsystemList}>
            {snapshot.subsystems.map((subsystem) => (
              <button
                type="button"
                className={selected?.key === subsystem.key ? styles.selectedSubsystem : undefined}
                aria-pressed={selected?.key === subsystem.key}
                onClick={() => setSelectedKey(subsystem.key)}
                key={subsystem.key}
              >
                <span>
                  <Box size={14} />
                  <strong>{subsystem.name}</strong>
                  <small>{subsystem.alertCount} 告警</small>
                </span>
                <span>
                  <b>{subsystem.healthScore}</b>
                  <StatusBadge
                    value={subsystem.state}
                    label={stateLabel[subsystem.state] ?? subsystem.state}
                    tone={stateTone(subsystem.state)}
                    compact
                  />
                </span>
              </button>
            ))}
          </div>
        </Card>

        <Card className={styles.inspectorPanel}>
          {selected ? (
            <>
              <CardHeader
                eyebrow="SELECTED NODE"
                title={selected.name}
                description={selected.primaryFinding}
                action={<StatusBadge value={selected.state} tone={stateTone(selected.state)} />}
              />
              <div className={styles.healthFocus}>
                <div>
                  <HealthBadge score={selected.healthScore} />
                  <strong>{selected.healthScore}</strong>
                  <small>HEALTH / 100</small>
                </div>
                <Progress
                  value={selected.healthScore}
                  tone={
                    selected.healthScore >= 90
                      ? "success"
                      : selected.healthScore >= 75
                        ? "warning"
                        : "critical"
                  }
                />
              </div>
              <div className={styles.riskMetrics}>
                <span>
                  <small>30D 失效概率</small>
                  <strong>{selected.failureProbability30d}%</strong>
                </span>
                <span>
                  <small>估计 RUL</small>
                  <strong>{selected.remainingUsefulLifeDays ?? "—"} 天</strong>
                </span>
                <span>
                  <small>Anomaly</small>
                  <strong>{selected.anomalyScore.toFixed(2)}</strong>
                </span>
                <span>
                  <small>关联告警</small>
                  <strong>{selected.alertCount}</strong>
                </span>
              </div>
              <div className={styles.inspectorActions}>
                <Link href={`/scada?turbineId=${turbineId}`}>
                  <Activity size={14} /> 查看 SCADA
                </Link>
                <Link href={`/predictive-maintenance?turbineId=${turbineId}`}>
                  <CircleGauge size={14} /> 查看预测
                </Link>
              </div>
            </>
          ) : null}
        </Card>
      </section>

      <section className={styles.lowerGrid}>
        <Card className={styles.signalsPanel}>
          <CardHeader
            eyebrow="OBSERVABLE SIGNALS"
            title="传感器同步"
            description={
              turbineId === "WT-023"
                ? "WebSocket 帧覆盖 API 快照中的同名测点"
                : "通用资产确定性运行快照"
            }
          />
          <div className={styles.signalGrid}>
            {signals.map((signal) => (
              <div data-anomaly={signal.isAnomaly} key={signal.metric}>
                <span>{signal.label}</span>
                <strong>
                  {signal.value.toFixed(2)} <small>{signal.unit}</small>
                </strong>
                <em>{signal.quality.toUpperCase()}</em>
              </div>
            ))}
          </div>
        </Card>

        <Card className={styles.contextPanel}>
          <CardHeader
            eyebrow="OPERATIONAL CONTEXT"
            title="关联执行上下文"
            description="Mission、工单与天气窗口的同源状态"
          />
          <div className={styles.contextList}>
            <Link
              href={
                snapshot.context.missionId ? `/missions/${snapshot.context.missionId}` : "/missions"
              }
            >
              <GitBranch size={17} />
              <span>
                <small>Mission</small>
                <strong>{snapshot.context.missionId ?? "暂无关联"}</strong>
              </span>
              <StatusBadge value={snapshot.context.missionStatus ?? "idle"} compact />
            </Link>
            <Link
              href={
                snapshot.context.workOrderId
                  ? `/work-orders?workOrder=${snapshot.context.workOrderId}`
                  : "/work-orders"
              }
            >
              <Wrench size={17} />
              <span>
                <small>Work Order</small>
                <strong>{snapshot.context.workOrderId ?? "暂无关联"}</strong>
              </span>
              <StatusBadge value={snapshot.context.workOrderStatus ?? "idle"} compact />
            </Link>
            <Link href="/resources">
              <CloudSun size={17} />
              <span>
                <small>Weather Window</small>
                <strong>{snapshot.context.nextWeatherWindowId ?? "暂无窗口"}</strong>
              </span>
              <StatusBadge
                value={snapshot.context.nextWeatherWindowSuitability ?? "unknown"}
                compact
              />
            </Link>
            <Link href={`/turbines/${turbineId}`}>
              <TowerControl size={17} />
              <span>
                <small>Asset Record</small>
                <strong>{turbineId}</strong>
              </span>
              <ArrowRight size={14} />
            </Link>
          </div>
          <p className={styles.modelNotice}>
            该页面是只读运营数字孪生：聚合确定性资产、SCADA
            与工作流状态；同步源以上方持久化标签为准，不执行真实物理仿真或控制指令。
          </p>
        </Card>
      </section>
    </AppShell>
  );
}
