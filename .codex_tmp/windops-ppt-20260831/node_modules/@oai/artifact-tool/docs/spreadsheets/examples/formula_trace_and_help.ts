import { Workbook } from "@oai/artifact-tool";

function clip(value: string, maxChars: number): string {
  return value.length > maxChars ? `${value.slice(0, maxChars)}...` : value;
}

function summarizeTrace(
  root: any,
  options: { maxDepth?: number; maxNodes?: number; maxFormulaChars?: number } = {},
): string[] {
  if (!root) return ["(no trace returned)"];

  const maxDepth = options.maxDepth ?? 4;
  const maxNodes = options.maxNodes ?? 30;
  const maxFormulaChars = options.maxFormulaChars ?? 120;
  const lines: string[] = [];
  let nodeCount = 0;
  let truncated = false;

  function walk(node: any, depth: number): void {
    if (nodeCount >= maxNodes) {
      truncated = true;
      return;
    }

    nodeCount += 1;
    const indent = "  ".repeat(depth);
    const formula = node.formula
      ? ` formula=${clip(String(node.formula), maxFormulaChars)}`
      : "";
    const error = node.error ? ` error=${node.error}` : "";
    lines.push(`${indent}${node.cell} value=${JSON.stringify(node.value)}${formula}${error}`);

    const children = (node.params ?? []) as any[];
    if (children.length === 0) return;
    if (depth >= maxDepth) {
      truncated = true;
      lines.push(`${indent}  ... ${children.length} precedent(s) not shown`);
      return;
    }
    for (const child of children) {
      walk(child, depth + 1);
    }
  }

  walk(root, 0);
  if (truncated) lines.push(`... trace summary capped at depth ${maxDepth}, ${maxNodes} nodes`);
  return lines;
}

function findTraceNode(root: any, cell: string): any | null {
  if (!root) return null;
  if (root.cell === cell) return root;
  for (const child of (root.params ?? []) as any[]) {
    const found = findTraceNode(child, cell);
    if (found) return found;
  }
  return null;
}

function formatNumber(value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (value !== 0 && Math.abs(value) < 0.01) return Number(value.toPrecision(3)).toString();
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatPercent(value: unknown): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : String(value);
}

function explainRevenueCheck(trace: any): string {
  const status = findTraceNode(trace, "Checks!F2")?.value;
  const difference = findTraceNode(trace, "Checks!D2")?.value;
  const actual = findTraceNode(trace, "Checks!B2")?.value;
  const expected = findTraceNode(trace, "Checks!C2")?.value;
  const tolerance = findTraceNode(trace, "Checks!E2")?.value;
  const baseRevenue = findTraceNode(trace, "Inputs!B2")?.value;
  const growthRate = findTraceNode(trace, "Inputs!B3")?.value;
  const revenue2025 = findTraceNode(trace, "Model!B4")?.value;

  return [
    `Checks!F2 returns "${status}" because the absolute difference is within the tolerance.`,
    `It compares Checks!D2 (${formatNumber(difference)}) against Checks!E2 (${formatNumber(tolerance)}).`,
    `Checks!D2 is actual revenue minus expected revenue: Checks!B2 (${formatNumber(actual)}) - Checks!C2 (${formatNumber(expected)}).`,
    `The actual value comes from Model!B5, which compounds Inputs!B2 (${formatNumber(baseRevenue)}) by the growth rate in Inputs!B3 (${formatPercent(growthRate)}) for two years: first to Model!B4 (${formatNumber(revenue2025)}), then to Model!B5 (${formatNumber(actual)}).`,
    `Caveat: the tiny difference shown is floating-point rounding noise, not a business variance.`,
  ].join("\n");
}

async function main(): Promise<void> {
  const workbook = Workbook.create();
  const inputs = workbook.worksheets.add("Inputs");
  const model = workbook.worksheets.add("Model");
  const checks = workbook.worksheets.add("Checks");

  inputs.getRange("A1:B4").values = [
    ["Metric", "Value"],
    ["Revenue 2024", 100],
    ["Growth Rate", 0.1],
    ["Expected Revenue 2026", 121],
  ];

  model.getRange("A1:B5").values = [
    ["Metric", "Value"],
    ["Revenue 2024", null],
    ["Growth Rate", null],
    ["Revenue 2025", null],
    ["Revenue 2026", null],
  ];
  model.getRange("B2:B5").formulas = [
    ["=Inputs!B2"],
    ["=Inputs!B3"],
    ["=B2*(1+B3)"],
    ["=B4*(1+B3)"],
  ];

  checks.getRange("A1:F2").values = [
    ["Check", "Actual", "Expected", "Difference", "Tolerance", "Status"],
    ["Revenue 2026 ties to expected case", null, null, null, 0.001, null],
  ];
  checks.getRange("B2:D2").formulas = [["=Model!B5", "=Inputs!B4", "=B2-C2"]];
  checks.getRange("F2").formulas = [["=IF(ABS(D2)<=E2,\"OK\",\"CHECK\")"]];

  workbook.recalculate();
  const trace = workbook.trace("Checks!F2");

  console.log("=== Formula trace for Checks!F2 ===");
  console.log(
    summarizeTrace(trace, {
      maxDepth: 4,
      maxNodes: 20,
    }).join("\n"),
  );

  console.log("\n=== User-facing answer: How is Checks!F2 calculated? ===");
  console.log(explainRevenueCheck(trace));

  console.log("\n=== Exact formula help: XLOOKUP ===");
  console.log(
    workbook.help("fx.XLOOKUP", {
      include: "index,examples,notes",
      maxChars: 2500,
    }).ndjson,
  );

  console.log("\n=== Formula category browse: financial ===");
  console.log(
    workbook.help("fx.*", {
      search: "financial",
      include: "index,examples",
      maxChars: 2500,
    }).ndjson,
  );

  console.log("\n=== Formula category browse: math-trig ===");
  console.log(
    workbook.help("fx.*", {
      search: "math-trig",
      include: "index,examples",
      maxChars: 2500,
    }).ndjson,
  );

  console.log("\n=== Semantic formula search: lookup with fallback ===");
  console.log(
    workbook.help("lookup value with fallback", {
      search: "XLOOKUP|INDEX|MATCH|IFERROR",
      include: "index,examples,notes",
      maxChars: 3000,
    }).ndjson,
  );
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
