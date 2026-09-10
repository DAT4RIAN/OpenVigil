"use client";

import {
  Activity,
  ChevronRight,
  Database,
  ExternalLink,
  Lock,
  Search,
  Server,
  TableProperties,
  TowerControl,
} from "lucide-react";
import Link from "next/link";

import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { dataCatalogCategories, dataCatalogStatuses } from "@/lib/platform-admin-data";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import { localizedMetricLabel } from "@/lib/ui-localization";

import styles from "./data-center-page.module.css";
import {
  catalogColumns,
  categoryLabels,
  compactHash,
  formatCount,
  statusLabels,
  summarizeRunCounts,
} from "./data-center-support";
import { useDataCenterWorkspace } from "./use-data-center-workspace";

export function DataCenterPage({ runtimeMode }: { runtimeMode: OpenVigilRuntimeMode }) {
  const {
    isProduction,
    category,
    setCategory,
    status,
    setStatus,
    setSelectedSubsystemKey,
    sourceId,
    setSourceId,
    sourceName,
    setSourceName,
    sourceKind,
    setSourceKind,
    sourceSecret,
    setSourceSecret,
    sourceReason,
    setSourceReason,
    contractSourceId,
    setContractSourceId,
    contractVariable,
    setContractVariable,
    contractJson,
    setContractJson,
    contractReason,
    setContractReason,
    benchmarkQueryText,
    setBenchmarkQueryText,
    benchmarkOffset,
    setBenchmarkOffset,
    setSelectedBenchmarkId,
    benchmarkFarm,
    setBenchmarkFarm,
    benchmarkEventOffset,
    setBenchmarkEventOffset,
    setSelectedReplayId,
    setSelectedReplayVariable,
    catalogQuery,
    governanceQuery,
    benchmarkDatasetsQuery,
    benchmarkDatasets,
    activeBenchmarkId,
    activeBenchmark,
    benchmarkEventsQuery,
    benchmarkEvents,
    replayOptions,
    activeReplay,
    activeReplayVariable,
    benchmarkCurveQuery,
    sourceMutation,
    contractMutation,
    hierarchy,
    selectedSubsystem,
    entries,
    filtered,
    scadaArchiveCount,
    schemaObjectCount,
    catalogTotal,
    benchmarkPermissionDenied,
    benchmarkShowsPreviousData,
    benchmarkCurveLine,
  } = useDataCenterWorkspace(runtimeMode);

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/data">
      <PageHeader
        eyebrow="平台治理"
        title="数据中心"
        description="从风场资产树追踪到测点，并审阅实时、归档、API 与 D1 Schema 数据资产。"
        breadcrumb={["平台管理", "数据中心"]}
        meta={
          <>
            <StatusBadge
              value="ready"
              label={isProduction ? "权威数据目录" : "确定性数据 · 只读"}
              tone="success"
            />
            <span className="page-meta-text">
              目录快照{" "}
              {catalogQuery.data?.meta.snapshotAt
                ? new Date(catalogQuery.data.meta.snapshotAt).toLocaleString("zh-CN")
                : "—"}
            </span>
          </>
        }
      />

      <section className={styles.kpis} aria-label="数据目录摘要">
        <Card>
          <span className={styles.kpiIcon}>
            <Database size={18} />
          </span>
          <small>SCADA 归档</small>
          <strong>{formatCount(scadaArchiveCount)}</strong>
          <em>{isProduction ? "TimescaleDB 实际记录" : "64 × 16 × 128"}</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TableProperties size={18} />
          </span>
          <small>数据模型对象</small>
          <strong>{schemaObjectCount}</strong>
          <em>{isProduction ? "PostgreSQL 逻辑对象" : "D1 逻辑对象"}</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TowerControl size={18} />
          </span>
          <small>资产树</small>
          <strong>{hierarchy.farm.turbineCount}</strong>
          <em>台风机 · {hierarchy.subsystems.length} 子系统</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <Server size={18} />
          </span>
          <small>目录数据集</small>
          <strong>{catalogTotal}</strong>
          <em>{isProduction ? "查询与受治理配置入口" : "统一只读查询入口"}</em>
        </Card>
      </section>

      <section className={styles.topGrid}>
        <Card className={styles.assetTree}>
          <CardHeader
            eyebrow="资产层级"
            title="风场 → 风机 → 子系统 → 传感器"
            description={
              isProduction
                ? "目录只展示已由真实遥测源写入并保留质量码的测点。"
                : "展开 WT-023 的完整 12 子系统测点目录；其余 63 台机组使用同一资产 Schema。"
            }
          />
          <div className={styles.treeRoot}>
            <span className={styles.treeNodeIcon}>
              <Database size={15} />
            </span>
            <div>
              <strong>{hierarchy.farm.name}</strong>
              <small>
                {hierarchy.farm.id} · {hierarchy.farm.capacityMW} MW
              </small>
            </div>
            <span>{hierarchy.farm.turbineCount} 台风机</span>
          </div>
          <div className={styles.treeBranch}>
            <div className={styles.focusTurbine}>
              <ChevronRight size={14} />
              <div>
                <strong>{hierarchy.focusTurbine.id}</strong>
                <small>
                  {hierarchy.focusTurbine.model} · 健康度 {hierarchy.focusTurbine.healthScore}
                </small>
              </div>
              <Link href="/turbines/WT-023">资产详情</Link>
            </div>
            <div className={styles.subsystemGrid}>
              {hierarchy.subsystems.map((subsystem) => (
                <button
                  type="button"
                  key={subsystem.id}
                  data-selected={selectedSubsystem?.key === subsystem.key}
                  onClick={() => setSelectedSubsystemKey(subsystem.key)}
                >
                  <span>
                    <strong>{subsystem.name}</strong>
                    <small>{subsystem.key}</small>
                  </span>
                  <span>
                    <b>{subsystem.healthScore}</b>
                    <small>{subsystem.sensors.length} 个传感器</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card className={styles.sensorPanel}>
          <CardHeader
            eyebrow="传感器检查器"
            title={selectedSubsystem?.name ?? "传感器"}
            description={
              isProduction
                ? "测点来自 TimescaleDB 实际变量；目录不会生成未接入传感器。"
                : "仅 Schema 表示目录中已定义、但当前演示归档没有伪造该测点数据。"
            }
            action={
              selectedSubsystem ? (
                <StatusBadge
                  value={selectedSubsystem.state}
                  label={`健康度 ${selectedSubsystem.healthScore}`}
                  tone={selectedSubsystem.healthScore < 75 ? "critical" : "success"}
                />
              ) : null
            }
          />
          <div className={styles.sensorList}>
            {selectedSubsystem?.sensors.map((sensor) => (
              <div key={sensor.id}>
                <span
                  className={styles.sensorDot}
                  data-live={sensor.source === "live-and-archive"}
                />
                <span>
                  <strong>{localizedMetricLabel(sensor.metric)}</strong>
                  <small>
                    {sensor.id} · {sensor.unit}
                  </small>
                </span>
                <StatusBadge
                  value={sensor.source}
                  label={sensor.source === "live-and-archive" ? "实时 + 归档" : "仅数据模型"}
                  tone={sensor.source === "live-and-archive" ? "success" : "neutral"}
                  compact
                />
                {sensor.queryHref ? (
                  <Link href={sensor.queryHref} aria-label={`查询 ${sensor.metric}`}>
                    <ExternalLink size={13} />
                  </Link>
                ) : (
                  <span className={styles.noQuery}>—</span>
                )}
              </div>
            ))}
          </div>
          <p className={styles.boundaryNote}>
            {isProduction
              ? "生产目录仅把已接收、带来源和质量状态的变量标记为实时与归档。"
              : "当前 SCADA 归档只包含 16 个明确声明的指标。目录不会把未接入测点标记为实时，也不会生成虚假测量值。"}
          </p>
        </Card>
      </section>

      {isProduction ? (
        <section className={styles.topGrid} aria-label="数据源与数据契约治理">
          <Card className={styles.assetTree}>
            <CardHeader
              eyebrow="采集源治理"
              title="配置真实数据源"
              description="写入版本化采集策略；凭据只保存 Secret Manager 引用，不进入浏览器响应。"
            />
            <label>
              <span>Source ID</span>
              <input
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value.toLowerCase())}
                placeholder="offshore-opcua-01"
              />
            </label>
            <label>
              <span>显示名称</span>
              <input
                value={sourceName}
                onChange={(event) => setSourceName(event.target.value)}
                placeholder="Offshore OPC UA 01"
              />
            </label>
            <label>
              <span>协议</span>
              <select value={sourceKind} onChange={(event) => setSourceKind(event.target.value)}>
                {["opcua", "mqtt", "iec61400_25", "cms", "weather", "rest"].map((kind) => (
                  <option value={kind} key={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Secret Manager 引用</span>
              <input
                value={sourceSecret}
                onChange={(event) => setSourceSecret(event.target.value)}
                placeholder="vault://openvigil/scada/offshore-opcua-01"
              />
            </label>
            <label>
              <span>变更原因</span>
              <input
                value={sourceReason}
                onChange={(event) => setSourceReason(event.target.value)}
                placeholder="关联采集接入审批单"
              />
            </label>
            {sourceMutation.error instanceof Error ? (
              <div className={styles.errorBanner} role="alert">
                {sourceMutation.error.message}
              </div>
            ) : null}
            <Button
              loading={sourceMutation.isPending}
              disabled={
                sourceId.trim().length < 3 ||
                sourceName.trim().length < 3 ||
                sourceReason.trim().length < 3
              }
              onClick={() => sourceMutation.mutate()}
            >
              保存数据源策略
            </Button>
            <div className={styles.sensorList}>
              {(governanceQuery.data?.data_sources ?? []).map((source) => (
                <div key={source.source_id}>
                  <span className={styles.sensorDot} data-live={source.enabled} />
                  <span>
                    <strong>{source.display_name}</strong>
                    <small>
                      {source.source_id} · {source.source_kind}
                    </small>
                  </span>
                  <StatusBadge
                    value={source.secret_configured ? "secret-bound" : "no-secret"}
                    label={source.secret_configured ? "凭据已托管" : "无凭据"}
                    tone={source.secret_configured ? "success" : "warning"}
                    compact
                  />
                </div>
              ))}
            </div>
          </Card>

          <Card className={styles.sensorPanel}>
            <CardHeader
              eyebrow="Schema 治理"
              title="激活数据契约"
              description="契约经过 Pydantic 校验并以 CAS 修订激活，采集器会立即使用活动契约进行单位、阈值和质量校验。"
            />
            <label>
              <span>Source ID</span>
              <input
                value={contractSourceId}
                onChange={(event) => setContractSourceId(event.target.value.toLowerCase())}
                placeholder="offshore-opcua-01"
              />
            </label>
            <label>
              <span>变量</span>
              <input
                value={contractVariable}
                onChange={(event) => setContractVariable(event.target.value.toLowerCase())}
                placeholder="main_bearing_temperature"
              />
            </label>
            <label>
              <span>契约 JSON</span>
              <textarea
                className="approval-comment"
                value={contractJson}
                onChange={(event) => setContractJson(event.target.value)}
                aria-label="数据契约 JSON"
              />
            </label>
            <label>
              <span>变更原因</span>
              <input
                value={contractReason}
                onChange={(event) => setContractReason(event.target.value)}
                placeholder="关联数据契约审批单"
              />
            </label>
            {contractMutation.error instanceof Error ? (
              <div className={styles.errorBanner} role="alert">
                {contractMutation.error.message}
              </div>
            ) : null}
            <Button
              loading={contractMutation.isPending}
              disabled={
                contractSourceId.trim().length < 3 ||
                contractVariable.trim().length < 2 ||
                contractReason.trim().length < 3
              }
              onClick={() => contractMutation.mutate()}
            >
              激活数据契约修订
            </Button>
            <div className={styles.sensorList}>
              {(governanceQuery.data?.data_contracts ?? []).map((contract) => (
                <div key={contract.contract_id}>
                  <span className={styles.sensorDot} data-live />
                  <span>
                    <strong>{contract.variable}</strong>
                    <small>
                      {contract.source_id} · 修订 {contract.revision}
                    </small>
                  </span>
                  <StatusBadge value="active" label="已激活" tone="success" compact />
                </div>
              ))}
            </div>
          </Card>
        </section>
      ) : null}

      <section id="care-benchmarks" aria-label="CARE 受治理基准数据">
        <Card className={styles.benchmarkPanel}>
          <CardHeader
            eyebrow="CARE Benchmark"
            title="受治理基准数据"
            description="从 PostgreSQL 元数据读取版本、许可证、校验和、映射、质量与运行状态；曲线仅使用服务端有界降采样。"
            action={
              isProduction && benchmarkDatasetsQuery.data ? (
                <span className={styles.resultCount}>
                  {benchmarkDatasetsQuery.data.meta.count} /{" "}
                  {benchmarkDatasetsQuery.data.meta.filtered_total}
                </span>
              ) : null
            }
          />
          {!isProduction ? (
            <div className={styles.benchmarkState} data-state="disabled">
              <Lock size={18} />
              <span>
                <strong>生产数据连接未启用</strong>
                <small>演示模式不会用 fixture 冒充 CARE 导入、评估或回放结果。</small>
              </span>
            </div>
          ) : benchmarkPermissionDenied ? (
            <div className={styles.benchmarkState} data-state="permission" role="alert">
              <Lock size={18} />
              <span>
                <strong>无 Benchmark 数据权限</strong>
                <small>当前身份缺少 benchmark scope；服务端已失败关闭且未返回数据。</small>
              </span>
            </div>
          ) : benchmarkDatasetsQuery.isLoading ? (
            <div className={styles.benchmarkState} aria-busy="true">
              <Activity size={18} />
              <span>
                <strong>正在读取基准元数据…</strong>
                <small>查询使用固定 10 条服务端分页上限。</small>
              </span>
            </div>
          ) : benchmarkDatasetsQuery.isError ? (
            <div className={styles.benchmarkState} data-state="error" role="alert">
              <Activity size={18} />
              <span>
                <strong>基准目录读取失败</strong>
                <small>
                  {benchmarkDatasetsQuery.error instanceof Error
                    ? benchmarkDatasetsQuery.error.message
                    : "生产 API 返回了未知错误。"}
                </small>
              </span>
            </div>
          ) : !benchmarkDatasets.length || !activeBenchmark ? (
            <div className={styles.benchmarkState} data-state="empty">
              <Database size={18} />
              <span>
                <strong>没有匹配的基准数据集</strong>
                <small>调整服务端搜索条件，或先完成受治理数据集登记。</small>
              </span>
            </div>
          ) : (
            <div className={styles.benchmarkBody}>
              <div className={styles.benchmarkToolbar}>
                <label>
                  <span>服务端搜索</span>
                  <input
                    value={benchmarkQueryText}
                    maxLength={100}
                    onChange={(event) => {
                      setBenchmarkQueryText(event.target.value);
                      setBenchmarkOffset(0);
                      setBenchmarkEventOffset(0);
                    }}
                    placeholder="版本、DOI 或许可证"
                  />
                </label>
                <label>
                  <span>数据集版本</span>
                  <select
                    value={activeBenchmarkId}
                    onChange={(event) => {
                      setSelectedBenchmarkId(event.target.value);
                      setBenchmarkEventOffset(0);
                      setSelectedReplayId("");
                      setSelectedReplayVariable("");
                    }}
                  >
                    {benchmarkDatasets.map((dataset) => (
                      <option value={dataset.dataset_version_id} key={dataset.dataset_version_id}>
                        {dataset.dataset_id} {dataset.version}
                      </option>
                    ))}
                  </select>
                </label>
                <span className={styles.paginationControls}>
                  <button
                    type="button"
                    disabled={benchmarkOffset === 0 || benchmarkDatasetsQuery.isFetching}
                    onClick={() => setBenchmarkOffset(Math.max(0, benchmarkOffset - 10))}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    disabled={
                      !benchmarkDatasetsQuery.data?.meta.has_more ||
                      benchmarkDatasetsQuery.isFetching
                    }
                    onClick={() =>
                      setBenchmarkOffset(
                        benchmarkDatasetsQuery.data?.meta.next_offset ?? benchmarkOffset,
                      )
                    }
                  >
                    下一页
                  </button>
                </span>
              </div>

              {benchmarkShowsPreviousData ? (
                <div className={styles.staleBanner} role="status">
                  正在刷新；当前暂时显示上一份有界快照，完成后会自动替换。
                </div>
              ) : null}

              <div className={styles.benchmarkIdentity}>
                <div>
                  <span className={styles.benchmarkTitleLine}>
                    <strong>
                      {activeBenchmark.dataset_id} {activeBenchmark.version}
                    </strong>
                    <StatusBadge
                      value={activeBenchmark.status}
                      label={activeBenchmark.status}
                      tone={activeBenchmark.status === "ready" ? "success" : "neutral"}
                      compact
                    />
                  </span>
                  <small>{activeBenchmark.dataset_version_id}</small>
                  <p>{activeBenchmark.license.citation}</p>
                </div>
                <div className={styles.benchmarkLinks}>
                  <a
                    href={`https://doi.org/${activeBenchmark.license.doi}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    DOI {activeBenchmark.license.doi} <ExternalLink size={11} />
                  </a>
                  <a href={activeBenchmark.license.url} target="_blank" rel="noreferrer">
                    {activeBenchmark.license.name} <ExternalLink size={11} />
                  </a>
                </div>
              </div>

              <div className={styles.benchmarkMetrics}>
                <div>
                  <small>覆盖事件 / 场 / 资产</small>
                  <strong>
                    {activeBenchmark.coverage.registered_event_count} /{" "}
                    {activeBenchmark.coverage.farm_count} / {activeBenchmark.coverage.asset_count}
                  </strong>
                  <em>{formatCount(activeBenchmark.coverage.time_point_count)} 个时间点</em>
                </div>
                <div>
                  <small>Train / Prediction</small>
                  <strong>
                    {formatCount(activeBenchmark.coverage.train_row_count)} /{" "}
                    {formatCount(activeBenchmark.coverage.prediction_row_count)}
                  </strong>
                  <em>匿名事件内时间，禁止跨事件排序</em>
                </div>
                <div>
                  <small>映射启用 / 总数</small>
                  <strong>
                    {activeBenchmark.mapping.enabled} / {activeBenchmark.mapping.total}
                  </strong>
                  <em>
                    禁用 {activeBenchmark.mapping.disabled} · 未知单位{" "}
                    {activeBenchmark.mapping.unknown_unit}
                  </em>
                </div>
                <div>
                  <small>质量报告 / Mask</small>
                  <strong>
                    {activeBenchmark.quality.completed_count} /{" "}
                    {formatCount(activeBenchmark.quality.mask_count)}
                  </strong>
                  <em>
                    {activeBenchmark.quality.raw_values_modified ? "原值已变更" : "原始值未改写"} ·
                    失败 {activeBenchmark.quality.failed_count}
                  </em>
                </div>
              </div>

              <div className={styles.benchmarkDetailGrid}>
                <div>
                  <h3>不可变身份</h3>
                  <dl>
                    <div>
                      <dt>Manifest SHA-256</dt>
                      <dd title={activeBenchmark.manifest.sha256}>
                        {compactHash(activeBenchmark.manifest.sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Archive SHA-256</dt>
                      <dd title={activeBenchmark.archive.sha256 ?? undefined}>
                        {compactHash(activeBenchmark.archive.sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Content SHA-256</dt>
                      <dd title={activeBenchmark.archive.content_sha256}>
                        {compactHash(activeBenchmark.archive.content_sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Archive MD5</dt>
                      <dd title={activeBenchmark.archive.md5 ?? undefined}>
                        {compactHash(activeBenchmark.archive.md5)}
                      </dd>
                    </div>
                  </dl>
                </div>
                <div>
                  <h3>数据层</h3>
                  <dl>
                    {Object.entries(activeBenchmark.layers).map(([layer, value]) => (
                      <div key={layer}>
                        <dt>{layer}</dt>
                        <dd>{value.status}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <div>
                  <h3>运行状态</h3>
                  <dl>
                    <div>
                      <dt>Import</dt>
                      <dd>{activeBenchmark.runs.import.status}</dd>
                    </div>
                    <div>
                      <dt>Evaluation</dt>
                      <dd>{summarizeRunCounts(activeBenchmark.runs.evaluation)}</dd>
                    </div>
                    <div>
                      <dt>Replay</dt>
                      <dd>{summarizeRunCounts(activeBenchmark.runs.replay)}</dd>
                    </div>
                    <div>
                      <dt>Truth</dt>
                      <dd>{activeBenchmark.coverage.truth_summary.access}</dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div className={styles.benchmarkSubsection}>
                <div className={styles.benchmarkSubheader}>
                  <span>
                    <strong>事件与质量摘要</strong>
                    <small>每页最多 12 个事件；prediction 真值默认受限。</small>
                  </span>
                  <label>
                    <span>风场</span>
                    <select
                      value={benchmarkFarm}
                      onChange={(event) => {
                        setBenchmarkFarm(event.target.value as typeof benchmarkFarm);
                        setBenchmarkEventOffset(0);
                      }}
                    >
                      <option value="all">全部</option>
                      <option value="A">A</option>
                      <option value="B">B</option>
                      <option value="C">C</option>
                    </select>
                  </label>
                  <span className={styles.paginationControls}>
                    <button
                      type="button"
                      disabled={benchmarkEventOffset === 0 || benchmarkEventsQuery.isFetching}
                      onClick={() =>
                        setBenchmarkEventOffset(Math.max(0, benchmarkEventOffset - 12))
                      }
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      disabled={
                        !benchmarkEventsQuery.data?.meta.has_more || benchmarkEventsQuery.isFetching
                      }
                      onClick={() =>
                        setBenchmarkEventOffset(
                          benchmarkEventsQuery.data?.meta.next_offset ?? benchmarkEventOffset,
                        )
                      }
                    >
                      下一页
                    </button>
                  </span>
                </div>
                {benchmarkEventsQuery.isLoading ? (
                  <div className={styles.benchmarkState} aria-busy="true">
                    正在读取事件摘要…
                  </div>
                ) : benchmarkEventsQuery.isError ? (
                  <div className={styles.benchmarkState} data-state="error" role="alert">
                    事件摘要读取失败；未使用本地或前端 fixture 回退。
                  </div>
                ) : benchmarkEvents.length ? (
                  <div className={styles.benchmarkEventList}>
                    {benchmarkEvents.map((event) => (
                      <article key={event.benchmark_event_id}>
                        <span>
                          <strong>
                            {event.farm}
                            {event.event_id} · {event.logical_asset_id}
                          </strong>
                          <small>
                            {formatCount(event.rows.total)} 行 · train{" "}
                            {formatCount(event.rows.train)} · prediction{" "}
                            {formatCount(event.rows.prediction)}
                          </small>
                        </span>
                        <span>
                          <small>质量</small>
                          <strong>{event.quality.status}</strong>
                          <em>{formatCount(event.quality.mask_count)} masks</em>
                        </span>
                        <span>
                          <small>评估</small>
                          <strong>{summarizeRunCounts(event.evaluation_results)}</strong>
                          <em>{event.recent_replays.length} 个最近回放</em>
                        </span>
                        <StatusBadge
                          value={event.truth.access}
                          label={event.truth.access === "restricted" ? "真值受限" : "真值可见"}
                          tone={event.truth.access === "restricted" ? "neutral" : "warning"}
                          compact
                        />
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className={styles.benchmarkState} data-state="empty">
                    当前筛选没有事件摘要。
                  </div>
                )}
              </div>

              <div className={styles.benchmarkSubsection}>
                <div className={styles.benchmarkSubheader}>
                  <span>
                    <strong>服务端降采样曲线</strong>
                    <small>最多 128 点；浏览器不读取原始 CSV，也不包含 prediction 真值。</small>
                  </span>
                  <label>
                    <span>Replay run</span>
                    <select
                      value={activeReplay?.replay_run_id ?? ""}
                      disabled={!replayOptions.length}
                      onChange={(event) => {
                        setSelectedReplayId(event.target.value);
                        setSelectedReplayVariable("");
                      }}
                    >
                      {!replayOptions.length ? <option value="">无可用回放</option> : null}
                      {replayOptions.map((replay) => (
                        <option value={replay.replay_run_id} key={replay.replay_run_id}>
                          {replay.replay_run_id} · {replay.status}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>变量</span>
                    <select
                      value={activeReplayVariable}
                      disabled={!activeReplay?.variables.length}
                      onChange={(event) => setSelectedReplayVariable(event.target.value)}
                    >
                      {!activeReplay?.variables.length ? <option value="">无变量</option> : null}
                      {activeReplay?.variables.map((variable) => (
                        <option value={variable} key={variable}>
                          {variable}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {benchmarkCurveQuery.isLoading ? (
                  <div className={styles.benchmarkState} aria-busy="true">
                    正在请求降采样曲线…
                  </div>
                ) : benchmarkCurveQuery.isError ? (
                  <div className={styles.benchmarkState} data-state="error" role="alert">
                    曲线读取失败；服务端未回退到原始文件。
                  </div>
                ) : benchmarkCurveLine ? (
                  <div className={styles.curvePanel}>
                    <svg
                      viewBox="0 0 100 40"
                      role="img"
                      aria-label={`${activeReplayVariable} 服务端降采样曲线`}
                    >
                      <polyline points={benchmarkCurveLine} vectorEffect="non-scaling-stroke" />
                    </svg>
                    <span>
                      <strong>{activeReplayVariable}</strong>
                      <small>
                        {benchmarkCurveQuery.data?.meta.count} /{" "}
                        {formatCount(benchmarkCurveQuery.data?.meta.source_point_count ?? 0)} 点 ·{" "}
                        {benchmarkCurveQuery.data?.meta.downsample_algorithm}
                      </small>
                    </span>
                  </div>
                ) : (
                  <div className={styles.benchmarkState} data-state="empty">
                    选择包含持久化样本的回放和变量后显示曲线。
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      </section>

      <Card className={styles.catalogPanel}>
        <CardHeader
          eyebrow="数据集目录"
          title="数据集目录"
          description="每个条目均给出新鲜度、质量、保留策略、来源和可执行查询链接。"
          action={
            <span className={styles.resultCount}>
              {catalogQuery.isFetching ? "同步中…" : `${entries.length} / ${catalogTotal}`}
            </span>
          }
        />
        {catalogQuery.isError ? (
          <div className={styles.errorBanner} role="alert">
            API 同步失败；
            {isProduction ? "生产模式不会显示演示目录。" : "目录继续显示最后一次确定性快照。"}
          </div>
        ) : null}
        {catalogQuery.isLoading ? (
          <div className={styles.loadingState}>正在读取数据目录…</div>
        ) : entries.length ? (
          <div className={styles.tableWrap}>
            <DataTable
              data={entries}
              columns={catalogColumns}
              getRowId={(entry) => entry.id}
              initialSorting={[{ id: "dataset", desc: false }]}
              pageSize={6}
              searchTextForRow={(entry) =>
                `${entry.name} ${entry.id} ${entry.source} ${entry.description}`
              }
              searchPlaceholder="搜索名称、ID、来源…"
              filterControls={
                <>
                  <label>
                    <span>分类</span>
                    <select
                      aria-label="筛选数据集分类"
                      value={category}
                      onChange={(event) => setCategory(event.target.value as typeof category)}
                    >
                      <option value="all">全部分类</option>
                      {dataCatalogCategories.map((value) => (
                        <option value={value} key={value}>
                          {categoryLabels[value]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>状态</span>
                    <select
                      aria-label="筛选数据集状态"
                      value={status}
                      onChange={(event) => setStatus(event.target.value as typeof status)}
                    >
                      <option value="all">全部状态</option>
                      {dataCatalogStatuses.map((value) => (
                        <option value={value} key={value}>
                          {statusLabels[value]}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              }
              bulkActions={[
                {
                  label: "复制数据集 ID",
                  onActivate: (selectedEntries) =>
                    navigator.clipboard.writeText(
                      selectedEntries.map((entry) => entry.id).join("\n"),
                    ),
                },
              ]}
              csvExport={{
                filename: "openvigil-data-catalog.csv",
                columns: [
                  { label: "数据集ID", value: (entry) => entry.id },
                  { label: "名称", value: (entry) => entry.name },
                  { label: "分类", value: (entry) => categoryLabels[entry.category] },
                  { label: "状态", value: (entry) => statusLabels[entry.status] },
                  { label: "记录数", value: (entry) => entry.recordCount },
                  { label: "新鲜度", value: (entry) => entry.freshness },
                  { label: "质量", value: (entry) => entry.quality },
                  { label: "保留策略", value: (entry) => entry.retention },
                  { label: "来源", value: (entry) => entry.source },
                  { label: "查询链接", value: (entry) => entry.queryHref },
                ],
              }}
            />
          </div>
        ) : (
          <EmptyState
            icon={<Search size={20} />}
            title="没有匹配的数据集"
            description={filtered ? "调整搜索词、分类或状态过滤后重试。" : "目录当前为空。"}
          />
        )}
      </Card>
    </AppShell>
  );
}
