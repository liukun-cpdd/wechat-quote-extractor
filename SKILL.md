---
name: wechat-quote-extractor
description: Extract structured market quotes from pasted Chinese hardware offer or purchase text, propose reviewable corrections for likely brand or model variants, and generate validated category CSV files for the existing market import workflow. Use for 微信报价整理、行情报价识别、采购价或售价提取、以及 GPU、CPU、内存和硬盘行情导入准备，不用于联系人或聊天记录管理
metadata:
  version: "0.5.0"
---

# WeChat Quote Extractor

Turn pasted quote text into reviewed market candidates and import-ready CSV files. The first release boundary ends at local CSV generation. Never upload to the market backend or call an import API unless the user separately requests and authorizes it

## References

Read [business-rules.md](references/business-rules.md) before interpreting quote text

Read [structured-schema.md](references/structured-schema.md) before presenting candidates or generating CSV files

Read [product-model-map.csv](references/product-model-map.csv) when resolving a product to the import dictionary

Read [brand-alias-map.csv](references/brand-alias-map.csv) when normalizing brands. Only mappings marked `confirmed` may be applied automatically

Read [tax-alias-map.csv](references/tax-alias-map.csv) when normalizing tax wording. Only mappings marked `confirmed` may be applied automatically

Read [release-manifest.json](references/release-manifest.json) before building a batch. Copy all version values into the structured batch

Read [examples.md](references/examples.md) when the source contains paragraph defaults, abbreviations, probable typos, purchase prices, USD, quantities, years, DC markers, kits, or unrelated products

Read [release-process.md](references/release-process.md) only when collecting feedback, changing mappings, packaging a release, or distributing the Skill to colleagues

## Workflow

1. Keep the pasted text unchanged as a transient reference; do not create contact or chat-history objects
2. Create a cleaned working copy by decoding harmless HTML entities, removing decorative emoji, normalizing whitespace, and preserving business-bearing tokens
3. Segment sections and product lines, resolve inherited context, and extract literal signals before deciding eligibility
4. Resolve product identity using the product map, confirmed alias map, source attributes, and semantic judgment. For a CPU without an explicit brand, infer Intel or AMD from the complete model expression before matching the map
5. If the wording is likely a typo, shorthand, or unconfirmed alias, propose mapped candidates with reasons. Do not silently replace the source wording
6. Ignore clearly unrelated products. Do not retain or ask about them unless the user requests a full audit
7. Discard extraction-only quantity, year, DC, batch, memory-layout, warranty, packing, and invoice-correspondence signals
8. Classify relevant candidates as `eligible`, `needs_confirmation`, or `excluded`, then show one complete preview
9. Ask all material clarification questions together. A user's answer may resolve only the current batch; it must not modify Skill files or shared dictionaries
10. Rebuild the preview after confirmation and run deterministic validation
11. Generate a complete timestamped daily snapshot from `eligible` records with `scripts/build-import-csv.py`
12. Return the snapshot path plus counts of eligible, pending, excluded, duplicates removed, and written records

## Decision boundary

- The model may recognize varied wording and propose candidates; it may not invent a product, brand, price, tax status, or mapping
- Automatic normalization is limited to formatting differences and confirmed entries in the relevant alias map
- CPU brand inference from a recognizable model is identity resolution, not alias creation. It is allowed only when the model identifies Intel or AMD and exactly one current product-map row matches
- A recognizable CPU brand with no current product-map match is `product_not_in_map`; do not ask the user to confirm an already identifiable brand
- A likely correction that changes brand or model identity requires user confirmation for the current batch
- Current-batch confirmation may produce an eligible row only when it resolves to one existing `product_id`
- A runtime correction is feedback, not a dictionary update. Never edit this Skill because a user accepts one suggestion during extraction
- Formal mapping and rule changes happen only through the reviewed release process

## Stable import constraints

- Unmarked currency is CNY
- `WS` is a confirmed tax-status alias for `未税`; matching is case-insensitive
- Tax status means only whether the quoted price includes tax. Any positive phrase containing `含税`, including invoice-mismatch wording, normalizes to `含税`; invoice correspondence is discarded
- Do not infer tax status when no explicit `含税`, `未税`, `不含税`, or confirmed tax alias appears
- Use paste time when the source has no explicit quote time
- For CPU and memory, write `全新` only when the applicable source explicitly states `全新`; otherwise write `拆机`
- For GPU, explicit brand-new wording writes `全新`, explicit non-new wording writes `拆机`, missing condition remains empty, and ambiguous condition requires confirmation
- DC forms such as `DC22+`, `22`, and `22+` remain semantic extraction cues only; do not retain them or use them to override an explicit `全新`
- A price with `x` or `X` replacing digits is invalid; multiplication such as `25800*10张` is not masking
- Explicit sell and purchase prices can be market evidence; a request for a quote without a concrete price cannot
- USD located in Hong Kong is converted with the official applicable USD/CNY central parity rate multiplied by `1.13`, then rounded to a whole yuan using decimal half-up
- Do not generate a hard-disk CSV until its category code and import template are confirmed
- Do not write unresolved, out-of-scope, or unmapped records to CSV
- Product names written to CSV must exactly match the current product map

## CSV generation

Prepare a UTF-8 JSON file following [structured-schema.md](references/structured-schema.md), including `batch_datetime` and versions from the release manifest. Confirm one snapshot root, then run

```powershell
python scripts/build-import-csv.py --input <records.json> --snapshot-root <confirmed-snapshot-root>
```

The generator creates a new time directory, inherits only the latest same-day snapshot, and starts fresh on a new date. Ask the user only when the snapshot root is unclear or the latest same-day baseline is not unique

Refresh the product dictionary only as part of a reviewed release

```powershell
python scripts/refresh-product-map.py --input <market-products.csv> --output references/product-model-map.csv
```

## Output boundary

CSV output contains exactly

```text
日期时间,产品名型号,报价,税务状态,货况
```

Each timestamped directory is a complete snapshot for that day. Inside it, use one file per category named `yy-MM-dd_category.csv`

Do not include contacts, chat history, direction, warehouse, issues, candidates, confidence, feedback, or version fields in the CSV

Quantity, year, batch, DC, memory layout, warranty, packaging, packing method, invoice correspondence, and invoice-description details are extraction-only. Do not retain them in the finalized structured batch or CSV

Deduplicate by `产品名型号`, `报价`, `税务状态`, and `货况`; `日期时间` is not part of the key. When the four fields match, retain the row with the earlier date-time
