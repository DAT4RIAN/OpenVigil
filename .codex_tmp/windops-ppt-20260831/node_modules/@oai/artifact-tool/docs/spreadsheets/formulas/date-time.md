# Date And Time Formulas

Date and time formulas create, parse, extract, and compare serial dates and times.

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
  `=DATE(${yearRef},${monthRef},${dayRef})`,
  `=TIME(${hourRef},${minuteRef},${secondRef})`,
  `=DATEVALUE(${textRef})`,
  `=TIMEVALUE(${textRef})`,
  `=YEAR(${dateRef})`,
  `=MONTH(${dateRef})`,
  `=DAY(${dateRef})`,
  `=WEEKDAY(${dateRef})`,
  `=WORKDAY(${startDateRef},${daysRef})`,
  `=NETWORKDAYS(${startDateRef},${endDateRef})`,
];
```

## Coverage

Supported families include date/time construction, extraction, workday and network-day calculations, year fractions, week numbers, today/current time, and end-of-month helpers.
