"use client";

import { useRef, useState } from "react";
import { apiPostCommand, createIdempotencyKey, OpenVigilApiError } from "@/lib/api-client";

/** Keep an unknown write result replayable; a new click must not create a second command. */
export function useStructuralCommand() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [unknown, setUnknown] = useState(false);
  const inFlight = useRef(false);
  const receipt = useRef<{ path: string; body: string; key: string; uncertain: boolean } | null>(
    null,
  );

  async function run<T>(
    path: string,
    body: unknown,
    success: string,
    validate?: (value: unknown) => value is T,
  ): Promise<T | undefined> {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const serialized = JSON.stringify(body);
      const changed = receipt.current?.path !== path || receipt.current?.body !== serialized;
      if (receipt.current?.uncertain && changed)
        throw new OpenVigilApiError(
          0,
          "COMMAND_RESULT_UNKNOWN",
          "原命令结果仍待核验，请恢复原输入后重试。",
          null,
          receipt.current.key,
        );
      if (!receipt.current || changed) {
        receipt.current = {
          path,
          body: serialized,
          key: createIdempotencyKey("structural"),
          uncertain: false,
        };
      }
      const result = await apiPostCommand<T>(path, body, receipt.current.key);
      if (validate && !validate(result))
        throw new OpenVigilApiError(
          0,
          "COMMAND_RESULT_UNKNOWN",
          "命令响应不完整，请保持原输入并重试核验。",
          null,
          receipt.current.key,
        );
      receipt.current = null;
      setUnknown(false);
      setNotice(success);
      return result;
    } catch (cause) {
      const uncertain = cause instanceof OpenVigilApiError && cause.status === 0;
      setUnknown(uncertain);
      if (uncertain && receipt.current) receipt.current.uncertain = true;
      else receipt.current = null;
      setError(cause instanceof Error ? cause.message : "操作失败，请刷新后重试。");
      return undefined;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { busy, unknown, error, notice, run };
}
