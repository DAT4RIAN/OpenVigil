"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Anchor,
  ArrowRight,
  CalendarClock,
  CloudSun,
  PackageCheck,
  Search,
  ShipWheel,
  UsersRound,
  Wrench,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState, Progress } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import { resourceCenterSnapshot } from "@/lib";
import type { ResourceCenterSnapshot } from "@/lib/types";
import { cn } from "@/lib/utils";

type ResourceTab = "spare-parts" | "crews" | "vessels" | "tools" | "weather";

type ResourceResponse = {
  data: Omit<ResourceCenterSnapshot, "snapshotAt">;
  meta: {
    count: number;
    total: number;
    snapshotAt: string;
    deterministic: true;
  };
};

const tabs: readonly { id: ResourceTab; label: string; icon: typeof PackageCheck }[] = [
  { id: "spare-parts", label: "备件库存", icon: PackageCheck },
  { id: "crews", label: "维护班组", icon: UsersRound },
  { id: "vessels", label: "作业船舶", icon: ShipWheel },
  { id: "tools", label: "专业工具", icon: Wrench },
  { id: "weather", label: "天气窗口", icon: CloudSun },
];

const availabilityLabel = {
  available: "可用",
  reserved: "已预留",
  assigned: "执行中",
  maintenance: "维护中",
} as const;

