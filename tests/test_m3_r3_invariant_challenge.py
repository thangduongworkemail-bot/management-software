#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milestone 3 Round 3 Empirical Invariant Challenge Suite
Challenger: m3_r3_challenger_2 (Milestone 3 Invariant Challenger)

Empirical Challenge Coverage:
1. GET /api/invoices/export boundary, SQL injection resistance, case insensitivity, Decree 123/Circular 78 compliance.
2. POST /api/orders/confirm-payment boundary values, status guards (DA_HUY, DA_HUY_HET_HAN), sequential idempotency, and concurrent burst serialization.
3. POST /api/webhook/payos boundary values, HMAC signature tampering, duplicate transaction replay, underpayment vs top-up reconciliation, and concurrent thundering herd replay.
4. POST /api/invoices/issue and update-mst lifecycle guards, MST regex validation, and replay re-issuing prevention.
5. D4_SO_CAI_TON append-only SQLite trigger enforcement and D9_NHAT_KY SHA-256 chain verification after all operations.
"""

import unittest
import urllib.request
import urllib.error
import json
import sqlite3
import hashlib
import hmac
import shutil
import tempfile
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer
import socketserver

# Ensure UTF-8 stdout on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 100

class M3R3InvariantChallengeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.temp_dir = tempfile.mkdtemp(prefix='m3_r3_challenger_')
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_khanhvan.db')
        server.DB_FILE = cls.test_db_path
        server.init_db()

        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Wait for server readiness
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
            raise RuntimeError(f"Challenger server failed to start on {cls.base_url}")

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def get_db(self):
        conn = sqlite3.connect(self.test_db_path, timeout=30.0)
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
                resp_body = resp.read()
                content_type = resp.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return resp.status, json.loads(resp_body.decode('utf-8')), resp_body
                return resp.status, None, resp_body
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            content_type = e.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                try:
                    return e.code, json.loads(resp_body.decode('utf-8')), resp_body
                except Exception:
                    pass
            return e.code, None, resp_body

    def sign_payload(self, payload):
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hmac.new(server.PAYOS_WEBHOOK_SECRET.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest()

    # =========================================================================
    # 1. GET /api/invoices/export BOUNDARY & INJECTION CHALLENGES
    # =========================================================================
    def test_01_export_missing_order_id_returns_400(self):
        status, data, _ = self.request('GET', '/api/invoices/export')
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'MISSING_ORDER_ID')

    def test_02_export_empty_order_id_returns_400(self):
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=%20%20')
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'MISSING_ORDER_ID')

    def test_03_export_sql_injection_attempt_safely_rejected_404(self):
        injected = urllib.parse.quote("' OR '1'='1")
        status, data, _ = self.request('GET', f"/api/invoices/export?order_id={injected}")
        self.assertEqual(status, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVOICE_NOT_FOUND')

    def test_04_export_nonexistent_order_returns_404(self):
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV-NONEXISTENT-999')
        self.assertEqual(status, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVOICE_NOT_FOUND')

    def test_05_export_valid_order_json_case_insensitive_format(self):
        for fmt in ['json', 'JSON', 'Json']:
            status, data, _ = self.request('GET', f'/api/invoices/export?order_id=KV261026001&format={fmt}')
            self.assertEqual(status, 200, f"Failed for format={fmt}")
            self.assertTrue(data['success'])
            self.assertIn('generalInvoiceInfo', data['data'])
            self.assertIn('sellerInfo', data['data'])
            self.assertIn('buyerInfo', data['data'])
            self.assertIn('itemInfo', data['data'])
            self.assertIn('settlementInfo', data['data'])

    def test_06_export_valid_order_xml_case_insensitive_format(self):
        for fmt in ['xml', 'XML', 'Xml']:
            status, _, raw_body = self.request('GET', f'/api/invoices/export?order_id=KV261026001&format={fmt}')
            self.assertEqual(status, 200, f"Failed for format={fmt}")
            xml_text = raw_body.decode('utf-8')
            self.assertTrue(xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
            self.assertIn('<HDon xmlns="http://laphoadon.gdt.gov.vn/2020/01">', xml_text)
            self.assertIn('<THDon>Hóa đơn giá trị gia tăng</THDon>', xml_text)
            self.assertIn('<KHHDon>1C26TKV</KHHDon>', xml_text)

    def test_07_export_unknown_format_defaults_to_json(self):
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=yaml')
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertIn('generalInvoiceInfo', data['data'])

    # =========================================================================
    # 2. POST /api/orders/confirm-payment BOUNDARY & STATE INVARIANTS
    # =========================================================================
    def test_08_confirm_payment_amount_zero_or_negative_returns_400(self):
        for bad_amount in [0, -1, -5000000]:
            status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
                'order_id': 'KV261026001',
                'amount': bad_amount
            })
            self.assertEqual(status, 400, f"Failed on amount={bad_amount}")
            self.assertFalse(data['success'])
            self.assertEqual(data['error'], 'INVALID_AMOUNT')

    def test_09_confirm_payment_non_numeric_amount_returns_400(self):
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'KV261026001',
            'amount': 'one_million'
        })
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVALID_AMOUNT')

    def test_10_confirm_payment_nonexistent_order_returns_404(self):
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'NONEXISTENT_ORDER_9999',
            'amount': 1000000
        })
        self.assertEqual(status, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'ORDER_NOT_FOUND')

    def test_11_confirm_payment_on_cancelled_and_expired_order_returns_400(self):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai) VALUES ('TEST_CANCELLED_01', '29/10/2026 10:00', 'Khách Test Hủy', 'Cô Vân', 5000000, 'CK', 'DA_HUY')")
        cur.execute("INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai) VALUES ('TEST_EXPIRED_01', '29/10/2026 10:00', 'Khách Test Hết Hạn', 'Cô Vân', 5000000, 'CK', 'DA_HUY_HET_HAN')")
        conn.commit()
        conn.close()

        for ord_id in ['TEST_CANCELLED_01', 'TEST_EXPIRED_01']:
            status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
                'order_id': ord_id,
                'amount': 5000000
            })
            self.assertEqual(status, 400, f"Accepted payment on cancelled/expired order {ord_id}")
            self.assertFalse(data['success'])
            self.assertEqual(data['error'], 'CANNOT_PAY_CANCELLED_ORDER')

    def test_12_confirm_payment_sequential_duplicate_idempotency(self):
        # Create dedicated order
        ord_id = f"TEST_SEQ_PAY_{int(time.time()*1000)%1000000}"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu) VALUES (?, '29/10/2026 10:00', 'Khách Seq', 'Cô Vân', 3000000, 'CK', 'GIU_CHO', 0, 3000000)", (ord_id,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('29/10 10:00', 'GIU_CHO', 'GUONG-HOP-SOI-1800', 'Giường hộp', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', ?, 'Cô Vân')", (f"Đơn #{ord_id}",))
        conn.commit()
        conn.close()

        # 1st call -> Success
        s1, d1, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ord_id, 'amount': 3000000})
        self.assertEqual(s1, 200)
        self.assertTrue(d1['success'])
        self.assertFalse(d1.get('duplicate', False))

        # 2nd call -> Duplicate idempotent
        s2, d2, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ord_id, 'amount': 3000000})
        self.assertEqual(s2, 200)
        self.assertTrue(d2['success'])
        self.assertTrue(d2.get('duplicate', False))

        # Check D4 has exactly 1 XUAT entry
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ord_id}",))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    def test_13_confirm_payment_concurrent_burst_serialization(self):
        ord_id = f"TEST_BURST_PAY_{int(time.time()*1000)%1000000}"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu) VALUES (?, '29/10/2026 10:00', 'Khách Burst', 'Cô Vân', 4000000, 'CK', 'GIU_CHO', 0, 4000000)", (ord_id,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('29/10 10:00', 'GIU_CHO', 'GUONG-HOP-SOI-1800', 'Giường hộp', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', ?, 'Cô Vân')", (f"Đơn #{ord_id}",))
        conn.commit()
        conn.close()

        def do_pay():
            return self.request('POST', '/api/orders/confirm-payment', {'order_id': ord_id, 'amount': 4000000})

        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(do_pay) for _ in range(15)]
            results = [f.result() for f in futures]

        statuses = [r[0] for r in results]
        self.assertTrue(all(s == 200 for s in statuses))

        initial_hits = sum(1 for r in results if not r[1].get('duplicate', False))
        duplicate_hits = sum(1 for r in results if r[1].get('duplicate', False))

        self.assertEqual(initial_hits, 1, f"Expected 1 initial hit but got {initial_hits}")
        self.assertEqual(duplicate_hits, 14, f"Expected 14 duplicate hits but got {duplicate_hits}")

        # Check D4 has exactly 1 XUAT entry
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ord_id}",))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    # =========================================================================
    # 3. POST /api/webhook/payos BOUNDARY & IDEMPOTENCY INVARIANTS
    # =========================================================================
    def test_14_webhook_amount_zero_or_negative_returns_400(self):
        for bad_amount in [0, -50000]:
            payload = {'order_id': 'KV261026001', 'amount': bad_amount, 'transaction_id': 'TXN_TEST_01'}
            sig = self.sign_payload(payload)
            status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
            self.assertEqual(status, 400)
            self.assertFalse(data['success'])
            self.assertEqual(data['error'], 'INVALID_AMOUNT')

    def test_15_webhook_missing_order_id_returns_400(self):
        payload = {'amount': 1000000, 'transaction_id': 'TXN_TEST_02'}
        sig = self.sign_payload(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'MISSING_ORDER_ID')

    def test_16_webhook_invalid_hmac_signature_returns_401(self):
        payload = {'order_id': 'KV261026001', 'amount': 17200000, 'transaction_id': 'TXN_TEST_03'}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': 'deadbeef'*8})
        self.assertEqual(status, 401)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVALID_SIGNATURE')

    def test_17_webhook_nonexistent_order_returns_404(self):
        payload = {'order_id': 'NONEXISTENT_KV_99999', 'amount': 1000000, 'transaction_id': 'TXN_TEST_04'}
        sig = self.sign_payload(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'ORDER_NOT_FOUND')

    def test_18_webhook_underpayment_and_topup_reconciliation(self):
        ord_id = f"TEST_RECON_{int(time.time()*1000)%1000000}"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu) VALUES (?, '29/10/2026 10:00', 'Khách Recon', 'Cô Vân', 10000000, 'VietQR Napas 247', 'GIU_CHO', 0, 10000000)", (ord_id,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('29/10 10:00', 'GIU_CHO', 'GUONG-HOP-SOI-1800', 'Giường hộp', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', ?, 'Cô Vân')", (f"Đơn #{ord_id}",))
        conn.commit()
        conn.close()

        # Step 1: Underpayment 8,000,000 out of 10,000,000
        p1 = {'order_id': ord_id, 'amount': 8000000, 'transaction_id': f'TXN_{ord_id}_P1'}
        s1, d1, _ = self.request('POST', '/api/webhook/payos', p1, headers={'X-Webhook-Signature': self.sign_payload(p1)})
        self.assertEqual(s1, 200)
        self.assertEqual(d1['trang_thai'], 'LECH_TIEN')
        self.assertEqual(d1['tien_da_thu'], 8000000)
        self.assertEqual(d1['con_phai_thu'], 2000000)

        # Check D7_CONG_NO was created with 2M deficit
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT con_lai, trang_thai FROM D7_CONG_NO WHERE tham_chieu LIKE ?", (f"%{ord_id}%",))
        debt_row = cur.fetchone()
        self.assertIsNotNone(debt_row)
        self.assertEqual(debt_row['con_lai'], 2000000)
        self.assertEqual(debt_row['trang_thai'], 'DANG_NO')
        conn.close()

        # Step 2: Top-up remaining 2,000,000
        p2 = {'order_id': ord_id, 'amount': 2000000, 'transaction_id': f'TXN_{ord_id}_P2'}
        s2, d2, _ = self.request('POST', '/api/webhook/payos', p2, headers={'X-Webhook-Signature': self.sign_payload(p2)})
        self.assertEqual(s2, 200)
        self.assertEqual(d2['trang_thai'], 'DA_THANH_TOAN')
        self.assertEqual(d2['tien_da_thu'], 10000000)
        self.assertEqual(d2['con_phai_thu'], 0)

        # Check D7_CONG_NO updated to DA_THU_DU
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT con_lai, trang_thai FROM D7_CONG_NO WHERE tham_chieu LIKE ?", (f"%{ord_id}%",))
        debt_row2 = cur.fetchone()
        self.assertIsNotNone(debt_row2)
        self.assertEqual(debt_row2['con_lai'], 0)
        self.assertEqual(debt_row2['trang_thai'], 'DA_THU_DU')
        conn.close()

    def test_19_webhook_concurrent_thundering_herd_replay_attack(self):
        ord_id = f"TEST_WH_HERD_{int(time.time()*1000)%1000000}"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu) VALUES (?, '29/10/2026 10:00', 'Khách Herd', 'Cô Vân', 5000000, 'VietQR Napas 247', 'GIU_CHO', 0, 5000000)", (ord_id,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('29/10 10:00', 'GIU_CHO', 'GUONG-HOP-SOI-1800', 'Giường hộp', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', ?, 'Cô Vân')", (f"Đơn #{ord_id}",))
        conn.commit()
        conn.close()

        txn_id = f"TXN_HERD_{ord_id}"
        payload = {'order_id': ord_id, 'amount': 5000000, 'transaction_id': txn_id}
        sig = self.sign_payload(payload)

        def send_hook():
            return self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(send_hook) for _ in range(20)]
            results = [f.result() for f in futures]

        statuses = [r[0] for r in results]
        self.assertTrue(all(s == 200 for s in statuses))

        initial_hits = sum(1 for r in results if not r[1].get('duplicate', False))
        duplicate_hits = sum(1 for r in results if r[1].get('duplicate', False))

        self.assertEqual(initial_hits, 1, f"Expected 1 initial hit but got {initial_hits}")
        self.assertEqual(duplicate_hits, 19, f"Expected 19 duplicate hits but got {duplicate_hits}")

        # Check D4 has exactly 1 XUAT entry
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{ord_id}%",))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    # =========================================================================
    # 4. POST /api/invoices/issue AND update-mst INVARIANTS
    # =========================================================================
    def test_20_issue_invoice_missing_order_id_returns_400(self):
        status, data, _ = self.request('POST', '/api/invoices/issue', {})
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'MISSING_ORDER_ID')

    def test_21_issue_invoice_nonexistent_order_returns_404(self):
        status, data, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'NONEXISTENT_INV_999'})
        self.assertEqual(status, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVOICE_NOT_FOUND')

    def test_22_issue_invoice_thieu_mst_blocked_returns_400(self):
        status, data, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026004'})
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVOICE_MISSING_MST')

    def test_23_update_mst_invalid_format_returns_400(self):
        for bad_mst in ['123', 'abc', '123456789', '12345678901']:
            status, data, _ = self.request('POST', '/api/invoices/update-mst', {
                'order_id': 'KV261026004',
                'mst': bad_mst
            })
            self.assertEqual(status, 400, f"Allowed invalid MST '{bad_mst}'")
            self.assertFalse(data['success'])
            self.assertEqual(data['error'], 'INVALID_MST')

    def test_24_update_mst_valid_10_digits_transitions_to_cho_xuat(self):
        status, data, _ = self.request('POST', '/api/invoices/update-mst', {
            'order_id': 'KV261026004',
            'mst': '0101234567'
        })
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['trang_thai'], 'CHO_XUAT')

        # Now issuing should succeed
        s_iss, d_iss, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026004'})
        self.assertEqual(s_iss, 200)
        self.assertTrue(d_iss['success'])
        self.assertEqual(d_iss['trang_thai'], 'DA_XUAT')
        self.assertTrue(bool(d_iss.get('invoice_no')))

        # Re-issuing should return 409 Conflict
        s_re, d_re, _ = self.request('POST', '/api/invoices/issue', {'order_id': 'KV261026004'})
        self.assertEqual(s_re, 409)
        self.assertFalse(d_re['success'])
        self.assertEqual(d_re['error'], 'INVOICE_ALREADY_ISSUED')

    # =========================================================================
    # 5. D4 APPEND-ONLY TRIGGERS & D9 SHA-256 AUDIT CHAIN INVARIANTS
    # =========================================================================
    def test_25_d4_ledger_triggers_prevent_update_and_delete(self):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM D4_SO_CAI_TON LIMIT 1")
        row = cur.fetchone()
        row_id = row['id']

        # UPDATE must raise sqlite3.Error
        with self.assertRaises(sqlite3.Error):
            cur.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 999 WHERE id = ?", (row_id,))

        # DELETE must raise sqlite3.Error
        with self.assertRaises(sqlite3.Error):
            cur.execute("DELETE FROM D4_SO_CAI_TON WHERE id = ?", (row_id,))

        conn.close()

    def test_26_sha256_audit_chain_remains_100_percent_valid(self):
        status, data, _ = self.request('POST', '/api/audit/verify')
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertTrue(data.get('valid', False), f"Audit chain verification failed: {data}")
        self.assertIn("toàn vẹn 100%", data.get('message', ''))

if __name__ == '__main__':
    unittest.main()
