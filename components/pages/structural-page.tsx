"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  structuralStatus,
  type StructuralContext,
  type StructuralHealth,
  type StructuralTopology,
} from "@/lib/structural-workflow";
import { useStructuralCommand } from "./structural-command";
import { StructuralReviewPanel, StructuralHealthReview } from "./structural-review-panel";
import { StructuralAcquisitionPanel } from "./structural-acquisition-panel";
import { StructuralPagination, useStructuralCursor } from "./structural-pagination";
import styles from "./structural-page.module.css";

interface MissionPage {
  readonly missions: readonly {
    readonly mission_id: string;
    readonly title: string;
    readonly work_order_id: string | null;
    readonly analysis_profile: { readonly component?: string };
  }[];
  readonly next_cursor: string | null;
}
interface ModalRun {
  readonly modal_observations: readonly { readonly id: string; readonly frequency_hz: number }[];
}

export function StructuralPage({ runtimeMode }: { readonly runtimeMode: "demo" | "production" }) {
  const { can } = useOpenVigilIdentity();
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [turbineId, setTurbineId] = useState("");
  const [componentId, setComponentId] = useState("");
  const [scenario, setScenario] = useState("modal_frequency_review");
  const [runId, setRunId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [previousId, setPreviousId] = useState("");
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState("");
  const [minimum, setMinimum] = useState("");
  const [maximum, setMaximum] = useState("");
  const [passageId, setPassageId] = useState("");
  const [quote, setQuote] = useState("");
  const [missionId, setMissionId] = useState("");
  const runCursor = useStructuralCursor();
  const prestressCursor = useStructuralCursor();
  const componentCursor = useStructuralCursor();
  const tendonCursor = useStructuralCursor();
  const sensorCursor = useStructuralCursor();
  const missionCursor = useStructuralCursor();
  const assetCursor = useStructuralCursor();
  const healthCursor = { run: runCursor.value, prestress: prestressCursor.value };
  const topologyCursor = {
    component: componentCursor.value,
    tendon: tendonCursor.value,
    sensor: sensorCursor.value,
  };
  const [workflowLocked, setWorkflowLocked] = useState(false);
  const [acquisitionLocked, setAcquisitionLocked] = useState(false);
  const externalLocked = workflowLocked || acquisitionLocked;
  const interactionLocked = externalLocked || command.unknown;
  const production = runtimeMode === "production";
  const assetsQuery = useQuery({
    queryKey: ["structural-assets", assetCursor.value],
    enabled: production,
    queryFn: ({ signal }) =>
      apiGet<{
        readonly turbines: readonly { readonly turbine_id: string; readonly model: string }[];
        readonly next_cursor: string | null;
      }>(`/api/backend/turbines?limit=200&cursor=${encodeURIComponent(assetCursor.value)}`, signal),
    retry: false,
  });
  const topologyQuery = useQuery({
    queryKey: ["structural-topology", turbineId, topologyCursor],
    enabled: production && Boolean(turbineId),
    queryFn: ({ signal }) =>
      apiGet<StructuralTopology>(
        `/api/backend/turbines/${encodeURIComponent(turbineId)}/tower-components?limit=100&component_cursor=${encodeURIComponent(topologyCursor.component)}&tendon_cursor=${encodeURIComponent(topologyCursor.tendon)}&sensor_cursor=${encodeURIComponent(topologyCursor.sensor)}`,
        signal,
      ),
    retry: false,
  });
  const healthQuery = useQuery({
    queryKey: ["structural-health", turbineId, healthCursor],
    enabled: production && Boolean(turbineId),
    queryFn: ({ signal }) =>
      apiGet<StructuralHealth>(
        `/api/backend/turbines/${encodeURIComponent(turbineId)}/structural-health?limit=20&run_cursor=${encodeURIComponent(healthCursor.run)}&prestress_cursor=${encodeURIComponent(healthCursor.prestress)}`,
        signal,
      ),
    refetchInterval: 10000,
    retry: false,
  });
  const runQuery = useQuery({
    queryKey: ["structural-run", runId],
    enabled: production && Boolean(runId),
    queryFn: ({ signal }) => apiGet<ModalRun>(`/api/backend/structural-analyses/${runId}`, signal),
    retry: false,
  });
  const missionsQuery = useQuery({
    queryKey: ["structural-missions", turbineId, missionCursor.value],
    enabled: production && Boolean(turbineId),
    queryFn: ({ signal }) =>
      apiGet<MissionPage>(
        `/api/backend/missions?turbine_id=${encodeURIComponent(turbineId)}&limit=100&cursor=${encodeURIComponent(missionCursor.value)}`,
        signal,
      ),
    refetchInterval: 10000,
    retry: false,
  });
  // Keep actual loaded options when a cursor changes. Cache keys include the asset;
  // changing turbines clears the selection and never imports another asset's rows.
  const loadedAssets = new Map(
    client
      .getQueriesData<typeof assetsQuery.data>({ queryKey: ["structural-assets"] })
      .flatMap(([, page]) => page?.turbines ?? [])
      .map((item) => [item.turbine_id, item]),
  );
  const loadedMissions = new Map(
    client
      .getQueriesData<MissionPage>({ queryKey: ["structural-missions", turbineId] })
      .flatMap(([, page]) => page?.missions ?? [])
      .map((item) => [item.mission_id, item]),
  );
  const topologyPages = client
    .getQueriesData<StructuralTopology>({
      queryKey: ["structural-topology", turbineId],
    })
    .flatMap(([, page]) => (page ? [page] : []));
  const topologyForSelection = topologyQuery.data ?? topologyPages[0];
  const loadedTopologyItems = (key: keyof StructuralTopology) => ({
    ...topologyForSelection[key],
    items: [
      ...new Map(
        topologyPages.flatMap((page) => page[key].items).map((item) => [item.id, item]),
      ).values(),
    ],
  });
  const loadedTopology: StructuralTopology | undefined = topologyForSelection
    ? {
        components: loadedTopologyItems("components"),
        tendons: loadedTopologyItems("tendons"),
        sensors: loadedTopologyItems("sensors"),
      }
    : undefined;
  const healthPages = client
    .getQueriesData<StructuralHealth>({
      queryKey: ["structural-health", turbineId],
    })
    .flatMap(([, page]) => (page ? [page] : []));
  const loadedAnalyses = [
    ...new Map(
      healthPages.flatMap((page) => page.analyses.items).map((item) => [item.id, item]),
    ).values(),
  ];
  const loadedPrestress = [
    ...new Map(
      healthPages.flatMap((page) => page.prestress.items).map((item) => [item.id, item]),
    ).values(),
  ];
  const mission = loadedMissions.get(missionId);
  const topology = topologyQuery.data;
  const health = healthQuery.data;
  function changeTurbine(value: string) {
    if (interactionLocked || command.busy) return;
    setTurbineId(value);
    setComponentId("");
    setSourceId("");
    setRunId("");
    setMissionId("");
    setBaselineId("");
    setPreviousId("");
    runCursor.first();
    prestressCursor.first();
    componentCursor.first();
    tendonCursor.first();
    sensorCursor.first();
    missionCursor.first();
  }
  async function createMission() {
    if (externalLocked || !can("mission.create") || !turbineId || !componentId || !sourceId) return;
    const payload = {
      turbine_id: turbineId,
      component_id: componentId,
      scenario,
      source_id: sourceId,
      title,
      planning_duration_hours: Number(duration),
      ...(scenario === "modal_frequency_review"
        ? baselineId
          ? { baseline_id: baselineId }
          : {}
        : {
            ...(previousId ? { previous_prestress_id: previousId } : {}),
            ...(minimum || maximum || passageId || quote
              ? {
                  force_acceptance: {
                    minimum_kn: Number(minimum),
                    maximum_kn: Number(maximum),
                    procedure: {
                      kind: "knowledge_passage",
                      source_id: passageId,
                      relation: "supports",
                      quote,
                    },
                  },
                }
              : {}),
          }),
    };
    const result = await command.run<StructuralContext>(
      "/api/backend/structural-missions",
      payload,
      "结构 Mission 已提交，后台将生成待审工程结论。",
    );
    if (result) {
      setMissionId(result.mission_id);
      missionCursor.first();
      await client.invalidateQueries({ queryKey: ["structural-missions"] });
    }
  }
  return (
    <AppShell activePath="/structural" runtimeMode={runtimeMode}>
      <PageHeader
        title="混塔结构工作台"
        eyebrow="Onshore · Hybrid tower"
        description="从实际模态与直接索力测量进入工程复核、受控复测和待审案例。现场资格等待试点资料验证。"
      />
      <div className={styles.stack}>
        {!production ? (
          <div className={styles.notice} role="status">
            结构工作台需要连接权威后端。当前为演示运行时，尚无结构数据；请配置生产网关后使用实际采集与审核。
          </div>
        ) : null}
        <Card className={styles.panel}>
          <CardHeader
            title="结构资产与观测"
            description="构件、索束、测点和校准版本来自数据库；未知数值保留缺失。"
          />
          <label className={styles.field}>
            选择授权机组
            <select
              disabled={!production || assetsQuery.isPending || command.busy || interactionLocked}
              value={turbineId}
              onChange={(event) => changeTurbine(event.target.value)}
            >
              <option value="">请选择机组</option>
              {[...loadedAssets.values()].map((item) => (
                <option key={item.turbine_id} value={item.turbine_id}>
                  {item.turbine_id} · {item.model}
                </option>
              ))}
            </select>
          </label>
          <StructuralPagination
            label="机组"
            cursor={assetCursor}
            nextCursor={assetsQuery.data?.next_cursor}
            disabled={assetsQuery.isFetching || command.busy || interactionLocked}
          />
          {production && assetsQuery.isPending ? <p role="status">正在读取资产…</p> : null}
          {assetsQuery.error ? (
            <p role="alert">
              {assetsQuery.error.message}
              <Button onClick={() => void assetsQuery.refetch()}>重试</Button>
            </p>
          ) : null}
          {production && assetsQuery.data && !assetsQuery.data.turbines.length ? (
            <p>当前权限范围内暂无机组。</p>
          ) : null}
          {turbineId ? (
            <>
              {topologyQuery.isPending || healthQuery.isPending ? (
                <p role="status">正在读取构件与结构观测…</p>
              ) : null}
              {topologyQuery.error || healthQuery.error ? (
                <p role="alert">
                  {topologyQuery.error?.message ?? healthQuery.error?.message}
                  <Button
                    onClick={() => {
                      void topologyQuery.refetch();
                      void healthQuery.refetch();
                    }}
                  >
                    重试
                  </Button>
                </p>
              ) : null}
              <p>
                {structuralStatus(health?.assessment_status ?? "no_data")} ·{" "}
                {structuralStatus(health?.baseline_status ?? "unavailable")}
              </p>
              <div className={styles.grid}>
                <div>
                  <h3>构件 / 索束 / 测点</h3>
                  {topology ? (
                    <>
                      <p>
                        {topology.components.items.length} 个本页构件 ·{" "}
                        {topology.tendons.items.length} 个本页索束 · {topology.sensors.items.length}{" "}
                        个本页测点
                      </p>
                      {topology.sensors.items.map((item) => (
                        <p key={item.id}>
                          {item.code} · {item.quantity} · 校准 {item.calibration_version} · 有效至{" "}
                          {item.calibration_valid_until}
                        </p>
                      ))}
                      {[componentCursor, tendonCursor, sensorCursor].map((cursor, index) => (
                        <StructuralPagination
                          key={index}
                          label={["构件", "索束", "测点"][index]}
                          cursor={cursor}
                          nextCursor={
                            [topology.components, topology.tendons, topology.sensors][index]
                              .next_cursor
                          }
                          disabled={topologyQuery.isFetching || interactionLocked || command.busy}
                        />
                      ))}
                    </>
                  ) : null}
                </div>
                <div>
                  <h3>实际结构观测</h3>
                  {health?.analyses.items.map((item) => (
                    <p key={item.id}>
                      {structuralStatus(item.status)} · {item.id}
                      {item.error_code ? ` · ${item.error_code}` : ""}
                    </p>
                  ))}
                  {health?.prestress.items.map((item) => (
                    <p key={item.id}>
                      {item.value_kn} kN · {item.observed_at} · {item.source_kind}
                    </p>
                  ))}
                  {health && !health.analyses.items.length && !health.prestress.items.length ? (
                    <p>尚无模态或直接索力观测。</p>
                  ) : null}
                  <StructuralPagination
                    label="分析"
                    cursor={runCursor}
                    nextCursor={health?.analyses.next_cursor}
                    disabled={healthQuery.isFetching || interactionLocked || command.busy}
                  />
                  <StructuralPagination
                    label="索力"
                    cursor={prestressCursor}
                    nextCursor={health?.prestress.next_cursor}
                    disabled={healthQuery.isFetching || interactionLocked || command.busy}
                  />
                </div>
              </div>
            </>
          ) : null}
        </Card>
        {production && turbineId && loadedTopology ? (
          <StructuralAcquisitionPanel
            key={turbineId}
            turbineId={turbineId}
            topology={loadedTopology}
            onLockChange={setAcquisitionLocked}
          />
        ) : null}
        {production && turbineId ? (
          <Card className={styles.panel}>
            <CardHeader
              title="创建结构复核 Mission"
              description="冻结构件、来源和审核范围。缺少基线或规程时保留缺失项，不能按默认健康分关单。"
            />
            <form
              className={styles.form}
              onSubmit={(event) => {
                event.preventDefault();
                void createMission();
              }}
            >
              <fieldset className={styles.formFields} disabled={interactionLocked || command.busy}>
                <label className={styles.field}>
                  构件
                  <select
                    required
                    aria-label="构件"
                    value={componentId}
                    onChange={(event) => {
                      setComponentId(event.target.value);
                      setSourceId("");
                      setPreviousId("");
                    }}
                  >
                    <option value="">请选择构件</option>
                    {loadedTopology?.components.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.code} · {item.name} · {item.revision}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={styles.field}>
                  复核场景
                  <select
                    value={scenario}
                    onChange={(event) => {
                      setScenario(event.target.value);
                      setSourceId("");
                    }}
                  >
                    <option value="modal_frequency_review">模态频率复核</option>
                    <option value="prestress_retest">直接索力复测</option>
                  </select>
                </label>
                {scenario === "modal_frequency_review" ? (
                  <>
                    <label className={styles.field}>
                      成功的分析记录
                      <select
                        required
                        value={runId}
                        onChange={(event) => {
                          setRunId(event.target.value);
                          setSourceId("");
                        }}
                      >
                        <option value="">请选择分析</option>
                        {loadedAnalyses
                          .filter((item) => item.status === "succeeded")
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.id}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className={styles.field}>
                      模态观测
                      <select
                        required
                        value={sourceId}
                        onChange={(event) => setSourceId(event.target.value)}
                      >
                        <option value="">请选择模态</option>
                        {runQuery.data?.modal_observations.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.frequency_hz} Hz · {item.id}
                          </option>
                        ))}
                      </select>
                    </label>
                    {runQuery.error ? <p role="alert">{runQuery.error.message}</p> : null}
                    <label className={styles.field}>
                      健康基线
                      <select
                        value={baselineId}
                        onChange={(event) => setBaselineId(event.target.value)}
                      >
                        <option value="">无已确认基线，保留缺失</option>
                        {health?.baseline ? (
                          <option value={health.baseline.id}>
                            {health.baseline.code} · {health.baseline.revision}
                          </option>
                        ) : null}
                      </select>
                    </label>
                  </>
                ) : (
                  <>
                    <label className={styles.field}>
                      直接索力观测
                      <select
                        required
                        value={sourceId}
                        onChange={(event) => setSourceId(event.target.value)}
                      >
                        <option value="">请选择观测</option>
                        {loadedPrestress.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.value_kn} kN · {item.observed_at}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className={styles.field}>
                      前次同测点观测
                      <select
                        value={previousId}
                        onChange={(event) => setPreviousId(event.target.value)}
                      >
                        <option value="">未提供前次观测</option>
                        {loadedPrestress
                          .filter((item) => item.id !== sourceId)
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.value_kn} kN · {item.observed_at}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className={styles.field}>
                      审核规程下限 (kN)
                      <input
                        type="number"
                        min="0.0001"
                        step="any"
                        value={minimum}
                        onChange={(event) => setMinimum(event.target.value)}
                      />
                    </label>
                    <label className={styles.field}>
                      审核规程上限 (kN)
                      <input
                        type="number"
                        min="0.0001"
                        step="any"
                        value={maximum}
                        onChange={(event) => setMaximum(event.target.value)}
                      />
                    </label>
                    <label className={styles.field}>
                      规程段落 ID
                      <input
                        value={passageId}
                        onChange={(event) => setPassageId(event.target.value)}
                      />
                    </label>
                    <label className={styles.field}>
                      规程原文摘录
                      <textarea
                        maxLength={2000}
                        value={quote}
                        onChange={(event) => setQuote(event.target.value)}
                      />
                    </label>
                  </>
                )}
                <label className={styles.field}>
                  任务标题
                  <input
                    required
                    minLength={3}
                    maxLength={160}
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                  />
                </label>
                <label className={styles.field}>
                  人工估计复测时长 (小时)
                  <input
                    required
                    type="number"
                    min="0.01"
                    max="24"
                    step="any"
                    value={duration}
                    onChange={(event) => setDuration(event.target.value)}
                  />
                </label>
              </fieldset>
              <Button
                type="submit"
                variant="primary"
                disabled={externalLocked || !can("mission.create") || !componentId || !sourceId}
                loading={command.busy}
              >
                {command.unknown ? "核验原结构复核提交" : "提交结构复核"}
              </Button>
            </form>
            {command.error ? (
              <p role="alert" className={styles.error}>
                {command.error}
              </p>
            ) : null}
            {command.notice ? <p role="status">{command.notice}</p> : null}
          </Card>
        ) : null}
        {production && turbineId ? (
          <Card className={styles.panel}>
            <CardHeader title="结构 Mission" />
            <label className={styles.field}>
              选择实际任务
              <select
                disabled={interactionLocked || command.busy}
                value={missionId}
                onChange={(event) => setMissionId(event.target.value)}
              >
                <option value="">请选择结构 Mission</option>
                {[...loadedMissions.values()]
                  .filter((item) => item.analysis_profile.component === "hybrid_tower_structure")
                  .map((item) => (
                    <option key={item.mission_id} value={item.mission_id}>
                      {item.title}
                    </option>
                  ))}
              </select>
            </label>
            {missionsQuery.error ? <p role="alert">{missionsQuery.error.message}</p> : null}
            <StructuralPagination
              label="任务"
              cursor={missionCursor}
              nextCursor={missionsQuery.data?.next_cursor}
              disabled={missionsQuery.isFetching || interactionLocked || command.busy}
            />
          </Card>
        ) : null}
        {production && missionId ? (
          <StructuralReviewPanel key={missionId} missionId={missionId} />
        ) : null}
        {production && mission?.work_order_id ? (
          <StructuralHealthReview
            key={mission.work_order_id}
            workOrderId={mission.work_order_id}
            turbineId={turbineId}
            onLockChange={setWorkflowLocked}
          />
        ) : null}
      </div>
    </AppShell>
  );
}
