# Business rules

## Confirmed scope

The skill processes transient pasted quote text and produces market candidates. It does not create contacts, store chat history, or upload files to the market backend

Current market categories

| Business category | CSV category code | Status |
|---|---|---|
| GPU | `gpu` | Confirmed |
| CPU | `cpu` | Confirmed |
| 内存 | `memory` | Confirmed |
| 硬盘 | Unknown | Do not generate until confirmed |

## Context inheritance

Section headings and default statements apply to subsequent product lines until a new heading or default replaces them

Precedence

```text
Explicit row value > section default > confirmed global default > needs_confirmation
```

Examples

- `特价出内存` establishes category `memory` and direction `sell`
- `默认拆机` supplies condition `拆机` only when a product line has no explicit condition
- `质保一年` is recognized as warranty context but does not enter the current CSV
- Invalid phrases such as `含税不对应` do not establish a tax default

## Brand normalization

Apply only these confirmed mappings

| Raw value | Normalized value | Handling |
|---|---|---|
| `SK` | `海力士` | Automatic |
| `美光` | `镁光` | Automatic |
| `MT` | None | Retain raw value and mark `needs_confirmation` |

Do not infer an unlisted brand alias from general knowledge

## Memory product name

For the current rule set, construct a memory product name from

```text
normalized brand + capacity + frequency
```

Keep condition in the separate `货况` column

Recognize but omit memory-layout tokens such as `2S2R4`, `2R4`, `2R8`, and `4DR4` from the product name. Do not discard them from the structured candidate

Treat year-like tokens such as `22年`, `2022年`, `25+`, and `22+` as DC or batch information. Preserve them together with explicit DC markers such as `DC21+` and `DC26` in structured fields, but do not add them to the product name or final CSV

Preserve warehouse and region in structured fields. They do not enter the current five-column CSV and do not block an otherwise eligible record

## Product-model mapping

Use [product-model-map.csv](product-model-map.csv) as the current product dictionary. It is generated from the supplied market-products export and intentionally kept separate so it can be replaced when that export changes

- Match only rows whose category is `cpu`, `gpu`, or `memory`; ignore `test` and unsupported categories
- Resolve casual quote wording to exactly one mapped model using the explicit model, capacity, form-factor, version, and other distinguishing tokens in the source
- Case, spacing, punctuation, and confirmed brand aliases may be normalized during matching
- Use the matched row's `csv_product_name` exactly in the final CSV
- If no mapped model matches, classify the candidate as `excluded` with issue `product_not_in_map`
- If more than one mapped model remains possible, classify it as `needs_confirmation` and ask only for the missing distinguishing attributes
- Never add an unmatched model to the map from general knowledge or from one quote

The source export stores condition at the end of `产品名称`. The mapping file preserves that original name but removes the trailing `全新` or `拆机` from `csv_product_name`, because condition is a separate CSV column

## Price evidence

Eligible price evidence may come from either direction

- Explicit sell price, such as `含税17000出`
- Explicit purchase or receiving price, such as `未税2600收100条`

Not price evidence

- `有货带价`
- `麻烦报价`
- `求报价`
- A quantity with no price
- A year, DC marker, capacity, frequency, deposit, total, or fee whose meaning is not a per-item market price
- A masked amount containing `x` or `X` in place of price digits, such as `18x00`, `17X00`, `11x000`, or `4X00USD`

An unmarked currency defaults to CNY

For an explicit USD quote whose warehouse or region is Hong Kong, calculate the final CNY quote as

```text
USD price × current-day USD/CNY rate × 1.13
```

Authoritative rate source

- Use the RMB central parity rate published by the China Foreign Exchange Trade System under authorization from the People's Bank of China
- Prefer the official People's Bank of China announcement page; an official China Money/CFETS page is also acceptable
- On a trading day after publication, use that day's published rate
- Before publication, on weekends, or on public holidays, use the latest official rate published on or before the paste time
- Record the rate value, actual publication date, official source name, and direct official URL; never label a previous trading day's rate as today's publication

Round the converted result to the nearest whole yuan using decimal half-up rounding. Store the original USD price, exchange-rate value, rate date, rate source, conversion factor, fixed rounding rule, and converted CNY price in the structured batch. Write only the integer CNY result to the final CSV

Do not convert or generate a USD row when Hong Kong location is not confirmed, or when the applicable official rate value, publication date, source name, or direct official URL is missing

## Processing boundary

Cleaning and signal extraction are separate stages

- Cleaning creates a working copy only: decode HTML entities, remove decorative emoji, normalize whitespace and line breaks, and retain all business-bearing text
- First-pass extraction identifies literal fields and nearby units without deciding import eligibility
- Second-pass signal resolution applies context inheritance, distinguishes price from quantity or totals, normalizes confirmed aliases, matches the product dictionary, and identifies conflicts
- Deterministic validation checks the final structured fields, exchange-rate record, model map, and CSV contract before file generation
- Keep a short `source_excerpt` for candidate-level verification, but do not write raw text or excerpts to CSV

A masked-price candidate is invalid for the current import. Classify it as `excluded`; after a person supplies the exact numeric price, parse the corrected text as a new candidate

Preserve `direction` internally because the CSV cannot distinguish bid from ask after import

## Number semantics

Use nearby units and words to distinguish numbers

| Expression | Meaning |
|---|---|
| `17000`, `含税17000` | Price candidate |
| `1400USD` | USD price candidate |
| `18x00`, `11x000` | Masked price; invalid until replaced with an exact amount |
| `25800*10张` | Unit price `25800` and quantity `10张`; not a masked price |
| `400条`, `数量2200条` | Quantity |
| `24*2` | Kit configuration |
| `4588/套` | Per-kit price |
| `22年`, `DC21+`, `DC26` | Year or batch candidate |

Do not coerce a range, bundle total, or unclear amount into one price

## Tax and condition

Current standard values

- Tax status: `含税`, `未税`
- Condition: `全新`, `拆机`

An explicit row value overrides a section default. Missing tax status still requires confirmation

A missing condition is allowed. Keep it empty and do not infer condition from `现货`, quantity, warehouse, packaging, year, or DC text

When the source has no explicit quote time, use the time when the user pasted the quote text as the import time

## Exclusions

Exclude

- `冰刃` and `兵刃` products
- Purchase requests without a concrete price
- Products outside the confirmed market scope
- Composite products with one inseparable total price
- Quotes whose price is masked or otherwise not an exact numeric amount

This does not authorize excluding every consumer-memory product. Apply only the confirmed product exclusion

## Unresolved policies

Until the user confirms them, keep the affected record out of CSV

- The hard-disk category code and import template
- Whether same-day merge uses exact-five-field deduplication
