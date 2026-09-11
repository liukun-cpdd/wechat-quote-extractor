---
name: wechat-quote-extractor
description: Extract structured market quotes from pasted Chinese hardware offer or purchase text, propose reviewable corrections for likely brand or model variants, and generate validated category CSV files for the existing market import workflow. Use for 微信报价整理、行情报价识别、采购价或售价提取、以及 GPU、CPU、内存和硬盘行情导入准备，不用于联系人或聊天记录管理
metadata:
  version: "0.3.1"
---

# WeChat Quote Extractor

Turn pasted quote text into reviewed market candidates and import-ready CSV files. The first release boundary ends at local CSV generation. Never upload to the market backend or call an import API unless the user separately requests and authorizes it

## References

Read [business-rules.md](references/business-rules.md) before interpreting quote text

Read [structured-schema.md](references/structured-schema.md) before presenting candidates or generating CSV files

Read [product-model-map.csv](references/product-model-map.csv) when resolving a product to the import dictionary

Read [brand-alias-map.csv](references/brand-alias-map.csv) when normalizing brands. Only mappings marked `confirmed` may be applied automatically

Read [release-manifest.json](references/release-manifest.json) before building a batch. Copy all four version values into the structured batch

Read [examples.md](references/examples.md) when the source contains paragraph defaults, abbreviations, probable typos, purchase prices, USD, quantities, years, DC markers, kits, or unrelated products

Read [release-process.md](references/release-process.md) only when collecting feedback, changing mappings, packaging a release, or distributing the Skill to colleagues

## Workflow

1. Keep the pasted text unchanged as a transient reference; do not create contact or chat-history objects
2. Create a cleaned working copy by decoding harmless HTML entities, removing decorative emoji, normalizing whitespace, and preserving business-bearing tokens
3. Segment sections and product lines, resolve inherited context, and extract literal fields before deciding eligibility
4. Resolve product identity using the product map, confirmed alias map, source attributes, and semantic judgment
5. If the wording is likely a typo, shorthand, or unconfirmed alias, propose mapped candidates with reasons. Do not silently replace the source wording
6. Ignore clearly unrelated products. Do not retain or ask about them unless the user requests a full audit
7. Classify relevant candidates as `eligible`, `needs_confirmation`, or `excluded`, then show one complete preview
8. Ask all material clarification questions together. A user's answer may resolve only the current batch; it must not modify Skill files or shared dictionaries
9. Rebuild the preview after confirmation and run deterministic validation
10. Generate CSV files from `eligible` records with `scripts/build-import-csv.py`
11. Return generated files plus counts of eligible, pending, excluded, and written records

## Decision boundary

- The model may recognize varied wording and propose candidates; it may not invent a product, brand, price, tax status, or mapping
- Automatic normalization is limited to formatting differences and confirmed entries in `brand-alias-map.csv`
- A likely correction that changes brand or model identity requires user confirmation for the current batch
- Current-batch confirmation may produce an eligible row only when it resolves to one existing `product_id`
- A runtime correction is feedback, not a dictionary update. Never edit this Skill because a user accepts one suggestion during extraction
- Formal mapping and rule changes happen only through the reviewed release process

## Stable import constraints

- Unmarked currency is CNY
- Use paste time when the source has no explicit quote time
- Missing condition is allowed and produces an empty `货况` cell
- For GPU, CPU, and memory, the only non-empty output conditions are `全新` and `拆机`. Normalize `拆新`, `拆机新`, `几成新`, and specific percentage-new expressions such as `九成新` or `9成新` to `拆机`
- A price with `x` or `X` replacing digits is invalid; multiplication such as `25800*10张` is not masking
- Explicit sell and purchase prices can be market evidence; a request for a quote without a concrete price cannot
- USD located in Hong Kong is converted with the official applicable USD/CNY central parity rate multiplied by `1.13`, then rounded to a whole yuan using decimal half-up
- Do not generate a hard-disk CSV until its category code and import template are confirmed
- Do not write unresolved, out-of-scope, or unmapped records to CSV
- Product names written to CSV must exactly match the current product map

## CSV generation

Prepare a UTF-8 JSON file following [structured-schema.md](references/structured-schema.md), including versions from the release manifest, then run

```powershell
python scripts/build-import-csv.py --input <records.json> --output-dir <output-directory>
```

Merge with an existing same-day category file only after the user explicitly confirms exact-five-field deduplication

```powershell
python scripts/build-import-csv.py --input <records.json> --output-dir <output-directory> --existing-dir <existing-csv-directory>
```

Refresh the product dictionary only as part of a reviewed release

```powershell
python scripts/refresh-product-map.py --input <market-products.csv> --output references/product-model-map.csv
```

## Output boundary

CSV output contains exactly

```text
日期时间,产品名型号,报价,税务状态,货况
```

Use one file per date and category named `yy-MM-dd_category.csv`

Do not include contacts, chat history, direction, quantity, warehouse, warranty, year, batch, DC, extra specifications, issues, candidates, confidence, feedback, or version fields in the CSV
