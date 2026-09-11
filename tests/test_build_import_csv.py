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
            "product_name": "海力士 32G 3200",
            "matched_product_id": "25",
            "match_method": "exact",
            "candidate_models": [],
            "requires_confirmation": False,
            "correction_reason": None,
            "confirmation": None,
            "price": "2650",
            "currency": "CNY",
            "tax_status": "含税",
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
                self.record(brand_raw="SK", match_method="confirmed_alias"),
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
