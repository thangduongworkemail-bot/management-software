"""
tests/test_audit_chain_attacks.py
Adversarial Stress Test Suite: SHA-256 Hash Chaining Audit Verification
Challenger: m1_challenger_2 (Milestone 1 - Database & Security Hardening)

Attack Vectors Tested:
1. Bit-flip tampering in historical records (payload fields, curr_hash, prev_hash).
2. Hash recomputation attack / local block forgery (altering record and recomputing block hash, leaving next record's prev_hash unchanged).
3. Genesis poisoning (non-zero prev_hash, short hash, genesis recomputation).
4. Intermediate row deletions and row swaps (middle deletion, genesis deletion, adjacent row swapping, middle insertion).
5. Edge cases: Empty audit log, single genesis row, dynamic append verification via REST API.
"""

import os
import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
import threading
import time
import urllib.request
import urllib.error
import socketserver

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Ensure parent directory is in path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server

class AuditChainAttacker:
    def __init__(self, port=5588):
        self.port = port
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.temp_dir = tempfile.mkdtemp(prefix="audit_attack_")
        self.db_path = os.path.join(self.temp_dir, "test_khanhvan.db")
        self.httpd = None
        self.server_thread = None

    def setup(self):
        # Initialize fresh test database using server.init_db
        server.DB_FILE = self.db_path
        server.PORT = self.port
        server.init_db()

        # Start HTTP server in daemon thread
        self.httpd = socketserver.TCPServer(("127.0.0.1", self.port), server.KhanhVanServer)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()
        time.sleep(0.4)
        print(f"[*] Test server started on {self.base_url} with isolated DB: {self.db_path}")

    def teardown(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        print("[*] Test server stopped and temporary DB cleaned up.")

    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def call_verify_api(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/audit/verify",
            data=b'{}',
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return resp.status, data
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode('utf-8'))
            return e.code, data

    def reset_clean_audit_log(self):
        conn = self.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM D9_NHAT_KY")
        cur.execute("DELETE FROM sqlite_sequence WHERE name = 'D9_NHAT_KY'")
        
        logs = [
            ('28/10 08:30', 'System', 'KHOI_DONG', 'Hệ thống Khanh Vân', 'Khởi động máy chủ v2026.1 ĐHBK Hà Nội', 'DEV-POS-COUNTER'),
            ('28/10 09:15', 'Anh Nam (Thợ)', 'LAP_BAO_GIA', 'Đơn #KV261026002', 'Lập báo giá Tủ thờ 2m4 (5.328.000 đ) cho Bác Hùng', 'DEV-POS-COUNTER'),
            ('28/10 10:00', 'Dương Văn Thắng', 'NHAP_KHO', 'Lô #PN2610-08', 'Nhập 5 tủ quần áo 4 cánh MDF từ Kho Gỗ CN', 'DEV-POS-COUNTER'),
            ('28/10 10:42', 'Cô Vân (Chủ)', 'XAC_NHAN_TIEN', 'Đơn #KV261026001', 'Xác nhận tay tiền về 17.200.000 đ qua sao kê MBBank *4817', 'DEV-REDMI12T'),
            ('28/10 11:15', 'Cô Vân (Chủ)', 'PHAT_HANH_HDDT', 'HĐ #00123', 'Ký số thành công qua API VNPT Invoice', 'DEV-POS-COUNTER'),
            ('28/10 12:00', 'PayOS-Webhook', 'TIEN_VE_TU_DONG', 'Đơn #KV261026004', 'Napas 247 báo có 12.400.000 đ', 'DEV-REDMI12T')
        ]
        
        prev_hash = '0' * 64
        for log in logs:
            raw_str = f"{prev_hash}|{log[0]}|{log[1]}|{log[2]}|{log[3]}|{log[4]}|{log[5]}"
            curr_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
            cur.execute('''
            INSERT INTO D9_NHAT_KY (thoi_diem, nguoi_thuc_hien, hanh_dong, doi_tuong, chi_tiet, thiet_bi, prev_hash, curr_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (log[0], log[1], log[2], log[3], log[4], log[5], prev_hash, curr_hash))
            prev_hash = curr_hash
            
        conn.commit()
        conn.close()

# ==============================================================================
# ATTACK VECTORS
# ==============================================================================

def test_baseline_pristine(attacker):
    print("\n--- [BASELINE] Pristine Audit Log Verification ---")
    attacker.reset_clean_audit_log()
    status, res = attacker.call_verify_api()
    print(f"HTTP Status: {status}, Response: {res['message']}")
    assert status == 200, f"Expected 200, got {status}"
    assert res['success'] is True
    assert res['valid'] is True
    assert res['unbroken_chain'] is True
    assert res['genesis_valid'] is True
    assert res['total_records'] == 6
    assert len(res['records']) == 6
    print("[PASS] Baseline pristine audit chain passed 100%.")

def test_vector_1_bit_flip_tampering(attacker):
    print("\n--- [VECTOR 1] Bit-Flip Tampering in Historical Records ---")
    fields_to_test = [
        ('thoi_diem', '28/10 09:16'),
        ('nguoi_thuc_hien', 'Anh Nam (Thợ Giả)'),
        ('hanh_dong', 'SUA_BAO_GIA'),
        ('doi_tuong', 'Đơn #KV261026999'),
        ('chi_tiet', 'Lập báo giá Tủ thờ 2m4 (9.999.000 đ)'),
        ('thiet_bi', 'DEV-HACKER-PC'),
        ('curr_hash', 'f' * 64),
        ('prev_hash', 'a' * 64)
    ]

    target_id = 3 # row 3 (NHAP_KHO)
    for field_name, tampered_value in fields_to_test:
        attacker.reset_clean_audit_log()
        conn = attacker.get_db_connection()
        cur = conn.cursor()
        
        # Tamper single field
        cur.execute(f"UPDATE D9_NHAT_KY SET {field_name} = ? WHERE id = ?", (tampered_value, target_id))
        assert cur.rowcount == 1, f"Expected 1 row updated for {field_name}, got {cur.rowcount}"
        conn.commit()
        conn.close()

        status, res = attacker.call_verify_api()
        print(f"  Tamper field '{field_name}' -> valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}, message: {res['message']}")
        
        assert status == 200
        assert res['success'] is True
        assert res['valid'] is False, f"VULNERABILITY: /api/audit/verify accepted bit-flip on '{field_name}'!"
        assert res['unbroken_chain'] is False
        assert "Cảnh báo: Chuỗi Hash bị gián đoạn!" in res['message']

    print("[PASS] Vector 1: Bit-flip tampering across all 8 fields rejected 100%.")

def test_vector_2_hash_recomputation(attacker):
    print("\n--- [VECTOR 2] Hash Recomputation Attack (Altered Row + Forged Block Hash) ---")
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()

    # Step 1: Attacker modifies row id=3 details
    cur.execute("SELECT prev_hash, thoi_diem, nguoi_thuc_hien, hanh_dong, doi_tuong, thiet_bi FROM D9_NHAT_KY WHERE id = 3")
    r = cur.fetchone()
    prev_h = r['prev_hash']
    tampered_details = "Rút ruột 5 tủ áo MDF đem bán chợ đen"

    # Step 2: Attacker recomputes valid block hash for row id=3
    raw = f"{prev_h}|{r['thoi_diem']}|{r['nguoi_thuc_hien']}|{r['hanh_dong']}|{r['doi_tuong']}|{tampered_details}|{r['thiet_bi']}"
    forged_curr_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # Step 3: Update row 3 with tampered details AND forged block hash, leaving row 4 prev_hash unchanged
    cur.execute("UPDATE D9_NHAT_KY SET chi_tiet = ?, curr_hash = ? WHERE id = 3", (tampered_details, forged_curr_hash))
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  Result -> valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}, msg: {res['message']}")

    assert status == 200
    assert res['valid'] is False, "VULNERABILITY: /api/audit/verify accepted locally forged block hash!"
    assert res['unbroken_chain'] is False
    assert "Chain continuity broken at index 3" in res['message']
    print("[PASS] Vector 2: Hash recomputation attack cleanly detected at subsequent link.")

def test_vector_3_genesis_poisoning(attacker):
    print("\n--- [VECTOR 3] Genesis Block Poisoning Attacks ---")
    
    # 3A: Genesis prev_hash set to non-zero 64-hex string
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE D9_NHAT_KY SET prev_hash = ? WHERE id = 1", ('1' * 64,))
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  3A (Non-zero prev_hash) -> genesis_valid: {res['genesis_valid']}, valid: {res['valid']}")
    assert status == 200
    assert res['genesis_valid'] is False
    assert res['unbroken_chain'] is False
    assert res['valid'] is False
    assert "Genesis block prev_hash invalid at id=1" in res['message']

    # 3B: Genesis prev_hash set to short string / empty string
    for invalid_genesis in ['', '0' * 32, '0' * 63, '0' * 65]:
        attacker.reset_clean_audit_log()
        conn = attacker.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE D9_NHAT_KY SET prev_hash = ? WHERE id = 1", (invalid_genesis,))
        assert cur.rowcount == 1
        conn.commit()
        conn.close()

        status, res = attacker.call_verify_api()
        assert res['genesis_valid'] is False
        assert res['valid'] is False

    # 3C: Genesis prev_hash tampered AND genesis curr_hash recomputed
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT thoi_diem, nguoi_thuc_hien, hanh_dong, doi_tuong, chi_tiet, thiet_bi FROM D9_NHAT_KY WHERE id = 1")
    r0 = cur.fetchone()
    poisoned_genesis = 'deadbeef' * 8
    raw0 = f"{poisoned_genesis}|{r0['thoi_diem']}|{r0['nguoi_thuc_hien']}|{r0['hanh_dong']}|{r0['doi_tuong']}|{r0['chi_tiet']}|{r0['thiet_bi']}"
    recomputed_h0 = hashlib.sha256(raw0.encode('utf-8')).hexdigest()
    cur.execute("UPDATE D9_NHAT_KY SET prev_hash = ?, curr_hash = ? WHERE id = 1", (poisoned_genesis, recomputed_h0))
    assert cur.rowcount == 1
    # Also update row 2 prev_hash to match new h0 so row 2 continuity wouldn't fail
    cur.execute("UPDATE D9_NHAT_KY SET prev_hash = ? WHERE id = 2", (recomputed_h0,))
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  3C (Recomputed genesis chain) -> genesis_valid: {res['genesis_valid']}, valid: {res['valid']}")
    assert res['genesis_valid'] is False, "VULNERABILITY: Recomputed genesis accepted!"
    assert res['valid'] is False
    assert "Genesis block prev_hash invalid at id=1" in res['message']

    print("[PASS] Vector 3: Genesis block poisoning attacks rejected 100%.")

def test_vector_4_intermediate_row_deletions_and_swaps(attacker):
    print("\n--- [VECTOR 4] Intermediate Row Deletions, Swaps & Insertions ---")

    # 4A: Delete middle row (id = 3)
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM D9_NHAT_KY WHERE id = 3")
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  4A (Middle row deleted) -> valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}")
    assert status == 200
    assert res['valid'] is False
    assert res['unbroken_chain'] is False
    assert "Chain continuity broken" in res['message']

    # 4B: Delete genesis row (id = 1)
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM D9_NHAT_KY WHERE id = 1")
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  4B (Genesis row deleted) -> valid: {res['valid']}, genesis_valid: {res['genesis_valid']}")
    assert status == 200
    assert res['valid'] is False
    assert res['genesis_valid'] is False
    assert "Genesis block prev_hash invalid" in res['message']

    # 4C: Swap two adjacent rows (id=2 and id=3)
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM D9_NHAT_KY WHERE id IN (2, 3) ORDER BY id ASC")
    rows = cur.fetchall()
    r2, r3 = rows[0], rows[1]
    
    # Swap contents of row 2 and row 3 except id
    cur.execute('''
    UPDATE D9_NHAT_KY SET thoi_diem=?, nguoi_thuc_hien=?, hanh_dong=?, doi_tuong=?, chi_tiet=?, thiet_bi=?, prev_hash=?, curr_hash=?
    WHERE id = 2
    ''', (r3['thoi_diem'], r3['nguoi_thuc_hien'], r3['hanh_dong'], r3['doi_tuong'], r3['chi_tiet'], r3['thiet_bi'], r3['prev_hash'], r3['curr_hash']))
    assert cur.rowcount == 1
    cur.execute('''
    UPDATE D9_NHAT_KY SET thoi_diem=?, nguoi_thuc_hien=?, hanh_dong=?, doi_tuong=?, chi_tiet=?, thiet_bi=?, prev_hash=?, curr_hash=?
    WHERE id = 3
    ''', (r2['thoi_diem'], r2['nguoi_thuc_hien'], r2['hanh_dong'], r2['doi_tuong'], r2['chi_tiet'], r2['thiet_bi'], r2['prev_hash'], r2['curr_hash']))
    assert cur.rowcount == 1
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  4C (Adjacent rows swapped) -> valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}")
    assert status == 200
    assert res['valid'] is False
    assert res['unbroken_chain'] is False

    # 4D: Middle row injection (extraneous row)
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO D9_NHAT_KY (thoi_diem, nguoi_thuc_hien, hanh_dong, doi_tuong, chi_tiet, thiet_bi, prev_hash, curr_hash)
    VALUES ('28/10 09:30', 'Kẻ Gian', 'GIAN_LAN', 'Két Tiền', 'Rút 50tr', 'DEV-POS-COUNTER', '0'*64, '1'*64)
    ''')
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  4D (Extraneous injected row) -> valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}")
    assert status == 200
    assert res['valid'] is False
    assert res['unbroken_chain'] is False

    print("[PASS] Vector 4: Intermediate row deletions, swaps, and injections rejected 100%.")

