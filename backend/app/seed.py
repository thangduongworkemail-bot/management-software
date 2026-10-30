"""Dữ liệu mẫu bám sát báo cáo, nạp qua chính các service nghiệp vụ để sổ cái, giá vốn
bình quân, công nợ và chuỗi băm nhật ký đều nhất quán như khi vận hành thật."""
import logging
from datetime import date, datetime

from psycopg.types.json import Jsonb

from . import db
from .adapters.payment import GiaoDichVao
from .security import NguoiDung, hash_mat_khau, tao_khoa_ky
from .services import catalog, codes, inventory, orders, payments

log = logging.getLogger("khanhvan.seed")

TAI_KHOAN = [
    ("covan", "Nguyễn Thị Vân (Cô Vân)", "CHU", "KhanhVan@2026"),
    ("anhnam", "Trần Văn Nam (Anh Nam)", "THO", "AnhNam@2026"),
    ("admin", "Quản trị viên hệ thống", "QUAN_TRI", "Admin@2026"),
]

HE_SO_GO = [("Sồi", 1000), ("Mít", 1200), ("Gõ đỏ", 1500), ("Xoan đào", 1100), ("Óc chó", 1400), ("MDF", 600)]

# Thuộc tính mẫu theo nhóm hàng: khóa là nhãn hiển thị, giá trị mặc định quyết định kiểu ô nhập
# (chữ / số / có-không). Biến thể mới của nhóm được điền sẵn các khóa này.
LOAI_HANG = [
    ("DO_THO", "Đồ thờ", "cái", {"Hoa văn": "", "Số tầng": 1, "Kiểu chân": "", "Có ngăn kéo": False}),
    ("GIUONG", "Giường", "cái", {"Kiểu dáng": "", "Có ngăn kéo": False, "Kích thước nệm": "", "Đầu giường": "",
                                 "Chiều cao gầm (mm)": 0}),
    ("TU_KE", "Tủ / Kệ", "cái", {"Số cánh": 2, "Số ngăn kéo": 0, "Có gương": False}),
    ("BAN_GHE", "Bàn ghế", "cái", {"Số chỗ ngồi": 0, "Kiểu mặt bàn": "", "Có đệm": False}),
    ("GO_CN", "Gỗ công nghiệp", "cái", {"Bề mặt": "Melamine", "Số cánh": 0, "Số ngăn kéo": 0, "Chống ẩm": False}),
]

XUONG = [
    ("CAT_DANG", "Xưởng Đồ Thờ Cát Đẳng", "Ông Hùng — Ý Yên, Nam Định", "0912000111", "Đồ thờ, án gian"),
    ("HAI_HAU", "Xưởng Giường & Bàn Ghế Hải Hậu", "Anh Quân — Hải Hậu, Nam Định", "0913000222", "Giường, bàn ghế"),
    ("MDF", "Kho Gỗ Công Nghiệp MDF", "Chị Lan — Thái Nguyên", "0914000333", "Tủ, kệ gỗ công nghiệp"),
]

