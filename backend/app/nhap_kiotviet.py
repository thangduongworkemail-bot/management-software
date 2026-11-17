"""Nhập danh mục hàng hóa từ file "Danh sách hàng hóa" của KiotViet (CSV) vào hệ thống.

    python -m app.nhap_kiotviet ../data_bo_sung/DanhSachSanPham_KV17112026-230038-395_khoi_phuc.csv --xem-truoc
    python -m app.nhap_kiotviet ../data_bo_sung/DanhSachSanPham_KV17112026-230038-395_khoi_phuc.csv

Mỗi dòng đi qua catalog.tao_bien_the như khi Chủ thêm hàng trên giao diện: giá niêm yết / giá vốn vào lịch sử giá,
tồn kho KiotViet ghi một dòng DIEU_CHINH "tồn đầu kỳ" vào sổ cái, mọi thao tác vào nhật ký có chuỗi băm.
Cả file nhập trong một giao dịch; mã đã có trong hệ thống thì bỏ qua, nên chạy lại nhiều lần vẫn an toàn.
--xem-truoc chạy đầy đủ rồi ROLLBACK để xem trước kết quả.
"""
import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path

from . import db
from .domain.kiotviet import LoiFileKiotViet, MatHangNhap, doc_csv, lap_ke_hoach
from .domain.text import chuan_hoa
from .errors import LoiNghiepVu
from .security import NguoiDung
from .services import audit, catalog

log = logging.getLogger("khanhvan.nhap_kiotviet")

# Cách viết riêng trong tên hàng của cửa hàng -> từ chuẩn, để gõ "sồi", "sập", "sofa" vẫn tìm ra
DONG_NGHIA_KIOTVIET = [("xồi", "sồi"), ("xập", "sập"), ("sopa", "sofa"), ("sopha", "sofa")]


def _loai_hang_cho(conn, m: MatHangNhap, loai: dict) -> dict:
    """Nhóm hàng hệ thống đoán theo tên; không có thì dùng (hoặc tạo) nhóm theo nhóm hàng KiotViet."""
    if m.ma_loai_hang in loai:
        return loai[m.ma_loai_hang]
    ten = m.nhom_kiotviet.split(">>")[-1].strip() or "Hàng KiotViet"
    co = next((l for l in loai.values() if chuan_hoa(l["ten"]) == chuan_hoa(ten)), None)
    if co:
        return co
    ma = "KV_" + re.sub(r"[^A-Z0-9]+", "_", chuan_hoa(ten).upper()).strip("_")
    moi = conn.execute("INSERT INTO loai_hang (ma, ten) VALUES (%s, %s) RETURNING id, ma, ten, don_vi_tinh",
                       (ma, ten)).fetchone()
    loai[ma] = moi
    return moi


def _them_dong_nghia(conn, nguoi: NguoiDung) -> list[str]:
    """Chỉ thêm từ chưa có: không ghi đè từ đồng nghĩa Chủ đã tự đặt."""
    them = []
    for tu_khoa, tu_chuan in DONG_NGHIA_KIOTVIET:
        if not conn.execute("SELECT 1 FROM tu_dong_nghia WHERE tu_khoa_cn = f_chuan_hoa(%s)", (tu_khoa,)).fetchone():
            catalog.them_dong_nghia(conn, nguoi, tu_khoa, tu_chuan)
            them.append(f"{tu_khoa} = {tu_chuan}")
    return them


