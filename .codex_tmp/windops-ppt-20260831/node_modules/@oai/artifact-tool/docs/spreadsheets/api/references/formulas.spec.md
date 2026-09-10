# Formulas

Workbook formulas are stored on ranges and evaluated by `workbook.recalculate()`.

## Assign Formulas

```ts
sheet.getRange("A1:B2").values = [
  [2, 3],
  [5, 7],
];

sheet.getRange("C1:C2").formulas = [["=A1+B1"], ["=A2+B2"]];
workbook.recalculate();
```

Strings starting with `=` assigned through `values` are treated as formulas.
Use a leading apostrophe for literal strings:

```ts
sheet.getRange("C1").values = [["=SUM(A1:B1)"]];
sheet.getRange("D1").values = [["'=SUM(A1:B1)"]];
```

## Dynamic Arrays And Spill

```ts
sheet.getRange("E1").formulas = [["=SEQUENCE(3, 2)"]];
workbook.recalculate();
```

Spill projection cells are not directly editable formula anchors.

## Trace

```ts
const trace = workbook.trace("Sheet1!C1");
```

`trace` recalculates first and returns a dependency tree for the target cell or
`null` for an invalid reference.

## Formula Usage Stats

```ts
const stats = workbook.collectFormulaUsageStats();
```

## Names

```ts
workbook.names.addRange("SalesRange", "Data!$A$1:$A$3", {
  description: "Sales data",
});

workbook.names.addFunction("AddTax", {
  formula: "=LAMBDA(amount, amount * 1.1)",
  description: "Add tax",
});

sheet.names.addRange("LocalRange", "Sheet1!$A$1:$A$10");
```

## Cookbook

```ts
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Calc");
sheet.getRange("A1:A3").values = [[1], [2], [3]];
sheet.getRange("B1").formulas = [["=SUM(A1:A3)"]];
workbook.recalculate();

const trace = workbook.trace("Calc!B1");
```
