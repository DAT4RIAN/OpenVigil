# Workbook API Docs

Use the workbook facades to create and edit Excel-style workbooks in TypeScript,
including worksheets, ranges, formulas, tables, charts, drawings, comments,
named ranges, import/export helpers, inspection, and recorded patches.

## Conventions

- **A1 addresses for ranges**: use `sheet.getRange("A1:B2")` for A1 ranges.
  Use `getRangeByIndexes(row, column, rowCount, columnCount)` and
  `getCell(row, column)` for zero-based index access.
- **Matrices are row-major**: range values and formulas use `rows x columns`
  arrays. Single-row and single-column ranges accept one-dimensional arrays.
- **Formulas include `=`**: assigning a string starting with `=` through
  `values` stores a formula; prefix with `'` to store a literal leading `=`.
- **Use `write` for shape-matched writes**: `range.write(...)` can resize from
  the target top-left cell.
- **Record user edits**: wrap edits in `workbook.record(() => { ... })` when a
  patch, id map, or CRDT update is needed.
- **Inspect before editing imported workbooks**: use `inspect`, `findCells`,
  and `resolve` to locate exact sheets, tables, charts, and threads.
- **Config-first creation**: prefer worksheet/range/table/chart config objects
  where available.

## Quick Start

```ts
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Data");

sheet.getRange("A1:C4").values = [
  ["Region", "Q1", "Q2"],
  ["North", 10, 12],
  ["South", 8, 9],
  ["Total", null, null],
];
sheet.getRange("B4:C4").formulas = [["=SUM(B2:B3)", "=SUM(C2:C3)"]];
workbook.recalculate();

const table = sheet.tables.add("A1:C4", true, "DataTable");
table.rows.add(null, [["West", 7, 11]]);

const chart = sheet.charts.add("bar", {
  from: { row: 1, col: 4 },
  extent: { widthPx: 420, heightPx: 260 },
});
chart.title = "Quarterly values";
chart.categories = ["North", "South", "West"];
const series = chart.series.add("Q1");
series.values = [10, 8, 7];
series.categories = chart.categories;

const preview = await workbook.export({
  sheet,
  range: "A1:C5",
  format: "png",
  scale: 2,
});
const layoutBlob = await workbook.export({
  sheet,
  range: "A1:C5",
  format: "layout",
});
const proto = workbook.toProto();
```

## Load Existing Workbook Data

```ts
const workbook = Workbook.load(proto, { validate: true });

const before = await workbook.inspect({
  kind: "sheet,table,formula,chart,thread",
  search: "Revenue",
  maxChars: 8000,
});

const sheet = workbook.resolve(sheetAnchorId);
sheet.getRange("B2").values = [["Updated"]];

const after = await workbook.inspect({
  target: { id: sheetAnchorId, beforeLines: 1, afterLines: 6 },
  kind: "sheet,table",
});
```

## Recorded Edit

```ts
const { result, patch, idMap, crdtUpdateV2 } = workbook.record(() => {
  const sheet = workbook.worksheets.getItem("Data");
  sheet.getRange("A1:B2").values = [
    ["Name", "Value"],
    ["A", 1],
  ];
  return sheet.tables.add("A1:B2", true, "DataTable");
});
```

`record` hydrates collaborative state when needed and returns the callback
result, a workbook patch, created-id aliases, and a merged CRDT update when
collaborative edits occurred.

## Core API Sequence

- Create workbooks with `Workbook.create()` and load with
  `Workbook.load(proto, { validate })`.
- Import simple tabular data with `Workbook.fromCSV(...)`,
  `workbook.fromCSV(...)`, and `Workbook.fromMarkdown(...)`.
- Add or select sheets with `workbook.worksheets.add(...)`, `getItem(...)`,
  `getActiveWorksheet()`, and
  `setActiveWorksheet(...)`.
- Edit data with `sheet.getRange("A1:B2").values`, `.formulas`,
  `.formulasR1C1`, `.write(...)`, `.clear(...)`, `.merge(...)`, and
  `.copyFrom(...)`.
