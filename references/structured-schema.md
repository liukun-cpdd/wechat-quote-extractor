# Structured schema and CSV contract

## Batch object

Before CSV generation, produce a JSON object with `batch_datetime`, `versions`, and finalized `records`. Include `conversion` only when needed. `feedback` is optional and transient

The finalized batch is not a transcript archive. Extraction-only signals must be discarded before this object is produced

```json
{
  "batch_datetime": "26/09/14/14:30:00",
  "versions": {
    "skill_version": "0.6.1",
    "ruleset_version": "2026-09-15.2",
    "product_map_version": "2026-09-11.1",
    "alias_map_version": "2026-09-11.2",
    "tax_map_version": "2026-09-11.1"
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
      "category": "memory",
      "brand_raw": "SK",
      "brand_normalized": "海力士",
      "brand_resolution_method": "confirmed_alias",
      "brand_inference_reason": null,
      "product_name": "海力士 32G 3200",
      "matched_product_id": "25",
      "match_method": "confirmed_alias",
      "candidate_models": [],
      "requires_confirmation": false,
      "correction_reason": null,
      "confirmation": null,
      "capacity": "32G",
      "frequency": "3200",
      "warehouse": null,
      "region": null,
      "price": "2650",
      "currency": "CNY",
      "converted_price_cny": null,
      "tax_status_raw": "含税",
      "tax_status": "含税",
      "condition_raw": null,
      "condition_classification": "missing",
      "condition": null,
      "price_unit": null,
      "eligibility": "eligible",
      "issues": []
    }
  ],
  "feedback": []
}
```

Copy version values exactly from [release-manifest.json](release-manifest.json). Do not infer or increment them while processing a quote

`batch_datetime` is the user's paste or processing time in `yy/MM/dd/HH:mm:ss`. It determines the `yy-MM-dd` date directory and timestamped output directory. Every eligible record in the batch must have the same calendar date

## Extraction-only signals

The model may recognize the following information while separating products, prices, and context, but it must discard the information before creating the finalized batch

- Raw source excerpts or chat text
- Quantity
- Year, DC, or batch
- Memory layout or other non-identity layout tokens
- Warranty
- Packaging or packing method
- Whether an invoice corresponds to the actual product, and any invoice-description detail

The finalized record must not contain `source_excerpt`, `quantity`, `year_or_batch`, `dc`, `extra_spec`, `memory_layout`, `warranty`, `packaging`, `packing_method`, `invoice_matching`, or `invoice_details`, even with a null value. The generator rejects these fields to prevent accidental long-term retention

Warehouse and region remain formal fields because they are required to validate Hong Kong USD conversion. Capacity and frequency remain formal product-identity fields

## Product resolution fields

| Field | Type | Rule |
|---|---|---|
| `matched_product_id` | string or null | Existing product ID selected from the bundled product map |
| `product_name` | string or null | Must equal the selected map row's `csv_product_name` for `eligible` |
| `match_method` | string or null | `exact`, `format_normalized`, `confirmed_alias`, `model_inferred`, or `user_confirmed` |
| `brand_resolution_method` | string or null | `explicit`, `confirmed_alias`, `model_inferred`, or `user_confirmed` |
| `brand_inference_reason` | string or null | Required when a CPU brand is inferred from a model without an explicit brand token |
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

## Other formal record fields

| Field | Type | Allowed or required values |
|---|---|---|
| `quote_datetime` | string or null | `yy/MM/dd/HH:mm`; required for `eligible` |
| `direction` | string | `sell`, `purchase`, `unknown` |
| `category` | string | `gpu`, `cpu`, `memory`, `disk`, `unknown` |
| `brand_raw` | string or null | Explicit brand token only; null when a CPU brand is inferred from model |
| `brand_normalized` | string or null | Set after explicit recognition, confirmed alias, model inference, or current-batch confirmation |
| `capacity` | string or null | Normalized identity value such as `32G` |
| `frequency` | string or null | Normalized identity value such as `3200` |
| `warehouse` | string or null | Examples `深圳仓`, `香港仓` |
| `region` | string or null | Location context such as `香港` |
| `price` | string, number, or null | Positive per-item source price |
| `currency` | string or null | `CNY`, `USD`, or null; unmarked input becomes `CNY` |
| `converted_price_cny` | string, number, or null | Preview or audit value; recomputed by the generator |
| `tax_status_raw` | string or null | Shortest decisive token such as `含税`, `未税`, or `WS`; never retain invoice-matching qualifiers here |
| `tax_status` | string or null | Normalized `含税` or `未税` |
| `condition_raw` | string or null | Literal condition expression used for validation |
| `condition_classification` | string | `explicit_new`, `explicit_not_new`, `missing`, or `ambiguous` |
| `condition` | string or null | Normalized `全新`, `拆机`, or null |
| `price_unit` | string or null | Price-unit evidence when needed to distinguish per-item price from a total |
| `eligibility` | string | `eligible`, `needs_confirmation`, `excluded` |
| `issues` | array | Specific unresolved or exclusion reasons |

Do not use a confidence score as a substitute for candidate evidence or a concrete issue

