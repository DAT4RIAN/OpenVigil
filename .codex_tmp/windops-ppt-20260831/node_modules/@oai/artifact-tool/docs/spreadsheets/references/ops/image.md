# image ops

Ops in the `image.*` namespace for `Workbook.apply`.

## Ops index

- `image.add`: Add an image anchored to worksheet cells.

## `image.add`

Add an image anchored to worksheet cells.

**Required fields**
- `op`
- `props`
- `sheet`

**Optional fields**
- `as`
- `props.alt`
- `props.anchor`
- `props.contentType`
- `props.dataUrl`
- `props.path`
- `props.prompt`
- `props.uri`

**Examples**
```json
{
  "op": "image.add",
  "sheet": "Images",
  "props": {
    "dataUrl": "data:image/png;base64,...",
    "anchor": {
      "from": {
        "row": 1,
        "col": 2
      },
      "extent": {
        "widthPx": 160,
        "heightPx": 120
      }
    }
  }
}
```
