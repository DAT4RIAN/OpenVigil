"use client";

import { useMemo } from "react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import type { Agent } from "@/lib/types";

export interface AgentControlTableRow {
  readonly agent: Agent;
  readonly currentTask: string;
}

export function AgentControlTable({
  rows,
  selectedAgentId,
  onInspect,
}: {
  readonly rows: readonly AgentControlTableRow[];
  readonly selectedAgentId: string | null;
  readonly onInspect: (agent: Agent) => void;
}) {
  const columns = useMemo<readonly LegacyColumnDef<AgentControlTableRow, unknown>[]>(
    () => [
      {
        id: "agent",
        header: "Agent",
        accessorFn: (row) => row.agent.name,
        cell: ({ row }) => (
          <span>
            <strong>{row.original.agent.shortName}</strong>
            <small className="mono">{row.original.agent.id}</small>
          </span>
        ),
      },
      {
        id: "layer",
        header: "Layer",
        accessorFn: (row) => row.agent.layer,
      },
      {
        id: "status",
        header: "Status",
        accessorFn: (row) => row.agent.status,
        cell: ({ row }) => <StatusBadge value={row.original.agent.status} compact />,
      },
      {
        id: "task",
        header: "Current task",
        accessorFn: (row) => row.currentTask,
      },
      {
        id: "queue",
        header: "Queue",
        accessorFn: (row) => row.agent.queueDepth,
      },
      {
        id: "success",
        header: "Success",
        accessorFn: (row) => row.agent.metrics.successRate,
        cell: ({ row }) => `${row.original.agent.metrics.successRate}%`,
      },
      {
        id: "latency",
        header: "Latency",
        accessorFn: (row) => row.agent.metrics.averageLatencySeconds,
        cell: ({ row }) => `${row.original.agent.metrics.averageLatencySeconds}s`,
      },
    ],
    [],
  );

  return (
    <DataTable
      data={rows}
      columns={columns}
      getRowId={(row) => row.agent.id}
      onRowActivate={(row) => onInspect(row.agent)}
      selectedRowId={selectedAgentId}
      pageSize={8}
      emptyMessage="没有符合当前条件的 Agent。"
      searchPlaceholder="搜索 Agent、角色、任务或工具…"
      searchTextForRow={(row) =>
        [
          row.agent.id,
          row.agent.name,
          row.agent.shortName,
          row.agent.role,
          row.agent.layer,
          row.agent.status,
          row.currentTask,
          ...row.agent.tools,
        ].join(" ")
      }
      bulkActions={[
        {
          label: "Inspect first selected Agent",
          onActivate: (selected) => {
            if (selected[0]) onInspect(selected[0].agent);
          },
        },
      ]}
      csvExport={{
        filename: "windops-agents.csv",
        columns: [
          { label: "Agent ID", value: (row) => row.agent.id },
          { label: "Name", value: (row) => row.agent.name },
          { label: "Role", value: (row) => row.agent.role },
          { label: "Layer", value: (row) => row.agent.layer },
          { label: "Status", value: (row) => row.agent.status },
          { label: "Current task", value: (row) => row.currentTask },
          { label: "Queue", value: (row) => row.agent.queueDepth },
          { label: "Success %", value: (row) => row.agent.metrics.successRate },
          {
            label: "Average latency seconds",
            value: (row) => row.agent.metrics.averageLatencySeconds,
          },
        ],
      }}
    />
  );
}
