"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
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
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
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

function applyTheme(preference: ThemePreference): void {
  const resolved =
    preference === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : preference;
  window.localStorage.setItem("windops-theme", preference);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  window.dispatchEvent(new CustomEvent("windops-theme-change"));
}

export function SystemSettingsPage() {
  const [theme, setTheme] = useState<ThemePreference>("light");
  const statusQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: ({ signal }) => apiGet<SystemEnvelope>("/api/system-status", signal),
    initialData: initialEnvelope,
    initialDataUpdatedAt: 0,
  });

  useEffect(() => {
    const stored = window.localStorage.getItem("windops-theme");
    const preference: ThemePreference =
      stored === "dark" || stored === "system" || stored === "light" ? stored : "light";
    const frame = window.requestAnimationFrame(() => setTheme(preference));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const data = statusQuery.data.data;

  const updateTheme = (preference: ThemePreference) => {
    setTheme(preference);
    applyTheme(preference);
  };

  return (
    <AppShell activePath="/settings">
      <PageHeader
        eyebrow="SYSTEM CONTROL"
        title="系统设置"
        description="核验运行时、D1、WebSocket 与身份边界，并管理真实生效的本机显示主题。"
        breadcrumb={["平台管理", "系统设置"]}
        meta={
          <>
            <StatusBadge
              value={data.integrity.valid ? "healthy" : "degraded"}
              label={data.integrity.valid ? "INTEGRITY PASS" : "INTEGRITY DEGRADED"}
              tone={data.integrity.valid ? "success" : "critical"}
            />
            <span className="page-meta-text">诊断仅返回状态，不暴露配置值</span>
          </>
        }
        actions={
          <Button
            variant="secondary"
            loading={statusQuery.isFetching}
            onClick={() => void statusQuery.refetch()}
          >
            <RefreshCw size={14} /> 重新检测
          </Button>
        }
      />

      {statusQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          在线诊断暂不可用；以下内容来自安全的只读基线，不包含敏感值。
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="系统状态摘要">
        <Card>
          <span>
            <Server size={18} />
          </span>
          <small>RUNTIME</small>
          <strong>WORKER ESM</strong>
          <em>vinext / RSC</em>
        </Card>
        <Card>
          <span>
            <Database size={18} />
          </span>
          <small>D1 WORKFLOW</small>
          <strong>{data.persistence.d1Binding === "bound" ? "BOUND" : "NOT BOUND"}</strong>
          <em>
            {data.persistence.workflowStore} · revision {data.persistence.workflowRevision}
          </em>
        </Card>
        <Card>
          <span>
            <Radio size={18} />
          </span>
          <small>WEBSOCKET ROUTES</small>
          <strong>{data.websockets.length}</strong>
          <em>deterministic demo streams</em>
        </Card>
        <Card>
          <span>
            <KeyRound size={18} />
          </span>
          <small>IDENTITY MODE</small>
          <strong>DEMO PRINCIPAL</strong>
          <em>server allow-list</em>
        </Card>
      </section>

      <section className={styles.mainGrid}>
        <Card className={styles.diagnostics}>
          <CardHeader
            eyebrow="CONNECTION DIAGNOSTICS"
            title="连接诊断"
            description="结论来自当前 Worker 能力与内部契约；不会把未执行的外部握手标记为成功。"
          />
          <div className={styles.connectionList}>
            {data.connections.map((connection) => (
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
                  label={connection.state.toUpperCase()}
                  tone={connection.state === "pass" ? "success" : "warning"}
                  compact
                />
              </article>
            ))}
          </div>
        </Card>

        <Card className={styles.runtimePanel}>
          <CardHeader
            eyebrow="RUNTIME & IDENTITY"
            title="运行与身份边界"
            description="只读配置摘要；敏感变量名和值均不进入响应。"
          />
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
              <dd>{data.runtime.execution}</dd>
            </div>
            <div>
              <dt>API 缓存</dt>
              <dd>{data.runtime.apiCachePolicy}</dd>
            </div>
            <div>
              <dt>身份模式</dt>
              <dd>{data.identity.mode}</dd>
            </div>
            <div>
              <dt>生产 SSO</dt>
              <dd>{data.identity.productionSso}</dd>
            </div>
          </dl>
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
            eyebrow="LOCAL PREFERENCE"
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
                    <small>{option.id}</small>
                  </span>
                  {theme === option.id ? <CheckCircle2 size={15} /> : null}
                </button>
              );
            })}
          </div>
          <p className={styles.localNote}>存储位置：{data.theme.persistence} · 不写入服务器</p>
        </Card>

        <Card className={styles.websocketPanel}>
          <CardHeader
            eyebrow="REALTIME CONTRACTS"
            title="WebSocket 通道"
            description="页面消费者可使用的同源演示流；此处只读，不伪造连接开关。"
          />
          <div className={styles.websocketList}>
            {data.websockets.map((socket) => (
              <Link href={socket.endpoint} key={socket.endpoint}>
                <Radio size={15} />
                <span>
                  <strong>{socket.endpoint}</strong>
                  <small>{socket.channel}</small>
                </span>
                <StatusBadge value="demo" label="DEMO STREAM" tone="info" compact />
                <ExternalLink size={12} />
              </Link>
            ))}
          </div>
        </Card>
      </section>

      <Card className={styles.policyPanel}>
        <CardHeader
          eyebrow="DATA POLICIES"
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
    </AppShell>
  );
}
