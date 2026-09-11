# Examples

## Mixed memory sale text

Input

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
| 镁光 64G 4800, 17000 CNY, 含税, 拆机 | `eligible` after paste time is applied | `22年` and `深圳仓` are retained internally only |
| 镁光 48G 6400, 1400 USD, 全新 | `excluded` | Product is absent from the current product-model map; tax status is also missing |
| 三星 128G 6400, 4550 USD, 全新 | `excluded` | Product is absent from the current product-model map; tax status is also missing |
| 三星 32G 6400 purchase request | `excluded` | No concrete purchase price |

Quantities are recognized but never used as prices

## Paragraph defaults and aliases

Input

```text
【特价出内存】
默认拆机 质保一年
三星 64g 2S2R4 2666 含税 2990
SK 32g 2R4 3200 含税 2650
MT 32G 2R8 2933 含税 1750
冰刃24*2 6000 c28 黑白 4588/套 有40套
```

Expected interpretation

| Candidate | Status | Reason |
|---|---|---|
| 三星 64G 2666, 2990 CNY, 含税, 拆机 | `eligible` after paste time is applied | `2S2R4` is recognized but omitted from product name |
| 海力士 32G 3200, 2650 CNY, 含税, 拆机 | `eligible` after paste time is applied | `SK` normalizes to `海力士`; `2R4` is omitted |
| MT 32G 2933, 1750, 含税, 拆机 | `needs_confirmation` | `MT` must not normalize automatically |
| 冰刃 kit | `excluded` | Product is outside current market scope |

## Purchase price versus request for price

```text
采购 三星32G6400 未税 2600收100条
```

This contains an explicit purchase price and may become market evidence after paste time is applied. Currency defaults to CNY and missing condition is allowed

```text
采购 三星32G6400 未税 接有货麻烦带数量报价
```

This has no price and must be excluded from the market CSV

## Multi-category input

Parse all candidates first, then group by category. Do not create one file per sentence

If one inseparable bundle price covers multiple categories, exclude or ask for component prices rather than splitting the total

## Masked price, optional condition, DC, and USD

```text
三星64G 5600 25+ 现货800条 含税18x00
镁光48G6400香港仓 1400USD 含税
PRO6000MAX-Q 含税110000
```

Expected interpretation

| Candidate | Status | Reason |
|---|---|---|
| 三星 64G 5600 | `excluded` | `18x00` is a masked price; `25+` is retained as DC only |
| 镁光 48G 6400, 1400USD, 含税, empty condition | `excluded` | Product is absent from the current product-model map |
| PRO6000MAX-Q, 110000 CNY, 含税, empty condition | `needs_confirmation` | Potential map match requires the missing `96G` attribute before canonical output can be selected |

## Hong Kong USD conversion

For a mapped Hong Kong quote of `1400USD`, a recorded same-day USD/CNY rate of `7.1300`, and factor `1.13`, the computed amount is `11279.66` and the final CNY quote is `11280`

The CSV contains the integer CNY result only. The USD amount, rate, official publication date, direct official URL, factor, and rounding rule stay in the structured result for review

If the quote is pasted on a weekend, use the latest rate officially published before that paste time and store that earlier publication date. Do not fabricate a weekend rate date
