"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/primitives";
import {
  acquisitionHeader,
  isStructuralObject,
  MAX_STRUCTURAL_BYTES,
  optionalNumber,
  type DirectForceHeader,
  type WaveformHeader,
} from "@/lib/structural-acquisition";
import { structuralFact } from "@/lib/structural-workflow";
import { useStructuralArtifactCommand } from "./structural-artifact-command";
import styles from "./structural-page.module.css";

export function StructuralRecordForm({
  turbineId,
  onRegistered,
  onLockChange,
}: {
  readonly turbineId: string;
  readonly onRegistered: (recordId: string) => void;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const client = useQueryClient();
  const command = useStructuralArtifactCommand();
  const [file, setFile] = useState<File | null>(null);
  const selected = useRef<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [header, setHeader] = useState<WaveformHeader | DirectForceHeader | null>(null);
  const [reading, setReading] = useState(false);
  const [sourceKind, setSourceKind] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [environment, setEnvironment] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [registeredId, setRegisteredId] = useState("");
  useEffect(() => {
    onLockChange(command.busy || command.unknown);
    return () => onLockChange(false);
  }, [command.busy, command.unknown, onLockChange]);
  async function readFile(value: File | null) {
    selected.current = value;
    setFile(value);
    setHeader(null);
    setError(null);
    setRegisteredId("");
    if (!value) {
      setReading(false);
      return;
    }
    setReading(true);
    try {
      if (!value.size || value.size > MAX_STRUCTURAL_BYTES)
        throw new Error("结构原始文件必须在 1 Byte 到 32 MiB 之间。");
      const parsed = acquisitionHeader(await value.text(), turbineId);
      if (selected.current === value) setHeader(parsed);
    } catch (cause) {
      if (selected.current === value)
        setError(cause instanceof Error ? cause.message : "资料解析失败。");
    } finally {
      if (selected.current === value) setReading(false);
    }
  }
  async function submit() {
    if (!file || !header || !sourceKind) return;
    setError(null);
    try {
      const body =
        header.kind === "waveform"
          ? {
              turbine_id: turbineId,
              channel_ids: header.channel_ids,
              started_at: header.started_at,
              ended_at: header.ended_at,
              sample_rate_hz: header.sample_rate_hz,
              sample_count: header.sample_count,
              source_kind: sourceKind,
              source_reference: sourceReference,
              environment: {
                operating_state: environment.operating_state,
                ...Object.fromEntries(
                  ["temperature_c", "wind_speed_ms", "rotor_speed_rpm", "power_kw"].map((key) => [
                    key,
                    optionalNumber(environment[key] ?? "", key),
                  ]),
                ),
              },
            }
          : {
              turbine_id: turbineId,
              tendon_id: header.tendon_id,
              sensor_id: header.sensor_id,
              source_kind: sourceKind,
            };
      const saved = await command.run(
        {
          file,
          presignPath: "/api/backend/structural-records/uploads/presign",
          presignBody: { turbine_id: turbineId },
          commandPath: `/api/backend/${header.kind === "waveform" ? "structural-records" : "prestress-observations"}`,
          commandBody: body,
        },
        isStructuralObject,
        "原始结构资料已校验并登记。",
      );
      if (saved) {
        setRegisteredId(saved.id);
        if (header.kind === "waveform") onRegistered(saved.id);
        await Promise.all([
          client.invalidateQueries({ queryKey: ["structural-records", turbineId] }),
          client.invalidateQueries({ queryKey: ["structural-health", turbineId] }),
          client.invalidateQueries({ queryKey: ["structural-retest-sources", turbineId] }),
        ]);
        setFile(null);
        selected.current = null;
        setHeader(null);
        if (fileInput.current) fileInput.current.value = "";
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "请核对采集资料。");
    }
  }
  return (
    <section aria-label="原始结构资料登记">
      <p>
        选择 openvigil.waveform.v1 波形或 openvigil.direct-force.v1 仪器
        JSON。上传原始字节；质量不合格不会自动修补或变成健康结论。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset className={styles.formFields} disabled={command.busy || command.unknown}>
          <label className={styles.field}>
            原始结构 JSON 文件
            <input
              type="file"
              accept=".json,application/json"
              required
              ref={fileInput}
              onChange={(event) => void readFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label className={styles.field}>
            资料来源分类
            <select
              required
              value={sourceKind}
              onChange={(event) => setSourceKind(event.target.value)}
            >
              <option value="">请选择实际来源</option>
              <option value="field_measurement">现场测量</option>
              <option value="public_sample">公开样本</option>
              <option value="synthetic_test">合成软件测试</option>
            </select>
          </label>
          {header?.kind === "waveform" ? (
            <>
              <label className={styles.field}>
                采集资料引用
                <input
                  required
                  maxLength={320}
                  value={sourceReference}
                  onChange={(event) => setSourceReference(event.target.value)}
                />
              </label>
              <label className={styles.field}>
                采集工况
                <select
                  required
                  value={environment.operating_state ?? ""}
                  onChange={(event) =>
                    setEnvironment({ ...environment, operating_state: event.target.value })
                  }
                >
                  <option value="">请选择</option>
                  <option value="stopped">停机</option>
                  <option value="running">运行</option>
                  <option value="unknown">未知（不用于健康基线）</option>
                </select>
              </label>
              {[
                ["temperature_c", "温度 (°C，可选)"],
                ["wind_speed_ms", "风速 (m/s，可选)"],
                ["rotor_speed_rpm", "转速 (rpm，可选)"],
                ["power_kw", "功率 (kW，可选)"],
              ].map(([key, label]) => (
                <label className={styles.field} key={key}>
                  {label}
                  <input
                    type="number"
                    step="any"
                    min={key === "wind_speed_ms" || key === "rotor_speed_rpm" ? 0 : undefined}
                    value={environment[key] ?? ""}
                    onChange={(event) =>
                      setEnvironment({ ...environment, [key]: event.target.value })
                    }
                  />
                </label>
              ))}
            </>
          ) : null}
        </fieldset>
        {reading ? <p role="status">正在读取原始资料头信息…</p> : null}
        {header ? (
          <div className={styles.item}>
            <h3>原始文件信息</h3>
            {header.kind === "waveform" ? (
              <>
                <p>
                  {header.channel_ids.length} 个通道 · {header.sample_count} 点/通道 ·{" "}
                  {header.sample_rate_hz} Hz
                </p>
                <p>
                  {header.started_at} → {header.ended_at}（结束时刻不包含）
                </p>
                <p>通道 {header.channel_ids.join("、")}</p>
              </>
            ) : (
              <>
                <p>
                  {header.value} {header.unit} · {header.observed_at}
                </p>
                <p>
                  索束 {header.tendon_id} · 测点 {header.sensor_id}
                </p>
                <p>校准 {structuralFact(header.calibration_version)}</p>
              </>
            )}
          </div>
        ) : null}
        {command.unknown ? <p role="status">提交结果待核验，保持原文件与来源声明后重试。</p> : null}
        <Button type="submit" loading={command.busy} disabled={!header || reading || !sourceKind}>
          {command.unknown ? "核验原资料登记" : "上传并登记原始资料"}
        </Button>
      </form>
      {error || command.error ? (
        <p role="alert" className={styles.error}>
          {error ?? command.error}
        </p>
      ) : null}
      {command.notice && registeredId ? (
        <p role="status">
          {command.notice} {registeredId}
        </p>
      ) : null}
    </section>
  );
}
