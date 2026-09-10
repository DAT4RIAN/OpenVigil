# Financial Formulas

Financial formulas cover loans, rates, cash flows, depreciation, securities, treasury bills, and coupon calculations.

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
  `=PMT(${rateRef},${periodsRef},${presentValueRef})`,
  `=PV(${rateRef},${periodsRef},${paymentRef})`,
  `=FV(${rateRef},${periodsRef},${paymentRef})`,
  `=NPV(${rateRef},${cashFlowRangeRef})`,
  `=IRR(${cashFlowRangeRef})`,
  `=XNPV(${rateRef},${cashFlowRangeRef},${dateRangeRef})`,
  `=XIRR(${cashFlowRangeRef},${dateRangeRef})`,
  `=RATE(${periodsRef},${paymentRef},${presentValueRef})`,
];
```

## Coverage

Supported families include payment and present/future value, net present value, return rate, depreciation, discount/yield, coupon date math, accrued interest, treasury bills, and compatibility variants.
