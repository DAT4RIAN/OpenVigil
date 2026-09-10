"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  ExternalLink,
  KeyRound,
  Monitor,
  Moon,
  Radio,
  RefreshCw,
  Server,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { apiGet, apiPost } from "@/lib/api-client";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import {
  PLATFORM_SNAPSHOT_AT,
  systemStatusFallback,
  type SystemStatusSnapshot,
} from "@/lib/platform-admin-data";
import styles from "./system-settings-page.module.css";

type ThemePreference = "light" | "dark" | "system";

type SystemEnvelope = {
  data: SystemStatusSnapshot;
  meta: {
    count: number;
    total: number;
    deterministic: true;
    readOnly: true;
    snapshotAt: string;
    redacted: true;
  };
};

type RuntimeEnvelope = {
  data: {
    runtimeMode: "demo" | "production";
    backendAuthentication: "sites_delegation" | "service_token";
    productionReady: boolean;
    fixtureFallbackAllowed: boolean;
    backend: {
      configured: boolean;
      reachable: boolean;
      status: number | null;
      latencyMs: number | null;
      errorCode: string | null;
      release: {
        releaseId: string;
        commitSha: string;
        imageDigest: string;
      } | null;
    };
  };
  error: null;
  meta: { readOnly: true; secretsRedacted: true };
};

type PlatformConfigurationEnvelope = {
  configurations: readonly {
    configuration_key: string;
    revision: number;
    value: Readonly<Record<string, unknown>>;
    secret_configured: boolean;
    reason: string;
    created_by: string;
    created_at: string;
  }[];
  meta: {
    secrets_redacted: true;
    serialization_verified: boolean;
    snapshot_at: string;
  };
};

type PlatformConfigurationStatusEnvelope = {
  data: {
    status: "ready" | "attention_required";
    configured_keys: readonly string[];
    configuration_count: number;
    pending_credential_rotations: number;
  };
  meta: { redacted: true; snapshot_at: string };
};

type ConfigurationKey =
  "scada_retention" | "event_stream" | "identity" | "model_governance" | "backup_policy";

const configurationTemplates: Readonly<Record<ConfigurationKey, string>> = {
  backup_policy: JSON.stringify(
    {
      schema_version: 1,
      rpo_minutes: 15,
      rto_minutes: 60,
      verification: { schema_version: 1, restore_test_interval_days: 30, retention_days: 30 },
    },
    null,
    2,
  ),
  scada_retention: JSON.stringify(
    { schema_version: 1, days: 365, downsample_after_days: 30 },
    null,
    2,
  ),
  event_stream: JSON.stringify(
    { schema_version: 1, transport: "sse", max_batch_size: 200 },
    null,
    2,
  ),
  identity: JSON.stringify(
    {
      schema_version: 1,
      issuer: "https://identity.example.com",
      audience: "windops",
      jwks_cache_seconds: 300,
    },
    null,
    2,
  ),
  model_governance: JSON.stringify(
    {
      schema_version: 1,
      approval_required: true,
      automatic_rollback: true,
      evaluation: {
        schema_version: 1,
        minimum_validation_auc: 0.8,
        minimum_evaluation_samples: 100,
        maximum_regression_percent: 2,
      },
    },
    null,
    2,
  ),
};

const initialEnvelope: SystemEnvelope = {
  data: systemStatusFallback,
  meta: {
    count: systemStatusFallback.connections.length,
    total: systemStatusFallback.connections.length,
    deterministic: true,
    readOnly: true,
    snapshotAt: PLATFORM_SNAPSHOT_AT,
    redacted: true,
  },
};

const themeOptions: readonly {
  readonly id: ThemePreference;
  readonly label: string;
  readonly icon: typeof Sun;
}[] = [
  { id: "light", label: "浅色", icon: Sun },
  { id: "dark", label: "深色", icon: Moon },
  { id: "system", label: "跟随系统", icon: Monitor },
];

