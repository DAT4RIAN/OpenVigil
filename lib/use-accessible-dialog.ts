"use client";

import { useEffect, useEffectEvent, useRef, type RefObject } from "react";

const focusableSelector = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/** Shared modal focus behavior for the four operational detail drawers. */
export function useAccessibleDialog<T extends HTMLElement>(
  onClose: () => void,
  active = true,
): RefObject<T | null> {
  const dialogRef = useRef<T>(null);
  const closeDialog = useEffectEvent(onClose);

  useEffect(() => {
    if (!active) return;
    const restoreTarget =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
    (focusable()[0] ?? dialog).focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      restoreTarget?.focus();
    };
  }, [active]);

  return dialogRef;
}
