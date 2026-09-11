from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build-import-csv.py"
MANIFEST = SKILL_DIR / "references" / "release-manifest.json"
OFFICIAL_SOURCE = "中国人民银行授权中国外汇交易中心公布的人民币汇率中间价"


class BuildImportCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.versions = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def run_build(self, payload: dict) -> tuple[subprocess.CompletedProcess[str], Path, tempfile.TemporaryDirectory[str]]:
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        input_path = root / "records.json"
        output_dir = root / "output"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
            check=False,
        )
        return result, output_dir, temp_dir

    def record(self, **overrides: object) -> dict:
        value = {
            "quote_datetime": "26/09/11/14:30",
            "direction": "sell",
            "category": "memory",
            "brand_raw": "海力士",
            "brand_normalized": "海力士",
            "brand_resolution_method": "explicit",
            "brand_inference_reason": None,
            "product_name": "海力士 32G 3200",
            "matched_product_id": "25",
            "match_method": "exact",
            "candidate_models": [],
            "requires_confirmation": False,
            "correction_reason": None,
            "confirmation": None,
            "price": "2650",
            "currency": "CNY",
            "tax_status_raw": "含税",
            "tax_status": "含税",
            "condition_raw": None,
            "condition_classification": "missing",
            "condition": None,
            "eligibility": "eligible",
            "issues": [],
        }
        value.update(overrides)
        return value

    def test_confirmed_alias_writes_mapped_product(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                self.record(
                    brand_raw="SK",
                    brand_resolution_method="confirmed_alias",
                    match_method="confirmed_alias",
                ),
                {"eligibility": "excluded", "issues": ["product_not_in_map"]},
            ],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["counts"], {"eligible": 1, "needs_confirmation": 0, "excluded": 1})
        with (output_dir / "26-09-11_memory.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1], ["26/09/11/14:30", "海力士 32G 3200", "2650", "含税", ""])

    def test_mt_is_a_confirmed_micron_alias(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                self.record(
                    brand_raw="MT",
                    brand_normalized="镁光",
                    product_name="镁光 32G 2933",
                    matched_product_id="28",
                    brand_resolution_method="confirmed_alias",
                    match_method="confirmed_alias",
                )
            ],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_memory.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "镁光 32G 2933")

    def test_ws_is_a_case_insensitive_untaxed_alias(self) -> None:
        for raw_tax in ["WS", "ws", "Ws"]:
            with self.subTest(raw_tax=raw_tax):
                payload = {
                    "versions": self.versions,
                    "records": [
                        self.record(
                            brand_raw="镁光",
                            brand_normalized="镁光",
                            product_name="镁光 64G 3200",
                            matched_product_id="31",
                            price="4200",
                            tax_status_raw=raw_tax,
                            tax_status=raw_tax,
                        )
                    ],
                }
                result, output_dir, temp_dir = self.run_build(payload)
                self.addCleanup(temp_dir.cleanup)
                self.assertEqual(result.returncode, 0, result.stderr)
                with (output_dir / "26-09-11_memory.csv").open(
                    encoding="utf-8", newline=""
                ) as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(
                    rows[1],
                    ["26/09/11/14:30", "镁光 64G 3200", "4200", "未税", ""],
                )

    def test_tax_inclusive_invoice_qualifiers_normalize_without_confirmation(self) -> None:
        phrases = ["含税不对应", "含税票不对应", "含税开其他品类发票"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                result, output_dir, temp_dir = self.run_build(
                    {
                        "versions": self.versions,
                        "records": [
                            self.record(
                                tax_status_raw=phrase,
                                tax_status="含税",
                            )
                        ],
                    }
                )
                self.addCleanup(temp_dir.cleanup)
                self.assertEqual(result.returncode, 0, result.stderr)
                with (output_dir / "26-09-11_memory.csv").open(
                    encoding="utf-8", newline=""
                ) as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(rows[1][3], "含税")

    def test_missing_explicit_tax_signal_is_rejected(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [self.record(tax_status_raw=None, tax_status=None)],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("缺少明确税务状态原文信号", result.stderr)

    def test_invoice_correspondence_alone_does_not_establish_tax_status(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        tax_status_raw="发票不对应",
                        tax_status=None,
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("税务状态无效", result.stderr)

    def test_not_tax_inclusive_is_not_misread_as_tax_inclusive(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [self.record(tax_status_raw="不含税", tax_status="未税")],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][3], "未税")

    def test_unconfirmed_tax_abbreviation_is_rejected(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        tax_status_raw="WST",
                        tax_status="WST",
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("税务状态无效", result.stderr)

    def test_semantically_non_new_conditions_normalize_to_disassembled(self) -> None:
        examples = [
            "二手",
            "旧货",
            "翻新",
            "开封使用",
            "拆新",
            "拆机新",
            "几成新",
            "九成新",
            "9成新",
            "9.5 成新",
        ]
        for raw_condition in examples:
            with self.subTest(raw_condition=raw_condition):
                result, output_dir, temp_dir = self.run_build(
                    {
                        "versions": self.versions,
                        "records": [
                            self.record(
                                condition_raw=raw_condition,
                                condition_classification="explicit_not_new",
                                condition=raw_condition,
                            )
                        ],
                    }
                )
                self.addCleanup(temp_dir.cleanup)
                self.assertEqual(result.returncode, 0, result.stderr)
                with (output_dir / "26-09-11_memory.csv").open(
                    encoding="utf-8", newline=""
                ) as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(rows[1][4], "拆机")

    def test_explicit_new_condition_writes_new(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        condition_raw="全新",
                        condition_classification="explicit_new",
                        condition="全新",
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][4], "全新")

    def test_ambiguous_condition_is_rejected(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        condition_raw="货况不详",
                        condition_classification="ambiguous",
                        condition=None,
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("货况语义仍有歧义", result.stderr)

    def test_user_confirmed_typo_requires_current_batch_evidence(self) -> None:
        record = self.record(
            category="gpu",
            brand_raw=None,
            brand_normalized=None,
            product_name="RTX 4090 24G 涡轮",
            matched_product_id="3904",
            match_method="user_confirmed",
            correction_reason="窝轮可能是涡轮的输入错误",
            confirmation={
                "confirmed": True,
                "scope": "current_batch",
                "confirmed_value": "RTX 4090 24G 涡轮",
                "confirmed_at": "26/09/11/14:35",
            },
            price="25800",
            condition_raw="拆机",
            condition_classification="explicit_not_new",
            condition="拆机",
        )
        result, output_dir, temp_dir = self.run_build({"versions": self.versions, "records": [record]})
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output_dir / "26-09-11_gpu.csv").exists())

        record["confirmation"] = None
        rejected, _, rejected_temp = self.run_build({"versions": self.versions, "records": [record]})
        self.addCleanup(rejected_temp.cleanup)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("缺少当前批次确认对象", rejected.stderr)

    def test_bare_cpu_model_can_infer_brand_and_write(self) -> None:
        record = self.record(
            category="cpu",
            brand_raw=None,
            brand_normalized="Intel",
            brand_resolution_method="model_inferred",
            brand_inference_reason="裸型号6530唯一匹配当前产品字典中的Intel 6530",
            product_name="Intel 6530",
            matched_product_id="1",
            match_method="model_inferred",
        )
        result, output_dir, temp_dir = self.run_build(
            {"versions": self.versions, "records": [record]}
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_cpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "Intel 6530")

    def test_cpu_with_explicit_brand_still_writes_normally(self) -> None:
        record = self.record(
            category="cpu",
            brand_raw="Intel",
            brand_normalized="Intel",
            brand_resolution_method="explicit",
            brand_inference_reason=None,
            product_name="Intel 6430",
            matched_product_id="84",
            match_method="exact",
        )
        result, output_dir, temp_dir = self.run_build(
            {"versions": self.versions, "records": [record]}
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_cpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "Intel 6430")

    def test_bare_cpu_model_requires_model_inference_evidence(self) -> None:
        record = self.record(
            category="cpu",
            brand_raw=None,
            brand_normalized="Intel",
            brand_resolution_method=None,
            brand_inference_reason=None,
            product_name="Intel 6530",
            matched_product_id="1",
            match_method="exact",
        )
        result, _, temp_dir = self.run_build(
            {"versions": self.versions, "records": [record]}
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("model_inferred解析依据", result.stderr)

    def test_inferred_cpu_brand_must_match_mapped_product(self) -> None:
        record = self.record(
            category="cpu",
            brand_raw=None,
            brand_normalized="AMD",
            brand_resolution_method="model_inferred",
            brand_inference_reason="型号被识别为AMD",
            product_name="Intel 6530",
            matched_product_id="1",
            match_method="model_inferred",
        )
        result, _, temp_dir = self.run_build(
            {"versions": self.versions, "records": [record]}
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("CPU品牌与映射表产品不一致", result.stderr)

    def test_recognizable_unmapped_cpu_is_excluded_without_brand_question(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                {
                    "category": "cpu",
                    "brand_raw": None,
                    "brand_normalized": "AMD",
                    "brand_resolution_method": "model_inferred",
                    "brand_inference_reason": "型号可明确识别为AMD",
                    "eligibility": "excluded",
                    "requires_confirmation": False,
                    "issues": ["product_not_in_map"],
                }
            ],
        }
        result, _, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["counts"]["excluded"], 1)
        self.assertEqual(output["written_rows"], 0)

    def test_transient_auxiliary_fields_are_rejected_from_formal_records(self) -> None:
        fields = {
            "source_excerpt": "原文",
            "quantity": "28条",
            "year_or_batch": "DC26",
            "dc": "DC26",
            "extra_spec": ["2R4"],
            "memory_layout": "2R4",
            "warranty": "一年",
            "packaging": "原包",
            "packing_method": "十张一箱",
            "invoice_matching": "不对应",
            "invoice_details": "开其他品类发票",
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                result, _, temp_dir = self.run_build(
                    {
                        "versions": self.versions,
                        "records": [self.record(**{field: value})],
                    }
                )
                self.addCleanup(temp_dir.cleanup)
                self.assertEqual(result.returncode, 2)
                self.assertIn("不得长期保存的辅助字段", result.stderr)

    def test_stale_batch_version_is_rejected(self) -> None:
        versions = dict(self.versions)
        versions["ruleset_version"] = "stale"
        result, _, temp_dir = self.run_build({"versions": versions, "records": [self.record()]})
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("批次版本与当前发布不一致", result.stderr)

    def test_masked_price_cannot_enter_csv(self) -> None:
        result, _, temp_dir = self.run_build(
            {"versions": self.versions, "records": [self.record(price="18x00")]}
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("报价不是有效数字", result.stderr)

    def test_hong_kong_usd_is_converted_and_rounded_half_up(self) -> None:
        payload = {
            "versions": self.versions,
            "conversion": {
                "usd_cny_rate": "7.1300",
                "rate_date": "2026-09-11",
                "rate_source": OFFICIAL_SOURCE,
                "rate_source_url": "https://www.pbc.gov.cn/example",
                "factor": "1.13",
                "rounding": "1",
            },
            "records": [self.record(price="1400", currency="USD", warehouse="香港仓")],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_memory.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][2], "11280")


if __name__ == "__main__":
    unittest.main()
