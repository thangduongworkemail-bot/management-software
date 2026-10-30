#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milestone 2 Round 2 - Advanced Concurrency & Hold Engine Stress Harness
Agent: m2_r2_challenger_1

Focus:
1. High-concurrency order holds (50 parallel threads against 7 items)
2. Single-order duplicate variant line items (pre-aggregation, stock limits, cancellation restoration)
3. Thundering herd cancellation (20 concurrent threads cancelling the identical order)
4. Batch race condition: 10 concurrent expired orders raced between auto-release and manual cancellation
5. D4_SO_CAI_TON Append-only triggers enforcement (verifying trg_d4_prevent_update and trg_d4_prevent_delete)
6. Zero stock saturation (concurrent attempts on 0 inventory)
7. Multi-item basket atomicity (rollback check to ensure no phantom partial holds when one variant fails)
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class ThreadedTCPServer(server.socketserver.ThreadingMixIn, server.socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 100

class M2R2AdvancedConcurrencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KhanhVanServer.log_message = lambda self, format, *args: None

        cls.test_dir = tempfile.mkdtemp(prefix='khanhvan_m2_r2_')
        cls.test_db_path = os.path.join(cls.test_dir, 'test_m2_r2.db')
        server.DB_FILE = cls.test_db_path

        cls.init_clean_db()

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
    # 1. 50 PARALLEL THREADS AGAINST 7 AVAILABLE STOCK
    # =========================================================================
    def test_r2_01_extreme_concurrency_saturation(self):
        """
        Challenge: 50 concurrent threads try to reserve 1 unit of product with 7 units available.
        Oracle:
        - Exactly 7 requests succeed (HTTP 200).
        - Exactly 43 requests fail with HTTP 400 INSUFFICIENT_STOCK.
        - 0 internal 500 errors or lock collisions.
        - dang_giu_cho is exactly 7 (<= ton_hien_co).
        - D4_SO_CAI_TON records exactly 7 GIU_CHO entries for this product.
        """
        prod_code = "R2-STRESS-50T"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Stress 50 Product', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 7, 0)
        ''', (prod_code,))
        conn.commit()
        conn.close()

        num_threads = 50
        results = []
        threads = []
        barrier = threading.Barrier(num_threads)

        def worker(idx):
            payload = {
                "khach_hang": f"Stress Buyer {idx}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "items": [{
                    "ma_bien_the": prod_code,
                    "so_luong": 1,
                    "don_gia": 2000000
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
            t.join(timeout=15)

        successes = [r for r in results if r[0] == 200]
        insufficient = [r for r in results if r[0] == 400 and r[1].get('error') == 'INSUFFICIENT_STOCK']
        errors = [r for r in results if r[0] not in (200, 400)]

        self.assertEqual(len(errors), 0, f"Unexpected error responses: {errors}")
        self.assertEqual(len(successes), 7, f"Expected exactly 7 successes, got {len(successes)}")
        self.assertEqual(len(insufficient), 43, f"Expected 43 insufficient stock errors, got {len(insufficient)}")

        # DB state check
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT ton_hien_co, dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        row = cur.fetchone()
        ton_hien_co, dang_giu_cho = row['ton_hien_co'], row['dang_giu_cho']

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE ma_bien_the = ? AND loai_dong = 'GIU_CHO'", (prod_code,))
        d4_count = cur.fetchone()[0]
        conn.close()

        self.assertEqual(dang_giu_cho, 7, f"Expected dang_giu_cho == 7, got {dang_giu_cho}")
        self.assertEqual(d4_count, 7, f"Expected 7 GIU_CHO ledger rows, got {d4_count}")
        self.assertLessEqual(dang_giu_cho, ton_hien_co)

    # =========================================================================
    # 2. DUPLICATE VARIANTS IN A SINGLE ORDER
    # =========================================================================
    def test_r2_02_duplicate_variant_in_single_order(self):
        """
        Challenge:
        Part A: Order requests variant X twice (qty 3 and qty 3 = total 6), but available is 5.
                Must fail with 400 INSUFFICIENT_STOCK.
        Part B: Product has 10 available. Order with qty 3 and qty 3 succeeds (hold = 6).
                Then order is cancelled: hold must drop to 0, and D4 must record 2 NHA_CHO entries.
        """
        prod_code = "R2-DUP-VAR-01"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Duplicate Variant Prod', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 5, 0)
        ''', (prod_code,))
        conn.commit()
        conn.close()

        # Part A: Exceeding stock via duplicate line items
        payload_fail = {
            "khach_hang": "Duplicate Variant Buyer",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [
                {"ma_bien_the": prod_code, "so_luong": 3, "don_gia": 2000000},
                {"ma_bien_the": prod_code, "so_luong": 3, "don_gia": 2000000}
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        s1, r1 = self.request('POST', '/api/orders', payload_fail)
        self.assertEqual(s1, 400)
        self.assertEqual(r1.get('error'), 'INSUFFICIENT_STOCK')

        # Verify hold is still 0
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        self.assertEqual(cur.fetchone()[0], 0, "Hold leaked on rejected duplicate variant order")
        conn.close()

        # Part B: Increase stock to 10 and submit
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE D1_SAN_PHAM SET ton_hien_co = 10 WHERE ma_bien_the = ?", (prod_code,))
        conn.commit()
        conn.close()

        s2, r2 = self.request('POST', '/api/orders', payload_fail)
        self.assertEqual(s2, 200)
        ma_don = r2['ma_don']

        # Verify hold increased by 6
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        self.assertEqual(cur.fetchone()[0], 6)
        conn.close()

        # Cancel the order
        sc, rc = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don})
        self.assertEqual(sc, 200)

        # Verify hold restored to 0 and D4 entries
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        self.assertEqual(cur.fetchone()[0], 0, "Hold not fully restored after cancelling duplicate variant order")

        cur.execute(
            "SELECT COUNT(*), SUM(bien_dong) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'",
            (f"%{ma_don}%",)
        )
        count_nha, sum_nha = cur.fetchone()
        conn.close()

        self.assertEqual(count_nha, 2, f"Expected 2 NHA_CHO rows for duplicate lines, got {count_nha}")
        self.assertEqual(sum_nha, 6, f"Expected total +6 restored in NHA_CHO, got {sum_nha}")

    # =========================================================================
    # 3. THUNDERING HERD CANCELLATION (20 CONCURRENT CANCEL CALLS ON 1 ORDER)
    # =========================================================================
    def test_r2_03_thundering_herd_cancellation(self):
        """
        Challenge: 20 concurrent threads all call POST /api/orders/cancel on the SAME order.
        Oracle:
        - All 20 return HTTP 200.
        - Exactly 1 NHA_CHO entry is created in D4_SO_CAI_TON.
        - dang_giu_cho is decremented exactly ONCE by the held amount (never negative).
        """
        prod_code = "R2-HERD-CANCEL"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Herd Cancel Prod', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 10, 0)
        ''', (prod_code,))
        conn.commit()
        conn.close()

        # Create order holding 4 items
        payload = {
            "khach_hang": "Herd Customer",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [{"ma_bien_the": prod_code, "so_luong": 4, "don_gia": 2000000}],
            "hinh_thuc_tt": "VIETQR"
        }
        s, r = self.request('POST', '/api/orders', payload)
        self.assertEqual(s, 200)
        ma_don = r['ma_don']

        # Concurrently fire 20 cancel requests
        num_cancels = 20
        results = []
        threads = []
        barrier = threading.Barrier(num_cancels)

        def cancel_worker(idx):
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            st, res = self.request('POST', '/api/orders/cancel', {'ma_don': ma_don})
            results.append((st, res))

        for i in range(num_cancels):
            t = threading.Thread(target=cancel_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        # All 20 should receive 200
        for st, res in results:
            self.assertEqual(st, 200, f"Non-200 cancel response: {res}")

        # Check DB invariants
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        final_hold = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*), SUM(bien_dong) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'",
            (f"%{ma_don}%",)
        )
        nha_count, nha_sum = cur.fetchone()
        conn.close()

        self.assertEqual(final_hold, 0, f"Expected hold to be 0, got {final_hold}")
        self.assertEqual(nha_count, 1, f"CRITICAL: Expected exactly 1 NHA_CHO row, got {nha_count}")
        self.assertEqual(nha_sum, 4, f"Expected total +4 restored, got {nha_sum}")

    # =========================================================================
    # 4. BATCH RACE: 10 CONCURRENT EXPIRED ORDERS (AUTO-RELEASE VS MANUAL CANCEL)
    # =========================================================================
    def test_r2_04_batch_auto_release_and_cancel_race(self):
        """
        Challenge: 10 distinct expired orders are simultaneously attacked by
        release_expired_holds() and manual POST /api/orders/cancel.
        Oracle:
        - Every order is transitioned to DA_HUY or DA_HUY_HET_HAN.
        - For every order, exactly ONE NHA_CHO record exists in D4.
        - Total NHA_CHO rows across all 10 orders is exactly 10.
        - Total restored stock across all orders is 10 * 2 = 20.
        - dang_giu_cho ends at 0.
        """
        prod_code = "R2-BATCH-RACE"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Batch Race Prod', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 50, 20)
        ''', (prod_code,))

        past_time = (datetime.now() - timedelta(minutes=45)).strftime('%Y-%m-%d %H:%M:%S')
        order_ids = [f"KV261028BAT{i:02d}" for i in range(10)]

        for oid in order_ids:
            cur.execute('''
            INSERT OR REPLACE INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, con_phai_thu)
            VALUES (?, ?, 'Batch Race Customer', 'anhnam@khanhvan.vn', 4000000, 'VIETQR', 'GIU_CHO', 4000000)
            ''', (oid, past_time))
            cur.execute('''
            INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
            VALUES ('28/10 14:00', 'GIU_CHO', ?, 'Batch Race Prod', 'Xưởng Thạch Thất', -2, 'KHA_DUNG', ?, 'anhnam@khanhvan.vn')
            ''', (prod_code, f"Đơn #{oid}"))

        conn.commit()
        conn.close()

        # Concurrently launch 1 auto-release worker and 10 manual cancel threads
        threads = []
        barrier = threading.Barrier(11)

        def auto_release_runner():
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            server.release_expired_holds()

        def manual_cancel_runner(oid):
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            self.request('POST', '/api/orders/cancel', {'ma_don': oid})

        t_auto = threading.Thread(target=auto_release_runner)
        threads.append(t_auto)

        for oid in order_ids:
            t = threading.Thread(target=manual_cancel_runner, args=(oid,))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=15)

        # Invariant Verification
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        final_hold = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*), SUM(bien_dong) FROM D4_SO_CAI_TON WHERE loai_dong = 'NHA_CHO' AND ma_bien_the = ?",
            (prod_code,)
        )
        total_nha_count, total_nha_sum = cur.fetchone()

        for oid in order_ids:
            cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = ?", (oid,))
            st = cur.fetchone()['trang_thai']
            self.assertIn(st, ('DA_HUY', 'DA_HUY_HET_HAN'), f"Order {oid} has unexpected status: {st}")

            cur.execute(
                "SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE tham_chieu LIKE ? AND loai_dong = 'NHA_CHO'",
                (f"%{oid}%",)
            )
            oid_nha_count = cur.fetchone()[0]
            self.assertEqual(oid_nha_count, 1, f"Order {oid} has {oid_nha_count} NHA_CHO rows, expected exactly 1")

        conn.close()

        self.assertEqual(final_hold, 0, f"Final dang_giu_cho expected 0, got {final_hold}")
        self.assertEqual(total_nha_count, 10, f"Expected 10 total NHA_CHO records, got {total_nha_count}")
        self.assertEqual(total_nha_sum, 20, f"Expected total +20 restored inventory, got {total_nha_sum}")

    # =========================================================================
    # 5. D4_SO_CAI_TON APPEND-ONLY TRIGGERS ENFORCEMENT
    # =========================================================================
    def test_r2_05_d4_ledger_triggers_prevent_update_and_delete(self):
        """
        Challenge: Verify that SQLite triggers trg_d4_prevent_update and trg_d4_prevent_delete:
        1. Exist in sqlite_master.
        2. Actively abort direct UPDATE on D4_SO_CAI_TON.
        3. Actively abort direct DELETE on D4_SO_CAI_TON.
        4. Preserve ledger integrity under adversary trying to modify stock history.
        """
        conn = self.get_db()
        cur = conn.cursor()

        # 1. Verify triggers exist
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'D4_SO_CAI_TON'")
        triggers = {r['name']: r['sql'] for r in cur.fetchall()}
        self.assertIn('trg_d4_prevent_update', triggers, "Trigger trg_d4_prevent_update missing!")
        self.assertIn('trg_d4_prevent_delete', triggers, "Trigger trg_d4_prevent_delete missing!")

        # 2. Insert a valid row
        cur.execute('''
        INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
        VALUES ('29/10 10:00', 'NHAP', 'TRIG-TEST-PROD', 'Trigger Prod', 'Xưởng Thạch Thất', 50, 'HIEN_CO', 'Phiếu #TEST-01', 'Admin')
        ''')
        row_id = cur.lastrowid
        conn.commit()

        # 3. Attempt UPDATE -> must raise OperationalError or IntegrityError
        with self.assertRaises(sqlite3.DatabaseError) as ctx_update:
            cur.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 999 WHERE id = ?", (row_id,))
            conn.commit()
        self.assertIn("Append-only violation", str(ctx_update.exception))

        # 4. Attempt DELETE -> must raise OperationalError or IntegrityError
        with self.assertRaises(sqlite3.DatabaseError) as ctx_delete:
            cur.execute("DELETE FROM D4_SO_CAI_TON WHERE id = ?", (row_id,))
            conn.commit()
        self.assertIn("Append-only violation", str(ctx_delete.exception))

        conn.close()

    # =========================================================================
    # 6. ZERO STOCK SATURATION
    # =========================================================================
    def test_r2_06_zero_stock_saturation(self):
        """
        Challenge: 10 concurrent requests arrive for an item with ton_hien_co = 0.
        Oracle:
        - 100% of requests must be rejected with 400 INSUFFICIENT_STOCK.
        - dang_giu_cho remains 0.
        - 0 rows inserted into D4_SO_CAI_TON.
        """
        prod_code = "R2-ZERO-STOCK"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Zero Stock Prod', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 0, 0)
        ''', (prod_code,))
        conn.commit()
        conn.close()

        num_threads = 10
        results = []
        threads = []
        barrier = threading.Barrier(num_threads)

        def worker(idx):
            payload = {
                "khach_hang": f"Zero Buyer {idx}",
                "nguoi_lap": "anhnam@khanhvan.vn",
                "items": [{"ma_bien_the": prod_code, "so_luong": 1, "don_gia": 2000000}],
                "hinh_thuc_tt": "VIETQR"
            }
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            st, res = self.request('POST', '/api/orders', payload)
            results.append((st, res))

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        for st, res in results:
            self.assertEqual(st, 400)
            self.assertEqual(res.get('error'), 'INSUFFICIENT_STOCK')

        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_code,))
        self.assertEqual(cur.fetchone()[0], 0)

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE ma_bien_the = ?", (prod_code,))
        self.assertEqual(cur.fetchone()[0], 0)
        conn.close()

    # =========================================================================
    # 7. MULTI-ITEM BASKET TRANSACTION ATOMICITY (NO PHANTOM HOLDS)
    # =========================================================================
    def test_r2_07_multi_item_basket_atomicity(self):
        """
        Challenge: Customer tries to buy Product A (1 unit, available = 10) AND Product B (2 units, available = 1).
        Product B has insufficient stock, so the order fails.
        Oracle:
        - HTTP 400 INSUFFICIENT_STOCK.
        - dang_giu_cho for Product A MUST NOT BE INCREMENTED (no partial phantom hold).
        - D4_SO_CAI_TON MUST NOT contain GIU_CHO for Product A.
        """
        prod_a = "R2-BASKET-A"
        prod_b = "R2-BASKET-B"
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Basket Prod A', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 10, 0)
        ''', (prod_a,))
        cur.execute('''
        INSERT OR REPLACE INTO D1_SAN_PHAM (ma_bien_the, ten_san_pham, nhom_hang, xuong, gia_von, gia_san, gia_niem_yet, ton_hien_co, dang_giu_cho)
        VALUES (?, 'Basket Prod B', 'bantra', 'Xưởng Thạch Thất', 1000000, 1500000, 2000000, 1, 0)
        ''', (prod_b,))
        conn.commit()
        conn.close()

        payload = {
            "khach_hang": "Basket Customer",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "items": [
                {"ma_bien_the": prod_a, "so_luong": 1, "don_gia": 2000000},
                {"ma_bien_the": prod_b, "so_luong": 2, "don_gia": 2000000}  # Available only 1
            ],
            "hinh_thuc_tt": "VIETQR"
        }
        status, res = self.request('POST', '/api/orders', payload)
        self.assertEqual(status, 400)
        self.assertEqual(res.get('error'), 'INSUFFICIENT_STOCK')

        # Check DB
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_a,))
        self.assertEqual(cur.fetchone()[0], 0, "Phantom hold leaked on Product A!")

        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = ?", (prod_b,))
        self.assertEqual(cur.fetchone()[0], 0, "Phantom hold leaked on Product B!")

        cur.execute("SELECT COUNT(*) FROM D4_SO_CAI_TON WHERE ma_bien_the IN (?, ?)", (prod_a, prod_b))
        self.assertEqual(cur.fetchone()[0], 0, "Phantom ledger entry leaked into D4!")
        conn.close()


if __name__ == '__main__':
    unittest.main()