# (loại, tên mẫu, thuộc tính, [biến thể])
# biến thể: (mã, tên, gỗ, dài, rộng, cao, màu, đặt riêng, tồn tối thiểu, (giá sàn, niêm yết) | None)
MAU_HANG = [
    ("DO_THO", "Tủ thờ chạm sen", {"Hoa văn": "Chạm sen", "Số tầng": 2}, [
        ("TUTHO-MIT-1270", "Tủ thờ Gỗ Mít chạm sen (cao 1270mm, đặt theo mét dài)", "Mít", None, 610, 1270, "Cánh gián",
         True, 0, None),
        ("TUTHO-MIT-1760", "Tủ thờ Gỗ Mít chạm sen 1m76", "Mít", 1760, 610, 1270, "Cánh gián", False, 2,
         (4_400_000, 4_900_000)),
    ]),
    ("DO_THO", "Án gian thờ", {"Hoa văn": "Tứ linh", "Số tầng": 1}, [
        ("ANGIAN-GODO-1970", "Án gian Gỗ Gõ đỏ 1m97 chạm tứ linh", "Gõ đỏ", 1970, 810, 1270, "Nâu đỏ", False, 2,
         (6_300_000, 6_900_000)),
    ]),
    ("GIUONG", "Giường hộp gỗ Sồi Nga", {"Kiểu dáng": "Hộp", "Có ngăn kéo": True}, [
        ("GUONG-HOP-SOI-1800", "Giường hộp Gỗ Sồi Nga 1m8 × 2m (màu óc chó)", "Sồi", 2000, 1800, 350, "Óc chó",
         False, 2, (8_100_000, 8_500_000)),
        ("GUONG-HOP-SOI-1600", "Giường hộp Gỗ Sồi Nga 1m6 × 2m (màu óc chó)", "Sồi", 2000, 1600, 350, "Óc chó",
         False, 2, (7_400_000, 7_800_000)),
        ("GUONG-HOP-SOI-DATRIENG", "Giường hộp Gỗ Sồi Nga — đặt theo bậc kích thước", "Sồi", 2000, None, 350,
         "Óc chó", True, 0, None),
    ]),
    ("BAN_GHE", "Bộ bàn ăn gỗ Sồi", {"Số chỗ ngồi": 6}, [
        ("BAN-AN-SOI-1600x800", "Bàn ăn Gỗ Sồi 1600×800mm", "Sồi", 1600, 800, 750, "Tự nhiên", False, 2,
         (7_000_000, 7_500_000)),
        ("GHE-AN-SOI", "Ghế ăn Gỗ Sồi tựa lưng cong", "Sồi", 450, 450, 950, "Tự nhiên", False, 6,
         (1_500_000, 1_750_000)),
    ]),
    ("BAN_GHE", "Mặt bàn gỗ ghép", {"Kiểu mặt bàn": "Ghép thanh"}, [
        ("MATBAN-GODO-DATRIENG", "Mặt bàn Gỗ Gõ đỏ ghép thanh — đặt theo m²", "Gõ đỏ", None, None, 40, "Nâu đỏ",
         True, 0, None),
    ]),
    ("GO_CN", "Tủ quần áo MDF 4 cánh", {"Bề mặt": "Melamine chống ẩm", "Số cánh": 4, "Chống ẩm": True}, [
        ("TU-AO-MDF-4C", "Tủ quần áo MDF 4 cánh 1m6", "MDF", 1600, 550, 2000, "Trắng vân gỗ", False, 2,
         (4_600_000, 5_200_000)),
    ]),
    ("GO_CN", "Kệ tivi MDF", {"Bề mặt": "Melamine", "Số ngăn kéo": 2}, [
        ("KE-TIVI-MDF-1800", "Kệ tivi MDF 1m8 hai ngăn kéo", "MDF", 1800, 400, 450, "Óc chó", False, 2,
         (2_200_000, 2_600_000)),
    ]),
]

