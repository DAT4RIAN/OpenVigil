# Information Formulas

Information formulas inspect value types, errors, blank cells, sheet indexes, and references.

## Formula Pattern

```ts
const formulaBlock = sheet.getRange(outputRange).write({
  formulas: formulaMatrix,
});
workbook.recalculate();
const results = formulaBlock.values;
```

## Common Shapes

```ts
const formulas = [
  `=ISBLANK(${valueRef})`,
  `=ISNUMBER(${valueRef})`,
  `=ISTEXT(${valueRef})`,
  `=ISLOGICAL(${valueRef})`,
  `=ISERROR(${valueRef})`,
  `=ISNA(${valueRef})`,
  `=TYPE(${valueRef})`,
  `=ERROR.TYPE(${valueRef})`,
  `=SHEET(${referenceRef})`,
  `=SHEETS(${referenceRef})`,
];
```

## Coverage

Supported families include type predicates, error predicates, blank checks, number/text/logical checks, N conversion, sheet lookup, and error type lookup.