const systemValueLabels: Readonly<Record<string, string>> = {
  bound: "已绑定",
  "not-bound": "未绑定",
  d1: "D1 持久化",
  ephemeral: "临时只读",
  pass: "通过",
  limited: "受限",
  light: "浅色",
  dark: "深色",
  system: "跟随系统",
  "server-demo-principal": "服务器演示主体",
  "not-configured": "未配置",
  "browser-local openvigil-theme": "浏览器本地 openvigil-theme",
};

const localizedSystemValue = (value: string): string => systemValueLabels[value] ?? value;

const themePreferenceKey = "openvigil-theme";
const legacyThemePreferenceKey = "windops-theme";

function applyTheme(preference: ThemePreference): void {
  const resolved =
    preference === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : preference;
  window.localStorage.setItem(themePreferenceKey, preference);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  window.dispatchEvent(new CustomEvent("openvigil-theme-change"));
}

export function SystemSettingsPage({
  runtimeMode = "demo",
}: {
  readonly runtimeMode?: OpenVigilRuntimeMode;
}) {
  const { can } = useOpenVigilIdentity();
  const canManagePlatform = runtimeMode === "demo" || can("platform.manage");
  const [theme, setTheme] = useState<ThemePreference>("light");
  const [configurationKey, setConfigurationKey] = useState<ConfigurationKey>("backup_policy");
  const [configurationValue, setConfigurationValue] = useState(
    configurationTemplates.backup_policy,
  );
  const [secretReference, setSecretReference] = useState("");
  const [configurationReason, setConfigurationReason] = useState("");
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: ({ signal }) => apiGet<SystemEnvelope>("/api/system-status", signal),
    initialData: runtimeMode === "demo" ? initialEnvelope : undefined,
    initialDataUpdatedAt: 0,
    enabled: runtimeMode === "demo",
  });
  const runtimeQuery = useQuery({
    queryKey: ["production-runtime"],
    queryFn: ({ signal }) => apiGet<RuntimeEnvelope>("/api/runtime", signal),
    retry: false,
  });
  const platformQuery = useQuery({
    queryKey: ["platform-configurations"],
    queryFn: ({ signal }) =>
      apiGet<PlatformConfigurationEnvelope>("/api/backend/platform/configurations", signal),
    enabled: runtimeMode === "production",
    retry: false,
  });
  const platformStatusQuery = useQuery({
    queryKey: ["platform-configuration-status"],
    queryFn: ({ signal }) =>
      apiGet<PlatformConfigurationStatusEnvelope>(
        "/api/backend/platform/configuration-status",
        signal,
      ),
    enabled: runtimeMode === "production",
    retry: false,
  });
  const configurationMutation = useMutation({
    mutationFn: async () => {
      if (!canManagePlatform) {
        throw new Error("当前角色没有创建平台配置修订的权限。");
      }
      let value: Readonly<Record<string, unknown>>;
      try {
        const parsed = JSON.parse(configurationValue) as unknown;
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("配置值必须是 JSON 对象。");
        }
        value = parsed as Readonly<Record<string, unknown>>;
      } catch (error) {
        throw error instanceof Error ? error : new Error("配置值不是有效 JSON。");
      }
      const current = platformQuery.data?.configurations.find(
        (item) => item.configuration_key === configurationKey,
      );
      return apiPost("/api/backend/platform/configurations", {
        configuration_key: configurationKey,
        value,
        secret_reference: secretReference.trim() || null,
        expected_revision: current?.revision ?? 0,
        reason: configurationReason.trim(),
      });
    },
    onSuccess: async () => {
      setConfigurationReason("");
      setSecretReference("");
      await queryClient.invalidateQueries({ queryKey: ["platform-configurations"] });
    },
  });

  useEffect(() => {
    const current = window.localStorage.getItem(themePreferenceKey);
    const stored = current ?? window.localStorage.getItem(legacyThemePreferenceKey);
    if (current === null && stored !== null) {
      window.localStorage.setItem(themePreferenceKey, stored);
    }
    const preference: ThemePreference =
      stored === "dark" || stored === "system" || stored === "light" ? stored : "light";
    const frame = window.requestAnimationFrame(() => setTheme(preference));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const data = statusQuery.data?.data ?? initialEnvelope.data;
  const runtime = runtimeQuery.data?.data;
  const productionMode = runtimeMode === "production" || runtime?.runtimeMode === "production";
  const productionReady = runtime?.productionReady === true;

  const updateTheme = (preference: ThemePreference) => {
    setTheme(preference);
    applyTheme(preference);
  };

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/settings">
      <PageHeader
        eyebrow="系统控制"
        title="系统设置"
        description="核验运行时、D1、WebSocket 与身份边界，并管理真实生效的本机显示主题。"
        breadcrumb={["平台管理", "系统设置"]}
        meta={
          <>
            <StatusBadge
              value={productionMode && !productionReady ? "degraded" : "healthy"}
              label={
                productionMode
                  ? productionReady
                    ? "生产后端就绪"
                    : "生产后端未就绪"
                  : data.integrity.valid
                    ? "Demo 完整性校验通过"
                    : "Demo 完整性校验降级"
              }
              tone={productionMode && !productionReady ? "critical" : "success"}
            />
            <span className="page-meta-text">诊断仅返回状态，不暴露配置值</span>
          </>
        }
        actions={
          <Button
            variant="secondary"
            loading={statusQuery.isFetching || runtimeQuery.isFetching}
            onClick={() =>
              void Promise.all(
                runtimeMode === "production"
                  ? [runtimeQuery.refetch(), platformQuery.refetch()]
                  : [statusQuery.refetch(), runtimeQuery.refetch()],
              )
            }
          >
            <RefreshCw size={14} /> 重新检测
          </Button>
        }
      />

      {!productionMode && statusQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          在线诊断暂不可用；以下内容来自安全的只读基线，不包含敏感值。
        </div>
      ) : null}

      {runtimeQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          生产运行时就绪探针失败；系统不会因此回退到 fixture 数据。
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="系统状态摘要">
        <Card>
          <span>
            <Server size={18} />
          </span>
          <small>运行时</small>
          <strong>{productionMode ? "Production" : "Demo"}</strong>
          <em>
            {productionMode
              ? productionReady
                ? `Python 后端 · ${runtime?.backend.latencyMs ?? "—"} ms`
                : `失败关闭 · ${runtime?.backend.errorCode ?? "未就绪"}`
              : "Worker fixture / D1"}
          </em>
        </Card>
        <Card>
          <span>
            <Database size={18} />
          </span>
          <small>{productionMode ? "权威账本" : "D1 工作流"}</small>
          <strong>
            {productionMode
              ? "PostgreSQL"
              : data.persistence.d1Binding === "bound"
                ? "已绑定"
                : "未绑定"}
          </strong>
          <em>
            {productionMode
              ? `${platformQuery.data?.configurations.length ?? 0} 个版本化配置`
              : `${localizedSystemValue(data.persistence.workflowStore)} · 修订 ${data.persistence.workflowRevision}`}
          </em>
        </Card>
        <Card>
          <span>
            <Radio size={18} />
          </span>
          <small>{productionMode ? "事件流" : "WebSocket 路由"}</small>
          <strong>{productionMode ? "SSE" : data.websockets.length}</strong>
          <em>{productionMode ? "PostgreSQL 事件账本与持久游标" : "确定性演示数据流"}</em>
        </Card>
        <Card>
          <span>
            <KeyRound size={18} />
          </span>
          <small>身份模式</small>
          <strong>{productionMode ? "服务端身份" : "演示主体"}</strong>
          <em>{productionMode ? "令牌已脱敏 · 用户上下文转发" : "服务器允许名单"}</em>
        </Card>
      </section>

      <section className={styles.mainGrid}>
        <Card className={styles.diagnostics}>
          <CardHeader
            eyebrow="连接诊断"
            title="连接诊断"
            description="结论来自当前 Worker 能力与内部契约；不会把未执行的外部握手标记为成功。"
          />
          <div className={styles.connectionList}>
            {runtime ? (
              <article>
                <span data-state={runtime.productionReady ? "pass" : "limited"}>
                  {runtime.productionReady ? <CheckCircle2 size={16} /> : <ShieldCheck size={16} />}
                </span>
                <div>
                  <strong>Python 生产后端</strong>
                  <small>HTTPS 服务端探针</small>
                  <p>
                    {runtime.runtimeMode === "demo"
                      ? "当前为 Demo 模式；fixture 回退只允许在该模式中使用。"
                      : runtime.backend.reachable
                        ? `后端已就绪，发布 ${runtime.backend.release?.releaseId ?? "—"}，镜像 ${runtime.backend.release?.imageDigest.slice(0, 19) ?? "—"}…，响应 ${runtime.backend.status}，耗时 ${runtime.backend.latencyMs ?? "—"} ms。`
                        : `后端未就绪；错误 ${runtime.backend.errorCode ?? "UNKNOWN"}，生产请求保持失败关闭。`}
                  </p>
                </div>
                <StatusBadge
                  value={runtime.productionReady ? "pass" : "limited"}
                  label={runtime.productionReady ? "通过" : "受限"}
                  tone={runtime.productionReady ? "success" : "warning"}
                  compact
                />
              </article>
            ) : null}
            {!productionMode
              ? data.connections.map((connection) => (
                  <article key={connection.id}>
                    <span data-state={connection.state}>
                      {connection.state === "pass" ? (
                        <CheckCircle2 size={16} />
                      ) : (
                        <ShieldCheck size={16} />
                      )}
                    </span>
                    <div>
                      <strong>{connection.label}</strong>
                      <small>{connection.check}</small>
                      <p>{connection.detail}</p>
                    </div>
                    <StatusBadge
                      value={connection.state}
                      label={connection.state === "pass" ? "通过" : "受限"}
                      tone={connection.state === "pass" ? "success" : "warning"}
                      compact
                    />
                  </article>
                ))
              : null}
          </div>
        </Card>

        <Card className={styles.runtimePanel}>
          <CardHeader
            eyebrow="运行时与身份"
            title="运行与身份边界"
            description="只读配置摘要；敏感变量名和值均不进入响应。"
          />
          {productionMode ? (
            <dl className={styles.definitionList}>
              <div>
                <dt>应用</dt>
                <dd>OpenVigil Production</dd>
              </div>
              <div>
                <dt>运行边界</dt>
                <dd>Cloudflare Sites 网关 + FastAPI</dd>
              </div>
              <div>
                <dt>API 缓存</dt>
                <dd>敏感响应 no-store</dd>
              </div>
              <div>
                <dt>身份模式</dt>
                <dd>Sites 用户短期委托令牌</dd>
              </div>
              <div>
                <dt>配置账本</dt>
                <dd>PostgreSQL CAS 修订与外部 Secret 引用</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{productionReady ? "依赖就绪" : "失败关闭"}</dd>
              </div>
            </dl>
          ) : (
            <dl className={styles.definitionList}>
              <div>
                <dt>应用</dt>
                <dd>{data.runtime.application}</dd>
              </div>
              <div>
                <dt>框架</dt>
                <dd>{data.runtime.framework}</dd>
              </div>
              <div>
                <dt>执行环境</dt>
                <dd>兼容 Cloudflare Worker 的 ESM</dd>
              </div>
              <div>
                <dt>API 缓存</dt>
                <dd>{data.runtime.apiCachePolicy}</dd>
              </div>
              <div>
                <dt>身份模式</dt>
                <dd>{localizedSystemValue(data.identity.mode)}</dd>
              </div>
              <div>
                <dt>生产 SSO</dt>
                <dd>{localizedSystemValue(data.identity.productionSso)}</dd>
              </div>
            </dl>
          )}
          <div className={styles.securityNotice}>
            <ShieldCheck size={17} />
            <span>
              <strong>诊断已脱敏</strong>
              <small>不显示环境值、凭据、连接字符串或密钥名称。</small>
            </span>
          </div>
        </Card>
      </section>

      <section className={styles.secondaryGrid}>
        <Card className={styles.themePanel}>
          <CardHeader
            eyebrow="本地偏好"
            title="显示主题"
            description="选择后立即应用，并仅保存在当前浏览器。没有虚假的“保存设置”步骤。"
          />
          <div className={styles.themeOptions} role="group" aria-label="显示主题">
            {themeOptions.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  type="button"
                  key={option.id}
                  aria-pressed={theme === option.id}
                  data-selected={theme === option.id}
                  onClick={() => updateTheme(option.id)}
                >
                  <Icon size={18} />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{localizedSystemValue(option.id)}</small>
                  </span>
                  {theme === option.id ? <CheckCircle2 size={15} /> : null}
                </button>
              );
            })}
          </div>
          <p className={styles.localNote}>
            存储位置：
            {productionMode
              ? "浏览器 localStorage"
              : localizedSystemValue(data.theme.persistence)}{" "}
            · 不写入服务器
          </p>
        </Card>

        <Card className={styles.websocketPanel}>
          <CardHeader
            eyebrow="实时通道契约"
            title={productionMode ? "持久事件通道" : "WebSocket 通道"}
            description={
              productionMode
                ? "生产事件来自 PostgreSQL 领域事件账本，SSE 支持 Last-Event-ID 断点续传。"
                : "同源演示流只用于 Demo，不代表生产消息总线。"
            }
          />
          {productionMode ? (
            <div className={styles.connectionList}>
              <article>
                <span data-state="pass">
                  <Radio size={15} />
                </span>
                <div>
                  <strong>/api/agent-events</strong>
                  <small>SSE · 持久序列游标 · 事件类型过滤</small>
                  <p>生产网关代理 FastAPI /api/v1/events/stream，不生成确定性活动。</p>
                </div>
                <StatusBadge value="persistent" label="持久事件" tone="success" compact />
              </article>
            </div>
          ) : (
            <div className={styles.websocketList}>
              {data.websockets.map((socket) => (
                <Link href={socket.endpoint} key={socket.endpoint}>
                  <Radio size={15} />
                  <span>
                    <strong>{socket.endpoint}</strong>
                    <small>{socket.channel}</small>
                  </span>
                  <StatusBadge value="demo" label="演示数据流" tone="info" compact />
                  <ExternalLink size={12} />
                </Link>
              ))}
            </div>
          )}
        </Card>
      </section>

      {productionMode ? (
        <Card className={styles.policyPanel}>
          <CardHeader
            eyebrow="版本化平台治理"
            title="生产配置修订"
            description="每次保存都会创建新修订并记录操作者与原因；密钥只接受外部 Secret Manager 引用，响应永不返回密钥值。"
          />
          {platformStatusQuery.data ? (
            <p role="status">
              脱敏配置状态：
              {platformStatusQuery.data.data.status === "ready" ? "正常" : "需要处置"} · 已配置
              {platformStatusQuery.data.data.configuration_count} 项 · 待轮换凭据
              {platformStatusQuery.data.data.pending_credential_rotations} 项
            </p>
          ) : null}
          {!canManagePlatform ? (
            <div className={styles.errorBanner} role="status" data-capability="platform.manage">
              当前身份仅可审阅已授权的平台状态；创建配置修订需要运维经理和全局平台授权。
            </div>
          ) : null}
          {platformQuery.isError ? (
            <div className={styles.errorBanner} role="alert">
              无法读取完整平台配置；该视图仅对具有全局授权的运维经理开放。
            </div>
          ) : null}
          <div className={styles.mainGrid}>
            <div>
              <label>
                <span>配置域</span>
                <select
                  disabled={!canManagePlatform}
                  value={configurationKey}
                  onChange={(event) => {
                    const nextKey = event.target.value as ConfigurationKey;
                    setConfigurationKey(nextKey);
                    setConfigurationValue(configurationTemplates[nextKey]);
                  }}
                >
                  <option value="backup_policy">备份与恢复目标</option>
                  <option value="scada_retention">SCADA 保留策略</option>
                  <option value="event_stream">事件流</option>
                  <option value="identity">企业身份</option>
                  <option value="model_governance">模型治理</option>
                </select>
              </label>
              <label>
                <span>配置 JSON</span>
                <textarea
                  disabled={!canManagePlatform}
                  className="approval-comment"
                  value={configurationValue}
                  onChange={(event) => setConfigurationValue(event.target.value)}
                  aria-label="平台配置 JSON"
                />
              </label>
              <label>
                <span>Secret Manager 引用（可选）</span>
                <input
                  disabled={!canManagePlatform}
                  value={secretReference}
                  onChange={(event) => setSecretReference(event.target.value)}
                  placeholder="vault://openvigil/platform/credential"
                />
              </label>
              <label>
                <span>变更原因</span>
                <input
                  disabled={!canManagePlatform}
                  value={configurationReason}
                  onChange={(event) => setConfigurationReason(event.target.value)}
                  placeholder="关联审批单或变更请求"
                />
              </label>
              {configurationMutation.error instanceof Error ? (
                <p className={styles.errorBanner} role="alert">
                  {configurationMutation.error.message}
                </p>
              ) : null}
              <Button
                variant="primary"
                loading={configurationMutation.isPending}
                disabled={!canManagePlatform || configurationReason.trim().length < 3}
                title={canManagePlatform ? undefined : "需要 platform.manage capability"}
                onClick={() => configurationMutation.mutate()}
              >
                创建配置修订
              </Button>
            </div>
            <div className={styles.connectionList}>
              {(platformQuery.data?.configurations ?? []).map((configuration) => (
                <article key={configuration.configuration_key}>
                  <span data-state="pass">
                    <ShieldCheck size={16} />
                  </span>
                  <div>
                    <strong>{configuration.configuration_key}</strong>
                    <small>
                      修订 {configuration.revision} · {configuration.created_by}
                    </small>
                    <p>{JSON.stringify(configuration.value)}</p>
                  </div>
                  <StatusBadge
                    value={configuration.secret_configured ? "secret-bound" : "no-secret"}
                    label={configuration.secret_configured ? "密钥已托管" : "无密钥"}
                    tone={configuration.secret_configured ? "success" : "neutral"}
                    compact
                  />
                </article>
              ))}
              {!platformQuery.isLoading && !platformQuery.data?.configurations.length ? (
                <p>尚无已激活的平台配置修订。</p>
              ) : null}
            </div>
          </div>
        </Card>
      ) : null}

      {!productionMode ? (
        <Card className={styles.policyPanel}>
          <CardHeader
            eyebrow="数据策略"
            title="数据与保留策略"
            description="策略描述与当前实现一致；生产数据治理、SSO 和密钥托管尚未配置。"
          />
          <div className={styles.policyGrid}>
            {data.dataPolicies.map((policy) => (
              <article key={policy.id}>
                <small>{policy.id}</small>
                <strong>{policy.scope}</strong>
                <p>{policy.policy}</p>
                <span>{policy.enforcement}</span>
              </article>
            ))}
          </div>
        </Card>
      ) : null}
    </AppShell>
  );
}