# Thông số chi tiết: (hoàn thiện, kiểu dáng, vật liệu/phụ kiện, xuất xứ, khối lượng kg, bảo hành tháng,
#                    thuộc tính riêng bổ sung)
CHI_TIET = {
    "TUTHO-MIT-1270": ("Sơn PU bóng mờ", "Cổ điển", "Bản lề đồng", "Ý Yên, Nam Định", None, 24,
                       {"Kiểu chân": "Chân quỳ", "Có ngăn kéo": True}),
    "TUTHO-MIT-1760": ("Sơn PU bóng mờ", "Cổ điển", "Bản lề đồng", "Ý Yên, Nam Định", 95, 24,
                       {"Kiểu chân": "Chân quỳ", "Có ngăn kéo": True}),
    "ANGIAN-GODO-1970": ("Lau dầu (vecni)", "Cổ điển", None, "Ý Yên, Nam Định", 140, 36,
                         {"Kiểu chân": "Chân quỳ dạ cá", "Có ngăn kéo": False}),
    "GUONG-HOP-SOI-1800": ("Sơn PU màu óc chó", "Hiện đại", "Ray trượt ngăn kéo giảm chấn", "Hải Hậu, Nam Định",
                           85, 24, {"Kích thước nệm": "1m8 × 2m", "Đầu giường": "Bọc nỉ", "Chiều cao gầm (mm)": 0}),
    "GUONG-HOP-SOI-1600": ("Sơn PU màu óc chó", "Hiện đại", "Ray trượt ngăn kéo giảm chấn", "Hải Hậu, Nam Định",
                           76, 24, {"Kích thước nệm": "1m6 × 2m", "Đầu giường": "Bọc nỉ", "Chiều cao gầm (mm)": 0}),
    "GUONG-HOP-SOI-DATRIENG": ("Sơn PU màu óc chó", "Hiện đại", "Ray trượt ngăn kéo giảm chấn", "Hải Hậu, Nam Định",
                               None, 24, {"Đầu giường": "Bọc nỉ"}),
    "BAN-AN-SOI-1600x800": ("Sơn PU tự nhiên", "Hiện đại", None, "Hải Hậu, Nam Định", 42, 12,
                            {"Kiểu mặt bàn": "Chữ nhật, bo góc"}),
    "GHE-AN-SOI": ("Sơn PU tự nhiên", "Hiện đại", "Đệm mút bọc da PU", "Hải Hậu, Nam Định", 6, 12,
                   {"Số chỗ ngồi": 1, "Có đệm": True}),
    "MATBAN-GODO-DATRIENG": ("Lau dầu (vecni)", "Hiện đại", None, "Hải Hậu, Nam Định", None, 12,
                             {"Kiểu mặt bàn": "Ghép thanh"}),
    "TU-AO-MDF-4C": ("Melamine chống ẩm", "Hiện đại", "Bản lề giảm chấn Hafele, gương soi cánh giữa", "Thái Nguyên",
                     120, 12, {"Bề mặt": "Melamine chống ẩm", "Số cánh": 4, "Số ngăn kéo": 2, "Có gương": True,
                               "Chống ẩm": True}),
    "KE-TIVI-MDF-1800": ("Melamine", "Hiện đại", "Ray bi giảm chấn", "Thái Nguyên", 35, 12,
                         {"Bề mặt": "Melamine", "Số cánh": 0, "Số ngăn kéo": 2}),
}

CONG_THUC = {
    "TUTHO-MIT-1270": dict(kieu="THEO_CHIEU_DAI", don_gia=1_850_000, phu_phi=0, bac_gia=[],
                           kich_thuoc_min_mm=1000, kich_thuoc_max_mm=3000, von=657, san=779),
    "GUONG-HOP-SOI-DATRIENG": dict(kieu="THEO_BAC", don_gia=None, phu_phi=0,
                                   bac_gia=[{"toi_da_mm": 1600, "gia": 7_800_000}, {"toi_da_mm": 1800, "gia": 8_500_000},
                                            {"toi_da_mm": 2200, "gia": 10_200_000}],
                                   kich_thuoc_min_mm=1200, kich_thuoc_max_mm=2200, von=800, san=950),
    "MATBAN-GODO-DATRIENG": dict(kieu="THEO_DIEN_TICH", don_gia=3_200_000, phu_phi=300_000, bac_gia=[],
                                 kich_thuoc_min_mm=400, kich_thuoc_max_mm=3000, von=620, san=780),
}

# (xưởng, mã biến thể, mã hàng của xưởng, giá nhập, số ngày giao)
MA_XUONG = [
    ("CAT_DANG", "TUTHO-MIT-1270", "CD-TT-SEN", 0, 10), ("CAT_DANG", "TUTHO-MIT-1760", "CD-TT-176", 3_600_000, 7),
    ("CAT_DANG", "ANGIAN-GODO-1970", "CD-AG-197", 5_200_000, 7),
    ("HAI_HAU", "GUONG-HOP-SOI-1800", "HH-GH18", 6_800_000, 5), ("HAI_HAU", "GUONG-HOP-SOI-1600", "HH-GH16", 6_200_000, 5),
    ("HAI_HAU", "GUONG-HOP-SOI-DATRIENG", "HH-GH-DR", 0, 12), ("HAI_HAU", "BAN-AN-SOI-1600x800", "HH-BA16", 6_000_000, 5),
    ("HAI_HAU", "GHE-AN-SOI", "HH-GA", 1_300_000, 5), ("HAI_HAU", "MATBAN-GODO-DATRIENG", "HH-MB-DR", 0, 10),
    ("MDF", "TU-AO-MDF-4C", "MDF-TA4C", 3_900_000, 3), ("MDF", "KE-TIVI-MDF-1800", "MDF-KTV18", 1_800_000, 3),
]

