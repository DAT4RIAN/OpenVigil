"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { apiGet, apiPost } from "@/lib/api-client";
import { buildDigitalTwinSnapshot, type DigitalTwinSnapshot } from "@/lib/digital-twin-data";
import { turbines } from "@/lib/farm-data";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { localizedMetricLabel } from "@/lib/ui-localization";
import { localizedStatusLabel } from "@/lib/ui-localization";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

import styles from "./digital-twin-page.module.css";
import { TwinModelViewer } from "./twin-model-viewer";

type DigitalTwinResponse = {
  readonly data: DigitalTwinSnapshot;
  readonly meta: {
    readonly turbineId: string;
    readonly snapshotAt: string;
    readonly deterministic: boolean;
    readonly readOnly: true;
    readonly workflowPersistence: "d1" | "ephemeral" | "postgresql" | null;
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
      <span className={styles.modelTag}>运营数字孪生 · 2D</span>
      <span className={styles.modelHealth}>
        <small>资产健康度</small>
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

type TurbineCollectionResponse = {
  readonly data: readonly {
    readonly id: string;
    readonly status: string;
  }[];
};

type TwinArtifactUpload = {
  readonly artifact_uri: string;
  readonly upload_url: string;
  readonly required_headers: Readonly<Record<string, string>>;
};

const twinContentType = (file: File): string => {
  if (file.type) return file.type;
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".gltf")) return "model/gltf+json";
  if (lower.endsWith(".glb")) return "model/gltf-binary";
  if (lower.endsWith(".zip")) return "application/zip";
  return "application/octet-stream";
};

const sha256Hex = async (file: File): Promise<string> => {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
};

