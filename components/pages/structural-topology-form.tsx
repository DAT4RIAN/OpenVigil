"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/primitives";
import {
  awareTimestamp,
  isStructuralObject,
  jsonObject,
  optionalNumber,
} from "@/lib/structural-acquisition";
import type { StructuralTopology } from "@/lib/structural-workflow";
import { useStructuralCommand } from "./structural-command";
import styles from "./structural-page.module.css";

type Kind = "component" | "tendon" | "sensor";
const labels = { component: "构件", tendon: "索束", sensor: "测点" };
export function StructuralTopologyForm({
  kind,
  turbineId,
  topology,
  onLockChange,
}: {
  readonly kind: Kind;
  readonly turbineId: string;
  readonly topology: StructuralTopology;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState("");
  const set = (name: string, value: string) =>
    setDraft((current) => ({
      ...current,
      [name]: value,
      ...(name === "component_id" ? { tendon_id: "" } : {}),
      ...(name === "quantity" ? { unit: "" } : {}),
    }));
  useEffect(() => {
    onLockChange(command.busy || command.unknown);
    return () => onLockChange(false);
  }, [command.busy, command.unknown, onLockChange]);
  const field = (
    name: string,
    label: string,
    options?: readonly (readonly [string, string])[],
    required = true,
    type = "text",
  ) => (
    <label className={styles.field} key={name}>
      {label}
      {options ? (
        <select
          required={required}
          value={draft[name] ?? ""}
          onChange={(event) => set(name, event.target.value)}
        >
          <option value="">请选择</option>
          {options.map(([id, text]) => (
            <option key={id} value={id}>
              {text}
            </option>
          ))}
        </select>
      ) : (
        <input
          required={required}
          type={type}
          step={type === "number" ? "any" : undefined}
          value={draft[name] ?? ""}
          onChange={(event) => set(name, event.target.value)}
          maxLength={type === "text" ? 320 : undefined}
        />
      )}
    </label>
  );
  const components = topology.components.items.map(
    (item) => [item.id, `${item.code} · ${item.name ?? item.id} · ${item.revision}`] as const,
  );
  const tendons = topology.tendons.items
    .filter((item) => item.component_id === draft.component_id)
    .map((item) => [item.id, `${item.code} · ${item.revision}`] as const);

  async function submit() {
    setError(null);
    try {
      const common = { turbine_id: turbineId, code: draft.code, revision: draft.revision };
      let payload: Record<string, unknown>;
      if (kind === "component")
        payload = {
          ...common,
          name: draft.name,
          component_type: draft.component_type,
          design_reference: draft.design_reference,
          ...(draft.parent_id ? { parent_id: draft.parent_id } : {}),
          geometry: draft.details ? jsonObject(JSON.parse(draft.details)) : {},
        };
      else if (kind === "tendon")
        payload = {
          ...common,
          component_id: draft.component_id,
          effective_length_m: optionalNumber(draft.effective_length_m ?? "", "有效长度"),
          line_density_kg_m: optionalNumber(draft.line_density_kg_m ?? "", "线密度"),
          boundary: draft.details ? jsonObject(JSON.parse(draft.details)) : {},
        };
      else
        payload = {
          ...common,
          component_id: draft.component_id,
          ...(draft.tendon_id ? { tendon_id: draft.tendon_id } : {}),
          quantity: draft.quantity,
          unit: draft.unit,
          direction: draft.direction,
          range_min: optionalNumber(draft.range_min ?? "", "量程下限"),
          range_max: optionalNumber(draft.range_max ?? "", "量程上限"),
          calibration_version: draft.calibration_version,
          calibration_at: awareTimestamp(draft.calibration_at ?? ""),
          calibration_valid_until: awareTimestamp(draft.calibration_valid_until ?? ""),
          calibration_reference: draft.calibration_reference,
          synchronization_source: draft.synchronization_source,
        };
      const saved = await command.run(
        `/api/backend/${{ component: "tower-components", tendon: "tendon-assemblies", sensor: "sensor-channels" }[kind]}`,
        payload,
        `${labels[kind]}版本已保存。`,
        isStructuralObject,
      );
      if (saved) {
        setCreatedId(saved.id);
        setDraft({});
        await client.invalidateQueries({ queryKey: ["structural-topology", turbineId] });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "请检查建档输入。");
    }
  }
  return (
    <section aria-label={`${labels[kind]}建档`}>
      <p>
        保存独立版本；现有资产和校准记录保持。时间需填写完整时区，例如 2026-10-05T10:00:00+08:00。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset className={styles.formFields} disabled={command.busy || command.unknown}>
          {field("code", `${labels[kind]}编码`)}
          {field("revision", `${labels[kind]}版本`)}
          {kind === "component" ? (
            <>
              {field("name", "构件名称")}
              {field("component_type", "构件类型", [
                ["concrete_segment", "混凝土段"],
                ["steel_segment", "钢段"],
                ["transition", "过渡段"],
                ["joint", "接缝"],
                ["anchor", "锚固"],
              ])}
              {field("design_reference", "设计资料引用")}
              {field("parent_id", "父构件（可选）", components, false)}
            </>
          ) : (
            field("component_id", "所属构件", components)
          )}
          {kind === "tendon" ? (
            <>
              {field("effective_length_m", "有效长度 (m，可选)", undefined, false, "number")}
              {field("line_density_kg_m", "线密度 (kg/m，可选)", undefined, false, "number")}
            </>
          ) : null}
          {kind === "sensor" ? (
            <>
              {field("quantity", "测量类型", [
                ["acceleration", "加速度"],
                ["force", "直接索力"],
                ["strain", "应变"],
              ])}
              {field("tendon_id", "所属索束（索力必填）", tendons, draft.quantity === "force")}
              {field(
                "unit",
                "测量单位",
                (
                  {
                    acceleration: [
                      ["m/s2", "m/s²"],
                      ["g", "g"],
                    ],
                    force: [
                      ["N", "N"],
                      ["kN", "kN"],
                    ],
                    strain: [["microstrain", "με"]],
                  } as Record<string, readonly (readonly [string, string])[]>
                )[draft.quantity] ?? [],
              )}
              {field("direction", "测量方向", [
                ["X", "X"],
                ["Y", "Y"],
                ["Z", "Z"],
                ["axial", "轴向"],
              ])}
              {field("range_min", "量程下限", undefined, true, "number")}
              {field("range_max", "量程上限", undefined, true, "number")}
              {field("calibration_version", "校准版本")}
              {field("calibration_at", "校准时间（含时区）")}
              {field("calibration_valid_until", "校准有效至（含时区）")}
              {field("calibration_reference", "校准资料引用")}
              {field("synchronization_source", "同步时钟来源")}
            </>
          ) : (
            <label className={styles.field}>
              {kind === "component"
                ? "几何参数 JSON（键名注明单位，可选）"
                : "边界条件 JSON（文字引用，可选）"}
              <textarea
                value={draft.details ?? ""}
                onChange={(event) => set("details", event.target.value)}
              />
            </label>
          )}
        </fieldset>
        {command.unknown ? <p role="status">结果待核验，保持原建档输入并重试。</p> : null}
        <Button type="submit" loading={command.busy}>
          {command.unknown ? "核验原建档" : `保存${labels[kind]}版本`}
        </Button>
      </form>
      {error || command.error ? (
        <p role="alert" className={styles.error}>
          {error ?? command.error}
        </p>
      ) : null}
      {command.notice ? (
        <p role="status">
          {command.notice} {createdId}
        </p>
      ) : null}
    </section>
  );
}