function ResourceContent({
  tab,
  resources,
  query,
}: {
  tab: ResourceTab;
  resources: ResourceResponse["data"];
  query: string;
}) {
  const normalized = query.trim().toLowerCase();
  const matches = (...values: readonly string[]) =>
    !normalized || values.some((value) => value.toLowerCase().includes(normalized));

  if (tab === "spare-parts") {
    const parts = resources.spareParts.filter((item) =>
      matches(item.name, item.partNumber, item.category, item.warehouse),
    );
    return parts.length ? (
      <div className="resource-table-wrap">
        <table className="resource-table">
          <thead>
            <tr>
              <th>备件</th>
              <th>位置</th>
              <th>在库</th>
              <th>预留</th>
              <th>可用</th>
              <th>状态</th>
              <th>关联</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.name}</strong>
                  <small>
                    {item.partNumber} · {item.category}
                  </small>
                </td>
                <td>{item.warehouse}</td>
                <td>
                  {item.onHand} {item.unit}
                </td>
                <td>{item.reserved}</td>
                <td>
                  <strong>{item.available}</strong>
                </td>
                <td>
                  <StatusBadge
                    value={item.status}
                    label={
                      item.status === "in-stock"
                        ? "库存正常"
                        : item.status === "low-stock"
                          ? "低库存"
                          : "缺货"
                    }
                    tone={
                      item.status === "in-stock"
                        ? "success"
                        : item.status === "low-stock"
                          ? "warning"
                          : "critical"
                    }
                    compact
                  />
                </td>
                <td>
                  {item.reservedForWorkOrderIds.map((id) => (
                    <Link key={id} href="/work-orders">
                      {id}
                    </Link>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <ResourceEmpty />
    );
  }

  if (tab === "crews") {
    const crews = resources.crews.filter((item) =>
      matches(item.name, item.currentLocation, ...item.specialties),
    );
    return crews.length ? (
      <div className="resource-card-grid">
        {crews.map((item) => (
          <article key={item.id} className="resource-entity-card">
            <span className="resource-entity-card__icon">
              <UsersRound size={18} />
            </span>
            <div className="resource-entity-card__header">
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.memberCount} 人 · {item.currentLocation}
                </small>
              </span>
              <StatusBadge
                value={item.availability}
                label={availabilityLabel[item.availability]}
                compact
              />
            </div>
            <div className="resource-chip-row">
              {item.specialties.map((value) => (
                <span key={value}>{value}</span>
              ))}
            </div>
            <small>{item.certifications.join(" · ")}</small>
            {item.assignedWorkOrderId ? (
              <Link href="/work-orders">
                {item.assignedWorkOrderId} <ArrowRight size={12} />
              </Link>
            ) : (
              <em>等待调度</em>
            )}
          </article>
        ))}
      </div>
    ) : (
      <ResourceEmpty />
    );
  }

  if (tab === "vessels") {
    const vessels = resources.vessels.filter((item) => matches(item.name, item.id, item.berth));
    return vessels.length ? (
      <div className="resource-card-grid">
        {vessels.map((item) => (
          <article key={item.id} className="resource-entity-card">
            <span className="resource-entity-card__icon">
              <ShipWheel size={18} />
            </span>
            <div className="resource-entity-card__header">
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.vesselType} · {item.berth}
                </small>
              </span>
              <StatusBadge
                value={item.availability}
                label={availabilityLabel[item.availability]}
                compact
              />
            </div>
            <div className="resource-metric-pair">
              <span>
                载员 <strong>{item.capacity}</strong>
              </span>
              <span>
                浪高限制 <strong>{item.maxWaveHeightM} m</strong>
              </span>
            </div>
            <small>
              {item.eta ? `预计 ${new Date(item.eta).toLocaleString("zh-CN")}` : "在港可调度"}
            </small>
            {item.assignedWorkOrderId ? (
              <Link href="/work-orders">
                {item.assignedWorkOrderId} <ArrowRight size={12} />
              </Link>
            ) : (
              <em>等待调度</em>
            )}
          </article>
        ))}
      </div>
    ) : (
      <ResourceEmpty />
    );
  }

  if (tab === "tools") {
    const tools = resources.tools.filter((item) =>
      matches(item.name, item.category, item.location),
    );
    return tools.length ? (
      <div className="resource-card-grid">
        {tools.map((item) => (
          <article key={item.id} className="resource-entity-card">
            <span className="resource-entity-card__icon">
              <Wrench size={18} />
            </span>
            <div className="resource-entity-card__header">
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.category} · {item.location}
                </small>
              </span>
              <StatusBadge
                value={item.availability}
                label={availabilityLabel[item.availability]}
                compact
              />
            </div>
            <small>校准到期 {new Date(item.calibrationDueAt).toLocaleDateString("zh-CN")}</small>
            {item.assignedWorkOrderId ? (
              <Link href="/work-orders">
                {item.assignedWorkOrderId} <ArrowRight size={12} />
              </Link>
            ) : (
              <em>可立即调度</em>
            )}
          </article>
        ))}
      </div>
    ) : (
      <ResourceEmpty />
    );
  }

  const windows = resources.weatherWindows.filter((item) => matches(item.id, item.reason));
  return windows.length ? (
    <div className="resource-weather-list">
      {windows.map((item) => (
        <article key={item.id}>
          <span className="resource-weather-date">
            <CalendarClock size={16} />
            <strong>
              {new Date(item.startsAt).toLocaleDateString("zh-CN", {
                month: "short",
                day: "numeric",
              })}
            </strong>
            <small>
              {new Date(item.startsAt).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
              –
              {new Date(item.endsAt).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </small>
          </span>
          <span>
            <StatusBadge
              value={item.suitability}
              label={
                item.suitability === "suitable"
                  ? "适合作业"
                  : item.suitability === "conditional"
                    ? "条件作业"
                    : "不可作业"
              }
              tone={
                item.suitability === "suitable"
                  ? "success"
                  : item.suitability === "conditional"
                    ? "warning"
                    : "critical"
              }
            />
            <small>{item.reason}</small>
          </span>
          <span className="resource-weather-metrics">
            <b>{item.windSpeedMps} m/s</b>
            <small>风速</small>
            <b>{item.waveHeightM} m</b>
            <small>浪高</small>
            <b>{item.visibilityKm} km</b>
            <small>能见度</small>
          </span>
        </article>
      ))}
    </div>
  ) : (
    <ResourceEmpty />
  );
}

function ResourceEmpty() {
  return (
    <EmptyState
      icon={<Search size={20} />}
      title="没有匹配资源"
      description="调整搜索条件或切换资源类别后重试。"
    />
  );
}

export function ResourceCenterPage() {
  const [activeTab, setActiveTab] = useState<ResourceTab>("spare-parts");
  const [query, setQuery] = useState("");
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const resourceQuery = useQuery({
    queryKey: ["resource-center"],
    queryFn: ({ signal }) => apiGet<ResourceResponse>("/api/resources", signal),
    initialData: {
      data: resourceCenterSnapshot,
      meta: {
        count:
          resourceCenterSnapshot.spareParts.length +
          resourceCenterSnapshot.crews.length +
          resourceCenterSnapshot.vessels.length +
          resourceCenterSnapshot.tools.length +
          resourceCenterSnapshot.weatherWindows.length,
        total:
          resourceCenterSnapshot.spareParts.length +
          resourceCenterSnapshot.crews.length +
          resourceCenterSnapshot.vessels.length +
          resourceCenterSnapshot.tools.length +
          resourceCenterSnapshot.weatherWindows.length,
        snapshotAt: resourceCenterSnapshot.snapshotAt,
        deterministic: true,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  const resources = useMemo(() => {
    if (!featuredOnly) return resourceQuery.data.data;
    return {
      spareParts: resourceQuery.data.data.spareParts.filter((item) =>
        item.reservedForWorkOrderIds.includes("WO-20260823-017"),
      ),
      crews: resourceQuery.data.data.crews.filter(
        (item) => item.assignedWorkOrderId === "WO-20260823-017",
      ),
      vessels: resourceQuery.data.data.vessels.filter(
        (item) => item.assignedWorkOrderId === "WO-20260823-017",
      ),
      tools: resourceQuery.data.data.tools.filter(
        (item) => item.assignedWorkOrderId === "WO-20260823-017",
      ),
      weatherWindows: resourceQuery.data.data.weatherWindows,
    };
  }, [featuredOnly, resourceQuery.data.data]);

  const lowStock = resourceQuery.data.data.spareParts.filter(
    (item) => item.status !== "in-stock",
  ).length;
  const reservedResources =
    resourceQuery.data.data.crews.filter((item) => item.availability === "reserved").length +
    resourceQuery.data.data.vessels.filter((item) => item.availability === "reserved").length +
    resourceQuery.data.data.tools.filter((item) => item.availability === "reserved").length;
  const nextWindow = resourceQuery.data.data.weatherWindows.find(
    (item) => item.suitability === "suitable",
  )!;

  return (
    <AppShell activePath="/resources">
      <PageHeader
        eyebrow="执行与维护"
        title="运维资源中心"
        description="统一调度备件、班组、船舶、专业工具与海上作业窗口"
        breadcrumb={["执行与维护", "运维资源"]}
        meta={
          <>
            <StatusBadge
              value={resourceQuery.isError ? "degraded" : "healthy"}
              label={resourceQuery.isError ? "FALLBACK SNAPSHOT" : "RESOURCE LEDGER CURRENT"}
            />
            <span className="page-meta-text">快照 2026-08-13 10:25</span>
          </>
        }
        actions={
          <Link className="button button--primary button--md" href="/work-orders">
            打开工单调度 <ArrowRight size={15} />
          </Link>
        }
      />

      <section className="resource-kpi-grid" aria-label="资源摘要">
        <Card>
          <span>
            <PackageCheck size={18} />
          </span>
          <small>SPARE PART SKUS</small>
          <strong>{resourceQuery.data.data.spareParts.length}</strong>
          <em>{lowStock} 项需补货</em>
        </Card>
        <Card>
          <span>
            <UsersRound size={18} />
          </span>
          <small>MAINTENANCE CREWS</small>
          <strong>{resourceQuery.data.data.crews.length}</strong>
          <em>{reservedResources} 项资源已预留</em>
        </Card>
        <Card>
          <span>
            <Anchor size={18} />
          </span>
          <small>VESSELS AVAILABLE</small>
          <strong>
            {
              resourceQuery.data.data.vessels.filter((item) => item.availability === "available")
                .length
            }{" "}
            / {resourceQuery.data.data.vessels.length}
          </strong>
          <em>CTV / SOV 船队</em>
        </Card>
        <Card>
          <span>
            <CloudSun size={18} />
          </span>
          <small>NEXT SAFE WINDOW</small>
          <strong>08:00</strong>
          <em>
            {new Date(nextWindow.startsAt).toLocaleDateString("zh-CN", {
              month: "short",
              day: "numeric",
            })}{" "}
            · 浪高 {nextWindow.waveHeightM} m
          </em>
        </Card>
      </section>

      <Card className="resource-featured-plan">
        <span className="resource-featured-plan__marker">WT-023</span>
        <div>
          <small>READY-TO-EXECUTE RESOURCE PLAN</small>
          <h2>WO-20260823-017 · 主轴承联合检查</h2>
          <p>海维二组、CTV-03、4 件专业工具和主轴承总成已锁定；首选天气窗满足 1.8 m 靠泊限制。</p>
        </div>
        <div className="resource-readiness">
          <strong>92%</strong>
          <Progress value={92} tone="success" />
          <small>等待船长最终确认</small>
        </div>
        <Button
          variant={featuredOnly ? "primary" : "secondary"}
          onClick={() => setFeaturedOnly((value) => !value)}
        >
          {featuredOnly ? "显示全部资源" : "只看本工单"}
        </Button>
      </Card>

      <section className="data-toolbar resource-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            aria-label="搜索资源"
            placeholder="搜索名称、编号、类别或位置…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <span className="toolbar-result">{resourceQuery.data.meta.total} RESOURCES</span>
        <Button variant="secondary" onClick={() => void resourceQuery.refetch()}>
          刷新台账
        </Button>
      </section>

      <Card className="resource-ledger">
        <CardHeader
          eyebrow="RESOURCE LEDGER"
          title="资源与窗口"
          description="所有预留均保留工单关联，支持跨模块追溯"
        />
        <div className="resource-tabs" role="tablist" aria-label="资源类别">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                className={cn(activeTab === tab.id && "active")}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <ResourceContent tab={activeTab} resources={resources} query={query} />
      </Card>
    </AppShell>
  );
}
