"use client";

import { useEffect, useRef } from "react";

/** Route feedback without remounting forms, replaying live data, or delaying navigation. */
export function usePageEntrance(route: string) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = ref.current;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!element || preference.matches || document.hidden || !element.animate) return;

    // Keep text at full contrast throughout the transition, including its first frame.
    const animations: Animation[] = [];
    const heading = element.querySelector<HTMLElement>(".page-header");
    if (heading) {
      animations.push(
        heading.animate([{ transform: "translateY(6px)" }, { transform: "none" }], {
          duration: 240,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        }),
      );
    }
    const cancel = () => animations.forEach((animation) => animation.cancel());
    const onPreferenceChange = () => {
      if (preference.matches) cancel();
    };
    preference.addEventListener("change", onPreferenceChange);
    return () => {
      cancel();
      preference.removeEventListener("change", onPreferenceChange);
    };
  }, [route]);

  return ref;
}
