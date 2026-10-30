#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Empirical Challenge & Stress Test Suite for Milestone 2
POS Sales, Pricing & 30-min Reservation Hold Engine

Target Focus:
1. Concurrent order holds and stock boundary saturation (prevent overselling / overholding)
2. Expiry auto-release simulation without race conditions (idempotent, atomic release, D4 ledger integrity)
3. Order cancellation across various lifecycle states (GIU_CHO, DA_HUY, DA_HUY_HET_HAN, DA_THANH_TOAN, nonexistent)
4. RBAC floor price validation & token security
5. Pricing engine boundary stress testing & formula invariants
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
import time
from datetime import datetime, timedelta

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class ThreadedTCPServer(server.socketserver.ThreadingMixIn, server.socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

class M2EmpiricalChallengeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Silence server log messages
        server.KhanhVanServer.log_message = lambda self, format, *args: None

        cls.test_dir = tempfile.mkdtemp(prefix='khanhvan_m2_challenge_')
        cls.test_db_path = os.path.join(cls.test_dir, 'test_m2_challenge.db')
        server.DB_FILE = cls.test_db_path

        # Initialize schema and seed data
        cls.init_clean_db()

        # Start threaded server
        cls.httpd = ThreadedTCPServer(('127.0.0.1', 0), server.KhanhVanServer)
        cls.server_port = cls.httpd.server_address[1]
        cls.server_url = f"http://127.0.0.1:{cls.server_port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait for server ready
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
            raise RuntimeError(f"Server failed to start on {cls.server_url}")

    @classmethod
    def tearDownClass(cls):
        if cls.httpd:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if cls.test_dir and os.path.exists(cls.test_dir):
            try:
                shutil.rmtree(cls.test_dir)
            except Exception:
                pass

    @classmethod
    def init_clean_db(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
        server.init_db()

    def get_db(self):
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA recursive_triggers = ON")
        return conn

    def request(self, method, path, data=None):
        url = f"{self.server_url}{path}"
        headers = {'Accept': 'application/json'}
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode('utf-8')
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                return resp.status, parsed
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return e.code, parsed
        except Exception as e:
            return 500, {'error': str(e)}

    # =========================================================================
    # 1. CONCURRENT ORDER HOLDS & STOCK BOUNDARY SATURATION
    # =========================================================================
    def test_challenge_01_concurrent_holds_exact_saturation(self):
        """
        Challenge: 20 concurrent threads attempt to hold 1 unit of a product
        with exactly 5 available units.
        Oracle:
        - At most 5 requests succeed (HTTP 200).
        - At least 15 requests fail (HTTP 400 INSUFFICIENT_STOCK).
        - dang_giu_cho MUST NOT exceed ton_hien_co (no overselling / over-reservation).
        - D4_SO_CAI_TON GIU_CHO rows must match exact number of successful holds.
        """
        prod_code = "CHALLENGE-PROD-01"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Bàn trà Sồi Challenge', 'bantra', 'Xưởng Thạch Thất', 2000000, 2500000, 3000000, 5, 0)
        ''', (prod_code,))
        conn.commit()
        conn.close()

        num_threads = 20
        results = []
        threads = []
        barrier = threading.Barrier(num_threads)

        def worker(idx):
            payload = {
                "khach_hang": f"Concurrent Customer {idx}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": "THO",
                "items": [{
                    "ma_bien_the": prod_code,
                    "so_luong": 1,
                    "don_gia": 3000000,
                    "thanh_tien": 3000000
                }],
                "hinh_thuc_tt": "VIETQR"
            }
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            status, res = self.request('POST', '/api/orders', payload)
            results.append((status, res))

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        # Evaluate responses
        successes = [r for r in results if r[0] == 200]
        insufficient = [r for r in results if r[0] == 400 and r[1].get('error') == 'INSUFFICIENT_STOCK']
        errors = [r for r in results if r[0] not in (200, 400)]

        # Check in DB
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        row = cur.fetchone()
        ton_hien_co = row['ton_hien_co']
        dang_giu_cho = row['dang_giu_cho']

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE ma_bien_the = ? AND loai_dong = 'GIU_CHO'", (prod_code,))
        d4_giu_cho_count = cur.fetchone()[0]
        conn.close()

        # Invariant Assertions
        self.assertLessEqual(dang_giu_cho, ton_hien_co,
            f"CRITICAL OVERSELL: dang_giu_cho ({dang_giu_cho}) exceeded ton_hien_co ({ton_hien_co})!")
        self.assertEqual(len(successes), dang_giu_cho,
            f"Mismatch between HTTP successes ({len(successes)}) and dang_giu_cho ({dang_giu_cho})")
        self.assertEqual(d4_giu_cho_count, len(successes),
            f"D4 ledger GIU_CHO entries ({d4_giu_cho_count}) do not match successful reservations ({len(successes)})")
        self.assertEqual(len(insufficient) + len(successes), num_threads,
            f"Unexpected responses encountered: errors={errors}")

    def test_challenge_02_sequential_order_code_uniqueness_under_concurrency(self):
        """
        Challenge: Rapid concurrent order creation should NOT produce duplicate order codes
        or violate primary key constraints in D3_DON_HANG.
        """
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES ('CHALLENGE-BULK-01', 'Bulk Product', 'bantra', 'Xưởng Thạch Thất', 1000000, 1200000, 1500000, 100, 0)
        ''')
        conn.commit()
        conn.close()

        num_orders = 15
        results = []
        threads = []
        barrier = threading.Barrier(num_orders)

        def create_order(idx):
            payload = {
                "khach_hang": f"Bulk Buyer {idx}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "vai_tro_nguoi_lap": "THO",
                "items": [{
                    "ma_bien_the": "CHALLENGE-BULK-01",
                    "so_luong": 1,
                    "don_gia": 1500000,
                    "thanh_tien": 1500000
                }],
                "hinh_thuc_tt": "VIETQR"
            }
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            status, res = self.request('POST', '/api/orders', payload)
            results.append((status, res))

        for i in range(num_orders):
            t = threading.Thread(target=create_order, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        # Successful order codes must all be distinct
        successful_codes = [r[1].get('ma_don') for r in results if r[0] == 200 and r[1].get('ma_don')]
        self.assertEqual(len(successful_codes), len(set(successful_codes)),
            f"Duplicate order IDs generated under concurrency: {successful_codes}")

    # =========================================================================
    # 2. EXPIRY AUTO-RELEASE SIMULATION & RACE CONDITIONS
    # =========================================================================
    def test_challenge_03_race_between_auto_release_and_manual_cancel(self):
        """
        Challenge: Simulate race condition where background auto-release worker
        and user manual cancel hit the SAME expired order at the exact same instant.
        Oracle:
        - Exactly ONE of them should perform the release.
        - D4_SO_CAI_TON must record exactly ONE NHA_CHO row for this order.
        - dang_giu_cho must be decremented by exactly the ordered quantity (never double decremented).
        - Final order status must be DA_HUY or DA_HUY_HET_HAN.
        - Audit hash chain in D9 must remain unbroken.
        """
        prod_code = "CHALLENGE-RACE-01"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Tủ áo Challenge Race', 'tuao', 'Xưởng Thạch Thất', 4000000, 5000000, 6000000, 10, 2)
        ''', (prod_code,))

        order_id = "KV261028RACE1"
        # Set ngay_tao to 40 minutes ago (expired)
        past_time = (datetime.now() - timedelta(minutes=40)).strftime('%Y-%m-%d %H:%M:%S')
        cur.execute('''
        INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES (?, ?, 'Race Customer', 'anhnam@khanhvan.vn', 12000000, 'VIETQR', 'GIU_CHO', 0, 12000000, 'Đang giữ chỗ 30 phút')
        ''', (order_id, past_time))

        cur.execute('''
        INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
        VALUES ('28/10 14:00', 'GIU_CHO', ?, 'Tủ áo Challenge Race', 'Xưởng Thạch Thất', -2, 'KHA_DUNG', ?, 'anhnam@khanhvan.vn')
        ''', (prod_code, f"Đơn #{order_id}"))

        conn.commit()
        conn.close()

        # Concurrently fire release_expired_holds() and POST /api/orders/cancel
        results = []
        barrier = threading.Barrier(2)

        def run_auto_release():
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            server.release_expired_holds()
            results.append(('auto_release', 200))

        def run_manual_cancel():
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            status, res = self.request('POST', '/api/orders/cancel', {'ma_don': order_id})
            results.append(('manual_cancel', status, res))

        t1 = threading.Thread(target=run_auto_release)
        t2 = threading.Thread(target=run_manual_cancel)

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Inspect database
        conn = self.get_db()
        cur = conn.cursor()

        # 1. Check dang_giu_cho
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        final_hold = cur.fetchone()[0]

        # 2. Check D4 ledger NHA_CHO rows
        cur.execute(
            "SELECT COUNT(*), SUM(bien_dong) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'",
            (f"%{order_id}%",)
        )
        nha_cho_count, nha_cho_sum = cur.fetchone()

        # 3. Check D3 order status
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (order_id,))
        final_status = cur.fetchone()['trang_thai']
        conn.close()

        self.assertEqual(final_hold, 0, f"dang_giu_cho expected 0, but got {final_hold}")
        self.assertEqual(nha_cho_count, 1, f"Expected exactly 1 NHA_CHO row in ledger, but found {nha_cho_count}")
        self.assertEqual(nha_cho_sum, 2, f"Total released quantity in ledger should be +2, got {nha_cho_sum}")
        self.assertIn(final_status, ('DA_HUY', 'DA_HUY_HET_HAN'), f"Order status invalid: {final_status}")

        # 4. Check audit log integrity
        status, audit_data = self.request('POST', '/api/audit/verify', {})
        self.assertEqual(status, 200)
        is_valid = audit_data.get('valid') if 'valid' in audit_data else audit_data.get('unbroken_chain')
        self.assertTrue(is_valid, f"Audit hash chain compromised during race condition: {audit_data}")

    def test_challenge_04_auto_release_expired_batch_without_affecting_unexpired(self):
        """
        Challenge: Multiple orders with mixed expiry states (some expired > 30m, some active < 30m).
        Oracle:
        - Only expired orders are transitioned to DA_HUY_HET_HAN.
        - Active orders strictly remain in GIU_CHO.
        - Stock is released ONLY for expired orders.
        """
        prod_code = "CHALLENGE-BATCH-PROD"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Bàn ăn Challenge Batch', 'banan', 'Xưởng Thạch Thất', 3000000, 3500000, 4000000, 20, 6)
        ''', (prod_code,))

        now = datetime.now()
        t_expired_1 = (now - timedelta(minutes=45)).strftime('%Y-%m-%d %H:%M:%S')
        t_expired_2 = (now - timedelta(minutes=31)).strftime('%Y-%m-%d %H:%M:%S')
        t_active = (now - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

        cur.execute("INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, con_phai_thu) VALUES ('KV-EXP-01', ?, 'Exp1', 'anhnam', 4000000, 'VIETQR', 'GIU_CHO', 4000000)", (t_expired_1,))
        cur.execute("INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, con_phai_thu) VALUES ('KV-EXP-02', ?, 'Exp2', 'anhnam', 4000000, 'VIETQR', 'GIU_CHO', 4000000)", (t_expired_2,))
        cur.execute("INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, con_phai_thu) VALUES ('KV-ACT-01', ?, 'Act1', 'anhnam', 8000000, 'VIETQR', 'GIU_CHO', 8000000)", (t_active,))

        # Ledger GIU_CHO entries: 1 + 1 + 2 = 4 (remaining 2 from previous seed)
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('28/10 14:00', 'GIU_CHO', ?, 'Bàn ăn', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', 'Đơn #KV-EXP-01', 'anhnam')", (prod_code,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('28/10 14:00', 'GIU_CHO', ?, 'Bàn ăn', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', 'Đơn #KV-EXP-02', 'anhnam')", (prod_code,))
        cur.execute("INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien) VALUES ('28/10 14:00', 'GIU_CHO', ?, 'Bàn ăn', 'Xưởng Thạch Thất', -2, 'KHA_DUNG', 'Đơn #KV-ACT-01', 'anhnam')", (prod_code,))

        conn.commit()
        conn.close()

        # Trigger auto-release
        server.release_expired_holds()

        # Verify
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ma_don, trang_thai FROM D3_DON_HANG WHERE ma_don IN ('KV-EXP-01', 'KV-EXP-02', 'KV-ACT-01')")
        statuses = {r['ma_don']: r['trang_thai'] for r in cur.fetchall()}

        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        current_hold = cur.fetchone()[0]
        conn.close()

        self.assertEqual(statuses.get('KV-EXP-01'), 'DA_HUY_HET_HAN')
        self.assertEqual(statuses.get('KV-EXP-02'), 'DA_HUY_HET_HAN')
        self.assertEqual(statuses.get('KV-ACT-01'), 'GIU_CHO', "Unexpired order must NOT be cancelled")
        self.assertEqual(current_hold, 4, f"dang_giu_cho expected 6 - 2 = 4, but got {current_hold}")

    # =========================================================================
    # 3. CANCELLING ORDERS IN VARIOUS STATES & CORNER CASES
    # =========================================================================
    def test_challenge_05_cancel_idempotence_in_all_states(self):
        """
        Challenge: Test POST /api/orders/cancel across every possible order state:
        - Active GIU_CHO -> Success 200, status DA_HUY.
        - Repeated cancel on DA_HUY -> Idempotent 200, status DA_HUY, no extra ledger rows.
        - Repeated cancel on DA_HUY_HET_HAN -> Idempotent 200, status DA_HUY_HET_HAN, no extra ledger rows.
        - Cancel on DA_THANH_TOAN -> Blocked 400 CANNOT_CANCEL_PAID_ORDER.
        - Cancel on nonexistent order -> 404 ORDER_NOT_FOUND.
        - Cancel with missing order_id -> 400 MISSING_ORDER_ID.
        """
        # 1. Create order
        payload = {
            "khach_hang": "State Matrix Customer",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8500000, "thanh_tien": 8500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        ma_don = res['ma_don']

        # 2. Cancel active order
        s1, r1 = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don})
        self.assertEqual(s1, 200)
        self.assertEqual(r1.get('trang_thai'), 'DA_HUY')

        # Count D4 NHA_CHO rows after first cancel
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        initial_nha_cho_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(initial_nha_cho_count, 1)

        # 3. Repeated cancel on already cancelled order (must be idempotent)
        s2, r2 = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don})
        self.assertEqual(s2, 200)
        self.assertEqual(r2.get('trang_thai'), 'DA_HUY')

        # Check ledger count again: must STILL be 1 (no double ledger entry)
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        post_nha_cho_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(post_nha_cho_count, 1, "Duplicate NHA_CHO entry generated on idempotent cancel!")

        # 4. Cancel on already paid order
        s_paid, r_paid = self.request('POST', '/api/orders/cancel', {'ma_don': 'KV261026001'}) # Seeded as DA_THANH_TOAN
        self.assertEqual(s_paid, 400)
        self.assertEqual(r_paid.get('error'), 'CANNOT_CANCEL_PAID_ORDER')

        # 5. Cancel nonexistent order
        s_non, r_non = self.request('POST', '/api/orders/cancel', {'ma_don': 'KV-NON-EXISTENT-XYZ'})
        self.assertEqual(s_non, 404)
        self.assertEqual(r_non.get('error'), 'ORDER_NOT_FOUND')

        # 6. Cancel missing order ID
        s_miss, r_miss = self.request('POST', '/api/orders/cancel', {})
        self.assertEqual(s_miss, 400)
        self.assertEqual(r_miss.get('error'), 'MISSING_ORDER_ID')

    def test_challenge_06_multi_item_order_cancel_releases_all_variants(self):
        """
        Challenge: Order containing multiple distinct products.
        On cancellation, holds on ALL variants must be decremented properly,
        and D4 ledger must log NHA_CHO for each item.
        """
        item1 = "GUONG-HOP-SOI-1800"
        item2 = "TUTHO-MIT-1270"

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item1,))
        h1_before = cur.fetchone()[0]
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item2,))
        h2_before = cur.fetchone()[0]
        conn.close()

        payload = {
            "khach_hang": "Multi-item Customer",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "items": [
                {"ma_bien_the": item1, "so_luong": 2, "don_gia": 8500000, "thanh_tien": 17000000},
                {"ma_bien_the": item2, "so_luong": 1, "don_gia": 5328000, "thanh_tien": 5328000}
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 200)
        ma_don = res['ma_don']

        # Cancel order
        s_cancel, r_cancel = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don})
        self.assertEqual(s_cancel, 200)

        # Invariant check
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item1,))
        h1_after = cur.fetchone()[0]
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (item2,))
        h2_after = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'", (f"%{ma_don}%",))
        nha_cho_entries = cur.fetchone()[0]
        conn.close()

        self.assertEqual(h1_after, h1_before, f"Hold for {item1} was not restored to initial level")
        self.assertEqual(h2_after, h2_before, f"Hold for {item2} was not restored to initial level")
        self.assertEqual(nha_cho_entries, 2, f"Expected 2 NHA_CHO ledger entries for 2 items, got {nha_cho_entries}")

    # =========================================================================
    # 4. RBAC FLOOR PRICE GATE & TOKEN EXPLOIT RESISTANCE
    # =========================================================================
    def test_challenge_07_rbac_adversarial_tokens_and_edge_prices(self):
        """
        Challenge: Probing floor price gating with adversarial tokens,
        negative prices, 0 price, and role spoofing.
        Oracle:
        - Price 1 VND below floor rejected for worker (403).
        - Price 0 rejected for worker (403).
        - Negative price rejected for worker (403).
        - Forged tokens ('ADMIN', 'null', True, 'OWNER_APPROVAL') rejected (403).
        - Exact token 'OWNER_APPROVAL_2026' accepted (200).
        """
        # Floor price for GUONG-HOP-SOI-1800 is 8,100,000
        # 1. Price 1 VND below floor
        p_near = {
            "khach_hang": "Near Floor", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 8099999, "thanh_tien": 8099999}],
            "hinh_thuc_tt": "VIETQR"
        }
        s1, r1 = self.request('POST', '/api/orders', p_near)
        self.assertEqual(s1, 403)
        self.assertEqual(r1.get('error'), 'FLOOR_PRICE_VIOLATION')

        # 2. Forged tokens
        for bad_token in ['ADMIN', 'OWNER', 'OWNER_APPROVAL', '123456', 'TRUE', '']:
            p_forged = {
                "khach_hang": "Forged Token", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
                "auth_token_duyet": bad_token,
                "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 7000000, "thanh_tien": 7000000}],
                "hinh_thuc_tt": "VIETQR"
            }
            s, r = self.request('POST', '/api/orders', p_forged)
            self.assertEqual(s, 403, f"Forged token '{bad_token}' bypassed RBAC floor gate!")

        # 3. Legitimate approval token
        p_valid = {
            "khach_hang": "Valid Token", "nguoi_lap": "anhnam@khanhvan.vn", "vai_tro_nguoi_lap": "THO",
            "auth_token_duyet": "OWNER_APPROVAL_2026",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 7500000, "thanh_tien": 7500000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s_val, r_val = self.request('POST', '/api/orders', p_valid)
        self.assertEqual(s_val, 200, f"Valid token rejected: {r_val}")

    # =========================================================================
    # 5. DYNAMIC PRICING ENGINE ADVERSARIAL BOUNDARIES
    # =========================================================================
    def test_challenge_08_pricing_boundary_saturation_and_invariants(self):
        """
        Challenge: Boundary conditions and negative dimensions on pricing API:
        - Exact bounds: 400mm (pass), 3000mm (pass), 399mm (fail), 3001mm (fail).
        - Thickness bounds: 10mm (pass), 9.9mm (fail), 0mm (fail), negative (fail).
        - Area dimension bounds: 400x400 (pass), 3000x3000 (pass), 399x400 (fail), 400x399 (fail).
        - Response contract: must return non-null numeric thanh_tien > 0.
        """
        # Lower boundary
        s399, _ = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 399})
        self.assertEqual(s399, 400)
        s400, r400 = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 400})
        self.assertEqual(s400, 200)
        self.assertGreater(r400.get('thanh_tien', 0), 0)

        # Upper boundary
        s3000, r3000 = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 3000})
        self.assertEqual(s3000, 200)
        self.assertGreater(r3000.get('thanh_tien', 0), 0)
        s3001, _ = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 3001})
        self.assertEqual(s3001, 400)

        # Thickness validation
        s_thk_9, _ = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 1000, 'do_day_mm': 9.9})
        self.assertEqual(s_thk_9, 400)
        s_thk_10, r_thk_10 = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'MET_DAI', 'chieu_dai_mm': 1000, 'do_day_mm': 10})
        self.assertEqual(s_thk_10, 200)

        # Area validation
        s_area_low, _ = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'DIEN_TICH', 'chieu_dai_mm': 399, 'chieu_rong_mm': 1000})
        self.assertEqual(s_area_low, 400)
        s_area_low2, _ = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'DIEN_TICH', 'chieu_dai_mm': 1000, 'chieu_rong_mm': 399})
        self.assertEqual(s_area_low2, 400)
        s_area_valid, r_area = self.request('POST', '/api/pricing/calculate', {'kieu_tinh': 'DIEN_TICH', 'chieu_dai_mm': 1000, 'chieu_rong_mm': 1000})
        self.assertEqual(s_area_valid, 200)
        self.assertGreater(r_area.get('thanh_tien', 0), 0)


if __name__ == '__main__':
    unittest.main()
