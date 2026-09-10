import { AppShell } from "@/components/layout/app-shell";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export default function Loading() {
  const runtimeMode = getProductionBackendConfig().mode;
  return (
    <AppShell runtimeMode={runtimeMode}>
      <div className="route-loading" aria-live="polite" aria-busy="true">
        <span className="sr-only">
          正在加载当前工作区。真实 App Shell 已保留，业务区域尚未返回权威数据。
        </span>
        <div className="route-loading__page">
          <div className="route-loading__heading">
            <span className="skeleton skeleton--eyebrow" />
            <span className="skeleton skeleton--heading" />
            <span className="skeleton skeleton--copy" />
          </div>
          <div className="route-loading__metrics">
            {Array.from({ length: 6 }, (_, index) => (
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
      </div>
    </AppShell>
  );
}
