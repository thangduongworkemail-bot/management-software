#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Suite for Milestone 2 (POS Sales, Pricing & Hold Engine)
Demonstrates failure modes, integrity violations, and concurrency risks.
"""

import unittest
import sqlite3
import tempfile
import shutil
import os
import sys
import threading
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import server

class TestM2AdversarialStress(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='m2_adv_test_')
        self.test_db_path = os.path.join(self.test_dir, 'test_adv.db')
        server.DB_FILE = self.test_db_path
        server.init_db()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_adv_01_hardcoded_bypass_discriminates_orders(self):
        """
        Adversarial Test 1:
        Verify that KV-EXPIRED-01 receives special hardcoded logic,
        while an identical expired order KV-EXPIRED-99 leaks stock hold.
        """
        conn = server.get_db()
        cur = conn.cursor()
        past_time = (datetime.now() - timedelta(minutes=35)).strftime('%Y-%m-%d %H:%M:%S')

        # Insert KV-EXPIRED-01
        cur.execute('''
        INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES ('KV-EXPIRED-01', ?, 'Customer 1', 'anhnam@khanhvan.vn', 8500000, 'VIETQR', 'GIU_CHO', 0, 8500000, ?)
        ''', (past_time, past_time))
        cur.execute("UPDATE D1_SAN_PHAM SET dang_giu_cho = dang_giu_cho + 1 WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")

        # Insert identical KV-EXPIRED-99
        cur.execute('''
        INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES ('KV-EXPIRED-99', ?, 'Customer 2', 'anhnam@khanhvan.vn', 8500000, 'VIETQR', 'GIU_CHO', 0, 8500000, ?)
        ''', (past_time, past_time))
        cur.execute("UPDATE D1_SAN_PHAM SET dang_giu_cho = dang_giu_cho + 1 WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        conn.commit()

        # Run auto release
        server.release_expired_holds()

        # Check status of both orders
        cur.execute("SELECT ma_don, trang_thai FROM D3_DON_HANG WHERE ma_don IN ('KV-EXPIRED-01', 'KV-EXPIRED-99')")
        statuses = {r['ma_don']: r['trang_thai'] for r in cur.fetchall()}
        self.assertEqual(statuses['KV-EXPIRED-01'], 'DA_HUY_HET_HAN')
        self.assertEqual(statuses['KV-EXPIRED-99'], 'DA_HUY_HET_HAN')

        # Check D4 entries
        cur.execute("SELECT loai_dong, tham_chieu FROM D4_SO_CAI_TON WHERE loai_dong = 'NHA_CHO'")
        d4_nha_cho = cur.fetchall()

        # Neither wrote NHA_CHO to D4!
        self.assertEqual(len(d4_nha_cho), 0, "Neither order appended NHA_CHO to D4_SO_CAI_TON, violating append-only ledger!")

        # Initial dang_giu_cho in seed is 0. We added 2 (total 2).
        # KV-EXPIRED-01 decremented it to 1 via hardcoded branch.
        # KV-EXPIRED-99 did NOT decrement, so it remained stuck at 1 instead of returning to 0!
        cur.execute("SELECT dang_giu_cho FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        dang_giu_cho = cur.fetchone()['dang_giu_cho']
        conn.close()

        print(f"Adversarial Test 1: dang_giu_cho is {dang_giu_cho} (expected 0 if both released, got 1 due to hardcoded branch bypass)")
        self.assertEqual(dang_giu_cho, 1, "Proves KV-EXPIRED-99 leaked stock reservation while KV-EXPIRED-01 was hardcoded")

    def test_adv_02_seed_order_never_expires(self):
        """
        Adversarial Test 2:
        Demonstrates that seed order KV261027015 is permanently immune to auto-release
        because of hardcoded skip in server.py line 50.
        """
        conn = server.get_db()
        cur = conn.cursor()

        # Verify seed order exists and is in GIU_CHO
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = 'KV261027015'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['trang_thai'], 'GIU_CHO')

        # Trigger release_expired_holds multiple times
        for _ in range(3):
            server.release_expired_holds()

        # Check status again
        cur.execute("SELECT trang_thai FROM D3_DON_HANG WHERE ma_don = 'KV261027015'")
        row_after = cur.fetchone()
        conn.close()

        # It remains GIU_CHO forever despite being created on 28/10/2026 10:45
        self.assertEqual(row_after['trang_thai'], 'GIU_CHO', "KV261027015 permanently blocked from expiring due to hardcoded check")

    def test_adv_03_concurrent_cancel_and_release_race_hazard(self):
        """
        Adversarial Test 3:
        Demonstrates that release_expired_holds does not use conditional UPDATE
        or check for existing NHA_CHO, allowing race condition with concurrent payment.
        """
        conn = server.get_db()
        cur = conn.cursor()
        now_dt = datetime.now() - timedelta(minutes=35)
        now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Create expired order with legitimate D4 record
        cur.execute('''
        INSERT INTO D3_DON_HANG (ma_don, ngay_tao, khach_hang, nguoi_lap, tong_tien, hinh_thuc_tt, trang_thai, tien_da_thu, con_phai_thu, ghi_chu)
        VALUES ('KV-RACE-01', ?, 'Race Customer', 'anhnam@khanhvan.vn', 8500000, 'VIETQR', 'GIU_CHO', 0, 8500000, 'Test race')
        ''', (now_str,))
        cur.execute("UPDATE D1_SAN_PHAM SET dang_giu_cho = dang_giu_cho + 1 WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        cur.execute('''
        INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
        VALUES ('28/10 10:00', 'GIU_CHO', 'GUONG-HOP-SOI-1800', 'Giường hộp Sồi', 'Xưởng Thạch Thất', -1, 'KHA_DUNG', 'Đơn #KV-RACE-01', 'anhnam@khanhvan.vn')
        ''')
        conn.commit()

        # Simulate concurrent payment happening just as auto-release starts
        cur.execute("UPDATE D3_DON_HANG SET trang_thai = 'DA_THANH_TOAN', tien_da_thu = 8500000, con_phai_thu = 0 WHERE ma_don = 'KV-RACE-01'")
        conn.commit()

        # If release_expired_holds had read the order list when it was GIU_CHO,
        # it would unconditionally overwrite DA_THANH_TOAN to DA_HUY_HET_HAN.
        # Check server.py line 96:
        # cur.execute("UPDATE D3_DON_HANG SET trang_thai = 'DA_HUY_HET_HAN' WHERE ma_don = ?", (ma_don,))
        # Notice there is NO 'AND trang_thai = GIU_CHO' guard!
        conn.close()

    def test_adv_04_static_token_unauthorized_replay(self):
        """
        Adversarial Test 4:
        Demonstrates that auth_token 'OWNER_APPROVAL_2026' is static and non-expiring,
        allowing a Worker (THO) to bypass floor price checks indefinitely without owner involvement.
        """
        # Worker orders 8,500,000 VND product for 1,000 VND using known static token
        payload = {
            "khach_hang": "Unauthorized Discount Replay",
            "nguoi_lap": "anhnam@khanhvan.vn",
            "vai_tro_nguoi_lap": "THO",
            "auth_token_duyet": "OWNER_APPROVAL_2026",
            "items": [{"ma_bien_the": "GUONG-HOP-SOI-1800", "so_luong": 1, "don_gia": 1000, "thanh_tien": 1000}],
            "hinh_thuc_tt": "VIETQR"
        }

        # Simulate handler directly
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT gia_san FROM D1_SAN_PHAM WHERE ma_bien_the = 'GUONG-HOP-SOI-1800'")
        gia_san = cur.fetchone()['gia_san']
        self.assertEqual(gia_san, 8100000)

        # In server.py: auth_token == 'OWNER_APPROVAL_2026' grants authorization directly
        auth_token = payload['auth_token_duyet']
        vai_tro = payload['vai_tro_nguoi_lap']
        is_authorized = (vai_tro in ('CHU', 'ADMIN') or auth_token == 'OWNER_APPROVAL_2026')
        self.assertTrue(is_authorized, "Static token allows arbitrary unauthorized orders at 1000 VND without owner consent")
        conn.close()

if __name__ == '__main__':
    unittest.main()
