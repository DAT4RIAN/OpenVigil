## Ranges API

Use `Worksheet.getRange(address)` to read and write grid data using Excel A1 notation.

### Values

`range.values` is a 2D array of `CellValue`:

- `string | number | boolean | Date | null`
- `null` represents an empty cell

```ts
sheet.getRange("A1:C1").values = [["Date", "Dog", "Resting HR (bpm)"]];
sheet.getRange("A2:C4").values = [
  ["2025-01-02", "Nova", 58],
  ["2025-01-03", "Nova", 61],
  ["2025-01-03", "Comet", 72],
];
```

### Checkboxes

Assign boolean values to create Excel checkbox cells. Use `range.values = null` to clear a range and remove the checkbox control.

```ts
sheet.getRange("A1").values = [[true]];
sheet.getRange("A2").values = [[false]];

sheet.getRange("A1:A2").values = null;
```

### Merged cells

Use `range.merge()` to merge a rectangular range into a single cell region, and `range.unmerge()` to remove merges that intersect the range.

```ts
// Merge a header across columns
sheet.getRange("B1:H1").merge();

// Merge across rows (one merge per row, like Excel “Merge Across”)
sheet.getRange("B2:H4").merge(true);

// Remove merges touching the range
sheet.getRange("B1:H4").unmerge();
```

### Formulas

`range.formulas` is a 2D array of strings. Call `workbook.recalculate()` before reading computed `values`.

```ts
sheet.getRange("E1").values = [["Average HR"]];
sheet.getRange("E2").formulas = [[`=AVERAGE(C2:C4)`]];

workbook.recalculate();
const average = sheet.getRange("E2").values[0]?.[0];
```

### A1 addressing conventions

Supported addressing patterns include:

- `A1` (single cell)
- `A1:C10` (rectangle)
- `A:A` (entire column)
- `2:2` (entire row)

In formulas, quote sheet names that contain spaces/punctuation: `'Cost Summary'!A1`.
