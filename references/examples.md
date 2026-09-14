# Examples

Examples illustrate decisions; they are not permanent alias rules

## Mixed memory sale text

```text
卖货
镁光 64G 4800 22年 400条含税17000深圳仓拆机
镁光48G6400香港仓1400USD数量2200条全新
三星128G6400香港仓DC26 4550USD数量1200全新
采购：三星32G6400未税接有货麻烦带数量报价
```

Expected interpretation

| Candidate | Status | Reason |
|---|---|---|
| 镁光 64G 4800, 17000 CNY, 含税, 拆机 | Eligible after paste time | `22年` is used transiently then discarded; `深圳仓` may remain for location context |
| 镁光 48G 6400, 1400 USD, 全新 | Excluded or pending | No current mapped product; tax is also missing |
| 三星 128G 6400, 4550 USD, 全新 | Excluded or pending | No current mapped product; tax is also missing |
| 三星 32G 6400 purchase request | Excluded | No concrete purchase price |

Quantities are recognized transiently to avoid treating them as prices, then discarded before the finalized batch

## Paragraph defaults and confirmed alias

```text
【特价出内存】
默认拆机 质保一年
三星 64g 2S2R4 2666 含税 2990
SK 32g 2R4 3200 含税 2650
MT 32G 2R8 2933 含税 1750
```

Expected interpretation

| Candidate | Status | Reason |
|---|---|---|
| 三星 64G 2666 | Eligible after paste time | Layout is used during extraction, omitted from the product name, then discarded |
| 海力士 32G 3200 | Eligible after paste time | `SK` is a confirmed alias in the current alias map |
| 镁光 32G 2933 | Eligible after paste time | `MT` is a confirmed alias for `镁光` in the current alias map |

From version `0.3.1`, `MT` normalizes to `镁光` automatically. Earlier versions remain unchanged in Git history

## Typo and shorthand proposal

```text
4090 24G 窝轮 拆机工包 含税25800*10张
```

If the map contains `RTX 4090 24G 涡轮` and the remaining source attributes agree, propose that mapped product and explain that `窝轮` may be a typo for `涡轮`. Keep the row `needs_confirmation` until the user confirms it

The confirmation applies only to this batch. A future occurrence must be evaluated again unless a later reviewed release adds a reusable normalization rule

```text
PRO6000MAX-Q 含税110000
```

If multiple mapped products or one mapped product with a required capacity remain possible, ask for the missing capacity rather than guessing

## Ambiguous brand or model

When a mistyped brand plus capacity and frequency point to several mapped rows, show the smallest useful candidate list and ask for the discriminator. Do not ask the user to approve a broad permanent alias

When one raw brand appears repeatedly in feedback, record that as a proposal for a future reviewed release. Runtime acceptance still does not edit the Skill

## CPU without an explicit brand

```text
6530 含税 12800
```

When the complete model expression uniquely matches `Intel 6530` in the current product map, infer `Intel`, record `model_inferred` with a concrete reason, and process the row without asking for the omitted brand

This example does not create a fixed `6530 → Intel` rule. Apply the same semantic procedure to every recognizable Intel or AMD CPU expression

- If the model clearly identifies Intel or AMD but the resulting product is absent from the current map, mark `product_not_in_map` and do not ask for brand confirmation
- If the model does not determine a brand, maps to multiple products, or lacks a required suffix or discriminator, use `needs_confirmation`
- Never default all bare numeric CPU models to Intel

## Clearly unrelated product

If a line is clearly outside CPU, GPU, memory, and the currently supported disk scope, ignore it before building quote records. Do not preserve a named exclusion list for each unrelated consumer product

If the text could plausibly be an in-scope product written incorrectly, do not ignore it. Propose candidates or mark it unresolved according to the product map

## Purchase price versus request for price

```text
采购 三星32G6400 未税 2600收100条
```

This contains an explicit purchase price and may become market evidence after paste time is applied. Currency defaults to CNY and missing condition is allowed

```text
采购 三星32G6400 未税 接有货麻烦带数量报价
```

This has no concrete price and cannot enter the market CSV

## Tax-status abbreviation and adjacent numbers

```text
镁光64G 3200 28条 WS 4200
```

Expected processing

