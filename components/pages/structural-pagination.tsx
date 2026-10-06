"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";
import styles from "./structural-page.module.css";

export function useStructuralCursor() {
  const [history, setHistory] = useState([""]);
  return {
    value: history[history.length - 1],
    hasPrevious: history.length > 1,
    next: (cursor: string) => {
      if (cursor) setHistory((current) => [...current, cursor]);
    },
    previous: () => setHistory((current) => (current.length > 1 ? current.slice(0, -1) : current)),
    first: () => setHistory([""]),
  };
}

export function StructuralPagination({
  label,
  cursor,
  nextCursor,
  disabled,
}: {
  readonly label: string;
  readonly cursor: ReturnType<typeof useStructuralCursor>;
  readonly nextCursor: string | null | undefined;
  readonly disabled: boolean;
}) {
  return (
    <div className={styles.row} aria-label={`${label}分页`}>
      <Button disabled={disabled || !cursor.hasPrevious} onClick={cursor.first}>
        {label}首页
      </Button>
      <Button disabled={disabled || !cursor.hasPrevious} onClick={cursor.previous}>
        {label}上页
      </Button>
      <Button disabled={disabled || !nextCursor} onClick={() => cursor.next(nextCursor ?? "")}>
        {label}下页
      </Button>
    </div>
  );
}
