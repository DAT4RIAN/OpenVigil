# Formatting, Validation, And Theme

Use range formatting for cell style, worksheet collections for validation and
conditional formatting, and `workbook.setColorScheme` for workbook theme colors.

## Range Format

```ts
range.format = {
  fill: "#f8fafc",
  font: {
    name: "Aptos",
    bold: true,
    color: "#0f172a",
    size: 11,
  },
  borders: {
    bottom: { style: "thin", color: "#94a3b8" },
  },
  numberFormat: "$#,##0.00",
  horizontalAlignment: "center",
  verticalAlignment: "middle",
  wrapText: true,
  rowHeightPx: 28,
  columnWidthPx: 120,
};
```

## Number Format

```ts
range.setNumberFormat("0.0%");
```

## Conditional Formatting

```ts
sheet.getRange("B2:B10").conditionalFormats.add("cellIs", {
  operator: "greaterThan",
  formula: 10,
  format: {
    fill: "#dcfce7",
    font: { bold: true, color: "#166534" },
  },
});
```

Use `workbook.getConditionalFormattingRenderCache(sheet.name)` when a renderer
needs evaluated conditional-format metadata.

## Data Validation

```ts
sheet.getRange("A2:A10").dataValidation = {
  list: {
    source: ["Open", "Closed"],
    inCellDropDown: true,
  },
  allowBlank: true,
};
```

The range setter accepts Office-style list assignments or validation config
objects.

## Freeze Panes

```ts
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(1);
sheet.freezePanes.unfreeze();
```

## Theme

```ts
workbook.setColorScheme({
  name: "Workbook Theme",
  themeColors: {
    accent1: "#2563eb",
    accent2: "#0f766e",
    bg1: "#ffffff",
    tx1: "#0f172a",
  },
});
```

## Cookbook

```ts
const header = sheet.getRange("A1:C1");
header.format = {
  fill: "#0f172a",
  font: { bold: true, color: "#ffffff" },
  horizontalAlignment: "center",
};
sheet.freezePanes.freezeRows(1);
```
