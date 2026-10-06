"use client";

import { useRef, useState } from "react";
import {
  StructuralArtifactCommand,
  type ArtifactCommandInput,
} from "@/lib/structural-artifact-command";

export function useStructuralArtifactCommand() {
  const session = useRef(new StructuralArtifactCommand());
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function run<T>(
    input: ArtifactCommandInput,
    validate: (value: unknown) => value is T,
    success: string,
  ): Promise<T | undefined> {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await session.current.run(input, validate);
      setNotice(success);
      return result;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "制品提交失败，请重试。");
      return undefined;
    } finally {
      setUnknown(session.current.resultUnknown);
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { busy, unknown, error, notice, run };
}
