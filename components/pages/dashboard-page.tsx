"use client";

import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

import { DemoDashboardPage } from "./dashboard-demo-page";
import { ProductionDashboardPage } from "./dashboard-production-page";

export function DashboardPage({ runtimeMode }: { readonly runtimeMode: OpenVigilRuntimeMode }) {
  return runtimeMode === "production" ? <ProductionDashboardPage /> : <DemoDashboardPage />;
}
