#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial Probe for Milestone 3 Remediation:
Stress tests edge cases, injections, boundaries for:
- GET /api/invoices/export
- POST /api/orders/confirm-payment
"""

import unittest
import sqlite3
import shutil
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class MockServerHandler:
    def __init__(self):
        self.status = 200
        self.data = None
        self.headers = {}
        self.wfile_bytes = b''
        class WFile:
            def __init__(self, parent):
                self.parent = parent
            def write(self, b):
                self.parent.wfile_bytes += b
        self.wfile = WFile(self)

    def send_json(self, d, status=200):
        self.status = status
        self.data = d

    def send_response(self, s):
        self.status = s

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass


class AdversarialProbeM3R2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix='m3_adv_probe_')
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_khanhvan.db')
        shutil.copy2('khanhvan.db', cls.test_db_path)
        server.DB_FILE = cls.test_db_path

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.handler = MockServerHandler()

    def test_adv_payment_invalid_amounts(self):
        """Adversarial amounts: 0, negative, strings, None, floats."""
        bad_amounts = [0, -1, -999999999, "0", "-500", "invalid", None, "", 1e-9]
        for amt in bad_amounts:
            handler = MockServerHandler()
            server.KhanhVanServer.handle_api_post(
                handler, '/api/orders/confirm-payment',
                {'order_id': 'KV261026001', 'amount': amt}
            )
            self.assertEqual(handler.status, 400, f"Expected 400 for amount {amt}, got {handler.status}")
            self.assertEqual(handler.data.get('error'), 'INVALID_AMOUNT')

    def test_adv_payment_nonexistent_order_ids(self):
        """Adversarial order IDs: blank, spaces, sql injection, non-existent strings."""
        bad_order_ids = ['', '   ', None, "' OR '1'='1", "KV-DOES-NOT-EXIST", "DROP TABLE D3_DON_HANG;"]
        for oid in bad_order_ids:
            handler = MockServerHandler()
            server.KhanhVanServer.handle_api_post(
                handler, '/api/orders/confirm-payment',
                {'order_id': oid, 'amount': 1000000}
            )
            self.assertEqual(handler.status, 404, f"Expected 404 for order_id {oid!r}, got {handler.status}")
            self.assertEqual(handler.data.get('error'), 'ORDER_NOT_FOUND')

    def test_adv_export_missing_order_ids(self):
        """Adversarial GET /api/invoices/export parameter validation."""
        bad_params = [
            {},
            {'order_id': ['']},
            {'order_id': ['   ']},
            {'ma_don': ['']},
        ]
        for p in bad_params:
            handler = MockServerHandler()
            server.KhanhVanServer.handle_api_get(handler, '/api/invoices/export', p)
            self.assertEqual(handler.status, 400, f"Expected 400 for params {p}, got {handler.status}")
            self.assertEqual(handler.data.get('error'), 'MISSING_ORDER_ID')

    def test_adv_export_nonexistent_order_ids(self):
        """Adversarial GET /api/invoices/export nonexistent orders."""
        bad_oids = ['KV-UNKNOWN-999', "' OR 1=1 --", "<script>alert(1)</script>"]
        for oid in bad_oids:
            handler = MockServerHandler()
            server.KhanhVanServer.handle_api_get(handler, '/api/invoices/export', {'order_id': [oid]})
            self.assertEqual(handler.status, 404, f"Expected 404 for order_id {oid!r}, got {handler.status}")
            self.assertEqual(handler.data.get('error'), 'INVOICE_NOT_FOUND')

    def test_adv_export_format_case_insensitive(self):
        """Verify format parameter is case-insensitive and trims whitespace."""
        for fmt in ['xml', 'XML', '  xml  ', 'Xml']:
            handler = MockServerHandler()
            server.KhanhVanServer.handle_api_get(
                handler, '/api/invoices/export',
                {'order_id': ['KV261026001'], 'format': [fmt]}
            )
            self.assertEqual(handler.status, 200, f"Expected 200 for format {fmt}, got {handler.status}")
            self.assertIn('application/xml', handler.headers.get('Content-Type', ''))
            self.assertTrue(len(handler.wfile_bytes) > 0)


if __name__ == '__main__':
    unittest.main()
