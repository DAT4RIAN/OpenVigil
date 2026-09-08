"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { agents, alarms, missions, turbines, workOrders } from "@/lib";
import { cn } from "@/lib/utils";
import { hydrateDemoWorkflow, useDemoWorkflow } from "@/lib/use-demo-workflow";

type NavigationItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  disabled?: boolean;
};

type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

const navigation: NavigationGroup[] = [
  {
    label: "概览",
    items: [{ label: "Operations Center", href: "/", icon: LayoutDashboard }],
  },
  {
    label: "资产与监测",
    items: [
      { label: "风场", href: "/wind-farms", icon: Wind },
      { label: "风机", href: "/turbines/WT-023", icon: TowerControl },
      { label: "实时监测", href: "/scada", icon: Activity },
      { label: "设备健康", href: "/health", icon: HeartPulse },
    ],
  },
  {
    label: "智能运维",
    items: [
      { label: "告警中心", href: "/alarms", icon: AlarmTriangle, badge: "17" },
      { label: "智能诊断", href: "#diagnosis", icon: BrainCircuit, disabled: true },
      { label: "预测性维护", href: "/predictive-maintenance", icon: CircleGauge },
    ],
  },
  {
    label: "AI Operations",
    items: [
      { label: "Agent Control", href: "/agents", icon: Bot, badge: "6" },
      { label: "Mission Center", href: "/missions", icon: GitBranch, badge: "10" },
      { label: "Decision Center", href: "/decisions", icon: ShieldCheck, badge: "2" },
    ],
  },
  {
    label: "运维执行",
    items: [
      { label: "工单中心", href: "/work-orders", icon: ClipboardCheck },
      { label: "维护计划", href: "#maintenance", icon: Wrench, disabled: true },
      { label: "运维资源", href: "/resources", icon: PackageSearch },
    ],
  },
  {
    label: "知识与数据",
    items: [
      { label: "知识库", href: "/knowledge", icon: Library },
      { label: "故障知识图谱", href: "#graph", icon: Boxes, disabled: true },
      { label: "数据中心", href: "#data", icon: Database, disabled: true },
      { label: "运维报告", href: "#reports", icon: FileBarChart, disabled: true },
    ],
  },
  {
    label: "系统",
    items: [
      { label: "模型管理", href: "#models", icon: Archive, disabled: true },
      { label: "系统设置", href: "#settings", icon: Settings2, disabled: true },
    ],
  },
];

const primaryCommands = [
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
    description: "64 台机组 · 风险与 RUL",
    href: "/health",
    icon: HeartPulse,
  },
  {
    label: "打开预测性维护",
    description: "64 台机组 · 失效概率 · RUL · 风险矩阵",
    href: "/predictive-maintenance",
    icon: CircleGauge,
  },
  {
    label: "查询运维资源",
    description: "备件 · 班组 · 船舶 · 工具 · 天气窗",
    href: "/resources",
    icon: PackageSearch,
  },
  {
    label: "打开知识库",
    description: "文档检索 · WT-023 引用式问答",
    href: "/knowledge",
    icon: Library,
  },
  { label: "查看实时 SCADA", description: "17 个在线测点", href: "/scada", icon: Activity },
  { label: "打开告警中心", description: "17 个活跃告警", href: "/alarms", icon: AlarmTriangle },
  {
    label: "创建检修工单",
    description: "基于当前 AI 决策",
    href: "/work-orders",
    icon: ClipboardCheck,
  },
  { label: "查看 Agent Control", description: "6 个 Agent 正在工作", href: "/agents", icon: Bot },
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
    href: "/alarms",
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
    href: "/work-orders",
    icon: ClipboardCheck,
  })),
  ...agents.map((agent) => ({
    label: agent.shortName,
    description: `${agent.name} · ${agent.role}`,
    href: "/agents",
    icon: Bot,
  })),
];

const commands = [...primaryCommands, ...domainCommands];

