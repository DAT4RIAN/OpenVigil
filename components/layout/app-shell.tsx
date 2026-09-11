"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  Archive,
  Bell,
  Bot,
  Boxes,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  CircleGauge,
  ClipboardCheck,
  Cloud,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  Database,
  FileBarChart,
  GitBranch,
  HeartPulse,
  LayoutDashboard,
  Library,
  Menu,
  Monitor,
  Moon,
  PackageSearch,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  TowerControl,
  Wind,
  Wrench,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Avatar, Button } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { RuntimeHealthBadge } from "@/components/ui/query-state";
import { agents } from "@/lib/agent-data";
import type { CurrentWeather, CurrentWeatherCondition } from "@/lib/current-weather";
import { turbines, windFarm } from "@/lib/farm-data";
import { alarms, decisions, missions, workOrders } from "@/lib/operations-data";
import { cn } from "@/lib/utils";
import { hydrateDemoWorkflow, useDemoWorkflow } from "@/lib/use-demo-workflow";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import type { OpenVigilCapability } from "@/lib/identity-session";
import {
  deriveWorkflowKpis,
  overlayClientAgents,
  overlayClientAlarms,
  overlayClientDecisions,
  overlayClientMissions,
} from "@/lib/client-workflow-overlays";
import { apiGet } from "@/lib/api-client";
import { isNavigationItemActive } from "@/lib/navigation-ownership";
import {
  deriveQueryViewState,
  mergeRuntimeHealth,
  queryRuntimeHealth,
  type RuntimeHealthSnapshot,
} from "@/lib/query-state";

type NavigationItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  disabled?: boolean;
  capability?: OpenVigilCapability;
};

type RuntimeMode = "demo" | "production";

type RuntimeEnvelope = {
  readonly data: {
    readonly productionReady: boolean;
  };
};

type CurrentWeatherEnvelope = {
  readonly data: CurrentWeather;
};

type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

const themePreferenceKey = "openvigil-theme";
const legacyThemePreferenceKey = "windops-theme";
const sidebarPreferenceKey = "openvigil-sidebar-collapsed";
const legacySidebarPreferenceKey = "windops-sidebar-collapsed";

const activeAgentCount = agents.filter((agent) =>
  ["thinking", "working", "reviewing"].includes(agent.status),
).length;
const visibleAlarmCount = alarms.filter(
  (alarm) => alarm.status !== "resolved" && alarm.status !== "suppressed",
).length;
const snapshotTime = new Date(windFarm.lastUpdatedAt).toLocaleTimeString("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: windFarm.timezone,
});

const weatherIcons: Readonly<Partial<Record<CurrentWeatherCondition, LucideIcon>>> = {
  clear: Sun,
  "partly-cloudy": CloudSun,
  cloudy: Cloud,
  overcast: Cloud,
  rain: CloudRain,
  snow: CloudSnow,
  storm: CloudLightning,
  fog: CloudFog,
};

