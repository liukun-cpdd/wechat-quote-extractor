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
| 镁光 64G 4800, 17000 CNY, 含税, 拆机 | Eligible after paste time | `22年` and `深圳仓` remain internal |
| 镁光 48G 6400, 1400 USD, 全新 | Excluded or pending | No current mapped product; tax is also missing |
| 三星 128G 6400, 4550 USD, 全新 | Excluded or pending | No current mapped product; tax is also missing |
| 三星 32G 6400 purchase request | Excluded | No concrete purchase price |

Quantities are recognized but never used as prices

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
| 三星 64G 2666 | Eligible after paste time | Layout is preserved outside product name |
| 海力士 32G 3200 | Eligible after paste time | `SK` is a confirmed alias in the current alias map |
| MT 32G 2933 | Needs confirmation | `MT` is not a confirmed alias; propose only plausible mapped products |

If the user selects one proposed mapped product for `MT`, mark that row `user_confirmed` for the current batch. Do not add `MT` to the alias map

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

## Multi-category input

Parse all candidates first, then group eligible rows by category. Do not create one file per sentence

If one inseparable bundle price covers multiple categories, exclude it or ask for component prices rather than splitting the total

## Masked price and optional condition

```text
三星64G 5600 25+ 现货800条 含税18x00
镁光64G 4800 现货540条 含税17000
```

- `18x00` is a masked price and the row is excluded until replaced by an exact amount
- `25+` remains DC or batch information only
- `现货` does not imply `全新` or `拆机`
- The second row may use an empty condition when all other fields are eligible

## Hong Kong USD conversion

For a mapped Hong Kong quote of `1400USD`, a recorded applicable USD/CNY rate of `7.1300`, and factor `1.13`, the computed amount is `11279.66` and the final CNY quote is `11280`

The CSV contains only the integer CNY result. The USD amount, rate, official publication date, direct official URL, factor, and rounding rule remain in the structured batch

If pasted on a weekend or before that day's publication, use the latest rate officially published on or before the paste time and store its actual publication date
