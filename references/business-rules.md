# Business rules

## Object boundary

The skill processes transient pasted quote text and produces market candidates. It does not create contacts, store chat history, maintain a permanent quote knowledge base, or upload files to the market backend

Current market categories

| Business category | CSV category code | Status |
|---|---|---|
| GPU | `gpu` | Confirmed |
| CPU | `cpu` | Confirmed |
| 内存 | `memory` | Confirmed |
| 硬盘 | Unknown | Do not generate until confirmed |

## Processing layers

Keep the four layers separate

1. Stable constraints control price validity, currency conversion, CSV fields, grouping, and authorization boundaries
2. Replaceable dictionaries contain importable products and reviewed brand or tax aliases
3. Model judgment interprets natural language, detects likely typos or shorthand, and proposes candidates
4. Deterministic validation enforces dictionary identity, release versions, conversion evidence, and the CSV contract

Model judgment may propose; only confirmed dictionaries or an explicit current-batch confirmation may authorize a corrected identity

## Cleaning and extraction

Cleaning creates a transient working copy only. Decode harmless HTML entities, remove decorative emoji, normalize whitespace and line breaks, and retain every token needed to separate product identity, price, tax, condition, warehouse, time, direction, or unit information

Extract literal signals before applying business meaning

- Section or line direction
- Raw brand and model wording
- Capacity, frequency, form factor, model suffix, and memory layout
- Price candidate, currency, quantity, and unit
- Tax status and condition
- Year, DC, batch, warehouse, and region

Second-pass resolution applies inherited context, distinguishes price from quantity or totals, resolves product identity, and assigns eligibility. Do not use it to invent missing facts

Quantity, year, DC, batch, memory layout, warranty, packaging, packing method, and invoice correspondence may be used during extraction, but they are not formal result fields. Discard them before creating the finalized batch object

## Context inheritance

Section headings and default statements apply to subsequent product lines until a new heading or default replaces them

```text
Explicit row value > section default > confirmed global default > needs_confirmation
```

- `特价出内存` establishes category `memory` and direction `sell`
- `默认拆机` supplies condition `拆机` only when a product line has no explicit condition
- `质保一年` is temporary warranty context and is discarded before the finalized batch
- `含税不对应`, `含税票不对应`, and `含税开其他品类发票` all establish tax status `含税`; discard the invoice-correspondence qualifier

## Product identity resolution

Use [product-model-map.csv](product-model-map.csv) as the only importable product dictionary. Use [brand-alias-map.csv](brand-alias-map.csv) as the only automatic brand-alias dictionary

Normalize case, full-width characters, spacing, and punctuation without confirmation when product identity does not change

Resolve in this order

1. Exact map match
2. Formatting-normalized match
3. Confirmed brand-alias match
4. Semantic candidate proposal based on the raw wording and the distinguishing fields present in the source
5. Current-batch user confirmation of exactly one existing mapped product

The model may use language understanding and the mapped catalog to recognize probable misspellings, phonetic variants, abbreviations, or omitted separators. A proposal must state the raw expression, the suggested mapped product, and the evidence for the suggestion. Never present a proposal as an established alias

Candidate handling

| Situation | Result |
|---|---|
| One exact, formatting-normalized, or confirmed-alias match | May be `eligible` when other fields pass |
| One plausible correction that changes identity | `needs_confirmation`; propose that mapped product |
| Multiple plausible mapped products | `needs_confirmation`; ask only for distinguishing attributes |
| Relevant hardware but no plausible mapped product | `excluded` with `product_not_in_map`; no CSV |
| Clearly unrelated to CPU, GPU, memory, or supported disk scope | Ignore before candidate persistence unless a full audit is requested |

After the user confirms a suggestion, mark the record `user_confirmed` for the current batch and preserve the confirmation evidence. Do not add the expression to a dictionary and do not modify any Skill file

### CPU brand inference

For CPU records, an omitted brand is not itself a confirmation reason. Use the complete model expression, including distinguishing suffixes, to determine whether it is Intel or AMD

