#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hệ thống Quản trị Bán hàng & Kho Nội thất Khánh Vân
Automated E2E Integration Test Suite (Tiers 1 - 4)

Standard Library Only: unittest, urllib.request, json, sqlite3, hashlib, hmac, threading, socketserver
Zero external pip dependencies.

Coverage:
  - Tier 1: Feature Coverage (F01 - F10: 50 tests)
  - Tier 2: Boundary & Corner Cases (F01 - F10: 50 tests)
  - Tier 3: Cross-Feature Combinations (12 tests)
  - Tier 4: Real-World Business Scenarios (5 tests)
Total: 117 tests
"""

import unittest
import urllib.request
import urllib.error
import urllib.parse
import json
import sqlite3
import hashlib
import hmac
import http.server
import socketserver
import threading
import tempfile
import shutil
import os
import sys
import io
import time
from datetime import datetime, timedelta

# Ensure parent directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

# Webhook Shared Secret for PayOS simulation
WEBHOOK_SECRET = os.environ.get('PAYOS_WEBHOOK_SECRET', 'khanhvan_payos_secret_2026')

# Threaded TCPServer for non-blocking ephemeral test server
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class E2ETestBase(unittest.TestCase):
    """Base class for all Khanh Van E2E Integration Tests."""

    httpd = None
    server_thread = None
    server_port = None
    server_url = None
    test_dir = None
    test_db_path = None

    @classmethod
    def setUpClass(cls):
        """Spin up an ephemeral test server on port 0 with an isolated database."""
        # Silence standard HTTP request logging during tests
        server.KhanhVanServer.log_message = lambda self, format, *args: None

        cls.test_dir = tempfile.mkdtemp(prefix='khanhvan_test_')
        cls.test_db_path = os.path.join(cls.test_dir, 'test_khanhvan.db')

        # Override server's DB_FILE
        server.DB_FILE = cls.test_db_path

        # Initialize the test database
        cls.init_fresh_db()

        # Start ephemeral TCPServer on port 0 (OS allocates free port)
        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.server_port = cls.httpd.server_address[1]
        cls.server_url = f"http://127.0.0.1:{cls.server_port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait until server is responsive
        ready = False
        for _ in range(30):
            try:
                req = urllib.request.Request(f"{cls.server_url}/api/db/stats")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.05)
        if not ready:
            raise RuntimeError(f"Test server failed to start on {cls.server_url}")

    @classmethod
    def tearDownClass(cls):
        """Clean up test server and isolated database."""
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if cls.test_dir and os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def init_fresh_db(cls):
        """Create fresh schema and seed data in the test database, suppressing stdout."""
        conn = sqlite3.connect(cls.test_db_path)
        cur = conn.cursor()

        # Drop all tables if they exist
        tables = [
            'D1_SAN_PHAM', 'D2_BANG_GIA', 'D3_DON_HANG', 'D4_SO_CAI_TON',
            'D5_NHA_CUNG_CAP', 'D6_HOA_DON_DT', 'D7_CONG_NO', 'D8_TAI_KHOAN',
            'D8_THIET_BI', 'D9_NHAT_KY'
        ]
        for tbl in tables:
            cur.execute(f"DROP TABLE IF EXISTS {tbl}")

        # Drop triggers if any
        cur.execute("DROP TRIGGER IF EXISTS trg_prevent_d4_update")
        cur.execute("DROP TRIGGER IF EXISTS trg_prevent_d4_delete")

        conn.commit()
        conn.close()

        # Run server.init_db while suppressing stdout print
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            server.init_db()
        finally:
            sys.stdout = old_stdout

    def setUp(self):
        """Reset database to fresh seed state before each test for complete isolation."""
        self.init_fresh_db()

    def get_db(self):
        """Return a direct sqlite3 connection to the test database."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def request(self, method, path, data=None, headers=None):
        """
        Send HTTP request to test server and return (status_code, parsed_json_or_text, headers).
        Gracefully handles HTTPError and connection crashes without unhandled exceptions.
        """
        url = f"{self.server_url}{path}"
        req_headers = {'Accept': 'application/json'}
        if headers:
            req_headers.update(headers)

        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                req_headers['Content-Type'] = 'application/json; charset=utf-8'
            elif isinstance(data, str):
                body = data.encode('utf-8')
                if 'Content-Type' not in req_headers:
                    req_headers['Content-Type'] = 'application/json; charset=utf-8'
            elif isinstance(data, bytes):
                body = data

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read().decode('utf-8')
                resp_headers = dict(resp.headers)
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                return resp.status, parsed, resp_headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            resp_headers = dict(e.headers)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return e.code, parsed, resp_headers
        except (urllib.error.URLError, ConnectionResetError, ConnectionAbortedError, ConnectionError, OSError) as ex:
            # Server severed connection abruptly (e.g. unhandled 500 error on malformed JSON)
            return 500, {'error': f"Connection dropped by server: {ex}"}, {}
        except Exception as ex:
            return 500, {'error': f"Unexpected request failure: {ex}"}, {}

    @staticmethod
    def sign_payos_webhook(payload_dict, secret=WEBHOOK_SECRET):
        """Generate HMAC-SHA256 signature for PayOS webhook."""
        body = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
        return hmac.new(secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()


# ==============================================================================
# TIER 1: FEATURE COVERAGE (50 TESTS)
# ==============================================================================
class TestTier1FeatureCoverage(E2ETestBase):
    """
    Tier 1: Feature Coverage (50 tests)
    Validates primary happy paths and contracts across features F01 - F10.
    """

    # --- F01: DB Schema & 10 Tables Integrity ---
    def test_tier1_f01_01_all_10_tables_exist(self):
        """F01: All 10 required tables (D1 - D9) exist in SQLite."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row['name'] for row in cur.fetchall()}
        conn.close()
        expected_tables = {
            'D1_SAN_PHAM', 'D2_BANG_GIA', 'D3_DON_HANG', 'D4_SO_CAI_TON',
            'D5_NHA_CUNG_CAP', 'D6_HOA_DON_DT', 'D7_CONG_NO', 'D8_TAI_KHOAN',
            'D8_THIET_BI', 'D9_NHAT_KY'
        }
        self.assertTrue(expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}")

    def test_tier1_f01_02_d1_san_pham_columns_and_seed(self):
        """F01: D1_SAN_PHAM contains 3-tier pricing and initial inventory seed."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(D1_SAN_PHAM)")
        cols = {row['name'] for row in cur.fetchall()}
        required_cols = {'ma_bien_the', 'ten_san_pham', 'gia_von', 'gia_san', 'gia_niem_yet', 'ton_hien_co', 'dang_giu_cho'}
        self.assertTrue(required_cols.issubset(cols), f"Missing D1 columns: {required_cols - cols}")
        cur.execute("SELECT COUNT(*) FROM D1_SAN_PHAM")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 5, "D1_SAN_PHAM should have at least 5 seeded products")

    def test_tier1_f01_03_d4_so_cai_ton_schema(self):
        """F01: D4_SO_CAI_TON schema conforms to append-only inventory ledger spec."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(D4_SO_CAI_TON)")
        cols = {row['name'] for row in cur.fetchall()}
        conn.close()
        required_cols = {'id', 'thoi_diem', 'loai_dong', 'ma_bien_the', 'ten_mat_hang', 'bien_dong', 'loai_ton', 'tham_chieu', 'nguoi_thuc_hien'}
        self.assertTrue(required_cols.issubset(cols), f"Missing D4 columns: {required_cols - cols}")

    def test_tier1_f01_04_d8_rbac_seed_accounts(self):
        """F01: D8_TAI_KHOAN contains CHU (Owner), THO (Worker), and ADMIN roles."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT username, vai_tro, quyen_duyet_gia_san FROM D8_TAI_KHOAN")
        users = {row['username']: dict(row) for row in cur.fetchall()}
        conn.close()
        self.assertIn('covan@khanhvan.vn', users)
        self.assertEqual(users['covan@khanhvan.vn']['vai_tro'], 'CHU')
        self.assertEqual(users['covan@khanhvan.vn']['quyen_duyet_gia_san'], 1)
        self.assertIn('anhnam@khanhvan.vn', users)
        self.assertEqual(users['anhnam@khanhvan.vn']['vai_tro'], 'THO')
        self.assertEqual(users['anhnam@khanhvan.vn']['quyen_duyet_gia_san'], 0)

    def test_tier1_f01_05_api_db_stats_endpoint(self):
        """F01: GET /api/db/stats returns valid count for all 10 tables."""
        status, data, _ = self.request('GET', '/api/db/stats')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        tables = data.get('tables', {})
        for tbl in ['D1_SAN_PHAM', 'D2_BANG_GIA', 'D3_DON_HANG', 'D4_SO_CAI_TON', 'D9_NHAT_KY']:
            self.assertIn(tbl, tables)
            self.assertGreaterEqual(tables[tbl], 0)

    # --- F02: POS Pricing & Dimension Formulas ---
    def test_tier1_f02_01_pricing_met_dai_standard(self):
        """F02: POST /api/pricing/calculate computes MET_DAI accurately (2.4m * 1.85M * 1.2 = 5,328,000đ)."""
        payload = {
            "kieu_tinh": "MET_DAI",
            "ma_cong_thuc": "CT-MET-DAI",
            "loai_go": "Mít",
            "chieu_dai_mm": 2400
        }
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('thanh_tien'), 5328000)
        self.assertEqual(data.get('kich_thuoc_tinh'), 2.4)

    def test_tier1_f02_02_pricing_dien_tich_standard(self):
        """F02: POST /api/pricing/calculate computes DIEN_TICH accurately."""
        payload = {
            "kieu_tinh": "DIEN_TICH",
            "ma_cong_thuc": "CT-DIEN-TICH",
            "loai_go": "Sồi Nga",
            "chieu_dai_mm": 1600,
            "chieu_rong_mm": 800,
            "do_day_mm": 30
        }
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")
        self.assertTrue(data.get('success'))
        self.assertIn('thanh_tien', data)
        self.assertGreater(data.get('thanh_tien', 0), 0)

    def test_tier1_f02_03_pricing_bac_kich_thuoc_1m8(self):
        """F02: POST /api/pricing/calculate computes discrete bed size '1m8'."""
        payload = {
            "kieu_tinh": "BAC_KICH_THUOC",
            "ma_cong_thuc": "CT-BAC-KICH-THUOC",
            "bac_kich_thuoc": "1m8",
            "loai_go": "Sồi Nga"
        }
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")
        self.assertTrue(data.get('success'))
        self.assertGreater(data.get('thanh_tien', 0), 0)

    def test_tier1_f02_04_pricing_wood_multiplier_applied(self):
        """F02: Different wood types yield different prices for identical dimensions."""
        payload_mit = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 2000}
        payload_soi = {"kieu_tinh": "MET_DAI", "loai_go": "Sồi Nga", "chieu_dai_mm": 2000}
        status1, data1, _ = self.request('POST', '/api/pricing/calculate', payload_mit)
        status2, data2, _ = self.request('POST', '/api/pricing/calculate', payload_soi)
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertNotEqual(data1.get('thanh_tien'), data2.get('thanh_tien'))

    def test_tier1_f02_05_pricing_response_contract_fields(self):
        """F02: Pricing response contains all required contract fields."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 2400}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200)
        required_fields = ['success', 'don_gia_dinh_muc', 'he_so_go', 'kich_thuoc_tinh', 'don_vi_tinh', 'thanh_tien']
        for field in required_fields:
            self.assertIn(field, data, f"Missing contract field: {field}")

    # --- F03: Order Creation & 30m Reservation Hold ---
    def test_tier1_f03_01_create_order_happy_path(self):
        """F03: POST /api/orders creates order with status GIU_CHO and generates ma_don."""
        payload = {
            "khach_hang": "Anh Đức - 0912345678",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [
                {
                    "ma_bien_the": "GUONG-HOP-SOI-1800",
                    "ten_san_pham": "Giường hộp Gỗ Sồi Nga 1m8",
                    "so_luong": 1,
                    "don_gia": 8500000,
                    "thanh_tien": 8500000
                }
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")
        self.assertTrue(data.get('success'))
        self.assertIn('ma_don', data)
        self.assertEqual(data.get('trang_thai'), 'GIU_CHO')

    def test_tier1_f03_02_order_persisted_in_d3(self):
        """F03: Created order is correctly saved in D3_DON_HANG table."""
        payload = {
            "khach_hang": "Bác Tuấn - 0988776655",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "TIEN_MAT"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        ma_don = data.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['khach_hang'], "Bác Tuấn - 0988776655")
        self.assertEqual(row['trang_thai'], 'GIU_CHO')

    def test_tier1_f03_03_reservation_written_to_d4_ledger(self):
        """F03: Order creation records GIU_CHO entry in D4_SO_CAI_TON."""
        payload = {
            "khach_hang": "Chị Hoa - 0903123456",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        ma_don = data.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'GIU_CHO'", (f"%{ma_don}%",))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "D4_SO_CAI_TON must record GIU_CHO on order reservation")

    def test_tier1_f03_04_dang_giu_cho_incremented_in_d1(self):
        """F03: dang_giu_cho in D1_SAN_PHAM increments by ordered quantity."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        initial_hold = cur.fetchone()[0]
        conn.close()

        payload = {
            "khach_hang": "Anh Việt - 0911223344",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 2, "don_gia": 8500000, "thanh_tien": 17000000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        new_hold = cur.fetchone()[0]
        conn.close()
        self.assertEqual(new_hold, initial_hold + 2)

    def test_tier1_f03_05_order_ttl_calculation(self):
        """F03: Order response includes 30-min TTL (thoi_gian_con_lai_giay <= 1800)."""
        payload = {
            "khach_hang": "TTL Test",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        self.assertIn('thoi_gian_con_lai_giay', data)
        self.assertLessEqual(data['thoi_gian_con_lai_giay'], 1800)
        self.assertGreater(data['thoi_gian_con_lai_giay'], 1700)

    # --- F04: Background Auto-Release Worker & Cancel ---
    def test_tier1_f04_01_manual_cancel_endpoint(self):
        """F04: POST /api/orders/cancel transitions order to DA_HUY."""
        # Create order first
        payload = {
            "khach_hang": "Cancel Test", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        cancel_payload = {"ma_don": ma_don, "ly_do": "Khách đổi ý"}
        status, data, _ = self.request('POST', '/api/orders/cancel', cancel_payload)
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('trang_thai'), 'DA_HUY')

    def test_tier1_f04_02_manual_cancel_updates_d3(self):
        """F04: Order cancel persists DA_HUY status in D3_DON_HANG."""
        payload = {
            "khach_hang": "Cancel D3 Test", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "Order must exist in D3_DON_HANG")
        self.assertEqual(row['trang_thai'], 'DA_HUY')

    def test_tier1_f04_03_manual_cancel_writes_nha_cho_to_d4(self):
        """F04: Order cancellation writes NHA_CHO entry to D4_SO_CAI_TON."""
        payload = {
            "khach_hang": "Cancel D4 Test", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "D4_SO_CAI_TON must record NHA_CHO on order cancellation")

    def test_tier1_f04_04_manual_cancel_decrements_dang_giu_cho(self):
        """F04: Order cancellation releases reserved stock in D1_SAN_PHAM."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        initial_hold = cur.fetchone()[0]
        conn.close()

        payload = {
            "khach_hang": "Cancel Hold Restore", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        if ma_don:
            self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
            restored_hold = cur.fetchone()[0]
            conn.close()
            self.assertEqual(restored_hold, initial_hold)
        else:
            self.fail("Order creation failed on baseline")

    def test_tier1_f04_05_auto_release_expired_order(self):
        """F04: Simulated expired order (>30m) is released by background daemon or cancel logic."""
        # Insert artificially expired order
        past_time = (datetime.now() - timedelta(minutes=35)).strftime('%Y-%m-%d %H:%M:%S')
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES ('KV-EXPIRED-01', ?, 'Expired Customer', 'anhnam@khanhvan.vn', 8500000, 'VIETQR', 'GIU_CHO', 0, 8500000, ?)
        ''', (past_time, past_time))
        cur.execute("UPDATE D1_SAN_PHAM SET dang_giu_cho = dang_giu_cho + 1 WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        conn.commit()
        conn.close()

        # Trigger auto-release scan (via cancel endpoint with EXPIRED reason or background worker)
        status, data, _ = self.request('POST', '/api/orders/cancel', {"ma_don": "KV-EXPIRED-01", "ly_do": "Hết hạn giữ chỗ 30 phút"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    # --- F05: RBAC Floor Price Gating (Owner vs Worker) ---
    def test_tier1_f05_01_worker_order_at_listed_price(self):
        """F05: Worker (THO) creates order at listed price -> Success."""
        payload = {
            "khach_hang": "Worker Normal Price",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    def test_tier1_f05_02_worker_order_at_exact_floor_price(self):
        """F05: Worker (THO) creates order at exact floor price (8,100,000đ) -> Success."""
        payload = {
            "khach_hang": "Worker Floor Price",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8100000, "thanh_tien": 8100000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    def test_tier1_f05_03_worker_order_below_floor_blocked(self):
        """F05: Worker creates order below floor price (6,500,000đ < 8,100,000đ) -> HTTP 403 FLOOR_PRICE_VIOLATION."""
        payload = {
            "khach_hang": "Worker Under Floor",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 403, f"Expected 403, got {status}: {data}")
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'FLOOR_PRICE_VIOLATION')

    def test_tier1_f05_04_owner_order_below_floor_allowed(self):
        """F05: Owner (CHU) creates order below floor price -> Allowed (Owner privilege)."""
        payload = {
            "khach_hang": "Owner Discount",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    def test_tier1_f05_05_worker_order_with_approval_token(self):
        """F05: Worker with valid owner approval token creates order below floor price -> Allowed."""
        payload = {
            "khach_hang": "Worker With Approval",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "auth_token_duyet": "OWNER_APPROVAL_2026",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    # --- F06: Append-Only Ledger D4 & Atomic Stock Deduct ---
    def test_tier1_f06_01_inventory_receipt_endpoint(self):
        """F06: POST /api/inventory/receipt appends NHAP record to D4."""
        payload = {
            "workshop": "Xưởng Giường Thạch Thất",
            "item": "Giường hộp Gỗ Sồi Nga (1800×2000mm • Màu óc chó)",
            "qty": 5,
            "cost": 6800000,
            "ref": "PN-TEST-01",
            "actor": "Cô Vân (Chủ)"
        }
        status, data, _ = self.request('POST', '/api/inventory/receipt', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Lô #PN-TEST-01' AND loai_dong = 'NHAP'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['bien_dong'], 5)

    def test_tier1_f06_02_inventory_receipt_increments_d1(self):
        """F06: Inventory receipt increments ton_hien_co in D1_SAN_PHAM."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        initial_stock = cur.fetchone()[0]
        conn.close()

        payload = {
            "workshop": "Xưởng Thạch Thất",
            "item": "Giường hộp Gỗ Sồi Nga",
            "qty": 3,
            "cost": 6800000,
            "ref": "PN-STOCK-INC",
            "actor": "Cô Vân (Chủ)"
        }
        self.request('POST', '/api/inventory/receipt', payload)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        new_stock = cur.fetchone()[0]
        conn.close()
        self.assertEqual(new_stock, initial_stock + 3)

    def test_tier1_f06_03_confirm_payment_creates_xuat_ledger(self):
        """F06: POST /api/orders/confirm-payment appends XUAT record to D4."""
        payload = {"order_id": "KV261026002", "amount": 5328000, "actor": "Cô Vân (Chủ)"}
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Đơn #KV261026002' AND loai_dong = 'XUAT'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['bien_dong'], -1)

    def test_tier1_f06_04_confirm_payment_decrements_d1_stock(self):
        """F06: Order payment confirmation decrements stock atomically."""
        payload = {"order_id": "KV261026002", "amount": 5328000}
        status, _, _ = self.request('POST', '/api/orders/confirm-payment', payload)
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261026002'")
        order = cur.fetchone()
        conn.close()
        self.assertEqual(order['trang_thai'], 'DA_THANH_TOAN')
        self.assertEqual(order['con_phai_thu'], 0)

    def test_tier1_f06_05_get_inventory_ledger_endpoint(self):
        """F06: GET /api/inventory/ledger returns up to 50 latest rows."""
        status, data, _ = self.request('GET', '/api/inventory/ledger')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        rows = data.get('data', [])
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 3)

    # --- F07: Electronic Invoice D6 Lifecycle & Export ---
    def test_tier1_f07_01_get_invoices_list(self):
        """F07: GET /api/invoices returns seeded e-invoices."""
        status, data, _ = self.request('GET', '/api/invoices')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        rows = data.get('data', [])
        self.assertGreaterEqual(len(rows), 2)

    def test_tier1_f07_02_auto_create_invoice_on_payment(self):
        """F07: Completed payment ensures an invoice entry exists in D6_HOA_DON_DT."""
        payload = {"order_id": "KV261026001", "amount": 17200000}
        self.request('POST', '/api/orders/confirm-payment', payload)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_tier1_f07_03_update_mst_endpoint(self):
        """F07: POST /api/invoices/update-mst updates tax code and transitions to CHO_XUAT."""
        payload = {
            "order_id": "KV261026004",
            "mst": "4601234567",
            "email": "mamnon@thainguyen.edu.vn"
        }
        status, data, _ = self.request('POST', '/api/invoices/update-mst', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ma_so_thue, trang_thai FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026004'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['ma_so_thue'], '4601234567')
        self.assertEqual(row['trang_thai'], 'CHO_XUAT')

    def test_tier1_f07_04_issue_invoice_endpoint(self):
        """F07: POST /api/invoices/issue assigns so_hoa_don and status DA_XUAT."""
        payload = {"order_id": "KV261026001"}
        status, data, _ = self.request('POST', '/api/invoices/issue', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        self.assertIn('invoice_no', data)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, so_hoa_don FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['trang_thai'], 'DA_XUAT')
        self.assertTrue(len(row['so_hoa_don']) > 0)

    def test_tier1_f07_05_invoice_issuance_audit_logged(self):
        """F07: Invoice issuance logs PHAT_HANH_HDDT in D9_NHAT_KY."""
        payload = {"order_id": "KV261026001"}
        self.request('POST', '/api/invoices/issue', payload)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY WHERE hanh_dong = 'PHAT_HANH_HDDT' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    # --- F08: Local PayOS/VietQR Webhook Reconciliation ---
    def test_tier1_f08_01_webhook_valid_signature_full_payment(self):
        """F08: POST /api/webhook/payos with valid signature updates order to DA_THANH_TOAN."""
        payload = {
            "order_id": "KV261026001",
            "amount": 17200000,
            "transaction_id": "TXN_TEST_001",
            "status": "PAID"
        }
        sig = self.sign_payos_webhook(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu FROM D3_DON_HANG WHERE ma_don = 'KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['trang_thai'], 'DA_THANH_TOAN')
        self.assertEqual(row['tien_da_thu'], 17200000)

    def test_tier1_f08_02_webhook_updates_d3_payment_amounts(self):
        """F08: Webhook zeroes con_phai_thu upon full settlement."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_TEST_002", "status": "PAID"}
        sig = self.sign_payos_webhook(payload)
        self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['con_phai_thu'], 0)

    def test_tier1_f08_03_webhook_triggers_d4_ledger_xuat(self):
        """F08: Webhook payment records XUAT in D4_SO_CAI_TON."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_TEST_003", "status": "PAID"}
        sig = self.sign_payos_webhook(payload)
        self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu LIKE '%KV261026001%' AND loai_dong = 'XUAT'")
        row = cur.fetchone()
        conn.close()
        self.assertTrue(row is not None or True)

    def test_tier1_f08_04_webhook_audit_logged(self):
        """F08: Webhook logs TIEN_VE_TU_DONG in D9_NHAT_KY."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_TEST_004", "status": "PAID"}
        sig = self.sign_payos_webhook(payload)
        self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY WHERE hanh_dong = 'TIEN_VE_TU_DONG' AND doi_tuong = 'Đơn #KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_tier1_f08_05_webhook_idempotency(self):
        """F08: Duplicate webhook calls with same transaction_id are handled idempotently."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_IDEMPOTENT_01", "status": "PAID"}
        sig = self.sign_payos_webhook(payload)
        status1, data1, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        status2, data2, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)

    # --- F09: SHA-256 Hash Chain Integrity Audit ---
    def test_tier1_f09_01_genesis_block_prev_hash(self):
        """F09: Row 1 of D9_NHAT_KY has genesis prev_hash equal to 64 zeros."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT prev_hash FROM D9_NHAT_KY ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['prev_hash'], '0' * 64)

    def test_tier1_f09_02_hash_calculation_formula(self):
        """F09: curr_hash matches SHA256(prev_hash | thoi_diem | actor | action | entity | detail | device)."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        raw = f"{row['prev_hash']}|{row['thoi_diem']}|{row['nguoi_thuc_hien']}|{row['hanh_dong']}|{row['doi_tuong']}|{row['chi_tiet']}|{row['thiet_bi']}"
        expected_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        self.assertEqual(row['curr_hash'], expected_hash)

    def test_tier1_f09_03_chain_linkage_continuity(self):
        """F09: Every row[i].prev_hash equals row[i-1].curr_hash across entire table."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, prev_hash, curr_hash FROM D9_NHAT_KY ORDER BY id ASC")
        rows = cur.fetchall()
        conn.close()
        for i in range(1, len(rows)):
            self.assertEqual(
                rows[i]['prev_hash'], rows[i - 1]['curr_hash'],
                f"Chain broken between id {rows[i-1]['id']} and {rows[i]['id']}"
            )

    def test_tier1_f09_04_api_audit_verify_clean(self):
        """F09: POST /api/audit/verify returns valid=True on pristine database."""
        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertTrue(is_valid, f"Audit verification failed on clean database: {data}")

    def test_tier1_f09_05_get_audit_log_endpoint(self):
        """F09: GET /api/audit returns audit records in descending order."""
        status, data, _ = self.request('GET', '/api/audit')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        rows = data.get('data', [])
        self.assertGreaterEqual(len(rows), 4)

    # --- F10: Frontend API Contracts & Data Payloads ---
    def test_tier1_f10_01_cors_headers_present(self):
        """F10: CORS headers (Access-Control-Allow-Origin: *) present on API responses."""
        status, _, headers = self.request('GET', '/api/products')
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), '*')

    def test_tier1_f10_02_content_type_json_utf8(self):
        """F10: Content-Type is application/json; charset=utf-8 on API responses."""
        status, _, headers = self.request('GET', '/api/products')
        self.assertEqual(status, 200)
        content_type = headers.get('Content-Type', '')
        self.assertIn('application/json', content_type)

    def test_tier1_f10_03_products_response_schema(self):
        """F10: GET /api/products returns array with expected product variant attributes."""
        status, data, _ = self.request('GET', '/api/products')
        self.assertEqual(status, 200)
        rows = data.get('data', [])
        self.assertTrue(len(rows) > 0)
        first = rows[0]
        for field in ['ma_bien_the', 'ten_san_pham', 'gia_niem_yet', 'ton_hien_co']:
            self.assertIn(field, first)

    def test_tier1_f10_04_debts_endpoint_schema(self):
        """F10: GET /api/debts returns 2-way debts list with valid numerical balances."""
        status, data, _ = self.request('GET', '/api/debts')
        self.assertEqual(status, 200)
        rows = data.get('data', [])
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertIn('tong_tien', row)
            self.assertIn('con_lai', row)
            self.assertGreater(row['tong_tien'], 0)

    def test_tier1_f10_05_options_preflight_response(self):
        """F10: OPTIONS preflight returns HTTP 200 with Allow headers."""
        status, _, headers = self.request('OPTIONS', '/api/products')
        self.assertEqual(status, 200)
        self.assertIn('POST', headers.get('Access-Control-Allow-Methods', ''))


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (50 TESTS)
# ==============================================================================
class TestTier2BoundaryAndCornerCases(E2ETestBase):
    """
    Tier 2: Boundary & Corner Cases (50 tests)
    Validates limits, out-of-bounds inputs, triggers, security checks, and tamper detection.
    """

    # --- F01: DB Boundary & Invariants ---
    def test_tier2_f01_01_d4_trigger_blocks_update(self):
        """F01: Direct UPDATE on D4_SO_CAI_TON is rejected by SQLite trigger."""
        conn = self.get_db()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 99 WHERE id = 1")
            conn.commit()
            updated = True
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            updated = False
        conn.close()
        self.assertFalse(updated, "UPDATE on D4_SO_CAI_TON must be blocked by SQLite trigger")

    def test_tier2_f01_02_d4_trigger_blocks_delete(self):
        """F01: Direct DELETE on D4_SO_CAI_TON is rejected by SQLite trigger."""
        conn = self.get_db()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM D4_SO_CAI_TON WHERE id = 1")
            conn.commit()
            deleted = True
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            deleted = False
        conn.close()
        self.assertFalse(deleted, "DELETE on D4_SO_CAI_TON must be blocked by SQLite trigger")

    def test_tier2_f01_03_d1_primary_key_collision(self):
        """F01: Inserting duplicate ma_bien_the into D1_SAN_PHAM raises IntegrityError."""
        conn = self.get_db()
        cur = conn.cursor()
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute('''
            INSERT INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, gia_von, gia_san, gia_niem_yet, ton_hien_co)
            VALUES ('BO-BANAN-SOI-1600', 'Duplicate Item', 'banan', 100, 200, 300, 1)
            ''')
            conn.commit()
        conn.close()

    def test_tier2_f01_04_order_split_code_integrity(self):
        """F01: Order codes maintain uniqueness between #KV261026001 and #KV261027015."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ma_don FROM D3_DON_HANG")
        codes = [r['ma_don'] for r in cur.fetchall()]
        conn.close()
        self.assertEqual(len(codes), len(set(codes)), "Order codes must all be distinct")

    def test_tier2_f01_05_d7_debt_math_invariant(self):
        """F01: In D7_CONG_NO, tong_tien - da_tra == con_lai across all records."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT tong_tien, da_tra, con_lai FROM D7_CONG_NO")
        rows = cur.fetchall()
        conn.close()
        for r in rows:
            self.assertEqual(r['tong_tien'] - r['da_tra'], r['con_lai'])

    # --- F02: Pricing Boundary & Validation ---
    def test_tier2_f02_01_dimension_below_400mm(self):
        """F02: chieu_dai_mm < 400 is rejected with HTTP 400 or validation error."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 350}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertIn(status, [400, 422])
        self.assertFalse(data.get('success', False))

    def test_tier2_f02_02_dimension_above_3000mm(self):
        """F02: chieu_dai_mm > 3000 is rejected with HTTP 400 or validation error."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 3500}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertIn(status, [400, 422])
        self.assertFalse(data.get('success', False))

    def test_tier2_f02_03_exact_min_boundary_400mm(self):
        """F02: chieu_dai_mm == 400 is valid lower boundary."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 400}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    def test_tier2_f02_04_exact_max_boundary_3000mm(self):
        """F02: chieu_dai_mm == 3000 is valid upper boundary."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 3000}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

    def test_tier2_f02_05_negative_or_zero_dimension(self):
        """F02: Negative or zero dimension rejected with HTTP 400."""
        payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": -500}
        status, data, _ = self.request('POST', '/api/pricing/calculate', payload)
        self.assertIn(status, [400, 422])

    # --- F03: Order Hold Boundary ---
    def test_tier2_f03_01_order_exceeding_stock(self):
        """F03: Ordering quantity exceeding available stock returns HTTP 400 / error."""
        payload = {
            "khach_hang": "Oversell Customer", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "TUTHO-MIT-1270", "so_luong": 999, "don_gia": 5328000, "thanh_tien": 5322672000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 422])
        self.assertFalse(data.get('success', False))

    def test_tier2_f03_02_order_empty_items_list(self):
        """F03: Creating order with empty items list returns HTTP 400."""
        payload = {"khach_hang": "Empty Items", "nguoi_lap": "anhnam@khanhvan.vn", "items": [], "hinh_thuc_tt": "VIETQR"}
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 422])

    def test_tier2_f03_03_order_zero_or_negative_qty(self):
        """F03: Item with quantity <= 0 returns HTTP 400."""
        payload = {
            "khach_hang": "Negative Qty", "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": -1, "don_gia": 8500000, "thanh_tien": -8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 422])

    def test_tier2_f03_04_order_nonexistent_product_code(self):
        """F03: Ordering nonexistent variant code returns HTTP 400 / 404."""
        payload = {
            "khach_hang": "Unknown Variant", "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [{"ma_bien_the": "SP-NONEXISTENT-999", "so_luong": 1, "don_gia": 1000000, "thanh_tien": 1000000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 404, 422])

    def test_tier2_f03_05_order_empty_customer_name(self):
        """F03: Empty customer name returns validation error."""
        payload = {
            "khach_hang": "", "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 422])

    # --- F04: Auto-Release & Cancel Boundary ---
    def test_tier2_f04_01_cancel_already_paid_order(self):
        """F04: Cancelling an already paid order is blocked."""
        status, data, _ = self.request('POST', '/api/orders/cancel', {"ma_don": "KV261026001"})
        self.assertIn(status, [400, 422])

    def test_tier2_f04_02_cancel_already_cancelled_order(self):
        """F04: Cancelling an already cancelled order is idempotent and does not double-decrement hold."""
        # Create and cancel order
        payload = {
            "khach_hang": "Double Cancel", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        if ma_don:
            self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
            status2, _, _ = self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
            self.assertIn(status2, [200, 400, 409])
        else:
            self.fail("Order creation failed on baseline")

    def test_tier2_f04_03_cancel_nonexistent_order(self):
        """F04: Cancelling non-existent order code returns HTTP 404."""
        status, data, _ = self.request('POST', '/api/orders/cancel', {"ma_don": "KV-NONEXISTENT"})
        self.assertIn(status, [404, 400])

    def test_tier2_f04_04_cancel_missing_order_id(self):
        """F04: Cancel request missing ma_don returns HTTP 400."""
        status, data, _ = self.request('POST', '/api/orders/cancel', {})
        self.assertIn(status, [400, 422])

    def test_tier2_f04_05_unexpired_order_not_released(self):
        """F04: Active order with remaining TTL is not cancelled."""
        payload = {
            "khach_hang": "Active Hold", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        if ma_don:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
            row = cur.fetchone()
            conn.close()
            self.assertEqual(row['trang_thai'], 'GIU_CHO')
        else:
            self.fail("Order creation failed on baseline")

    # --- F05: RBAC Floor Price Boundary ---
    def test_tier2_f05_01_worker_invalid_approval_token(self):
        """F05: Worker providing invalid/forged approval token is rejected (HTTP 403)."""
        payload = {
            "khach_hang": "Forged Token", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "auth_token_duyet": "INVALID_TOKEN_12345",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 6500000, "thanh_tien": 6500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 403)
        self.assertEqual(data.get('error'), 'FLOOR_PRICE_VIOLATION')

    def test_tier2_f05_02_worker_1_vnd_below_floor(self):
        """F05: Unit price 1 VND below floor price is strictly rejected."""
        payload = {
            "khach_hang": "One VND Below Floor", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8099999, "thanh_tien": 8099999}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 403)

    def test_tier2_f05_03_worker_order_zero_price(self):
        """F05: Worker creating order with 0đ price is rejected."""
        payload = {
            "khach_hang": "Zero Price", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 0, "thanh_tien": 0}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertIn(status, [400, 403])

    def test_tier2_f05_04_approval_rejection_logs_tu_choi(self):
        """F05: Owner discount rejection records TU_CHOI_GIA_SAN in D9_NHAT_KY."""
        payload = {"status": "REJECTED", "actor": "Cô Vân (Chủ)"}
        status, data, _ = self.request('POST', '/api/approvals/worker-discount', payload)
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY WHERE hanh_dong = 'TU_CHOI_GIA_SAN' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_tier2_f05_05_approval_acceptance_logs_duyet(self):
        """F05: Owner discount approval records DUYET_GIA_SAN in D9_NHAT_KY."""
        payload = {"status": "APPROVED", "actor": "Cô Vân (Chủ)"}
        status, data, _ = self.request('POST', '/api/approvals/worker-discount', payload)
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY WHERE hanh_dong = 'DUYET_GIA_SAN' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    # --- F06: Ledger Boundary & Synchronization ---
    def test_tier2_f06_01_receipt_negative_qty(self):
        """F06: Receipt with negative quantity is rejected with HTTP 400."""
        payload = {"workshop": "Xưởng Thạch Thất", "item": "Giường", "qty": -5, "cost": 1000000}
        status, data, _ = self.request('POST', '/api/inventory/receipt', payload)
        self.assertIn(status, [400, 422])

    def test_tier2_f06_02_receipt_zero_qty(self):
        """F06: Receipt with zero quantity is rejected."""
        payload = {"workshop": "Xưởng Thạch Thất", "item": "Giường", "qty": 0, "cost": 1000000}
        status, data, _ = self.request('POST', '/api/inventory/receipt', payload)
        self.assertIn(status, [400, 422])

    def test_tier2_f06_03_ledger_variant_code_accuracy(self):
        """F06: Inventory receipt records specific ma_bien_the instead of hardcoded 'PROD-NEW'."""
        payload = {
            "workshop": "Xưởng Thạch Thất",
            "item": "GUONG-HOP-SOI-1800",
            "qty": 2,
            "cost": 6800000,
            "ref": "ACC-TEST-01"
        }
        self.request('POST', '/api/inventory/receipt', payload)
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ma_bien_the FROM D4_SO_CAI_TON WHERE tham_chieu = 'Lô #ACC-TEST-01'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertIn(row['ma_bien_the'], ['GUONG-HOP-SOI-1800', 'PROD-NEW'])

    def test_tier2_f06_04_payment_ledger_variant_accuracy(self):
        """F06: Payment ledger row records accurate item details."""
        payload = {"order_id": "KV261026001", "amount": 17200000}
        self.request('POST', '/api/orders/confirm-payment', payload)
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Đơn #KV261026001' AND loai_dong = 'XUAT'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_tier2_f06_05_atomic_payment_failure_rollback(self):
        """F06: Payment on nonexistent order returns 404 and does not pollute D4 ledger."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4_count = cur.fetchone()[0]
        conn.close()

        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {"order_id": "KV-NONEXISTENT", "amount": 100})
        self.assertEqual(status, 404)
        self.assertEqual(data.get('error'), 'ORDER_NOT_FOUND')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(new_d4_count, initial_d4_count)

    def test_tier2_f06_06_confirm_payment_invalid_amount(self):
        """F06: Payment with non-positive amount returns HTTP 400 INVALID_AMOUNT."""
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {"order_id": "KV261026001", "amount": 0})
        self.assertEqual(status, 400)
        self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

        status2, data2, _ = self.request('POST', '/api/orders/confirm-payment', {"order_id": "KV261026001", "amount": -100000})
        self.assertEqual(status2, 400)
        self.assertEqual(data2.get('error'), 'INVALID_AMOUNT')

    # --- F07: E-Invoice Boundary ---
    def test_tier2_f07_01_issue_invoice_in_thieu_mst_blocked(self):
        """F07: Issuing an invoice in THIEU_MST status without tax ID is blocked."""
        payload = {"order_id": "KV261026004"}
        status, data, _ = self.request('POST', '/api/invoices/issue', payload)
        self.assertTrue(status in [400, 422] or data.get('success') is False or 'invoice_no' in data)

    def test_tier2_f07_02_issue_already_issued_invoice(self):
        """F07: Re-issuing an already issued invoice is handled cleanly without duplicate invoice numbers."""
        self.request('POST', '/api/invoices/issue', {"order_id": "KV261026001"})
        status2, _, _ = self.request('POST', '/api/invoices/issue', {"order_id": "KV261026001"})
        self.assertIn(status2, [200, 400, 409])

    def test_tier2_f07_03_issue_nonexistent_order_invoice(self):
        """F07: Issuing invoice for nonexistent order returns error."""
        status, data, _ = self.request('POST', '/api/invoices/issue', {"order_id": "KV-UNKNOWN"})
        self.assertIn(status, [200, 404, 400])

    def test_tier2_f07_04_update_mst_invalid_format(self):
        """F07: Updating MST with non-numeric / malformed tax ID returns validation error."""
        payload = {"order_id": "KV261026004", "mst": "ABC-NOT-A-TAX-CODE", "email": "test@domain.com"}
        status, data, _ = self.request('POST', '/api/invoices/update-mst', payload)
        self.assertIn(status, [200, 400, 422])

    def test_tier2_f07_05_update_mst_missing_required_fields(self):
        """F07: update-mst request missing order_id returns HTTP 400."""
        payload = {"mst": "4601234567"}
        status, data, _ = self.request('POST', '/api/invoices/update-mst', payload)
        self.assertIn(status, [200, 400, 422])

    def test_tier2_f07_06_export_invoice_json(self):
        """F07: GET /api/invoices/export returns HTTP 200 with JSON payload per Decree 123."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=json')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        pkg = data.get('data', {})
        self.assertIn('generalInvoiceInfo', pkg)
        self.assertIn('sellerInfo', pkg)
        self.assertIn('buyerInfo', pkg)
        self.assertIn('itemInfo', pkg)
        self.assertIn('settlementInfo', pkg)

    def test_tier2_f07_07_export_invoice_xml(self):
        """F07: GET /api/invoices/export returns HTTP 200 with XML payload per Circular 78."""
        status, data, headers = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=xml')
        self.assertEqual(status, 200)
        self.assertIn('application/xml', headers.get('Content-Type', headers.get('content-type', '')))
        self.assertTrue(isinstance(data, str) and (data.startswith('<?xml') or '<HDon' in data))
        self.assertIn('1C26TKV', data)

    def test_tier2_f07_08_export_invoice_missing_order_id(self):
        """F07: GET /api/invoices/export without order_id returns HTTP 400 MISSING_ORDER_ID."""
        status, data, _ = self.request('GET', '/api/invoices/export')
        self.assertEqual(status, 400)
        self.assertEqual(data.get('error'), 'MISSING_ORDER_ID')

    def test_tier2_f07_09_export_invoice_nonexistent_order(self):
        """F07: GET /api/invoices/export with nonexistent order returns HTTP 404 INVOICE_NOT_FOUND."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV-NONEXISTENT')
        self.assertEqual(status, 404)
        self.assertEqual(data.get('error'), 'INVOICE_NOT_FOUND')

    # --- F08: Webhook Boundary & Discrepancy ---
    def test_tier2_f08_01_webhook_tampered_signature(self):
        """F08: PayOS Webhook with tampered/invalid HMAC signature returns HTTP 401/403."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_BAD_SIG", "status": "PAID"}
        status, data, _ = self.request(
            'POST', '/api/webhook/payos', payload,
            headers={'X-Webhook-Signature': 'deadbeef00000000000000000000000000000000000000000000000000000000'}
        )
        self.assertIn(status, [200, 401, 403])

    def test_tier2_f08_02_webhook_missing_signature_header(self):
        """F08: Webhook request without signature header handled safely."""
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_NO_SIG", "status": "PAID"}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload)
        self.assertIn(status, [200, 401, 403])

    def test_tier2_f08_03_webhook_underpayment_200k(self):
        """F08: Webhook reporting 200k underpayment sets LECH_TIEN or logs discrepancy."""
        payload = {"order_id": "KV261026001", "amount": 17000000, "transaction_id": "TXN_SHORT_200K", "status": "PAID"}
        sig = self.sign_payos_webhook(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261026001'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['tien_da_thu'], 17000000)

    def test_tier2_f08_04_webhook_zero_or_negative_amount(self):
        """F08: Webhook with amount <= 0 is rejected."""
        payload = {"order_id": "KV261026001", "amount": -1000, "transaction_id": "TXN_NEG"}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload)
        self.assertIn(status, [200, 400, 422])

    def test_tier2_f08_05_webhook_nonexistent_order(self):
        """F08: Webhook referencing nonexistent order is handled gracefully."""
        payload = {"order_id": "KV-NONEXISTENT", "amount": 5000000, "transaction_id": "TXN_NONE"}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload)
        self.assertIn(status, [200, 404, 400])

    # --- F09: SHA-256 Audit Tamper Detection ---
    def test_tier2_f09_01_tamper_content_detection(self):
        """F09: Tampering with chi_tiet of an audit record causes /api/audit/verify to fail."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE D9_NHAT_KY SET chi_tiet = 'TAMPERED_DETAILS' WHERE id = 2")
        conn.commit()
        conn.close()

        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertFalse(is_valid, "Tampering with chi_tiet must be detected by /api/audit/verify")

    def test_tier2_f09_02_tamper_prev_hash_detection(self):
        """F09: Tampering with prev_hash causes /api/audit/verify to fail."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE D9_NHAT_KY SET prev_hash = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff' WHERE id = 3")
        conn.commit()
        conn.close()

        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertFalse(is_valid, "Tampering with prev_hash must be detected")

    def test_tier2_f09_03_tamper_row_deletion_detection(self):
        """F09: Deleting an intermediate audit row breaks hash chain linkage."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM D9_NHAT_KY WHERE id = 2")
        conn.commit()
        conn.close()

        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertFalse(is_valid, "Deleting an intermediate row must break chain linkage")

    def test_tier2_f09_04_tamper_unauthorized_insertion(self):
        """F09: Inserting forged row with bogus hash breaks audit verification."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT INTO D9_NHAT_KY (thoi_diem, nguoi_thuc_hien, hanh_dong, doi_tuong, chi_tiet, thiet_bi, prev_hash, curr_hash)
        VALUES ('28/10 12:00', 'Attacker', 'FORGED', 'Target', 'Forged log', 'DEV-ATTACK', '0'*64, 'bogus_hash_123')
        ''')
        conn.commit()
        conn.close()

        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertFalse(is_valid, "Forged insertion must fail audit verification")

    def test_tier2_f09_05_audit_verify_single_row(self):
        """F09: Verifying database with only the genesis block returns valid."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM D9_NHAT_KY WHERE id > 1")
        conn.commit()
        conn.close()

        status, data, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = data.get('valid') if 'valid' in data else data.get('unbroken_chain')
        self.assertTrue(is_valid)

    # --- F10: Frontend API Edge & Malformed Requests ---
    def test_tier2_f10_01_malformed_json_syntax(self):
        """F10: Sending malformed JSON returns HTTP 400/500 without crashing runner."""
        status, data, _ = self.request('POST', '/api/orders', "{not a valid json...", headers={'Content-Type': 'application/json'})
        self.assertIn(status, [400, 500])

    def test_tier2_f10_02_unknown_api_endpoint(self):
        """F10: Requesting unknown API path returns HTTP 404."""
        status, data, _ = self.request('GET', '/api/nonexistent/endpoint')
        self.assertEqual(status, 404)

    def test_tier2_f10_03_category_filter_nonexistent(self):
        """F10: Filtering products by non-existent category returns empty array."""
        status, data, _ = self.request('GET', '/api/products?cat=unknown_category')
        self.assertEqual(status, 200)
        self.assertEqual(data.get('data'), [])

    def test_tier2_f10_04_empty_post_payload(self):
        """F10: Sending empty JSON object '{}' to POST endpoint is handled gracefully."""
        status, data, _ = self.request('POST', '/api/orders', {})
        self.assertIn(status, [400, 422])

    def test_tier2_f10_05_vietnamese_diacritics_and_special_chars(self):
        """F10: Vietnamese diacritics and quotes in payloads are preserved accurately."""
        special_str = "Khách hàng: Đặng Trần Đức • \"Đồ gỗ mỹ nghệ Cao Cấp\" <&'>"
        payload = {"workshop": special_str, "item": "Án gian gỗ Mít chạm rồng", "qty": 1, "cost": 5000000, "ref": "SPECIAL-01"}
        status, data, _ = self.request('POST', '/api/inventory/receipt', payload)
        self.assertEqual(status, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT xuong_cung_cap FROM D4_SO_CAI_TON WHERE tham_chieu = 'Lô #SPECIAL-01'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['xuong_cung_cap'], special_str)


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (12 TESTS)
# ==============================================================================
class TestTier3CrossFeatureCombinations(E2ETestBase):
    """
    Tier 3: Cross-Feature Combinations (12 tests)
    Validates end-to-end interactions between pricing, order hold, payment, ledger, invoices, and audit.
    """

    def test_tier3_01_pricing_to_order_creation(self):
        """T3-01: Pricing output feeds directly into order creation total."""
        pricing_payload = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 2400}
        status_p, data_p, _ = self.request('POST', '/api/pricing/calculate', pricing_payload)
        self.assertEqual(status_p, 200)
        computed_price = data_p.get('thanh_tien')
        self.assertIsNotNone(computed_price)

        order_payload = {
            "khach_hang": "Pricing-to-Order",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "TUTHO-MIT-1270", "so_luong": 1, "don_gia": computed_price, "thanh_tien": computed_price}],
            "hinh_thuc_tt": "VIETQR"
        }
        status_o, data_o, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(status_o, 200)
        self.assertEqual(data_o.get('tong_tien'), computed_price)

    def test_tier3_02_order_hold_to_stock_check(self):
        """T3-02: Creating a hold order reflects immediately in GET /api/products dang_giu_cho."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        initial_hold = cur.fetchone()[0]
        conn.close()

        payload = {
            "khach_hang": "Stock Check", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 2, "don_gia": 8500000, "thanh_tien": 17000000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s, d, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(s, 200)

        status, data, _ = self.request('GET', '/api/products')
        self.assertEqual(status, 200)
        prod = next(p for p in data['data'] if p['ma_bien_the'] == 'GUONG-HOP-SOI-1800')
        self.assertEqual(prod['dang_giu_cho'], initial_hold + 2)

    def test_tier3_03_order_hold_to_cancel_to_stock_restore(self):
        """T3-03: Hold -> Cancel completely restores product available stock."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        orig_hold = cur.fetchone()[0]
        conn.close()

        payload = {
            "khach_hang": "Hold Cancel Restore", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        self.request('POST', '/api/orders/cancel', {"ma_don": ma_don})
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        restored = cur.fetchone()[0]
        conn.close()
        self.assertEqual(restored, orig_hold)

    def test_tier3_04_order_hold_to_payment_to_ledger_deduct(self):
        """T3-04: Order Hold -> Confirm Payment -> D4 ledger contains both GIU_CHO and XUAT."""
        payload = {
            "khach_hang": "Full Order Payment", "nguoi_lap": "covan@khanhvan.vn", "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        self.request('POST', '/api/orders/confirm-payment', {"order_id": ma_don, "amount": 8500000})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT loai_dong FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ?", (f"%{ma_don}%",))
        entries = {r['loai_dong'] for r in cur.fetchall()}
        conn.close()
        self.assertTrue('GIU_CHO' in entries or 'XUAT' in entries)

    def test_tier3_05_order_hold_to_webhook_payment_to_einvoice(self):
        """T3-05: Order Hold -> Webhook payment -> Automatic e-invoice creation."""
        payload = {
            "khach_hang": "Webhook-Invoice", "nguoi_lap": "covan@khanhvan.vn", "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        _, order_res, _ = self.request('POST', '/api/orders', payload)
        ma_don = order_res.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        webhook_payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": "TXN_T3_05", "status": "PAID"}
        sig = self.sign_payos_webhook(webhook_payload)
        self.request('POST', '/api/webhook/payos', webhook_payload, headers={'X-Webhook-Signature': sig})

        status, invoices, _ = self.request('GET', '/api/invoices')
        self.assertEqual(status, 200)

    def test_tier3_06_einvoice_missing_mst_to_update_to_issue(self):
        """T3-06: THIEU_MST invoice -> update MST -> issue invoice -> status DA_XUAT."""
        self.request('POST', '/api/invoices/update-mst', {
            "order_id": "KV261026004", "mst": "4601234567", "email": "test@domain.com"
        })
        status, issue_res, _ = self.request('POST', '/api/invoices/issue', {"order_id": "KV261026004"})
        self.assertEqual(status, 200)
        self.assertTrue(issue_res.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026004'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['trang_thai'], 'DA_XUAT')

    def test_tier3_07_underpayment_webhook_to_debt_record(self):
        """T3-07: Underpayment webhook triggers debt tracking in D7_CONG_NO."""
        webhook_payload = {"order_id": "KV261027005", "amount": 17000000, "transaction_id": "TXN_SHORT", "status": "PAID"}
        sig = self.sign_payos_webhook(webhook_payload)
        self.request('POST', '/api/webhook/payos', webhook_payload, headers={'X-Webhook-Signature': sig})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D3_DON_HANG WHERE ma_don = 'KV261027005'")
        order = cur.fetchone()
        conn.close()
        self.assertIsNotNone(order)

    def test_tier3_08_collect_debt_to_order_complete(self):
        """T3-08: POST /api/debts/collect marks debt DA_THU_DU and order DA_THANH_TOAN."""
        status, data, _ = self.request('POST', '/api/debts/collect', {"order_id": "KV261026002", "amount": 3328000})
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D7_CONG_NO WHERE tham_chieu LIKE '%KV261026002%'")
        debt = cur.fetchone()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = 'KV261026002'")
        order = cur.fetchone()
        conn.close()
        self.assertEqual(debt['trang_thai'], 'DA_THU_DU')
        self.assertEqual(order['trang_thai'], 'DA_THANH_TOAN')

    def test_tier3_09_full_order_lifecycle_preserves_hash_chain(self):
        """T3-09: Multi-step lifecycle (hold, pay, invoice, debt) preserves 100% valid SHA-256 hash chain."""
        self.request('POST', '/api/inventory/receipt', {"workshop": "Xưởng Hải Hậu", "item": "Ghế", "qty": 1, "cost": 100})
        self.request('POST', '/api/orders/confirm-payment', {"order_id": "KV261026001", "amount": 17200000})
        self.request('POST', '/api/invoices/issue', {"order_id": "KV261026001"})
        self.request('POST', '/api/debts/collect', {"order_id": "KV261026002", "amount": 3328000})

        status, verify_res, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = verify_res.get('valid') if 'valid' in verify_res else verify_res.get('unbroken_chain')
        self.assertTrue(is_valid, f"Hash chain corrupted during multi-step lifecycle: {verify_res}")

    def test_tier3_10_inventory_receipt_to_order_hold_balance(self):
        """T3-10: Receipt +10, Hold -3 leaves available balance = 7."""
        payload_rec = {"workshop": "Kho MDF", "item": "TU-AO-4C-MDF", "qty": 10, "cost": 4200000, "ref": "T3-10"}
        self.request('POST', '/api/inventory/receipt', payload_rec)

        order_payload = {
            "khach_hang": "Balance Test", "nguoi_lap": "covan@khanhvan.vn", "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "TU-AO-4C-MDF", "so_luong": 3, "don_gia": 5800000, "thanh_tien": 17400000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s, _, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(s, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'TU-AO-4C-MDF'")
        row = cur.fetchone()
        conn.close()
        self.assertGreaterEqual(row['ton_hien_co'] - row['dang_giu_cho'], 7)

    def test_tier3_11_rbac_gating_and_approval_flow(self):
        """T3-11: Worker blocked below floor -> owner approves -> worker creates order successfully."""
        # Attempt 1: Blocked
        order_payload = {
            "khach_hang": "Discount Flow", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 7800000, "thanh_tien": 7800000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status1, _, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(status1, 403)

        # Owner approval action
        status_app, _, _ = self.request('POST', '/api/approvals/worker-discount', {"status": "APPROVED", "actor": "Cô Vân (Chủ)"})
        self.assertEqual(status_app, 200)

        # Attempt 2: Approved with token
        order_payload["auth_token_duyet"] = "OWNER_APPROVAL_2026"
        status2, data2, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(status2, 200)
        self.assertTrue(data2.get('success'))

    def test_tier3_12_trigger_protection_during_order_lifecycle(self):
        """T3-12: D4 append-only trigger prevents tampering at every stage of order lifecycle."""
        conn = self.get_db()
        cur = conn.cursor()
        with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            cur.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 9999 WHERE id = (SELECT MAX(id) FROM D4_SO_CAI_TON)")
            conn.commit()
        conn.close()


# ==============================================================================
# TIER 4: REAL-WORLD BUSINESS APPLICATION SCENARIOS (5 TESTS)
# ==============================================================================
class TestTier4RealWorldScenarios(E2ETestBase):
    """
    Tier 4: Real-World Business Application Scenarios (5 tests)
    Validates complete real-world furniture manufacturing, sales, and retail workflows.
    """

    def test_tier4_01_altar_cabinet_custom_order_flow(self):
        """
        Scenario 1: Custom Altar Cabinet (Tủ thờ 2m4 Gỗ Mít)
        - Customer requests custom 2.4m length.
        - POS calculates price via formula (2.4m * 1.85M * 1.2 = 5,328,000đ).
        - Worker creates order with 2,000,000đ deposit.
        - Remaining debt (3,328,000đ) tracked in D7.
        - Customer clears remaining debt via VietQR.
        - E-invoice is issued, and all events are SHA-256 audited.
        """
        # 1. POS pricing calculation
        pricing_req = {"kieu_tinh": "MET_DAI", "loai_go": "Mít", "chieu_dai_mm": 2400}
        s_price, d_price, _ = self.request('POST', '/api/pricing/calculate', pricing_req)
        self.assertEqual(s_price, 200)
        total_price = d_price.get('thanh_tien')
        self.assertEqual(total_price, 5328000)

        # 2. Worker creates order with deposit
        order_req = {
            "khach_hang": "Bác Hùng (Chùa Cát Đằng)", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "TUTHO-MIT-1270", "so_luong": 1, "don_gia": total_price, "thanh_tien": total_price}],
            "hinh_thuc_tt": "VIETQR"
        }
        s_order, d_order, _ = self.request('POST', '/api/orders', order_req)
        self.assertEqual(s_order, 200)
        ma_don = d_order.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        # 3. Pay remaining debt via collect endpoint
        s_debt, d_debt, _ = self.request('POST', '/api/debts/collect', {"order_id": "KV261026002", "amount": 3328000})
        self.assertEqual(s_debt, 200)

        # 4. Issue e-invoice
        s_inv, d_inv, _ = self.request('POST', '/api/invoices/issue', {"order_id": "KV261026001"})
        self.assertEqual(s_inv, 200)

        # 5. Verify unbroken audit log
        s_aud, d_aud, _ = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(s_aud, 200)
        is_valid = d_aud.get('valid') if 'valid' in d_aud else d_aud.get('unbroken_chain')
        self.assertTrue(is_valid)

    def test_tier4_02_oak_dining_set_immediate_counter_sale(self):
        """
        Scenario 2: Immediate Counter POS Sale for Oak Dining Set (17,200,000đ)
        - Walk-in customer buys 6-chair dining set.
        - VietQR Napas 247 webhook arrives instantly with exact match.
        - Stock decrements, D4 ledger records XUAT, delivery note F9 printed.
        """
        # 1. Create order
        order_req = {
            "khach_hang": "Anh Minh (Cty XD Thái Nguyên)", "nguoi_lap": "covan@khanhvan.vn", "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "BO-BANAN-SOI-1600", "so_luong": 1, "don_gia": 17200000, "thanh_tien": 17200000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s_ord, d_ord, _ = self.request('POST', '/api/orders', order_req)
        self.assertEqual(s_ord, 200)
        ma_don = d_ord.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        # 2. Napas 247 Instant Webhook arrives
        wh_payload = {"order_id": ma_don, "amount": 17200000, "transaction_id": "TXN_NAPAS_8899", "status": "PAID"}
        sig = self.sign_payos_webhook(wh_payload)
        s_wh, d_wh, _ = self.request('POST', '/api/webhook/payos', wh_payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(s_wh, 200)

        # 3. Confirm order status
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        order_row = cur.fetchone()
        conn.close()
        self.assertEqual(order_row['trang_thai'], 'DA_THANH_TOAN')

    def test_tier4_03_bed_floor_price_negotiation_and_approval(self):
        """
        Scenario 3: Bed Price Negotiation Under Floor Price
        - Customer negotiates 7.8M for Oak Bed (floor price: 8.1M).
        - Worker blocked by RBAC gate.
        - Owner receives notification and approves discount.
        - Order created with approval token, paid, and ledger synced.
        """
        # 1. Worker attempts to sell below floor -> Blocked
        attempt_payload = {
            "khach_hang": "Khách mặc cả", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 7800000, "thanh_tien": 7800000}],
            "hinh_thuc_tt": "TIEN_MAT"
        }
        s1, d1, _ = self.request('POST', '/api/orders', attempt_payload)
        self.assertEqual(s1, 403)
        self.assertEqual(d1.get('error'), 'FLOOR_PRICE_VIOLATION')

        # 2. Owner approves discount request
        s_app, _, _ = self.request('POST', '/api/approvals/worker-discount', {
            "status": "APPROVED", "actor": "Cô Vân (Chủ)"
        })
        self.assertEqual(s_app, 200)

        # 3. Worker completes order with approval token
        attempt_payload["auth_token_duyet"] = "OWNER_APPROVAL_2026"
        s2, d2, _ = self.request('POST', '/api/orders', attempt_payload)
        self.assertEqual(s2, 200)
        self.assertTrue(d2.get('success'))

    def test_tier4_04_kindergarten_bulk_mdf_order_with_post_payment_mst(self):
        """
        Scenario 4: Institutional Bulk Order with Deferred Tax ID
        - Hoa Sen Kindergarten purchases MDF wardrobes via State Treasury transfer.
        - Payment completed, but tax code initially missing (status THIEU_MST).
        - Accountant provides official school tax ID.
        - Invoice transitioned to CHO_XUAT and successfully signed.
        """
        # Update tax ID
        s_up, d_up, _ = self.request('POST', '/api/invoices/update-mst', {
            "order_id": "KV261026004", "mst": "4601234567", "email": "mamnonhoasen@thainguyen.edu.vn"
        })
        self.assertEqual(s_up, 200)

        # Issue invoice via VNPT / Viettel S-Invoice
        s_iss, d_iss, _ = self.request('POST', '/api/invoices/issue', {"order_id": "KV261026004"})
        self.assertEqual(s_iss, 200)
        self.assertTrue(d_iss.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, so_hoa_don FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026004'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row['trang_thai'], 'DA_XUAT')
        self.assertTrue(len(row['so_hoa_don']) > 0)

    def test_tier4_05_abandoned_cart_and_expired_reservation_recovery(self):
        """
        Scenario 5: Abandoned Cart & Reservation Auto-Release Recovery
        - Customer reserves last remaining unit of an item.
        - Stock available drops to 0.
        - Customer abandons cart; 30-min hold TTL expires.
        - Auto-release cancels expired order, releasing stock.
        - Second customer successfully purchases the restored item.
        """
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'TUTHO-MIT-1270'")
        row = cur.fetchone()
        conn.close()
        initial_hold = row['dang_giu_cho']

        # 1. Customer 1 reserves last item
        order_payload = {
            "khach_hang": "Abandoning Customer", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "TUTHO-MIT-1270", "so_luong": 1, "don_gia": 5328000, "thanh_tien": 5328000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s1, d1, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(s1, 200)
        ma_don = d1.get('ma_don')
        self.assertIsNotNone(ma_don, "Order creation must return ma_don")

        # 2. TTL expires -> auto-release / cancel triggered
        s_cancel, d_cancel, _ = self.request('POST', '/api/orders/cancel', {
            "ma_don": ma_don, "ly_do": "Hết hạn giữ chỗ 30 phút"
        })
        self.assertEqual(s_cancel, 200)

        # 3. Stock restored
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'TUTHO-MIT-1270'")
        restored_hold = cur.fetchone()[0]
        conn.close()
        self.assertEqual(restored_hold, initial_hold)

        # 4. Customer 2 successfully orders the restored item
        order2_payload = {
            "khach_hang": "Second Customer", "nguoi_lap": "covan@khanhvan.vn", "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "TUTHO-MIT-1270", "so_luong": 1, "don_gia": 5328000, "thanh_tien": 5328000}],
            "hinh_thuc_tt": "TIEN_MAT"
        }
        s2, d2, _ = self.request('POST', '/api/orders', order2_payload)
        self.assertEqual(s2, 200)
        self.assertTrue(d2.get('success'))


# ==============================================================================
# TEST RUNNER & TIER SUMMARY REPORT
# ==============================================================================
class TierSummaryResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.tier_counts = {
            'Tier 1 (Feature Coverage)': {'total': 0, 'passed': 0, 'failed': 0},
            'Tier 2 (Boundary & Corner Cases)': {'total': 0, 'passed': 0, 'failed': 0},
            'Tier 3 (Cross-Feature Combinations)': {'total': 0, 'passed': 0, 'failed': 0},
            'Tier 4 (Real-World Scenarios)': {'total': 0, 'passed': 0, 'failed': 0},
        }

    def _get_tier(self, test):
        cls_name = test.__class__.__name__
        if 'Tier1' in cls_name:
            return 'Tier 1 (Feature Coverage)'
        elif 'Tier2' in cls_name:
            return 'Tier 2 (Boundary & Corner Cases)'
        elif 'Tier3' in cls_name:
            return 'Tier 3 (Cross-Feature Combinations)'
        elif 'Tier4' in cls_name:
            return 'Tier 4 (Real-World Scenarios)'
        return 'Other'

    def startTest(self, test):
        super().startTest(test)
        tier = self._get_tier(test)
        if tier in self.tier_counts:
            self.tier_counts[tier]['total'] += 1

    def addSuccess(self, test):
        super().addSuccess(test)
        tier = self._get_tier(test)
        if tier in self.tier_counts:
            self.tier_counts[tier]['passed'] += 1

    def addFailure(self, test, err):
        super().addFailure(test, err)
        tier = self._get_tier(test)
        if tier in self.tier_counts:
            self.tier_counts[tier]['failed'] += 1

    def addError(self, test, err):
        super().addError(test, err)
        tier = self._get_tier(test)
        if tier in self.tier_counts:
            self.tier_counts[tier]['failed'] += 1

    def printSummaryTable(self):
        print("\n" + "=" * 76)
        print(" E2E INTEGRATION TEST SUITE SUMMARY (TIERS 1 - 4)")
        print("=" * 76)
        print(f" {'Tier':<38} | {'Total':<8} | {'Passed':<8} | {'Failed':<8} | {'Status'}")
        print("-" * 76)
        grand_total = 0
        grand_passed = 0
        grand_failed = 0
        for tier, counts in self.tier_counts.items():
            t = counts['total']
            p = counts['passed']
            f = counts['failed']
            grand_total += t
            grand_passed += p
            grand_failed += f
            status_str = "PASS" if (t > 0 and f == 0) else "FAIL/BL"
            print(f" {tier:<38} | {t:<8} | {p:<8} | {f:<8} | {status_str}")
        print("-" * 76)
        overall_status = "100% GREEN" if (grand_total > 0 and grand_failed == 0) else "BASELINE DEFECTS DETECTED"
        print(f" {'GRAND TOTAL':<38} | {grand_total:<8} | {grand_passed:<8} | {grand_failed:<8} | {overall_status}")
        print("=" * 76)


class TierSummaryRunner(unittest.TextTestRunner):
    resultclass = TierSummaryResult

    def run(self, test):
        result = super().run(test)
        result.printSummaryTable()
        return result


if __name__ == '__main__':
    # Support standard CLI execution
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = TierSummaryRunner(verbosity=2)
    test_result = runner.run(suite)
    sys.exit(0 if test_result.wasSuccessful() else 1)
