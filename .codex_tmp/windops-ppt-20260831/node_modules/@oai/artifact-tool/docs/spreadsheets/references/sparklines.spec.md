# Sparklines

Use `sheet.sparklineGroups` for worksheet sparkline groups.

## Add Group

```ts
const group = sheet.sparklineGroups.add({
  type,
  targetRange,
  sourceData,
  dateAxisRange,
  seriesColor,
  negativeColor,
  markers,
  axis,
  lineWeight,
  displayEmptyCellsAs,
  displayHidden,
});
```

Sparkline type is a string. Empty-cell display mode and axis min/max modes are proto enum numbers on the current facade; inspect nearby tests before setting them directly.

## Sparkline Inline Type

```ts
type SparklineConfig = {
  type: "line" | "column" | "stacked";
  targetRange: Range | string;
  sourceData: Range | string;
  dateAxisRange?: Range | string;
  lineWeight?: number;
  displayHidden?: boolean;
  seriesColor?: ColorConfig;
  negativeColor?: ColorConfig;
  axisColor?: ColorConfig;
  markersColor?: ColorConfig;
  firstMarkerColor?: ColorConfig;
  lastMarkerColor?: ColorConfig;
  highMarkerColor?: ColorConfig;
  lowMarkerColor?: ColorConfig;
  markers?: SparklineMarkersOptions;
  axis?: SparklineAxisOptions;
};

type SparklineMarkersOptions = {
  show?: boolean;
  high?: boolean;
  low?: boolean;
  first?: boolean;
  last?: boolean;
  negative?: boolean;
};

type SparklineAxisOptions = {
  showAxis?: boolean;
  manualMin?: number;
  manualMax?: number;
  rightToLeft?: boolean;
};
```

## Range Alias

```ts
const group = targetRange.sparklines.add(type, sourceRange, sparklineConfig);
```

## Edit And Delete

```ts
group.seriesColor = colorConfig;
group.markers = markerConfig;
group.axis = axisConfig;
group.delete();
sheet.sparklineGroups.deleteAll();
```
