import { Bot, Wind } from "lucide-react";

export default function Loading() {
  return (
    <main className="route-loading" aria-live="polite" aria-busy="true">
      <span className="route-loading__brand">
        <span>
          <Wind size={20} /> WindOps
        </span>
        <small>
          <Bot size={13} /> Industrial AI Control Center
        </small>
      </span>
      <span className="sr-only">正在同步 SCADA、Mission、Agent 与工单关联数据。</span>
      <div className="route-loading__topbar">
        <span className="skeleton skeleton--title" />
        <span className="skeleton skeleton--control" />
        <span className="skeleton skeleton--avatar" />
      </div>
      <div className="route-loading__page">
        <div className="route-loading__heading">
          <span className="skeleton skeleton--eyebrow" />
          <span className="skeleton skeleton--heading" />
          <span className="skeleton skeleton--copy" />
        </div>
        <div className="route-loading__metrics">
          {Array.from({ length: 8 }, (_, index) => (
            <span className="route-loading__metric" key={index}>
              <i className="skeleton skeleton--eyebrow" />
              <i className="skeleton skeleton--value" />
              <i className="skeleton skeleton--copy" />
            </span>
          ))}
        </div>
        <div className="route-loading__panels">
          <span>
            <i className="skeleton skeleton--heading" />
            <i className="skeleton skeleton--chart" />
          </span>
          <span>
            <i className="skeleton skeleton--heading" />
            <i className="skeleton skeleton--rows" />
          </span>
        </div>
      </div>
    </main>
  );
}
