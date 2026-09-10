# Import, Export, HTML, Images, And Google Sheets

Workbook import/export helpers cover CSV, Markdown, HTML copy/paste,
image/chart conversion, rendering, and Google Sheets adapter flows.

## CSV

```ts
const workbook = await Workbook.fromCSV(csv, {
  sheetName: "Data",
});

const { sheet, range } = await workbook.fromCSV(csv, {
  sheetName: "Imported",
});
```

## Markdown Table

```ts
const workbook = await Workbook.fromMarkdown(markdown, {
  sheetName: "Data",
  format: true,
});
```

Markdown import expects a Markdown table. With `format: true`, the imported
range is formatted as a worksheet table and columns are autofit.

## HTML

```ts
const html = source.toHTML(0, "A1:B2");
const withFormulas = source.toHTML(0, "A1:B2", { formulas: true });

const result = target.fromHTML(0, html, "C3");
const filled = target.fromHTML(0, html, "B2:C4");
```

`sheetIndex` is zero-based. The optional range uses A1 syntax.

## Image Import

```ts
const result = workbook.fromImage(
  0,
  { bytes: imageBytes, contentType: "image/png" },
  "A1:D10",
);
```

### Worksheet Images

```ts
const sheet = workbook.worksheets.getItem("Data");
sheet.images.add({
  svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /></svg>',
  anchor: {
    from: { row: 0, col: 4 },
    extent: { widthPx: 48, heightPx: 48 },
  },
});
```

## Chart To Image

```ts
const result = await workbook.chartToImage(0, chart.id);
```

## Render And Export

```ts
const renderBlob = await workbook.render({
  sheet: "Data",
  range: "A1:C10",
  format: "png",
  scale: 2,
});

const exportBlob = await workbook.export({
  sheetName: "Data",
  range: "A1:C10",
  format: "png",
  scale: 2,
  headers: true,
});

const layoutBlob = await workbook.export({
  sheetName: "Data",
  range: "A1:C10",
  format: "layout",
});

const xlsxBlob = await workbook.export({ format: "xlsx" });
```

`format: "layout"` exports JSON evidence for workbook template
reconstruction. It includes sheet/range geometry, row and column metrics,
per-cell frames, style records, style regions, merged ranges, validations,
defined names, and drawing anchors. Use it as inspection evidence; keep authored
workbook creation scripts semantic instead of replaying the layout JSON at
runtime. Layout exports support sheet selection, `range`, and `autoCrop`;
`center`, `width`, and `height` are raster export options.

## Export Inline Types

```ts
type WorkbookExportFormat = "png" | "jpeg" | "layout" | "xlsx";

type WorkbookExportOptions = {
  fileName?: string;
  sheet?: Worksheet | string | number;
  sheetName?: string;
  sheetIndex?: number;
  range?: string;
  center?: string;
  width?: number;
  height?: number;
  scale?: number;
  autoCrop?: "all" | "charts";
  headers?: boolean;
  format?: WorkbookExportFormat;
  quality?: number;
};
```

## Google Sheets

```ts
const workbook = await Workbook.fromGoogleSheets(config);
workbook.configureGoogleSheets(config);

const { patch } = workbook.record(() => {
  workbook.worksheets.getItem("Data").getRange("A1").values = [["Updated"]];
});

await workbook.apply(patch, { target: "googleSheets" });
```

## Cookbook

```ts
const workbook = await Workbook.fromCSV(csv, { sheetName: "Data" });
const preview = await workbook.export({
  sheetName: "Data",
  range: "A1:D20",
  format: "png",
  scale: 2,
});
const proto = workbook.toProto();
```
