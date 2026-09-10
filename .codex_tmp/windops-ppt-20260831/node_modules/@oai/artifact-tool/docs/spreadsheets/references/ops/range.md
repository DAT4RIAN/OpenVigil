# range ops

Ops in the `range.*` namespace for `Workbook.apply`.

## Ops index

- `range.format.set`: Apply formatting to a range.
- `range.formulas.set`: Set formulas for a range.
- `range.merge`: Merge cells in a range.
- `range.unmerge`: Unmerge any merged blocks intersecting the range.
- `range.values.set`: Set cell values for a range.

## `range.format.set`

Apply formatting to a range.

**Required fields**
- `op`
- `props`
- `target`

**Optional fields**
- `props.borders`
- `props.columnWidth`
- `props.fill`
- `props.font`
- `props.horizontalAlignment`
- `props.numberFormat`
- `props.rowHeight`
- `props.verticalAlignment`
- `props.wrapText`

**Enums**
- `props.borders.preset`: See [enums](../enums.md).
- `props.fill.color.value`: See [enums](../enums.md).
- `props.fill.gradientKind`: See [enums](../enums.md).
- `props.fill.pattern.type`: See [enums](../enums.md).
- `props.horizontalAlignment`: See [enums](../enums.md).
- `props.verticalAlignment`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "range.format.set",
  "target": {
    "sheet": "Scorecard",
    "range": "A1:C1"
  },
  "props": {
    "fill": "accent1",
    "font": {
      "bold": true,
      "size": 14
    },
    "horizontalAlignment": "Center"
  }
}
```

## `range.formulas.set`

Set formulas for a range.

**Required fields**
- `formulas`
- `op`
- `target`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "range.formulas.set",
  "target": {
    "sheet": "Inventory",
    "range": "E2"
  },
  "formulas": [
    [
      "=AVERAGE(C2:C4)"
    ]
  ]
}
```

## `range.merge`

Merge cells in a range.

**Required fields**
- `op`
- `target`

**Optional fields**
- `across`

**Examples**
```json
{
  "op": "range.merge",
  "target": {
    "sheet": "Report",
    "range": "A1:D1"
  }
}
```

## `range.unmerge`

Unmerge any merged blocks intersecting the range.

**Required fields**
- `op`
- `target`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "range.unmerge",
  "target": {
    "sheet": "Report",
    "range": "A1:D4"
  }
}
```

## `range.values.set`

Set cell values for a range.

**Required fields**
- `op`
- `target`
- `values`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "range.values.set",
  "target": {
    "sheet": "Inventory",
    "range": "A1:C2"
  },
  "values": [
    [
      "SKU",
      "Color",
      "Stock"
    ],
    [
      "100-001",
      "Black",
      15
    ]
  ]
}
```
