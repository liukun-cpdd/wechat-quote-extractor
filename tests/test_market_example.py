from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MarketExampleTest(unittest.TestCase):
    def test_catalog_comparison_and_csv_generation(self):
        password_path = Path(os.environ.get('CPLIGHT_TEST_PASSWORD_FILE', ROOT / 'ops-password.local'))
        if not password_path.is_file():
            self.skipTest('local operations password is not configured')
        password = password_path.read_text(encoding='utf-8').strip()
        request = urllib.request.Request(
            'https://www.cplight.com/api/vgo/market/ops/products?category=memory&page=1&limit=100',
            headers={'X-Ops-Password': password},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)['data']
        self.assertLessEqual(data['total'], len(data['list']), 'test requires complete category page')
        matches = [item for item in data['list'] if item['name'] == '海力士 64G 5600 拆机']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['product_status_label'], '拆机新')
        ref = Decimal(str(matches[0]['latest_price']))
        self.assertGreater(ref, 0)
        self.assertFalse(abs(ref * Decimal('1.08') - ref) / ref > Decimal('.08'))
        self.assertTrue(abs(ref * Decimal('1.081') - ref) / ref > Decimal('.08'))
        self.assertFalse(any(item['name'] == '海力士 999G 9999 全新' for item in data['list']))

        record = {
            'quote_datetime': '26/11/09/14:30', 'direction': 'sell', 'category': 'memory',
            'brand_raw': 'SK', 'brand_normalized': '海力士', 'brand_resolution_method': 'confirmed_alias',
            'product_name': '海力士 64G 5600', 'matched_product_id': '119', 'match_method': 'confirmed_alias',
            'requires_confirmation': False, 'price': '15000', 'currency': 'CNY',
            'tax_status_raw': '含税', 'tax_status': '含税', 'condition_raw': '拆机',
            'condition_classification': 'explicit_not_new', 'condition': '拆机',
            'eligibility': 'eligible', 'issues': [],
        }
        payload = {'batch_datetime': '26/11/09/14:30:00',
                   'versions': json.loads((ROOT / 'references/release-manifest.json').read_text(encoding='utf-8')),
                   'records': [record]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'snapshots').mkdir()
            source = root / 'batch.json'
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/build-import-csv.py'),
                                  '--input', str(source), '--snapshot-root', str(root / 'snapshots')],
                                 capture_output=True, text=True, encoding='utf-8',
                                 env={**os.environ, 'PYTHONUTF8': '1'})
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            output = next((root / 'snapshots').rglob('*_memory.csv')).read_text(encoding='utf-8')
            self.assertIn('海力士 64G 5600,15000,含税,拆机', output)


if __name__ == '__main__':
    unittest.main()
