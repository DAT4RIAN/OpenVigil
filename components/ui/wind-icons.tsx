import { createLucideIcon } from "lucide-react";

// Product asset icons share Lucide's viewBox, currentColor, stroke and ref contract.
// Decorative beside their existing navigation labels; no additional tab stop.
export const WindTurbineIcon = createLucideIcon("WindTurbine", [
  ["circle", { cx: "12", cy: "9", r: "1.5", key: "hub" }],
  ["path", { d: "M12 7.5V2m1.3 7.75 5.76 3.33M10.7 9.75l-5.76 3.33", key: "blades" }],
  ["path", { d: "M12 10.5V22m-4 0h8", key: "tower" }],
]);

export const WindFarmIcon = createLucideIcon("WindFarm", [
  ["circle", { cx: "8", cy: "8", r: "1.25", key: "near-hub" }],
  ["path", { d: "M8 6.75V2m1.08 6.63L13.2 11M6.92 8.63 2.8 11", key: "near-blades" }],
  ["path", { d: "M8 9.25V22", key: "near-tower" }],
  ["circle", { cx: "18", cy: "12", r: "1", key: "far-hub" }],
  ["path", { d: "M18 11V7m.87 5.5 3.46 2m-5.2-2-3.46 2", key: "far-blades" }],
  ["path", { d: "M18 13v9M4 22h18", key: "far-tower-and-ground" }],
]);
