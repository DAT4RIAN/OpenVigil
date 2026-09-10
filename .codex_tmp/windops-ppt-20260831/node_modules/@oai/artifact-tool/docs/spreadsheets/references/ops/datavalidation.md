# datavalidation ops

Ops in the `datavalidation.*` namespace for `Workbook.apply`.

## Ops index

- `datavalidation.set`: Set data validation rules for a range.

## `datavalidation.set`

Set data validation rules for a range.

**Required fields**
- `op`
- `props`
- `target`
- `props.rule`

**Optional fields**
- `props.errorAlert`
- `props.ignoreBlanks`
- `props.inCellDropDown`
- `props.prompt`

**Enums**
- `props.errorAlert.style`: See [enums](../enums.md).
- `props.rule.operator`: See [enums](../enums.md).
- `props.rule.type`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "datavalidation.set",
  "target": {
    "sheet": "Validation",
    "range": "B2:B10"
  },
  "props": {
    "rule": {
      "type": "list",
      "values": [
        "Dog",
        "Cat",
        "Bat"
      ]
    },
    "prompt": {
      "title": "Pick an animal",
      "show": true
    },
    "errorAlert": {
      "title": "Invalid choice",
      "show": true
    },
    "ignoreBlanks": true,
    "inCellDropDown": true
  }
}
```
