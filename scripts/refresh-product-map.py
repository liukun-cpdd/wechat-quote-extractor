#!/usr/bin/env python3
"""Build the replaceable product-model map from a market-products CSV export."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


SOURCE_HEADERS = [
    "产品ID",
    "大类编码",
    "产品名称",
    "最新价格",
    "24小时涨跌额",
    "24小时涨跌幅%",
    "24小时最高价",
    "24小时最低价",
    "最后报价时间",
    "更新时间",
]
OUTPUT_HEADERS = [
    "product_id",
    "category",
    "canonical_product_name",
    "csv_product_name",
    "source_condition",
]
SUPPORTED_CATEGORIES = {"cpu", "gpu", "memory"}
CONDITION_PATTERN = re.compile(r"\s+(全新|拆机)\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh product-model mapping CSV")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != SOURCE_HEADERS:
                raise ValueError("商品库CSV表头与预期不一致")
            output_rows = []
            seen_ids = set()
            for line_number, row in enumerate(reader, start=2):
                category = row["大类编码"].strip()
                if category not in SUPPORTED_CATEGORIES:
                    continue
                product_id = row["产品ID"].strip()
                canonical_name = row["产品名称"].strip()
                if not product_id or not canonical_name:
                    raise ValueError(f"第{line_number}行缺少产品ID或产品名称")
                key = (category, product_id)
                if key in seen_ids:
                    raise ValueError(f"第{line_number}行产品ID重复: {category}/{product_id}")
                seen_ids.add(key)
                match = CONDITION_PATTERN.search(canonical_name)
                condition = match.group(1) if match else ""
                csv_name = CONDITION_PATTERN.sub("", canonical_name).strip()
                output_rows.append(
                    [product_id, category, canonical_name, csv_name, condition]
                )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(OUTPUT_HEADERS)
            writer.writerows(output_rows)
        print(f"written={len(output_rows)} output={args.output.resolve()}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
