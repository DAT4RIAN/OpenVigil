# Math And Trig Formulas

Math and trigonometry formulas cover arithmetic, rounding, aggregation, matrix math, random values, base conversion, and trig functions.

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
  `=SUM(${rangeRef})`,
  `=PRODUCT(${rangeRef})`,
  `=ROUND(${valueRef},${digits})`,
  `=POWER(${valueRef},${power})`,
  `=MOD(${valueRef},${divisor})`,
  `=SIN(${angleRef})`,
  `=COS(${angleRef})`,
  `=TAN(${angleRef})`,
  `=MMULT(${matrixARef},${matrixBRef})`,
];
```

## Coverage

Supported families include aggregate math, rounding, logarithms, powers, matrix functions, random generators, trig, hyperbolic trig, Roman/base conversion, subtotaling, and compatibility variants.
