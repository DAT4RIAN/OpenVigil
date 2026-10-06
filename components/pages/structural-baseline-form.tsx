"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/primitives";
import {
  awareTimestamp,
  isStructuralObject,
  optionalNumber,
  trainingModalIds,
} from "@/lib/structural-acquisition";
import { structuralFact, type StructuralTopology } from "@/lib/structural-workflow";
import { useStructuralCommand } from "./structural-command";
import styles from "./structural-page.module.css";

export function StructuralBaselineForm({
  turbineId,
  topology,
  onLockChange,
}: {
  readonly turbineId: string;
  readonly topology: StructuralTopology;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [draft, setDraft] = useState<Record<string, string>>({
    minimum_mac: "0.9",
    maximum_relative_frequency_shift: "0.2",
    screening_sigma: "3",
  });
  const [features, setFeatures] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [published, setPublished] = useState<{ id: string; validation: unknown } | null>(null);
  const set = (key: string, value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const ids = (draft.training ?? "")
    .trim()
    .split(/[\s,]+/)
    .filter(Boolean);
  useEffect(() => {
    onLockChange(command.busy || command.unknown);
    return () => onLockChange(false);
  }, [command.busy, command.unknown, onLockChange]);
  async function submit() {
    if (!confirmed || !features.length) return;
    setError(null);
    try {
      const observations = trainingModalIds(draft.training ?? "");
      const saved = await command.run(
        "/api/backend/health-baselines",
        {
          turbine_id: turbineId,
          component_id: draft.component_id,
          code: draft.code,
          revision: draft.revision,
          confirmation_reference: draft.confirmation_reference,
          reference_modal_id: draft.reference_modal_id,
          training_modal_ids: observations,
          features,
          valid_until: awareTimestamp(draft.valid_until ?? ""),
          ...Object.fromEntries(
            ["minimum_mac", "maximum_relative_frequency_shift", "screening_sigma"].map((key) => [
              key,
              optionalNumber(draft[key] ?? "", key),
            ]),
          ),
        },
        "健康基线版本已发布，实时数据不会自动改写它。",
        isStructuralObject,
      );
      if (saved) {
        const model = saved.model;
        setPublished({
          id: saved.id,
          validation:
            model && typeof model === "object" && "validation" in model
              ? model.validation
              : undefined,
        });
        setConfirmed(false);
        await client.invalidateQueries({ queryKey: ["structural-health", turbineId] });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "请核对健康基线资料。");
    }
  }
  return (
    <section aria-label="健康基线发布">
      <p>
        使用 30–256
        个互不重叠、已确认健康的采集窗。服务端核验构件、方法/配置、通道/校准、MAC、工况和环境适用域，保留最后
        20% 窗口的验证结果。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset className={styles.formFields} disabled={command.busy || command.unknown}>
          <label className={styles.field}>
            基线所属构件
            <select
              required
              value={draft.component_id ?? ""}
              onChange={(event) => set("component_id", event.target.value)}
            >
              <option value="">请选择实际构件</option>
              {topology.components.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.code} · {item.name} · {item.revision}
                </option>
              ))}
            </select>
          </label>
          {[
            ["code", "基线编码"],
            ["revision", "基线版本"],
            ["confirmation_reference", "健康确认资料引用"],
            ["valid_until", "基线有效至（含时区）"],
          ].map(([key, label]) => (
            <label className={styles.field} key={key}>
              {label}
              <input
                required
                maxLength={320}
                value={draft[key] ?? ""}
                onChange={(event) => set(key, event.target.value)}
              />
            </label>
          ))}
          <label className={styles.field}>
            健康训练模态 ID（每行一个）
            <textarea
              required
              value={draft.training ?? ""}
              onChange={(event) => {
                set("training", event.target.value);
                set("reference_modal_id", "");
              }}
            />
          </label>
          <p>已填写 {ids.length} 个引用。填写 ID 不代表窗口已通过质量与健康确认。</p>
          <label className={styles.field}>
            参考模态观测
            <select
              required
              value={draft.reference_modal_id ?? ""}
              onChange={(event) => set("reference_modal_id", event.target.value)}
            >
              <option value="">从训练观测中选择</option>
              {[...new Set(ids)].map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.row}>
            {[
              ["temperature_c", "温度"],
              ["wind_speed_ms", "风速"],
              ["rotor_speed_rpm", "转速"],
              ["power_kw", "功率"],
            ].map(([key, label]) => (
              <label className={styles.check} key={key}>
                <input
                  type="checkbox"
                  checked={features.includes(key)}
                  onChange={(event) =>
                    setFeatures(
                      event.target.checked
                        ? [...features, key]
                        : features.filter((value) => value !== key),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          {[
            ["minimum_mac", "最低 MAC", "0.8", "1"],
            ["maximum_relative_frequency_shift", "最大相对频率偏移", "0.000001", "0.5"],
            ["screening_sigma", "筛查 sigma 参数", "2", "6"],
          ].map(([key, label, min, max]) => (
            <label className={styles.field} key={key}>
              {label}
              <input
                required
                type="number"
                step="any"
                min={min}
                max={max}
                value={draft[key] ?? ""}
                onChange={(event) => set(key, event.target.value)}
              />
            </label>
          ))}
          <label className={styles.check}>
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            我确认这些窗口来自资料所指的健康期间，并承担本次基线发布责任。
          </label>
        </fieldset>
        {command.unknown ? <p role="status">发布结果待核验，使用原训练引用和版本重试。</p> : null}
        <Button
          type="submit"
          loading={command.busy}
          disabled={!features.length || (!confirmed && !command.unknown)}
        >
          {command.unknown ? "核验原基线发布" : "发布健康基线版本"}
        </Button>
      </form>
      {error || command.error ? (
        <p role="alert" className={styles.error}>
          {error ?? command.error}
        </p>
      ) : null}
      {command.notice ? <p role="status">{command.notice}</p> : null}
      {published ? (
        <div className={styles.item}>
          <h3>实际发布版本 {published.id}</h3>
          <p>{structuralFact(published.validation)}</p>
        </div>
      ) : null}
    </section>
  );
}
