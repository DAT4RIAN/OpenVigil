# Worksheets

`workbook.worksheets` and `workbook.sheets` expose the worksheet collection.

## Collection

```ts
const sheet = workbook.worksheets.add("Data");
const existing = workbook.worksheets.getItem("Data");
const maybe = workbook.worksheets.getItemOrNullObject("Data");
const first = workbook.worksheets.getFirst();
const active = workbook.worksheets.getActiveWorksheet();

workbook.worksheets.setActiveWorksheet("Data");
const count = workbook.worksheets.getSheetCount();
const index = workbook.worksheets.getSheetIndex("Data");
const name = workbook.worksheets.getSheetNameByIndex(0);
const byIndex = workbook.worksheets.getItemAt(0);
```

## Worksheet Properties

```ts
sheet.name = "Renamed";
sheet.index = 0;
sheet.showGridLines = false;
sheet.tabColor = "#1F4E78";

sheet.id;
sheet.sheetId;
sheet.tabColor;
sheet.defaultRowHeight;
sheet.defaultColWidth;
sheet.baseColWidth;
```

## Ranges

```ts
const range = sheet.getRange("A1:B2");
const byIndexes = sheet.getRangeByIndexes(0, 0, 2, 2);
const cell = sheet.getCell(0, 0);
const used = sheet.getUsedRange();
const usedValuesOnly = sheet.getUsedRange(true);
```

`getRange` accepts A1 strings only. Use zero-based row/column indexes with
`getRangeByIndexes` and `getCell`.

## Worksheet Collections

```ts
sheet.tables;
sheet.charts;
sheet.shapes;
sheet.images;
sheet.pivotTables;
sheet.slicers;
sheet.sparklineGroups;
sheet.conditionalFormattings;
sheet.dataValidations;
sheet.freezePanes;
sheet.names;
sheet.cells;
```

## Reset And Delete

```ts
sheet.reset({
  clear: "used",
  applyTo: "all",
  deleteTables: true,
  deleteCharts: true,
  deleteDrawings: true,
  deleteSparklines: true,
});

sheet.delete();
```

## Merge

```ts
sheet.mergeCells("A1:B2");
sheet.unmergeCells("A1:B2");
```

## Drawings

```ts
sheet.deleteAllDrawings();
sheet.autoLayoutDrawings(items, options);
```

## Inline Types

```ts
type WorksheetResetOptions = {
  clear?: "used" | "none";
  applyTo?: "contents" | "formats" | "all";
  deleteTables?: boolean;
  deleteCharts?: boolean;
  deleteDrawings?: boolean;
  deleteSparklines?: boolean;
};
```

## Cookbook

```ts
const sheet = workbook.worksheets.add("Data");
sheet.getRange("A1:B2").values = [
  ["Name", "Value"],
  ["A", 1],
];
sheet.mergeCells("D1:E1");
sheet.freezePanes.freezeRows(1);
```
