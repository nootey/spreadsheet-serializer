# spreadsheet-serializer

This is a small and highly specific helper, meant to help me serialize my non-standard format Excel spreadsheets.

The format is generalized and can be imported into my app.

## Input

Here is a sample input file, that needs to be placed in `./input/{year}.json`

```json
{
  "year": 2025,

  "sheet_name": ["Inflows","Outflows","Investments"],

  "header_scan_rows": 12,
  "category_col_hint": null,
  "debug": false,

  "months": {
    "1":  ["JANUAR","JAN","JAN.","1","JANUARY"],
    "2":  ["FEBRUAR","FEB","FEB.","2","FEBRUARY"],
    "3":  ["MAREC","MAR","MAR.","3","MARCH"],
    "4":  ["APRIL","APR","APR.","4"],
    "5":  ["MAJ","MAJ.","5","MAY","MAY."],
    "6":  ["JUNIJ","JUN","JUN.","6","JUNE"],
    "7":  ["JULIJ","JUL","JUL.","7","JULY"],
    "8":  ["AVGUST","AVG","AVG.","8","AUG","AUG.","AUG,"],
    "9":  ["SEPTEMBER","SEP","SEPT","SEP.","9","SEPTEMBER","SEPT."],
    "10": ["OKTOBER","OKT","OKT.","10","OCT","OCT."],
    "11": ["NOVEMBER","NOV","NOV.","11"],
    "12": ["DECEMBER","DEC","DEC.","12"]
  },

  "section_prefixes": [
    ["Inflow", "income"],
    ["Outflows fixed", "expense"],
    ["Outflows variable", "expense"],
    ["Investments", "investments"]
  ],

  "ignored_prefixes": ["Stat", "Category", "Rate"],
  "ignored_exact": ["Gotovina", "Total"],

  "used_col_aliases": ["USED", "PORABLJENO", "SPENT"],

  "expected_totals": {
    "income":      "100.00",
    "expense":     "50.00",
    "savings":     "0.00",
    "investments": "1000.00"
  },
  "mismatch_policy": "fail"
}
```

## Output

This is an example output. It gets generated into `./output/{year}.json`

```json
{
  "generated_at": "2025-10-26T11:59:10.639082+00:00",
  "transactions": [
    {
      "transaction_type": "income",
      "amount": "100.00",
      "currency": "EUR",
      "txn_date": "2025-09-01T00:00:00Z",
      "category": "Other",
      "description": ""
    },
    {
      "transaction_type": "expense",
      "amount": "50.00",
      "currency": "EUR",
      "txn_date": "2025-10-01T00:00:00Z",
      "category": "Random",
      "description": ""
    }
  ],
  "transfers": [
    {
      "transaction_type": "investments",
      "amount": "1000.00",
      "currency": "EUR",
      "txn_date": "2025-02-01T00:00:00Z",
      "category": "Crypto",
      "description": ""
    }
  ],
  "categories": []
}
```
