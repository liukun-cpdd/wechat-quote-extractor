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
2. Replaceable dictionaries contain importable products and reviewed brand aliases
3. Model judgment interprets natural language, detects likely typos or shorthand, and proposes candidates
4. Deterministic validation enforces dictionary identity, release versions, conversion evidence, and the CSV contract

Model judgment may propose; only confirmed dictionaries or an explicit current-batch confirmation may authorize a corrected identity

## Cleaning and extraction

Cleaning creates a working copy only. Decode harmless HTML entities, remove decorative emoji, normalize whitespace and line breaks, and retain every token that may carry product, price, quantity, tax, condition, warehouse, time, DC, batch, direction, or unit information

Extract literal signals before applying business meaning

- Section or line direction
- Raw brand and model wording
- Capacity, frequency, form factor, model suffix, and memory layout
- Price candidate, currency, quantity, and unit
- Tax status and condition
- Year, DC, batch, warehouse, and region

Second-pass resolution applies inherited context, distinguishes price from quantity or totals, resolves product identity, and assigns eligibility. Do not use it to invent missing facts

## Context inheritance

Section headings and default statements apply to subsequent product lines until a new heading or default replaces them

```text
Explicit row value > section default > confirmed global default > needs_confirmation
```

- `特价出内存` establishes category `memory` and direction `sell`
- `默认拆机` supplies condition `拆机` only when a product line has no explicit condition
- `质保一年` is warranty context and does not enter the current CSV
- Invalid or contradictory phrases such as `含税不对应` do not establish a tax default

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

## Brand aliases

Only rows whose `status` is `confirmed` in [brand-alias-map.csv](brand-alias-map.csv) may normalize automatically

An unlisted brand token remains raw. If the source attributes point to one plausible mapped brand or model, propose it and ask for current-batch confirmation. If several mappings are plausible, show the candidates and ask for the missing discriminator. If none is plausible, exclude the record

Do not create a permanent alias from general knowledge, one quote, or one user's runtime answer

## Product naming

The final `product_name` must equal the selected row's `csv_product_name` exactly

For memory candidates, capacity and frequency are important matching signals. Recognize memory-layout tokens such as `2S2R4`, `2R4`, `2R8`, and `4DR4`, preserve them in `extra_spec`, and do not append them to the final product name

Treat tokens such as `22年`, `2022年`, `25+`, `22+`, `DC21+`, and `DC26` as year, DC, or batch information. Preserve them in structured fields, but do not add them to the product name or CSV

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

- Tax status accepts `含税` or `未税`; missing tax status requires confirmation
- Condition accepts `全新`, `拆机`, or empty
- Do not infer condition from `现货`, warehouse, packaging, year, DC, or quantity
- When the source has no explicit quote time, use the user's paste time as `quote_datetime`
- Preserve `direction` internally because the CSV cannot distinguish purchase from sell evidence

## Eligibility and output

Only `eligible` records enter CSV. `needs_confirmation`, `excluded`, ignored unrelated text, suggestions, and feedback never enter CSV

One eligible row must have a supported category, exact mapped product ID and name, valid quote time, sell or purchase direction, exact positive price, tax status, allowed condition, no unresolved issue, compatible release versions, and any required current-batch confirmation evidence

Do not generate a hard-disk CSV until the real category code and import template are confirmed

## Version and feedback isolation

Every batch must copy the four values from [release-manifest.json](release-manifest.json). The generator rejects batches built against a different Skill, ruleset, product map, or alias map version

Runtime confirmation applies only to that batch. Keep feedback transient unless the user explicitly requests an export. Shared behavior changes only after reviewed edits, tests, a Git commit, a release tag, and redistribution according to [release-process.md](release-process.md)

## Unresolved policies

Until confirmed, keep the affected operation out of the output

- Hard-disk category code and import template
- Whether same-day merging uses exact-five-field deduplication
