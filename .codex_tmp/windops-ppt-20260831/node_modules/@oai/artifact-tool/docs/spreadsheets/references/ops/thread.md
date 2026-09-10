# thread ops

Ops in the `thread.*` namespace for `Workbook.apply`.

## Ops index

- `thread.add`: Create a threaded comment on a cell or range.
- `thread.reopen`: Reopen a resolved comment thread.
- `thread.reply`: Reply to a comment thread.
- `thread.resolve`: Resolve a comment thread.

## `thread.add`

Create a threaded comment on a cell or range.

**Required fields**
- `body`
- `op`
- `target`

**Optional fields**
- `author`
- `createdAt`

**Examples**
```json
{
  "op": "thread.add",
  "target": {
    "cell": {
      "sheet": "Sheet1",
      "address": "F5"
    }
  },
  "body": "Cell comment"
}
```

## `thread.reopen`

Reopen a resolved comment thread.

**Required fields**
- `op`
- `target`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "thread.reopen",
  "target": "threadId"
}
```

## `thread.reply`

Reply to a comment thread.

**Required fields**
- `body`
- `op`
- `target`

**Optional fields**
- `author`
- `createdAt`

**Examples**
```json
{
  "op": "thread.reply",
  "target": "threadId",
  "body": "Reply on cell"
}
```

## `thread.resolve`

Resolve a comment thread.

**Required fields**
- `op`
- `target`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "thread.resolve",
  "target": "threadId"
}
```
