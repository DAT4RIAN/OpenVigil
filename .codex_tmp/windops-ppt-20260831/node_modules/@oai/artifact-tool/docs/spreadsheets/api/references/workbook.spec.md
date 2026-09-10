# Workbook Facade

## Create And Load

```ts
const workbook = Workbook.create();
const [sheet1, sheet2] = workbook.worksheets.add(["Sheet1", "Sheet2"]);
const loaded = Workbook.load(proto);
const validated = Workbook.load(proto, { validate: true });
```

## Import

```ts
const fromCsv = await Workbook.fromCSV(csv, { sheetName: "Data" });
const fromMarkdown = await Workbook.fromMarkdown(markdown, {
  sheetName: "Data",
  format: true,
});

const { sheet, range } = await workbook.fromCSV(csv, { sheetName: "Data" });
```

## Root Collections

```ts
workbook.worksheets;
workbook.sheets; // alias
workbook.pivotTables;
workbook.slicers;
workbook.comments;
workbook.notes;
workbook.names;
workbook.definedNames; // alias
workbook.awareness;
```

## Theme

```ts
workbook.setColorScheme({
  name: "Workbook Theme",
  themeColors: {
    accent1: "#2563eb",
    bg1: "#ffffff",
    tx1: "#0f172a",
  },
});
const theme = workbook.theme;
```

## Recalculate And Trace

```ts
workbook.recalculate();
const trace = workbook.trace("Data!C2");
const stats = workbook.collectFormulaUsageStats();
```

## Inspect, Search, Help, Resolve

```ts
const snapshot = await workbook.inspect({ kind: "sheet,table,formula" });
const matches = workbook.findCells({
  searchTerm: "East",
  sheetId: "Revenue",
  options: { maxResults: 10, matchFormulas: true },
});
const help = workbook.help("*", {
  search: "setColorScheme|worksheet.charts.add",
  include: ["index", "examples", "notes"],
});
const target = workbook.resolve(anchorId);
```

## Record And Apply

```ts
const { result, patch, idMap, crdtUpdateV2 } = workbook.record(() => {
  const sheet = workbook.worksheets.getItem("Data");
  sheet.getRange("A1").values = [["Value"]];
  return sheet;
});

const applied = workbook.apply(patch);
```

## CRDT

```ts
workbook.hydrateCrdtFromProto();
const ready = workbook.isCollaborativeStateReady();
const unsubscribe = workbook.onCrdtUpdateV2((update, origin) => {
  send(update);
});
workbook.applyCrdtUpdateV2(remoteUpdate, { recalculate: true });
unsubscribe();
```

## Serialize

```ts
const proto = workbook.toProto();
```

## Utilities

```ts
workbook.utils.columnToLetter(1); // "A"
workbook.utils.letterToColumn("AA"); // 27
workbook.utils.toA1String(1, 1, 3, 2); // "A1:B3"
workbook.utils.fillRight([[1]], 3); // [[1, 1, 1]]
workbook.utils.fillDown([[1]], 3); // [[1], [1], [1]]
```

## Cookbook

```ts
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Data");
sheet.getRange("A1:B2").values = [
  ["Name", "Value"],
  ["A", 1],
];

const { patch } = workbook.record(() => {
  sheet.getRange("B2").values = [[2]];
});
```
