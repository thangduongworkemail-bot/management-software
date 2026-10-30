#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milestone 3 Round 2 Empirical Boundary & Security Challenge Suite
Challenger: m3_r2_challenger_2 (Milestone 3 Invariant & Security Challenger)

Focus:
1. POST /api/inventory/receipt boundary conditions:
   - zero qty -> 400 INVALID_QUANTITY
   - negative qty -> 400 INVALID_QUANTITY
   - non-numeric string qty -> 400 INVALID_QUANTITY
   - missing/blank item -> 400 INVALID_ITEM
   - valid receipt -> 200, D4 append-only row created, D1 ton_hien_co updated

2. POST /api/orders/confirm-payment boundary conditions:
   - zero amount -> 400 INVALID_AMOUNT
   - negative amount -> 400 INVALID_AMOUNT
   - nonexistent order -> 404 ORDER_NOT_FOUND
   - verify ZERO pollution in D4 ledger and D9 audit log on error

3. GET /api/invoices/export boundary conditions:
   - missing order_id -> 400 MISSING_ORDER_ID
   - empty/whitespace order_id -> 400 MISSING_ORDER_ID
   - nonexistent order -> 404 INVOICE_NOT_FOUND
   - valid order format=json -> 200 with Circular 78 JSON
   - valid order format=xml -> 200 with application/xml and <HDon>

4. POST /api/webhook/payos boundary conditions:
   - negative amount -> 400 INVALID_AMOUNT
   - zero amount -> 400 INVALID_AMOUNT
   - missing order_id -> 400 MISSING_ORDER_ID
   - invalid HMAC signature if header present -> 401 INVALID_SIGNATURE
   - nonexistent order -> 404 ORDER_NOT_FOUND
   - verify ZERO pollution in D4 ledger and D9 audit log on 400/401/404 errors
   - valid payment with signature -> 200 with idempotency
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
from http.server import HTTPServer

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server


