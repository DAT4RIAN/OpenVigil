# Logical Formulas

Logical formulas branch, combine conditions, handle error values, and run lambda transforms.

## Formula Pattern

```ts
const formulaBlock = sheet.getRange(outputRange).write({
  formulas: formulaMatrix,
});
workbook.recalculate();
const results = formulaBlock.values;
```

## Boolean And Branching Shapes

```ts
const formulas = [
  `=TRUE()`,
  `=FALSE()`,
  `=NA()`,
  `=AND(${conditionRef1},${conditionRef2})`,
  `=OR(${conditionRef1},${conditionRef2})`,
  `=NOT(${conditionRef})`,
  `=XOR(${conditionRef1},${conditionRef2})`,
  `=IF(${conditionRef},${trueValueRef},${falseValueRef})`,
  `=IFS(${conditionRef1},${valueRef1},${conditionRef2},${valueRef2})`,
  `=SWITCH(${valueRef},${caseRef1},${resultRef1},${defaultRef})`,
];
```

## Error Handling Shapes

```ts
const formulas = [
  `=IFERROR(${valueRef},${replacementRef})`,
  `=IFNA(${valueRef},${replacementRef})`,
];
```

## Lambda Shapes

```ts
const formulas = [
  `=BYROW(${rangeRef},LAMBDA(row,${rowExpression}))`,
  `=BYCOL(${rangeRef},LAMBDA(col,${columnExpression}))`,
];
```

## Named Lambda

```ts
workbook.names.addFunction(functionName, {
  lambda,
  description,
  parameters,
  returns,
});
```

## Coverage

Supported families include TRUE, FALSE, NA, IF, IFS, SWITCH, IFERROR, IFNA, AND, OR, NOT, XOR, LET, LAMBDA, BYROW, and BYCOL.
