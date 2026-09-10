# Worksheet Images

Use `sheet.images.add(...)` to attach images to cell-grid anchors.

## Add Image

```ts
const image = sheet.images.add({
  path,
  blob,
  dataUrl,
  uri,
  prompt,
  alt,
  anchor,
});

const icon = sheet.images.add({
  svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#2563eb"/></svg>',
  anchor: { from: { row: 1, col: 5 }, extent: { widthPx: 48, heightPx: 48 } },
});
```

## Image Inline Types

```ts
type WorksheetImageConfig = ImageSource & {
  alt?: string;
  contentType?: string;
  anchor?: DrawingAnchorConfig;
};

type ImageSource =
  | { path: string }
  | { svg: string }
  | { blob: ArrayBuffer }
  | { dataUrl: string }
  | { uri: string }
  | { prompt: string };
```

## Anchor

```ts
const anchor = {
  from,
  to,
  extent,
};
```

`from`, `to`, and `extent` use the same zero-based anchor and pixel extent shapes as worksheet charts and shapes.

## Anchor Inline Type

```ts
type DrawingAnchorConfig = {
  from: AnchorInput;
  to?: AnchorInput;
  extent?: {
    widthPx?: number;
    heightPx?: number;
    widthEmu?: number;
    heightEmu?: number;
  };
};

type AnchorInput = {
  row: number;
  col: number;
  rowOffsetPx?: number;
  colOffsetPx?: number;
  rowOffsetEmu?: number;
  colOffsetEmu?: number;
};
```

## Edit

```ts
image.anchor = anchor;
image.alt = altText;
image.replace(sourceConfig);
image.delete();
```
