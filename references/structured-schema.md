# Structured schema and CSV contract

## Batch object

Before CSV generation, produce a JSON object with `versions` and `records`. Include `conversion` only when needed. `feedback` is optional and transient

```json
{
  "versions": {
    "skill_version": "0.3.1",
    "ruleset_version": "2026-09-11.2",
    "product_map_version": "2026-09-11.1",
    "alias_map_version": "2026-09-11.2"
  },
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
      "match_method": "confirmed_alias",
      "candidate_models": [],
      "requires_confirmation": false,
      "correction_reason": null,
      "confirmation": null,
      "capacity": "32G",
      "frequency": "3200",
      "extra_spec": ["2R4"],
      "year_or_batch": null,
      "warehouse": null,
      "region": null,
      "price": "2650",
      "currency": "CNY",
      "converted_price_cny": null,
      "tax_status": "含税",
      "condition_raw": null,
      "condition": null,
      "quantity": null,
      "price_unit": null,
      "eligibility": "eligible",
      "issues": []
    }
  ],
  "feedback": []
}
```

Copy version values exactly from [release-manifest.json](release-manifest.json). Do not infer or increment them while processing a quote

## Product resolution fields

| Field | Type | Rule |
|---|---|---|
| `matched_product_id` | string or null | Existing product ID selected from the bundled product map |
| `product_name` | string or null | Must equal the selected map row's `csv_product_name` for `eligible` |
| `match_method` | string or null | `exact`, `format_normalized`, `confirmed_alias`, or `user_confirmed` |
| `candidate_models` | array | Proposed existing products with `product_id`, `category`, `csv_product_name`, and `reason` |
| `requires_confirmation` | boolean | True when a proposed identity or missing discriminator awaits the user |
| `correction_reason` | string or null | Why the source may be a typo, abbreviation, alias, or incomplete expression |
| `confirmation` | object or null | Required for an eligible `user_confirmed` match |

A current-batch confirmation object uses

```json
{
  "confirmed": true,
  "scope": "current_batch",
  "confirmed_value": "RTX 4090 24G 涡轮",
  "confirmed_at": "26/09/11/14:35"
}
```

This object proves only that the current row was reviewed. It does not authorize an alias-map or product-map edit

## Other record fields

| Field | Type | Allowed or required values |
|---|---|---|
| `quote_datetime` | string or null | `yy/MM/dd/HH:mm`; required for `eligible` |
| `direction` | string | `sell`, `purchase`, `unknown` |
| `source_excerpt` | string or null | Short transient fragment; never enters CSV |
| `category` | string | `gpu`, `cpu`, `memory`, `disk`, `unknown` |
| `brand_raw` | string or null | Exact recognized source token |
| `brand_normalized` | string or null | Set after exact mapping, confirmed alias, or current-batch confirmation |
| `capacity` | string or null | Normalized unit such as `32G` |
| `frequency` | string or null | Normalized value such as `3200` |
| `extra_spec` | array | Recognized non-output specifications |
| `year_or_batch` | string or null | Examples `22年`, `DC26` |
| `warehouse` | string or null | Examples `深圳仓`, `香港仓` |
| `region` | string or null | Location context such as `香港` |
| `price` | string, number, or null | Positive per-item source price |
| `currency` | string or null | `CNY`, `USD`, or null; unmarked input becomes `CNY` |
| `converted_price_cny` | string, number, or null | Preview or audit value; recomputed by the generator |
| `tax_status` | string or null | `含税`, `未税` |
| `condition_raw` | string or null | Literal condition expression such as `拆机新` or `九成新`; internal only |
| `condition` | string or null | Normalized `全新`, `拆机`, or null; `拆新`, `拆机新`, and percentage-new expressions normalize to `拆机` |
| `quantity` | string, number, or null | Internal only |
| `price_unit` | string or null | Internal only |
| `eligibility` | string | `eligible`, `needs_confirmation`, `excluded` |
| `issues` | array | Specific unresolved or exclusion reasons |

Do not use a confidence score as a substitute for candidate evidence or a concrete issue

Useful issue codes include `masked_price`, `missing_price`, `missing_tax_status`, `ambiguous_product`, `product_not_in_map`, `unsupported_category`, `missing_rate_evidence`, and `unconfirmed_correction`

Clearly unrelated text is ignored before record persistence and therefore has no record or issue code unless the user requests a full audit

## Eligibility contract

An `eligible` record must have

- A category supported by the generator
- Valid quote datetime
- Direction `sell` or `purchase`
- One existing `matched_product_id`
- `product_name` exactly matching that map row
- A permitted `match_method`
- `requires_confirmation` set to false
- A valid current-batch `confirmation` when `match_method` is `user_confirmed`
- Positive numeric price
- Currency `CNY` or `USD`
- Tax status `含税` or `未税`
- Condition normalized to `全新`, `拆机`, or null
- No unresolved issue

A proposed correction cannot be eligible before confirmation. An unsupported hard-disk row, masked price, missing price, unresolved product, or missing required field cannot be eligible

Missing condition is allowed. DC, year, batch, warehouse, and region do not block an otherwise valid CNY row

## Confirmed alias contract

When `match_method` is `confirmed_alias`, the pair `brand_raw` and `brand_normalized` must match a `confirmed` row in [brand-alias-map.csv](brand-alias-map.csv)

An unlisted expression may use `user_confirmed` for the current batch after the user selects one existing mapped product. It must not be labeled `confirmed_alias`

## USD eligibility

For an eligible USD record, warehouse or region must identify Hong Kong. The batch `conversion` object must contain

- Positive `usd_cny_rate`
- Official publication `rate_date` not later than the quote date
- Exact official `rate_source`
- Direct HTTPS `rate_source_url` on `pbc.gov.cn` or `chinamoney.com.cn`
- Factor `1.13`
- Rounding step `1`

The generator recomputes `price × rate × 1.13` and rounds to a whole yuan with decimal half-up

## CSV mapping

| CSV column | Structured source |
|---|---|
| `日期时间` | `quote_datetime` |
| `产品名型号` | Mapped `product_name` |
| `报价` | CNY price, or recomputed and rounded CNY result for USD |
| `税务状态` | `tax_status` |
| `货况` | `condition`, empty when null |

CSV contains exactly those five columns in that order. Direction, quantity, warehouse, year, batch, candidates, confirmation, feedback, and versions never enter CSV

Encoding and filename

- UTF-8 without BOM
- English comma delimiter
- LF line endings
- One file per date and category
- `yy-MM-dd_category.csv`

## Merge contract

The script accepts `--existing-dir` only when the user explicitly chooses to merge

- Load only the same output filename from the existing directory
- Require the exact five-column header
- Remove only rows whose five CSV fields are identical
- Preserve rows when any field differs
- Never merge across dates
