# Charts And Drawings

Worksheets expose drawing collections for charts, images, and shapes.

## Charts

```ts
const chart = sheet.charts.add("bar", {
  from: { row: 1, col: 4 },
  extent: { widthPx: 420, heightPx: 260 },
});
chart.title = "Values";
chart.categories = ["A", "B", "C"];
const series = chart.series.add("Value");
series.values = [3, 5, 8];
series.categories = chart.categories;
```

Charts can be resolved from inspect anchors:

```ts
const chart = workbook.resolve("ch/<chartId>");
```

## Chart To Image

```ts
const result = await workbook.chartToImage(0, chart.id);
```

## Images

```ts
const image = sheet.images.add({
  blob: imageBytes,
  contentType: "image/png",
  anchor: {
    from: { row: 1, col: 2 },
    extent: { widthPx: 240, heightPx: 160 },
  },
});

image.bytes;
image.contentType;
image.prompt;
image.uri;
```

## Shapes

```ts
const shape = sheet.shapes.add({
  geometry: "rect",
  anchor: {
    from: { row: 2, col: 3 },
    extent: { widthPx: 240, heightPx: 80 },
  },
  fill: "#f8fafc",
  line: { fill: "#334155", width: 1 },
});
shape.text = "Label";
```

## Sparklines

```ts
sheet.sparklineGroups.add({
  targetRange: sheet.getRange("D2:D10"),
  sourceData: sheet.getRange("B2:C10"),
  type: "line",
});
```

`sheet.sparklines` is a deprecated alias for `sheet.sparklineGroups`.

## Auto Layout

```ts
sheet.autoLayoutDrawings(sheet.charts.items, {
  direction: "vertical",
  frame: { startCell: "E2", width: 800, height: 1200 },
  gap: 16,
  padding: 24,
});
```

## Cookbook

```ts
sheet.getRange("A1:B4").values = [
  ["Name", "Value"],
  ["A", 3],
  ["B", 5],
  ["C", 8],
];

sheet.charts.add("bar", {
  from: { row: 1, col: 4 },
  extent: { widthPx: 420, heightPx: 260 },
});
```