Useful issue codes include `masked_price`, `missing_price`, `missing_tax_status`, `ambiguous_product`, `missing_product_discriminator`, `product_not_in_map`, `unsupported_category`, `missing_rate_evidence`, and `unconfirmed_correction`

Clearly unrelated text is ignored before record persistence and therefore has no record or issue code unless the user requests a full audit. Memory quotes that semantically describe white-label or dual-label modules are also ignored before persistence and are never expanded as shared multi-brand quotes

## CPU brand-resolution contract

An omitted CPU brand is not itself a confirmation reason

1. Use the complete model expression and its distinguishing suffixes to determine whether the CPU is Intel or AMD
2. Search the current product map using the inferred brand and model identity
3. When exactly one mapped product matches, set `brand_raw` to null, set `brand_normalized` and both resolution methods to `model_inferred`, record a concrete `brand_inference_reason`, and continue normally
4. When the model identifies a brand but no mapped product exists, use `excluded` with `product_not_in_map`; do not ask the user to confirm the brand
5. Use `needs_confirmation` only when the brand cannot be determined, multiple mapped products remain possible, or key model information needed to distinguish products is missing

This is a model-semantic rule for all recognizable Intel and AMD CPU expressions. Do not maintain a fixed model allowlist and never default every bare CPU model to Intel

For an eligible CPU, the generator verifies that the normalized brand is `Intel` or `AMD`, the mapped product name uses that brand, and a brandless source has `model_inferred` evidence

## Eligibility contract

An `eligible` record must have

- A category supported by the generator
- Valid quote datetime
- Direction `sell` or `purchase`
- One existing `matched_product_id`
- `product_name` exactly matching that map row
- A permitted `match_method`
- Valid CPU brand-resolution evidence when category is `cpu`
- `requires_confirmation` set to false
- A valid current-batch `confirmation` when `match_method` is `user_confirmed`
- Positive numeric price
- Currency `CNY` or `USD`
- Tax status `含税` or `未税`
- Condition normalized to `全新`, `拆机`, or null
- Condition classification consistent with raw wording and normalized output
- No unresolved issue
- None of the extraction-only fields listed above

A proposed correction cannot be eligible before confirmation. An unsupported hard-disk row, masked price, missing price, unresolved product, or missing required field cannot be eligible

`explicit_new` writes `全新` and `explicit_not_new` writes `拆机`. For CPU and memory, `missing` and `ambiguous` also write `拆机`; for GPU, `missing` writes an empty cell and `ambiguous` cannot be eligible until clarified

The model determines whether arbitrary wording explicitly means brand-new or non-new. Do not require wording to appear in a fixed alias list. Warehouse and region do not block an otherwise valid CNY row

## Confirmed alias contract

When `match_method` is `confirmed_alias`, the pair `brand_raw` and `brand_normalized` must match a `confirmed` row in [brand-alias-map.csv](brand-alias-map.csv)

An unlisted expression may use `user_confirmed` for the current batch after the user selects one existing mapped product. It must not be labeled `confirmed_alias`

## Tax contract

Tax status answers only whether the quoted price includes tax. It does not represent whether invoice content corresponds to the actual product

- Any positive expression containing `含税`, including `含税不对应`, `含税票不对应`, and `含税开其他品类发票`, normalizes to `含税` without confirmation
- `未税` and the explicit negation `不含税` normalize to `未税`
- `WS` is a confirmed case-insensitive alias for `未税`
- Invoice correspondence wording without an explicit tax-inclusion signal does not establish a tax status
- If no explicit `含税`, `未税`, `不含税`, or confirmed tax alias appears, the record needs confirmation and cannot be eligible
- If both positive tax-inclusive and tax-exclusive signals apply to the same record, the record needs confirmation

Extract only the shortest decisive token into `tax_status_raw`. Discard invoice correspondence and invoice-description wording before creating the finalized batch. The generator also recognizes full tax-bearing phrases defensively but never writes those qualifiers to CSV

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
| `产品名型号` | Mapped `product_name`; prefix GPU output with `英伟达` after matching |
| `报价` | CNY price, or recomputed and rounded CNY result for USD |
| `税务状态` | Normalized `tax_status` |
| `货况` | `condition`, empty when null |

CSV contains exactly those five columns in that order. No other structured or extraction-only field enters CSV

Encoding and filename

- UTF-8 without BOM
- English comma delimiter
- LF line endings
- One file per date and category
- `yy-MM-dd_category.csv`

## Snapshot contract

The generator requires `--snapshot-root <confirmed-root>` and creates `yy-MM-dd/yy-MM-dd_HH-mm-ss` beneath it. Its result reports `snapshot_directory`, `baseline_directory`, and `first_snapshot_of_day`

The baseline is either null for the day's first batch or exactly one latest earlier snapshot inside the same date directory. Every inherited CSV must pass the five-column contract before the new snapshot is created. New snapshots normalize inherited legacy GPU names to the current `英伟达` prefix while leaving the baseline untouched

The deduplication key is the four-tuple `(产品名型号, 报价, 税务状态, 货况)`. When duplicate keys exist, retain the row with the earliest valid `日期时间`. `duplicate_rows_removed` reports discarded rows
