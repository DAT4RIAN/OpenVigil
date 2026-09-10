# Text Formulas

Text formulas transform, search, split, join, format, and extract strings.

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
  `=TEXT(${valueRef},${formatRef})`,
  `=CONCAT(${rangeRef})`,
  `=TEXTJOIN(${delimiterRef},${ignoreEmptyRef},${rangeRef})`,
  `=LEFT(${textRef},${countRef})`,
  `=RIGHT(${textRef},${countRef})`,
  `=MID(${textRef},${startRef},${countRef})`,
  `=FIND(${needleRef},${textRef})`,
  `=SEARCH(${needleRef},${textRef})`,
  `=SUBSTITUTE(${textRef},${oldTextRef},${newTextRef})`,
  `=TEXTSPLIT(${textRef},${delimiterRef})`,
];
```

## Coverage

Supported families include length, casing, replacement, extraction, joining, splitting, number-to-text formatting, Unicode helpers, and regex helpers.