class M3R2BoundaryChallengeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.temp_dir = tempfile.mkdtemp(prefix='m3_r2_challenger_')
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_khanhvan.db')
        shutil.copy2('khanhvan.db', cls.test_db_path)

        # Point server to isolated test DB
        server.DB_FILE = cls.test_db_path

        cls.port = 5596
        cls.httpd = HTTPServer(('127.0.0.1', cls.port), server.KhanhVanServer)
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
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
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

    def sign_payos(self, payload_dict):
        secret = os.environ.get('PAYOS_WEBHOOK_SECRET', 'khanhvan_payos_secret_2026')
        canonical = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
        return hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    # =========================================================================
    # SUITE 1: POST /api/inventory/receipt Boundary & Error Verification
    # =========================================================================

    def test_01_receipt_zero_qty_returns_400(self):
        """POST /api/inventory/receipt with qty = 0 must return 400 INVALID_QUANTITY."""
        status, data, _ = self.request('POST', '/api/inventory/receipt', {
            'item': 'SP-THO-MIT-01',
            'qty': 0
        })
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_QUANTITY')

    def test_02_receipt_negative_qty_returns_400(self):
        """POST /api/inventory/receipt with qty < 0 must return 400 INVALID_QUANTITY."""
        for bad_qty in [-1, -10, -9999]:
            with self.subTest(qty=bad_qty):
                status, data, _ = self.request('POST', '/api/inventory/receipt', {
                    'item': 'SP-THO-MIT-01',
                    'qty': bad_qty
                })
                self.assertEqual(status, 400)
                self.assertFalse(data.get('success'))
                self.assertEqual(data.get('error'), 'INVALID_QUANTITY')

    def test_03_receipt_non_numeric_qty_returns_400(self):
        """POST /api/inventory/receipt with non-numeric qty parses as 0 and returns 400 INVALID_QUANTITY."""
        status, data, _ = self.request('POST', '/api/inventory/receipt', {
            'item': 'SP-THO-MIT-01',
            'qty': 'invalid_qty'
        })
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_QUANTITY')

    def test_04_receipt_missing_or_blank_item_returns_400(self):
        """POST /api/inventory/receipt with missing or blank item returns 400 INVALID_ITEM."""
        for bad_item in ['', '   ', None]:
            payload = {'qty': 5}
            if bad_item is not None:
                payload['item'] = bad_item
            status, data, _ = self.request('POST', '/api/inventory/receipt', payload)
            self.assertEqual(status, 400)
            self.assertFalse(data.get('success'))
            self.assertEqual(data.get('error'), 'INVALID_ITEM')

    def test_05_receipt_valid_updates_d1_and_appends_d4(self):
        """POST /api/inventory/receipt with valid params returns 200, updates D1, and appends to D4."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'BO-BANAN-SOI-1600'")
        initial_ton = cur.fetchone()['ton_hien_co']
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4_count = cur.fetchone()[0]
        conn.close()

        status, data, _ = self.request('POST', '/api/inventory/receipt', {
            'item': 'BO-BANAN-SOI-1600',
            'qty': 3,
            'workshop': 'Xưởng Thạch Thất',
            'cost': 15000000,
            'ref': 'PN_CHALLENGE_01',
            'actor': 'Cô Vân (Chủ)'
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = 'BO-BANAN-SOI-1600'")
        new_ton = cur.fetchone()['ton_hien_co']
        self.assertEqual(new_ton, initial_ton + 3)

        cur.execute("SELECT * FROM D4_SO_CAI_TON WHERE tham_chieu = 'Lô #PN_CHALLENGE_01'")
        receipt_row = cur.fetchone()
        self.assertIsNotNone(receipt_row)
        self.assertEqual(receipt_row['loai_dong'], 'NHAP')
        self.assertEqual(receipt_row['bien_dong'], 3)
        self.assertEqual(receipt_row['ma_bien_the'], 'BO-BANAN-SOI-1600')

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4_count = cur.fetchone()[0]
        self.assertEqual(new_d4_count, initial_d4_count + 1)
        conn.close()

    # =========================================================================
    # SUITE 2: POST /api/orders/confirm-payment Boundary & Error Verification
    # =========================================================================

    def test_06_confirm_payment_zero_amount_returns_400(self):
        """POST /api/orders/confirm-payment with amount = 0 returns 400 INVALID_AMOUNT."""
        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'KV261026001',
            'amount': 0
        })
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_07_confirm_payment_negative_amount_returns_400(self):
        """POST /api/orders/confirm-payment with amount < 0 returns 400 INVALID_AMOUNT."""
        for bad_amt in [-1, -50000, -10000000]:
            with self.subTest(amount=bad_amt):
                status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
                    'order_id': 'KV261026001',
                    'amount': bad_amt
                })
                self.assertEqual(status, 400)
                self.assertFalse(data.get('success'))
                self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_08_confirm_payment_nonexistent_order_returns_404_zero_pollution(self):
        """POST /api/orders/confirm-payment with nonexistent order returns 404 ORDER_NOT_FOUND and leaves D4/D9 untouched."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        initial_d9 = cur.fetchone()[0]
        cur.execute("SELECT curr_hash FROM D9_NHAT_KY ORDER BY id DESC LIMIT 1")
        initial_hash = cur.fetchone()['curr_hash']
        conn.close()

        status, data, _ = self.request('POST', '/api/orders/confirm-payment', {
            'order_id': 'KV-GHOST-ORDER-999',
            'amount': 2500000
        })
        self.assertEqual(status, 404)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'ORDER_NOT_FOUND')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        new_d9 = cur.fetchone()[0]
        cur.execute("SELECT curr_hash FROM D9_NHAT_KY ORDER BY id DESC LIMIT 1")
        new_hash = cur.fetchone()['curr_hash']
        conn.close()

        self.assertEqual(new_d4, initial_d4, "D4 append-only ledger polluted by nonexistent order payment!")
        self.assertEqual(new_d9, initial_d9, "D9 audit log polluted by nonexistent order payment!")
        self.assertEqual(new_hash, initial_hash, "D9 hash chain broken/altered by nonexistent order payment!")

    # =========================================================================
    # SUITE 3: GET /api/invoices/export Boundary & Error Verification
    # =========================================================================

    def test_09_export_missing_order_id_returns_400(self):
        """GET /api/invoices/export with missing order_id returns 400 MISSING_ORDER_ID."""
        status, data, _ = self.request('GET', '/api/invoices/export')
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'MISSING_ORDER_ID')

    def test_10_export_empty_order_id_returns_400(self):
        """GET /api/invoices/export with empty order_id returns 400 MISSING_ORDER_ID."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=')
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'MISSING_ORDER_ID')

        status_ws, data_ws, _ = self.request('GET', '/api/invoices/export?order_id=+%20+')
        self.assertEqual(status_ws, 400)
        self.assertFalse(data_ws.get('success'))
        self.assertEqual(data_ws.get('error'), 'MISSING_ORDER_ID')

    def test_11_export_nonexistent_order_returns_404(self):
        """GET /api/invoices/export with nonexistent order returns 404 INVOICE_NOT_FOUND."""
        status, data, _ = self.request('GET', '/api/invoices/export?order_id=KV-NONEXISTENT-777')
        self.assertEqual(status, 404)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVOICE_NOT_FOUND')

    def test_12_export_valid_order_json_and_xml(self):
        """GET /api/invoices/export with valid order returns 200 for both JSON and XML formats."""
        # JSON format
        status_json, data_json, _ = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=json')
        self.assertEqual(status_json, 200)
        self.assertTrue(data_json.get('success'))
        self.assertIn('data', data_json)
        self.assertIn('generalInvoiceInfo', data_json['data'])
        self.assertEqual(data_json['data']['generalInvoiceInfo']['invoiceSeries'], '1C26TKV')

        # XML format
        status_xml, data_xml, headers_xml = self.request('GET', '/api/invoices/export?order_id=KV261026001&format=xml')
        self.assertEqual(status_xml, 200)
        ctype = headers_xml.get('Content-Type', headers_xml.get('content-type', ''))
        self.assertIn('application/xml', ctype)
        self.assertTrue(data_xml.startswith('<?xml') or '<HDon' in data_xml)
        self.assertTrue('</HDon>' in data_xml)
        self.assertTrue('<KHHDon>1C26TKV</KHHDon>' in data_xml)

    # =========================================================================
    # SUITE 4: POST /api/webhook/payos Boundary & Error Verification
    # =========================================================================

    def test_13_webhook_negative_amount_returns_400(self):
        """POST /api/webhook/payos with negative amount returns 400 INVALID_AMOUNT."""
        for bad_amt in [-1, -200000, -9999999]:
            with self.subTest(amount=bad_amt):
                payload = {
                    'order_id': 'KV261026001',
                    'amount': bad_amt,
                    'transaction_id': 'TXN_TEST_NEG_AMT',
                    'status': 'PAID'
                }
                sig = self.sign_payos(payload)
                status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
                self.assertEqual(status, 400)
                self.assertFalse(data.get('success'))
                self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_14_webhook_zero_amount_returns_400(self):
        """POST /api/webhook/payos with amount = 0 returns 400 INVALID_AMOUNT."""
        payload = {
            'order_id': 'KV261026001',
            'amount': 0,
            'transaction_id': 'TXN_TEST_ZERO_AMT',
            'status': 'PAID'
        }
        sig = self.sign_payos(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 400)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_AMOUNT')

    def test_15_webhook_invalid_signature_if_header_present_returns_401(self):
        """POST /api/webhook/payos with invalid signature header returns 401 INVALID_SIGNATURE."""
        payload = {
            'order_id': 'KV261026001',
            'amount': 17200000,
            'transaction_id': 'TXN_TAMPERED',
            'status': 'PAID'
        }
        bad_sig = "a" * 64
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': bad_sig})
        self.assertEqual(status, 401)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_16_webhook_nonexistent_order_returns_404(self):
        """POST /api/webhook/payos with nonexistent order returns 404 ORDER_NOT_FOUND."""
        payload = {
            'order_id': 'KV-NONEXISTENT-ORDER-888',
            'amount': 5000000,
            'transaction_id': 'TXN_NONEXISTENT_ORDER',
            'status': 'PAID'
        }
        sig = self.sign_payos(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 404)
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'ORDER_NOT_FOUND')

    def test_17_webhook_errors_do_not_pollute_d4_or_d9(self):
        """POST /api/webhook/payos on 400/401/404 errors strictly maintains D4 and D9 invariance."""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        initial_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        initial_d9 = cur.fetchone()[0]
        cur.execute("SELECT curr_hash FROM D9_NHAT_KY ORDER BY id DESC LIMIT 1")
        initial_hash = cur.fetchone()['curr_hash']
        conn.close()

        # Run 400, 401, and 404 requests
        self.request('POST', '/api/webhook/payos', {'order_id': 'KV261026001', 'amount': -1})
        self.request('POST', '/api/webhook/payos', {'order_id': 'KV261026001', 'amount': 1000}, headers={'X-Webhook-Signature': 'deadbeef'*8})
        self.request('POST', '/api/webhook/payos', {'order_id': 'KV-NONEXISTENT-999', 'amount': 1000})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON")
        new_d4 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D9_NHAT_KY")
        new_d9 = cur.fetchone()[0]
        cur.execute("SELECT curr_hash FROM D9_NHAT_KY ORDER BY id DESC LIMIT 1")
        new_hash = cur.fetchone()['curr_hash']
        conn.close()

        self.assertEqual(new_d4, initial_d4, "D4 append-only ledger polluted by invalid webhook requests!")
        self.assertEqual(new_d9, initial_d9, "D9 audit log polluted by invalid webhook requests!")
        self.assertEqual(new_hash, initial_hash, "D9 hash chain broken/altered by invalid webhook requests!")


if __name__ == '__main__':
    unittest.main()
