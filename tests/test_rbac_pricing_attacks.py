"""
tests/test_rbac_pricing_attacks.py
Adversarial Stress Test Suite: RBAC Floor Price Validation & Dynamic Pricing Engine
Challenger: m2_challenger_2 (Milestone 2 - POS Sales, Pricing & 30-min Reservation Hold Engine)

Comprehensive empirical challenges covering:
1. Pricing calculation boundaries, negative/extreme dimensions, thickness checks, NaN/Infinity, SQL injection in wood type.
2. RBAC floor price validation, forged tokens, spoofed roles (worker claiming CHU/ADMIN, unregistered users), zero/negative prices, empty items.
3. Cryptographic hash chain and ledger invariance after all attacks.
"""

import os
import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
import threading
import time
import urllib.request
import urllib.error
import socketserver
import unittest

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class TestRbacPricingAttacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="challenger_m2_")
        cls.db_path = os.path.join(cls.temp_dir, "test_khanhvan.db")
        cls.port = 5592
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Initialize clean test DB
        server.DB_FILE = cls.db_path
        server.PORT = cls.port
        server.init_db()

        # Start server in background thread
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
        req_headers = {'Accept': 'application/json'}
        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                req_headers['Content-Type'] = 'application/json; charset=utf-8'
            elif isinstance(data, (str, bytes)):
                body = data.encode('utf-8') if isinstance(data, str) else data
                req_headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read().decode('utf-8')
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                return resp.status, parsed
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return e.code, parsed
        except Exception as ex:
            return 500, {'error': f"Connection failure: {ex}"}

    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==========================================================================
    # GROUP 1: DYNAMIC PRICING ENGINE ADVERSARIAL ATTACKS (F02)
    # ==========================================================================

    def test_adv_p01_pricing_extreme_negative_dimension(self):
        """Pricing: Negative dimensions must be rejected with HTTP 400 (DIMENSION_OUT_OF_BOUNDS)."""
        for neg_val in [-1, -400, -3000, -999999]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": neg_val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for {neg_val}, got {status}")
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('error'), 'DIMENSION_OUT_OF_BOUNDS')

    def test_adv_p02_pricing_zero_dimension(self):
        """Pricing: 0mm length or width must be rejected with HTTP 400."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 0}
        status, res = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 400)
        self.assertFalse(res.get('success'))

    def test_adv_p03_pricing_sub_boundary_dimensions(self):
        """Pricing: Dimensions just below 400mm (399mm, 399.9mm) must be rejected with HTTP 400."""
        for val in [399, 399.9, 399.999]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for {val}, got {status}")
            self.assertFalse(res.get('success'))

    def test_adv_p04_pricing_exact_boundary_dimensions(self):
        """Pricing: Exact boundary dimensions 400mm and 3000mm must succeed."""
        for val in [400, 400.0, 3000, 3000.0]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 200, f"Expected 200 for {val}, got {status}: {res}")
            self.assertTrue(res.get('success'))
            self.assertGreater(res.get('thanh_tien', 0), 0)

    def test_adv_p05_pricing_super_boundary_dimensions(self):
        """Pricing: Dimensions just above 3000mm (3000.1mm, 3001mm, 10000mm) must be rejected."""
        for val in [3000.1, 3001, 5000, 1000000]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for {val}, got {status}")
            self.assertFalse(res.get('success'))

    def test_adv_p06_pricing_dien_tich_width_boundaries(self):
        """Pricing: DIEN_TICH width (chieu_rong_mm) must also obey [400, 3000]mm boundaries."""
        # Width < 400
        payload1 = {"kieu_tinh": "DIEN_TICH", "loai_go": "Sồi Nga", "chieu_dai_mm": 1000, "chieu_rong_mm": 350}
        status1, res1 = self.request('POST', '/api/pricing/calculate', payload1)
        self.assertEqual(status1, 400)
        self.assertEqual(res1.get('error'), 'DIMENSION_OUT_OF_BOUNDS')

        # Width > 3000
        payload2 = {"kieu_tinh": "DIEN_TICH", "loai_go": "Sồi Nga", "chieu_dai_mm": 1000, "chieu_rong_mm": 3500}
        status2, res2 = self.request('POST', '/api/pricing/calculate', payload2)
        self.assertEqual(status2, 400)
        self.assertEqual(res2.get('error'), 'DIMENSION_OUT_OF_BOUNDS')

        # Both at exact min boundary (400x400)
        payload3 = {"kieu_tinh": "DIEN_TICH", "loai_go": "Sồi Nga", "chieu_dai_mm": 400, "chieu_rong_mm": 400}
        status3, res3 = self.request('POST', '/api/pricing/calculate', payload3)
        self.assertEqual(status3, 200)
        self.assertEqual(res3.get('kich_thuoc_tinh'), 0.16)

    def test_adv_p07_pricing_thickness_bounds(self):
        """Pricing: Thickness do_day_mm < 10mm must be rejected with HTTP 400 INVALID_THICKNESS."""
        for val in [-5, 0, 5, 9, 9.9]:
            payload = {"kieu_tinh": "DIEN_TICH", "chieu_dai_mm": 1000, "chieu_rong_mm": 1000, "do_day_mm": val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for do_day_mm={val}, got {status}")
            self.assertEqual(res.get('error'), 'INVALID_THICKNESS')

        # Valid thickness >= 10
        payload_ok = {"kieu_tinh": "DIEN_TICH", "chieu_dai_mm": 1000, "chieu_rong_mm": 1000, "do_day_mm": 10}
        status_ok, res_ok = self.request('POST', '/api/pricing/calculate', payload_ok)
        self.assertEqual(status_ok, 200)

    def test_adv_p08_pricing_string_dimension_formats(self):
        """Pricing: String parsing of dimensions supports '2m4', '2.4m', '2400mm', but rejects invalid formats."""
        # Valid string formats
        for s, expected_mm in [('2m4', 2.4), ('2.4m', 2.4), ('2400mm', 2.4), ('2400', 2.4)]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": s}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 200, f"Expected 200 for format '{s}'")
            self.assertEqual(res.get('kich_thuoc_tinh'), expected_mm)

        # Invalid string formats
        for s in ['3m5', '0m2', 'invalid_string', '1000xyz', '']:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": s}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for invalid format '{s}', got {status}")

    def test_adv_p09_pricing_sql_injection_in_wood_type(self):
        """Pricing: SQL injection in loai_go or formula must be safely handled without SQL error."""
        payload = {
            "kieu_tinh": "MET_DAI",
            "loai_go": "Mít' OR '1'='1'; DROP TABLE D1_SAN_PHAM; --",
            "chieu_dai_mm": 2000
        }
        status, res = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200, "Should safely resolve or fallback without executing SQL")

        # Verify D1_SAN_PHAM still exists intact
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D1_SAN_PHAM")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreater(count, 0, "Database table must remain intact")

    def test_adv_p10_pricing_missing_or_invalid_formula(self):
        """Pricing: Missing or invalid formula type must return HTTP 400."""
        # Missing
        status1, res1 = self.request('POST', '/api/pricing/calculate', {})
        self.assertEqual(status1, 400)
        self.assertEqual(res1.get('error'), 'MISSING_FORMULA')

        # Invalid enum
        status2, res2 = self.request('POST', '/api/pricing/calculate', {"kieu_tinh": "THE_TICH"})
        self.assertEqual(status2, 400)
        self.assertEqual(res2.get('error'), 'INVALID_FORMULA')

    # ==========================================================================
    # GROUP 2: RBAC FLOOR PRICE GATE & ORDER ATTACKS (F05 & F03)
    # ==========================================================================

    def test_adv_r01_worker_below_floor_strictly_blocked_403(self):
        """RBAC: Worker (THO) selling below floor price must be rejected with HTTP 403 FLOOR_PRICE_VIOLATION."""
        # GUONG-HOP-SOI-1800: gia_san is 8,100,000đ
        for price in [8099999, 8000000, 7500000, 6800000, 1000000]:
            payload = {
                "khach_hang": f"Attacker Price {price}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": "THO",
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": price, "thanh_tien": price}],
                "hinh_thuc_tt": "VIETQR"
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 403, f"Expected 403 for price {price}, got {status}")
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('error'), 'FLOOR_PRICE_VIOLATION')

    def test_adv_r02_worker_zero_and_negative_prices_rejected(self):
        """RBAC: Worker creating order with 0đ or negative price must be rejected."""
        for price in [0, -1, -5000000]:
            payload = {
                "khach_hang": "Negative Price Attacker",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": "THO",
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": price, "thanh_tien": price}],
                "hinh_thuc_tt": "VIETQR"
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertIn(status, [400, 403], f"Price {price} must be rejected, got {status}")
            self.assertFalse(res.get('success'))

    def test_adv_r03_forged_approval_tokens_rejected_403(self):
        """RBAC: Forged, expired, or malformed approval tokens must be rejected with HTTP 403."""
        forged_tokens = [
            "OWNER_APPROVAL_2025",
            "OWNER_APPROVAL_2027",
            "owner_approval_2026", # lowercase
            "ADMIN_OVERRIDE_TRUE",
            "TOKEN_ABC123",
            "123456",
            "' OR '1'='1",
            "null",
            "true",
            "",
            "   "
        ]
        for token in forged_tokens:
            payload = {
                "khach_hang": "Token Forger",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": "THO",
                "auth_token_duyet": token,
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
                "hinh_thuc_tt": "VIETQR"
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 403, f"Expected 403 for token '{token}', got {status}")
            self.assertEqual(res.get('error'), 'FLOOR_PRICE_VIOLATION')

    def test_adv_r04_client_role_spoofing_worker_claims_owner(self):
        """
        RBAC VULNERABILITY CHALLENGE:
        A worker (anhnam@khanhvan.vn, whose D8 record has vai_tro='THO') attempts to bypass
        the floor price gate by claiming 'vai_tro_nguoi_lap': 'CHU' in the request JSON.

        The server MUST NOT allow role spoofing. An account with vai_tro='THO' in D8_TAI_KHOAN
        must NOT be granted Owner privileges simply because client payload specified 'CHU'.
        """
        payload = {
            "khach_hang": "Role Spoofing Test",
            "nguoi_lap": "anhnam@khanhvan.vn",       # Registered worker in D8_TAI_KHOAN
            "vai_tro_nguoi_lap": "CHU",               # Spoofed role
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        # We record whether the server blocked this attack or allowed it.
        # Under strict RBAC, this must return HTTP 403.
        # If it returns HTTP 200, this proves a role spoofing vulnerability!
        self.assertEqual(status, 403, f"Role spoofing attack succeeded! Worker bypassed floor price by sending vai_tro_nguoi_lap='CHU'. Status: {status}, Response: {res}")

    def test_adv_r05_client_role_spoofing_unknown_user_claims_owner(self):
        """
        RBAC VULNERABILITY CHALLENGE:
        An unregistered user (imposter@unknown.com) attempts to create an order below floor price
        by claiming 'vai_tro_nguoi_lap': 'CHU'.

        Unauthenticated / unregistered users must not be able to self-assign CHU/ADMIN roles.
        """
        payload = {
            "khach_hang": "Anonymous Attacker",
            "nguoi_lap": "imposter@unknown.com",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [401, 403], f"Unregistered user allowed to create discount order by spoofing CHU! Status: {status}")

    def test_adv_r06_empty_or_malformed_items(self):
        """Order: Empty items array, null items, or non-dict items must return HTTP 400."""
        # Empty array
        s1, r1 = self.request('POST', '/api/orders', {"khach_hang": "Test", "items": []})
        self.assertEqual(s1, 400)
        self.assertEqual(r1.get('error'), 'EMPTY_ITEMS')

        # None items
        s2, r2 = self.request('POST', '/api/orders', {"khach_hang": "Test", "items": None})
        self.assertEqual(s2, 400)

        # List of non-dicts
        s3, r3 = self.request('POST', '/api/orders', {"khach_hang": "Test", "items": ["GUONG-HOP-SOI-1800"]})
        self.assertEqual(s3, 400)
        self.assertEqual(r3.get('error'), 'INVALID_ITEM')

    def test_adv_r07_zero_or_negative_quantity(self):
        """Order: Item quantity <= 0 or non-integer must return HTTP 400 INVALID_QUANTITY."""
        for qty in [0, -1, -99, "two", None]:
            payload = {
                "khach_hang": "Invalid Qty",
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": qty, "don_gia": 8500000}]
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 400, f"Expected 400 for qty {qty}, got {status}")
            self.assertEqual(res.get('error'), 'INVALID_QUANTITY')

    def test_adv_r08_nonexistent_product_variant(self):
        """Order: Nonexistent product code must return HTTP 404 PRODUCT_NOT_FOUND."""
        payload = {
            "khach_hang": "Unknown Product",
            "items": [{"ma_bien_the": "NON_EXISTENT_SP_9999", "so_luong": 1, "don_gia": 1000000}]
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 404)
        self.assertEqual(res.get('error'), 'PRODUCT_NOT_FOUND')

    def test_adv_r09_empty_customer_name(self):
        """Order: Blank or whitespace customer name must return HTTP 400 INVALID_CUSTOMER."""
        for name in ["", "   ", "\t\n"]:
            payload = {
                "khach_hang": name,
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000}]
            }
            status, res = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 400, f"Expected 400 for customer '{name}', got {status}")
            self.assertEqual(res.get('error'), 'INVALID_CUSTOMER')

    def test_adv_r10_stock_oversell_rejection(self):
        """Order: Ordering quantity exceeding ton_kha_dung must return HTTP 400 INSUFFICIENT_STOCK."""
        payload = {
            "khach_hang": "Stock Saturation",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 999999, "don_gia": 8500000}]
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 400)
        self.assertEqual(res.get('error'), 'INSUFFICIENT_STOCK')

    def test_adv_r11_forged_thanh_tien_calculation_bypass(self):
        """
        PRICING INTEGRITY CHALLENGE:
        A malicious client attempts to sell a luxury bed at listed unit price (don_gia=8500000),
        bypassing the don_gia < gia_san floor check, but specifies forged thanh_tien=1000.
        The server MUST recalculate thanh_tien = don_gia * so_luong and reject forged sums.
        """
        payload = {
            "khach_hang": "Math Forger",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{
                "ma_bien_the": "GUONG-HOP-SOI-1800",
                "so_luong": 1,
                "don_gia": 8500000,
                "thanh_tien": 1000  # Forged 1,000 VND instead of 8,500,000 VND
            }],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        # Server should not blindly accept forged thanh_tien: 1000
        if status == 200:
            tong_tien = res.get('tong_tien')
            self.assertEqual(tong_tien, 8500000, f"Server accepted forged thanh_tien! tong_tien was {tong_tien} instead of 8,500,000")

    def test_adv_r12_negative_don_gia_owner(self):
        """
        PRICING INTEGRITY CHALLENGE:
        An Owner attempts to create an order with negative don_gia (-1,000,000 VND).
        Even for Owner, unit prices and order totals cannot be negative.
        """
        payload = {
            "khach_hang": "Negative Price Owner",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{
                "ma_bien_the": "GUONG-HOP-SOI-1800",
                "so_luong": 1,
                "don_gia": -1000000,
                "thanh_tien": -1000000
            }],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 422], f"Negative unit price accepted for Owner! Status: {status}, Response: {res}")

    def test_adv_p11_pricing_nan_dimensions(self):
        """
        PRICING FUZZING CHALLENGE:
        Passing NaN or Infinity values into pricing calculation must be rejected safely
        without crashing the server (HTTP 500) or uncaught ValueError.
        """
        for val in ["NaN", "Infinity", "-Infinity"]:
            payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": val}
            status, res = self.request('POST', '/api/pricing/calculate', payload)
            self.assertEqual(status, 400, f"Expected 400 for {val}, got {status}: {res}")


    # ==========================================================================
    # GROUP 3: LEDGER AND AUDIT INVARIANTS AFTER ATTACKS
    # ==========================================================================

    def test_adv_i01_no_phantom_holds_after_rejected_orders(self):
        """Invariant: Rejected orders must not increment dang_giu_cho in D1 or write to D4."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        initial_hold = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE loai_dong = 'GIU_CHO'")
        initial_d4_holds = cur.fetchone()[0]
        conn.close()

        # Fire multiple invalid requests
        self.request('POST', '/api/orders', {
            "khach_hang": "Phantom Test 1", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 5000000}]
        })
        self.request('POST', '/api/orders', {
            "khach_hang": "Phantom Test 2", "items": [{"ma_bien_the": "NON_EXISTENT", "so_luong": 1}]
        })
        self.request('POST', '/api/orders', {
            "khach_hang": "", "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1}]
        })

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        final_hold = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE loai_dong = 'GIU_CHO'")
        final_d4_holds = cur.fetchone()[0]
        conn.close()

        self.assertEqual(final_hold, initial_hold, "dang_giu_cho must not leak on rejected orders")
        self.assertEqual(final_d4_holds, initial_d4_holds, "D4_SO_CAI_TON must not receive rows on rejected orders")

    def test_adv_i02_sha256_audit_chain_integrity(self):
        """Invariant: Cryptographic SHA-256 hash chain in D9_NHAT_KY must remain valid and unbroken."""
        status, res = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        self.assertTrue(res.get('success'))
        is_valid = res.get('unbroken_chain') or res.get('valid')
        self.assertTrue(is_valid, f"SHA-256 audit chain broken after attacks: {res}")


if __name__ == '__main__':
    unittest.main()
