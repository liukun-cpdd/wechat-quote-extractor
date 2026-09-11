# Structured schema and CSV contract

## Batch object

Before CSV generation, produce a JSON object with a `records` array

```json
{
  "conversion": {
    "usd_cny_rate": null,
    "rate_date": null,
    "rate_source": "中国人民银行授权中国外汇交易中心公布的人民币汇率中间价",
    "rate_source_url": null,
    "factor": "1.13",
    "rounding": "1"
  },
  "records": [
    {
      "quote_datetime": "26/09/11/14:30",
      "direction": "sell",
      "source_excerpt": "SK 32g 2R4 3200 含税 2650",
      "category": "memory",
      "brand_raw": "SK",
      "brand_normalized": "海力士",
      "product_name": "海力士 32G 3200",
      "matched_product_id": "25",
      "capacity": "32G",
      "frequency": "3200",
      "extra_spec": ["2R4"],
      "year_or_batch": null,
      "warehouse": null,
      "price": "2650",
      "currency": "CNY",
      "tax_status": "含税",
      "condition": "拆机",
      "quantity": null,
      "price_unit": null,
      "eligibility": "eligible",
      "issues": []
    }
  ]
}
```

## Field rules

| Field | Type | Allowed or required values |
|---|---|---|
| `quote_datetime` | string or null | `yy/MM/dd/HH:mm`; required for `eligible` |
| `direction` | string | `sell`, `purchase`, `unknown` |
| `source_excerpt` | string or null | Short transient source fragment for verification; never enters CSV |
| `category` | string | `gpu`, `cpu`, `memory`, `disk`, `unknown` |
| `brand_raw` | string or null | Exact recognized token |
| `brand_normalized` | string or null | Only after a confirmed mapping |
| `product_name` | string or null | Required for `eligible` |
| `matched_product_id` | string or null | Product ID from the current product-model map |
| `capacity` | string or null | Preserve normalized unit such as `32G` |
| `frequency` | string or null | Preserve normalized value such as `3200` |
| `extra_spec` | array | Recognized non-output specifications |
| `year_or_batch` | string or null | Examples `22年`, `DC26` |
| `warehouse` | string or null | Examples `深圳仓`, `香港仓` |
| `price` | string or number or null | Positive per-item price |
| `currency` | string or null | `CNY`, `USD`, or null; null or unmarked input normalizes to `CNY` |
| `converted_price_cny` | string, number, or null | Preview/audit value for USD conversion; recomputed by the generator |
| `tax_status` | string or null | `含税`, `未税` |
| `condition` | string or null | `全新`, `拆机`, or null; null writes an empty CSV cell |
| `quantity` | string, number, or null | Internal only |
| `price_unit` | string or null | Internal only |
| `eligibility` | string | `eligible`, `needs_confirmation`, `excluded` |
| `issues` | array | Specific reasons requiring attention |

Do not use confidence scores as a substitute for specific issues

## Eligibility contract

An `eligible` record must have

- Confirmed category code supported by the CSV generator
- Valid quote datetime
- Direction `sell` or `purchase`
- Complete product name
- A unique `matched_product_id` whose category and `csv_product_name` match the current product-model map
- Positive numeric price
- Currency `CNY` or `USD`; unmarked source currency normalizes to `CNY`
- Tax status `含税` or `未税`
- No unresolved issues

Records using raw brand `MT`, unknown hard-disk code, masked prices, unmatched product models, or missing required fields cannot be `eligible`

For an eligible USD record, `warehouse` or region must identify Hong Kong and the batch `conversion` object must contain a positive `usd_cny_rate`, an official publication `rate_date` not later than the quote date, the fixed official `rate_source`, a direct `rate_source_url` on `pbc.gov.cn` or `chinamoney.com.cn`, and fixed factor `1.13`. The rounding step is fixed at `1`, using decimal half-up rounding

Missing condition is allowed and does not create an issue. DC/year/batch, warehouse, and region are internal attributes and do not block eligibility

## CSV mapping

| CSV column | Structured source |
|---|---|
| `日期时间` | `quote_datetime` |
| `产品名型号` | `product_name` |
| `报价` | CNY: normalized numeric `price`; USD: `price × usd_cny_rate × 1.13`, rounded half-up to a whole yuan |
| `税务状态` | `tax_status` |
| `货况` | `condition` |

CSV contains exactly those five columns in that order

Use the paste/submission timestamp when the source has no explicit quote time. DC/year/batch, warehouse, and region are never appended to CSV fields

Encoding and filename

- UTF-8 without BOM
- English comma delimiter
- LF line endings
- One file per date and category
- `yy-MM-dd_category.csv`

## Merge contract

The script accepts `--existing-dir` only when the user has explicitly chosen to merge

- Load only the same output filename from the existing directory
- Require the exact five-column header
- Remove only rows whose five CSV fields are identical
- Preserve rows when any field differs
- Never merge across dates
