#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification suite for Milestone 3 Remediation:
- GET /api/invoices/export (JSON, XML, 400 on missing order_id, 404 on nonexistent order)
- POST /api/orders/confirm-payment (400 on amount <= 0, 404 on nonexistent order, zero ledger pollution)
"""

import unittest
import urllib.request
import urllib.error
import json
import sqlite3
import shutil
import tempfile
import os
import sys
import threading
from http.server import HTTPServer

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class M3ExportPaymentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix='m3_export_payment_')
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_khanhvan.db')
        shutil.copy2('khanhvan.db', cls.test_db_path)

        # Point server to isolated test DB
        server.DB_FILE = cls.test_db_path

        cls.port = 5599
        cls.httpd = HTTPServer(('127.0.0.1', cls.port), server.KhanhVanServer)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def request(self, method, path, data=None):
        url = f"{self.base_url}{path}"
        req_headers = {'Accept': 'application/json'}
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            req_headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read().decode('utf-8')
                headers = dict(resp.headers)
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                return resp.status, parsed, headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            headers = dict(e.headers)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return e.code, parsed, headers

    def get_db(self):
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------------------
    # 1. GET /api/invoices/export Tests
    # -------------------------------------------------------------------------
    def test_01_export_invoice_json_success(self):
        """Export invoice in JSON format for existing order returns 200 and schema compliant payload."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=json')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        pkg = data.get('data', {})
        self.assertIn('generalInvoiceInfo', pkg)
        self.assertIn('sellerInfo', pkg)
        self.assertIn('buyerInfo', pkg)
        self.assertIn('itemInfo', pkg)
        self.assertIn('settlementInfo', pkg)
        self.assertEqual(pkg['generalInvoiceInfo']['invoiceSeries'], '1C26TKV')

    def test_02_export_invoice_xml_success(self):
        """Export invoice in XML format returns 200 with application/xml header and valid XML root."""
        status, data, headers = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=xml')
        self.assertEqual(status, 200)
        content_type = headers.get('Content-Type', headers.get('content-type', ''))
        self.assertIn('application/xml', content_type)
        self.assertTrue(isinstance(data, str))
        self.assertTrue(data.startswith('<?xml') or '<HDon' in data)
        self.assertIn('<KHHDon>1C26TKV</KHHDon>', data)

    def test_03_export_invoice_missing_order_id(self):
        """Export invoice without order_id parameter returns HTTP 400 MISSING_ORDER_ID."""
        status, data, _ = self.request('GET', '/api/invoices/export')
        self.assertEqual(status, 400)
        self.assertEqual(data.get('error'), 'MISSING_ORDER_ID')

    def test_04_export_invoice_nonexistent_order(self):
        """Export invoice with nonexistent order returns HTTP 404 INVOICE_NOT_FOUND."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV-NONEXISTENT-999')
        self.assertEqual(status, 404)
        self.assertEqual(data.get('error'), 'INVOICE_NOT_FOUND')

    # -------------------------------------------------------------------------
    # 2. POST /api/orders/confirm-payment Tests
    # -------------------------------------------------------------------------
    def test_05_confirm_payment_amount_zero_rejected(self):
        """Confirming payment with amount = 0 returns HTTP 400 INVALID_AMOUNT."""
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': 'KV261026001', 'amount': 0})
        self.assertEqual(status, 400)
        self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_06_confirm_payment_amount_negative_rejected(self):
        """Confirming payment with negative amount returns HTTP 400 INVALID_AMOUNT."""
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': 'KV261026001', 'amount': -500000})
        self.assertEqual(status, 400)
        self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_07_confirm_payment_nonexistent_order_no_pollution(self):
        """Confirming payment on nonexistent order returns HTTP 404 and NEVER inserts into D4 or D9."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        initial_d9 = cur.fetchone()[0]
        conn.close()

        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'KV-BOGUS-NONEXISTENT',
            'amount': 1500000
        })
        self.assertEqual(status, 404)
        self.assertEqual(data.get('error'), 'ORDER_NOT_FOUND')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        new_d9 = cur.fetchone()[0]
        conn.close()

        self.assertEqual(new_d4, initial_d4, "D4 append-only ledger must not be polluted on nonexistent orders!")
        self.assertEqual(new_d9, initial_d9, "D9 audit chain must not log for nonexistent orders!")

    def test_08_confirm_payment_success_flow(self):
        """Valid payment confirmation successfully creates XUAT record in D4 and updates D3 order status."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4 = cur.fetchone()[0]
        conn.close()

        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'KV261026002',
            'amount': 5328000
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = 'KV261026002'")
        order = cur.fetchone()
        self.assertEqual(order['trang_thai'], 'DA_THANH_TOAN')
        self.assertEqual(order['con_phai_thu'], 0)

        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Đơn #KV261026002' AND loai_dong = 'XUAT'")
        xuat_row = cur.fetchone()
        self.assertIsNotNone(xuat_row)
        self.assertEqual(xuat_row['bien_dong'], -1)

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4 = cur.fetchone()[0]
        self.assertEqual(new_d4, initial_d4 + 1)
        conn.close()


if __name__ == '__main__':
    unittest.main()
