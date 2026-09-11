---
name: wechat-quote-extractor
description: Extract structured market quotes from pasted Chinese hardware offer or purchase text, resolve ambiguities, and generate validated category CSV files for the existing market import workflow. Use for 微信报价整理、行情报价识别、采购价或售价提取、以及 GPU、CPU、内存和硬盘行情导入准备，不用于联系人或聊天记录管理
---

# WeChat Quote Extractor

## Purpose

Turn one or more pasted quote-text blocks into reviewed market candidates and, only after ambiguities are resolved, import-ready CSV files

The first release ends at local CSV generation. Never upload to the market backend or call an import API unless the user separately requests and authorizes that action

## Required references

Read [business-rules.md](references/business-rules.md) before interpreting quote text

Read [structured-schema.md](references/structured-schema.md) before producing structured candidates or CSV files

Read [examples.md](references/examples.md) when the input contains paragraph defaults, abbreviations, purchase prices, USD, quantities, years, DC markers, kits, or excluded products

Read [product-model-map.csv](references/product-model-map.csv) before resolving product names. It is the replaceable product dictionary derived from the market-products export

## Workflow

1. Keep the pasted text unchanged as a transient raw reference; do not create contact or chat-history objects
2. Build a cleaned working copy by decoding harmless HTML entities, removing decorative emoji, normalizing whitespace and line breaks, and preserving every business-bearing token
3. Segment the cleaned copy into sections and candidate rows, then resolve inherited context such as category, sell or purchase direction, tax status, and condition
4. Perform first-pass field extraction for product wording, price, currency, quantity, tax, condition, DC/batch, warehouse, and extra specifications
5. Perform second-pass business-signal resolution to distinguish price from quantity or total, validate paragraph inheritance, reject masked prices, and normalize only confirmed aliases
6. Resolve each candidate to exactly one row in `product-model-map.csv` and use its `csv_product_name`. Exclude an unmatched candidate and ask for missing differentiating attributes when multiple rows remain possible
7. Run deterministic eligibility and CSV-contract validation; do not use the second pass to invent missing facts
8. Classify every candidate as `eligible`, `needs_confirmation`, or `excluded`
9. Show a complete preview, including excluded rows and reasons, with a short source excerpt when it helps verification
10. Ask all material clarification questions together rather than interrupting once per row
11. Apply the user's answers and rebuild the preview
12. Generate CSV files only from `eligible` records by running `scripts/build-import-csv.py`
13. Return the generated files and a concise count of eligible, pending, excluded, and written records

## Non-negotiable rules

- Never invent a missing price, tax status, brand, capacity, frequency, category, or price unit
- Treat an unmarked currency as CNY
- Use the time when the user pastes the quote text as `quote_datetime` when the source has no explicit quote time
- Allow a missing condition and write an empty `货况` cell; do not infer `全新` or `拆机` from `现货`, warehouse, packaging, year, or DC text
- Treat a masked price containing `x` or `X` in place of price digits as invalid. Exclude it from CSV until the user replaces it with an exact numeric price. Do not confuse multiplication expressions such as `25800*10张` with masked prices
- `SK` normalizes to `海力士`
- `美光` normalizes to `镁光`
- Do not normalize `MT` to `镁光`; retain `MT` and mark the record `needs_confirmation`
- Recognize `2S2R4`, `2R4`, `2R8`, `4DR4`, and similar memory-layout tokens, but do not include them in the current product name
- Treat an explicit sell price or explicit purchase price as possible market evidence
- A request for a quote without a concrete price is not market evidence
- Exclude `冰刃` and `兵刃` products from the current market scope
- Do not write `needs_confirmation` or `excluded` records into CSV
- Do not generate a hard-disk CSV until its real category code and import template are confirmed
- For a USD quote located in Hong Kong, convert to CNY with `USD price × the current day's USD/CNY rate × 1.13`; write only the resulting CNY amount to CSV
- Use the RMB central parity rate published by the China Foreign Exchange Trade System under authorization from the People's Bank of China. On a non-trading day or before that day's publication, use the latest official publication available at the paste time and record its actual publication date and official URL
- Round the converted CNY amount to the nearest whole yuan using decimal half-up rounding
- Do not generate a USD-derived row until the exchange-rate value, date, and source are recorded for that batch
- Preserve DC/year/batch, warehouse, and region in the structured result, but do not add them to the product name or CSV and do not block an otherwise eligible record
- Do not write a product that cannot be resolved to the bundled product-model map
- Keep sell or purchase direction in the structured result even though the five-column CSV cannot preserve it

## CSV generation

Prepare a UTF-8 JSON file that follows [structured-schema.md](references/structured-schema.md), then run

```powershell
python scripts/build-import-csv.py --input <records.json> --output-dir <output-directory>
```

Merge with existing same-day category files only after the user explicitly confirms the current exact-five-field deduplication rule

```powershell
python scripts/build-import-csv.py --input <records.json> --output-dir <output-directory> --existing-dir <existing-csv-directory>
```

The deterministic script owns validation, grouping, optional merge, exact-row deduplication, encoding, headers, and filenames. The model owns semantic extraction and clarification

Refresh the bundled model map when a new market-products export is supplied

```powershell
python scripts/refresh-product-map.py --input <market-products.csv> --output references/product-model-map.csv
```

## Output boundary

CSV output contains exactly

```text
日期时间,产品名型号,报价,税务状态,货况
```

Use one file per date and category with the filename `yy-MM-dd_category.csv`

Do not include contacts, chat history, direction, quantity, warehouse, warranty, year, batch, DC, extra specifications, issues, or confidence fields in the CSV
