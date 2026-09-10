# Range Formatting

Use `range.format` to style cells with fills, fonts, borders, number formats, sizing, and alignment.

## Shared Color And Fill Inline Types

```ts
type ThemeColorName =
  | "accent1" | "accent2" | "accent3" | "accent4" | "accent5" | "accent6"
  | "bg1" | "bg2" | "tx1" | "tx2" | "dk1" | "lt1" | "dk2" | "lt2"
  | "hlink" | "folHlink";

type ColorConfig =
  | string
  | { type: "rgb"; value: string; transform?: { opacity?: number; lighten?: number; darken?: number } }
  | { type: "theme"; value: ThemeColorName; transform?: { opacity?: number; lighten?: number; darken?: number } };

type FillConfig =
  | string
  | { type: "none" }
  | { type: "solid"; color: ColorConfig }
  | { type: "gradient"; stops: Array<{ offset: number; color: ColorConfig }>; angleDeg?: number; gradientKind?: "linear" | "path" };
```

## Grouped Format

```ts
range.format = {
  fill,
  font,
  horizontalAlignment,
  verticalAlignment,
  wrapText,
  borders,
  numberFormat,
};
```

## Format Inline Types

```ts
type RangeFormatConfig = {
  fill?: FillConfig | null;
  font?: RangeFontConfig | null;
  borders?: RangeBordersConfig;
  numberFormat?: string | string[][];
  wrapText?: boolean;
  horizontalAlignment?:
    | "general"
    | "left"
    | "center"
    | "right"
    | "fill"
    | "justify"
    | "centerAcrossSelection"
    | "distributed";
  verticalAlignment?: "top" | "middle" | "bottom" | "center";
  rowHeight?: number; // points
  rowHeightPx?: number;
  columnWidth?: number; // Excel width units
  columnWidthPx?: number;
};

type RangeFontConfig = {
  bold?: boolean;
  italic?: boolean;
  size?: number;
  name?: string;
  color?: ColorConfig;
};
```

## Sizing

```ts
range.format.rowHeightPx = rowHeightPx;
range.format.columnWidthPx = columnWidthPx;
```

Pixel sizing is the preferred surface for layout-sensitive work. Point row heights and Excel-width column widths are also available through `rowHeight` and `columnWidth`.

## Borders

```ts
range.format.borders = {
  preset,
  style,
  color,
};
```

Use the border preset strings below. Border style strings are Excel/OpenXML-style names such as `"thin"`, `"medium"`, `"thick"`, `"dashed"`, and `"dotted"`.

## Border Inline Type

```ts
type RangeBordersConfig =
  | {
      preset: "none" | "outside" | "inside" | "all" | "doubleBottom";
      style?: string; // common: "thin", "medium", "thick", "dashed", "dotted"
      color?: ColorConfig;
    }
  | {
      top?: BorderLineInput;
      bottom?: BorderLineInput;
      left?: BorderLineInput;
      right?: BorderLineInput;
      inside?: BorderLineInput;
      insideHorizontal?: BorderLineInput;
      insideVertical?: BorderLineInput;
      diagonalUp?: BorderLineInput;
      diagonalDown?: BorderLineInput;
    };

type BorderLineInput = {
  style?: string;
  color?: ColorConfig;
  weight?: number;
};
```
