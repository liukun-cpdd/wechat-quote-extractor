#!/usr/bin/env python3
"""Validate structured quote candidates and build market-import CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HEADERS = ["日期时间", "产品名型号", "报价", "税务状态", "货况"]
CATEGORY_CODES = {"gpu": "gpu", "cpu": "cpu", "memory": "memory"}
GPU_CSV_BRAND_PREFIX = "英伟达 "
ALLOWED_DIRECTIONS = {"sell", "purchase"}
ALLOWED_TAX = {"含税", "未税"}
ALLOWED_CONDITION_CLASSIFICATIONS = {
    "explicit_new",
    "explicit_not_new",
    "missing",
    "ambiguous",
}
ALLOWED_MATCH_METHODS = {
    "exact",
    "format_normalized",
    "confirmed_alias",
    "model_inferred",
    "user_confirmed",
}
ALLOWED_BRAND_RESOLUTION_METHODS = {
    "explicit",
    "confirmed_alias",
    "model_inferred",
    "user_confirmed",
}
CPU_BRANDS = {"Intel", "AMD"}
FORBIDDEN_FORMAL_RECORD_FIELDS = {
    "source_excerpt",
    "quantity",
    "year_or_batch",
    "dc",
    "extra_spec",
    "memory_layout",
    "warranty",
    "packaging",
    "packing_method",
    "invoice_matching",
    "invoice_details",
}
EXTRA_SPEC_PATTERN = re.compile(r"(?:\d+S)?\d+R\d+|\d+DR\d+", re.IGNORECASE)
PRODUCT_MAP_HEADERS = [
    "product_id",
    "category",
    "canonical_product_name",
    "csv_product_name",
    "source_condition",
]
BRAND_ALIAS_MAP_HEADERS = ["alias", "canonical_brand", "status", "version_added", "note"]
TAX_ALIAS_MAP_HEADERS = [
    "alias",
    "canonical_tax_status",
    "status",
    "version_added",
    "note",
]
RELEASE_VERSION_KEYS = [
    "skill_version",
    "ruleset_version",
    "product_map_version",
    "alias_map_version",
    "tax_map_version",
]
DEFAULT_PRODUCT_MAP = Path(__file__).resolve().parent.parent / "references" / "product-model-map.csv"
DEFAULT_ALIAS_MAP = Path(__file__).resolve().parent.parent / "references" / "brand-alias-map.csv"
DEFAULT_TAX_ALIAS_MAP = Path(__file__).resolve().parent.parent / "references" / "tax-alias-map.csv"
DEFAULT_RELEASE_MANIFEST = (
    Path(__file__).resolve().parent.parent / "references" / "release-manifest.json"
)
USD_CONVERSION_FACTOR = Decimal("1.13")
OFFICIAL_RATE_SOURCE = "中国人民银行授权中国外汇交易中心公布的人民币汇率中间价"
OFFICIAL_RATE_HOSTS = {"www.pbc.gov.cn", "pbc.gov.cn", "www.chinamoney.com.cn", "chinamoney.com.cn"}
SNAPSHOT_NAME_PATTERN = re.compile(
    r"^(?P<date>\d{2}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})(?:_.+)?$"
)
CSV_NAME_PATTERN = re.compile(r"^(?P<date>\d{2}-\d{2}-\d{2})_.+\.csv$", re.IGNORECASE)


class ValidationError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build category CSV files from reviewed structured quote records"
    )
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 JSON input")
    parser.add_argument(
        "--snapshot-root",
        required=True,
        type=Path,
        help="Confirmed root containing date folders and immutable timestamped snapshots",
    )
    parser.add_argument(
        "--product-map",
        type=Path,
        default=DEFAULT_PRODUCT_MAP,
        help="Product-model map CSV; defaults to the bundled map",
    )
    parser.add_argument(
        "--alias-map",
        type=Path,
        default=DEFAULT_ALIAS_MAP,
        help="Confirmed brand-alias map CSV; defaults to the bundled map",
    )
    parser.add_argument(
        "--tax-alias-map",
        type=Path,
        default=DEFAULT_TAX_ALIAS_MAP,
        help="Confirmed tax-status alias map CSV; defaults to the bundled map",
    )
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=DEFAULT_RELEASE_MANIFEST,
        help="Release version manifest JSON; defaults to the bundled manifest",
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


def format_csv_product_name(category: str, mapped_product_name: str) -> str:
    if category == "gpu" and not mapped_product_name.startswith(GPU_CSV_BRAND_PREFIX):
        return f"{GPU_CSV_BRAND_PREFIX}{mapped_product_name}"
    return mapped_product_name


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


def normalize_condition(record: dict[str, Any], index: int) -> str:
    raw = clean_text(record.get("condition_raw"))
    value = clean_text(record.get("condition"))
    classification = clean_text(record.get("condition_classification"))
    if classification not in ALLOWED_CONDITION_CLASSIFICATIONS:
        raise ValidationError(
            f"第{index}条condition_classification无效: {classification or '<空>'}"
        )
    category = clean_text(record.get("category"))
    defaults_to_disassembled = category in {"cpu", "memory"}
    if classification == "missing":
        if raw or value:
            raise ValidationError(f"第{index}条货况分类为missing但仍包含货况值")
        return "拆机" if defaults_to_disassembled else ""
    if classification == "ambiguous":
        if defaults_to_disassembled:
            if "全新" in raw or value == "全新":
                raise ValidationError(f"第{index}条默认拆机分类与全新货况冲突")
            return "拆机"
        raise ValidationError(f"第{index}条货况语义仍有歧义，不能进入CSV")
    if not raw:
        raise ValidationError(f"第{index}条明确货况缺少condition_raw")
    if classification == "explicit_new":
        if value not in {"", "全新"}:
            raise ValidationError(f"第{index}条全新分类与货况值冲突")
        return "全新"
    if value == "全新":
        raise ValidationError(f"第{index}条非全新分类与货况值冲突")
    return "拆机"


def normalize_tax_status(
    record: dict[str, Any], index: int, tax_aliases: dict[str, str]
) -> str:
    raw = clean_text(record.get("tax_status_raw"))
    value = clean_text(record.get("tax_status"))
    if not raw:
        raise ValidationError(f"第{index}条缺少明确税务状态原文信号")

    def resolve(token: str) -> str | None:
        compact = re.sub(r"\s+", "", token)
        if not compact:
            return None

        alias = tax_aliases.get(compact.casefold())
        if alias is not None:
            return alias

        has_untaxed = "未税" in compact or "不含税" in compact
        positive_text = compact.replace("不含税", "")
        has_taxed = "含税" in positive_text
        if has_taxed and has_untaxed:
            raise ValidationError(f"第{index}条同时包含含税与未税信号")
        if has_taxed:
            return "含税"
        if has_untaxed:
            return "未税"
        return None

    source_token = raw
    normalized = resolve(source_token)
    if normalized is None:
        raise ValidationError(f"第{index}条税务状态无效: {source_token or '<空>'}")
    if value:
        value_normalized = resolve(value)
        if value_normalized != normalized:
            raise ValidationError(f"第{index}条税务状态原文与归一值冲突")
    return normalized


def validate_formal_record_boundary(record: dict[str, Any], index: int) -> None:
    forbidden = sorted(FORBIDDEN_FORMAL_RECORD_FIELDS.intersection(record))
    if forbidden:
        raise ValidationError(
            f"第{index}条包含不得长期保存的辅助字段: {', '.join(forbidden)}"
        )


def validate_cpu_brand_resolution(
    record: dict[str, Any], index: int, mapped_product_name: str
) -> None:
    if clean_text(record.get("category")) != "cpu":
        return

    brand_raw = clean_text(record.get("brand_raw"))
    brand_normalized = clean_text(record.get("brand_normalized"))
    resolution_method = clean_text(record.get("brand_resolution_method"))
    inference_reason = clean_text(record.get("brand_inference_reason"))
    match_method = clean_text(record.get("match_method"))

    if brand_normalized not in CPU_BRANDS:
        raise ValidationError(f"第{index}条CPU品牌必须归一为Intel或AMD")
    if not mapped_product_name.casefold().startswith(
        f"{brand_normalized} ".casefold()
    ):
        raise ValidationError(f"第{index}条CPU品牌与映射表产品不一致")

    if not brand_raw:
        if resolution_method != "model_inferred" or match_method != "model_inferred":
            raise ValidationError(f"第{index}条无品牌CPU必须记录model_inferred解析依据")
        if not inference_reason:
            raise ValidationError(f"第{index}条无品牌CPU缺少brand_inference_reason")
        return

    if resolution_method not in ALLOWED_BRAND_RESOLUTION_METHODS:
        raise ValidationError(
            f"第{index}条brand_resolution_method无效: {resolution_method or '<空>'}"
        )
    if resolution_method == "model_inferred":
        raise ValidationError(f"第{index}条已出现品牌原文，不应标记为model_inferred")


def validate_datetime(value: Any) -> tuple[str, str]:
    raw = clean_text(value)
    try:
        parsed = datetime.strptime(raw, "%y/%m/%d/%H:%M")
    except ValueError as exc:
        raise ValidationError(f"日期时间必须符合yy/MM/dd/HH:mm: {raw or '<空>'}") from exc
    return raw, parsed.strftime("%y-%m-%d")


def load_batch_datetime(payload: dict[str, Any]) -> datetime:
    raw = clean_text(payload.get("batch_datetime"))
    try:
        return datetime.strptime(raw, "%y/%m/%d/%H:%M:%S")
    except ValueError as exc:
        raise ValidationError(
            f"batch_datetime必须符合yy/MM/dd/HH:mm:ss: {raw or '<空>'}"
        ) from exc


def select_daily_baseline(
    snapshot_root: Path, batch_datetime: datetime
) -> tuple[Path, Path | None]:
    if not snapshot_root.exists() or not snapshot_root.is_dir():
        raise ValidationError(f"快照输出根目录不存在或不是目录: {snapshot_root}")

    day_text = batch_datetime.strftime("%y-%m-%d")
    day_directory = snapshot_root / day_text
    if day_directory.exists() and not day_directory.is_dir():
        raise ValidationError(f"当日快照路径存在但不是目录: {day_directory}")
    target = day_directory / batch_datetime.strftime("%y-%m-%d_%H-%M-%S")
    if target.exists():
        raise ValidationError(f"本批快照目录已存在，禁止覆盖: {target}")

    candidates: list[tuple[datetime, Path]] = []
    unrecognized = []
    non_historical = []
    children = day_directory.iterdir() if day_directory.exists() else []
    for child in children:
        if not child.is_dir():
            continue
        match = SNAPSHOT_NAME_PATTERN.fullmatch(child.name)
        if match is None:
            if child.name.startswith(f"{day_text}_"):
                unrecognized.append(child.name)
            continue
        try:
            parsed = datetime.strptime(
                f"{match.group('date')}_{match.group('time')}",
                "%y-%m-%d_%H-%M-%S",
            )
        except ValueError:
            if match.group("date") == day_text:
                unrecognized.append(child.name)
            continue
        if parsed.strftime("%y-%m-%d") != day_text:
            continue
        if parsed >= batch_datetime:
            non_historical.append(child.name)
            continue
        candidates.append((parsed, child))

    if unrecognized:
        raise ValidationError(
            "无法唯一识别当日历史快照目录: " + ", ".join(sorted(unrecognized))
        )
    if non_historical:
        raise ValidationError(
            "本批时间必须晚于已有当日快照: " + ", ".join(sorted(non_historical))
        )
    if not candidates:
        return target, None

    latest_time = max(item[0] for item in candidates)
    latest = [path for parsed, path in candidates if parsed == latest_time]
    if len(latest) != 1:
        raise ValidationError(
            "无法唯一确定当日最新历史快照: "
            + ", ".join(sorted(path.name for path in latest))
        )
    return target, latest[0]


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


def load_brand_aliases(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != BRAND_ALIAS_MAP_HEADERS:
                raise ValidationError(f"品牌别名表表头不匹配: {path}")
            aliases: dict[str, str] = {}
            for line_number, row in enumerate(reader, start=2):
                alias = clean_text(row["alias"])
                canonical_brand = clean_text(row["canonical_brand"])
                status = clean_text(row["status"])
                version_added = clean_text(row["version_added"])
                if not alias or not canonical_brand or not version_added:
                    raise ValidationError(f"品牌别名表第{line_number}行字段无效")
                if status != "confirmed":
                    raise ValidationError(f"品牌别名表第{line_number}行不是confirmed")
                key = alias.casefold()
                if key in aliases:
                    raise ValidationError(f"品牌别名重复: {alias}")
                aliases[key] = canonical_brand
            return aliases
    except OSError as exc:
        raise ValidationError(f"无法读取品牌别名表 {path}: {exc}") from exc


def load_tax_aliases(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != TAX_ALIAS_MAP_HEADERS:
                raise ValidationError(f"税务别名表表头不匹配: {path}")
            aliases: dict[str, str] = {}
            for line_number, row in enumerate(reader, start=2):
                alias = clean_text(row["alias"])
                canonical_tax_status = clean_text(row["canonical_tax_status"])
                status = clean_text(row["status"])
                version_added = clean_text(row["version_added"])
                if (
                    not alias
                    or canonical_tax_status not in ALLOWED_TAX
                    or not version_added
                ):
                    raise ValidationError(f"税务别名表第{line_number}行字段无效")
                if status != "confirmed":
                    raise ValidationError(f"税务别名表第{line_number}行不是confirmed")
                key = alias.casefold()
                if key in aliases:
                    raise ValidationError(f"税务别名重复: {alias}")
                aliases[key] = canonical_tax_status
            return aliases
    except OSError as exc:
        raise ValidationError(f"无法读取税务别名表 {path}: {exc}") from exc


def load_release_manifest(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"无法读取发布清单 {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValidationError("发布清单必须是JSON对象")
    versions: dict[str, str] = {}
    for key in RELEASE_VERSION_KEYS:
        value = clean_text(manifest.get(key))
        if not value:
            raise ValidationError(f"发布清单缺少版本字段: {key}")
        versions[key] = value
    return versions


def validate_payload_versions(payload: dict[str, Any], manifest: dict[str, str]) -> None:
    versions = payload.get("versions")
    if not isinstance(versions, dict):
        raise ValidationError("JSON根对象必须包含versions对象")
    mismatches = []
    for key in RELEASE_VERSION_KEYS:
        actual = clean_text(versions.get(key))
        expected = manifest[key]
        if actual != expected:
            mismatches.append(f"{key}: 输入={actual or '<空>'}, 当前={expected}")
    if mismatches:
        raise ValidationError("批次版本与当前发布不一致: " + "; ".join(mismatches))


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
    brand_aliases: dict[str, str],
    tax_aliases: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(record, dict):
        raise ValidationError(f"第{index}条记录必须是对象")
    if record.get("eligibility") != "eligible":
        raise ValidationError(f"第{index}条记录不是eligible，不应进入验证函数")

    issues = record.get("issues", [])
    if not isinstance(issues, list):
        raise ValidationError(f"第{index}条issues必须是数组")
    if issues:
        raise ValidationError(f"第{index}条eligible记录仍有未解决issues")

    direction = clean_text(record.get("direction"))
    if direction not in ALLOWED_DIRECTIONS:
        raise ValidationError(f"第{index}条方向必须是sell或purchase")

    category = clean_text(record.get("category"))
    if category not in CATEGORY_CODES:
        raise ValidationError(f"第{index}条品类尚不支持生成CSV: {category or '<空>'}")

    brand_raw = clean_text(record.get("brand_raw"))
    brand_normalized = clean_text(record.get("brand_normalized"))
    product_name = clean_text(record.get("product_name"))
    if not product_name:
        raise ValidationError(f"第{index}条产品名型号为空")
    if EXTRA_SPEC_PATTERN.search(product_name):
        raise ValidationError(f"第{index}条产品名包含当前不应写入的附加规格")
    if "\n" in product_name or "\r" in product_name:
        raise ValidationError(f"第{index}条产品名不能包含换行")

    requires_confirmation = record.get("requires_confirmation")
    if requires_confirmation is not False:
        raise ValidationError(f"第{index}条eligible记录仍需确认")
    match_method = clean_text(record.get("match_method"))
    if match_method not in ALLOWED_MATCH_METHODS:
        raise ValidationError(f"第{index}条match_method无效: {match_method or '<空>'}")
    if match_method == "confirmed_alias":
        expected_brand = brand_aliases.get(brand_raw.casefold())
        if expected_brand is None or expected_brand != brand_normalized:
            raise ValidationError(f"第{index}条品牌别名未在当前confirmed映射表中")
    if match_method == "user_confirmed":
        confirmation = record.get("confirmation")
        if not isinstance(confirmation, dict):
            raise ValidationError(f"第{index}条缺少当前批次确认对象")
        if confirmation.get("confirmed") is not True:
            raise ValidationError(f"第{index}条当前批次确认状态无效")
        if clean_text(confirmation.get("scope")) != "current_batch":
            raise ValidationError(f"第{index}条确认范围必须是current_batch")
        if clean_text(confirmation.get("confirmed_value")) != product_name:
            raise ValidationError(f"第{index}条确认值与产品名不一致")
        validate_datetime(confirmation.get("confirmed_at"))

    matched_product_id = clean_text(record.get("matched_product_id"))
    mapped = product_map.get((category, matched_product_id))
    if mapped is None:
        raise ValidationError(f"第{index}条产品未匹配当前型号映射表")
    if product_name != mapped[0]:
        raise ValidationError(
            f"第{index}条产品名必须使用映射表写法: {mapped[0]}"
        )
    validate_cpu_brand_resolution(record, index, mapped[0])

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

    tax_status = normalize_tax_status(record, index, tax_aliases)

    condition = normalize_condition(record, index)

    csv_product_name = format_csv_product_name(category, product_name)
    row = (quote_datetime, csv_product_name, csv_price, tax_status, condition)
    return f"{file_date}_{CATEGORY_CODES[category]}.csv", row


def read_existing(
    path: Path, expected_date: str
) -> tuple[list[tuple[str, ...]], bool]:
    if not path.exists():
        return [], False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != HEADERS:
                raise ValidationError(f"已有CSV表头不匹配: {path}")
            rows = []
            normalized = False
            category = path.stem.rsplit("_", 1)[-1].casefold()
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(HEADERS):
                    raise ValidationError(f"已有CSV第{line_number}行列数错误: {path}")
                try:
                    _, row_date = validate_datetime(row[0])
                except ValidationError as exc:
                    raise ValidationError(
                        f"已有CSV第{line_number}行日期时间无效: {path}"
                    ) from exc
                if row_date != expected_date:
                    raise ValidationError(f"已有CSV包含跨日期记录: {path}")
                formatted_name = format_csv_product_name(category, row[1])
                if formatted_name != row[1]:
                    row[1] = formatted_name
                    normalized = True
                rows.append(tuple(row))
            return rows, normalized
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"无法读取已有CSV {path}: {exc}") from exc


def load_baseline_files(
    baseline_dir: Path | None, expected_date: str
) -> tuple[dict[str, list[tuple[str, ...]]], set[str]]:
    if baseline_dir is None:
        return {}, set()

    files: dict[str, list[tuple[str, ...]]] = {}
    normalized_files: set[str] = set()
    for path in sorted(baseline_dir.glob("*.csv")):
        match = CSV_NAME_PATTERN.fullmatch(path.name)
        if match is None or match.group("date") != expected_date:
            raise ValidationError(f"历史快照包含日期或命名不匹配的CSV: {path}")
        rows, normalized = read_existing(path, expected_date)
        files[path.name] = rows
        if normalized:
            normalized_files.add(path.name)
    return files, normalized_files


def write_csv(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(HEADERS)
            writer.writerows(rows)
    except OSError as exc:
        raise ValidationError(f"无法写入CSV {path}: {exc}") from exc


def deduplicate_rows_keep_earliest(
    rows: list[tuple[str, ...]],
) -> tuple[list[tuple[str, ...]], int]:
    unique_rows = []
    key_indexes: dict[tuple[str, ...], int] = {}
    duplicate_count = 0
    for row in rows:
        key = row[1:]
        existing_index = key_indexes.get(key)
        if existing_index is None:
            key_indexes[key] = len(unique_rows)
            unique_rows.append(row)
            continue
        duplicate_count += 1
        existing = unique_rows[existing_index]
        existing_time = datetime.strptime(existing[0], "%y/%m/%d/%H:%M")
        candidate_time = datetime.strptime(row[0], "%y/%m/%d/%H:%M")
        if candidate_time < existing_time:
            unique_rows[existing_index] = row
    return unique_rows, duplicate_count


def main() -> int:
    args = parse_args()
    try:
        payload = load_payload(args.input)
        batch_datetime = load_batch_datetime(payload)
        snapshot_date = batch_datetime.strftime("%y-%m-%d")
        target_dir, baseline_dir = select_daily_baseline(
            args.snapshot_root, batch_datetime
        )
        release_versions = load_release_manifest(args.release_manifest)
        validate_payload_versions(payload, release_versions)
        product_map = load_product_map(args.product_map)
        brand_aliases = load_brand_aliases(args.alias_map)
        tax_aliases = load_tax_aliases(args.tax_alias_map)
        grouped: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        counts = {"eligible": 0, "needs_confirmation": 0, "excluded": 0}

        for index, record in enumerate(payload["records"], start=1):
            if not isinstance(record, dict):
                raise ValidationError(f"第{index}条记录必须是对象")
            validate_formal_record_boundary(record, index)
            eligibility = record.get("eligibility")
            if eligibility not in counts:
                raise ValidationError(f"第{index}条eligibility无效: {eligibility}")
            counts[eligibility] += 1
            if eligibility == "eligible":
                filename, row = validate_eligible(
                    record,
                    index,
                    payload,
                    product_map,
                    brand_aliases,
                    tax_aliases,
                )
                if not filename.startswith(f"{snapshot_date}_"):
                    raise ValidationError(
                        f"第{index}条报价日期与本批快照日期不一致，禁止跨日期累计"
                    )
                grouped[filename].append(row)

        baseline_files, normalized_baseline_files = load_baseline_files(
            baseline_dir, snapshot_date
        )
        all_filenames = sorted(set(baseline_files).union(grouped))
        prepared: dict[str, tuple[list[tuple[str, ...]], bool, int, int]] = {}
        outputs = []
        total_written = 0
        total_duplicates = 0
        for filename in all_filenames:
            baseline_rows = baseline_files.get(filename, [])
            new_rows = grouped.get(filename, [])
            inherited_unchanged = (
                filename in baseline_files
                and not new_rows
                and filename not in normalized_baseline_files
            )
            if inherited_unchanged:
                final_rows = baseline_rows
                duplicates_removed = 0
            else:
                final_rows, duplicates_removed = deduplicate_rows_keep_earliest(
                    baseline_rows + new_rows
                )
            prepared[filename] = (
                final_rows,
                inherited_unchanged,
                len(baseline_rows),
                duplicates_removed,
            )
            total_duplicates += duplicates_removed
            total_written += len(final_rows)

        target_dir.mkdir(parents=True)
        for filename in all_filenames:
            final_rows, inherited_unchanged, baseline_count, duplicates_removed = prepared[
                filename
            ]
            output_path = target_dir / filename
            if inherited_unchanged and baseline_dir is not None:
                shutil.copy2(baseline_dir / filename, output_path)
            else:
                write_csv(output_path, final_rows)
            outputs.append(
                {
                    "path": str(output_path.resolve()),
                    "baseline_rows": baseline_count,
                    "new_rows": len(grouped.get(filename, [])),
                    "duplicate_rows_removed": duplicates_removed,
                    "written_rows": len(final_rows),
                    "inherited_unchanged": inherited_unchanged,
                }
            )

        print(
            json.dumps(
                {
                    "versions": release_versions,
                    "batch_datetime": batch_datetime.strftime("%y/%m/%d/%H:%M:%S"),
                    "snapshot_directory": str(target_dir.resolve()),
                    "baseline_directory": (
                        str(baseline_dir.resolve()) if baseline_dir is not None else None
                    ),
                    "first_snapshot_of_day": baseline_dir is None,
                    "counts": counts,
                    "duplicate_rows_removed": total_duplicates,
                    "written_rows": total_written,
                    "outputs": outputs,
                },
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
