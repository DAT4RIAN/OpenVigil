# sparkline ops

Ops in the `sparkline.*` namespace for `Workbook.apply`.

## Ops index

- `sparkline.add`: Create a sparkline group backed by source data.

## `sparkline.add`

Create a sparkline group backed by source data.

**Required fields**
- `op`
- `props`
- `props.sourceData`
- `props.targetRange`
- `props.type`

**Optional fields**
- `props.axis`
- `props.axisColor`
- `props.dateAxisRange`
- `props.displayEmptyCellsAs`
- `props.displayHidden`
- `props.firstMarkerColor`
- `props.highMarkerColor`
- `props.lastMarkerColor`
- `props.lineWeight`
- `props.lowMarkerColor`
- `props.markers`
- `props.markersColor`
- `props.negativeColor`
- `props.seriesColor`

**Enums**
- `props.axis.maxMode`: See [enums](../enums.md).
- `props.axis.minMode`: See [enums](../enums.md).
- `props.displayEmptyCellsAs`: See [enums](../enums.md).
- `props.seriesColor.value`: See [enums](../enums.md).
- `props.type`: See [enums](../enums.md).

**Examples**
```json
{
  "op": "sparkline.add",
  "props": {
    "type": "line",
    "targetRange": {
      "sheet": "KPIs",
      "range": "H2:H3"
    },
    "sourceData": {
      "sheet": "KPIs",
      "range": "B2:G3"
    },
    "dateAxisRange": {
      "sheet": "KPIs",
      "range": "B1:G1"
    },
    "seriesColor": "accent1",
    "markers": {
      "show": true,
      "high": true,
      "low": true
    }
  }
}
```
