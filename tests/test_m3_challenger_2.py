#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milestone 3 Empirical Challenge Suite - Challenger 2
Focus: E-Invoice Lifecycle & Discrepancy Reconciliation Engine

Empirical Adversarial Tests:
1. E-Invoice Lifecycle & Invariants:
   - Issue invoice in THIEU_MST must return 400 INVOICE_MISSING_MST.
   - Re-issue already issued invoice must return 409 INVOICE_ALREADY_ISSUED.
   - Issue nonexistent order must return 404 INVOICE_NOT_FOUND without D9 audit spam.
   - Update MST with invalid strings must return 400 INVALID_MST.
   - Update MST with valid 10/13 digits must transition status to CHO_XUAT.
   - Sequential 7-digit so_hoa_don incrementing (0000001, 0000002, ...).
   - High-concurrency race condition probe on invoice issuing (detection of duplicate so_hoa_don).
2. Discrepancy Reconciliation Engine:
   - Seed order KV261027005 (deficit 200k in LECH_TIEN):
     - Initial status check: LECH_TIEN, con_phai_thu = 200,000.
     - Top-up webhook with amount: 200,000 -> transitions order to DA_THANH_TOAN, con_phai_thu = 0.
     - Draft invoice created in D6_HOA_DON_DT.
     - Stock decremented in D1_SAN_PHAM and XUAT row appended to D4_SO_CAI_TON.
     - D7_CONG_NO customer debt status verified as DA_THU_DU (empirical boundary audit).
   - Two-stage discrepancy lifecycle (Order -> Underpayment creates debt -> Top-up settles debt).
   - Webhook idempotency deduplication on duplicate top-up transactions.
   - Webhook HMAC signature verification and tampering rejection.
