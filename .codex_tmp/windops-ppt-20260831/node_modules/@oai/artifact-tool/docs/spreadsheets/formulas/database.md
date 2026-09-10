# Database Formulas

Database formulas aggregate rows from headered ranges using criteria ranges.

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
  `=DSUM(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DCOUNT(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DCOUNTA(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DAVERAGE(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DMIN(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DMAX(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DSTDEV(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
  `=DVAR(${databaseRangeRef},${fieldRef},${criteriaRangeRef})`,
];
```

## Coverage

Supported families include database sum, count, average, min, max, product, standard deviation, variance, and single-value lookup.
