#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_m3_r2_challenge_stress.py
Milestone 3 Empirical Concurrency & Stress Challenge Suite
Agent: m3_r2_challenger_1

Focus:
1. Sequential Webhook Replay Deduplication (Idempotency)
2. Concurrent Webhook Thundering Herd Replay Attack (Race condition)
3. Sequential Duplicate Payment Confirmation (Double deduction check)
4. Concurrent Payment Confirmation Burst (Multi-thread idempotency check)
5. Payment Confirmation on Cancelled / Expired Orders (State transition guard)
6. High-Concurrency E-Invoice Export Burst (Decree 123 XML & JSON)
"""

import sys
import os
import json
import sqlite3
import threading
import tempfile
import shutil
import time
import hmac
import hashlib
import urllib.request
import urllib.error
import socketserver
import unittest

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 100

class M3R2ChallengeStressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.temp_dir = tempfile.mkdtemp(prefix="m3_r2_stress_")
        cls.db_path = os.path.join(cls.temp_dir, "test_khanhvan.db")
        server.DB_FILE = cls.db_path

        server.init_db()

        cls.httpd = ThreadedTCPServer(("127.0.0.1", 0), server.KhanhVanServer)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait for server ready
        ready = False
        for _ in range(30):
            try:
                req = urllib.request.Request(f"{cls.base_url}/api/db/stats")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.05)
        if not ready:
            raise RuntimeError("Server failed to start")

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def get_db(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA recursive_triggers = ON")
        return conn

    def request(self, method, path, data=None, headers=None):
        url = f"{self.base_url}{path}"
        req_headers = {'Accept': 'application/json'}
        if headers:
            req_headers.update(headers)
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            req_headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read()
                content_type = resp.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return resp.status, json.loads(raw.decode('utf-8')), raw
                return resp.status, None, raw
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                parsed = json.loads(raw.decode('utf-8'))
            except Exception:
                parsed = None
            return e.code, parsed, raw
        except Exception as ex:
            return 500, {'error': str(ex)}, b''

    def sign_payos(self, payload):
        canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        return hmac.new(server.PAYOS_WEBHOOK_SECRET.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    def seed_test_product(self, prod_code, initial_stock=50):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, ?, 'giuong', 'Xưởng Thạch Thất', 5000000, 7000000, 8500000, ?, 0)
        ''', (prod_code, f"Sản phẩm Test {prod_code}", initial_stock))
        conn.commit()
        conn.close()

    def create_test_order(self, customer_name, prod_code, qty=1, price=8500000):
        payload = {
            "khach_hang": customer_name,
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [
                {
                    "ma_bien_the": prod_code,
                    "ten_san_pham": f"Sản phẩm Test {prod_code}",
                    "so_luong": qty,
                    "don_gia": price,
                    "thanh_tien": price * qty
                }
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, data, _ = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200, f"Failed to create order: {data}")
        return data['ma_don']

    # =========================================================================
    # 1. Sequential Webhook Replay
    # =========================================================================
    def test_01_webhook_sequential_replay(self):
        """Sequential replay of webhook with identical transaction_id must return duplicate=True"""
        prod_code = "STRESS-WH-SEQ"
        self.seed_test_product(prod_code, 20)
        ma_don = self.create_test_order("Replay Sequential", prod_code, 1, 8500000)
        txn_id = f"TXN_REPLAY_SEQ_{int(time.time()*1000)}"

        payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": txn_id}
        sig = self.sign_payos(payload)

        # First webhook delivery
        s1, d1, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(s1, 200)
        self.assertFalse(d1.get('duplicate', False))
        self.assertEqual(d1.get('trang_thai'), 'DA_THANH_TOAN')

        # Replay webhook delivery
        s2, d2, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(s2, 200)
        self.assertTrue(d2.get('duplicate', False), "Replayed webhook must return duplicate=True")

        # Verify exactly 1 XUAT in D4
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(xuat_count, 1, f"Expected exactly 1 XUAT in D4, got {xuat_count}")

    # =========================================================================
    # 2. Concurrent Webhook Replay (Thundering Herd)
    # =========================================================================
    def test_02_webhook_concurrent_thundering_herd_replay(self):
        """
        25 concurrent threads send the EXACT SAME webhook payload and transaction_id.
        Oracle:
        - 0 internal 500 crashes
        - Exactly 1 thread does the initial settlement (duplicate != True)
        - Exactly 24 threads receive duplicate == True
        - Exactly 1 XUAT is inserted into D4_SO_CAI_TON (NO double-decrement!)
        """
        prod_code = "STRESS-WH-CONC"
        self.seed_test_product(prod_code, 30)
        ma_don = self.create_test_order("Thundering Herd Webhook", prod_code, 1, 8500000)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_start = cur.fetchone()['ton_hien_co']
        conn.close()

        txn_id = f"TXN_HERD_{int(time.time()*1000)}"
        payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": txn_id}
        sig = self.sign_payos(payload)

        num_threads = 25
        results = []
        barrier = threading.Barrier(num_threads)

        def worker():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
            results.append((s, d))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        statuses = [r[0] for r in results]
        self.assertEqual(len(statuses), num_threads)
        self.assertTrue(all(s == 200 for s in statuses), f"Got non-200 statuses: {statuses}")

        initial_hits = [r[1] for r in results if not r[1].get('duplicate')]
        duplicate_hits = [r[1] for r in results if r[1].get('duplicate')]

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_count = cur.fetchone()[0]
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_end = cur.fetchone()['ton_hien_co']
        conn.close()

        self.assertEqual(len(initial_hits), 1, f"VULNERABILITY: Multiple concurrent webhooks passed idempotency guard! Initial hits: {len(initial_hits)}")
        self.assertEqual(len(duplicate_hits), 24, f"Expected 24 duplicate responses, got {len(duplicate_hits)}")
        self.assertEqual(xuat_count, 1, f"VULNERABILITY: Duplicate XUAT records inserted into D4_SO_CAI_TON! Count={xuat_count}")
        self.assertEqual(ton_end, ton_start - 1, f"Stock should decrement by exactly 1! Expected {ton_start - 1}, got {ton_end}")

    # =========================================================================
    # 3. Sequential Duplicate Payment Confirmation
    # =========================================================================
    def test_03_confirm_payment_sequential_duplicate(self):
        """
        Calling /api/orders/confirm-payment twice sequentially on the same order.
        Second call must NOT decrement stock again and must NOT insert duplicate XUAT.
        """
        prod_code = "STRESS-PAY-SEQ"
        self.seed_test_product(prod_code, 20)
        ma_don = self.create_test_order("Sequential Pay Test", prod_code, 1, 8500000)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_start = cur.fetchone()['ton_hien_co']
        conn.close()

        # Call 1: Initial Payment
        s1, d1, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
        self.assertEqual(s1, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_after_pay1 = cur.fetchone()['ton_hien_co']
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_after_pay1 = cur.fetchone()[0]
        conn.close()

        self.assertEqual(ton_after_pay1, ton_start - 1)
        self.assertEqual(xuat_after_pay1, 1)

        # Call 2: Duplicate Payment Confirmation on ALREADY PAID order
        s2, d2, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_after_pay2 = cur.fetchone()['ton_hien_co']
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_after_pay2 = cur.fetchone()[0]
        conn.close()

        self.assertEqual(xuat_after_pay2, 1, f"VULNERABILITY: Duplicate confirm-payment appended second XUAT row in D4! Count={xuat_after_pay2}")
        self.assertEqual(ton_after_pay2, ton_start - 1, f"VULNERABILITY: Duplicate confirm-payment decremented stock again! Start={ton_start}, Pay1={ton_after_pay1}, Pay2={ton_after_pay2}")

    # =========================================================================
    # 4. Concurrent Payment Confirmation Burst
    # =========================================================================
    def test_04_confirm_payment_concurrent_burst(self):
        """
        20 concurrent threads calling /api/orders/confirm-payment for the SAME order.
        Oracle:
        - Exactly 1 XUAT recorded in D4_SO_CAI_TON
        - Exactly 1 stock decrement in D1_SAN_PHAM
        """
        prod_code = "STRESS-PAY-CONC"
        self.seed_test_product(prod_code, 25)
        ma_don = self.create_test_order("Concurrent Payment Order", prod_code, 1, 8500000)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_start = cur.fetchone()['ton_hien_co']
        conn.close()

        num_threads = 20
        results = []
        barrier = threading.Barrier(num_threads)

        def worker():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
            results.append((s, d))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_count = cur.fetchone()[0]
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        ton_end = cur.fetchone()['ton_hien_co']
        conn.close()

        self.assertEqual(xuat_count, 1, f"VULNERABILITY: Concurrent confirm-payment appended multiple XUAT rows in D4! Count={xuat_count}")
        self.assertEqual(ton_end, ton_start - 1, f"VULNERABILITY: Concurrent confirm-payment decremented stock multiple times! Start={ton_start}, End={ton_end}")

    # =========================================================================
    # 5. Payment Confirmation on Cancelled / Expired Orders
    # =========================================================================
    def test_05_confirm_payment_on_cancelled_order(self):
        """
        Attempting to confirm payment on an already CANCELLED order (DA_HUY).
        When cancelled, hold was released. Payment must be rejected (400) or at least not decrement stock.
        """
        prod_code = "STRESS-PAY-CANCEL"
        self.seed_test_product(prod_code, 20)
        ma_don = self.create_test_order("Cancel Before Pay Order", prod_code, 1, 8500000)

        # Cancel the order
        s_can, d_can, _ = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don, 'ly_do': 'Khách đổi ý'})
        self.assertEqual(s_can, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        stock_after_cancel = dict(cur.fetchone())
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        status_after_cancel = cur.fetchone()['trang_thai']
        conn.close()
        self.assertEqual(status_after_cancel, 'DA_HUY')

        # Attempt to confirm payment on cancelled order
        s_pay, d_pay, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        stock_after_pay = dict(cur.fetchone())
        conn.close()

        # Oracle: A cancelled order must NOT be successfully confirmed and must NOT decrement inventory
        self.assertNotEqual(s_pay, 200, f"VULNERABILITY: Server accepted payment on CANCELLED order ({status_after_cancel})! HTTP status={s_pay}")
        self.assertEqual(stock_after_pay['ton_hien_co'], stock_after_cancel['ton_hien_co'], "Stock was deducted for a cancelled order!")

    # =========================================================================
    # 6. High-Concurrency Invoice Export (XML & JSON)
    # =========================================================================
    def test_06_concurrent_invoice_export_burst(self):
        """
        30 concurrent threads export invoice (15 JSON, 15 XML).
        Must all return 200 with valid content, zero 500 errors, zero lock deadlocks.
        """
        prod_code = "STRESS-INV-EXPORT"
        self.seed_test_product(prod_code, 20)
        ma_don = self.create_test_order("Export Concurrency Order", prod_code, 1, 8500000)
        self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})

        num_threads = 30
        results = []
        barrier = threading.Barrier(num_threads)

        def worker(is_xml):
            barrier.wait()
            path = f"/api/invoices/export?order_id={ma_don}&format={'xml' if is_xml else 'json'}"
            s, d, raw = self.request('GET', path)
            results.append((s, is_xml, len(raw)))

        threads = [threading.Thread(target=worker, args=(i % 2 == 0,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), num_threads)
        for s, is_xml, byte_len in results:
            self.assertEqual(s, 200, f"Expected 200 for invoice export, got {s}")
            self.assertGreater(byte_len, 100)

if __name__ == '__main__':
    unittest.main()
