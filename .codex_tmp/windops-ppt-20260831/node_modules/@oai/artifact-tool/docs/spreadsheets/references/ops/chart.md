# chart ops

Ops in the `chart.*` namespace for `Workbook.apply`.

## Ops index

- `chart.add`: Add a chart anchored to worksheet cells.

## `chart.add`

Add a chart anchored to worksheet cells.

**Required fields**
- `op`
- `props`
- `sheet`
- `props.anchor`
- `props.chartType`

**Optional fields**
- `as`
- `props.categories`
- `props.dataLabels`
- `props.displayBlanksAs`
- `props.hasLegend`
- `props.legend`
- `props.series`
- `props.title`

**Enums**
- `props.chartType`: See [enums](../enums.md).
- `props.displayBlanksAs`: See [enums](../enums.md).
- `props.legend.position`: See [enums](../enums.md).
- `props.series[].marker.symbol`: See [enums](../enums.md).
- `props.series[].stroke.fill.color.value`: See [enums](../enums.md).
- `props.series[].stroke.fill.gradientKind`: See [enums](../enums.md).
- `props.series[].stroke.fill.pattern.type`: See [enums](../enums.md).
- `props.series[].stroke.style`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "chart.add",
  "sheet": "Charts",
  "props": {
    "chartType": "line",
    "anchor": {
      "from": {
        "row": 1,
        "col": 1,
        "rowOffsetPx": 4,
        "colOffsetPx": 8
      },
      "extent": {
        "widthPx": 520,
        "heightPx": 280
      }
    },
    "title": "Milky Way Star Birth Rate",
    "categories": [
      "2020",
      "2021",
      "2022",
      "2023"
    ],
    "series": [
      {
        "name": "Milky Way",
        "values": [
          1.8,
          1.9,
          2,
          2.2
        ]
      }
    ],
    "hasLegend": true,
    "legend": {
      "position": "bottom"
    },
    "dataLabels": {
      "showValue": true
    }
  }
}
```
