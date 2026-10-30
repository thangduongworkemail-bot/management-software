"""
Empirical Challenge & Stress Harness for D4_SO_CAI_TON Append-Only Invariant
Milestone: Milestone 1 (Database & Security Hardening)
Agent: m1_challenger_1 (Empirical Challenger)
"""

import sqlite3
import hashlib
import json
import shutil
import sys
import os

DB_PATH = 'khanhvan.db'
BACKUP_PATH = 'khanhvan.db.challenger_bak'

def hash_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien FROM D4_SO_CAI_TON ORDER BY id ASC")
    rows = cur.fetchall()
    serialized = json.dumps([list(r) for r in rows], ensure_ascii=False)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest(), len(rows), rows

def run_challenge():
    print("=" * 80)
    print("EMPIRICAL ADVERSARIAL CHALLENGE: D4_SO_CAI_TON INVARIANT VERIFICATION")
    print("=" * 80)

    # 1. Safety backup of khanhvan.db
    shutil.copyfile(DB_PATH, BACKUP_PATH)
    print(f"[*] Created safety backup: {BACKUP_PATH}")

    results = []

    def record_result(category, test_name, expected, actual, passed, details=""):
        status = "PASS" if passed else "FAIL"
        results.append({
            "category": category,
            "test_name": test_name,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "details": details
        })
        print(f"[{status}] {category:14} | {test_name:38} | {details}")

    # Baseline check
    conn_base = sqlite3.connect(DB_PATH)
    base_hash, base_count, base_rows = hash_table(conn_base)
    conn_base.close()
    print(f"[*] Baseline D4_SO_CAI_TON: count={base_count}, sha256={base_hash[:16]}...\n")

    try:
        # =========================================================================
        # SUITE 1: Direct UPDATE Attacks (Under PRAGMA recursive_triggers = ON)
        # =========================================================================
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA recursive_triggers = ON")

        # 1.1 Single-row UPDATE on primary key (id)
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET id = 999 WHERE id = 1")
            record_result("UPDATE", "Update Primary Key id", "Abort", "Allowed", False, "Vulnerability: Primary key modified")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Update Primary Key id", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.2 Single-row UPDATE on quantity (bien_dong)
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 9999 WHERE id = 1")
            record_result("UPDATE", "Update bien_dong", "Abort", "Allowed", False, "Vulnerability: bien_dong modified")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Update bien_dong", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.3 Single-row UPDATE on loai_dong
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET loai_dong = 'TAMPERED' WHERE id = 1")
            record_result("UPDATE", "Update loai_dong", "Abort", "Allowed", False, "Vulnerability: loai_dong modified")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Update loai_dong", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.4 Single-row UPDATE on tham_chieu & nguoi_thuc_hien
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET tham_chieu = 'HACKED', nguoi_thuc_hien = 'HACKER' WHERE id = 2")
            record_result("UPDATE", "Update reference & user", "Abort", "Allowed", False, "Vulnerability: reference modified")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Update reference & user", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.5 Bulk UPDATE on all rows
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 0")
            record_result("UPDATE", "Bulk UPDATE all rows", "Abort", "Allowed", False, "Vulnerability: Bulk update succeeded")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Bulk UPDATE all rows", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.6 Complex subquery UPDATE
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = (SELECT COUNT(*) FROM D3_DON_HANG) WHERE id = 1")
            record_result("UPDATE", "Complex subquery UPDATE", "Abort", "Allowed", False, "Vulnerability: Subquery UPDATE executed")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "Complex subquery UPDATE", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.7 Conditional CASE statement UPDATE
        try:
            conn.execute("UPDATE D4_SO_CAI_TON SET bien_dong = CASE WHEN bien_dong > 0 THEN 0 ELSE 1 END WHERE id = 2")
            record_result("UPDATE", "CASE statement UPDATE", "Abort", "Allowed", False, "Vulnerability: CASE statement UPDATE executed")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "CASE statement UPDATE", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 1.8 UPSERT (INSERT ... ON CONFLICT DO UPDATE)
        try:
            conn.execute("""
                INSERT INTO D4_SO_CAI_TON (id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, bien_dong, loai_ton, nguoi_thuc_hien)
                VALUES (1, '2026-10-28 00:00:00', 'TAMPER', 'P', 'N', 1, 'KHA_DUNG', 'HACKER')
                ON CONFLICT(id) DO UPDATE SET bien_dong = 999
            """)
            record_result("UPDATE", "UPSERT ON CONFLICT DO UPDATE", "Abort", "Allowed", False, "Vulnerability: UPSERT succeeded")
        except sqlite3.IntegrityError as e:
            record_result("UPDATE", "UPSERT ON CONFLICT DO UPDATE", "Abort", "IntegrityError", True, f"Blocked: {e}")

        conn.close()

        # =========================================================================
        # SUITE 2: Direct DELETE Attacks (Under PRAGMA recursive_triggers = ON)
        # =========================================================================
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA recursive_triggers = ON")

        # 2.1 Single-row DELETE by ID
        try:
            conn.execute("DELETE FROM D4_SO_CAI_TON WHERE id = 1")
            record_result("DELETE", "Single-row DELETE by id", "Abort", "Allowed", False, "Vulnerability: Single row deleted")
        except sqlite3.IntegrityError as e:
            record_result("DELETE", "Single-row DELETE by id", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 2.2 Conditional multi-row DELETE
        try:
            conn.execute("DELETE FROM D4_SO_CAI_TON WHERE bien_dong > 0")
            record_result("DELETE", "Conditional multi-row DELETE", "Abort", "Allowed", False, "Vulnerability: Rows deleted")
        except sqlite3.IntegrityError as e:
            record_result("DELETE", "Conditional multi-row DELETE", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 2.3 Unconditional bulk DELETE
        try:
            conn.execute("DELETE FROM D4_SO_CAI_TON")
            record_result("DELETE", "Bulk DELETE all rows", "Abort", "Allowed", False, "Vulnerability: Table truncated")
        except sqlite3.IntegrityError as e:
            record_result("DELETE", "Bulk DELETE all rows", "Abort", "IntegrityError", True, f"Blocked: {e}")

        # 2.4 Subquery DELETE
        try:
            conn.execute("DELETE FROM D4_SO_CAI_TON WHERE id IN (SELECT id FROM D4_SO_CAI_TON WHERE id <= 3)")
            record_result("DELETE", "Subquery DELETE", "Abort", "Allowed", False, "Vulnerability: Subquery DELETE succeeded")
        except sqlite3.IntegrityError as e:
            record_result("DELETE", "Subquery DELETE", "Abort", "IntegrityError", True, f"Blocked: {e}")

        conn.close()

        # =========================================================================
        # SUITE 3: INSERT OR REPLACE & REPLACE INTO Attacks
        # =========================================================================
        # 3.1 With server.py connection profile (recursive_triggers = ON)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA recursive_triggers = ON")

        try:
            conn.execute("""
                INSERT OR REPLACE INTO D4_SO_CAI_TON (id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, bien_dong, loai_ton, nguoi_thuc_hien)
                VALUES (1, '2026-10-28 00:00:00', 'TAMPER', 'SP-TAMPER', 'Tampered Product', 999, 'KHA_DUNG', 'hacker@khanhvan.vn')
            """)
            record_result("REPLACE", "INSERT OR REPLACE (recursive_triggers=ON)", "Abort", "Allowed", False, "Vulnerability: INSERT OR REPLACE overwritten row 1")
        except sqlite3.IntegrityError as e:
            record_result("REPLACE", "INSERT OR REPLACE (recursive_triggers=ON)", "Abort", "IntegrityError", True, f"Blocked by recursive DELETE trigger: {e}")

        try:
            conn.execute("""
                REPLACE INTO D4_SO_CAI_TON (id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, bien_dong, loai_ton, nguoi_thuc_hien)
                VALUES (2, '2026-10-28 00:00:00', 'TAMPER', 'SP-TAMPER', 'Tampered Product', 999, 'KHA_DUNG', 'hacker@khanhvan.vn')
            """)
            record_result("REPLACE", "REPLACE INTO (recursive_triggers=ON)", "Abort", "Allowed", False, "Vulnerability: REPLACE INTO overwritten row 2")
        except sqlite3.IntegrityError as e:
            record_result("REPLACE", "REPLACE INTO (recursive_triggers=ON)", "Abort", "IntegrityError", True, f"Blocked by recursive DELETE trigger: {e}")

        conn.close()

        # 3.2 With SQLite default connection profile (recursive_triggers = OFF)
        conn_off = sqlite3.connect(DB_PATH)
        conn_off.isolation_level = None
        try:
            conn_off.execute("BEGIN TRANSACTION")
            conn_off.execute("""
                INSERT OR REPLACE INTO D4_SO_CAI_TON (id, thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, bien_dong, loai_ton, nguoi_thuc_hien)
                VALUES (3, '2026-10-28 00:00:00', 'TAMPER', 'SP-TAMPER', 'Tampered Product', 999, 'KHA_DUNG', 'hacker@khanhvan.vn')
            """)
            conn_off.execute("ROLLBACK")
            record_result("REPLACE", "INSERT OR REPLACE (recursive_triggers=OFF)", "Blocked", "Allowed", False,
                          "CAVEAT: SQLite default connection (recursive_triggers=OFF) permits REPLACE conflict resolution to delete row without triggering trg_d4_prevent_delete")
        except sqlite3.IntegrityError as e:
            conn_off.execute("ROLLBACK")
            record_result("REPLACE", "INSERT OR REPLACE (recursive_triggers=OFF)", "Blocked", "IntegrityError", True, f"Blocked: {e}")
        finally:
            conn_off.close()

        # =========================================================================
        # SUITE 4: Multi-Statement Transaction Atomicity & Batch Execution
        # =========================================================================
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA recursive_triggers = ON")
        conn.isolation_level = None

        # 4.1 Multi-statement transaction rollback upon trigger abort
        try:
            conn.execute("BEGIN TRANSACTION")
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, bien_dong, loai_ton, nguoi_thuc_hien)
                VALUES ('2026-10-28 20:00:00', 'NHAP', 'SP-TX-TEST', 'Tx Test Item', 10, 'HIEN_CO', 'test@khanhvan.vn')
            """)
            # Illegal update triggers abort
            cur.execute("UPDATE D4_SO_CAI_TON SET bien_dong = 999 WHERE id = 1")
            conn.execute("COMMIT")
            record_result("TRANSACTION", "TX Rollback on Abort", "Rollback", "Committed", False, "Vulnerability: Transaction committed despite illegal update")
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK")
            cur.execute("SELECT count(*) FROM D4_SO_CAI_TON WHERE ma_bien_the = 'SP-TX-TEST'")
            orphans = cur.fetchone()[0]
            if orphans == 0:
                record_result("TRANSACTION", "TX Rollback on Abort", "Rollback", "Clean Rollback", True, "Trigger abort cleanly rolled back; zero orphaned rows")
            else:
                record_result("TRANSACTION", "TX Rollback on Abort", "Rollback", "Orphaned Rows", False, f"Trigger aborted but {orphans} rows remained")

        # 4.2 Batch executescript injection
        try:
            conn.executescript("""
                UPDATE D4_SO_CAI_TON SET bien_dong = 0 WHERE id = 1;
                DELETE FROM D4_SO_CAI_TON WHERE id = 2;
            """)
            record_result("TRANSACTION", "Batch executescript injection", "Abort", "Allowed", False, "Vulnerability: Batch execution succeeded")
        except sqlite3.IntegrityError as e:
            record_result("TRANSACTION", "Batch executescript injection", "Abort", "IntegrityError", True, f"Blocked during batch execution: {e}")

        conn.close()

        # =========================================================================
        # SUITE 5: Legitimate Append Operations (Positive Invariant)
        # =========================================================================
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA recursive_triggers = ON")
        new_id = None
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO D4_SO_CAI_TON (thoi_diem, loai_dong, ma_bien_the, ten_mat_hang, xuong_cung_cap, bien_dong, loai_ton, tham_chieu, nguoi_thuc_hien)
                VALUES ('2026-10-28 19:55:00', 'NHAP', 'SP-BAN-THO-MIT-01', 'Bàn thờ Gỗ Mít Cát Đằng', 'Xưởng Đồng Kỵ', 5, 'HIEN_CO', 'Phiếu nhập #PN261028001', 'challenger_test@khanhvan.vn')
            """)
            new_id = cur.lastrowid
            conn.commit()
            record_result("APPEND", "Valid append operation", "Success", f"Success (id={new_id})", True, f"Valid append succeeded with assigned id={new_id}")
        except Exception as e:
            record_result("APPEND", "Valid append operation", "Success", type(e).__name__, False, f"Append failed unexpectedly: {e}")

        if new_id:
            try:
                conn.execute(f"UPDATE D4_SO_CAI_TON SET bien_dong = 999 WHERE id = {new_id}")
                record_result("IMMUTABILITY", "Update newly appended row", "Abort", "Allowed", False, "Vulnerability: Newly appended row modified")
            except sqlite3.IntegrityError as e:
                record_result("IMMUTABILITY", "Update newly appended row", "Abort", "IntegrityError", True, f"Blocked: {e}")

            try:
                conn.execute(f"DELETE FROM D4_SO_CAI_TON WHERE id = {new_id}")
                record_result("IMMUTABILITY", "Delete newly appended row", "Abort", "Allowed", False, "Vulnerability: Newly appended row deleted")
            except sqlite3.IntegrityError as e:
                record_result("IMMUTABILITY", "Delete newly appended row", "Abort", "IntegrityError", True, f"Blocked: {e}")

        conn.close()

    finally:
        # Restore the database from backup so khanhvan.db remains in its pristine worker handoff state!
        shutil.copyfile(BACKUP_PATH, DB_PATH)
        os.remove(BACKUP_PATH)
        print("\n[*] Restored khanhvan.db to pristine baseline state (clean cleanup)")

    conn_final = sqlite3.connect(DB_PATH)
    final_hash, final_count, _ = hash_table(conn_final)
    conn_final.close()

    assert final_hash == base_hash, "Database hash mismatch after cleanup!"
    assert final_count == base_count, "Database row count mismatch after cleanup!"
    print(f"[*] Verified khanhvan.db pristine integrity: count={final_count}, hash={final_hash[:16]}... OK")

    print("\n" + "=" * 80)
    print("EMPIRICAL CHALLENGE SUMMARY")
    print("=" * 80)
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['passed'])
    findings = [r for r in results if not r['passed']]
    print(f"Total Probes Executed: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Adversarial Caveats / Findings: {len(findings)}")
    for f in findings:
        print(f" -> [{f['category']}] {f['test_name']}: {f['details']}")

    output_report = {
        "total_probes": total_tests,
        "passed": passed_tests,
        "findings_count": len(findings),
        "results": results
    }
    with open("tests/challenge_results.json", "w", encoding="utf-8") as f:
        json.dump(output_report, f, indent=2, ensure_ascii=False)
    print("[*] Saved results to tests/challenge_results.json\n")

    return results

if __name__ == "__main__":
    run_challenge()
