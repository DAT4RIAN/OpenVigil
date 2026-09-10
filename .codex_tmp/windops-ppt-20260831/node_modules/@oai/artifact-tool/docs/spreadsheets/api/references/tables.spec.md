# Tables

Worksheet tables are created from an existing range and can edit rows, headers,
data body ranges, names, style, and totals.

## Add Table

```ts
const sheet = workbook.worksheets.add("Inventory");
sheet.getRange("A1:C3").values = [
  ["SKU", "Color", "Stock"],
  ["100-001", "Black", 15],
  ["100-002", "Sage", 40],
];

const table = sheet.tables.add("A1:C3", true, "InventoryTable");
```

## Read

```ts
sheet.tables.items;
sheet.tables.getItem("InventoryTable");
sheet.tables.getItemAt(0);

table.name;
table.address;
table.getRange();
table.getHeaderRowRange();
table.getDataRows();
```

## Add Rows

```ts
table.rows.add(null, [["100-003", "Denim", 12]]);
```

## Headerless Table

```ts
sheet.getRange("A1:B3").values = [
  ["West", 12],
  ["East", 9],
  ["South", 15],
];
sheet.tables.add("A1:B3", false, "HeaderlessTable");
```

## Recorded Table Edit

```ts
const { patch } = workbook.record(() => {
  const table = sheet.tables.add("A1:C3", true, "InventoryTable");
  table.rows.add(null, [["100-003", "Denim", 12]]);
});
```

The recorded patch uses `table.add` followed by row/column/table operations for
subsequent edits.

## Cookbook

```ts
const table = sheet.tables.add("A1:D5", true, "DataTable");
table.rows.add(null, [["West", "Ava", 12, 14]]);

sheet.getRange(table.address).format = {
  font: { name: "Aptos" },
  wrapText: true,
};
```
