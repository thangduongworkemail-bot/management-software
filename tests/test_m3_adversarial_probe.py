#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial Probe for Milestone 3 Review
Testing F06, F07, F08 in server.py
"""

import unittest
import urllib.request
import urllib.error
import json
import sqlite3
import threading
import tempfile
import shutil
import os
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import hmac
import hashlib
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class ThreadedTCPServer(server.socketserver.ThreadingMixIn, server.socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

class M3AdversarialProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.test_dir = tempfile.mkdtemp(prefix='m3_probe_')
        cls.test_db_path = os.path.join(cls.test_dir, 'm3_probe.db')
        server.DB_FILE = cls.test_db_path

        # Init clean DB
        conn = server.get_db()
        server.init_db()
        conn.close()

        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.server_port = cls.httpd.server_address[1]
        cls.server_url = f"http://127.0.0.1:{cls.server_port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def request(self, method, path, data=None, headers=None):
        url = f"{self.server_url}{path}"
        req_headers = {}
        if headers:
            req_headers.update(headers)
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            req_headers['Content-Type'] = 'application/json'

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read()
                content_type = resp.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return resp.status, json.loads(resp_body.decode('utf-8')), resp_body
                return resp.status, None, resp_body
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            try:
                parsed = json.loads(resp_body.decode('utf-8'))
            except Exception:
                parsed = None
            return e.code, parsed, resp_body

    def sign_payos(self, payload):
        canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        return hmac.new(server.PAYOS_WEBHOOK_SECRET.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    # ----------------------------------------------------
    # Probe F06: Inventory Receipt & Confirm Payment
    # ----------------------------------------------------
    def test_p1_inventory_receipt_validation_and_ledger(self):
        # 1. qty <= 0 rejected
        s, d, _ = self.request('POST', '/api/inventory/receipt', {'item': 'GUONG-HOP-SOI-1800', 'qty': 0})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'INVALID_QUANTITY')

        s, d, _ = self.request('POST', '/api/inventory/receipt', {'item': 'GUONG-HOP-SOI-1800', 'qty': -3})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'INVALID_QUANTITY')

        # 2. empty item rejected
        s, d, _ = self.request('POST', '/api/inventory/receipt', {'item': '', 'qty': 5})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'INVALID_ITEM')

        # 3. valid receipt increments D1 ton_hien_co and appends NHAP to D4
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        stock_before = cur.fetchone()['ton_hien_co']
        conn.close()

        s, d, _ = self.request('POST', '/api/inventory/receipt', {
            'item': 'GUONG-HOP-SOI-1800',
            'qty': 5,
            'workshop': 'Xưởng Giường Thạch Thất',
            'ref': 'PN-TEST-99'
        })
        self.assertEqual(s, 200)
        self.assertTrue(d.get('success'))

        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        stock_after = cur.fetchone()['ton_hien_co']
        self.assertEqual(stock_after, stock_before + 5)

        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Lô #PN-TEST-99'")
        ledger = cur.fetchone()
        conn.close()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger['loai_dong'], 'NHAP')
        self.assertEqual(ledger['bien_dong'], 5)
        self.assertEqual(ledger['ma_bien_the'], 'GUONG-HOP-SOI-1800')

    def test_p2_confirm_payment_stock_decrement_and_einvoice(self):
        # Create order with GUONG-HOP-SOI-1800 qty 1
        order_payload = {
            "khach_hang": "Nguyễn Văn Test - 0988111222",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [
                {
                    "ma_bien_the": "GUONG-HOP-SOI-1800",
                    "ten_san_pham": "Giường hộp Gỗ Sồi Nga (1800×2000mm)",
                    "so_luong": 1,
                    "don_gia": 8500000,
                    "thanh_tien": 8500000
                }
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        s, d, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(s, 200)
        ma_don = d['ma_don']

        # Check held stock
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        row_held = cur.fetchone()
        cur_ton = row_held['ton_hien_co']
        cur_giu = row_held['dang_giu_cho']
        conn.close()

        # Confirm payment
        s, d, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': ma_don,
            'amount': 8500000
        })
        self.assertEqual(s, 200)
        self.assertTrue(d.get('success'))

        # Verify D1 decrements
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        row_after = cur.fetchone()
        self.assertEqual(row_after['ton_hien_co'], cur_ton - 1)
        self.assertEqual(row_after['dang_giu_cho'], cur_giu - 1)

        # Verify D4 ledger XUAT
        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_row = cur.fetchone()
        self.assertIsNotNone(xuat_row)
        self.assertEqual(xuat_row['bien_dong'], -1)
        self.assertEqual(xuat_row['ma_bien_the'], 'GUONG-HOP-SOI-1800')

        # Verify D6 auto-created invoice
        cur.execute("SELECT * FROM D6_HOA_DON_DT WHERE ma_don = ?", (ma_don,))
        inv_row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(inv_row)
        self.assertEqual(inv_row['trang_thai'], 'THIEU_MST')

    # ----------------------------------------------------
    # Probe F07: E-Invoice Update MST & Issue
    # ----------------------------------------------------
    def test_p3_invoice_update_mst_validation(self):
        # 1. Missing order_id
        s, d, _ = self.request('POST', '/api/invoices/update-mst', {'mst': '0123456789'})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'MISSING_ORDER_ID')

        # 2. Missing mst
        s, d, _ = self.request('POST', '/api/invoices/update-mst', {'order_id': 'KV261026001', 'mst': ''})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'MISSING_MST')

        # 3. Invalid MST regex
        for bad_mst in ['123', 'abcdefghij', '123456789', '12345678901', '1234567890-12']:
            s, d, _ = self.request('POST', '/api/invoices/update-mst', {'order_id': 'KV261026001', 'mst': bad_mst})
            self.assertEqual(s, 400, f"Failed for bad mst: {bad_mst}")
            self.assertEqual(d.get('error'), 'INVALID_MST')

        # 4. Non-existent order_id
        s, d, _ = self.request('POST', '/api/invoices/update-mst', {'order_id': 'NONEXISTENT', 'mst': '0123456789'})
        self.assertEqual(s, 404)
        self.assertEqual(d.get('error'), 'INVOICE_NOT_FOUND')

    def test_p4_invoice_issuance_lifecycle(self):
        # Create an order, confirm payment -> draft invoice THIEU_MST
        order_payload = {
            "khach_hang": "Công ty TNHH Thử Nghiệm",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s, d, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(s, 200)
        ma_don = d['ma_don']
        self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})

        # Try to issue while THIEU_MST -> should fail 400
        s, d, _ = self.request('POST', '/api/invoices/issue', {'order_id': ma_don})
        self.assertEqual(s, 400)
        self.assertEqual(d.get('error'), 'INVOICE_MISSING_MST')

        # Update valid 10-digit MST
        s, d, _ = self.request('POST', '/api/invoices/update-mst', {
            'order_id': ma_don,
            'mst': '0101234567',
            'email': 'ketoan@thunghiem.vn'
        })
        self.assertEqual(s, 200)
        self.assertEqual(d['trang_thai'], 'CHO_XUAT')

        # Issue invoice -> should succeed with 7-digit so_hoa_don
        s, d, _ = self.request('POST', '/api/invoices/issue', {'order_id': ma_don})
        self.assertEqual(s, 200)
        inv_no = d.get('invoice_no')
        self.assertIsNotNone(inv_no)
        self.assertEqual(len(inv_no), 7)
        self.assertTrue(inv_no.isdigit())

        # Check D9 audit log
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM D9_NHAT_KY WHERE hanh_dong = 'PHAT_HANH_HDDT' AND doi_tuong = ?", (f"HĐ #{inv_no}",))
        audit = cur.fetchone()
        conn.close()
        self.assertIsNotNone(audit)

        # Re-issue already issued invoice -> should return 409
        s, d, _ = self.request('POST', '/api/invoices/issue', {'order_id': ma_don})
        self.assertEqual(s, 409)
        self.assertEqual(d.get('error'), 'INVOICE_ALREADY_ISSUED')

        # Try updating MST on already issued invoice -> should return 409
        s, d, _ = self.request('POST', '/api/invoices/update-mst', {'order_id': ma_don, 'mst': '0109999999'})
        self.assertEqual(s, 409)
        self.assertEqual(d.get('error'), 'INVOICE_ALREADY_ISSUED')

    # ----------------------------------------------------
    # Probe F07: Export Invoice Package (Decree 123 / Circular 78)
    # ----------------------------------------------------
    def test_p5_export_invoice_endpoint(self):
        """Testing GET /api/invoices/export"""
        # Test 1: calling without order_id
        s, d, raw = self.request('GET', '/api/invoices/export')
        print(f"\n[EXPORT PROBE 1] status: {s}, response: {d or raw[:200]}")

        # Test 2: calling with existing order_id
        s2, d2, raw2 = self.request('GET', '/api/invoices/export?order_id=KV261026001')
        print(f"[EXPORT PROBE 2] status: {s2}, response: {d2 or raw2[:200]}")

        # Test 3: calling with format=xml
        s3, d3, raw3 = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=xml')
        print(f"[EXPORT PROBE 3] status: {s3}, raw len: {len(raw3)}")

    # ----------------------------------------------------
    # Probe F08: Webhook PayOS (HMAC, Deduplication, Reconciliation)
    # ----------------------------------------------------
    def test_p6_webhook_payos_edge_cases(self):
        # 1. Invalid signature when header present
        payload = {"order_id": "KV261026001", "amount": 17200000, "transaction_id": "TXN_BAD_SIG"}
        s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': 'invalid_sig'})
        self.assertEqual(s, 401)
        self.assertEqual(d.get('error'), 'INVALID_SIGNATURE')

        # 2. Valid signature
        sig = self.sign_payos(payload)
        s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(s, 200)

        # 3. Deduplication (same txn_id)
        s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(s, 200)
        self.assertTrue(d.get('duplicate'))

        # 4. Underpayment reconciliation (LECH_TIEN)
        # Create order for 8,500,000
        ord_p = {
            "khach_hang": "Khách thiếu tiền",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s, d, _ = self.request('POST', '/api/orders', ord_p)
        self.assertEqual(s, 200)
        ma_don = d['ma_don']

        # Pay only 8,000,000 (deficit 500,000)
        part_p = {"order_id": ma_don, "amount": 8000000, "transaction_id": f"TXN_PART_{int(time.time())}"}
        sig_part = self.sign_payos(part_p)
        s, d, _ = self.request('POST', '/api/webhook/payos', part_p, headers={'X-Webhook-Signature': sig_part})
        self.assertEqual(s, 200)
        self.assertEqual(d.get('trang_thai'), 'LECH_TIEN')
        self.assertEqual(d.get('con_phai_thu'), 500000)

        # Top up the remaining 500,000
        topup_p = {"order_id": ma_don, "amount": 500000, "transaction_id": f"TXN_TOPUP_{int(time.time())}"}
        sig_topup = self.sign_payos(topup_p)
        s, d, _ = self.request('POST', '/api/webhook/payos', topup_p, headers={'X-Webhook-Signature': sig_topup})
        self.assertEqual(s, 200)
        self.assertEqual(d.get('trang_thai'), 'DA_THANH_TOAN')
        self.assertEqual(d.get('con_phai_thu'), 0)

if __name__ == '__main__':
    unittest.main()