- If the brand can be identified and exactly one current product-map row matches, fill `brand_normalized`, use `model_inferred`, record the reasoning, and continue normally
- If the brand can be identified but no current product-map row matches, use `excluded` with `product_not_in_map`; do not ask for brand confirmation
- Use `needs_confirmation` only when the model cannot determine the brand, multiple mapped products remain possible, or product-distinguishing model information is missing

Apply this semantic rule to all recognizable Intel and AMD CPU expressions. Do not maintain a fixed CPU model list and never default every bare model to Intel

## Brand aliases

Only rows whose `status` is `confirmed` in [brand-alias-map.csv](brand-alias-map.csv) may normalize automatically

An unlisted brand token remains raw. If the source attributes point to one plausible mapped brand or model, propose it and ask for current-batch confirmation. If several mappings are plausible, show the candidates and ask for the missing discriminator. If none is plausible, exclude the record

Do not create a permanent alias from general knowledge, one quote, or one user's runtime answer

## Product naming

The final `product_name` must equal the selected row's `csv_product_name` exactly

For memory candidates, capacity and frequency are important matching signals. Recognize memory-layout tokens such as `2S2R4`, `2R4`, `2R8`, and `4DR4` only to separate source attributes. Do not append them to the final product name and discard them before the finalized batch

Treat tokens such as `22年`, `2022年`, `25+`, `22+`, `DC21+`, and `DC26` as possible temporary year, DC, or batch signals. Do not add them to the product name, finalized batch, or CSV

For memory, DC may appear as an explicit form such as `DC22+` or as a short form such as `22` or `22+`. The likely value range is generally from the teens through `26`. These forms are recognition cues, not a fixed pattern list. Require memory-product context and semantic placement, and do not reinterpret capacity, frequency, quantity, or price as DC merely because its numeric value falls in that range

Preserve warehouse and region in structured fields. They do not enter the five-column CSV and do not block an otherwise eligible CNY record

## Price evidence

Either direction can provide market evidence

- Explicit sell price such as `含税17000出`
- Explicit purchase price such as `未税2600收100条`

The following are not price evidence

- `有货带价`, `麻烦报价`, or `求报价`
- Quantity with no price
- Year, DC, capacity, frequency, deposit, total, or fee that is not clearly a per-item market price
- Masked price with `x` or `X` replacing digits, such as `18x00`, `17X00`, `11x000`, or `4X00USD`

An unmarked currency defaults to CNY

A masked-price record is excluded from the current import. If a person supplies the exact numeric price, parse the corrected text as a new current-batch candidate

## Number semantics

Use nearby units and language to distinguish numbers

| Expression | Meaning |
|---|---|
| `17000`, `含税17000` | Price candidate |
| `1400USD` | USD price candidate |
| `18x00`, `11x000` | Masked price, invalid until replaced |
| `25800*10张` | Unit price `25800` and quantity `10张` |
| `400条`, `数量2200条` | Quantity |
| `24*2` | Kit configuration unless context proves multiplication |
| `4588/套` | Per-kit price |
| `22年`, `DC21+`, `DC26` | Year or batch candidate |

Do not coerce a range, bundle total, or unclear amount into one price

## USD conversion

For an explicit USD quote confirmed to be located in Hong Kong, calculate

```text
USD price × applicable USD/CNY rate × 1.13
```

Use the RMB central parity rate published by the China Foreign Exchange Trade System under authorization from the People's Bank of China

- Prefer the official People's Bank of China announcement page; an official China Money/CFETS page is also acceptable
- On a trading day after publication, use that day's published rate
- Before publication, on weekends, or on public holidays, use the latest official rate published on or before paste time
- Record the rate value, actual publication date, official source name, and direct official URL
- Never label a previous trading day's rate as today's publication

Round the converted result to the nearest whole yuan using decimal half-up. Preserve the original USD price, rate, publication date, source, URL, factor, rounding rule, and converted amount in the structured batch. Write only the integer CNY amount to CSV

Do not generate a USD-derived row when Hong Kong location is unconfirmed or any required exchange-rate evidence is missing