async function fetchCurrentWeather(signal: AbortSignal): Promise<CurrentWeatherEnvelope> {
  const response = await fetch("/api/weather", {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Current weather returned ${response.status}.`);
  return (await response.json()) as CurrentWeatherEnvelope;
}

const navigation: NavigationGroup[] = [
  {
    label: "概览",
    items: [
      {
        label: "运营指挥中心",
        href: "/",
        icon: LayoutDashboard,
        capability: "view.dashboard",
      },
    ],
  },
  {
    label: "资产与监测",
    items: [
      { label: "风场", href: "/wind-farms", icon: Wind, capability: "view.assets" },
      {
        label: "风机",
        href: "/turbines/WT-023",
        icon: TowerControl,
        capability: "view.assets",
      },
      { label: "实时监测", href: "/scada", icon: Activity, capability: "view.telemetry" },
      { label: "设备健康", href: "/health", icon: HeartPulse, capability: "view.assets" },
    ],
  },
  {
    label: "智能运维",
    items: [
      {
        label: "告警中心",
        href: "/alarms",
        icon: AlarmTriangle,
        badge: String(visibleAlarmCount),
        capability: "view.alarms",
      },
      {
        label: "智能诊断",
        href: "/diagnosis",
        icon: BrainCircuit,
        capability: "view.missions",
      },
      {
        label: "预测性维护",
        href: "/predictive-maintenance",
        icon: CircleGauge,
        capability: "view.models",
      },
    ],
  },
  {
    label: "AI 运营",
    items: [
      {
        label: "Agent 控制中心",
        href: "/agents",
        icon: Bot,
        badge: String(activeAgentCount),
        capability: "view.agents",
      },
      {
        label: "Mission 中心",
        href: "/missions",
        icon: GitBranch,
        badge: String(windFarm.activeMissionCount),
        capability: "view.missions",
      },
      {
        label: "决策中心",
        href: "/decisions",
        icon: ShieldCheck,
        badge: "2",
        capability: "view.decisions",
      },
    ],
  },
  {
    label: "运维执行",
    items: [
      {
        label: "工单中心",
        href: "/work-orders",
        icon: ClipboardCheck,
        capability: "view.work_orders",
      },
      {
        label: "维护计划",
        href: "/maintenance",
        icon: Wrench,
        capability: "view.work_orders",
      },
      {
        label: "运维资源",
        href: "/resources",
        icon: PackageSearch,
        capability: "view.resources",
      },
    ],
  },
  {
    label: "知识与数据",
    items: [
      { label: "知识库", href: "/knowledge", icon: Library, capability: "view.knowledge" },
      { label: "数字孪生", href: "/digital-twin", icon: Monitor, capability: "view.assets" },
      {
        label: "故障知识图谱",
        href: "/knowledge-graph",
        icon: Boxes,
        capability: "view.knowledge",
      },
      { label: "数据中心", href: "/data", icon: Database, capability: "view.platform" },
      { label: "运维报告", href: "/reports", icon: FileBarChart, capability: "view.reports" },
    ],
  },
  {
    label: "系统",
    items: [
      { label: "模型管理", href: "/models", icon: Archive, capability: "view.models" },
      { label: "系统设置", href: "/settings", icon: Settings2, capability: "view.platform" },
    ],
  },
];

const primaryCommands = [
  {
    label: "打开 Mission 中心",
    description: "查看全部 Mission，并支持机组范围筛选",
    href: "/missions",
    icon: GitBranch,
  },
  {
    label: "创建工单 · 只读受控入口",
    description: "打开 WT-023 工单工作台并说明写入边界；此命令不会创建工单",
    href: "/work-orders?turbineId=WT-023&intent=create",
    icon: ClipboardCheck,
  },
  {
    label: "启动诊断 · 只读诊断入口",
    description: "仅打开 WT-023 现有 Mission 诊断视图；不会启动新 Agent 或写入诊断",
    href: "/missions?turbineId=WT-023&intent=diagnosis",
    icon: BrainCircuit,
  },
  {
    label: "打开 WT-023 机组详情",
    description: "健康度 68 · 主轴承预警",
    href: "/turbines/WT-023",
    icon: TowerControl,
  },
  {
    label: "查看 MISSION-2026-0823",
    description: "主轴承异常 · 可重放完整闭环",
    href: "/missions/MISSION-2026-0823",
    icon: GitBranch,
  },
  {
    label: "打开设备健康矩阵",
    description: "64 台机组 · 健康 · 异常 · 告警",
    href: "/health",
    icon: HeartPulse,
  },
  {
    label: "打开预测性维护",
    description: "64 台机组 · 状态证据 · 维护优先级",
    href: "/predictive-maintenance",
    icon: CircleGauge,
  },
  {
    label: "打开智能诊断",
    description: "差异诊断 · 证据支持与反证 · Agent 协作",
    href: "/diagnosis?turbineId=WT-023",
    icon: BrainCircuit,
  },
  {
    label: "查询运维资源",
    description: "备件 · 班组 · 船舶 · 工具 · 天气窗",
    href: "/resources",
    icon: PackageSearch,
  },
  {
    label: "打开维护计划",
    description: "工单 · 天气窗口 · 班组与资源冲突",
    href: "/maintenance",
    icon: Wrench,
  },
  {
    label: "打开运维报告",
    description: "六类报告 · 预览 · PDF · DOCX",
    href: "/reports",
    icon: FileBarChart,
  },
  {
    label: "打开知识库",
    description: "文档检索 · WT-023 引用式问答",
    href: "/knowledge",
    icon: Library,
  },
  {
    label: "打开数字孪生",
    description: "风场拓扑 · 机组状态 · 运维闭环映射",
    href: "/digital-twin",
    icon: Monitor,
  },
  { label: "查看实时 SCADA", description: "17 个在线测点", href: "/scada", icon: Activity },
  {
    label: "打开告警中心",
    description: `${visibleAlarmCount} 个待处理告警`,
    href: "/alarms",
    icon: AlarmTriangle,
  },
  {
    label: "打开检修工单",
    description: "查看 AI 决策关联的可审计工单",
    href: "/work-orders?workOrder=WO-20260823-017",
    icon: ClipboardCheck,
  },
  {
    label: "选择风场",
    description: "当前可用：华东海上风电场",
    href: "/wind-farms",
    icon: Wind,
  },
  {
    label: "查看 Agent 控制中心",
    description: `${activeAgentCount} 个 Agent 正在工作`,
    href: "/agents",
    icon: Bot,
  },
];

const domainCommands = [
  ...turbines.map((turbine) => ({
    label: turbine.id,
    description: `${turbine.model} · 健康度 ${turbine.healthScore} · ${turbine.status}`,
    href: `/turbines/${turbine.id}`,
    icon: TowerControl,
  })),
  ...alarms.map((alarm) => ({
    label: alarm.id,
    description: `${alarm.turbineId} · ${alarm.code} · ${alarm.title}`,
    href: `/alarms?alarm=${alarm.id}`,
    icon: AlarmTriangle,
  })),
  ...missions.map((mission) => ({
    label: mission.id,
    description: `${mission.turbineId} · ${mission.title}`,
    href: `/missions/${mission.id}`,
    icon: GitBranch,
  })),
  ...workOrders.map((workOrder) => ({
    label: workOrder.id,
    description: `${workOrder.turbineId} · ${workOrder.issue}`,
    href: `/work-orders?workOrder=${workOrder.id}`,
    icon: ClipboardCheck,
  })),
  ...agents.map((agent) => ({
    label: agent.shortName,
    description: `${agent.name} · ${agent.role}`,
    href: `/agents?agent=${agent.id}`,
    icon: Bot,
  })),
];

const commands = [...primaryCommands, ...domainCommands];

const productionCommands = navigation.flatMap((group) =>
  group.items
    .filter((item) => !item.disabled)
    .map((item) => ({
      label: `打开${item.label}`,
      description: `进入${group.label}的${item.label}权威数据视图`,
      href: item.href === "/turbines/WT-023" ? "/wind-farms" : item.href,
      icon: item.icon,
      capability: item.capability,
    })),
);

function ThemeControl() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("light");

  useEffect(() => {
    const current = window.localStorage.getItem(themePreferenceKey);
    const stored = current ?? window.localStorage.getItem(legacyThemePreferenceKey);
    if (current === null && stored !== null) {
      window.localStorage.setItem(themePreferenceKey, stored);
    }
    const preference =
      stored === "dark" || stored === "light" || stored === "system" ? stored : "light";
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = (value: "light" | "dark" | "system") => {
      document.documentElement.dataset.theme =
        value === "system" ? (media.matches ? "dark" : "light") : value;
      document.documentElement.style.colorScheme =
        value === "system" ? (media.matches ? "dark" : "light") : value;
      window.dispatchEvent(new CustomEvent("openvigil-theme-change"));
    };
    apply(preference);
    const frame = window.requestAnimationFrame(() => setTheme(preference));
    const handleSystemChange = () => {
      if ((window.localStorage.getItem(themePreferenceKey) ?? "light") === "system") {
        apply("system");
      }
    };
    media.addEventListener("change", handleSystemChange);
    return () => {
      window.cancelAnimationFrame(frame);
      media.removeEventListener("change", handleSystemChange);
    };
  }, []);

  function toggleTheme() {
    const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
    setTheme(next);
    window.localStorage.setItem(themePreferenceKey, next);
    document.documentElement.dataset.theme =
      next === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : next;
    document.documentElement.style.colorScheme = document.documentElement.dataset.theme;
    window.dispatchEvent(new CustomEvent("openvigil-theme-change"));
  }

  return (
    <Button
      size="icon"
      variant="ghost"
      onClick={toggleTheme}
      aria-label={`当前${theme === "system" ? "跟随系统" : theme === "light" ? "浅色" : "深色"}，点击切换主题`}
      title={`主题：${theme}`}
    >
      {theme === "light" ? (
        <Sun size={17} />
      ) : theme === "dark" ? (
        <Moon size={17} />
      ) : (
        <Monitor size={17} />
      )}
    </Button>
  );
}

function CommandPalette({
  open,
  onClose,
  runtimeMode,
}: {
  open: boolean;
  onClose: () => void;
  runtimeMode: RuntimeMode;
}) {
  const { can } = useOpenVigilIdentity();
  const dialogRef = useAccessibleDialog<HTMLDivElement>(onClose, open);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const permittedProductionCommands = productionCommands.filter(
      (command) => !command.capability || can(command.capability),
    );
    const catalog = runtimeMode === "production" ? permittedProductionCommands : commands;
    const defaults = runtimeMode === "production" ? permittedProductionCommands : primaryCommands;
    return normalized
      ? catalog.filter((command) =>
          `${command.label} ${command.description}`.toLowerCase().includes(normalized),
        )
      : defaults;
  }, [can, query, runtimeMode]);

  if (!open) return null;

  return (
    <div className="dialog-backdrop">
      <button
        type="button"
        className="dialog-backdrop__dismiss"
        onClick={onClose}
        aria-label="关闭快捷命令"
      />
      <div
        ref={dialogRef}
        className="command-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="OpenVigil 快捷命令"
        tabIndex={-1}
      >
        <div className="command-dialog__search">
          <Search size={18} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((value) => Math.min(results.length - 1, value + 1));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((value) => Math.max(0, value - 1));
              }
              if (event.key === "Enter" && results[activeIndex]) {
                event.preventDefault();
                window.location.assign(results[activeIndex].href);
              }
            }}
            placeholder="搜索机组、告警、Mission 或工单…"
            aria-label="搜索快捷命令"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="command-dialog__body">
          <span className="command-dialog__label">快捷操作</span>
          {results.length ? (
            results.map((command, index) => {
              const Icon = command.icon;
              return (
                <a
                  className={cn("command-item", index === activeIndex && "command-item--active")}
                  href={command.href}
                  key={`${command.label}-${command.href}`}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <span className="command-item__icon">
                    <Icon size={17} />
                  </span>
                  <span>
                    <strong>{command.label}</strong>
                    <small>{command.description}</small>
                  </span>
                  <ChevronRight size={15} />
                </a>
              );
            })
          ) : (
            <div className="command-empty">没有找到相关对象</div>
          )}
        </div>
        <div className="command-dialog__footer">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> 导航
          </span>
          <span>
            <kbd>↵</kbd> 打开
          </span>
        </div>
      </div>
    </div>
  );
}

export function AppShell({
  children,
  activePath = "/",
  runtimeMode,
  pageHealth,
}: {
  children: ReactNode;
  activePath?: string;
  runtimeMode: RuntimeMode;
  pageHealth?: RuntimeHealthSnapshot;
}) {
  const isProduction = runtimeMode === "production";
  const { session, can } = useOpenVigilIdentity();
  const workflow = useDemoWorkflow();
  const displayAlarms = useMemo(
    () => (isProduction ? [] : overlayClientAlarms(alarms, workflow)),
    [isProduction, workflow],
  );
  const displayDecisions = useMemo(
    () => (isProduction ? [] : overlayClientDecisions(decisions, workflow)),
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
  const workflowKpis = useMemo(
    () => deriveWorkflowKpis(turbines, displayAlarms, displayMissions, displayAgents),
    [displayAgents, displayAlarms, displayMissions],
  );
  const pendingDecisionCount = useMemo(
    () =>
      displayDecisions.filter((decision) =>
        ["under-review", "revision-requested"].includes(decision.status),
      ).length,
    [displayDecisions],
  );
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [overlayNavigation, setOverlayNavigation] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [currentTime, setCurrentTime] = useState("--:--:--");
  const runtimeQuery = useQuery({
    queryKey: ["production-runtime"],
    queryFn: ({ signal }) => apiGet<RuntimeEnvelope>("/api/runtime", signal),
    enabled: isProduction,
    retry: false,
    refetchInterval: 30_000,
    staleTime: 45_000,
  });
  const weatherQuery = useQuery({
    queryKey: ["current-weather"],
    queryFn: ({ signal }) => fetchCurrentWeather(signal),
    retry: 1,
    refetchInterval: 600_000,
    staleTime: 300_000,
  });
  const currentWeather = weatherQuery.data?.data;
  const WeatherIcon = currentWeather
    ? (weatherIcons[currentWeather.condition] ?? CloudSun)
    : CloudSun;
  const runtimeState = deriveQueryViewState({
    data: runtimeQuery.data?.data,
    dataUpdatedAt: runtimeQuery.dataUpdatedAt,
    error: runtimeQuery.error,
    isError: runtimeQuery.isError,
    isFetching: runtimeQuery.isFetching,
    isPending: runtimeQuery.isPending,
    isStale: runtimeQuery.isStale,
    isEmpty: () => false,
    staleAfterMs: 60_000,
  });
  const systemHealth = mergeRuntimeHealth(
    isProduction ? queryRuntimeHealth(runtimeState, "生产运行时") : null,
    isProduction ? pageHealth : null,
  );
  const visibleNavigation = useMemo(
    () =>
      navigation
        .map((group) => ({
          ...group,
          items: group.items.filter(
            (item) => !isProduction || !item.capability || can(item.capability),
          ),
        }))
        .filter((group) => group.items.length > 0),
    [can, isProduction],
  );
  const sidebarDialogRef = useAccessibleDialog<HTMLElement>(
    () => setMobileOpen(false),
    mobileOpen && overlayNavigation,
  );

  useEffect(() => {
    const overlayQuery = window.matchMedia("(max-width: 1023px)");
    const laptopQuery = window.matchMedia("(min-width: 1024px) and (max-width: 1439px)");
    const currentPreference = window.localStorage.getItem(sidebarPreferenceKey);
    const storedPreference =
      currentPreference ?? window.localStorage.getItem(legacySidebarPreferenceKey);
    if (currentPreference === null && storedPreference !== null) {
      window.localStorage.setItem(sidebarPreferenceKey, storedPreference);
    }

    const updateOverlayNavigation = () => {
      setOverlayNavigation(overlayQuery.matches);
      if (!overlayQuery.matches) setMobileOpen(false);
    };
    const frame = window.requestAnimationFrame(() => {
      setCollapsed(
        storedPreference === "true"
          ? true
          : storedPreference === "false"
            ? false
            : laptopQuery.matches,
      );
      updateOverlayNavigation();
    });
    overlayQuery.addEventListener("change", updateOverlayNavigation);
    return () => {
      window.cancelAnimationFrame(frame);
      overlayQuery.removeEventListener("change", updateOverlayNavigation);
    };
  }, []);

  useEffect(() => {
    if (!mobileOpen || !overlayNavigation) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileOpen, overlayNavigation]);

  useEffect(() => {
    if (!isProduction) hydrateDemoWorkflow();

    const updateClock = () =>
      setCurrentTime(
        new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
          timeZone: windFarm.timezone,
        }),
      );
    updateClock();
    const clockTimer = window.setInterval(updateClock, 1_000);

    function handleKeyboard(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setNotificationsOpen(false);
        setMobileOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyboard);
    return () => {
      window.clearInterval(clockTimer);
      window.removeEventListener("keydown", handleKeyboard);
    };
  }, [isProduction]);

  return (
    <div className={cn("app-shell", collapsed && !overlayNavigation && "app-shell--collapsed")}>
      {mobileOpen ? (
        <button
          className="mobile-backdrop"
          aria-label="关闭导航"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <aside
        ref={sidebarDialogRef}
        id="openvigil-primary-sidebar"
        className={cn("sidebar", mobileOpen && "sidebar--mobile-open")}
        role={mobileOpen && overlayNavigation ? "dialog" : undefined}
        aria-modal={mobileOpen && overlayNavigation ? "true" : undefined}
        aria-label={mobileOpen && overlayNavigation ? "主导航抽屉" : undefined}
        aria-hidden={overlayNavigation && !mobileOpen ? "true" : undefined}
        inert={overlayNavigation && !mobileOpen ? true : undefined}
        tabIndex={mobileOpen && overlayNavigation ? -1 : undefined}
      >
        <div className="sidebar__brand">
          <Link href="/" className="brand-lockup" aria-label="OpenVigil 首页">
            <span className="brand-mark">
              <Wind size={20} strokeWidth={2.25} />
            </span>
            <span className="brand-copy">
              <strong>OpenVigil</strong>
              <small>工业智能</small>
            </span>
          </Link>
          <Button
            size="icon"
            variant="ghost"
            className="sidebar__mobile-close"
            onClick={() => setMobileOpen(false)}
            aria-label="关闭导航"
          >
            <X size={17} />
          </Button>
        </div>

        <Link className="farm-switcher" href="/wind-farms" aria-label="选择风场">
          <span className="farm-switcher__icon">
            <TowerControl size={17} />
          </span>
          <span className="farm-switcher__copy">
            <small>{isProduction ? "生产资产范围" : "当前风场"}</small>
            <strong>{isProduction ? "风场目录" : "华东海上风电场"}</strong>
          </span>
          <ChevronDown size={14} />
        </Link>

        <nav className="sidebar__nav" aria-label="主导航">
          {visibleNavigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group__label">{group.label}</span>
              <div className="nav-group__items">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const href =
                    isProduction && item.href === "/turbines/WT-023" ? "/wind-farms" : item.href;
                  const active = isNavigationItemActive(activePath, href, runtimeMode);
                  if (item.disabled) {
                    return (
                      <span
                        className="nav-item nav-item--disabled"
                        aria-disabled="true"
                        title={`${item.label} · 下一阶段`}
                        key={item.label}
                      >
                        <Icon size={17} />
                        <span>{item.label}</span>
                        <small>即将开放</small>
                      </span>
                    );
                  }
                  return (
                    <a
                      className={cn("nav-item", active && "nav-item--active")}
                      href={href}
                      key={item.label}
                      title={collapsed ? item.label : undefined}
                      aria-current={active ? "page" : undefined}
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
                      {item.badge && !isProduction ? (
                        <small>
                          {item.href === "/alarms"
                            ? workflowKpis.activeAlarmCount
                            : item.href === "/missions"
                              ? workflowKpis.activeMissionCount
                              : item.href === "/decisions"
                                ? pendingDecisionCount
                                : item.href === "/agents"
                                  ? workflowKpis.activeAgentCount
                                  : item.badge}
                        </small>
                      ) : null}
                    </a>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="system-health" data-health={isProduction ? systemHealth.status : "ready"}>
            <span className="system-health__icon">
              <Zap size={16} />
            </span>
            <span>
              <strong>{isProduction ? `Production · ${systemHealth.label}` : "AI 系统正常"}</strong>
              <small>
                {isProduction
                  ? systemHealth.detail
                  : `${workflowKpis.onlineAgentCount} / ${displayAgents.length} Agent 在线`}
              </small>
            </span>
            <span
              className={cn(
                "system-health__pulse",
                isProduction && `system-health__pulse--${systemHealth.status}`,
              )}
            />
          </div>
          <button
            className="sidebar-collapse"
            onClick={() => {
              const next = !collapsed;
              setCollapsed(next);
              window.localStorage.setItem(sidebarPreferenceKey, String(next));
            }}
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            <span>{collapsed ? "展开" : "收起侧栏"}</span>
          </button>
        </div>
      </aside>

      <div className="app-column">
        <header className="topbar">
          <div className="topbar__left">
            <Button
              size="icon"
              variant="ghost"
              className="mobile-menu-button"
              onClick={() => setMobileOpen(true)}
              aria-label="打开导航"
              aria-controls="openvigil-primary-sidebar"
              aria-expanded={mobileOpen}
            >
              <Menu size={19} />
            </Button>
            <div className="live-context" aria-live="polite">
              <StatusBadge
                value={runtimeMode}
                label={isProduction ? "Production" : "Demo"}
                tone="neutral"
                compact
              />
              <span>
                {isProduction ? "PostgreSQL / TimescaleDB 权威数据" : `SCADA 快照 ${snapshotTime}`}
              </span>
              <time dateTime={currentTime === "--:--:--" ? undefined : currentTime}>
                {currentTime}
              </time>
              {isProduction ? (
                <RuntimeHealthBadge health={systemHealth} compact />
              ) : (
                <span
                  title={
                    workflow.lastSyncError ?? `WT-023 服务端工作流修订 ${workflow.serverRevision}`
                  }
                >
                  <StatusBadge
                    value={workflow.syncStatus}
                    label={
                      workflow.syncStatus === "loading"
                        ? "同步中"
                        : workflow.syncStatus === "saving"
                          ? "保存中"
                          : workflow.syncStatus === "error"
                            ? "离线"
                            : !workflow.writable
                              ? "只读"
                              : workflow.persistence === "d1"
                                ? `D1 · R${workflow.serverRevision}`
                                : "内存"
                    }
                    tone={
                      workflow.syncStatus === "error"
                        ? "critical"
                        : workflow.syncStatus === "loading" || workflow.syncStatus === "saving"
                          ? "info"
                          : !workflow.writable
                            ? "warning"
                            : workflow.persistence === "d1"
                              ? "success"
                              : "warning"
                    }
                    compact
                  />
                </span>
              )}
            </div>
          </div>
          <div className="topbar__right">
            <div
              className="weather-chip"
              aria-live="polite"
              title={
                currentWeather
                  ? `和风天气 · 获取于 ${new Date(currentWeather.fetchedAt).toLocaleString("zh-CN")}${
                      currentWeather.stale ? " · 当前显示陈旧缓存" : ""
                    }`
                  : weatherQuery.isPending
                    ? "正在获取实时天气"
                    : "实时天气暂不可用，请检查服务端配置或网络"
              }
            >
              <WeatherIcon size={17} aria-hidden="true" />
              <span>
                <strong>
                  {currentWeather
                    ? `${currentWeather.locationName} · ${currentWeather.conditionText} ${currentWeather.temperatureC.toFixed(0)}°C`
                    : weatherQuery.isPending
                      ? "实时天气同步中"
                      : "实时天气暂不可用"}
                </strong>
                <small>
                  {currentWeather
                    ? `${currentWeather.windDirection} ${currentWeather.windSpeedMps.toFixed(1)} m/s${currentWeather.stale ? " · 陈旧" : ""}`
                    : weatherQuery.isPending
                      ? "正在连接和风天气"
                      : "保留业务页面，稍后自动重试"}
                  {currentWeather ? (
                    <>
                      {" · "}
                      <a href="https://www.qweather.com/" target="_blank" rel="noreferrer">
                        和风天气
                      </a>
                    </>
                  ) : null}
                </small>
              </span>
            </div>
            <button
              className="global-search"
              onClick={() => setPaletteOpen(true)}
              aria-label="打开全局搜索"
            >
              <Search size={16} />
              <span>搜索机组、告警、Mission…</span>
              <kbd>Ctrl K</kbd>
            </button>
            <div className="topbar-divider" />
            <ThemeControl />
            <div className="popover-anchor">
              <Button
                size="icon"
                variant="ghost"
                onClick={() => setNotificationsOpen((value) => !value)}
                aria-label="通知"
              >
                <Bell size={17} />
                {!isProduction ? <span className="notification-dot" /> : null}
              </Button>
              {notificationsOpen ? (
                <div className="notification-popover">
                  <div className="notification-popover__header">
                    <strong>最新动态</strong>
                    <span>{isProduction ? "权威事件入口" : "3 条未读"}</span>
                  </div>
                  {isProduction ? (
                    <>
                      <Link href="/alarms">
                        <span className="notification-icon notification-icon--critical">
                          <AlarmTriangle size={15} />
                        </span>
                        <span>
                          <strong>打开告警中心</strong>
                          <small>查看当前权威告警与处置状态</small>
                        </span>
                      </Link>
                      <Link href="/missions">
                        <span className="notification-icon notification-icon--info">
                          <GitBranch size={15} />
                        </span>
                        <span>
                          <strong>打开 Mission 中心</strong>
                          <small>查看持久化事件与 Agent 执行进度</small>
                        </span>
                      </Link>
                    </>
                  ) : (
                    <>
                      <Link href="/missions/MISSION-2026-0823">
                        <span className="notification-icon notification-icon--warning">
                          <ShieldCheck size={15} />
                        </span>
                        <span>
                          <strong>
                            {workflow.missionStatus === "completed"
                              ? "WT-023 闭环已完成"
                              : workflow.decisionStatus === "under-review"
                                ? "WT-023 等待人工审批"
                                : workflow.workOrderStatus === "in-progress"
                                  ? "WT-023 现场任务执行中"
                                  : "作业资源等待最终确认"}
                          </strong>
                          <small>
                            {workflow.missionStatus.replaceAll("-", " ")} ·{" "}
                            {workflow.missionProgress}%
                          </small>
                        </span>
                      </Link>
                      <a href="/alarms">
                        <span className="notification-icon notification-icon--critical">
                          <AlarmTriangle size={15} />
                        </span>
                        <span>
                          <strong>主轴承振动告警升级</strong>
                          <small>ALARM-0031 · 9 分钟前</small>
                        </span>
                      </a>
                      <a href="/agents">
                        <span className="notification-icon notification-icon--info">
                          <Bot size={15} />
                        </span>
                        <span>
                          <strong>诊断 Agent 已完成分析</strong>
                          <small>置信度 87% · 14 分钟前</small>
                        </span>
                      </a>
                    </>
                  )}
                </div>
              ) : null}
            </div>
            {isProduction && session ? (
              <a
                className="user-menu"
                href={session.signOutPath}
                title="安全退出 OpenVigil"
                data-authenticated-subject={session.subject}
              >
                <Avatar label={session.displayName} tone="slate" size="sm" />
                <span>
                  <strong>{session.displayName}</strong>
                  <small>{session.roles.join(" · ")} · Sites 委托身份</small>
                </span>
                <ChevronDown size={14} />
              </a>
            ) : (
              <div className="user-menu">
                <Avatar label="林 工" tone="slate" size="sm" />
                <span>
                  <strong>林工</strong>
                  <small>值班工程师</small>
                </span>
                <ChevronDown size={14} />
              </div>
            )}
          </div>
        </header>
        <main className="app-main">{children}</main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        runtimeMode={runtimeMode}
      />
    </div>
  );
}