"""

import unittest
import urllib.request
import urllib.error
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

class M3Challenger2Tests(unittest.TestCase):
    httpd = None
    server_thread = None
    server_port = None
    server_url = None
    test_dir = None
    test_db_path = None

    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.test_dir = tempfile.mkdtemp(prefix='m3_challenger2_')
        cls.test_db_path = os.path.join(cls.test_dir, 'm3_challenge.db')
        server.DB_FILE = cls.test_db_path
        cls.init_fresh_db()

        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.server_port = cls.httpd.server_address[1]
        cls.server_url = f"http://127.0.0.1:{cls.server_port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait for server readiness
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
            raise RuntimeError(f"Challenger test server failed to start on {cls.server_url}")

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if cls.test_dir and os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def init_fresh_db(cls):
        conn = sqlite3.connect(cls.test_db_path)
        cur = conn.cursor()
        tables = [
            'D1_SAN_PHAM', 'D2_BANG_GIA', 'D3_DON_HANG', 'D4_SO_CAI_TON',
            'D5_NHA_CUNG_CAP', 'D6_HOA_DON_DT', 'D7_CONG_NO', 'D8_TAI_KHOAN',
            'D8_THIET_BI', 'D9_NHAT_KY'
        ]
        for tbl in tables:
            cur.execute(f"DROP TABLE IF EXISTS {tbl}")
        cur.execute("DROP TRIGGER IF EXISTS trg_prevent_d4_update")
        cur.execute("DROP TRIGGER IF EXISTS trg_prevent_d4_delete")
        conn.commit()
        conn.close()

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            server.init_db()
        finally:
            sys.stdout = old_stdout

    def setUp(self):
        self.init_fresh_db()

    def get_db(self):
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def request(self, method, path, data=None, headers=None):
        url = f"{self.server_url}{path}"
        req_headers = {'Accept': 'application/json'}
        if headers:
            req_headers.update(headers)

        body = None
        if data is not None:
            req_headers['Content-Type'] = 'application/json'
            body = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                resp_bytes = resp.read()
                try:
                    parsed = json.loads(resp_bytes.decode('utf-8'))
                except Exception:
                    parsed = resp_bytes.decode('utf-8')
                return resp.status, parsed, dict(resp.headers)
        except urllib.error.HTTPError as e:
            err_bytes = e.read()
            try:
                parsed = json.loads(err_bytes.decode('utf-8'))
            except Exception:
                parsed = err_bytes.decode('utf-8')
            return e.code, parsed, dict(e.headers)

    def sign_payos_webhook(self, payload_dict):
        secret = os.environ.get('PAYOS_WEBHOOK_SECRET', 'khanhvan_payos_secret_2026')
        canonical = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
        return hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    # =========================================================================
    # PART 1: E-INVOICE LIFECYCLE TESTS
    # =========================================================================

    def test_01_issue_invoice_in_thieu_mst_returns_400(self):
        """1.1: Issuing an invoice for an order with status THIEU_MST must return HTTP 400 INVOICE_MISSING_MST."""
        # KV261026004 is seeded with status THIEU_MST in D6_HOA_DON_DT
        status, data, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026004'})
        self.assertEqual(status, 400, f"Expected 400 for THIEU_MST invoice issue, got {status}: {data}")
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVOICE_MISSING_MST')

    def test_02_reissue_already_issued_invoice_returns_409(self):
        """1.2: Re-issuing an already issued invoice (DA_XUAT) must return HTTP 409 INVOICE_ALREADY_ISSUED."""
        # First issue KV261026001 (seeded in CHO_XUAT with valid MST)
        status1, data1, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026001'})
        self.assertEqual(status1, 200, f"Initial issue failed: {data1}")
        self.assertTrue(data1.get('success'))
        self.assertEqual(data1.get('trang_thai'), 'DA_XUAT')
        issued_no = data1.get('invoice_no')
        self.assertTrue(bool(issued_no))

        # Attempt to re-issue the same invoice
        status2, data2, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026001'})
        self.assertEqual(status2, 409, f"Expected 409 for duplicate issue, got {status2}: {data2}")
        self.assertFalse(data2.get('success'))
        self.assertEqual(data2.get('error'), 'INVOICE_ALREADY_ISSUED')
        self.assertEqual(data2.get('invoice_no'), issued_no)

    def test_03_issue_nonexistent_order_returns_404_without_audit_spam(self):
        """1.3: Issuing for nonexistent order must return HTTP 404 INVOICE_NOT_FOUND without polluting D9_NHAT_KY."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MAX(id), curr_hash FROM D9_NHAT_KY GROUP BY id ORDER BY id DESC LIMIT 1")
        audit_before = cur.fetchone()
        count_before = audit_before[0] if audit_before else 0
        hash_before = audit_before[2] if audit_before else ''
        conn.close()

        status, data, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV_NONEXISTENT_ORDER_99999'})
        self.assertEqual(status, 404, f"Expected 404 for nonexistent order invoice issue, got {status}: {data}")
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVOICE_NOT_FOUND')

        # Check D9_NHAT_KY audit log count and hash invariant
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MAX(id), curr_hash FROM D9_NHAT_KY GROUP BY id ORDER BY id DESC LIMIT 1")
        audit_after = cur.fetchone()
        count_after = audit_after[0] if audit_after else 0
        hash_after = audit_after[2] if audit_after else ''
        conn.close()

        self.assertEqual(count_after, count_before, "D9 audit log was modified on 404 error (audit spam defect)!")
        self.assertEqual(hash_after, hash_before, "D9 audit hash was altered on 404 error!")

    def test_04_update_mst_invalid_strings_returns_400(self):
        """1.4: Updating MST with invalid strings (letters, symbols, bad length) must return HTTP 400 INVALID_MST."""
        invalid_mst_samples = [
            "ABCDEFGHIJ",          # 10 letters
            "460123-ABC",          # letters in suffix
            "460123@#$%^",         # special symbols
            "12345678",            # 8 digits (too short)
            "123456789",           # 9 digits
            "12345678901",         # 11 digits
            "123456789012",        # 12 digits
            "12345678901234",      # 14 digits
            "123456789012345",     # 15 digits
            "4601234567-01",       # invalid suffix (2 digits instead of 3)
            "4601234567-0001",     # invalid suffix (4 digits instead of 3)
            "4601234567' OR 1=1--" # SQL injection string
        ]

        for sample in invalid_mst_samples:
            with self.subTest(mst=sample):
                status, data, _ = self.request('POST', '/api/invoices/update-mst', {
                    'order_id': 'KV261026004',
                    'mst': sample,
                    'email': 'test@invalid.vn'
                })
                self.assertEqual(status, 400, f"Expected 400 for invalid MST '{sample}', got {status}: {data}")
                self.assertFalse(data.get('success'))
                self.assertEqual(data.get('error'), 'INVALID_MST')

        # Test empty MST
        status_empty, data_empty, _ = self.request('POST', '/api/invoices/update-mst', {
            'order_id': 'KV261026004',
            'mst': '',
            'email': 'test@invalid.vn'
        })
        self.assertEqual(status_empty, 400)
        self.assertEqual(data_empty.get('error'), 'MISSING_MST')

    def test_05_update_mst_valid_10_and_13_digits_transitions_to_cho_xuat(self):
        """1.5: Updating MST with valid 10 and 13 digit tax codes must transition status to CHO_XUAT."""
        valid_samples = [
            "0101234567",       # 10 digits
            "0101234567-001",   # 10 digits + hyphen + 3 digits
            "0101234567001"     # 13 contiguous digits
        ]

        for mst in valid_samples:
            # Reset KV261026004 to THIEU_MST before each subtest
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("UPDATE D6_HOA_DON_DT SET trang_thai = 'THIEU_MST', ma_so_thue = '' WHERE ma_don = 'KV261026004'")
            conn.commit()
            conn.close()

            status, data, _ = self.request('POST', '/api/invoices/update-mst', {
                'order_id': 'KV261026004',
                'mst': mst,
                'email': 'ketoan@mamnonhoasen.edu.vn'
            })
            self.assertEqual(status, 200, f"Expected 200 for valid MST '{mst}', got {status}: {data}")
            self.assertTrue(data.get('success'))
            self.assertEqual(data.get('trang_thai'), 'CHO_XUAT')
            self.assertEqual(data.get('mst'), mst)

            # Verify database persistence in D6_HOA_DON_DT
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("SELECT trang_thai, ma_so_thue, email FROM D6_HOA_DON_DT WHERE ma_don = 'KV261026004'")
            row = cur.fetchone()
            conn.close()
            self.assertEqual(row['trang_thai'], 'CHO_XUAT')
            self.assertEqual(row['ma_so_thue'], mst)
            self.assertEqual(row['email'], 'ketoan@mamnonhoasen.edu.vn')

    def test_06_update_mst_on_already_issued_invoice_returns_409(self):
        """1.6: Attempting to update MST on an already issued invoice (DA_XUAT) must return HTTP 409."""
        # Issue KV261026001
        self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026001'})

        # Attempt to modify MST
        status, data, _ = self.request('POST', '/api/invoices/update-mst', {
            'order_id': 'KV261026001',
            'mst': '0109999999',
            'email': 'newemail@khanhvan.vn'
        })
        self.assertEqual(status, 409, f"Expected 409 for updating issued invoice, got {status}: {data}")
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVOICE_ALREADY_ISSUED')

    def test_07_sequential_7digit_so_hoa_don_incrementing(self):
        """1.7: Sequential issue of multiple valid invoices must produce strictly sequential 7-digit numbers."""
        # 1. Issue KV261026001 (first invoice)
        status1, data1, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026001'})
        self.assertEqual(status1, 200)
        inv1 = data1.get('invoice_no')
        self.assertEqual(inv1, '0000001', f"First invoice number must be 0000001, got '{inv1}'")

        # 2. Update MST for KV261026004 and issue it (second invoice)
        self.request('POST', '/api/invoices/update-mst', {
            'order_id': 'KV261026004',
            'mst': '0101234567',
            'email': 'hoasen@edu.vn'
        })
        status2, data2, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026004'})
        self.assertEqual(status2, 200)
        inv2 = data2.get('invoice_no')
        self.assertEqual(inv2, '0000002', f"Second invoice number must be 0000002, got '{inv2}'")

        # 3. Create a third invoice in D6 and issue it (third invoice)
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu) VALUES ('KV_TEST_SEQ_3', '28/10/2026', 'Khách VIP 3', 'Cô Vân', 5000000, 'CK', 'DA_THANH_TOAN', 5000000, 0, '')")
        cur.execute("INSERT INTO D6_HOA_DON_DT (ma_hoa_don, ma_don, khach_hang, ma_so_thue, email, tong_tien, trang_thai, so_hoa_don, ngay_ky, goi_du_lieu) VALUES ('HD-KV_TEST_SEQ_3', 'KV_TEST_SEQ_3', 'Khách VIP 3', '0109876543', 'vip3@test.vn', 5000000, 'CHO_XUAT', '', '', '')")
        conn.commit()
        conn.close()

        status3, data3, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV_TEST_SEQ_3'})
        self.assertEqual(status3, 200)
        inv3 = data3.get('invoice_no')
        self.assertEqual(inv3, '0000003', f"Third invoice number must be 0000003, got '{inv3}'")

    def test_08_adversarial_concurrency_race_condition_on_invoice_issue(self):
        """1.8 (Adversarial): Multi-threaded concurrent invoice issuing stress test."""
        num_threads = 5
        conn = self.get_db()
        cur = conn.cursor()
        for i in range(1, num_threads + 1):
            oid = f"KV_CONCUR_ORDER_{i}"
            cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu) VALUES (?, '28/10/2026', 'Khách đồng thời', 'Cô Vân', 2000000, 'CK', 'DA_THANH_TOAN', 2000000, 0, '')", (oid,))
            cur.execute("INSERT INTO D6_HOA_DON_DT (ma_hoa_don, ma_don, khach_hang, ma_so_thue, email, tong_tien, trang_thai, so_hoa_don, ngay_ky, goi_du_lieu) VALUES (?, ?, 'Khách đồng thời', '0101234567', 'concur@test.vn', 2000000, 'CHO_XUAT', '', '', '')", (f"HD-{oid}", oid))
        conn.commit()
        conn.close()

        barrier = threading.Barrier(num_threads)
        results = []

        def worker(order_id):
            barrier.wait()
            status, data, _ = self.request('POST', '/api/invoices/issue', {'order_id': order_id})
            results.append((order_id, status, data.get('invoice_no')))

        threads = [threading.Thread(target=worker, args=(f"KV_CONCUR_ORDER_{i}",)) for i in range(1, num_threads + 1)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # Check all succeeded
        for oid, st, inv_no in results:
            self.assertEqual(st, 200, f"Concurrent issue failed for {oid}: status {st}")
            self.assertIsNotNone(inv_no, f"Missing invoice_no for {oid}")

        issued_numbers = [r[2] for r in results]
        unique_numbers = set(issued_numbers)
        # Empirical finding check: if race condition exists, unique count < total count
        has_race_condition = len(unique_numbers) < len(issued_numbers)
        if has_race_condition:
            print(f"\n[CRITIC FINDING] Race condition detected in invoice issuing: {issued_numbers}")
        # Note: We record this adversarial finding in report

    # =========================================================================
    # PART 2: DISCREPANCY RECONCILIATION TESTS
    # =========================================================================

    def test_09_discrepancy_reconciliation_topup_kv261027005(self):
        """2.1: Discrepancy reconciliation for seed order KV261027005 (deficit 200k)."""
        # Step 1: Verify initial state in D3_DON_HANG
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tong_tien, tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261027005'")
        initial_order = cur.fetchone()
        conn.close()
        self.assertIsNotNone(initial_order, "Order KV261027005 not found in D3_DON_HANG!")
        self.assertEqual(initial_order['trang_thai'], 'LECH_TIEN', f"Initial status must be LECH_TIEN, got {initial_order['trang_thai']}")
        self.assertEqual(initial_order['con_phai_thu'], 200000, f"Initial con_phai_thu must be 200,000, got {initial_order['con_phai_thu']}")

        # Initial stock of BO-BANAN-SOI-1600
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'BO-BANAN-SOI-1600'")
        stock_before = cur.fetchone()['ton_hien_co']
        conn.close()

        # Step 2: Send top-up webhook with amount: 200,000
        webhook_payload = {
            "order_id": "KV261027005",
            "amount": 200000,
            "transaction_id": "TXN_RECON_TOPUP_200K",
            "status": "PAID"
        }
        sig = self.sign_payos_webhook(webhook_payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', webhook_payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 200, f"Top-up webhook failed: {data}")
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('trang_thai'), 'DA_THANH_TOAN')
        self.assertEqual(data.get('con_phai_thu'), 0)
        self.assertEqual(data.get('discrepancy'), 0)

        # Step 3: Verify order transitions in D3_DON_HANG
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261027005'")
        order_after = cur.fetchone()
        self.assertEqual(order_after['trang_thai'], 'DA_THANH_TOAN')
        self.assertEqual(order_after['con_phai_thu'], 0)
        self.assertEqual(order_after['tien_da_thu'], 17200000)

        # Step 4: Verify draft invoice is auto-created in D6_HOA_DON_DT
        cur.execute("SELECT ma_hoa_don, trang_thai, tong_tien FROM D6_HOA_DON_DT WHERE ma_don = 'KV261027005'")
        invoice_row = cur.fetchone()
        self.assertIsNotNone(invoice_row, "Draft invoice was NOT created in D6_HOA_DON_DT for settled order KV261027005!")
        self.assertEqual(invoice_row['ma_hoa_don'], 'HD-KV261027005')
        self.assertEqual(invoice_row['tong_tien'], 17200000)
        self.assertIn(invoice_row['trang_thai'], ['THIEU_MST', 'CHO_XUAT'])

        # Step 5: Verify stock is decremented in D1_SAN_PHAM and XUAT row appended to D4_SO_CAI_TON
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'BO-BANAN-SOI-1600'")
        stock_after = cur.fetchone()['ton_hien_co']
        self.assertEqual(stock_after, stock_before - 1, f"Physical stock was not decremented! Before: {stock_before}, After: {stock_after}")

        cur.execute("SELECT loai_dong, bien_dong, ma_bien_the FROM D4_SO_CAI_TON WHERE tham_chieu LIKE '%KV261027005%' AND loai_dong = 'XUAT'")
        xuat_row = cur.fetchone()
        self.assertIsNotNone(xuat_row, "XUAT row was NOT appended to D4_SO_CAI_TON for KV261027005!")
        self.assertEqual(xuat_row['bien_dong'], -1)
        self.assertEqual(xuat_row['ma_bien_the'], 'BO-BANAN-SOI-1600')

        # Step 6: Verify D7_CONG_NO is updated to DA_THU_DU
        cur.execute("SELECT id, loai_no, tham_chieu, da_tra, con_lai, trang_thai FROM D7_CONG_NO WHERE tham_chieu LIKE '%KV261027005%'")
        debt_row = cur.fetchone()
        conn.close()

        # EMPIRICAL FINDING ASSERTION:
        # If D7_CONG_NO had no record for KV261027005, debt_row will be None!
        self.assertIsNotNone(
            debt_row,
            "CRITICAL DEFECT: D7_CONG_NO has NO record for order KV261027005! "
            "Neither init_db() seeded the debt, nor did webhook full settlement upsert the DA_THU_DU record!"
        )
        self.assertEqual(debt_row['trang_thai'], 'DA_THU_DU')
        self.assertEqual(debt_row['con_lai'], 0)

    def test_10_two_stage_discrepancy_lifecycle_underpay_then_topup(self):
        """2.2: Full end-to-end discrepancy lifecycle (Order -> Underpay -> D7 DANG_NO -> Top-up -> D7 DA_THU_DU)."""
        # Step A: Create order in D3_DON_HANG
        order_id = "KV261028_TEST_RECON"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES (?, '28/10/2026 14:00', 'Anh Thắng (Khách thử nghiệm)', 'Cô Vân', 17200000, 'VIETQR', 'GIU_CHO', 0, 17200000, '[{"ma_bien_the":"BO-BANAN-SOI-1600","so_luong":1}]')
        """, (order_id,))
        # Also simulate hold in D4
        cur.execute("""
        INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
        VALUES ('28/10 14:00', 'GIU_CHO', 'BO-BANAN-SOI-1600', 'Bộ bàn ghế ăn 6 ghế Gỗ Sồi', 'Xưởng Hải Hậu', -1, 'KHA_DUNG', ?, 'Cô Vân')
        """, (f"Đơn #{order_id}",))
        conn.commit()
        conn.close()

        # Step B: Underpayment webhook: 17,000,000 (short 200,000)
        p1 = {"order_id": order_id, "amount": 17000000, "transaction_id": "TXN_SHORT_17M", "status": "PAID"}
        sig1 = self.sign_payos_webhook(p1)
        st1, d1, _ = self.request('POST', '/api/webhook/payos', p1, headers={'X-Webhook-Signature': sig1})
        self.assertEqual(st1, 200)
        self.assertEqual(d1.get('trang_thai'), 'LECH_TIEN')
        self.assertEqual(d1.get('con_phai_thu'), 200000)

        # Check D7_CONG_NO after underpayment
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, con_lai FROM D7_CONG_NO WHERE tham_chieu LIKE ?", (f"%{order_id}%",))
        d7_short = cur.fetchone()
        conn.close()
        self.assertIsNotNone(d7_short, "Underpayment must create a debt record in D7_CONG_NO!")
        self.assertEqual(d7_short['trang_thai'], 'DANG_NO')
        self.assertEqual(d7_short['con_lai'], 200000)

        # Step C: Top-up webhook: 200,000
        p2 = {"order_id": order_id, "amount": 200000, "transaction_id": "TXN_TOPUP_RECON_200K", "status": "PAID"}
        sig2 = self.sign_payos_webhook(p2)
        st2, d2, _ = self.request('POST', '/api/webhook/payos', p2, headers={'X-Webhook-Signature': sig2})
        self.assertEqual(st2, 200)
        self.assertEqual(d2.get('trang_thai'), 'DA_THANH_TOAN')
        self.assertEqual(d2.get('con_phai_thu'), 0)

        # Check D7_CONG_NO after top-up
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, con_lai, da_tra FROM D7_CONG_NO WHERE tham_chieu LIKE ?", (f"%{order_id}%",))
        d7_settled = cur.fetchone()
        conn.close()
        self.assertIsNotNone(d7_settled)
        self.assertEqual(d7_settled['trang_thai'], 'DA_THU_DU')
        self.assertEqual(d7_settled['con_lai'], 0)
        self.assertEqual(d7_settled['da_tra'], 17200000)

    def test_11_webhook_idempotency_prevents_duplicate_processing(self):
        """2.3: Replaying the same webhook transaction_id must return duplicate: true and not double-decrement stock."""
        payload = {
            "order_id": "KV261026001",
            "amount": 17200000,
            "transaction_id": "TXN_IDEMPOTENT_TEST_999",
            "status": "PAID"
        }
        sig = self.sign_payos_webhook(payload)

        # First request
        st1, d1, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(st1, 200)

        # Count XUAT rows
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE '%KV261026001%' AND loai_dong = 'XUAT'")
        count_first = cur.fetchone()[0]
        conn.close()

        # Replay duplicate request with same txn_id
        st2, d2, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(st2, 200)
        self.assertTrue(d2.get('duplicate'), "Webhook replay did not trigger idempotency deduplication!")

        # Verify no duplicate stock decrement in D4
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE '%KV261026001%' AND loai_dong = 'XUAT'")
        count_second = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count_second, count_first, "Duplicate webhook caused duplicate stock decrement row in D4!")

    def test_12_webhook_signature_tampering_rejected_with_401(self):
        """2.4: Sending webhook with tampered or invalid HMAC signature must return HTTP 401 INVALID_SIGNATURE."""
        payload = {"order_id": "KV261027005", "amount": 200000, "transaction_id": "TXN_ATTACK", "status": "PAID"}
        bad_sig = "deadbeefcafebabe0123456789abcdef0123456789abcdef0123456789abcdef"

        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': bad_sig})
        self.assertEqual(status, 401, f"Expected 401 for bad signature, got {status}: {data}")
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')


if __name__ == '__main__':
    unittest.main()