PHIEU_NHAP = [
    ("CAT_DANG", [("TUTHO-MIT-1760", 1, 3_600_000), ("ANGIAN-GODO-1970", 2, 5_200_000)]),
    ("HAI_HAU", [("GUONG-HOP-SOI-1800", 5, 6_800_000), ("GUONG-HOP-SOI-1600", 4, 6_200_000),
                 ("BAN-AN-SOI-1600x800", 4, 6_000_000), ("GHE-AN-SOI", 24, 1_300_000)]),
    ("MDF", [("TU-AO-MDF-4C", 6, 3_900_000), ("KE-TIVI-MDF-1800", 8, 1_800_000)]),
]

DONG_NGHIA = [("tủ áo", "tủ quần áo"), ("xoan", "xoan đào"), ("kệ ti vi", "kệ tivi"), ("bàn thờ", "tủ thờ"),
              ("ghế ăn", "ghế ăn"), ("gỗ gõ", "gõ đỏ")]

KHACH_HANG = [
    ("Cty TNHH Xây dựng Thái Nguyên", "02083851234", "4601234567", "ketoan@xdthainguyen.vn", "Phường Hoàng Văn Thụ, TP. Thái Nguyên"),
    ("Chị Hoa (Phổ Yên)", "0987654321", None, None, "Phổ Yên, Thái Nguyên"),
    ("Anh Tuấn (Đồng Hỷ)", "0966111222", None, None, "Đồng Hỷ, Thái Nguyên"),
]


def bo_sung_chi_tiet(conn) -> int:
    """Điền thông số chi tiết + thuộc tính mẫu của nhóm cho dữ liệu mẫu. Chỉ chạm vào biến thể chưa
    có thông số (hoan_thien trống), nên chạy lại trên CSDL đang dùng không ghi đè thông tin Chủ đã sửa."""
    for ma, _ten, _dvt, mau in LOAI_HANG:
        conn.execute("UPDATE loai_hang SET thuoc_tinh_mau = %s || thuoc_tinh_mau WHERE ma = %s", (Jsonb(mau), ma))
    so_dong = 0
    for ma, (hoan_thien, kieu_dang, vat_lieu, xuat_xu, kg, bao_hanh, them) in CHI_TIET.items():
        so_dong += conn.execute(
            """UPDATE bien_the bt SET hoan_thien = %s, kieu_dang = %s, vat_lieu_phu = %s, xuat_xu = %s,
                                     khoi_luong_kg = %s, bao_hanh_thang = %s,
                                     thuoc_tinh = l.thuoc_tinh_mau || bt.thuoc_tinh || %s
               FROM mau_hang m JOIN loai_hang l ON l.id = m.loai_hang_id
               WHERE m.id = bt.mau_hang_id AND bt.ma_noi_bo = %s AND bt.hoan_thien IS NULL""",
            (hoan_thien, kieu_dang, vat_lieu, xuat_xu, kg, bao_hanh, Jsonb(them), ma)).rowcount
    return so_dong


def nap(url: str | None = None) -> None:
    with db.connect(url) as conn:
        with conn.transaction():
            _nap(conn)
    log.info("Đã nạp dữ liệu mẫu")