def nhap(conn, nguoi: NguoiDung, du_lieu: bytes, ten_file: str = "") -> dict:
    """Nhập cả file trong giao dịch của conn (không commit). Trả về báo cáo."""
    loai_go = [r["loai_go"] for r in conn.execute("SELECT loai_go FROM he_so_go")]
    ke_hoach, bo_qua = lap_ke_hoach(doc_csv(du_lieu), loai_go)
    dong_nghia = _them_dong_nghia(conn, nguoi)

    loai = {r["ma"]: r for r in conn.execute("SELECT id, ma, ten, don_vi_tinh FROM loai_hang")}
    da_co = {r["ma_noi_bo"] for r in conn.execute("SELECT ma_noi_bo FROM bien_the WHERE ma_noi_bo = ANY(%s)",
                                                   ([m.ma for m in ke_hoach],))}
    da_nhap, nhom, canh_bao = [], Counter(), []
    for m in ke_hoach:
        if m.ma in da_co:
            bo_qua.append(f"{m.ma}: mã đã có trong hệ thống")
            continue
        lh = _loai_hang_cho(conn, m, loai)
        catalog.tao_bien_the(conn, nguoi, {
            "ma_noi_bo": m.ma, "ten_hien_thi": m.ten_hien_thi, "ten_mau_moi": m.ten_mau, "loai_hang_id": lh["id"],
            "loai_go": m.loai_go, "dai_mm": m.dai_mm, "rong_mm": m.rong_mm, "thuoc_tinh": m.thuoc_tinh,
            # Trùng đơn vị của nhóm thì để trống, như form Sửa thông tin
            "don_vi_tinh": None if m.don_vi_tinh in (None, lh["don_vi_tinh"]) else m.don_vi_tinh,
            "ton_toi_thieu": m.ton_toi_thieu, "mo_ta": m.mo_ta, "anh_url": m.anh_url,
            "gia_niem_yet": m.gia_niem_yet, "gia_von": m.gia_von,
            "ton_ban_dau": m.ton, "ly_do": f"Tồn đầu kỳ chuyển từ KiotViet ({m.ma})",
        })
        da_nhap.append(m.ma)
        nhom[lh["ten"]] += 1
        canh_bao += [f"{m.ma} {m.ten_hien_thi}: {c}" for c in m.canh_bao]

    bao_cao = {"da_nhap": da_nhap, "theo_nhom": dict(nhom), "ton_dau_ky": sum(m.ton for m in ke_hoach if m.ma in da_nhap),
               "so_mau": len({m.ten_mau for m in ke_hoach if m.ma in da_nhap}), "bo_qua": bo_qua,
               "canh_bao": canh_bao, "dong_nghia_moi": dong_nghia}
    if da_nhap:
        audit.ghi(conn, nguoi, "NHAP_KIOTVIET", "BIEN_THE", None,
                  sau={"file": ten_file, "so_mat_hang": len(da_nhap), "ma_dau": da_nhap[0], "ma_cuoi": da_nhap[-1],
                       "bo_qua": len(bo_qua)})
    return bao_cao


def _nguoi_nhap(conn, ten_dang_nhap: str | None) -> NguoiDung:
    if ten_dang_nhap:
        r = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE ten_dang_nhap = %s", (ten_dang_nhap,)).fetchone()
    else:
        r = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE vai_tro = 'CHU' ORDER BY id LIMIT 1").fetchone()
    if not r or r["vai_tro"] != "CHU":
        raise SystemExit("Cần một tài khoản Chủ cửa hàng để ghi nhận người nhập (--tai-khoan)")
    return NguoiDung(id=r["id"], vai_tro=r["vai_tro"], ho_ten=r["ho_ten"])


def _in_bao_cao(bc: dict, xem_truoc: bool) -> None:
    dau = "XEM TRƯỚC (chưa ghi gì)" if xem_truoc else "ĐÃ NHẬP"
    print(f"{dau}: {len(bc['da_nhap'])} mặt hàng, {bc['so_mau']} mẫu, tồn đầu kỳ {bc['ton_dau_ky']} cái")
    for ten, so in bc["theo_nhom"].items():
        print(f"  - {ten}: {so}")
    if bc["dong_nghia_moi"]:
        print("Từ đồng nghĩa mới:", "; ".join(bc["dong_nghia_moi"]))
    if bc["bo_qua"]:
        print(f"Bỏ qua {len(bc['bo_qua'])} dòng:")
        for b in bc["bo_qua"]:
            print("  -", b)
    if bc["canh_bao"]:
        print(f"Cần kiểm tra lại {len(bc['canh_bao'])} chỗ:")
        for c in bc["canh_bao"]:
            print("  -", c)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Nhập danh mục hàng hóa từ file CSV xuất từ KiotViet")
    p.add_argument("file", type=Path)
    p.add_argument("--xem-truoc", action="store_true", help="chạy thử rồi hoàn tác, không ghi gì")
    p.add_argument("--tai-khoan", help="tên đăng nhập của Chủ ghi trong nhật ký (mặc định: Chủ đầu tiên)")
    a = p.parse_args()
    try:
        with db.connect() as conn:   # một giao dịch: commit khi thoát khối, lỗi giữa chừng thì không ghi gì
            bc = nhap(conn, _nguoi_nhap(conn, a.tai_khoan), a.file.read_bytes(), a.file.name)
            if a.xem_truoc:
                conn.rollback()
    except LoiFileKiotViet as e:
        sys.exit(f"Lỗi file, chưa nhập gì: {e}")
    except LoiNghiepVu as e:
        sys.exit(f"Lỗi dữ liệu, chưa nhập gì: {e.thong_bao}")
    _in_bao_cao(bc, a.xem_truoc)
