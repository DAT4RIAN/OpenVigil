# table ops

Ops in the `table.*` namespace for `Workbook.apply`.

## Ops index

- `table.add`: Create a table from a range.
- `table.rows.add`: Append or insert rows into a table.

## `table.add`

Create a table from a range.

**Required fields**
- `op`
- `props`
- `props.range`

**Optional fields**
- `as`
- `props.hasHeaders`
- `props.name`

**Examples**
```json
{
  "op": "table.add",
  "props": {
    "range": {
      "sheet": "Inventory",
      "range": "A1:C3"
    },
    "hasHeaders": true,
    "name": "InventoryTable"
  }
}
```

## `table.rows.add`

Append or insert rows into a table.

**Required fields**
- `op`
- `props`
- `target`
- `props.values`

**Optional fields**
- `props.index`

**Examples**
```json
{
  "op": "table.rows.add",
  "target": {
    "name": "InventoryTable",
    "sheet": "Inventory"
  },
  "props": {
    "index": null,
    "values": [
      [
        "100-003",
        "Denim",
        12
      ]
    ]
  }
}
```
