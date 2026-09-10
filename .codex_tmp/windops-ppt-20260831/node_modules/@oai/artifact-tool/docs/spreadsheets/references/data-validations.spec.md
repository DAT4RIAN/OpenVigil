# Data Validations

Use range-level or worksheet-level data validation config.

## Range Assignment

```ts
range.dataValidation = validationConfig;
```

## Rule Config

```ts
range.dataValidation.rule = {
  type,
  formula1,
  formula2,
  values,
  operator,
};
range.dataValidation.prompt = promptConfig;
range.dataValidation.errorAlert = errorAlertConfig;
range.dataValidation.ignoreBlanks = ignoreBlanks;
range.dataValidation.inCellDropDown = inCellDropDown;
```

## Validation Inline Types

```ts
type DataValidationRule = {
  type: "none" | "whole" | "decimal" | "list" | "date" | "time" | "textLength" | "custom";
  operator?:
    | "between"
    | "notBetween"
    | "equal"
    | "notEqual"
    | "lessThan"
    | "lessThanOrEqual"
    | "greaterThan"
    | "greaterThanOrEqual";
  formula1?: string | number;
  formula2?: string | number;
  values?: string[];
};

type ValidationConfig = {
  rule?: DataValidationRule | null;
  prompt?: { title?: string; message?: string; show?: boolean } | null;
  errorAlert?: {
    title?: string;
    message?: string;
    style?: "stop" | "warning" | "information";
    show?: boolean;
  } | null;
  ignoreBlanks?: boolean;
  inCellDropDown?: boolean;
};
```

## Collection Add

```ts
sheet.dataValidations.add({
  range,
  rule,
  prompt,
  errorAlert,
  ignoreBlanks,
  inCellDropDown,
});
```

Validation type, operator, and error style values are the strings listed above.
