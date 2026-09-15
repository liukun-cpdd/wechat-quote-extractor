from __future__ import annotations

import csv
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build-import-csv.py"
MANIFEST = SKILL_DIR / "references" / "release-manifest.json"
OFFICIAL_SOURCE = "中国人民银行授权中国外汇交易中心公布的人民币汇率中间价"


class BuildImportCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.versions = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def run_build_in_root(
        self, payload: dict, snapshot_root: Path
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        prepared = dict(payload)
        prepared.setdefault("batch_datetime", "26/09/11/14:30:00")
        snapshot_root.mkdir(parents=True, exist_ok=True)
        batch_datetime = datetime.strptime(
            prepared["batch_datetime"], "%y/%m/%d/%H:%M:%S"
        )
        day_dir = snapshot_root / batch_datetime.strftime("%y-%m-%d")
        snapshot_dir = day_dir / batch_datetime.strftime("%y-%m-%d_%H-%M-%S")
        input_path = snapshot_root.parent / "records.json"
        input_path.write_text(json.dumps(prepared, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--snapshot-root",
                str(snapshot_root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
            check=False,
        )
        return result, snapshot_dir

    def run_build(self, payload: dict) -> tuple[subprocess.CompletedProcess[str], Path, tempfile.TemporaryDirectory[str]]:
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        result, snapshot_dir = self.run_build_in_root(payload, root / "snapshots")
        return result, snapshot_dir, temp_dir

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
        self.assertEqual(rows[1], ["26/09/11/14:30", "海力士 32G 3200", "2650", "含税", "拆机"])

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

    def test_expanded_shared_memory_quote_writes_each_mapped_brand_independently(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                self.record(
                    brand_raw="三星",
                    brand_normalized="三星",
                    product_name="三星 32G 4800",
                    matched_product_id="59",
                    price="8200",
                ),
                self.record(
                    brand_raw="SK",
                    brand_normalized="海力士",
                    brand_resolution_method="confirmed_alias",
                    product_name="海力士 32G 4800",
                    matched_product_id="60",
                    match_method="confirmed_alias",
                    price="8200",
                ),
                {
                    "category": "memory",
                    "brand_raw": "未收录品牌",
                    "eligibility": "excluded",
                    "requires_confirmation": False,
                    "issues": ["product_not_in_map"],
                },
            ],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["counts"],
            {"eligible": 2, "needs_confirmation": 0, "excluded": 1},
        )
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(
            {tuple(row[1:]) for row in rows[1:]},
            {
                ("三星 32G 4800", "8200", "含税", "拆机"),
                ("海力士 32G 4800", "8200", "含税", "拆机"),
            },
        )

    def test_ws_untaxed_quote_is_rejected_from_eligible_csv(self) -> None:
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
                result, _, temp_dir = self.run_build(payload)
                self.addCleanup(temp_dir.cleanup)
                self.assertEqual(result.returncode, 2)
                self.assertIn("当前仅录入含税报价", result.stderr)

    def test_excluded_untaxed_quote_does_not_block_taxed_output(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                self.record(),
                self.record(
                    eligibility="excluded",
                    tax_status_raw="未税",
                    tax_status="未税",
                    issues=["untaxed_not_collected"],
                ),
            ],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["counts"],
            {"eligible": 1, "needs_confirmation": 0, "excluded": 1},
        )
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], "含税")

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

    def test_not_tax_inclusive_is_recognized_but_not_recorded(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [self.record(tax_status_raw="不含税", tax_status="未税")],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 2)
        self.assertIn("当前仅录入含税报价", result.stderr)

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

    def test_missing_memory_condition_defaults_to_disassembled(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        condition_raw=None,
                        condition_classification="missing",
                        condition=None,
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

    def test_missing_cpu_condition_defaults_to_disassembled(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        category="cpu",
                        brand_raw="Intel",
                        brand_normalized="Intel",
                        brand_resolution_method="explicit",
                        product_name="Intel 6430",
                        matched_product_id="84",
                        condition_classification="missing",
                        condition=None,
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_cpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][4], "拆机")

    def test_ambiguous_cpu_condition_defaults_to_disassembled(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        category="cpu",
                        brand_raw="Intel",
                        brand_normalized="Intel",
                        brand_resolution_method="explicit",
                        product_name="Intel 6430",
                        matched_product_id="84",
                        condition_raw="货况不详",
                        condition_classification="ambiguous",
                        condition=None,
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_cpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][4], "拆机")

    def test_missing_gpu_condition_defaults_to_new(self) -> None:
        result, output_dir, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        category="gpu",
                        brand_raw=None,
                        brand_normalized=None,
                        product_name="RTX 4090 24G 涡轮",
                        matched_product_id="3904",
                    )
                ],
            }
        )
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (output_dir / "26-09-11_gpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "英伟达 RTX 4090 24G 涡轮")
        self.assertEqual(rows[1][4], "全新")

    def test_special_gpu_missing_condition_is_rejected(self) -> None:
        namespace = runpy.run_path(str(SCRIPT))
        normalize_condition = namespace["normalize_condition"]
        validation_error = namespace["ValidationError"]
        for product_name in ["H100 整机", "H100 模组"]:
            with self.subTest(product_name=product_name):
                with self.assertRaisesRegex(validation_error, "特殊GPU未标明货况"):
                    normalize_condition(
                        {
                            "category": "gpu",
                            "product_name": product_name,
                            "condition_raw": None,
                            "condition_classification": "missing",
                            "condition": None,
                        },
                        1,
                    )

    def test_prefixed_gpu_snapshot_is_inherited_without_double_prefix(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        gpu_record = self.record(
            quote_datetime="26/09/11/09:00",
            category="gpu",
            brand_raw=None,
            brand_normalized=None,
            product_name="RTX 4090 24G 涡轮",
            matched_product_id="3904",
        )
        first, first_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/09:00:00",
                "versions": self.versions,
                "records": [gpu_record],
            },
            snapshot_root,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        original = (first_dir / "26-09-11_gpu.csv").read_bytes()

        second, second_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [],
            },
            snapshot_root,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        inherited = (second_dir / "26-09-11_gpu.csv").read_bytes()
        self.assertEqual(inherited, original)
        self.assertEqual(inherited.count("英伟达 ".encode()), 1)

    def test_legacy_gpu_baseline_is_normalized_without_mutating_history(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        baseline = snapshot_root / "26-09-11" / "26-09-11_09-00-00"
        baseline.mkdir(parents=True)
        legacy_file = baseline / "26-09-11_gpu.csv"
        legacy_file.write_text(
            "日期时间,产品名型号,报价,税务状态,货况\n"
            "26/09/11/09:00,RTX 4090 24G 涡轮,25800,含税,拆机\n",
            encoding="utf-8",
            newline="",
        )
        original = legacy_file.read_bytes()

        result, output_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [],
            },
            snapshot_root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(legacy_file.read_bytes(), original)
        with (output_dir / "26-09-11_gpu.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "英伟达 RTX 4090 24G 涡轮")

    def test_ambiguous_condition_is_rejected(self) -> None:
        result, _, temp_dir = self.run_build(
            {
                "versions": self.versions,
                "records": [
                    self.record(
                        category="gpu",
                        brand_raw=None,
                        brand_normalized=None,
                        product_name="RTX 4090 24G 涡轮",
                        matched_product_id="3904",
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

    def test_current_batch_four_field_duplicates_keep_earlier_time(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [
                self.record(price="2650", tax_status_raw="含税", tax_status="含税"),
                self.record(
                    quote_datetime="26/09/11/14:35",
                    price="2650.00",
                    tax_status_raw="含税不对应",
                    tax_status="含税",
                ),
            ],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["counts"]["eligible"], 2)
        self.assertEqual(output["duplicate_rows_removed"], 1)
        self.assertEqual(output["outputs"][0]["new_rows"], 2)
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "26/09/11/14:30")

    def test_rows_with_different_final_price_are_preserved(self) -> None:
        payload = {
            "versions": self.versions,
            "records": [self.record(price="2650"), self.record(price="2651")],
        }
        result, output_dir, temp_dir = self.run_build(payload)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["duplicate_rows_removed"], 0)
        with (output_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 3)

    def test_same_day_snapshot_inherits_unmodified_categories(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"

        first_payload = {
            "batch_datetime": "26/09/11/09:00:00",
            "versions": self.versions,
            "records": [self.record(quote_datetime="26/09/11/09:00")],
        }
        first, first_dir = self.run_build_in_root(first_payload, snapshot_root)
        self.assertEqual(first.returncode, 0, first.stderr)
        memory_before = (first_dir / "26-09-11_memory.csv").read_bytes()

        cpu_record = self.record(
            quote_datetime="26/09/11/10:00",
            category="cpu",
            brand_raw="Intel",
            brand_normalized="Intel",
            brand_resolution_method="explicit",
            product_name="Intel 6430",
            matched_product_id="84",
            price="12800",
        )
        second_payload = {
            "batch_datetime": "26/09/11/10:00:00",
            "versions": self.versions,
            "records": [cpu_record],
        }
        second, second_dir = self.run_build_in_root(second_payload, snapshot_root)
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads(second.stdout)
        self.assertEqual(Path(output["baseline_directory"]), first_dir.resolve())
        self.assertEqual((first_dir / "26-09-11_memory.csv").read_bytes(), memory_before)
        self.assertEqual((second_dir / "26-09-11_memory.csv").read_bytes(), memory_before)
        self.assertTrue((second_dir / "26-09-11_cpu.csv").exists())

    def test_snapshot_uses_only_latest_same_day_baseline(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"

        first, first_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/09:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/09:00")],
            },
            snapshot_root,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        second, second_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/10:00", price="2651")],
            },
            snapshot_root,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        with (second_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            second_rows = list(csv.reader(handle))
        self.assertEqual(len(second_rows), 3)
        third, _ = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/11:00:00",
                "versions": self.versions,
                "records": [],
            },
            snapshot_root,
        )
        self.assertEqual(third.returncode, 0, third.stderr)
        output = json.loads(third.stdout)
        self.assertEqual(Path(output["baseline_directory"]), second_dir.resolve())
        self.assertNotEqual(Path(output["baseline_directory"]), first_dir.resolve())

    def test_cross_day_snapshot_does_not_inherit_previous_day(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        first, _ = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/09:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/09:00")],
            },
            snapshot_root,
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        cpu_record = self.record(
            quote_datetime="26/09/12/09:00",
            category="cpu",
            brand_raw="Intel",
            brand_normalized="Intel",
            brand_resolution_method="explicit",
            product_name="Intel 6430",
            matched_product_id="84",
        )
        second, second_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/12/09:00:00",
                "versions": self.versions,
                "records": [cpu_record],
            },
            snapshot_root,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads(second.stdout)
        self.assertTrue(output["first_snapshot_of_day"])
        self.assertIsNone(output["baseline_directory"])
        self.assertTrue((snapshot_root / "26-09-11").is_dir())
        self.assertTrue((snapshot_root / "26-09-12").is_dir())
        self.assertTrue((second_dir / "26-09-12_cpu.csv").exists())
        self.assertFalse((second_dir / "26-09-12_memory.csv").exists())

    def test_same_four_fields_across_snapshots_keep_earlier_datetime(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        first, _ = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/09:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/09:00")],
            },
            snapshot_root,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        second, second_dir = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/10:00")],
            },
            snapshot_root,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads(second.stdout)
        self.assertEqual(output["duplicate_rows_removed"], 1)
        with (second_dir / "26-09-11_memory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "26/09/11/09:00")

    def test_ambiguous_latest_snapshot_stops_before_writing(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        day_dir = snapshot_root / "26-09-11"
        (day_dir / "26-09-11_09-00-00_a").mkdir(parents=True)
        (day_dir / "26-09-11_09-00-00_b").mkdir()
        result, target = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/10:00")],
            },
            snapshot_root,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("无法唯一确定当日最新历史快照", result.stderr)
        self.assertFalse(target.exists())

    def test_invalid_baseline_header_stops_before_writing(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        baseline = snapshot_root / "26-09-11" / "26-09-11_09-00-00"
        baseline.mkdir(parents=True)
        invalid_file = baseline / "26-09-11_memory.csv"
        invalid_file.write_text("错误表头\n", encoding="utf-8")
        original = invalid_file.read_bytes()
        result, target = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/10:00")],
            },
            snapshot_root,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("已有CSV表头不匹配", result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(invalid_file.read_bytes(), original)

    def test_existing_target_snapshot_is_never_overwritten(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        snapshot_root = Path(temp_dir.name) / "snapshots"
        target = snapshot_root / "26-09-11" / "26-09-11_10-00-00"
        target.mkdir(parents=True)
        sentinel = target / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        result, _ = self.run_build_in_root(
            {
                "batch_datetime": "26/09/11/10:00:00",
                "versions": self.versions,
                "records": [self.record(quote_datetime="26/09/11/10:00")],
            },
            snapshot_root,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("禁止覆盖", result.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
