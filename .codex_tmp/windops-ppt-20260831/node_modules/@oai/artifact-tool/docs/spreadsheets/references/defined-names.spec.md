## Defined names (`workbook.names`, `worksheet.names`)

Use defined names for reusable ranges and workbook functions.

### Named ranges

Workbook-scoped named range:

```ts
const data = workbook.worksheets.add("Data");
data.getRange("A1:A3").values = [[1], [2], [3]];

workbook.names.addRange("SalesRange", "Data!$A$1:$A$3", {
  description: "Input sales data",
});

data.getRange("B1").formulas = [["=SUM(SalesRange)"]];
workbook.recalculate();
```

Sheet-scoped named range:

```ts
const sheet1 = workbook.worksheets.add("Sheet1");
sheet1.names.addRange("LocalRange", "Sheet1!$A$1:$A$10");

sheet1.getRange("B1").formulas = [["=SUM(LocalRange)"]];
workbook.recalculate();
```

### Named functions (LAMBDA)

```ts
workbook.names.addFunction("AddTax", {
  lambda: "LAMBDA(price, tax, price*(1+tax))", // export may auto-prefix "="
  description: "Adds tax to a price",
  parameters: [
    { name: "price", description: "Base price" },
    { name: "tax", description: "Tax rate (e.g. 0.1)" },
  ],
  returns: "Taxed price",
});
```
