# shape ops

Ops in the `shape.*` namespace for `Workbook.apply`.

## Ops index

- `shape.add`: Add a shape anchored to worksheet cells.

## `shape.add`

Add a shape anchored to worksheet cells.

**Required fields**
- `op`
- `props`
- `sheet`
- `props.geometry`

**Optional fields**
- `as`
- `props.anchor`
- `props.fill`
- `props.line`

**Enums**
- `props.fill.color.value`: See [enums](../enums.md).
- `props.fill.gradientKind`: See [enums](../enums.md).
- `props.fill.pattern.type`: See [enums](../enums.md).
- `props.geometry`: See [enums](../enums.md).
- `props.line.style`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "shape.add",
  "sheet": "Shapes",
  "props": {
    "geometry": "rect",
    "anchor": {
      "from": {
        "row": 2,
        "col": 3
      },
      "extent": {
        "widthPx": 260,
        "heightPx": 140
      }
    },
    "fill": "accent1",
    "line": {
      "style": "dashed",
      "fill": "accent4",
      "width": 1
    }
  }
}
```
