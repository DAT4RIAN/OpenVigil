import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TurbineDetailPage } from "@/components/pages/turbine-detail-page";
import { getTurbine } from "@/lib";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  if (getProductionBackendConfig().mode === "production") {
    return {
      title: `${id} 数字资产`,
      description: `${id} 生产资产、SCADA、健康、告警与维护信息。`,
    };
  }
  const turbine = getTurbine(id);
  return turbine
    ? {
        title: `${turbine.id} 数字资产`,
        description: `${turbine.id} 机组健康、SCADA、告警与维护信息。`,
      }
    : { title: "机组未找到" };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runtimeMode = getProductionBackendConfig().mode;
  if (runtimeMode === "production") {
    return <TurbineDetailPage turbineId={id} runtimeMode={runtimeMode} />;
  }
  const turbine = getTurbine(id);
  if (!turbine) notFound();
  return <TurbineDetailPage turbineId={turbine.id} runtimeMode={runtimeMode} />;
}
