# Ranges

Ranges read and write cell values, formulas, formatting, validation,
conditional formats, sparklines, merges, fills, and copies.

## Addressing

```ts
const range = sheet.getRange("A1:B2");
const byIndexes = sheet.getRangeByIndexes(0, 0, 2, 2);
const cell = sheet.getCell(0, 0);

range.address;
range.getAddress();
range.rowIndex;
range.columnIndex;
range.rowCount;
range.columnCount;
```

## Values

```ts
sheet.getRange("A1:B2").values = [
  [1, 2],
  [3, 4],
];

sheet.getRange("B1:I1").values = [1, 2, 3, 4, 5, 6, 7, 8];
sheet.getRange("A2:A5").values = ["a", "b", "c", "d"];
```

Single-cell ranges can spill larger matrices:

```ts
sheet.getRange("N9").values = [[1, 2, 3]];
sheet.getRange("B2").values = [[1], [2], [3]];
```

## Formulas

```ts
sheet.getRange("C1").values = [["=SUM(A1:B1)"]];
sheet.getRange("D1").values = [["'=SUM(A1:B1)"]];

sheet.getRange("C1:C2").formulas = [["=A1+B1"], ["=A2+B2"]];
sheet.getRange("B3:E3").formulas = ["=1+1", "=2+2", "=3+3", "=4+4"];
sheet.getRange("G2:G5").formulas = ["=10", "=11", "=12", "=13"];
```

## Write

```ts
sheet.getRange("A1").write([
  ["Name", "Value"],
  ["A", 1],
]);

sheet.getRange("C1").write({ formulas: [["=SUM(B2:B10)"]] });
sheet.getRange("E1").write({ values: [["Literal"]] }, { overwrite: "error" });
```

## Format

```ts
range.format = {
  fill: "#f8fafc",
  font: { bold: true, color: "#0f172a" },
  numberFormat: "$#,##0.00",
  horizontalAlignment: "center",
  verticalAlignment: "middle",
  wrapText: true,
  rowHeightPx: 28,
  columnWidthPx: 120,
};

range.setNumberFormat("0.0%");
```

## Navigation

```ts
range.getCell(0, 1);
range.getRow(0);
range.getColumn(1);
range.getRange("A1");
range.getRangeByIndexes(0, 0, 1, 1);
range.getOffsetRange(1, 0);
range.getResizedRange(2, 3);
range.getResizeRange(10, 4);
range.offset(1, 0);
range.resize(10, 4);
range.getCurrentRegion();
```

## Clear, Merge, Fill, Copy

```ts
range.clear({ applyTo: "contents" });
range.clear({ applyTo: "formats" });
range.clear({ applyTo: "all" });

range.merge();
range.unmerge();

range.fillDown();
range.fillRight();
range.fillFrom(sourceRange);

range.copyFrom(sourceRange);
range.copyTo(targetRange);
```

## Inline Types

```ts
type CellValue = string | number | boolean | Date | null;

type RangeWriteOptions = {
  clear?: "contents" | "formats" | "all";
  overwrite?: "allow" | "error";
  resize?: "auto" | "none";
};

type RangeWritePayload =
  | CellValue[][]
  | CellValue[]
  | null
  | {
      values?: CellValue[][] | CellValue[] | null;
      formulas?: string[][] | string[];
      formulasR1C1?: string[][] | string[];
    };
```

## Cookbook

```ts
const data = sheet.getRange("A1:C4");
data.values = [
  ["Region", "Q1", "Q2"],
  ["North", 10, 12],
  ["South", 8, 9],
  ["Total", null, null],
];
sheet.getRange("B4:C4").formulas = [["=SUM(B2:B3)", "=SUM(C2:C3)"]];
data.format = { numberFormat: "General", wrapText: true };
```