| Stage | Result |
|---|---|
| Transient extraction | Recognize `28条` as quantity so it is not mistaken for price |
| Final product | `镁光 64G 3200` |
| Final tax evidence | `tax_status_raw=WS`, `tax_status=未税` |
| Final price | `4200` CNY |
| Final condition | Missing; keep empty |

Discard `28条` before creating the finalized batch. `WS` is a confirmed tax alias and matches case-insensitively. This standalone line does not by itself establish sell or purchase direction; inherit direction from valid surrounding context or ask for it before CSV generation

## Tax inclusion versus invoice correspondence

```text
默认拆机 质保一年
含税不对应
三星 64G 2666 2990
```

The inherited tax status is `含税`. `不对应` describes invoice correspondence, not whether the quoted price includes tax, so it does not trigger confirmation

Retain only `tax_status_raw=含税` and `tax_status=含税` in the finalized row. Discard `质保一年` and the invoice-correspondence wording. The same result applies to `含税票不对应` and `含税开其他品类发票`

`发票不对应` by itself contains no tax-inclusion signal and therefore cannot establish `含税` or `未税`

## Multi-category input

Parse all candidates first, then group eligible rows by category. Do not create one file per sentence

If one inseparable bundle price covers multiple categories, exclude it or ask for component prices rather than splitting the total

## Masked price and optional condition

```text
三星64G 5600 25+ 现货800条 含税18x00
镁光64G 4800 现货540条 含税17000
```

- `18x00` is a masked price and the row is excluded until replaced by an exact amount
- `25+` is treated as a transient DC or batch signal and discarded before the finalized batch
- `现货` does not imply `全新` or `拆机`
- The second row may use an empty condition when all other fields are eligible

## Condition normalization

For GPU, CPU, and memory, preserve the raw expression, classify its meaning, and normalize the final condition as follows

| Raw expression | Classification | Final `condition` |
|---|---|---|
| `全新` | `explicit_new` | `全新` |
| `拆机`, `二手`, `旧货` | `explicit_not_new` | `拆机` |
| `拆新`, `拆机新`, `翻新` | `explicit_not_new` | `拆机` |
| `几成新`, `九成新`, `9成新` | `explicit_not_new` | `拆机` |
| No condition wording | `missing` | null |
| Wording mentions condition but does not establish new or non-new | `ambiguous` | Needs confirmation |

These phrases are examples, not an allowlist. Any explicit wording that clearly indicates a non-brand-new state belongs to `explicit_not_new` and writes `拆机`

Except for the memory DC rule below, do not infer condition from `现货`, warehouse, packaging, year, DC, or quantity

## Memory DC condition default

```text
三星64G 4800 DC22+ 含税17000
海力士64G 5600 22 含税18000
镁光64G 4800 22+ 全新 含税17500
```

Expected interpretation

| Candidate | DC interpretation | Final condition |
|---|---|---|
| 三星 64G 4800 | `DC22+` is explicit DC | `拆机` |
| 海力士 64G 5600 | Bare `22` is DC from its memory-product position and context | `拆机` |
| 镁光 64G 4800 | `22+` is DC, but the row explicitly says `全新` | `全新` |

Short forms such as `22` or `22+`, generally in the teens through `26`, are prompts for semantic recognition rather than a hard-coded list. Do not treat a nearby price, quantity, capacity, or frequency as DC solely because it falls within that range

After condition resolution, discard the DC token. Use `condition_classification=memory_dc_default` for the first two rows and `explicit_new` for the third

## Current-batch duplicate removal

If two cleaned candidates normalize to the same date-time, mapped product name, CNY price, tax status, and condition, keep only the first CSV row

For example, `2650` and `2650.00` become the same price, and `含税` and `含税不对应` both become `含税`. When all other final CSV fields also match, the second row is removed as a duplicate

A different price, tax status, condition, mapped product, or date-time remains a separate row. Historical-file merging is still performed only when the user explicitly supplies `--existing-dir`

## Hong Kong USD conversion

For a mapped Hong Kong quote of `1400USD`, a recorded applicable USD/CNY rate of `7.1300`, and factor `1.13`, the computed amount is `11279.66` and the final CNY quote is `11280`

The CSV contains only the integer CNY result. The USD amount, rate, official publication date, direct official URL, factor, and rounding rule remain in the structured batch

If pasted on a weekend or before that day's publication, use the latest rate officially published on or before the paste time and store its actual publication date
