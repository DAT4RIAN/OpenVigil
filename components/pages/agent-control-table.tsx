"use client";

import { useMemo } from "react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agentDisplayName, agentLayerMeta, agentStatusLabel } from "@/lib/agent-control-meta";
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
            <strong>{agentDisplayName(row.original.agent.id, row.original.agent.shortName)}</strong>
            <small className="mono">{row.original.agent.id}</small>
          </span>
        ),
      },
      {
        id: "layer",
        header: "层级",
        accessorFn: (row) => row.agent.layer,
        cell: ({ row }) => agentLayerMeta[row.original.agent.layer].label,
      },
      {
        id: "status",
        header: "状态",
        accessorFn: (row) => row.agent.status,
        cell: ({ row }) => <StatusBadge value={row.original.agent.status} compact />,
      },
      {
        id: "task",
        header: "当前任务",
        accessorFn: (row) => row.currentTask,
      },
      {
        id: "queue",
        header: "队列",
        accessorFn: (row) => row.agent.queueDepth,
      },
      {
        id: "success",
        header: "成功率",
        accessorFn: (row) => row.agent.metrics.successRate,
        cell: ({ row }) => `${row.original.agent.metrics.successRate}%`,
      },
      {
        id: "latency",
        header: "延迟",
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
          label: "查看首个已选 Agent",
          onActivate: (selected) => {
            if (selected[0]) onInspect(selected[0].agent);
          },
        },
      ]}
      csvExport={{
        filename: "windops-agents.csv",
        columns: [
          { label: "Agent ID", value: (row) => row.agent.id },
          { label: "名称", value: (row) => agentDisplayName(row.agent.id, row.agent.name) },
          { label: "角色", value: (row) => row.agent.role },
          { label: "层级", value: (row) => agentLayerMeta[row.agent.layer].label },
          { label: "状态", value: (row) => agentStatusLabel[row.agent.status] },
          { label: "当前任务", value: (row) => row.currentTask },
          { label: "队列", value: (row) => row.agent.queueDepth },
          { label: "成功率 %", value: (row) => row.agent.metrics.successRate },
          {
            label: "平均延迟（秒）",
            value: (row) => row.agent.metrics.averageLatencySeconds,
          },
        ],
      }}
    />
  );
}
