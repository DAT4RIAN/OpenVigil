# Comments, Notes, And Names

Workbook comments, notes, and names are root-level facades. Sheet-scoped names
are available from `worksheet.names`.

## Comments

```ts
workbook.comments.setSelf({
  displayName: "Reviewer",
  initials: "RV",
});

const thread = workbook.comments.addThread(
  { cell: sheet.getRange("B2") },
  "Review this cell",
);

thread.addReply("Updated.");
thread.resolve();
thread.reopen();
```

Threads appear in `workbook.inspect({ kind: "thread" })` and resolve from
`th/...` anchors.

## Notes

```ts
workbook.notes;
```

Notes serialize through `workbook.toProto()` and participate in recorded
workbook state.

## Workbook-Scoped Names

```ts
workbook.names.addRange("SalesRange", "Data!$A$1:$A$3", {
  description: "Sales data",
});

const namedRange = workbook.names.getItem("SalesRange");
const range = namedRange.getRange();
namedRange.delete();
```

## Functions

```ts
workbook.names.addFunction("AddTax", {
  formula: "=LAMBDA(amount, amount * 1.1)",
  description: "Add tax",
});
```

## Sheet-Scoped Names

```ts
sheet.names.addRange("LocalRange", "Sheet1!$A$1:$A$10");
```

## Alias

```ts
workbook.definedNames === workbook.names;
```

## Cookbook

```ts
const data = workbook.worksheets.add("Data");
data.getRange("A1:A3").values = [[1], [2], [3]];
workbook.names.add("SalesRange", data.getRange("A1:A3"));

workbook.comments.setSelf({ displayName: "Reviewer", initials: "RV" });
workbook.comments.addThread({ cell: data.getRange("A1") }, "Check value.");
```
