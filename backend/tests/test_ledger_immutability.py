"""Sổ cái tồn kho và nhật ký chỉ ghi thêm; chuỗi băm phát hiện được mọi chỉnh sửa lén."""
import psycopg
import pytest

from app.services import audit, inventory

from .conftest import id_bien_the, ton


def _bi_chan(conn, cau_lenh, ma_loi="KV001"):
    with pytest.raises(psycopg.Error) as e:
        with conn.transaction():  # savepoint: giao dịch ngoài vẫn dùng tiếp được
            conn.execute(cau_lenh)
    assert e.value.sqlstate == ma_loi, e.value
    return e.value


@pytest.mark.parametrize("bang", ["so_cai_ton", "nhat_ky"])
def test_chan_update(conn, bang):
    cot = "so_luong = so_luong + 1" if bang == "so_cai_ton" else "hanh_dong = 'SUA_LEN'"
    loi = _bi_chan(conn, f"UPDATE {bang} SET {cot} WHERE id = (SELECT min(id) FROM {bang})")
    assert "chỉ cho phép ghi thêm" in loi.diag.message_primary


@pytest.mark.parametrize("bang", ["so_cai_ton", "nhat_ky"])
def test_chan_delete(conn, bang):
    _bi_chan(conn, f"DELETE FROM {bang} WHERE id = (SELECT min(id) FROM {bang})")


@pytest.mark.parametrize("bang", ["so_cai_ton", "nhat_ky"])
def test_chan_truncate(conn, bang):
    _bi_chan(conn, f"TRUNCATE {bang} CASCADE")


def test_van_cho_phep_insert_va_ton_tinh_tu_so_cai(conn, chu):
    bt = id_bien_the(conn, "KE-TIVI-MDF-1800")
    truoc = ton(conn, "KE-TIVI-MDF-1800")
    inventory.ghi_so_cai(conn, bt, "NHAP", 3, nguoi=chu, tham_chieu="test")
    inventory.ghi_so_cai(conn, bt, "DIEU_CHINH", -1, nguoi=chu, ly_do="Kiểm kê thiếu")
    sau = ton(conn, "KE-TIVI-MDF-1800")
    assert sau["ton_hien_co"] == truoc["ton_hien_co"] + 2
    assert sau["ton_kha_dung"] == truoc["ton_kha_dung"] + 2


@pytest.mark.parametrize("loai, so_luong", [("NHAP", -1), ("XUAT", 1), ("GIU_CHO", -2), ("NHA_CHO", 1), ("NHAP", 0)])
def test_rang_buoc_dau_so_luong(conn, loai, so_luong):
    bt = id_bien_the(conn, "KE-TIVI-MDF-1800")
    don = conn.execute("SELECT id FROM don_hang LIMIT 1").fetchone()["id"]
    _bi_chan(conn, f"INSERT INTO so_cai_ton (bien_the_id, loai, so_luong, don_hang_id) "
                   f"VALUES ({bt}, '{loai}', {so_luong}, {don})", ma_loi="23514")


def test_dieu_chinh_bat_buoc_ly_do(conn):
    bt = id_bien_the(conn, "KE-TIVI-MDF-1800")
    _bi_chan(conn, f"INSERT INTO so_cai_ton (bien_the_id, loai, so_luong) VALUES ({bt}, 'DIEU_CHINH', 1)",
             ma_loi="23514")


def test_chuoi_bam_nhat_ky_toan_ven_sau_seed(conn):
    assert audit.kiem_tra_chuoi(conn) == []
    dong = conn.execute("SELECT prev_hash, current_hash FROM nhat_ky ORDER BY id LIMIT 2").fetchall()
    assert dong[0]["prev_hash"] == "0" * 64
    assert dong[1]["prev_hash"] == dong[0]["current_hash"]


def test_trigger_tu_tinh_bam_khong_tin_gia_tri_client(conn, chu):
    r = conn.execute("""INSERT INTO nhat_ky (ten_nguoi_thuc_hien, hanh_dong, thuc_the, prev_hash, current_hash)
                        VALUES ('Kẻ gian', 'GIA_MAO', 'X', %s, %s) RETURNING prev_hash, current_hash""",
                     ("f" * 64, "e" * 64)).fetchone()
    assert r["current_hash"] != "e" * 64 and r["prev_hash"] != "f" * 64
    assert audit.kiem_tra_chuoi(conn) == []


def test_phat_hien_sua_len_khi_vo_hieu_trigger(conn):
    # Kẻ có quyền chủ bảng tắt trigger để sửa dữ liệu: job kiểm tra vẫn phát hiện được
    conn.execute("ALTER TABLE nhat_ky DISABLE TRIGGER nhat_ky_chan_sua_xoa")
    muc_tieu = conn.execute("SELECT id FROM nhat_ky WHERE hanh_dong = 'XAC_NHAN_TIEN_TAY' LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE nhat_ky SET du_lieu_sau = '{\"so_tien\": 1}' WHERE id = %s", (muc_tieu,))
    loi = audit.kiem_tra_chuoi(conn)
    assert [r["nhat_ky_id"] for r in loi] == [muc_tieu]
    assert "current_hash" in loi[0]["ly_do"]


def test_xoa_dong_giua_chuoi_bi_phat_hien(conn):
    conn.execute("ALTER TABLE nhat_ky DISABLE TRIGGER nhat_ky_chan_sua_xoa")
    ids = [r["id"] for r in conn.execute("SELECT id FROM nhat_ky ORDER BY id LIMIT 3").fetchall()]
    conn.execute("DELETE FROM nhat_ky WHERE id = %s", (ids[1],))
    loi = audit.kiem_tra_chuoi(conn)
    assert loi and loi[0]["nhat_ky_id"] == ids[2] and "prev_hash" in loi[0]["ly_do"]


def test_lich_su_gia_khong_ghi_de(conn):
    gia = conn.execute("SELECT id FROM gia_hieu_luc WHERE den_ngay IS NULL LIMIT 1").fetchone()["id"]
    _bi_chan(conn, f"UPDATE gia_hieu_luc SET so_tien = 1 WHERE id = {gia}", ma_loi="KV002")
    _bi_chan(conn, f"DELETE FROM gia_hieu_luc WHERE id = {gia}", ma_loi="KV002")


def test_dong_don_la_ban_chup(conn):
    dong = conn.execute("SELECT id FROM dong_don LIMIT 1").fetchone()["id"]
    _bi_chan(conn, f"UPDATE dong_don SET don_gia_ban = 1, thanh_tien = so_luong WHERE id = {dong}", ma_loi="KV002")
    _bi_chan(conn, f"DELETE FROM dong_don WHERE id = {dong}", ma_loi="KV002")


def test_tien_va_kich_thuoc_khong_am(conn):
    bt = id_bien_the(conn, "KE-TIVI-MDF-1800")
    _bi_chan(conn, f"UPDATE bien_the SET dai_mm = -1 WHERE id = {bt}", ma_loi="23514")
    _bi_chan(conn, "UPDATE khach_hang SET du_no = -5", ma_loi="23514")
    _bi_chan(conn, f"INSERT INTO gia_hieu_luc (bien_the_id, loai_gia, so_tien, den_ngay) "
                   f"VALUES ({bt}, 'GIA_VON', -100, now())", ma_loi="23514")
