import { turbines, windFarm } from "../farm-data";
import { AgentToolRuntimeError } from "./contracts";
import type { AgentToolArguments, AgentToolExecutionContext } from "./contracts";
import { workOrders } from "../operations-data";
import { historicalWorkOrders } from "../archive-data";

export const requiredTurbine = (turbineId: string) => {
  const turbine = turbines.find((item) => item.id === turbineId);
  if (!turbine) {
    throw new AgentToolRuntimeError(
      "TURBINE_NOT_FOUND",
      `Wind turbine ${turbineId} was not found.`,
      404,
      { turbineId },
    );
  }
  return turbine;
};

export const round = (value: number, precision = 2): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

export const aggregateNumbers = (values: readonly number[]) => ({
  minimum: values.length === 0 ? null : Math.min(...values),
  maximum: values.length === 0 ? null : Math.max(...values),
  average:
    values.length === 0
      ? null
      : round(values.reduce((sum, value) => sum + value, 0) / values.length),
});

export const workflowSnapshotAt = (context: AgentToolExecutionContext): string =>
  context.workflowSnapshot?.updatedAt ?? windFarm.lastUpdatedAt;

const allWorkOrders = Object.freeze([...workOrders, ...historicalWorkOrders]);

export const requiredWorkOrder = (workOrderId: string) => {
  const workOrder = allWorkOrders.find((item) => item.id === workOrderId);
  if (!workOrder) {
    throw new AgentToolRuntimeError(
      "WORK_ORDER_NOT_FOUND",
      `Work order ${workOrderId} was not found.`,
      404,
      { workOrderId },
    );
  }
  return workOrder;
};

interface ResourceScope {
  readonly turbineId: string | null;
  readonly workOrderId: string | null;
  readonly linkedWorkOrderIds: readonly string[];
}

export const resolveResourceScope = (args: AgentToolArguments): ResourceScope => {
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const workOrderId = (args.workOrderId as string | undefined) ?? null;
  const turbine = turbineId ? requiredTurbine(turbineId) : null;
  const workOrder = workOrderId ? requiredWorkOrder(workOrderId) : null;

  if (turbine && workOrder && workOrder.turbineId !== turbine.id) {
    throw new AgentToolRuntimeError(
      "WORK_ORDER_TURBINE_MISMATCH",
      `Work order ${workOrder.id} does not belong to turbine ${turbine.id}.`,
      422,
      { workOrderId: workOrder.id, turbineId: turbine.id, actualTurbineId: workOrder.turbineId },
    );
  }

  const linkedWorkOrderIds = workOrder
    ? [workOrder.id]
    : turbine
      ? allWorkOrders.filter((item) => item.turbineId === turbine.id).map((item) => item.id)
      : [];

  return Object.freeze({
    turbineId: turbine?.id ?? null,
    workOrderId: workOrder?.id ?? null,
    linkedWorkOrderIds: Object.freeze(linkedWorkOrderIds),
  });
};
