import type { Metadata } from "next";
import { WindFarmPage } from "@/components/pages/wind-farm-page";

export const metadata: Metadata = { title: "华东海上风电场", description: "64 台海上风电机组的状态、健康与拓扑概览。" };

export default function Page() { return <WindFarmPage />; }