- Add tables with `sheet.tables.add(range, hasHeaders, name)` and edit rows,
  columns, styles, totals, and filters on the table facade.
- Add charts, images, shapes, sparklines, conditional formats, data
  validations, freeze panes, pivot tables, slicers, comments, notes, and names
  through their worksheet/workbook facades.
- Recalculate formulas with `workbook.recalculate()` and inspect dependencies
  with `workbook.trace("Sheet!A1")`.
- Inspect imported workbooks with `workbook.inspect(...)`, `findCells(...)`,
  `help(...)`, and `resolve(...)`.
- Render previews with `workbook.render(...)` or `workbook.export(...)`.
- Export grid and style evidence with `workbook.export({ format: "layout" })`
  when template reconstruction needs cell frames, style regions, merged ranges,
  validations, defined names, and drawing anchors.
- Serialize workbook data with `workbook.toProto()`.

## Output Map

| Output          | API                                           | Result                                        |
| --------------- | --------------------------------------------- | --------------------------------------------- |
| Serialized data | `workbook.toProto()`                          | Serializable workbook proto                   |
| Inspect records | `await workbook.inspect(options)`             | Structured records and NDJSON                 |
| Cell search     | `workbook.findCells(options)`                 | Matches with sheet/address/value/formula info |
| Help records    | `workbook.help(query, options)`               | Bounded NDJSON API help records               |
| Image preview   | `workbook.export({ format: "png" })`          | Workbook/sheet/range render blob              |
| Layout JSON     | `workbook.export({ format: "layout" })`       | Typed grid and style evidence                 |
| Native workbook | `workbook.export({ format: "xlsx" })`         | Editable XLSX `Blob`                          |
| Render blob     | `workbook.render(options)`                    | Render-provider blob                          |
| HTML table      | `workbook.toHTML(sheetIndex, range, options)` | Excel/Sheets-compatible HTML                  |
| Recorded patch  | `workbook.record(fn)`                         | `{ result, patch, idMap, crdtUpdateV2 }`      |

## Minimal Patterns

```ts
// Data + formulas.
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Calc");
sheet.getRange("A1:B2").values = [
  [2, 3],
  [5, 7],
];
sheet.getRange("C1:C2").formulas = [["=A1+B1"], ["=A2+B2"]];
workbook.recalculate();
```

```ts
// Inspect, resolve, edit, re-inspect.
const snapshot = await workbook.inspect({
  kind: "sheet,table,formula,thread,chart",
  search: "Status",
});
const sheet = workbook.resolve(sheetAnchorId);
sheet.getRange("B2").values = [["Closed"]];
const updated = await workbook.inspect({
  target: { id: sheetAnchorId },
  kind: "sheet,table",
});
```

## Reference Map

- [`references/workbook.spec.md`](./references/workbook.spec.md) -
  `Workbook` create/load/import/export/inspect/help/record surface.
- [`references/worksheets.spec.md`](./references/worksheets.spec.md) -
  worksheet collection and worksheet facade.
- [`references/ranges.spec.md`](./references/ranges.spec.md) - values,
  formulas, indexing, formatting, clearing, merging, fill, and copy.
- [`references/tables.spec.md`](./references/tables.spec.md) - worksheet
  tables, rows, columns, headers, totals, and recorded patches.
- [`references/formulas.spec.md`](./references/formulas.spec.md) -
  recalculation, formula assignment, dynamic arrays, trace, and names.
- [`references/formatting.spec.md`](./references/formatting.spec.md) - range
  formats, workbook theme, conditional formatting, data validation, and freeze
  panes.
- [`references/charts-drawings.spec.md`](./references/charts-drawings.spec.md)
  - worksheet charts, images, shapes, sparklines, and drawing layout.
- [`references/comments-notes-names.spec.md`](./references/comments-notes-names.spec.md)
  - comments, notes, workbook-scoped names, and sheet-scoped names.
- [`references/inspect-help.md`](./references/inspect-help.md) - inspect,
  resolve, findCells, and help workflows.
- [`references/import-export.md`](./references/import-export.md) - CSV,
  Markdown, HTML, image import, rendering, export, and Google Sheets adapters.
