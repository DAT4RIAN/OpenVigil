"use client";

import { featuredMission, getMission } from "@/lib/operations-data";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

import { FeaturedMissionDetailPage } from "./mission-detail-featured";
import { GenericMissionDetailPage } from "./mission-detail-generic";
import { ProductionMissionDetailPage } from "./mission-detail-production";

export function MissionDetailPage({
  missionId = "MISSION-2026-0823",
  runtimeMode = "demo",
}: {
  missionId?: string;
  runtimeMode?: OpenVigilRuntimeMode;
}) {
  if (runtimeMode === "production") {
    return <ProductionMissionDetailPage missionId={missionId} />;
  }
  const mission = getMission(missionId);
  if (!mission) return null;
  return mission.id === featuredMission.id ? (
    <FeaturedMissionDetailPage />
  ) : (
    <GenericMissionDetailPage mission={mission} />
  );
}
