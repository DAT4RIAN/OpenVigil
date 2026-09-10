import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { MissionDetailPage } from "@/components/pages/mission-detail-page";
import { getMission } from "@/lib/operations-data";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const mission = getMission(id);
  const production = getProductionBackendConfig().mode === "production";
  return mission || production
    ? {
        title: mission?.id ?? id,
        description: mission
          ? `${mission.turbineId} ${mission.title} 的多 Agent 协作与执行记录。`
          : `${id} 的权威 Mission、证据、决策与执行记录。`,
      }
    : { title: "Mission 未找到" };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runtimeMode = getProductionBackendConfig().mode;
  const mission = getMission(id);
  if (!mission && runtimeMode !== "production") notFound();
  return <MissionDetailPage missionId={mission?.id ?? id} runtimeMode={runtimeMode} />;
}