def _nap(conn) -> None:
    nguoi = {}
    for ten_dn, ho_ten, vai_tro, mk in TAI_KHOAN:
        r = conn.execute("INSERT INTO tai_khoan (ten_dang_nhap, ho_ten, vai_tro, mat_khau_hash) VALUES (%s, %s, %s, %s) "
                         "RETURNING id", (ten_dn, ho_ten, vai_tro, hash_mat_khau(mk))).fetchone()
        nguoi[ten_dn] = NguoiDung(id=r["id"], vai_tro=vai_tro, ho_ten=ho_ten)
    co_van, anh_nam = nguoi["covan"], nguoi["anhnam"]

    conn.cursor().executemany("INSERT INTO he_so_go (loai_go, he_so_phan_nghin) VALUES (%s, %s)", HE_SO_GO)
    loai = {}
    for ma, ten, dvt, mau in LOAI_HANG:
        loai[ma] = conn.execute("INSERT INTO loai_hang (ma, ten, don_vi_tinh, thuoc_tinh_mau) VALUES (%s, %s, %s, %s) "
                                "RETURNING id", (ma, ten, dvt, Jsonb(mau))).fetchone()["id"]
    xuong = {}
    for ma, ten, lien_he, sdt, loai_hang in XUONG:
        xuong[ma] = conn.execute("INSERT INTO nha_cung_cap (ma, ten, lien_he, so_dien_thoai, loai_hang) "
                                 "VALUES (%s, %s, %s, %s, %s) RETURNING id", (ma, ten, lien_he, sdt, loai_hang)
                                 ).fetchone()["id"]

    bien_the = {}
    for ma_loai, ten_mau, thuoc_tinh, ds in MAU_HANG:
        mau_id = conn.execute("INSERT INTO mau_hang (loai_hang_id, ten, thuoc_tinh, mo_ta) VALUES (%s, %s, %s, %s) "
                              "RETURNING id", (loai[ma_loai], ten_mau, Jsonb(thuoc_tinh), ten_mau)).fetchone()["id"]
        for ma, ten, go, dai, rong, cao, mau_sac, dat_rieng, toi_thieu, gia in ds:
            bt_id = conn.execute(
                """INSERT INTO bien_the (mau_hang_id, ma_noi_bo, ten_hien_thi, loai_go, dai_mm, rong_mm, cao_mm,
                                         mau_sac, dat_theo_kich_thuoc, ton_toi_thieu, thuoc_tinh)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (mau_id, ma, ten, go, dai, rong, cao, mau_sac, dat_rieng, toi_thieu, Jsonb(thuoc_tinh))).fetchone()["id"]
            bien_the[ma] = bt_id
            if gia:
                catalog.dat_gia(conn, co_van, bt_id, "GIA_SAN", gia[0])
                catalog.dat_gia(conn, co_van, bt_id, "GIA_NIEM_YET", gia[1])

    bo_sung_chi_tiet(conn)

    for ma, ct in CONG_THUC.items():
        conn.execute(
            """INSERT INTO cong_thuc_gia (bien_the_id, kieu, don_gia, phu_phi, bac_gia, kich_thuoc_min_mm,
                                          kich_thuoc_max_mm, ty_le_gia_von_phan_nghin, ty_le_gia_san_phan_nghin)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (bien_the[ma], ct["kieu"], ct["don_gia"], ct["phu_phi"], Jsonb(ct["bac_gia"]), ct["kich_thuoc_min_mm"],
             ct["kich_thuoc_max_mm"], ct["von"], ct["san"]))

    for ma_x, ma_bt, ma_hang, gia_nhap, ngay in MA_XUONG:
        conn.execute("INSERT INTO ma_xuong (bien_the_id, nha_cung_cap_id, ma_hang_xuong, gia_nhap, so_ngay_giao) "
                     "VALUES (%s, %s, %s, %s, %s)", (bien_the[ma_bt], xuong[ma_x], ma_hang, gia_nhap, ngay))

    bo_id = conn.execute(
        """INSERT INTO bo_san_pham (ma, ten, mo_ta, gia_niem_yet, gia_san)
           VALUES ('BO-BANAN-SOI-1600', 'Bộ bàn ghế ăn 6 ghế Gỗ Sồi (1600×800mm)',
                   'Bộ 7 món: 1 bàn + 6 ghế — tự trừ tồn từng món khi bán', 17200000, 16500000) RETURNING id"""
    ).fetchone()["id"]
    conn.cursor().executemany("INSERT INTO thanh_phan_bo (bo_san_pham_id, bien_the_id, so_luong) VALUES (%s, %s, %s)",
                     [(bo_id, bien_the["BAN-AN-SOI-1600x800"], 1), (bo_id, bien_the["GHE-AN-SOI"], 6)])

    for tu_khoa, tu_chuan in DONG_NGHIA:
        if tu_khoa != tu_chuan:
            catalog.them_dong_nghia(conn, co_van, tu_khoa, tu_chuan)

    for i, (ma_x, dong) in enumerate(PHIEU_NHAP, 1):
        inventory.tao_phieu_nhap(conn, anh_nam, xuong[ma_x],
                                 [{"bien_the_id": bien_the[m], "so_luong": sl, "gia_von_don_vi": g} for m, sl, g in dong],
                                 ghi_chu="Nhập hàng đầu kỳ", ma=f"PN261020{i:02d}")
    codes.dat_bo_dem(conn, "PN", date(2026, 10, 20), 3)

    kh = []
    for ten, sdt, mst, email, dia_chi in KHACH_HANG:
        kh.append(conn.execute("INSERT INTO khach_hang (ten, so_dien_thoai, ma_so_thue, email, dia_chi) "
                               "VALUES (%s, %s, %s, %s, %s) RETURNING id", (ten, sdt, mst, email, dia_chi)).fetchone()["id"])

    # #KV261026001 — Bộ bàn ăn, chủ xác nhận tay (4 số cuối 4817), cần xuất HĐĐT cho công ty
    d1 = orders.tao_don(conn, co_van, {"dong": [{"ma": "BO-BANAN-SOI-1600"}], "khach_hang_id": kh[0],
                                       "can_hoa_don": True}, ma="KV261026001")
    payments.xac_nhan_tay(conn, co_van, d1["id"], bon_so_cuoi="4817")

    # #KV261026002 — Tủ thờ Gỗ Mít đặt riêng 2m4 = 5.328.000 đ, khách cọc 2 triệu tiền mặt
    d2 = orders.tao_don(conn, co_van, {"dong": [{"ma": "TUTHO-MIT-1270", "kich_thuoc": "2m4"}],
                                       "khach_hang_id": kh[1]}, ma="KV261026002")
    payments.ghi_nhan_thanh_toan(conn, co_van, d2["id"], 2_000_000, "TIEN_MAT", la_coc=True)

    # #KV261027005 — Bộ bàn ăn 17,2 tr nhưng Máy nhận tiền báo về 17,0 tr (lệch -200k)
    orders.tao_don(conn, anh_nam, {"dong": [{"ma": "BO-BANAN-SOI-1600"}], "khach_hang_id": kh[2]}, ma="KV261027005")
    payments.nhan_giao_dich(conn, GiaoDichVao(
        nguon="MAY_NHAN_TIEN", ma_giao_dich="FT26300112345", so_tien=17_000_000,
        noi_dung="KV261027005 chuyen tien mua ban an", ngan_hang="Vietcombank", thoi_diem=datetime.now(),
        du_lieu_goc={"seed": True}))

    # #KV261027006 — Anh Nam xin bán Giường hộp 1m8 giá 7,8 tr (dưới giá sàn 8,1 tr) -> chờ Chủ duyệt
    orders.tao_don(conn, anh_nam, {"dong": [{"ma": "GUONG-HOP-SOI-1800", "don_gia_ban": 7_800_000}],
                                   "khach_hang": {"ten": "Anh Dũng (Sông Công)", "so_dien_thoai": "0977333444"}},
                   ma="KV261027006")

    for ma, ngay in (("KV261026001", "2026-10-26 10:42"), ("KV261026002", "2026-10-26 15:10"),
                     ("KV261027005", "2026-10-27 09:05"), ("KV261027006", "2026-10-27 10:20")):
        conn.execute("UPDATE don_hang SET tao_luc = %s WHERE ma = %s", (ngay, ma))
    codes.dat_bo_dem(conn, "KV", date(2026, 10, 26), 2)
    codes.dat_bo_dem(conn, "KV", date(2026, 10, 27), 6)

    conn.execute(
        """INSERT INTO thiet_bi (ten, loai, trang_thai, khoa_ky, lan_bao_song, chu_so_huu_id) VALUES
           ('Redmi Note 12T Pro (Máy nhận tiền)', 'MAY_NHAN_TIEN', 'HOAT_DONG', %s, now(), %s),
           ('Máy tính quầy', 'MAY_QUAY', 'HOAT_DONG', %s, now(), %s)""",
        (tao_khoa_ky(), co_van.id, tao_khoa_ky(), co_van.id))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    nap()
