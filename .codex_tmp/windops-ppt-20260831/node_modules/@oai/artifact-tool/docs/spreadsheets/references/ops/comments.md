# comments ops

Ops in the `comments.*` namespace for `Workbook.apply`.

## Ops index

- `comments.self.set`: Set the current comment author identity.

## `comments.self.set`

Set the current comment author identity.

**Required fields**
- `op`
- `person`

**Optional fields**
- (none)

**Examples**
```json
{
  "op": "comments.self.set",
  "person": {
    "displayName": "Artifact Bot",
    "initials": "AB"
  }
}
```
