#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_m3_r3_stress_and_probe.py
Milestone 3 Round 3 Empirical Challenger Stress Suite
Agent: m3_r3_challenger_1
"""

import sys
import os
import json
import sqlite3
import threading
import tempfile
import shutil
import time
from datetime import datetime, timedelta
import hmac
import hashlib
import urllib.request
import urllib.error
import socketserver
import unittest

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 120

class M3R3StressAndProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None
        cls.temp_dir = tempfile.mkdtemp(prefix="m3_r3_stress_")
        cls.db_path = os.path.join(cls.temp_dir, "test_khanhvan.db")
        server.DB_FILE = cls.db_path

        server.init_db()

        cls.httpd = ThreadedTCPServer(("127.0.0.1", 0), server.KhanhVanServer)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

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

    def seed_product(self, prod_code, initial_stock=50):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, ?, 'giuong', 'Xưởng Thạch Thất', 5000000, 7000000, 8500000, ?, 0)
        ''', (prod_code, f"Sản phẩm Test {prod_code}", initial_stock))
        conn.commit()
        conn.close()

    def create_order(self, customer_name, prod_code, qty=1, price=8500000):
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
    # Test 1: 25-Thread Thundering Herd Webhook Replay
    # =========================================================================
    def test_01_thundering_herd_webhook_25_threads(self):
        """Stress test: 25 concurrent threads hit /api/webhook/payos simultaneously with same transaction_id."""
        prod = "R3-HERD-25"
        self.seed_product(prod, 30)
        ma_don = self.create_order("Herd 25 Test", prod, 1, 8500000)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        start_stock = cur.fetchone()['ton_hien_co']
        conn.close()

        txn_id = f"TXN_HERD25_{int(time.time()*1000)}"
        payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": txn_id}
        sig = self.sign_payos(payload)

        num_threads = 25
        barrier = threading.Barrier(num_threads)
        results = []

        def worker():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
            results.append((s, d))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 25)
        self.assertTrue(all(s == 200 for s, _ in results))

        initials = [d for s, d in results if not d.get('duplicate')]
        duplicates = [d for s, d in results if d.get('duplicate')]

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_cnt = cur.fetchone()[0]
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        end_stock = cur.fetchone()['ton_hien_co']
        conn.close()

        self.assertEqual(len(initials), 1, f"Expected 1 initial hit, got {len(initials)}")
        self.assertEqual(len(duplicates), 24, f"Expected 24 duplicates, got {len(duplicates)}")
        self.assertEqual(xuat_cnt, 1, f"Expected 1 XUAT in D4, got {xuat_cnt}")
        self.assertEqual(end_stock, start_stock - 1, f"Expected stock decrement by 1, got {end_stock}")

    # =========================================================================
    # Test 2: 20-Thread Concurrent Confirm-Payment Burst
    # =========================================================================
    def test_02_concurrent_confirm_payment_burst_20_threads(self):
        """Stress test: 20 concurrent threads hit /api/orders/confirm-payment simultaneously."""
        prod = "R3-BURST-20"
        self.seed_product(prod, 25)
        ma_don = self.create_order("Burst 20 Test", prod, 1, 8500000)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        start_stock = cur.fetchone()['ton_hien_co']
        conn.close()

        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results = []

        def worker():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
            results.append((s, d))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 20)
        self.assertTrue(all(s == 200 for s, _ in results))

        initials = [d for s, d in results if not d.get('duplicate')]
        duplicates = [d for s, d in results if d.get('duplicate')]

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu = ? AND loai_dong = 'XUAT'", (f"Đơn #{ma_don}",))
        xuat_cnt = cur.fetchone()[0]
        cur.execute("SELECT ton_hien_co FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        end_stock = cur.fetchone()['ton_hien_co']
        conn.close()

        self.assertEqual(len(initials), 1, f"Expected 1 initial confirmation, got {len(initials)}")
        self.assertEqual(len(duplicates), 19, f"Expected 19 duplicate responses, got {len(duplicates)}")
        self.assertEqual(xuat_cnt, 1, f"Expected 1 XUAT in D4, got {xuat_cnt}")
        self.assertEqual(end_stock, start_stock - 1, f"Expected stock decrement by 1, got {end_stock}")

    # =========================================================================
    # Test 3: Confirm-Payment Rejection on Cancelled Order (DA_HUY)
    # =========================================================================
    def test_03_confirm_payment_rejection_on_cancelled_order(self):
        """Verify confirm-payment is strictly rejected (400) on DA_HUY orders."""
        prod = "R3-REJECT-CANCEL"
        self.seed_product(prod, 20)

        ma_don = self.create_order("Cancel Manual", prod, 1, 8500000)
        s_c, d_c, _ = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don, 'ly_do': 'Khách đổi ý'})
        self.assertEqual(s_c, 200)

        s_p, d_p, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
        self.assertEqual(s_p, 400, f"Expected 400 for DA_HUY, got {s_p}: {d_p}")
        self.assertEqual(d_p.get('error'), 'CANNOT_PAY_CANCELLED_ORDER')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{ma_don}%",))
        self.assertEqual(cur.fetchone()[0], 0, "No XUAT should be inserted on cancelled order payment attempt")
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        stk = dict(cur.fetchone())
        conn.close()

        self.assertEqual(stk['ton_hien_co'], 20)
        self.assertEqual(stk['dang_giu_cho'], 0)

    # =========================================================================
    # Test 4: Confirm-Payment Rejection on Expired Order (DA_HUY_HET_HAN)
    # =========================================================================
    def test_04_confirm_payment_rejection_on_expired_order(self):
        """Verify confirm-payment is strictly rejected (400) on DA_HUY_HET_HAN orders."""
        prod = "R3-REJECT-EXPIRED"
        self.seed_product(prod, 20)

        ma_don = self.create_order("Cancel Expired", prod, 1, 8500000)

        # Backdate order creation to 35 minutes ago
        past_time = (datetime.now() - timedelta(minutes=35)).strftime('%d/%m/%Y %H:%M')
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE D3_DON_HANG SET ngay_tao = ? WHERE ma_don = ?", (past_time, ma_don))
        conn.commit()
        conn.close()

        # Run daemon release function
        server.release_expired_holds()

        # Verify order transitioned to DA_HUY_HET_HAN and hold released
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        st = cur.fetchone()['trang_thai']
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        stk = dict(cur.fetchone())
        conn.close()

        self.assertEqual(st, 'DA_HUY_HET_HAN')
        self.assertEqual(stk['ton_hien_co'], 20)
        self.assertEqual(stk['dang_giu_cho'], 0)

        # Attempt confirm-payment on DA_HUY_HET_HAN
        s_p, d_p, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
        self.assertEqual(s_p, 400, f"Expected 400 for DA_HUY_HET_HAN, got {s_p}: {d_p}")
        self.assertEqual(d_p.get('error'), 'CANNOT_PAY_CANCELLED_ORDER')

    # =========================================================================
    # Test 5: Probe Webhook on Cancelled Order (Empirical Observation)
    # =========================================================================
    def test_05_probe_webhook_on_cancelled_order(self):
        """
        Adversarial Probe: What happens when /api/webhook/payos arrives for a DA_HUY order?
        Expected robust behavior: Reject or do not decrement inventory on cancelled order.
        Current implementation: Does not check order status, resurrects order to DA_THANH_TOAN and decrements stock!
        """
        prod = "R3-WH-CANCEL"
        self.seed_product(prod, 20)
        ma_don = self.create_order("WH Cancel Test", prod, 1, 8500000)

        # Cancel order
        s_c, _, _ = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don, 'ly_do': 'Khách đổi ý'})
        self.assertEqual(s_c, 200)

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        stock_after_cancel = dict(cur.fetchone())
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        status_after_cancel = cur.fetchone()['trang_thai']
        conn.close()
        self.assertEqual(status_after_cancel, 'DA_HUY')
        self.assertEqual(stock_after_cancel['ton_hien_co'], 20)
        self.assertEqual(stock_after_cancel['dang_giu_cho'], 0)

        txn_id = f"TXN_WH_CANCEL_{int(time.time()*1000)}"
        payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": txn_id}
        sig = self.sign_payos(payload)

        s_wh, d_wh, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        status_after_wh = cur.fetchone()['trang_thai']
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        stock_after_wh = dict(cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{ma_don}%",))
        xuat_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        nha_cnt = cur.fetchone()[0]
        conn.close()

        # Record empirical observation
        print(f"\n[EMPIRICAL PROBE 5] Webhook on Cancelled Order:")
        print(f"  HTTP Status: {s_wh}")
        print(f"  Response: {d_wh}")
        print(f"  Status before webhook: {status_after_cancel} -> after webhook: {status_after_wh}")
        print(f"  Stock before webhook: {stock_after_cancel} -> after webhook: {stock_after_wh}")
        print(f"  Ledger D4 entries: NHA_CHO={nha_cnt}, XUAT={xuat_cnt}")

    # =========================================================================
    # Test 6: Probe Race Condition between Cancel and Confirm-Payment
    # =========================================================================
    def test_06_probe_race_cancel_vs_confirm_payment(self):
        """
        Adversarial Probe: Race between /api/orders/cancel and /api/orders/confirm-payment.
        Because /api/orders/cancel lacks _order_lock synchronization, concurrent requests can both succeed (200).
        """
        prod = "R3-RACE-PAY-CAN"
        self.seed_product(prod, 20)
        ma_don = self.create_order("Race Pay Can", prod, 1, 8500000)

        barrier = threading.Barrier(2)
        results = {}

        def do_pay():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/orders/confirm-payment', {'order_id': ma_don, 'amount': 8500000})
            results['pay'] = (s, d)

        def do_can():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don, 'ly_do': 'Khách đổi ý'})
            results['can'] = (s, d)

        t1 = threading.Thread(target=do_pay)
        t2 = threading.Thread(target=do_can)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        pay_status, pay_data = results['pay']
        can_status, can_data = results['can']

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        final_status = cur.fetchone()['trang_thai']
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        final_stock = dict(cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{ma_don}%",))
        xuat_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        nha_cnt = cur.fetchone()[0]
        conn.close()

        print(f"\n[EMPIRICAL PROBE 6] Race Cancel vs Confirm-Payment:")
        print(f"  Confirm-Payment HTTP Status: {pay_status}, Response: {pay_data}")
        print(f"  Cancel HTTP Status: {can_status}, Response: {can_data}")
        print(f"  Final Order Status: {final_status}")
        print(f"  Final Stock: {final_stock}")
        print(f"  Ledger D4 entries: NHA_CHO={nha_cnt}, XUAT={xuat_cnt}")

    # =========================================================================
    # Test 7: Probe Race Condition between Cancel and Webhook
    # =========================================================================
    def test_07_probe_race_cancel_vs_webhook(self):
        """
        Adversarial Probe: Race between /api/orders/cancel and /api/webhook/payos.
        Because /api/orders/cancel lacks _order_lock synchronization, concurrent cancel + webhook can race.
        """
        prod = "R3-RACE-WH-CAN"
        self.seed_product(prod, 20)
        ma_don = self.create_order("Race WH Can", prod, 1, 8500000)

        txn_id = f"TXN_RACE_WH_CAN_{int(time.time()*1000)}"
        payload = {"order_id": ma_don, "amount": 8500000, "transaction_id": txn_id}
        sig = self.sign_payos(payload)

        barrier = threading.Barrier(2)
        results = {}

        def do_wh():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/webhook/payos', payload, headers={'X-Webhook-Signature': sig})
            results['wh'] = (s, d)

        def do_can():
            barrier.wait()
            s, d, _ = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don, 'ly_do': 'Khách đổi ý'})
            results['can'] = (s, d)

        t1 = threading.Thread(target=do_wh)
        t2 = threading.Thread(target=do_can)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        wh_status, wh_data = results['wh']
        can_status, can_data = results['can']

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (ma_don,))
        final_status = cur.fetchone()['trang_thai']
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod,))
        final_stock = dict(cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'XUAT'", (f"%{ma_don}%",))
        xuat_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        nha_cnt = cur.fetchone()[0]
        conn.close()

        print(f"\n[EMPIRICAL PROBE 7] Race Cancel vs Webhook:")
        print(f"  Webhook HTTP Status: {wh_status}, Response: {wh_data}")
        print(f"  Cancel HTTP Status: {can_status}, Response: {can_data}")
        print(f"  Final Order Status: {final_status}")
        print(f"  Final Stock: {final_stock}")
        print(f"  Ledger D4 entries: NHA_CHO={nha_cnt}, XUAT={xuat_cnt}")

if __name__ == '__main__':
    unittest.main()
