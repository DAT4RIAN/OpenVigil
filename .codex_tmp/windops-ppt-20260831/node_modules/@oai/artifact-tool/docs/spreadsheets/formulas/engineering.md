# Engineering Formulas

Engineering formulas cover complex numbers, Bessel functions, bitwise operations, unit conversion, and number-base conversion.

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
  `=COMPLEX(${realRef},${imaginaryRef})`,
  `=IMSUM(${complexRangeRef})`,
  `=IMPRODUCT(${complexRangeRef})`,
  `=IMABS(${complexRef})`,
  `=CONVERT(${valueRef},${fromUnitRef},${toUnitRef})`,
  `=BIN2DEC(${binaryRef})`,
  `=DEC2HEX(${decimalRef})`,
  `=BITAND(${valueRef1},${valueRef2})`,
  `=BITOR(${valueRef1},${valueRef2})`,
  `=BESSELJ(${valueRef},${orderRef})`,
];
```

## Coverage

Supported families include complex arithmetic, bitwise functions, base conversions, Bessel functions, error functions, delta/threshold helpers, and unit conversions.