function ThemeControl() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  useEffect(() => {
    const stored = window.localStorage.getItem("windops-theme");
    const preference =
      stored === "dark" || stored === "light" || stored === "system" ? stored : "system";
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = (value: "light" | "dark" | "system") => {
      document.documentElement.dataset.theme =
        value === "system" ? (media.matches ? "dark" : "light") : value;
      window.dispatchEvent(new CustomEvent("windops-theme-change"));
    };
    apply(preference);
    const frame = window.requestAnimationFrame(() => setTheme(preference));
    const handleSystemChange = () => {
      if ((window.localStorage.getItem("windops-theme") ?? "system") === "system") apply("system");
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
    window.localStorage.setItem("windops-theme", next);
    document.documentElement.dataset.theme =
      next === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : next;
    window.dispatchEvent(new CustomEvent("windops-theme-change"));
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

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return normalized
      ? commands.filter((command) =>
          `${command.label} ${command.description}`.toLowerCase().includes(normalized),
        )
      : primaryCommands;
  }, [query]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="dialog-backdrop"
      role="button"
      tabIndex={-1}
      aria-label="关闭快捷命令"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setActiveIndex((value) => Math.min(results.length - 1, value + 1));
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          setActiveIndex((value) => Math.max(0, value - 1));
        }
        if (event.key === "Enter" && results[activeIndex]) {
          window.location.assign(results[activeIndex].href);
        }
      }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="command-dialog" role="dialog" aria-modal="true" aria-label="WindOps 快捷命令">
        <div className="command-dialog__search">
          <Search size={18} aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
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
}: {
  children: ReactNode;
  activePath?: string;
}) {
  const workflow = useDemoWorkflow();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  useEffect(() => {
    hydrateDemoWorkflow();

    function handleKeyboard(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setNotificationsOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyboard);
    return () => window.removeEventListener("keydown", handleKeyboard);
  }, []);

  return (
    <div className={cn("app-shell", collapsed && "app-shell--collapsed")}>
      {mobileOpen ? (
        <button
          className="mobile-backdrop"
          aria-label="关闭导航"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <aside className={cn("sidebar", mobileOpen && "sidebar--mobile-open")}>
        <div className="sidebar__brand">
          <Link href="/" className="brand-lockup" aria-label="WindOps 首页">
            <span className="brand-mark">
              <Wind size={20} strokeWidth={2.25} />
            </span>
            <span className="brand-copy">
              <strong>WindOps</strong>
              <small>Industrial AI</small>
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

        <div className="farm-switcher">
          <span className="farm-switcher__icon">
            <TowerControl size={17} />
          </span>
          <span className="farm-switcher__copy">
            <small>当前风场</small>
            <strong>华东海上风电场</strong>
          </span>
          <ChevronDown size={14} />
        </div>

        <nav className="sidebar__nav" aria-label="主导航">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group__label">{group.label}</span>
              <div className="nav-group__items">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = item.href === "/" ? activePath === "/" : activePath === item.href;
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
                        <small>SOON</small>
                      </span>
                    );
                  }
                  return (
                    <a
                      className={cn("nav-item", active && "nav-item--active")}
                      href={item.href}
                      key={item.label}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
                      {item.badge ? <small>{item.badge}</small> : null}
                    </a>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="system-health">
            <span className="system-health__icon">
              <Zap size={16} />
            </span>
            <span>
              <strong>AI 系统正常</strong>
              <small>15 / 15 Agents online</small>
            </span>
            <span className="system-health__pulse" />
          </div>
          <button
            className="sidebar-collapse"
            onClick={() => setCollapsed((value) => !value)}
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
            >
              <Menu size={19} />
            </Button>
            <div className="live-context" aria-live="polite">
              <StatusBadge value="running" label="LIVE" tone="success" pulse compact />
              <span>数据更新于 12 秒前</span>
              <span
                title={
                  workflow.lastSyncError ??
                  `WT-023 server workflow revision ${workflow.serverRevision}`
                }
              >
                <StatusBadge
                  value={workflow.syncStatus}
                  label={
                    workflow.syncStatus === "loading"
                      ? "SYNC"
                      : workflow.syncStatus === "saving"
                        ? "SAVING"
                        : workflow.syncStatus === "error"
                          ? "OFFLINE"
                          : !workflow.writable
                            ? "READ ONLY"
                            : workflow.persistence === "d1"
                              ? `D1 · R${workflow.serverRevision}`
                              : "MEMORY"
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
            </div>
          </div>
          <div className="topbar__right">
            <div className="weather-chip">
              <CloudSun size={17} />
              <span>
                <strong>9.7 m/s</strong>
                <small>东南风 · 18°C</small>
              </span>
            </div>
            <button className="global-search" onClick={() => setPaletteOpen(true)}>
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
                <span className="notification-dot" />
              </Button>
              {notificationsOpen ? (
                <div className="notification-popover">
                  <div className="notification-popover__header">
                    <strong>最新动态</strong>
                    <span>3 条未读</span>
                  </div>
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
                        {workflow.missionStatus.replaceAll("-", " ")} · {workflow.missionProgress}%
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
                </div>
              ) : null}
            </div>
            <div className="user-menu">
              <Avatar label="林 工" tone="slate" size="sm" />
              <span>
                <strong>林工</strong>
                <small>值班工程师</small>
              </span>
              <ChevronDown size={14} />
            </div>
          </div>
        </header>
        <main className="app-main">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
