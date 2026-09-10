"use client";

import {
  BrainCircuit,
  ExternalLink,
  FileText,
  LoaderCircle,
  Rocket,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { modelKinds, modelRegistry, modelStatuses } from "@/lib/platform-admin-data";

import styles from "./model-management-page.module.css";
import { initialEnvelope, kindIcons, kindLabels } from "./model-management-support";
import { useModelManagement } from "./use-model-management";

export function ModelManagementPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const {
    canManageModels,
    query,
    setQuery,
    kind,
    setKind,
    status,
    setStatus,
    setSelectedId,
    registrationOpen,
    setRegistrationOpen,
    setArtifact,
    registration,
    setRegistration,
    mutationState,
    setSelectedEvaluationId,
    revealEvaluationTruth,
    setRevealEvaluationTruth,
    registryQuery,
    models,
    selected,
    benchmarkEvaluationsQuery,
    benchmarkEvaluations,
    selectedEvaluation,
    benchmarkResultsQuery,
    registerArtifact,
    stageDeployment,
    activate,
    rollback,
  } = useModelManagement(runtimeMode);

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/models">
      <PageHeader
        eyebrow="模型治理"
        title="模型管理"
        description={
          runtimeMode === "production"
            ? "登记经过哈希校验的模型制品，治理部署流量、回滚和在线推理监控。"
            : "审阅 OpenVigil 当前确定性评分、检索与文档生成能力，以及它们真实的运行边界。"
        }
        breadcrumb={["平台管理", "模型管理"]}
        meta={
          <>
            <StatusBadge
              value={runtimeMode}
              label={runtimeMode === "production" ? "生产模型治理" : "能力披露"}
              tone={runtimeMode === "production" ? "success" : "warning"}
            />
            <span className="page-meta-text">
              {runtimeMode === "production"
                ? "制品哈希 · Schema 门禁 · 灰度流量 · 可审计回滚"
                : "无训练权重 · 无托管推理 · 无真实 embedding"}
            </span>
          </>
        }
        actions={
          runtimeMode === "production" ? (
            <Button
              onClick={() => setRegistrationOpen(true)}
              disabled={mutationState.busy || !canManageModels}
              title={canManageModels ? undefined : "需要 model.manage capability"}
            >
              <Upload size={15} /> 登记模型制品
            </Button>
          ) : undefined
        }
      />

      <section className={styles.disclosure} aria-label="模型能力披露">
        <ShieldAlert size={19} />
        <div>
          <strong>
            {runtimeMode === "production"
              ? "模型执行与应用控制保持隔离"
              : "这是能力注册表，不是生产 ML 模型仓库"}
          </strong>
          <p>{registryQuery.data?.meta.disclosure ?? initialEnvelope.meta.disclosure}</p>
        </div>
        <span>
          真实推理 <b>{registryQuery.data?.meta.realInferenceCount ?? 0}</b>
        </span>
        <span>
          {runtimeMode === "production" ? "活动部署" : "向量嵌入支持"}{" "}
          <b>
            {runtimeMode === "production"
              ? (registryQuery.data?.meta.activeDeploymentCount ?? 0)
              : (registryQuery.data?.meta.embeddingBackedCount ?? 0)}
          </b>
        </span>
      </section>

      {runtimeMode === "production" && !canManageModels ? (
        <div className={styles.errorBanner} role="status" data-capability="model.manage">
          当前身份可审阅模型注册表，但登记、部署、激活和回滚需要运维经理及全局模型授权。
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="模型注册表摘要">
        <Card>
          <small>已注册引擎</small>
          <strong>{registryQuery.data?.meta.total ?? modelRegistry.length}</strong>
          <em>确定性能力</em>
        </Card>
        <Card>
          <small>{runtimeMode === "production" ? "活动部署" : "仅演示"}</small>
          <strong>
            {runtimeMode === "production"
              ? (registryQuery.data?.meta.activeDeploymentCount ?? 0)
              : modelRegistry.filter((model) => model.status === "demo-only").length}
          </strong>
          <em>{runtimeMode === "production" ? "总流量覆盖 100%" : "不可用于真实决策"}</em>
        </Card>
        <Card>
          <small>真实推理</small>
          <strong>{registryQuery.data?.meta.realInferenceCount ?? 0}</strong>
          <em>
            {runtimeMode === "production"
              ? `P95 ${registryQuery.data?.meta.monitoring?.p95LatencyMs ?? 0} ms`
              : "未配置模型服务"}
          </em>
        </Card>
        <Card>
          <small>模型制品</small>
          <strong>{registryQuery.data?.meta.artifactCount ?? 0}</strong>
          <em>{runtimeMode === "production" ? "MinIO + SHA-256" : "无权重与校准包"}</em>
        </Card>
      </section>

      <Card className={styles.toolbar}>
        <label className={styles.searchField}>
          <Search size={15} />
          <span className="sr-only">搜索模型能力</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={100}
            placeholder="搜索模型、输入或输出…"
          />
        </label>
        <label>
          <span>能力类型</span>
          <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
            <option value="all">全部类型</option>
            {modelKinds.map((value) => (
              <option value={value} key={value}>
                {kindLabels[value]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>状态</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as typeof status)}
          >
            <option value="all">全部状态</option>
            {modelStatuses.map((value) => (
              <option value={value} key={value}>
                {value === "available"
                  ? "可用"
                  : runtimeMode === "production"
                    ? "待部署"
                    : "仅演示"}
              </option>
            ))}
          </select>
        </label>
        <span className={styles.resultCount}>
          {registryQuery.isFetching
            ? "同步中…"
            : `${models.length} / ${registryQuery.data?.meta.total ?? modelRegistry.length}`}
        </span>
      </Card>

      {registryQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          {runtimeMode === "production"
            ? "生产模型注册表不可用；未回退到演示数据。"
            : "API 同步失败；继续显示最后一次确定性注册表快照。"}
        </div>
      ) : null}
      {mutationState.error || mutationState.message ? (
        <div className={styles.errorBanner} role="status">
          {mutationState.error ?? mutationState.message}
        </div>
      ) : null}

      <section className={styles.workspace}>
        <Card className={styles.registryList}>
          <CardHeader
            eyebrow="能力注册表"
            title="能力与版本"
            description="选择条目查看输入、输出、指标与限制。"
          />
          {registryQuery.isLoading ? (
            <div className={styles.loadingState}>正在读取模型注册表…</div>
          ) : models.length ? (
            <div className={styles.modelList}>
              {models.map((model) => {
                const Icon = kindIcons[model.kind];
                return (
                  <button
                    type="button"
                    data-selected={selected?.id === model.id}
                    onClick={() => {
                      setSelectedId(model.id);
                      setSelectedEvaluationId("");
                      setRevealEvaluationTruth(false);
                    }}
                    key={model.id}
                  >
                    <span className={styles.modelIcon}>
                      <Icon size={17} />
                    </span>
                    <span>
                      <strong>{model.name}</strong>
                      <small>
                        {model.id} · v{model.version}
                      </small>
                      <em>{model.runtime}</em>
                    </span>
                    <span className={styles.modelState}>
                      <StatusBadge
                        value={model.status}
                        label={
                          model.status === "available"
                            ? "可用"
                            : runtimeMode === "production"
                              ? "待部署"
                              : "仅演示"
                        }
                        tone={model.status === "available" ? "success" : "warning"}
                        compact
                      />
                      <small>{kindLabels[model.kind]}</small>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配的能力"
              description="调整搜索词、能力类型或状态过滤后重试。"
            />
          )}
        </Card>

        <Card className={styles.detailPanel}>
          {selected ? (
            <>
              <CardHeader
                eyebrow={`${kindLabels[selected.kind]} · v${selected.version}`}
                title={selected.name}
                description={selected.runtime}
                action={
                  <StatusBadge
                    value={selected.lifecycleStatus ?? "deterministic"}
                    label={selected.lifecycleStatus ?? "确定性"}
                    tone={selected.realInference ? "success" : "info"}
                  />
                }
              />

              <div className={styles.boundaries}>
                <span data-enabled={selected.realInference}>
                  <Sparkles size={14} />
                  <span>
                    <small>真实推理</small>
                    <strong>{selected.realInference ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.usesEmbeddings}>
                  <BrainCircuit size={14} />
                  <span>
                    <small>向量嵌入</small>
                    <strong>{selected.usesEmbeddings ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.artifactBacked}>
                  <FileText size={14} />
                  <span>
                    <small>模型制品</small>
                    <strong>{selected.artifactBacked ? "已登记" : "无"}</strong>
                  </span>
                </span>
              </div>

              <div className={styles.ioGrid}>
                <section>
                  <h3>输入</h3>
                  <ul>
                    {selected.inputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h3>输出</h3>
                  <ul>
                    {selected.outputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
              </div>

              <section className={styles.metrics}>
                <h3>指标与证据</h3>
                <div>
                  {selected.metrics.map((metric) => (
                    <span key={metric.label}>
                      <small>{metric.label}</small>
                      <strong>{metric.value}</strong>
                    </span>
                  ))}
                </div>
              </section>

              <section className={styles.limitation}>
                <ShieldAlert size={16} />
                <div>
                  <strong>能力边界</strong>
                  <p>{selected.limitation}</p>
                </div>
              </section>

              {runtimeMode === "production" ? (
                <section className={styles.deployments}>
                  <div>
                    <h3>部署与流量</h3>
                    <Button
                      variant="secondary"
                      onClick={() => void stageDeployment()}
                      disabled={!canManageModels || mutationState.busy}
                    >
                      <Rocket size={14} /> 创建部署
                    </Button>
                  </div>
                  {selected.deployments?.length ? (
                    selected.deployments.map((deployment) => (
                      <article key={deployment.id}>
                        <span>
                          <strong>{deployment.targetId}</strong>
                          <small>
                            {deployment.status} · {deployment.trafficPercent}% 流量
                          </small>
                        </span>
                        <div>
                          {deployment.status !== "active" ? (
                            <Button
                              variant="secondary"
                              onClick={() => void activate(deployment.id)}
                              disabled={mutationState.busy || !canManageModels}
                            >
                              <Rocket size={13} /> 激活
                            </Button>
                          ) : null}
                          {deployment.status === "inactive" ? (
                            <Button
                              variant="secondary"
                              onClick={() => void rollback(deployment.id)}
                              disabled={mutationState.busy || !canManageModels}
                            >
                              <RotateCcw size={13} /> 回滚至此
                            </Button>
                          ) : null}
                        </div>
                      </article>
                    ))
                  ) : (
                    <p>尚无部署。登记制品后创建部署，激活前不会接收生产流量。</p>
                  )}
                </section>
              ) : null}

              {runtimeMode === "production" && selected.kind === "anomaly" ? (
                <section className={styles.benchmarkGovernance} aria-label="CARE 基准评估治理">
                  <div className={styles.benchmarkHeader}>
                    <div>
                      <span>CARE v6 · 权威评估</span>
                      <h3>异常模型发布证据</h3>
                      <p>数据库指标与不可变制品；服务器门槛不可由页面覆盖。</p>
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => void benchmarkEvaluationsQuery.refetch()}
                      disabled={benchmarkEvaluationsQuery.isFetching}
                    >
                      <RotateCcw size={13} />
                      {benchmarkEvaluationsQuery.isFetching ? "同步中…" : "刷新评估"}
                    </Button>
                  </div>

                  {benchmarkEvaluationsQuery.isLoading ? (
                    <div className={styles.benchmarkState}>
                      <LoaderCircle size={15} /> 正在读取受治理评估…
                    </div>
                  ) : benchmarkEvaluationsQuery.isError ? (
                    <div className={styles.benchmarkState} data-tone="error" role="alert">
                      <ShieldAlert size={15} /> 评估 API 或权限校验失败；未显示演示指标。
                    </div>
                  ) : !benchmarkEvaluations.length ? (
                    <div className={styles.benchmarkState}>
                      此 anomaly 模型没有可用的 CARE 评估运行；模型不得据此宣称通过发布门槛。
                    </div>
                  ) : selectedEvaluation ? (
                    <>
                      <div className={styles.evaluationTabs} role="list" aria-label="评估运行">
                        {benchmarkEvaluations.map((evaluation) => (
                          <button
                            type="button"
                            key={evaluation.evaluation_run_id}
                            data-selected={
                              evaluation.evaluation_run_id === selectedEvaluation.evaluation_run_id
                            }
                            onClick={() => {
                              setSelectedEvaluationId(evaluation.evaluation_run_id);
                              setRevealEvaluationTruth(false);
                            }}
                          >
                            <strong>{evaluation.model.evaluation_role ?? "未标注角色"}</strong>
                            <small>{evaluation.evaluation_run_id}</small>
                            <StatusBadge
                              value={evaluation.server_gate.eligible ? "passed" : "failed"}
                              label={evaluation.server_gate.eligible ? "门槛通过" : "门槛失败"}
                              tone={evaluation.server_gate.eligible ? "success" : "critical"}
                              compact
                            />
                          </button>
                        ))}
                      </div>

                      <div className={styles.evaluationFacts}>
                        <span>
                          <small>算法 / 类型</small>
                          <strong>
                            {selectedEvaluation.model.algorithm ?? "未登记"} · anomaly
                          </strong>
                        </span>
                        <span>
                          <small>协议 / 风场</small>
                          <strong>
                            {selectedEvaluation.run.protocol_version} ·{" "}
                            {selectedEvaluation.run.farm ?? "多场"}
                          </strong>
                        </span>
                        <span>
                          <small>特征 / 质量</small>
                          <strong>
                            {selectedEvaluation.run.feature_set_version} ·{" "}
                            {selectedEvaluation.run.quality_rule_version}
                          </strong>
                        </span>
                        <span>
                          <small>阈值 / 随机种子</small>
                          <strong>
                            {selectedEvaluation.run.threshold_policy_version} ·{" "}
                            {selectedEvaluation.run.random_seed}
                          </strong>
                        </span>
                      </div>

                      <div
                        className={styles.releaseGate}
                        data-passed={selectedEvaluation.server_gate.eligible}
                      >
                        <ShieldAlert size={15} />
                        <span>
                          <strong>
                            服务器发布门槛：
                            {selectedEvaluation.server_gate.eligible ? "通过" : "未通过"}
                          </strong>
                          <small>
                            {selectedEvaluation.server_gate.reasons.length
                              ? selectedEvaluation.server_gate.reasons.join(" · ")
                              : "不可变评估、事件核算和 release metrics 均满足。"}
                          </small>
                        </span>
                      </div>

                      <div className={styles.accountingGrid}>
                        {Object.entries(selectedEvaluation.event_accounting).map(([key, value]) => (
                          <span
                            key={key}
                            data-alert={(key === "failed" || key === "unscorable") && value > 0}
                          >
                            <small>
                              {key === "requested"
                                ? "请求事件"
                                : key === "scored"
                                  ? "已评分"
                                  : key === "failed"
                                    ? "失败"
                                    : "不可评分"}
                            </small>
                            <strong>{value}</strong>
                          </span>
                        ))}
                      </div>

                      <div className={styles.metricTable}>
                        {selectedEvaluation.metrics.map((metric) => (
                          <span key={metric.name} data-failed={metric.passed === false}>
                            <small>{metric.name}</small>
                            <strong>
                              {metric.value} {metric.unit}
                            </strong>
                            <em>
                              {metric.is_release_metric
                                ? [
                                    "release",
                                    metric.threshold_direction ?? "—",
                                    metric.threshold_value ?? "—",
                                    metric.passed ? "PASS" : "FAIL",
                                  ].join(" · ")
                                : "观察指标"}
                            </em>
                          </span>
                        ))}
                      </div>

                      <div className={styles.artifactStatus}>
                        <span data-missing={!selectedEvaluation.model.artifact.present}>
                          模型制品{" "}
                          {selectedEvaluation.model.artifact.present
                            ? selectedEvaluation.model.artifact.sha256?.slice(0, 12)
                            : "缺失"}
                        </span>
                        <span data-missing={!selectedEvaluation.evaluation_artifact.present}>
                          评估制品{" "}
                          {selectedEvaluation.evaluation_artifact.present
                            ? selectedEvaluation.evaluation_artifact.sha256?.slice(0, 12)
                            : "缺失"}
                        </span>
                        {selectedEvaluation.deployments.map((deployment) => (
                          <span
                            key={deployment.deployment_id}
                            data-missing={deployment.authorization_state === "stale"}
                          >
                            部署 {deployment.deployment_id.slice(0, 12)} ·{" "}
                            {deployment.authorization_state === "current"
                              ? "授权当前"
                              : deployment.authorization_state === "stale"
                                ? "授权已陈旧"
                                : deployment.authorization_state}
                          </span>
                        ))}
                      </div>

                      <div className={styles.resultHeader}>
                        <div>
                          <strong>事件级结果</strong>
                          <small>
                            失败与不可评分事件不会隐藏；提前量是事件评分项，不是经验证 RUL。
                          </small>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => setRevealEvaluationTruth((current) => !current)}
                          disabled={
                            benchmarkResultsQuery.isFetching ||
                            !benchmarkResultsQuery.data?.meta.truth_reveal_allowed
                          }
                          title={
                            benchmarkResultsQuery.data?.meta.truth_reveal_allowed
                              ? undefined
                              : "当前身份没有 benchmark_truth 数据范围"
                          }
                        >
                          {revealEvaluationTruth ? "隐藏真值" : "按权限揭示真值"}
                        </Button>
                      </div>
                      {benchmarkResultsQuery.isLoading ? (
                        <div className={styles.benchmarkState}>正在读取事件结果…</div>
                      ) : benchmarkResultsQuery.isError ? (
                        <div className={styles.benchmarkState} data-tone="error" role="alert">
                          事件结果或真值权限请求失败；未回退到 fixture。
                        </div>
                      ) : benchmarkResultsQuery.data?.data.length ? (
                        <div className={styles.eventResults}>
                          {benchmarkResultsQuery.data.data.map((result) => (
                            <article key={result.result_id} data-status={result.status}>
                              <span>
                                <strong>
                                  {result.farm}
                                  {result.event_id} · {result.status}
                                </strong>
                                <small>
                                  {result.failure_code ?? result.result_sha256.slice(0, 12)}
                                </small>
                              </span>
                              <span>
                                <small>CARE / coverage / accuracy</small>
                                <strong>
                                  {result.scores.care ?? "—"} / {result.scores.coverage ?? "—"} /{" "}
                                  {result.scores.accuracy ?? "—"}
                                </strong>
                              </span>
                              <span>
                                <small>真值</small>
                                <strong>
                                  {result.truth.access === "revealed"
                                    ? [
                                        result.truth.event_label ?? "—",
                                        result.truth.failure_type ?? "无故障描述",
                                      ].join(" · ")
                                    : "受限"}
                                </strong>
                              </span>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.benchmarkState}>该评估没有事件级结果。</div>
                      )}
                    </>
                  ) : null}
                </section>
              ) : runtimeMode === "demo" && selected.kind === "anomaly" ? (
                <section className={styles.benchmarkGovernance} aria-label="CARE 基准评估边界">
                  <div className={styles.benchmarkState}>
                    演示模式不会用固定模型卡冒充 CARE 评估、release metric 或服务器门槛。
                  </div>
                </section>
              ) : null}

              <Link className={styles.endpointLink} href={selected.endpoint}>
                打开只读接口 <ExternalLink size={13} />
              </Link>
            </>
          ) : (
            <EmptyState
              icon={<BrainCircuit size={20} />}
              title="选择一项能力"
              description="从左侧注册表选择能力以查看详情。"
            />
          )}
        </Card>
      </section>

      {registrationOpen ? (
        <div className={styles.dialogBackdrop} role="presentation">
          <form
            className={styles.registrationDialog}
            onSubmit={(event) => void registerArtifact(event)}
          >
            <header>
              <div>
                <strong>登记预测模型制品</strong>
                <p>
                  制品将直传对象存储；后端验证对象范围、内容类型和
                  SHA-256。寿命与故障概率字段仅适用于已经独立完成业务验证的外部模型；CARE
                  不验证这些能力，Demo 也不会生成或展示此类结论。
                </p>
              </div>
              <button type="button" onClick={() => setRegistrationOpen(false)} aria-label="关闭">
                <X size={16} />
              </button>
            </header>
            <div className={styles.registrationGrid}>
              <label>
                <span>模型 ID</span>
                <input
                  required
                  pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}"
                  value={registration.modelId}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, modelId: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>版本</span>
                <input
                  required
                  value={registration.version}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, version: event.target.value }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>名称</span>
                <input
                  required
                  value={registration.name}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, name: event.target.value }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>制品（ONNX、JSON、ZIP 或二进制包）</span>
                <input
                  required
                  type="file"
                  accept=".onnx,.json,.zip,.bin,application/onnx,application/json,application/zip"
                  onChange={(event) => setArtifact(event.target.files?.[0] ?? null)}
                />
              </label>
              <label className={styles.wideField}>
                <span>治理说明</span>
                <input
                  required
                  minLength={3}
                  value={registration.description}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      description: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>输入 JSON Schema</span>
                <textarea
                  required
                  rows={14}
                  value={registration.inputSchema}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      inputSchema: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>输出 JSON Schema</span>
                <textarea
                  required
                  rows={14}
                  value={registration.outputSchema}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      outputSchema: event.target.value,
                    }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>验证指标 JSON</span>
                <textarea
                  required
                  rows={3}
                  value={registration.metrics}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, metrics: event.target.value }))
                  }
                />
              </label>
            </div>
            <footer>
              <Button type="button" variant="secondary" onClick={() => setRegistrationOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={mutationState.busy || !canManageModels}>
                {mutationState.busy ? <LoaderCircle size={14} /> : <Upload size={14} />}
                校验并登记
              </Button>
            </footer>
          </form>
        </div>
      ) : null}
    </AppShell>
  );
}
