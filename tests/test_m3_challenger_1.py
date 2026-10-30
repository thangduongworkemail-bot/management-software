#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milestone 3 Empirical Challenge Test Harness
Agent: m3_challenger_1 (Empirical Challenger)
Milestone: Milestone 3 (Inventory Ledger, E-Invoice & Webhook Payment Engine)

Stress-testing 4 Core Security & Business Invariants:
1. D4_SO_CAI_TON Append-Only Invariant: Direct UPDATE and DELETE attempts must be aborted by SQLite triggers.
2. Webhook Signature Tampering: Invalid, forged, or altered signatures must return HTTP 401 INVALID_SIGNATURE.
3. Webhook Idempotency & Replay Protection: Duplicate transaction_id replay must return HTTP 200 duplicate: True
   without double credit, without double stock decrement, and without duplicate XUAT ledger entries.
4. Concurrency Stress: High concurrency on inventory receipts, order payments, and mixed load.
"""

import unittest
import urllib.request
import urllib.error
import urllib.parse
import json
import sqlite3
import hashlib
import hmac
import socketserver
import threading
import tempfile
import shutil
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server

WEBHOOK_SECRET = os.environ.get('PAYOS_WEBHOOK_SECRET', 'khanhvan_payos_secret_2026')
SAMPLE_PRODUCT = 'GUONG-HOP-SOI-1800'  # 8,500,000 listed in D1_SAN_PHAM


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class M3ChallengerBase(unittest.TestCase):
    """Base harness managing ephemeral server and database isolation for adversarial testing."""

    httpd = None
    server_thread = None
    server_port = None
    server_url = None
    test_dir = None
    test_db_path = None

    @classmethod
    def setUpClass(cls):
        # Silence server log messages during adversarial runs
        server.KhanhVanServer.log_message = lambda self, format, *args: None

        cls.test_dir = tempfile.mkdtemp(prefix='m3_challenger_')
        cls.test_db_path = os.path.join(cls.test_dir, 'test_m3_khanhvan.db')
        server.DB_FILE = cls.test_db_path

        cls.init_isolated_db()

        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.server_port = cls.httpd.server_address[1]
        cls.server_url = f"http://127.0.0.1:{cls.server_port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait for server readiness
        ready = False
        for _ in range(40):
            try:
                req = urllib.request.Request(f"{cls.server_url}/api/db/stats")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.05)
        if not ready:
            raise RuntimeError(f"Ephemeral test server failed to start on {cls.server_url}")

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if cls.test_dir and os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def init_isolated_db(cls):
        """Build database schema, triggers and seed from server.py."""
        conn = sqlite3.connect(cls.test_db_path)
        cur = conn.cursor()

        tables = [
            'D1_SAN_PHAM', 'D2_BANG_GIA', 'D3_DON_HANG', 'D4_SO_CAI_TON',
            'D5_NHA_CUNG_CAP', 'D6_HOA_DON_DT', 'D7_CONG_NO', 'D8_TAI_KHOAN',
            'D8_THIET_BI', 'D9_NHAT_KY'
        ]
        for t in tables:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("DROP TRIGGER IF EXISTS trg_d4_prevent_update")
        cur.execute("DROP TRIGGER IF EXISTS trg_d4_prevent_delete")
        conn.commit()
        conn.close()

        server.init_db()

    def get_db(self):
        conn = sqlite3.connect(self.test_db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA recursive_triggers = ON")
        return conn

    def request(self, method, path, data=None, headers=None):
        url = f"{self.server_url}{path}"
        body_bytes = None
        req_headers = {'Content-Type': 'application/json'}
        if headers:
            req_headers.update(headers)
        if data is not None:
            body_bytes = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                resp_body = resp.read().decode('utf-8')
                resp_json = json.loads(resp_body) if resp_body else {}
                return resp.status, resp_json, resp.headers
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {'raw': err_body}
            return e.code, err_json, e.headers

    @staticmethod
    def sign_payload(payload, secret=WEBHOOK_SECRET):
        canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        return hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    def compute_d4_hash(self):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien FROM D4_SO_CAI_TON ORDER BY id ASC")
        rows = cur.fetchall()
        conn.close()
        dump = json.dumps([list(r) for r in rows], ensure_ascii=False)
        return hashlib.sha256(dump.encode('utf-8')).hexdigest(), len(rows)


class TestChallenge1_D4AppendOnlyTriggers(M3ChallengerBase):
    """
    Challenge 1: D4_SO_CAI_TON trigger aborts: direct UPDATE and DELETE must fail.
    The ledger must remain completely immutable to in-place edits and row deletions.
    """

    def test_01_direct_update_primary_key_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET id = 9999 WHERE id = 1")
        self.assertIn("Append-only violation", str(ctx.exception))
        conn.close()

    def test_02_direct_update_quantity_bien_dong_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 999 WHERE id = 1")
        self.assertIn("UPDATE is strictly forbidden", str(ctx.exception))
        conn.close()

    def test_03_direct_update_movement_type_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET loai_dong = 'TAMPERED' WHERE id = 1")
        self.assertIn("Append-only violation", str(ctx.exception))
        conn.close()

    def test_04_direct_update_metadata_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET tham_chieu = 'FORGED_REF', nguoi_thuc_hien = 'ATTACKER' WHERE id = 1")
        self.assertIn("UPDATE is strictly forbidden", str(ctx.exception))
        conn.close()

    def test_05_direct_bulk_update_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 0")
        self.assertIn("Append-only violation", str(ctx.exception))
        conn.close()

    def test_06_direct_subquery_update_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = (SELECT COUNT(*) FROM D3_DON_HANG) WHERE id = 1")
        self.assertIn("Append-only violation", str(ctx.exception))
        conn.close()

    def test_07_direct_delete_single_row_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("DELETE FROM D4_SO_CAI_TON WHERE id = 1")
        self.assertIn("DELETE is strictly forbidden", str(ctx.exception))
        conn.close()

    def test_08_direct_delete_bulk_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("DELETE FROM D4_SO_CAI_TON")
        self.assertIn("Append-only violation", str(ctx.exception))
        conn.close()

    def test_09_direct_delete_conditional_aborts(self):
        conn = self.get_db()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("DELETE FROM D4_SO_CAI_TON WHERE bien_dong < 0")
        self.assertIn("DELETE is strictly forbidden", str(ctx.exception))
        conn.close()

    def test_10_table_hash_unmodified_after_all_mutation_attempts(self):
        hash_before, count_before = self.compute_d4_hash()

        conn = self.get_db()
        attacks = [
            "UPDATE D4_SO_CAI_TON SET id = 888 WHERE id = 1",
            "UPDATE D4_SO_CAI_TON SET bien_dong = -500 WHERE id = 2",
            "UPDATE D4_SO_CAI_TON SET loai_dong = 'XOA' WHERE id = 1",
            "DELETE FROM D4_SO_CAI_TON WHERE id = 1",
            "DELETE FROM D4_SO_CAI_TON WHERE id > 0",
            "DELETE FROM D4_SO_CAI_TON"
        ]
        for sql in attacks:
            try:
                conn.execute(sql)
            except sqlite3.IntegrityError:
                pass
        conn.close()

        hash_after, count_after = self.compute_d4_hash()
        self.assertEqual(count_before, count_after, "D4 row count must not change after failed attacks")
        self.assertEqual(hash_before, hash_after, "D4 table SHA-256 hash must remain 100% bit-for-bit identical")


class TestChallenge2_WebhookSignatureTampering(M3ChallengerBase):
    """
    Challenge 2: Webhook signature tampering: invalid signature must return 401 INVALID_SIGNATURE.
    No unauthenticated or altered payloads may affect ledger or payment state.
    """

    def setUp(self):
        # Create a fresh order for tampering tests using seeded variant
        order_payload = {
            "khach_hang": "Adversarial Buyer - 0988776655",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [
                {
                    "ma_bien_the": SAMPLE_PRODUCT,
                    "ten_san_pham": "Gương hộp Gỗ Sồi 1m8",
                    "so_luong": 1,
                    "don_gia": 8500000,
                    "thanh_tien": 8500000
                }
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, resp, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(status, 200, f"Order creation failed: {resp}")
        self.order_id = resp['ma_don']

    def test_01_random_fake_hex_signature_rejected(self):
        payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_FAKE_HEX_01",
            "status": "PAID"
        }
        headers = {'X-Webhook-Signature': 'deadbeef0000111122223333444455556666777788889999aaaabbbbccccdddd'}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_02_wrong_secret_signature_rejected(self):
        payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_WRONG_SECRET_01",
            "status": "PAID"
        }
        wrong_sig = self.sign_payload(payload, secret='completely_wrong_secret_key')
        headers = {'X-Webhook-Signature': wrong_sig}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_03_single_bitflip_in_signature_rejected(self):
        payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_BITFLIP_01",
            "status": "PAID"
        }
        valid_sig = self.sign_payload(payload)
        corrupted_sig = ('0' if valid_sig[0] != '0' else '1') + valid_sig[1:]
        headers = {'X-Webhook-Signature': corrupted_sig}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_04_tampered_payload_amount_after_signing_rejected(self):
        legit_payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_TAMPER_AMT_01",
            "status": "PAID"
        }
        legit_sig = self.sign_payload(legit_payload)

        # Adversary lowers payment amount after signing
        tampered_payload = dict(legit_payload)
        tampered_payload["amount"] = 100000

        headers = {'X-Webhook-Signature': legit_sig}
        status, data, _ = self.request('POST', '/api/webhook/payos', tampered_payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_05_tampered_order_id_after_signing_rejected(self):
        legit_payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_TAMPER_ORD_01",
            "status": "PAID"
        }
        legit_sig = self.sign_payload(legit_payload)

        tampered_payload = dict(legit_payload)
        tampered_payload["order_id"] = "KV999999999"

        headers = {'X-Webhook-Signature': legit_sig}
        status, data, _ = self.request('POST', '/api/webhook/payos', tampered_payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_06_truncated_signature_rejected(self):
        payload = {
            "order_id": self.order_id,
            "amount": 8500000,
            "transaction_id": "TXN_TRUNC_01",
            "status": "PAID"
        }
        valid_sig = self.sign_payload(payload)
        truncated_sig = valid_sig[:32]
        headers = {'X-Webhook-Signature': truncated_sig}
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers)
        self.assertEqual(status, 401)
        self.assertEqual(data.get('error'), 'INVALID_SIGNATURE')

    def test_07_tampered_requests_produce_zero_side_effects(self):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai, tien_da_thu FROM D3_DON_HANG WHERE ma_don = ?", (self.order_id,))
        row = cur.fetchone()
        self.assertEqual(row['trang_thai'], 'GIU_CHO')
        self.assertEqual(row['tien_da_thu'], 0)

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        xuat_count = cur.fetchone()[0]
        self.assertEqual(xuat_count, 0)
        conn.close()


class TestChallenge3_WebhookIdempotencyReplay(M3ChallengerBase):
    """
    Challenge 3: Webhook idempotency duplicate replay:
    Sending duplicate transaction_id must return 200 duplicate: True without double credit or double stock decrement.
    """

    def setUp(self):
        order_payload = {
            "khach_hang": "Idempotency Test Subject - 0911223344",
            "nguoi_lap": "covan@khanhvan.vn",
            "vai_tro_nguoi_lap": "CHU",
            "items": [
                {
                    "ma_bien_the": SAMPLE_PRODUCT,
                    "ten_san_pham": "Gương hộp Gỗ Sồi 1m8",
                    "so_luong": 2,
                    "don_gia": 8500000,
                    "thanh_tien": 17000000
                }
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, resp, _ = self.request('POST', '/api/orders', order_payload)
        self.assertEqual(status, 200, f"Order creation failed: {resp}")
        self.order_id = resp['ma_don']

    def test_01_first_legitimate_payment_succeeds(self):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        prod_before = cur.fetchone()
        ton_before = prod_before['ton_hien_co']
        giu_before = prod_before['dang_giu_cho']
        conn.close()

        txn_id = f"TXN_IDEM_{self.order_id}_01"
        payload = {
            "order_id": self.order_id,
            "amount": 17000000,
            "transaction_id": txn_id,
            "status": "PAID"
        }
        sig = self.sign_payload(payload)
        status, data, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('trang_thai'), 'DA_THANH_TOAN')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        prod_after = cur.fetchone()
        self.assertEqual(prod_after['ton_hien_co'], ton_before - 2)
        self.assertEqual(prod_after['dang_giu_cho'], giu_before - 2)

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    def test_02_sequential_replay_returns_200_duplicate_true(self):
        txn_id = f"TXN_IDEM_{self.order_id}_02"
        payload = {
            "order_id": self.order_id,
            "amount": 17000000,
            "transaction_id": txn_id,
            "status": "PAID"
        }
        sig = self.sign_payload(payload)

        # 1st execution
        status1, data1, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status1, 200)
        self.assertFalse(data1.get('duplicate', False))

        # Snapshot after 1st execution
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = ?", (self.order_id,))
        order_row1 = cur.fetchone()
        da_thu_1 = order_row1['tien_da_thu']

        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        prod_row1 = cur.fetchone()
        ton_1 = prod_row1['ton_hien_co']

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        xuat_count1 = cur.fetchone()[0]
        conn.close()

        # 2nd execution: Exact duplicate replay
        status2, data2, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
        self.assertEqual(status2, 200)
        self.assertTrue(data2.get('success'))
        self.assertTrue(data2.get('duplicate'))
        self.assertIn("đã được xử lý trước đó", data2.get('message', ''))

        # Verify zero side effects on replay
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = ?", (self.order_id,))
        order_row2 = cur.fetchone()
        self.assertEqual(order_row2['tien_da_thu'], da_thu_1, "tien_da_thu MUST NOT double-credit on replay")

        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        prod_row2 = cur.fetchone()
        self.assertEqual(prod_row2['ton_hien_co'], ton_1, "ton_hien_co MUST NOT double-decrement on replay")

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        self.assertEqual(cur.fetchone()[0], xuat_count1, "D4_SO_CAI_TON MUST NOT append extra XUAT rows on replay")
        conn.close()

    def test_03_replay_with_tampered_amount_caught_by_txn_id(self):
        txn_id = f"TXN_IDEM_{self.order_id}_03"
        payload1 = {
            "order_id": self.order_id,
            "amount": 17000000,
            "transaction_id": txn_id,
            "status": "PAID"
        }
        sig1 = self.sign_payload(payload1)
        self.request('POST', '/api/webhook/payos', payload1, headers={'X-Webhook-Signature': sig1})

        # Replay with same transaction_id but modified amount
        payload2 = {
            "order_id": self.order_id,
            "amount": 20000000,
            "transaction_id": txn_id,
            "status": "PAID"
        }
        sig2 = self.sign_payload(payload2)
        status2, data2, _ = self.request('POST', '/api/webhook/payos', payload2, headers={'X-Webhook-Signature': sig2})
        self.assertEqual(status2, 200)
        self.assertTrue(data2.get('duplicate'))

        # Verify tien_da_thu was not altered
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT tien_da_thu FROM D3_DON_HANG WHERE ma_don = ?", (self.order_id,))
        self.assertEqual(cur.fetchone()['tien_da_thu'], 17000000)
        conn.close()

    def test_04_rapid_burst_concurrent_replays(self):
        txn_id = f"TXN_BURST_{self.order_id}_04"
        payload = {
            "order_id": self.order_id,
            "amount": 17000000,
            "transaction_id": txn_id,
            "status": "PAID"
        }
        sig = self.sign_payload(payload)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        xuat_before = cur.fetchone()[0]
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        stock_before = cur.fetchone()['ton_hien_co']
        conn.close()

        def send_duplicate():
            return self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        burst_size = 12
        responses = []
        with ThreadPoolExecutor(max_workers=burst_size) as executor:
            futures = [executor.submit(send_duplicate) for _ in range(burst_size)]
            for fut in as_completed(futures):
                responses.append(fut.result())

        for code, data, _ in responses:
            self.assertEqual(code, 200)
            self.assertTrue(data.get('success'))

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{self.order_id}%",))
        xuat_after = cur.fetchone()[0]
        self.assertIn(xuat_after - xuat_before, (0, 1), "Concurrent burst must result in at most 1 XUAT entry")

        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (SAMPLE_PRODUCT,))
        stock_after = cur.fetchone()['ton_hien_co']
        delta_stock = stock_before - stock_after
        self.assertIn(delta_stock, (0, 2), "Stock decrement must be exactly 0 or 2, never multiplied")
        conn.close()


class TestChallenge4_ConcurrencyStress(M3ChallengerBase):
    """
    Challenge 4: Concurrency test on inventory receipts and payments.
    Stress-test high volume of concurrent workshop receipts, concurrent payments, and mixed traffic.
    """

    def test_01_high_concurrency_inventory_receipts(self):
        """20 concurrent threads submitting workshop receipts for the same product variant."""
        item_code = SAMPLE_PRODUCT
        num_workers = 20
        qty_per_receipt = 3

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item_code,))
        initial_stock = cur.fetchone()['ton_hien_co']
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE loai_dong = 'NHAP'")
        initial_nhap_count = cur.fetchone()[0]
        conn.close()

        def submit_receipt(idx):
            payload = {
                "item": item_code,
                "qty": qty_per_receipt,
                "cost": 5000000,
                "workshop": "Xưởng Hải Hậu",
                "ref": f"PN_CONC_{idx}_{int(time.time()*1000)}",
                "actor": f"Thợ Test {idx}"
            }
            return self.request('POST', '/api/inventory/receipt', payload)

        results = []
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(submit_receipt, i) for i in range(num_workers)]
            for fut in as_completed(futures):
                results.append(fut.result())

        for status, data, _ in results:
            self.assertEqual(status, 200, f"Receipt failed: {data}")
            self.assertTrue(data.get('success'))

        expected_total_added = num_workers * qty_per_receipt

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item_code,))
        final_stock = cur.fetchone()['ton_hien_co']
        self.assertEqual(final_stock, initial_stock + expected_total_added,
                         f"Final stock {final_stock} must equal initial {initial_stock} + {expected_total_added}")

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE loai_dong = 'NHAP'")
        final_nhap_count = cur.fetchone()[0]
        self.assertEqual(final_nhap_count, initial_nhap_count + num_workers,
                         f"D4 ledger must have exactly {num_workers} new NHAP rows")
        conn.close()

    def test_02_concurrent_webhook_payments_on_distinct_orders(self):
        """Create 8 separate orders and pay all 8 concurrently in parallel threads."""
        num_orders = 8
        order_ids = []

        # Create orders
        for i in range(num_orders):
            payload = {
                "khach_hang": f"Concurrent Customer {i} - 090000000{i}",
                "nguoi_lap": "covan@khanhvan.vn",
                "vai_tro_nguoi_lap": "CHU",
                "items": [
                    {
                        "ma_bien_the": SAMPLE_PRODUCT,
                        "ten_san_pham": "Gương hộp Gỗ Sồi 1m8",
                        "so_luong": 1,
                        "don_gia": 8500000,
                        "thanh_tien": 8500000
                    }
                ],
                "hinh_thuc_tt": "VIETQR"
            }
            status, resp, _ = self.request('POST', '/api/orders', payload)
            self.assertEqual(status, 200, f"Failed to create order {i}: {resp}")
            order_ids.append(resp['ma_don'])

        def pay_order(oid):
            txn_id = f"TXN_CONC_PAY_{oid}"
            p = {
                "order_id": oid,
                "amount": 8500000,
                "transaction_id": txn_id,
                "status": "PAID"
            }
            sig = self.sign_payload(p)
            return self.request('POST', '/api/webhook/payos', p, headers={'X-Webhook-Signature': sig})

        pay_results = []
        with ThreadPoolExecutor(max_workers=num_orders) as executor:
            futures = [executor.submit(pay_order, oid) for oid in order_ids]
            for fut in as_completed(futures):
                pay_results.append(fut.result())

        for status, data, _ in pay_results:
            self.assertEqual(status, 200)
            self.assertTrue(data.get('success'))
            self.assertEqual(data.get('trang_thai'), 'DA_THANH_TOAN')

        conn = self.get_db()
        cur = conn.cursor()
        for oid in order_ids:
            cur.execute("SELECT trang_thai, tien_da_thu, con_phai_thu FROM D3_DON_HANG WHERE ma_don = ?", (oid,))
            row = cur.fetchone()
            self.assertEqual(row['trang_thai'], 'DA_THANH_TOAN')
            self.assertEqual(row['tien_da_thu'], 8500000)
            self.assertEqual(row['con_phai_thu'], 0)
        conn.close()

    def test_03_mixed_concurrent_receipts_and_payments_stress(self):
        """
        Mixed stress workload:
        8 threads performing inventory receipts (+1 qty each = +8)
        8 threads paying distinct orders (-1 qty each = -8)
        Net delta must be exactly 0, and ledger must contain all 8 NHAP + 8 XUAT entries.
        """
        item_code = SAMPLE_PRODUCT
        num_tasks = 8

        order_ids = []
        for i in range(num_tasks):
            p = {
                "khach_hang": f"Mixed Customer {i} - 093333333{i}",
                "nguoi_lap": "covan@khanhvan.vn",
                "vai_tro_nguoi_lap": "CHU",
                "items": [
                    {
                        "ma_bien_the": item_code,
                        "ten_san_pham": "Gương hộp Gỗ Sồi 1m8",
                        "so_luong": 1,
                        "don_gia": 8500000,
                        "thanh_tien": 8500000
                    }
                ],
                "hinh_thuc_tt": "VIETQR"
            }
            status, resp, _ = self.request('POST', '/api/orders', p)
            self.assertEqual(status, 200, f"Failed creating order: {resp}")
            order_ids.append(resp['ma_don'])

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item_code,))
        baseline_stock = cur.fetchone()['ton_hien_co']
        conn.close()

        def do_receipt(i):
            payload = {
                "item": item_code,
                "qty": 1,
                "cost": 5000000,
                "workshop": "Xưởng Thạch Thất",
                "ref": f"PN_MIX_{i}_{int(time.time()*1000)}",
                "actor": f"Thợ Kho {i}"
            }
            return ('receipt', self.request('POST', '/api/inventory/receipt', payload))

        def do_payment(oid):
            p = {
                "order_id": oid,
                "amount": 8500000,
                "transaction_id": f"TXN_MIX_{oid}",
                "status": "PAID"
            }
            sig = self.sign_payload(p)
            return ('payment', self.request('POST', '/api/webhook/payos', p, headers={'X-Webhook-Signature': sig}))

        all_futures = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            for i in range(num_tasks):
                all_futures.append(executor.submit(do_receipt, i))
                all_futures.append(executor.submit(do_payment, order_ids[i]))

            results = [f.result() for f in as_completed(all_futures)]

        for action_type, (code, data, _) in results:
            self.assertEqual(code, 200, f"Action {action_type} failed with {code}: {data}")
            self.assertTrue(data.get('success'))

        # Verify net inventory arithmetic
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item_code,))
        final_stock = cur.fetchone()['ton_hien_co']
        self.assertEqual(final_stock, baseline_stock,
                         f"Net stock must be completely preserved (+8 receipts - 8 payments). Baseline: {baseline_stock}, Final: {final_stock}")

        # Verify ledger row count: exactly 8 new NHAP and 8 new XUAT
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE 'Lô #PN_MIX_%' AND loai_dong = 'NHAP'")
        nhap_count = cur.fetchone()[0]
        self.assertEqual(nhap_count, num_tasks)

        for oid in order_ids:
            cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{oid}%",))
            self.assertEqual(cur.fetchone()[0], 1)

        conn.close()

    def test_04_audit_chain_integrity_after_concurrent_stress(self):
        """Verify that D9_NHAT_KY SHA-256 hash chain remains 100% unbroken after all concurrency tests."""
        status, data, _ = self.request('POST', '/api/audit/verify')
        self.assertEqual(status, 200)
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('valid'), "D9 hash chain must be 100% valid with zero broken links")
        self.assertTrue(data.get('unbroken_chain'), "D9 unbroken_chain attribute must be True")
        self.assertTrue(data.get('genesis_valid'), "D9 genesis block must be valid")


if __name__ == '__main__':
    print("=" * 80)
    print("RUNNING EMPIRICAL CHALLENGER SUITE: MILESTONE 3")
    print("Author: m3_challenger_1 | Target: D4 Triggers, Webhook HMAC, Idempotency, Concurrency")
    print("=" * 80)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestChallenge1_D4AppendOnlyTriggers))
    suite.addTests(loader.loadTestsFromTestCase(TestChallenge2_WebhookSignatureTampering))
    suite.addTests(loader.loadTestsFromTestCase(TestChallenge3_WebhookIdempotencyReplay))
    suite.addTests(loader.loadTestsFromTestCase(TestChallenge4_ConcurrencyStress))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    sys.exit(0 if result.wasSuccessful() else 1)
