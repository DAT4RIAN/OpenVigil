## Workbook API

Use `Workbook` to create, edit, recalculate, and export spreadsheet artifacts.

### Quick start

```ts
import { Workbook } from "@oai/artifact-tool";

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Sheet1");

sheet.getRange("A1").values = [["Hello"]];
workbook.recalculate();

const proto = workbook.toProto();
```

### Workbook lifecycle

- `Workbook.create()` — start a new workbook.
- `new Workbook(proto)` — hydrate from an existing artifact, edit, then `toProto()` again.
- `workbook.recalculate()` — evaluate formulas.
- `workbook.toProto()` — produce the protobuf-like JSON artifact.

### Worksheets

- `workbook.worksheets.add(name)` — add (or return) a worksheet by name.
- `workbook.worksheets.getItem(name | index)` — fetch by name or index.
- `workbook.worksheets.getActiveWorksheet()` — fetch the active worksheet.
- `workbook.worksheets.count` — number of sheets.
