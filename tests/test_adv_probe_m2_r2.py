"""
tests/test_adv_probe_m2_r2.py
Empirical Challenger Round 2 Adversarial Probe Harness
Target: RBAC floor price validation, formula edge boundaries, price math tampering, invariant integrity
"""

import sys
import os
import json
import sqlite3
import hashlib
import time
import urllib.request
import urllib.error
import threading
import tempfile
import shutil
import socketserver
import unittest

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class TestAdvProbeRound2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="adv_r2_")
        cls.db_path = os.path.join(cls.temp_dir, "test_khanhvan.db")
        cls.port = 5595
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        server.DB_FILE = cls.db_path
        server.PORT = cls.port
        server.init_db()

        cls.httpd = socketserver.TCPServer(("127.0.0.1", cls.port), server.KhanhVanServer)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        try:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def request(self, method, path, data=None):
        url = f"{self.base_url}{path}"
        headers = {'Accept': 'application/json'}
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read().decode('utf-8')
                try:
                    return resp.status, json.loads(raw)
                except Exception:
                    return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw
        except Exception as ex:
            return 500, {'error': str(ex)}

    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --------------------------------------------------------------------------
    # 1. RBAC Floor Price Adversarial Tests
    # --------------------------------------------------------------------------
    def test_probe_01_worker_spoofing_case_variants(self):
        """Worker sending case variants of role ('chu', 'Admin', 'CHU', 'quan_tri') must still be blocked (403)"""
        for spoof_role in ['chu', 'ADMIN', 'Admin', 'quan_tri', 'CHỦ', 'GIÁM_ĐỐC']:
            payload = {
                "khach_hang": f"Spoof Test {spoof_role}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": spoof_role,
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 7000000}], # below floor 8,100,000
                "hinh_thuc_tt": "TIEN_MAT"
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 403, f"Expected 403 for spoofed role '{spoof_role}', got {status}")
            self.assertEqual(res.get('error'), 'FLOOR_PRICE_VIOLATION')

    def test_probe_02_sql_injection_in_nguoi_lap(self):
        """SQL injection in nguoi_lap to extract or bypass role check must not elevate privileges"""
        injections = [
            "' OR vai_tro='CHU' --",
            "covan@khanhvan.vn' --",
            "anhnam@khanhvan.vn' OR '1'='1",
            "admin' UNION SELECT 'CHU', 1 --"
        ]
        for inj in injections:
            payload = {
                "khach_hang": "SQLi Nguoi Lap",
                "nguoi_lap": inj,
                "vai_tro_nguoi_lap": "CHU",
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6000000}],
                "hinh_thuc_tt": "TIEN_MAT"
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 403, f"SQL injection '{inj}' must not bypass floor price! Got {status}")

    def test_probe_03_multi_item_order_mixed_floor_prices(self):
        """An order with 2 items: item 1 at regular price, item 2 below floor price -> Must be 403 for worker"""
        payload = {
            "khach_hang": "Multi-item Discount Test",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [
                {"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000}, # above floor
                {"ma_bien_the": "BO-BANAN-SOI-1600", "so_luong": 1, "don_gia": 1000000}   # way below floor (floor is 16,500,000)
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 403, f"Expected 403 for multi-item order with one item below floor, got {status}")
        self.assertEqual(res.get('error'), 'FLOOR_PRICE_VIOLATION')

    # --------------------------------------------------------------------------
    # 2. Price Math Integrity Tests
    # --------------------------------------------------------------------------
    def test_probe_04_tampered_tong_tien_and_thanh_tien(self):
        """Client supplying forged outer tong_tien and forged inner thanh_tien -> Server must enforce exact math"""
        payload = {
            "khach_hang": "Outer Tong Tien Forger",
            "nguoi_lap": "covan@khanhvan.vn",
            "tong_tien": 500, # forged total
            "items": [
                {"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 2, "don_gia": 8500000, "thanh_tien": 100} # forged item total
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200, f"Order creation failed: {res}")
        self.assertEqual(res.get('tong_tien'), 17000000, f"Expected server recalculated tong_tien 17,000,000, got {res.get('tong_tien')}")

        # Check DB persistence
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT tong_tien FROM D3_DON_HANG WHERE ma_don = ?", (res.get('ma_don'),))
        db_total = cur.fetchone()[0]
        conn.close()
        self.assertEqual(db_total, 17000000, "DB persisted total must match server-calculated sum")

    def test_probe_05_floating_point_and_zero_don_gia(self):
        """Unit price 0, 0.0, or negative floats must be rejected with HTTP 400 INVALID_PRICE"""
        for invalid_price in [0, 0.0, -0.01, -0.0001, -100.5]:
            payload = {
                "khach_hang": "Floating Zero Attacker",
                "nguoi_lap": "covan@khanhvan.vn",
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": invalid_price}]
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 400, f"Expected 400 for price {invalid_price}, got {status}")
            self.assertEqual(res.get('error'), 'INVALID_PRICE')

    # --------------------------------------------------------------------------
    # 3. Dynamic Formula Calculation Boundaries (F02)
    # --------------------------------------------------------------------------
    def test_probe_06_formula_met_dai_extreme_boundaries(self):
        """Verify MET_DAI calculations and boundary rejections"""
        # Exactly 400mm
        status, res = self.request('POST', '/api/pricing/calculate', {
            "kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 400
        })
        self.assertEqual(status, 200)
        self.assertEqual(res.get('kich_thuoc_tinh'), 0.4)
        # Expected: 0.4 * 1,850,000 * 1.2 = 888,000
        self.assertEqual(res.get('thanh_tien'), 888000)

        # Exactly 3000mm
        status, res = self.request('POST', '/api/pricing/calculate', {
            "kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 3000
        })
        self.assertEqual(status, 200)
        self.assertEqual(res.get('kich_thuoc_tinh'), 3.0)
        # Expected: 3.0 * 1,850,000 * 1.2 = 6,660,000
        self.assertEqual(res.get('thanh_tien'), 6660000)

        # 399.99mm and 3000.01mm
        for bad_dim in [399.99, 3000.01]:
            s, r = self.request('POST', '/api/pricing/calculate', {
                "kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": bad_dim
            })
            self.assertEqual(s, 400, f"Dim {bad_dim} should be rejected")
            self.assertEqual(r.get('error'), 'DIMENSION_OUT_OF_BOUNDS')

    def test_probe_07_formula_dien_tich_boundaries_and_thickness(self):
        """Verify DIEN_TICH area calculation, boundary rejection, and thickness threshold"""
        # Valid 1000mm x 2000mm, thickness 10mm
        status, res = self.request('POST', '/api/pricing/calculate', {
            "kieu_tinh": "DIEN_TICH", "loai_go": "Sồi", "chieu_dai_mm": 1000, "chieu_rong_mm": 2000, "do_day_mm": 10
        })
        self.assertEqual(status, 200)
        self.assertEqual(res.get('kich_thuoc_tinh'), 2.0)
        self.assertEqual(res.get('don_vi_tinh'), 'm2')

        # Thickness below 10 (e.g. 9.99mm)
        status, res = self.request('POST', '/api/pricing/calculate', {
            "kieu_tinh": "DIEN_TICH", "loai_go": "Sồi", "chieu_dai_mm": 1000, "chieu_rong_mm": 2000, "do_day_mm": 9.99
        })
        self.assertEqual(status, 400)
        self.assertEqual(res.get('error'), 'INVALID_THICKNESS')

    def test_probe_08_formula_bac_kich_thuoc(self):
        """Verify BAC_KICH_THUOC discrete dimensions: 1m6, 1m8, 2m2"""
        expected_prices = {
            '1m6': 7800000,
            '1.6m': 7800000,
            '1600': 7800000,
            '1m8': 8500000,
            '1.8m': 8500000,
            '1800': 8500000,
            '2m2': 10200000,
            '2.2m': 10200000,
            '2200': 10200000,
        }
        for bac, expected_p in expected_prices.items():
            status, res = self.request('POST', '/api/pricing/calculate', {
                "kieu_tinh": "BAC_KICH_THUOC", "loai_go": "Sồi Nga", "bac_kich_thuoc": bac
            })
            self.assertEqual(status, 200, f"Failed for {bac}")
            self.assertEqual(res.get('thanh_tien'), expected_p, f"Mismatch for {bac}: got {res.get('thanh_tien')}")

    # --------------------------------------------------------------------------
    # 4. Invariant Protection & Stock Isolation
    # --------------------------------------------------------------------------
    def test_probe_09_no_side_effects_on_attacks(self):
        """After all previous attacks, verify stock availability, ledger rows, and audit chain"""
        # Verify SHA-256 chain integrity
        status, res = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        self.assertTrue(res.get('success'))
        self.assertTrue(res.get('unbroken_chain') or res.get('valid'))

        # Verify no orphan holds in D1
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ma_bien_the, ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM")
        for row in cur.fetchall():
            self.assertGreaterEqual(row['ton_hien_co'], row['dang_giu_cho'], f"Stock oversold on {row['ma_bien_the']}")
            self.assertGreaterEqual(row['dang_giu_cho'], 0, f"Negative hold on {row['ma_bien_the']}")
        conn.close()


if __name__ == '__main__':
    unittest.main()
