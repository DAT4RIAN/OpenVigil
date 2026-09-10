# conditionalformat ops

Ops in the `conditionalformat.*` namespace for `Workbook.apply`.

## Ops index

- `conditionalformat.add`: Add a conditional formatting rule to a range.

## `conditionalformat.add`

Add a conditional formatting rule to a range.

**Required fields**
- `op`
- `props`
- `target`
- `props.rule`

**Optional fields**
- (none)

**Enums**
- `props.rule.format.fill.color.value`: See [enums](../enums.md).
- `props.rule.format.fill.gradientKind`: See [enums](../enums.md).
- `props.rule.format.fill.pattern.type`: See [enums](../enums.md).
- `props.rule.operator`: See [enums](../enums.md).
- `props.rule.thresholds[].type`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "conditionalformat.add",
  "target": {
    "sheet": "CF",
    "range": "A1:A3"
  },
  "props": {
    "rule": {
      "type": "cellIs",
      "operator": "greaterThan",
      "formula": 3,
      "format": {
        "fill": "accent2",
        "font": {
          "bold": true,
          "color": "accent3"
        }
      }
    }
  }
}
```
