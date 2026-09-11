#!/usr/bin/env python3
"""Validate structured quote candidates and build market-import CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HEADERS = ["日期时间", "产品名型号", "报价", "税务状态", "货况"]
CATEGORY_CODES = {"gpu": "gpu", "cpu": "cpu", "memory": "memory"}
ALLOWED_DIRECTIONS = {"sell", "purchase"}
ALLOWED_TAX = {"含税", "未税"}
ALLOWED_CONDITIONS = {"", "全新", "拆机"}
EXCLUDED_PRODUCT_TOKENS = ("冰刃", "兵刃")
EXTRA_SPEC_PATTERN = re.compile(r"(?:\d+S)?\d+R\d+|\d+DR\d+", re.IGNORECASE)
PRODUCT_MAP_HEADERS = [
    "product_id",
    "category",
    "canonical_product_name",
    "csv_product_name",
    "source_condition",
]
DEFAULT_PRODUCT_MAP = Path(__file__).resolve().parent.parent / "references" / "product-model-map.csv"
USD_CONVERSION_FACTOR = Decimal("1.13")
OFFICIAL_RATE_SOURCE = "中国人民银行授权中国外汇交易中心公布的人民币汇率中间价"
OFFICIAL_RATE_HOSTS = {"www.pbc.gov.cn", "pbc.gov.cn", "www.chinamoney.com.cn", "chinamoney.com.cn"}


class ValidationError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build category CSV files from reviewed structured quote records"
    )
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 JSON input")
    parser.add_argument("--output-dir", required=True, type=Path, help="CSV output directory")
    parser.add_argument(
        "--product-map",
        type=Path,
        default=DEFAULT_PRODUCT_MAP,
        help="Product-model map CSV; defaults to the bundled map",
    )
    parser.add_argument(
        "--existing-dir",
        type=Path,
        help="Optional same-day CSV directory to merge using exact five-field deduplication",
    )
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"无法读取JSON输入: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValidationError("JSON根对象必须包含records数组")
    return payload


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def positive_decimal(value: Any, field_name: str) -> Decimal:
    raw = clean_text(value)
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name}不是有效数字: {raw or '<空>'}") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(f"{field_name}必须为正数: {raw or '<空>'}")
    return amount


def normalize_price(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        raise ValidationError("报价为空")
    amount = positive_decimal(raw, "报价")
    normalized = format(amount, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def validate_datetime(value: Any) -> tuple[str, str]:
    raw = clean_text(value)
    try:
        parsed = datetime.strptime(raw, "%y/%m/%d/%H:%M")
    except ValueError as exc:
        raise ValidationError(f"日期时间必须符合yy/MM/dd/HH:mm: {raw or '<空>'}") from exc
    return raw, parsed.strftime("%y-%m-%d")


def load_product_map(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != PRODUCT_MAP_HEADERS:
                raise ValidationError(f"产品映射表表头不匹配: {path}")
            mapping: dict[tuple[str, str], tuple[str, str]] = {}
            for line_number, row in enumerate(reader, start=2):
                category = clean_text(row["category"])
                product_id = clean_text(row["product_id"])
                csv_name = clean_text(row["csv_product_name"])
                if category not in CATEGORY_CODES or not product_id or not csv_name:
                    raise ValidationError(f"产品映射表第{line_number}行字段无效")
                id_key = (category, product_id)
                if id_key in mapping:
                    raise ValidationError(f"产品映射表产品ID重复: {category}/{product_id}")
                mapping[id_key] = (csv_name, clean_text(row["canonical_product_name"]))
            return mapping
    except OSError as exc:
        raise ValidationError(f"无法读取产品映射表 {path}: {exc}") from exc


def load_usd_conversion(payload: dict[str, Any]) -> tuple[Decimal, str, str, str, Decimal]:
    conversion = payload.get("conversion")
    if not isinstance(conversion, dict):
        raise ValidationError("存在USD报价时，JSON根对象必须包含conversion对象")
    rate = positive_decimal(conversion.get("usd_cny_rate"), "USD/CNY汇率")
    rate_date = clean_text(conversion.get("rate_date"))
    try:
        datetime.strptime(rate_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("汇率日期必须符合YYYY-MM-DD") from exc
    rate_source = clean_text(conversion.get("rate_source"))
    if rate_source != OFFICIAL_RATE_SOURCE:
        raise ValidationError("USD汇率来源必须是人民银行授权公布的人民币汇率中间价")
    rate_source_url = clean_text(conversion.get("rate_source_url"))
    parsed_url = urlparse(rate_source_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in OFFICIAL_RATE_HOSTS:
        raise ValidationError("USD汇率必须记录人民银行或中国外汇交易中心的官方链接")
    factor = clean_text(conversion.get("factor"))
    if factor and factor != "1.13":
        raise ValidationError("USD转换系数必须为1.13")
    rounding_text = clean_text(conversion.get("rounding")) or "1"
    if rounding_text != "1":
        raise ValidationError("USD换算必须四舍五入到整数元")
    return rate, rate_date, rate_source, rate_source_url, Decimal("1")


def validate_eligible(
    record: Any,
    index: int,
    payload: dict[str, Any],
    product_map: dict[tuple[str, str], tuple[str, str]],
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(record, dict):
        raise ValidationError(f"第{index}条记录必须是对象")
    if record.get("eligibility") != "eligible":
        raise ValidationError(f"第{index}条记录不是eligible，不应进入验证函数")

    issues = record.get("issues", [])
    if issues not in (None, []) and len(issues) > 0:
        raise ValidationError(f"第{index}条eligible记录仍有未解决issues")

    direction = clean_text(record.get("direction"))
    if direction not in ALLOWED_DIRECTIONS:
        raise ValidationError(f"第{index}条方向必须是sell或purchase")

    category = clean_text(record.get("category"))
    if category not in CATEGORY_CODES:
        raise ValidationError(f"第{index}条品类尚不支持生成CSV: {category or '<空>'}")

    brand_raw = clean_text(record.get("brand_raw"))
    product_name = clean_text(record.get("product_name"))
    if not product_name:
        raise ValidationError(f"第{index}条产品名型号为空")
    if brand_raw.upper() == "MT" or re.match(r"^MT(?:\s|$)", product_name, re.IGNORECASE):
        raise ValidationError(f"第{index}条MT品牌未经确认，不能进入CSV")
    if any(token in product_name for token in EXCLUDED_PRODUCT_TOKENS):
        raise ValidationError(f"第{index}条产品属于已排除范围")
    if EXTRA_SPEC_PATTERN.search(product_name):
        raise ValidationError(f"第{index}条产品名包含当前不应写入的附加规格")
    if "\n" in product_name or "\r" in product_name:
        raise ValidationError(f"第{index}条产品名不能包含换行")

    matched_product_id = clean_text(record.get("matched_product_id"))
    mapped = product_map.get((category, matched_product_id))
    if mapped is None:
        raise ValidationError(f"第{index}条产品未匹配当前型号映射表")
    if product_name != mapped[0]:
        raise ValidationError(
            f"第{index}条产品名必须使用映射表写法: {mapped[0]}"
        )

    quote_datetime, file_date = validate_datetime(record.get("quote_datetime"))
    price = normalize_price(record.get("price"))

    currency = clean_text(record.get("currency")).upper() or "CNY"
    if currency not in {"CNY", "USD"}:
        raise ValidationError(f"第{index}条币种必须是CNY或USD")
    csv_price = price
    if currency == "USD":
        warehouse = clean_text(record.get("warehouse"))
        region = clean_text(record.get("region"))
        if "香港" not in f"{warehouse} {region}":
            raise ValidationError(f"第{index}条USD报价未确认货在香港")
        rate, rate_date, _, _, rounding_step = load_usd_conversion(payload)
        quote_date = datetime.strptime(quote_datetime, "%y/%m/%d/%H:%M").strftime("%Y-%m-%d")
        if rate_date > quote_date:
            raise ValidationError(f"第{index}条USD汇率发布日期晚于报价日期")
        converted = (Decimal(price) * rate * USD_CONVERSION_FACTOR).quantize(
            rounding_step, rounding=ROUND_HALF_UP
        )
        csv_price = normalize_price(converted)

    tax_status = clean_text(record.get("tax_status"))
    if tax_status not in ALLOWED_TAX:
        raise ValidationError(f"第{index}条税务状态无效: {tax_status or '<空>'}")

    condition = clean_text(record.get("condition"))
    if condition not in ALLOWED_CONDITIONS:
        raise ValidationError(f"第{index}条货况无效: {condition or '<空>'}")

    row = (quote_datetime, product_name, csv_price, tax_status, condition)
    return f"{file_date}_{CATEGORY_CODES[category]}.csv", row


def read_existing(path: Path) -> list[tuple[str, ...]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != HEADERS:
                raise ValidationError(f"已有CSV表头不匹配: {path}")
            rows = []
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(HEADERS):
                    raise ValidationError(f"已有CSV第{line_number}行列数错误: {path}")
                rows.append(tuple(row))
            return rows
    except OSError as exc:
        raise ValidationError(f"无法读取已有CSV {path}: {exc}") from exc


def write_csv(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(HEADERS)
            writer.writerows(rows)
    except OSError as exc:
        raise ValidationError(f"无法写入CSV {path}: {exc}") from exc


def main() -> int:
    args = parse_args()
    try:
        payload = load_payload(args.input)
        product_map = load_product_map(args.product_map)
        grouped: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        counts = {"eligible": 0, "needs_confirmation": 0, "excluded": 0}

        for index, record in enumerate(payload["records"], start=1):
            if not isinstance(record, dict):
                raise ValidationError(f"第{index}条记录必须是对象")
            eligibility = record.get("eligibility")
            if eligibility not in counts:
                raise ValidationError(f"第{index}条eligibility无效: {eligibility}")
            counts[eligibility] += 1
            if eligibility == "eligible":
                filename, row = validate_eligible(record, index, payload, product_map)
                grouped[filename].append(row)

        outputs = []
        total_written = 0
        for filename, new_rows in sorted(grouped.items()):
            prior_rows = []
            if args.existing_dir is not None:
                prior_rows = read_existing(args.existing_dir / filename)
            merged = []
            seen = set()
            for row in prior_rows + new_rows:
                if row not in seen:
                    seen.add(row)
                    merged.append(row)
            output_path = args.output_dir / filename
            write_csv(output_path, merged)
            total_written += len(merged)
            outputs.append(
                {
                    "path": str(output_path.resolve()),
                    "existing_rows": len(prior_rows),
                    "new_rows": len(new_rows),
                    "written_rows": len(merged),
                }
            )

        print(
            json.dumps(
                {"counts": counts, "written_rows": total_written, "outputs": outputs},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except ValidationError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
