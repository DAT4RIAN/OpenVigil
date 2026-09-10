# Conditional Formatting

Use `range.conditionalFormats` to add formatting rules to ranges.

## Rule Pattern

```ts
range.conditionalFormats.add(ruleType, {
  operator,
  formula,
  format,
});
```

Choose `ruleType`, `operator`, color, and style strings from the inline types below.

## Rule Inline Types

```ts
type ConditionalFormatRuleType =
  | "cellIs" | "CellValue" | "Custom" | "expression"
  | "colorScale" | "dataBar" | "iconSet"
  | "containsText" | "notContainsText" | "beginsWith" | "endsWith"
  | "containsBlanks" | "notContainsBlanks" | "containsErrors" | "notContainsErrors"
  | "duplicateValues" | "uniqueValues" | "timePeriod" | "top10" | "aboveAverage";

type CellIsOperator =
  | "greaterThan"
  | "greaterThanOrEqual"
  | "lessThan"
  | "lessThanOrEqual"
  | "equal"
  | "notEqual"
  | "between"
  | "notBetween";

type ConditionalFormatConfig =
  | { operator: CellIsOperator; formula: string | number | Array<string | number>; format?: DifferentialFormatConfig }
  | { formula: string | number; format?: DifferentialFormatConfig }
  | { colors?: ColorConfig[]; thresholds?: CfvoInput[] }
  | { color?: ColorConfig; thresholds?: CfvoInput[]; gradient?: boolean }
  | { iconSet: string; showValue?: boolean; reverse?: boolean; thresholds?: CfvoInput[] }
  | { text: string; format?: DifferentialFormatConfig }
  | { timePeriod: "yesterday" | "today" | "tomorrow" | "last7Days" | "lastWeek" | "thisWeek" | "nextWeek" | "lastMonth" | "thisMonth" | "nextMonth"; format?: DifferentialFormatConfig }
  | { rank?: number; percent?: boolean; bottom?: boolean; format?: DifferentialFormatConfig }
  | { aboveAverage?: boolean; equalAverage?: boolean; stdDev?: number; format?: DifferentialFormatConfig };

type DifferentialFormatConfig = {
  fill?: FillConfig;
  font?: { bold?: boolean; italic?: boolean; color?: ColorConfig };
  border?: RangeBordersConfig;
  numberFormat?: string;
};

type CfvoInput =
  | "min"
  | "max"
  | number
  | `${number}%`
  | { type: "min" | "max" | "num" | "percent" | "percentile"; value?: string | number };
```

## Custom Rule

```ts
range.conditionalFormats.addCustom(expression, {
  fill,
  font,
  border,
});
```

## Rule Families

Supported rule families include cell value, custom expression, text, blank/error, duplicate/unique, time period, top/bottom, above/below average, color scale, data bar, and icon set.

## Clear Rules

```ts
range.conditionalFormats.deleteAll();
```
