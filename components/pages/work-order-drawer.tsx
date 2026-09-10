"use client";

import { useState } from "react";
import {
  Bot,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Download,
  HardHat,
  PackageCheck,
  ShieldCheck,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import { Button, KeyValue, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import type { WorkOrder, WorkOrderTask } from "@/lib/types";
import { asText } from "@/lib/utils";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import { apiPost } from "@/lib/api-client";
import {
  FIELD_ARTIFACT_ACCEPT,
  MAX_FIELD_ARTIFACT_BYTES,
  WORKFLOW_WORK_ORDER_ID,
  fieldContentType,
  recordValue,
  sha256Hex,
  statusLabels,
  type ArtifactUploadGrant,
  type SchemaProperty,
} from "./work-order-support";

function FieldTaskCompletionForm({
  workOrderId,
  task,
  onCompleted,
  authorized,
}: {
  workOrderId: string;
  task: WorkOrderTask;
  onCompleted: () => Promise<void>;
  authorized: boolean;
}) {
  const schema = recordValue(task.measurementSchema);
  const properties = recordValue(schema.properties);
  const required = new Set(
    Array.isArray(schema.required)
      ? schema.required.filter((value): value is string => typeof value === "string")
      : [],
  );
  const initialMeasurement = Object.fromEntries(
    Object.entries(properties)
      .map(([name, value]) => [name, recordValue(value).const] as const)
      .filter((entry) => entry[1] !== undefined),
  );
  const [measurement, setMeasurement] = useState<Record<string, unknown>>(initialMeasurement);
  const [result, setResult] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateMeasurement = (name: string, raw: string, property: SchemaProperty) => {
    setMeasurement((current) => {
      const next = { ...current };
      if (raw === "") {
        delete next[name];
        return next;
      }
      next[name] =
        property.type === "number" || property.type === "integer"
          ? Number(raw)
          : property.type === "boolean"
            ? raw === "true"
            : raw;
      return next;
    });
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!authorized) {
      setError("当前角色没有提交现场证据或完成任务的权限。");
      return;
    }
    if (!file) {
      setError("请选择现场证据文件。");
      return;
    }
    if (file.size <= 0 || file.size > MAX_FIELD_ARTIFACT_BYTES) {
      setError("现场证据文件必须在 1 Byte 到 50 MiB 之间。");
      return;
    }
    const contentType = fieldContentType(file);
    if (!contentType) {
      setError("仅支持 JSON、PDF、JPEG、PNG、TXT 或 MP4 证据文件。");
      return;
    }
    const missing = [...required].filter(
      (name) => measurement[name] === undefined || measurement[name] === "",
    );
    if (missing.length) {
      setError(`请填写必填测量字段：${missing.join("、")}。`);
      return;
    }
    if (result.trim().length < 3) {
      setError("请填写至少 3 个字符的现场结论。");
      return;
    }

    setSubmitting(true);
    try {
      const artifactSha256 = await sha256Hex(file);
      const taskPath = `/api/backend/work-orders/${encodeURIComponent(workOrderId)}/tasks/${encodeURIComponent(task.id)}`;
      const grant = await apiPost<ArtifactUploadGrant>(`${taskPath}/artifacts/presign`, {
        file_name: file.name,
        content_type: contentType,
        artifact_sha256: artifactSha256,
      });
      const upload = await fetch(grant.upload_url, {
        method: "PUT",
        headers: grant.required_headers,
        body: file,
      });
      if (!upload.ok) {
        throw new Error(`对象存储上传失败（HTTP ${upload.status}）。`);
      }
      await apiPost(`${taskPath}/complete`, {
        result: result.trim(),
        artifact_uri: grant.artifact_uri,
        artifact_sha256: artifactSha256,
        measurement,
      });
      await onCompleted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "现场证据提交失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="field-evidence-form" onSubmit={(event) => void submit(event)}>
      <div className="field-evidence-form__heading">
        <span>
          <ShieldCheck size={14} /> 当前可执行任务
        </span>
        <small className="mono">{task.schemaVersion ?? "schema-unversioned"}</small>
      </div>
      <strong>
        {task.sequence}. {task.title}
      </strong>
      <div className="field-evidence-form__fields">
        {Object.entries(properties).map(([name, rawProperty]) => {
          const property = recordValue(rawProperty);
          const label = typeof property.title === "string" ? property.title : name;
          const enumValues = Array.isArray(property.enum) ? property.enum : null;
          const constant = property.const;
          return (
            <label key={name}>
              <span>
                {label} {required.has(name) ? "*" : ""}
              </span>
              {constant !== undefined ? (
                <input value={asText(constant)} readOnly aria-readonly="true" />
              ) : enumValues ? (
                <select
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                >
                  <option value="">请选择</option>
                  {enumValues.map((value) => (
                    <option key={String(value)} value={String(value)}>
                      {String(value)}
                    </option>
                  ))}
                </select>
              ) : property.type === "boolean" ? (
                <select
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                >
                  <option value="">请选择</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              ) : (
                <input
                  type={
                    property.type === "number" || property.type === "integer" ? "number" : "text"
                  }
                  step={
                    property.type === "integer" ? 1 : property.type === "number" ? "any" : undefined
                  }
                  min={typeof property.minimum === "number" ? property.minimum : undefined}
                  max={typeof property.maximum === "number" ? property.maximum : undefined}
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                />
              )}
              {typeof property.description === "string" ? (
                <small>{property.description}</small>
              ) : null}
            </label>
          );
        })}
        <label>
          <span>现场结论 *</span>
          <textarea
            rows={3}
            value={result}
            onChange={(event) => setResult(event.target.value)}
            placeholder="记录检查、测量和处置结论"
            required
          />
        </label>
        <label>
          <span>不可变现场证据 *</span>
          <input
            type="file"
            accept={FIELD_ARTIFACT_ACCEPT}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
          <small>上传后由后端重新计算 SHA-256；最大 50 MiB。</small>
        </label>
      </div>
      {error ? (
        <p className="field-evidence-form__error" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" variant="primary" disabled={submitting || !authorized}>
        <ShieldCheck size={14} /> {submitting ? "校验并提交中…" : "上传证据并完成任务"}
      </Button>
    </form>
  );
}

export function WorkOrderDrawer({
  workOrder,
  runtimeMode,
  isWorkflowWorkOrder,
  workflowWritable,
  onClose,
  onToggleTask,
  onStart,
  onComplete,
  onProductionTaskCompleted,
  canComplete,
  canCompleteProductionTask,
}: {
  workOrder: WorkOrder;
  runtimeMode: "demo" | "production";
  isWorkflowWorkOrder: boolean;
  workflowWritable: boolean;
  onClose: () => void;
  onToggleTask: (taskId: string) => void;
  onStart: () => void;
  onComplete: () => void;
  onProductionTaskCompleted: () => Promise<void>;
  canComplete: boolean;
  canCompleteProductionTask: boolean;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const completed = workOrder.tasks.filter((task) => task.completed).length;
  const productionMode = runtimeMode === "production";
  const nextProductionTask = productionMode
    ? workOrder.tasks.find((task) => !task.completed)
    : undefined;
  const eamStatusLabel =
    workOrder.eam?.syncStatus === "pending"
      ? "等待发布"
      : workOrder.eam?.syncStatus === "accepted"
        ? "EAM 已接收"
        : workOrder.eam?.syncStatus === "in_progress"
          ? "EAM 执行中"
          : workOrder.eam?.syncStatus === "completed" || workOrder.eam?.syncStatus === "closed"
            ? "EAM 已完成"
            : (workOrder.eam?.syncStatus.replaceAll("_", " ") ?? "未启用");
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭工单详情" />
      <aside
        ref={dialogRef}
        tabIndex={-1}
        className="detail-drawer work-order-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${workOrder.id} 工单详情`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">工单</span>
            <h2>{workOrder.id}</h2>
            <p>
              {workOrder.turbineId} · {workOrder.assignedTeam}
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="detail-drawer__status">
          <StatusBadge
            value={workOrder.status}
            label={statusLabels[workOrder.status]}
            tone={
              workOrder.status === "completed" || workOrder.status === "closed"
                ? "success"
                : workOrder.status === "in-progress"
                  ? "info"
                  : "warning"
            }
          />
          <StatusBadge
            value={workOrder.priority}
            label={
              workOrder.priority === "critical"
                ? "严重"
                : workOrder.priority === "high"
                  ? "高"
                  : workOrder.priority === "medium"
                    ? "中"
                    : "低"
            }
            tone={
              workOrder.priority === "critical"
                ? "critical"
                : workOrder.priority === "high"
                  ? "warning"
                  : "info"
            }
          />
          <span>{new Date(workOrder.plannedStart).toLocaleDateString("zh-CN")}</span>
        </div>
        <section className="work-order-hero">
          <span>
            <ClipboardCheck size={22} />
          </span>
          <div>
            <h3>{workOrder.issue}</h3>
            <p>{workOrder.description}</p>
          </div>
        </section>
        {workOrder.createdByAgentId ? (
          <div className="ai-generated-note">
            <Bot size={15} />
            <span>
              <strong>由工单 Agent 自动生成</strong>
              <small>来源 {workOrder.relatedMissionId} · 已通过安全审核</small>
            </span>
            <StatusBadge value="approved" label="AI 已验证" tone="info" compact />
          </div>
        ) : null}
        {productionMode && workOrder.eam ? (
          <div className="ai-generated-note" role="status">
            <PackageCheck size={15} />
            <span>
              <strong>企业资产管理系统同步</strong>
              <small>
                {workOrder.eam.externalId
                  ? `${workOrder.eam.provider ?? "EAM"} 工单 ${workOrder.eam.externalId}`
                  : "审批事务已持久化，等待出站工作进程发布"}
                {workOrder.eam.externalUpdatedAt
                  ? ` · 外部更新时间 ${new Date(workOrder.eam.externalUpdatedAt).toLocaleString("zh-CN")}`
                  : ""}
              </small>
            </span>
            <StatusBadge
              value={workOrder.eam.syncStatus}
              label={eamStatusLabel}
              tone={
                workOrder.eam.syncStatus === "completed" || workOrder.eam.syncStatus === "closed"
                  ? "success"
                  : workOrder.eam.syncStatus === "pending"
                    ? "warning"
                    : "info"
              }
              compact
            />
          </div>
        ) : null}
        <section className="drawer-section">
          <h3>计划信息</h3>
          <div className="key-value-list">
            <KeyValue
              label="计划开始"
              value={new Date(workOrder.plannedStart).toLocaleString("zh-CN")}
            />
            <KeyValue
              label="完成期限"
              value={new Date(workOrder.deadline).toLocaleString("zh-CN")}
            />
            <KeyValue label="预计时长" value={`${workOrder.estimatedDurationHours} 小时`} />
            <KeyValue label="责任班组" value={workOrder.assignedTeam} />
            <KeyValue label="关联 Mission" value={workOrder.relatedMissionId ?? "—"} mono />
          </div>
        </section>
        <section className="drawer-section">
          <div className="drawer-section__title">
            <h3>任务清单</h3>
            <span className="record-count">
              {completed} / {workOrder.tasks.length}
            </span>
          </div>
          <Progress value={(completed / Math.max(1, workOrder.tasks.length)) * 100} tone="info" />
          {!productionMode && (!isWorkflowWorkOrder || !workflowWritable) ? (
            <div className="ai-generated-note" role="note">
              <ShieldCheck size={15} />
              <span>
                <strong>{isWorkflowWorkOrder ? "D1 暂不可写" : "只读 Demo 工单"}</strong>
                <small>
                  {isWorkflowWorkOrder
                    ? "服务器持久化不可用，任务与执行动作已安全禁用。"
                    : `当前状态为 ${statusLabels[workOrder.status]}；仅 ${WORKFLOW_WORK_ORDER_ID} 接入 WT-023 闭环，任务与执行动作已禁用。`}
                </small>
              </span>
              <StatusBadge value="read-only" label="只读" tone="maintenance" compact />
            </div>
          ) : null}
          <div className="task-checklist">
            {workOrder.tasks.map((task) => (
              <label key={task.id}>
                <input
                  type="checkbox"
                  checked={task.completed}
                  disabled={
                    productionMode ||
                    !isWorkflowWorkOrder ||
                    !workflowWritable ||
                    workOrder.status !== "in-progress"
                  }
                  onChange={() => {
                    if (isWorkflowWorkOrder) onToggleTask(task.id);
                  }}
                />
                <span>
                  <strong>
                    {task.sequence}. {task.title}
                  </strong>
                  {task.completionNote ? <small>{task.completionNote}</small> : null}
                </span>
              </label>
            ))}
          </div>
          {productionMode &&
          nextProductionTask &&
          (workOrder.status === "scheduled" || workOrder.status === "in-progress") ? (
            canCompleteProductionTask ? (
              <FieldTaskCompletionForm
                key={nextProductionTask.id}
                workOrderId={workOrder.id}
                task={nextProductionTask}
                onCompleted={onProductionTaskCompleted}
                authorized={canCompleteProductionTask}
              />
            ) : (
              <div
                className="ai-generated-note"
                role="status"
                data-capability="work_order.task.complete"
              >
                <ShieldCheck size={15} />
                <span>
                  <strong>现场任务只读</strong>
                  <small>提交证据和完成任务需要现场技术员及对应工单范围授权。</small>
                </span>
              </div>
            )
          ) : null}
        </section>
        <section className="drawer-section">
          <h3>安全与 PPE</h3>
          <div className="safety-procedure">
            <span className="safety-procedure__icon">
              <ShieldCheck size={15} />
            </span>
            <div>
              {workOrder.safetyProcedures.map((procedure) => (
                <span key={procedure}>
                  <Check size={11} /> {procedure}
                </span>
              ))}
            </div>
          </div>
          <div className="ppe-chips">
            {workOrder.ppeRequirements.map((item) => (
              <span key={item}>
                <HardHat size={11} /> {item}
              </span>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>备件与工具</h3>
          <div className="part-list">
            {workOrder.spareParts.map((part) => (
              <div key={part.partNumber}>
                <span>
                  <PackageCheck size={14} />
                </span>
                <div>
                  <strong>{part.name}</strong>
                  <small>
                    {part.partNumber} · 需要 {part.quantity}
                  </small>
                </div>
                <StatusBadge
                  value={part.available >= part.quantity ? "available" : "shortage"}
                  label={part.available >= part.quantity ? `可用 ${part.available}` : "库存不足"}
                  tone={part.available >= part.quantity ? "success" : "critical"}
                  compact
                />
              </div>
            ))}
          </div>
          <div className="tool-chip-grid">
            {workOrder.requiredTools.map((tool) => (
              <span key={tool}>
                <Wrench size={11} /> {tool}
              </span>
            ))}
          </div>
        </section>
        <footer className="detail-drawer__footer">
          <Button variant="secondary" onClick={() => window.print()}>
            <Download size={14} /> 导出 PDF
          </Button>
          <Button variant="secondary" disabled title="资源重新指派将在资源中心完成">
            <UserRound size={14} /> 重新指派
          </Button>
          {productionMode ? (
            <Button variant="primary" disabled>
              <ShieldCheck size={14} />
              {workOrder.status === "completed"
                ? "证据已验证 · 工单已闭环"
                : nextProductionTask
                  ? `按任务 ${nextProductionTask.sequence} 提交现场证据`
                  : `当前状态 · ${statusLabels[workOrder.status]}`}
            </Button>
          ) : !isWorkflowWorkOrder || !workflowWritable ? (
            <Button
              variant="primary"
              disabled
              title={
                isWorkflowWorkOrder
                  ? "D1 持久化当前不可用"
                  : `${workOrder.id} 为只读 Demo 工单，不会修改 WT-023 闭环状态`
              }
            >
              <ShieldCheck size={14} /> 只读 · {statusLabels[workOrder.status]}
            </Button>
          ) : workOrder.status === "scheduled" ? (
            <Button variant="primary" onClick={onStart}>
              <Wrench size={14} /> 开始执行
            </Button>
          ) : workOrder.status === "in-progress" ? (
            <Button variant="primary" onClick={onComplete} disabled={!canComplete}>
              <CheckCircle2 size={14} />{" "}
              {canComplete ? "完成并回写" : `完成任务 ${completed}/${workOrder.tasks.length}`}
            </Button>
          ) : (
            <Button variant="primary" disabled>
              <CheckCircle2 size={14} />{" "}
              {workOrder.status === "completed" ? "闭环已完成" : "等待审批"}
            </Button>
          )}
        </footer>
      </aside>
    </>
  );
}
