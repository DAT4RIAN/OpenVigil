# Inspect, Resolve, Find Cells, And Help

Use `inspect`, `resolve`, `findCells`, and `help` to edit imported workbooks
without guessing object identities.

## Inspect

```ts
const result = await workbook.inspect({
  kind: "sheet,table,formula,chart,thread",
  include: "id,text",
  exclude: "status",
  search: "Revenue",
  maxChars: 8000,
});

console.log(result.ndjson);
```

`inspect` returns bounded NDJSON records and metadata for parsed options,
unknown tokens, search filters, truncation, and target context.

## Targeted Inspect

```ts
const focused = await workbook.inspect({
  target: { id: sheetAnchorId, beforeLines: 1, afterLines: 6 },
  kind: "sheet,table",
});
```

## Resolve

```ts
const workbookTarget = workbook.resolve("wb/<id>");
const sheet = workbook.resolve("ws/<sheet-id-or-name>");
const thread = workbook.resolve("th/<thread-id>");
const chart = workbook.resolve("ch/<chart-id>");
```

`resolve` maps inspect anchors to editable facades.

## Find Cells

```ts
const matches = workbook.findCells({
  searchTerm: "East",
  sheetId: "Revenue",
  options: {
    maxResults: 10,
    matchFormulas: true,
  },
});
```

Result matches include sheet, address, value/formula match metadata, and total
count.

## Help

```ts
const result = workbook.help("*", {
  search: "setColorScheme|worksheet.charts.add",
  include: ["index", "examples", "notes"],
  maxChars: 12000,
});
console.log(result.ndjson);
```

Common queries:

```text
*, workbook.setColorScheme, worksheet.charts.add, formulas, enum.ChartType
```

## Create/Edit Loop

```ts
const before = await workbook.inspect({
  kind: "sheet,table,formula,thread,chart",
  search: "Status",
  maxChars: 8000,
});

const sheet = workbook.resolve(sheetAnchorId);
sheet.getRange("B2").values = [["Closed"]];

const after = await workbook.inspect({
  target: { id: sheetAnchorId, beforeLines: 1, afterLines: 6 },
  kind: "sheet,table",
  search: "Closed",
});
```

## Inline Types

```ts
type WorkbookInspectOptions = {
  fileName?: string | null;
  target?: { id: string; beforeLines?: number; afterLines?: number };
  kind?: string;
  include?: string;
  exclude?: string;
  search?: string;
  maxChars?: number;
};

type WorkbookInspectResult = {
  readonly records: readonly WorkbookInspectRecord[];
  readonly recordCount: number;
  ndjson: string;
  truncated: boolean;
  metadata: WorkbookInspectMetadata;
};

type WorkbookHelpOptions = {
  include?: string[] | string;
  search?: string;
  maxChars?: number;
};
```