## Tax, condition, and time

- Tax status answers only whether the quoted price includes tax. It never records whether invoice content corresponds to the actual product
- Any positive expression containing `含税`, including `含税不对应`, `含税票不对应`, and `含税开其他品类发票`, normalizes to `含税` without confirmation
- `未税` and the explicit negation `不含税` normalize to `未税`
- `WS` is a confirmed alias for `未税`; apply it case-insensitively
- Invoice correspondence wording without an explicit tax-inclusion signal does not establish tax status
- If no explicit tax-inclusion expression or confirmed tax alias appears, do not infer tax status; mark the record `needs_confirmation`
- If both positive tax-inclusive and tax-exclusive signals apply to the same row, mark the record `needs_confirmation`
- Keep only the shortest decisive tax token in `tax_status_raw`; discard invoice correspondence and invoice-description wording before the finalized batch
- Keep quantity and price signals separate from nearby tax aliases. In `镁光64G 3200 28条 WS 4200`, `28条` is quantity, `WS` is `未税`, and `4200` is the price candidate
- For GPU, CPU, and memory, the normalized condition accepts only `全新`, `拆机`, or empty
- Classify condition by meaning rather than by an exhaustive term list
- Use `explicit_new` and normalize to `全新` only when the wording clearly states that the item is brand-new
- Use `explicit_not_new` and normalize to `拆机` whenever the wording clearly states that the item is not brand-new. This includes used, disassembled, opened, refurbished, and percentage-new descriptions; examples such as `二手`, `旧货`, `拆新`, `拆机新`, `翻新`, `几成新`, `九成新`, and `9成新` are illustrative, not exhaustive
- Use `missing` and leave condition empty when no condition wording appears
- Use `ambiguous` and mark the record `needs_confirmation` only when condition wording appears but does not establish whether the item is brand-new
- Memory DC exception: when a memory candidate contains a semantically recognizable DC or production-date signal and the applicable row or section does not explicitly state `全新`, use `memory_dc_default` and normalize condition to `拆机`
- An explicit `全新` on the applicable memory row or inherited section overrides the DC default and remains `explicit_new`
- Do not apply `memory_dc_default` to GPU, CPU, or a memory record without recognizable DC evidence
- Preserve the literal source wording in `condition_raw`; write only the normalized `condition` to CSV
- Except for the memory DC rule above, do not infer condition from `现货`, warehouse, packaging, year, DC, or quantity
- When the source has no explicit quote time, use the user's paste time as `quote_datetime`
- Preserve `direction` internally because the CSV cannot distinguish purchase from sell evidence

## Eligibility and output

Only `eligible` records enter CSV. `needs_confirmation`, `excluded`, ignored unrelated text, suggestions, and feedback never enter CSV

One eligible row must have a supported category, exact mapped product ID and name, valid quote time, sell or purchase direction, exact positive price, tax status, allowed condition, no unresolved issue, compatible release versions, and any required current-batch confirmation evidence. An eligible CPU with an omitted source brand must also carry valid `model_inferred` evidence

Do not generate a hard-disk CSV until the real category code and import template are confirmed

After all normalization and conversion, deduplicate eligible rows within the current batch by the exact five CSV fields: `日期时间`, `产品名型号`, `报价`, `税务状态`, and `货况`. Keep the first occurrence and discard later identical rows. If any one field differs, preserve both rows

Current-batch deduplication is automatic. Historical same-day CSV merging still requires the user's explicit choice and uses the same exact-five-field identity

## Version and feedback isolation

Every batch must copy all values from [release-manifest.json](release-manifest.json). The generator rejects batches built against a different Skill, ruleset, product map, brand-alias map, or tax-alias map version

Runtime confirmation applies only to that batch. Keep feedback transient unless the user explicitly requests an export. Shared behavior changes only after reviewed edits, tests, a Git commit, a release tag, and redistribution according to [release-process.md](release-process.md)

## Unresolved policies

Until confirmed, keep the affected operation out of the output

- Hard-disk category code and import template
