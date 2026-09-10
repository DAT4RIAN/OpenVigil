# names ops

Ops in the `names.*` namespace for `Workbook.apply`.

## Ops index

- `names.function.add`: Define a workbook or worksheet named function (LAMBDA).
- `names.range.add`: Define a workbook or worksheet named range.

## `names.function.add`

Define a workbook or worksheet named function (LAMBDA).

**Required fields**
- `lambda`
- `name`
- `op`

**Optional fields**
- `description`
- `parameters`
- `returns`
- `sheet`

**Examples**
```json
{
  "op": "names.function.add",
  "name": "AddTax",
  "lambda": "LAMBDA(price, tax, price*(1+tax))",
  "description": "Adds tax to a price",
  "parameters": [
    {
      "name": "price",
      "description": "Base price"
    },
    {
      "name": "tax",
      "description": "Tax rate (e.g. 0.1)"
    }
  ],
  "returns": "Taxed price"
}
```

## `names.range.add`

Define a workbook or worksheet named range.

**Required fields**
- `formula`
- `name`
- `op`

**Optional fields**
- `description`
- `sheet`

**Examples**
```json
{
  "op": "names.range.add",
  "name": "SalesRange",
  "formula": "Data!$A$1:$A$3",
  "description": "Input sales data"
}
```
