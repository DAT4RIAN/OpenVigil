# Statistical Formulas

Statistical formulas summarize, rank, distribute, correlate, and forecast values.

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
  `=AVERAGE(${rangeRef})`,
  `=MEDIAN(${rangeRef})`,
  `=STDEV.S(${rangeRef})`,
  `=VAR.P(${rangeRef})`,
  `=QUARTILE(${rangeRef},${quartileIndex})`,
  `=CORREL(${xRangeRef},${yRangeRef})`,
  `=FORECAST.LINEAR(${xRef},${knownYRangeRef},${knownXRangeRef})`,
  `=FORECAST.ETS(${targetDateRef},${valuesRangeRef},${timelineRangeRef})`,
];
```

## Coverage

Supported families include averages, counts, rank and percentile functions, variance and standard deviation, distributions, regression, covariance/correlation, forecasting, and compatibility names.