export function DigitalTwinPage({ runtimeMode }: { runtimeMode: OpenVigilRuntimeMode }) {
  const isProduction = runtimeMode === "production";
  const [turbineId, setTurbineId] = useState("WT-023");
  const [selectedKey, setSelectedKey] = useState("main-bearing");
  const [manufacturer, setManufacturer] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [elevationM, setElevationM] = useState("0");
  const [coordinateReferenceSystem, setCoordinateReferenceSystem] = useState("EPSG:4326");
  const [geometryFile, setGeometryFile] = useState<File | null>(null);
  const [profileReason, setProfileReason] = useState("");
  const queryClient = useQueryClient();
  const realtime = useRealtimeChannel("scada", !isProduction && turbineId === "WT-023");
  const productionStream = useProductionEvents({
    enabled: isProduction,
    eventTypes: [
      "scada.sample.accepted",
      "alarm.opened",
      "alarm.acknowledged",
      "alarm.assigned",
      "alarm.unassigned",
      "alarm.resolved",
      "mission.created",
      "mission.review_ready",
      "work_order.created",
      "work_order.task.completed",
      "work_order.completed",
      "asset.twin-profile.updated",
    ],
    cursorKey: "windops.production-events.digital-twin.v1",
    minimumDispatchIntervalMs: 1_000,
    onReady: () => void queryClient.invalidateQueries({ queryKey: ["digital-twin", turbineId] }),
    onEvent: () => {
      void queryClient.invalidateQueries({ queryKey: ["digital-twin", turbineId] });
      void queryClient.invalidateQueries({ queryKey: ["digital-twin-assets"] });
    },
  });
  const assetsQuery = useQuery({
    queryKey: ["digital-twin-assets", runtimeMode],
    queryFn: ({ signal }) => apiGet<TurbineCollectionResponse>("/api/turbines", signal),
    enabled: isProduction,
  });
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
  const unavailableResponse = useMemo<DigitalTwinResponse>(
    () => ({
      data: {
        turbine: {
          id: turbineId,
          model: "unavailable",
          manufacturer: "unavailable",
          status: "offline",
          powerMW: 0,
          windSpeedMps: 0,
          healthScore: 0,
          latitude: null,
          longitude: null,
        },
        subsystems: [],
        signals: [],
        context: {
          activeAlarmCount: 0,
          missionId: null,
          missionStatus: null,
          workOrderId: null,
          workOrderStatus: null,
          nextWeatherWindowId: null,
          nextWeatherWindowSuitability: null,
        },
        model: {
          mode: "unavailable",
          realPhysicsSimulation: false,
          readOnly: true,
          source: "unavailable",
        },
        snapshotAt: new Date(0).toISOString(),
      },
      meta: {
        turbineId,
        snapshotAt: new Date(0).toISOString(),
        deterministic: false,
        readOnly: true,
        workflowPersistence: null,
        workflowRevision: 0,
      },
    }),
    [turbineId],
  );
  const response = twinQuery.data ?? (isProduction ? unavailableResponse : fallbackResponse);
  const snapshot = response.data;
  const profileMutation = useMutation({
    mutationFn: async () => {
      if (!geometryFile) throw new Error("请选择 GLB、glTF 或 ZIP 几何制品。");
      const artifactSha256 = await sha256Hex(geometryFile);
      const contentType = twinContentType(geometryFile);
      const upload = await apiPost<TwinArtifactUpload>(
        `/api/backend/turbines/${encodeURIComponent(turbineId)}/twin-profile/artifacts/presign`,
        {
          file_name: geometryFile.name,
          content_type: contentType,
          artifact_sha256: artifactSha256,
        },
      );
      const uploaded = await fetch(upload.upload_url, {
        method: "PUT",
        headers: upload.required_headers,
        body: geometryFile,
      });
      if (!uploaded.ok) throw new Error(`几何制品上传失败（HTTP ${uploaded.status}）。`);
      return apiPost(`/api/backend/turbines/${encodeURIComponent(turbineId)}/twin-profile`, {
        manufacturer: manufacturer.trim(),
        latitude: Number(latitude),
        longitude: Number(longitude),
        elevation_m: Number(elevationM),
        coordinate_reference_system: coordinateReferenceSystem.trim(),
        geometry_uri: upload.artifact_uri,
        geometry_sha256: artifactSha256,
        expected_updated_at: snapshot.model.profileUpdatedAt ?? null,
        reason: profileReason.trim(),
      });
    },
    onSuccess: async () => {
      setGeometryFile(null);
      setProfileReason("");
      await queryClient.invalidateQueries({ queryKey: ["digital-twin", turbineId] });
    },
  });

  useEffect(() => {
    const deepLinked = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!deepLinked || !/^WT-[A-Z0-9-]+$/.test(deepLinked)) return;
    const timer = window.setTimeout(() => setTurbineId(deepLinked), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!isProduction || !assetsQuery.data?.data.length) return;
    if (assetsQuery.data.data.some((asset) => asset.id === turbineId)) return;
    const timer = window.setTimeout(() => setTurbineId(assetsQuery.data.data[0].id), 0);
    return () => window.clearTimeout(timer);
  }, [assetsQuery.data, isProduction, turbineId]);

  useEffect(() => {
    const subsystems = snapshot.subsystems;
    if (subsystems.some((subsystem) => subsystem.key === selectedKey)) return;
    const timer = window.setTimeout(() => setSelectedKey(subsystems[0]?.key ?? ""), 0);
    return () => window.clearTimeout(timer);
  }, [selectedKey, snapshot.subsystems]);

  useEffect(() => {
    if (!isProduction) return;
    const timer = window.setTimeout(() => {
      setManufacturer(
        snapshot.turbine.manufacturer === "unconfigured" ? "" : snapshot.turbine.manufacturer,
      );
      setLatitude(snapshot.turbine.latitude?.toString() ?? "");
      setLongitude(snapshot.turbine.longitude?.toString() ?? "");
      setElevationM(snapshot.model.elevationM?.toString() ?? "0");
      setCoordinateReferenceSystem(snapshot.model.coordinateReferenceSystem ?? "EPSG:4326");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    isProduction,
    snapshot.model.coordinateReferenceSystem,
    snapshot.model.elevationM,
    snapshot.turbine.latitude,
    snapshot.turbine.longitude,
    snapshot.turbine.manufacturer,
  ]);

  const selected =
    snapshot.subsystems.find((subsystem) => subsystem.key === selectedKey) ??
    snapshot.subsystems[0];
  const liveValues = useMemo(() => realtimeSignalValues(realtime.frame), [realtime.frame]);
  const signals = snapshot.signals.map((signal) => ({
    ...signal,
    value: liveValues.get(signal.metric) ?? signal.value,
  }));
  const sourceLabel =
    isProduction && twinQuery.data
      ? "PostgreSQL / TimescaleDB"
      : !twinQuery.data
        ? isProduction
          ? "不可用"
          : "本地"
        : snapshot.model.source === "fixture"
          ? "演示数据"
          : response.meta.workflowPersistence === "d1"
            ? "D1"
            : "临时状态";
  const sourceDetail =
    isProduction && twinQuery.data
      ? `${snapshot.turbine.id} · 权威资产、遥测与工作流快照`
      : !twinQuery.data
        ? isProduction
          ? `${snapshot.turbine.id} · 生产模式已停止展示`
          : `${snapshot.turbine.id} · 同资产降级快照`
        : snapshot.model.source === "fixture"
          ? `${snapshot.turbine.id} · 确定性演示数据`
          : `${response.meta.workflowPersistence} · 修订 ${response.meta.workflowRevision}`;

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/digital-twin">
      <PageHeader
        eyebrow="资产智能"
        title="数字孪生"
        description="把资产结构、SCADA、健康评估、告警与执行上下文汇聚到同一可追溯视图。"
        breadcrumb={["知识与数据", "数字孪生", turbineId]}
        meta={
          <>
            <StatusBadge
              value={isProduction ? productionStream.status : realtime.status}
              label={
                isProduction
                  ? productionStream.status === "connected"
                    ? `SSE 实时 · 游标 ${productionStream.cursor ?? "同步中"}`
                    : twinQuery.isError
                      ? "权威数据不可用"
                      : "SSE 重连中 · TimescaleDB 快照"
                  : turbineId === "WT-023"
                    ? `WS · ${realtime.status === "connected" ? "已连接" : "连接中"}`
                    : "演示数据"
              }
              tone={
                (isProduction ? productionStream.status : realtime.status) === "connected"
                  ? "success"
                  : "warning"
              }
              pulse={(isProduction ? productionStream.status : realtime.status) === "connected"}
            />
            <StatusBadge value="read-only" label="只读" tone="neutral" />
            <span className="page-meta-text">
              非物理仿真 · {isProduction ? "可追溯运营状态孪生" : "确定性运营孪生"}
            </span>
          </>
        }
        actions={
          <>
            <label className={styles.assetSelector}>
              <span>资产</span>
              <select value={turbineId} onChange={(event) => setTurbineId(event.target.value)}>
                {(isProduction ? (assetsQuery.data?.data ?? []) : turbines).map((turbine) => (
                  <option value={turbine.id} key={turbine.id}>
                    {turbine.id} · {localizedStatusLabel(turbine.status)}
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
            description={
              isProduction
                ? "生产模式不会回退到本地演示孪生；请恢复 Python 后端或遥测依赖。"
                : "当前显示所选资产的本地确定性快照。可重试 API 同步。"
            }
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
            eyebrow="12 个子系统"
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
                eyebrow="已选节点"
                title={selected.name}
                description={selected.primaryFinding}
                action={<StatusBadge value={selected.state} tone={stateTone(selected.state)} />}
              />
              <div className={styles.healthFocus}>
                <div>
                  <HealthBadge score={selected.healthScore} />
                  <strong>{selected.healthScore}</strong>
                  <small>健康度 / 100</small>
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
                  <small>异常分数</small>
                  <strong>{selected.anomalyScore.toFixed(2)}</strong>
                </span>
                <span>
                  <small>健康趋势</small>
                  <strong>{selected.state === "healthy" ? "稳定" : "需关注"}</strong>
                </span>
                <span>
                  <small>健康评分</small>
                  <strong>{selected.healthScore} / 100</strong>
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
        {isProduction && snapshot.model.geometryConfigured ? (
          <TwinModelViewer turbineId={turbineId} />
        ) : null}
        {isProduction ? (
          <Card className={styles.contextPanel}>
            <CardHeader
              eyebrow="资产孪生制品治理"
              title="GIS 与三维模型档案"
              description="上传内容寻址的 GLB/glTF 制品并绑定真实坐标；后端会验证 MinIO 对象、内容类型和 SHA-256 后才激活档案。"
              action={
                <StatusBadge
                  value={snapshot.model.geometryConfigured ? "configured" : "unconfigured"}
                  label={snapshot.model.geometryConfigured ? "制品已验证" : "尚未配置"}
                  tone={snapshot.model.geometryConfigured ? "success" : "warning"}
                />
              }
            />
            <label>
              <span>制造商</span>
              <input
                value={manufacturer}
                onChange={(event) => setManufacturer(event.target.value)}
                placeholder="Goldwind"
              />
            </label>
            <label>
              <span>纬度</span>
              <input
                type="number"
                step="any"
                value={latitude}
                onChange={(event) => setLatitude(event.target.value)}
              />
            </label>
            <label>
              <span>经度</span>
              <input
                type="number"
                step="any"
                value={longitude}
                onChange={(event) => setLongitude(event.target.value)}
              />
            </label>
            <label>
              <span>高程（m）</span>
              <input
                type="number"
                step="any"
                value={elevationM}
                onChange={(event) => setElevationM(event.target.value)}
              />
            </label>
            <label>
              <span>坐标参考系</span>
              <input
                value={coordinateReferenceSystem}
                onChange={(event) => setCoordinateReferenceSystem(event.target.value)}
              />
            </label>
            <label>
              <span>几何制品</span>
              <input
                type="file"
                accept=".glb,.gltf,.zip,model/gltf-binary,model/gltf+json,application/zip"
                onChange={(event) => setGeometryFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <label>
              <span>变更原因</span>
              <input
                value={profileReason}
                onChange={(event) => setProfileReason(event.target.value)}
                placeholder="关联资产档案或工程变更单"
              />
            </label>
            {profileMutation.error instanceof Error ? (
              <p role="alert">{profileMutation.error.message}</p>
            ) : null}
            <Button
              loading={profileMutation.isPending}
              disabled={
                !geometryFile ||
                manufacturer.trim().length < 2 ||
                !Number.isFinite(Number(latitude)) ||
                !Number.isFinite(Number(longitude)) ||
                profileReason.trim().length < 3
              }
              onClick={() => profileMutation.mutate()}
            >
              上传并激活孪生档案
            </Button>
            {snapshot.model.geometryUri ? (
              <p className={styles.modelNotice}>
                已验证对象：{snapshot.model.geometryUri} · SHA-256 {snapshot.model.geometrySha256}
              </p>
            ) : null}
          </Card>
        ) : null}

        <Card className={styles.signalsPanel}>
          <CardHeader
            eyebrow="可观测信号"
            title="传感器同步"
            description={
              isProduction
                ? "TimescaleDB 权威快照；每条信号保留来源、质量和观测时间。"
                : turbineId === "WT-023"
                  ? "WebSocket 帧覆盖 API 快照中的同名测点"
                  : "通用资产确定性运行快照"
            }
          />
          <div className={styles.signalGrid}>
            {signals.map((signal) => (
              <div data-anomaly={signal.isAnomaly} key={signal.metric}>
                <span>{localizedMetricLabel(signal.metric, signal.label)}</span>
                <strong>
                  {signal.value.toFixed(2)} <small>{signal.unit}</small>
                </strong>
                <em>{localizedStatusLabel(signal.quality)}</em>
              </div>
            ))}
          </div>
        </Card>

        <Card className={styles.contextPanel}>
          <CardHeader
            eyebrow="运营上下文"
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
                <small>工单</small>
                <strong>{snapshot.context.workOrderId ?? "暂无关联"}</strong>
              </span>
              <StatusBadge value={snapshot.context.workOrderStatus ?? "idle"} compact />
            </Link>
            <Link href="/resources">
              <CloudSun size={17} />
              <span>
                <small>天气窗口</small>
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
                <small>资产档案</small>
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
