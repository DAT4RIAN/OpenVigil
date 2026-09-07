"use client";

import { TriangleAlert, RefreshCcw, Wind } from "lucide-react";
import { Button } from "@/components/ui/primitives";

export default function ErrorBoundary({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="route-state" role="alert">
      <span className="route-state__brand">
        <Wind size={22} /> WindOps
      </span>
      <div className="route-state__icon route-state__icon--critical">
        <TriangleAlert size={25} />
      </div>
      <h1>运行数据暂时无法加载</h1>
      <p>当前视图没有修改任何设备或工单状态。请重试同步。</p>
      <Button variant="primary" onClick={reset}>
        <RefreshCcw size={15} /> 重新加载
      </Button>
    </main>
  );
}
