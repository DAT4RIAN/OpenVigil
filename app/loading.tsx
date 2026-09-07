import { Activity, Bot, Wind } from "lucide-react";

export default function Loading() {
  return (
    <main className="route-state" aria-live="polite" aria-busy="true">
      <span className="route-state__brand">
        <Wind size={22} /> WindOps
      </span>
      <div className="route-state__icon spin">
        <Activity size={25} />
      </div>
      <h1>正在同步运行态势</h1>
      <p>加载 SCADA、Mission、Agent 与工单关联数据…</p>
      <span className="route-state__status">
        <Bot size={14} /> Industrial AI Control Center
      </span>
    </main>
  );
}
