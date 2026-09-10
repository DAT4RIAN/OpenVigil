# Worksheet Tables

Use `sheet.tables` to add and edit Excel-style tables.

## Add Table

```ts
const table = sheet.tables.add(rangeAddress, hasHeaders, tableName);
```

## Add Inline Type

```ts
type WorksheetTableAddArgs = {
  range: string | Range;
  hasHeaders?: boolean;
  name?: string;
};
```

## Rows And Values

```ts
table.rows.add(rowIndex, rowValues);
table.getRange().values = tableValues;
```

## Table Style

```ts
table.name = tableName;
table.showTotals = showTotals;
table.style = tableStyleName;
table.styleOptions = tableStyleOptions;
```

## Table Inline Type

```ts
type WorkbookTableStyleOptions = {
  showHeaders?: boolean;
  showTotals?: boolean;
  bandedRows?: boolean;
  bandedColumns?: boolean;
  firstColumn?: boolean;
  lastColumn?: boolean;
};
```

## Delete

```ts
table.delete();
sheet.tables.deleteAll();
```