def test_vector_5_edge_cases_and_live_appends(attacker):
    print("\n--- [VECTOR 5] Boundary Stress & Dynamic Append Integrity ---")

    # 5A: Empty Audit Log Table
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM D9_NHAT_KY")
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  5A (Empty table) -> total_records: {res['total_records']}, valid: {res['valid']}")
    assert status == 200
    assert res['total_records'] == 0
    assert res['valid'] is True # 0 records is vacuously valid

    # 5B: Single Genesis Record
    attacker.reset_clean_audit_log()
    conn = attacker.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM D9_NHAT_KY WHERE id > 1")
    conn.commit()
    conn.close()

    status, res = attacker.call_verify_api()
    print(f"  5B (Single record) -> total_records: {res['total_records']}, valid: {res['valid']}")
    assert status == 200
    assert res['total_records'] == 1
    assert res['valid'] is True
    assert res['unbroken_chain'] is True
    assert res['genesis_valid'] is True

    # 5C: Dynamic Appends via API Endpoints
    attacker.reset_clean_audit_log()
    
    # Execute API actions that append to D9_NHAT_KY
    api_actions = [
        ('/api/orders/confirm-payment', {'order_id': 'KV261026001', 'amount': 17200000, 'actor': 'Cô Vân (Chủ)'}),
        ('/api/inventory/receipt', {'workshop': 'Xưởng Thạch Thất', 'item': 'Giường gỗ sồi', 'qty': 2, 'cost': 15000000, 'actor': 'Cô Vân (Chủ)'}),
        ('/api/invoices/issue', {'order_id': 'KV261026001', 'actor': 'Cô Vân (Chủ)'}),
        ('/api/webhook/payos', {'order_id': 'KV261026001', 'amount': 17200000})
    ]

    for endpoint, payload in api_actions:
        req = urllib.request.Request(
            f"{attacker.base_url}{endpoint}",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

    # Verify chain after 4 live appends (original 6 + 4 = 10 records)
    status, res = attacker.call_verify_api()
    print(f"  5C (Dynamic appends) -> total_records: {res['total_records']}, valid: {res['valid']}, unbroken_chain: {res['unbroken_chain']}")
    assert status == 200
    assert res['total_records'] == 10
    assert res['valid'] is True
    assert res['unbroken_chain'] is True
    assert res['genesis_valid'] is True

    print("[PASS] Vector 5: Boundary stress & dynamic appends passed 100%.")

def main():
    print("=" * 70)
    print("STARTING EMPIRICAL ADVERSARIAL CHALLENGE ON SHA-256 AUDIT VERIFICATION")
    print("=" * 70)

    attacker = AuditChainAttacker(port=5588)
    try:
        attacker.setup()
        test_baseline_pristine(attacker)
        test_vector_1_bit_flip_tampering(attacker)
        test_vector_2_hash_recomputation(attacker)
        test_vector_3_genesis_poisoning(attacker)
        test_vector_4_intermediate_row_deletions_and_swaps(attacker)
        test_vector_5_edge_cases_and_live_appends(attacker)
        print("\n" + "=" * 70)
        print("ALL 5 ADVERSARIAL ATTACK TEST SUITES PASSED! ZERO DEFECTS FOUND.")
        print("=" * 70)
    finally:
        attacker.teardown()

if __name__ == '__main__':
    main()
