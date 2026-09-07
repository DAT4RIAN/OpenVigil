import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { MissionDetailPage } from "@/components/pages/mission-detail-page";
import { getMission } from "@/lib";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const mission = getMission(id);
  return mission
    ? {
        title: mission.id,
        description: `${mission.turbineId} ${mission.title} 的多 Agent 协作与执行记录。`,
      }
    : { title: "Mission 未找到" };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const mission = getMission(id);
  if (!mission) notFound();
  return <MissionDetailPage missionId={mission.id} />;
}
