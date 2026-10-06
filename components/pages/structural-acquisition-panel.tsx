"use client";

import { useEffect, useState } from "react";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { Card, CardHeader } from "@/components/ui/primitives";
import type { StructuralTopology } from "@/lib/structural-workflow";
import { StructuralTopologyForm } from "./structural-topology-form";
import { StructuralRecordForm } from "./structural-record-form";
import { StructuralAnalysisForm } from "./structural-analysis-form";
import { StructuralBaselineForm } from "./structural-baseline-form";
import styles from "./structural-page.module.css";

export function StructuralAcquisitionPanel({
  turbineId,
  topology,
  onLockChange,
}: {
  readonly turbineId: string;
  readonly topology: StructuralTopology;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const { session } = useOpenVigilIdentity();
  const [operation, setOperation] = useState("");
  const [recordId, setRecordId] = useState("");
  const [writeLocked, setWriteLocked] = useState(false);
  const [analysisLocked, setAnalysisLocked] = useState(false);
  const manager = session?.roles.includes("operations_manager");
  const field = manager || session?.roles.includes("field_technician");
  const analyst = manager || session?.roles.includes("maintenance_reviewer");
  const locked = writeLocked || analysisLocked;
  useEffect(() => {
    onLockChange(locked);
    return () => onLockChange(false);
  }, [locked, onLockChange]);
  return (
    <Card className={styles.panel}>
      <CardHeader
        title="结构采集与健康基线"
        description="按授权机组建立版本、登记原始资料、提交独立分析和发布已确认基线。"
      />
      <label className={styles.field}>
        采集操作
        <select
          value={operation}
          disabled={locked}
          onChange={(event) => setOperation(event.target.value)}
        >
          <option value="">请选择操作</option>
          <option value="component" disabled={!manager}>
            构件建档
          </option>
          <option value="tendon" disabled={!manager}>
            索束建档
          </option>
          <option value="sensor" disabled={!manager}>
            测点与校准建档
          </option>
          <option value="record" disabled={!field}>
            原始波形 / 直接索力登记
          </option>
          <option value="analysis" disabled={!analyst}>
            后台模态分析
          </option>
          <option value="baseline" disabled={!analyst}>
            健康基线发布
          </option>
        </select>
      </label>
      {manager &&
      (operation === "component" || operation === "tendon" || operation === "sensor") ? (
        <StructuralTopologyForm
          key={operation}
          kind={operation}
          turbineId={turbineId}
          topology={topology}
          onLockChange={setWriteLocked}
        />
      ) : null}
      {field && operation === "record" ? (
        <StructuralRecordForm
          turbineId={turbineId}
          onRegistered={setRecordId}
          onLockChange={setWriteLocked}
        />
      ) : null}
      {analyst && operation === "analysis" ? (
        <StructuralAnalysisForm
          turbineId={turbineId}
          recordId={recordId}
          onRecordChange={setRecordId}
          onLockChange={setAnalysisLocked}
        />
      ) : null}
      {analyst && operation === "baseline" ? (
        <StructuralBaselineForm
          turbineId={turbineId}
          topology={topology}
          onLockChange={setWriteLocked}
        />
      ) : null}
      {!manager && !field && !analyst ? (
        <p>当前角色可读取结构观测；采集与发布操作需要对应责任人权限。</p>
      ) : null}
    </Card>
  );
}
