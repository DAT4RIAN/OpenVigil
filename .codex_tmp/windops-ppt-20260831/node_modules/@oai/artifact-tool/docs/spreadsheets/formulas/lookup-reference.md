# Lookup And Reference Formulas

Lookup and reference formulas locate values, reshape arrays, and return addresses or dimensions.

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
  `=XLOOKUP(${lookupRef},${lookupRangeRef},${returnRangeRef})`,
  `=VLOOKUP(${lookupRef},${tableRangeRef},${columnIndexRef},${exactRef})`,
  `=INDEX(${rangeRef},${rowIndexRef},${columnIndexRef})`,
  `=MATCH(${lookupRef},${lookupRangeRef},${matchModeRef})`,
  `=XMATCH(${lookupRef},${lookupRangeRef})`,
  `=FILTER(${rangeRef},${includeRangeRef})`,
  `=SORT(${rangeRef})`,
  `=UNIQUE(${rangeRef})`,
  `=TRANSPOSE(${rangeRef})`,
  `=CHOOSECOLS(${rangeRef},${columnIndexesRef})`,
];
```

## Coverage

Supported families include lookup, index/match, array filtering and sorting, stacking, wrapping, taking/dropping rows and columns, address helpers, and dimension helpers.
