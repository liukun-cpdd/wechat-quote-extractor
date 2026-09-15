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

## Shared memory quote across brands

```text
三星、SK 32G 4800 含税8200
```

When the brand position and shared scope are unambiguous, expand this into separate `三星 32G 4800` and `海力士 32G 4800` candidates. Both inherit price `8200`, tax status `含税`, and the memory default condition `拆机`, then match the product map independently

Expressions such as `三星/SK` or `三星和SK` may carry the same meaning. These are examples, not a delimiter allowlist; do not split separators inside models or configurations, and do not apply this memory rule to CPU or GPU lists. If one expanded brand is unmapped, exclude only that candidate. Missing price or tax evidence remains subject to the normal eligibility rules

## White-label and dual-label memory

```text
白牌 镁光 32G 5600 含税6800
三星联想双标64G 6400 含税7200
```

Ignore both lines before candidate persistence. They describe special white-label or dual-label memory whose price is not used as market evidence. Do not ask for missing attributes, include them in the preview, or write an exclusion record

The second line is one dual-label module, not a shared-price expression for separate Samsung and Lenovo products. This exclusion takes precedence over the shared multi-brand expansion rule. The examples illustrate the meaning and are not a fixed wording list

## GPU CSV product name

After `RTX 4090 24G 涡轮` resolves to one product-map row, keep that mapped name in the structured record and write `英伟达 RTX 4090 24G 涡轮` to the GPU CSV. Do not add the prefix before identity resolution or to CPU and memory rows

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
采购 三星32G6400 含税 2600收100条
```

This contains an explicit purchase price and may become market evidence after paste time is applied. Currency defaults to CNY and the missing memory condition normalizes to `拆机`

An otherwise identical quote marked `未税`, `不含税`, or `WS` is recognized but excluded from the current import with `untaxed_not_collected`

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
| Tax evidence | `tax_status_raw=WS`, `tax_status=未税` |
| Final price | `4200` CNY |
| Eligibility | `excluded` with `untaxed_not_collected`; no CSV row |

Discard `28条` before creating the finalized batch. `WS` is a confirmed tax alias and matches case-insensitively, but the current release records only tax-inclusive quotes

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
- The second row has no explicit `全新`, so memory condition is `拆机`

## Condition normalization

For GPU, CPU, and memory, preserve the raw expression, classify its meaning, and normalize the final condition as follows

| Raw expression | Classification | Final `condition` |
|---|---|---|
| `全新` | `explicit_new` | `全新` |
| `拆机`, `二手`, `旧货` | `explicit_not_new` | `拆机` |
| `拆新`, `拆机新`, `翻新` | `explicit_not_new` | `拆机` |
| `几成新`, `九成新`, `9成新` | `explicit_not_new` | `拆机` |
| CPU or memory with no condition wording | `missing` | `拆机` |
| CPU or memory with ambiguous condition wording | `ambiguous` | `拆机` |
| Ordinary GPU with no condition wording | `missing` | `全新` |
| GPU with ambiguous condition wording | `ambiguous` | Needs confirmation |
| GPU explicitly described as `整机` or `模组`, with no condition wording | `missing` | Excluded |

These phrases are examples, not an allowlist. Any explicit wording that clearly indicates a non-brand-new state belongs to `explicit_not_new` and writes `拆机`

For CPU and memory, only an applicable explicit `全新` statement produces `全新`. Do not treat `现货`, warehouse, packaging, year, DC, or quantity as that statement

For GPU, `整机` and `模组` directly identify special forms. Interpret equivalent descriptions semantically rather than through a fixed list. If a likely equivalent cannot be resolved, ask whether it is a special form; when a confirmed special form has no condition, use `special_gpu_missing_condition` and do not record it

## Memory DC recognition

```text
三星64G 4800 DC22+ 含税17000
海力士64G 5600 22 含税18000
镁光64G 4800 22+ 全新 含税17500
```

Expected interpretation

| Candidate | DC interpretation | Final condition |
|---|---|---|
| 三星 64G 4800 | `DC22+` is explicit DC | `拆机` because no `全新` appears |
| 海力士 64G 5600 | Bare `22` is DC from its memory-product position and context | `拆机` because no `全新` appears |
| 镁光 64G 4800 | `22+` is DC, but the row explicitly says `全新` | `全新` |

Short forms such as `22` or `22+`, generally in the teens through `26`, are prompts for semantic recognition rather than a hard-coded list. Do not treat a nearby price, quantity, capacity, or frequency as DC solely because it falls within that range

After extraction, discard the DC token. The first two rows use `condition_classification=missing`; the third uses `explicit_new`

## Daily snapshot duplicate removal

Use the latest earlier snapshot inside the same `yy-MM-dd` date directory as the only baseline. Carry its category files into the new timestamped directory and merge the current batch into affected categories

For example, `2650` and `2650.00` become the same price, and `含税` and `含税不对应` both become `含税`. When product, normalized price, tax status, and condition match, they represent one quote even if their date-times differ

Retain the row with the earlier date-time. A different product, price, tax status, or condition remains separate. A different date-time alone does not create a separate quote

## Hong Kong USD conversion

For a mapped Hong Kong quote of `1400USD`, a recorded applicable USD/CNY rate of `7.1300`, and factor `1.13`, the computed amount is `11279.66` and the final CNY quote is `11280`

The CSV contains only the integer CNY result. The USD amount, rate, official publication date, direct official URL, factor, and rounding rule remain in the structured batch

If pasted on a weekend or before that day's publication, use the latest rate officially published on or before the paste time and store its actual publication date
