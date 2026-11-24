"""Bổ sung 30 mặt hàng nội thất gỗ phổ biến vào danh mục, giá bán tham khảo mặt bằng bán lẻ
(Shopee, Chợ Tốt, trang nội thất) tháng 11/2026. Mọi thứ đi qua chính các service nghiệp vụ như hàng thật:

- mặt hàng: catalog.tao_bien_the (giá niêm yết / giá sàn vào lịch sử giá, nhật ký có chuỗi băm);
- tồn đầu: mỗi xưởng một phiếu nhập (sổ cái NHAP, giá vốn bình quân, công nợ xưởng tăng);
- hàng đặt theo kích thước: catalog.luu_cong_thuc; thêm 2 bộ sản phẩm, mã hàng của xưởng, từ đồng nghĩa.

Chạy lại không tạo trùng và không ghi đè: mặt hàng / bộ / xưởng / loại gỗ / từ đồng nghĩa đã có (kể cả hàng
Chủ đã xóa khỏi danh mục) thì bỏ qua.

    python -m app.hang_mau_bo_sung --xem-truoc   # chạy thử rồi hoàn tác, chỉ in kết quả
    python -m app.hang_mau_bo_sung               # nạp vào CSDL đang cấu hình (DATABASE_URL)
"""
import argparse
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from . import db, seed
from .errors import LoiNghiepVu
from .security import NguoiDung
from .services import audit, catalog, inventory

log = logging.getLogger("khanhvan.hang_mau_bo_sung")

# Gỗ mới cho hàng bổ sung (hệ số dùng khi tính giá hàng đặt riêng; Sồi = 1000)
LOAI_GO_MOI = [("Cao su", 850), ("Thông", 750), ("Gụ", 1700)]

# khóa -> (tên, liên hệ, SĐT, địa chỉ, loại hàng). Ba xưởng đầu có sẵn từ dữ liệu mẫu (tìm theo mã),
# hai xưởng sau là nguồn hàng mới (tìm theo tên).
XUONG = {
    "CAT_DANG": ("Xưởng Đồ Thờ Cát Đẳng", "Ông Hùng — Ý Yên, Nam Định", "0912000111", None, "Đồ thờ, án gian"),
    "HAI_HAU": ("Xưởng Giường & Bàn Ghế Hải Hậu", "Anh Quân — Hải Hậu, Nam Định", "0913000222", None,
                "Giường, bàn ghế"),
    "MDF": ("Kho Gỗ Công Nghiệp MDF", "Chị Lan — Thái Nguyên", "0914000333", None, "Tủ, kệ gỗ công nghiệp"),
    "DONG_KY": ("Xưởng Mộc Đồng Kỵ", "Anh Thành", "0915000444", "Đồng Kỵ, Từ Sơn, Bắc Ninh",
                "Tủ áo, tủ rượu, sofa, bàn ghế phòng khách, giường gỗ quý"),
    "THUAN_AN": ("Xưởng Gỗ Cao Su & Thông Thuận An", "Chị Mai", "0916000555", "Thuận An, Bình Dương",
                 "Bàn ăn, giường, kệ gỗ cao su và gỗ thông"),
}
XUAT_XU = {"CAT_DANG": "Ý Yên, Nam Định", "HAI_HAU": "Hải Hậu, Nam Định", "MDF": "Thái Nguyên",
           "DONG_KY": "Đồng Kỵ, Bắc Ninh", "THUAN_AN": "Thuận An, Bình Dương"}


@dataclass(frozen=True)
class HangMau:
    loai: str                  # mã nhóm hàng (loai_hang.ma)
    mau: str                   # tên mẫu hàng (tạo mới nếu nhóm chưa có)
    ma: str
    ten: str
    go: str
    kt: tuple                  # (dài, rộng, cao) mm; None = không cố định (hàng đặt riêng)
    mau_sac: str
    xuong: str                 # khóa trong XUONG
    ma_xuong: str              # mã hàng bên xưởng
    chi_tiet: tuple            # (hoàn thiện, kiểu dáng, vật liệu / phụ kiện, khối lượng kg, bảo hành tháng)
    thuoc_tinh: dict
    mo_ta: str
    gia: tuple | None = None   # (giá sàn, giá niêm yết)
    nhap: tuple | None = None  # (số lượng nhập đầu, giá nhập / cái)
    toi_thieu: int = 0
    ngay_giao: int = 7
    cong_thuc: dict | None = None
    dvt: str | None = None
    them: dict = field(default_factory=dict)


def _ct(kieu, *, don_gia=None, phu_phi=0, bac=(), tu, den, von, san) -> dict:
    return {"kieu": kieu, "don_gia": don_gia, "phu_phi": phu_phi,
            "bac_gia": [{"toi_da_mm": t, "gia": g} for t, g in bac],
            "kich_thuoc_min_mm": tu, "kich_thuoc_max_mm": den,
            "ty_le_gia_von_phan_nghin": von, "ty_le_gia_san_phan_nghin": san}


HANG_MAU = [
    # ---------------- Đồ thờ (Ý Yên) ----------------
    HangMau("DO_THO", "Bàn thờ treo tường gỗ Sồi", "BANTHO-TREO-SOI-810", "Bàn thờ treo tường Gỗ Sồi 81cm",
            "Sồi", (810, 480, 350), "Cánh gián", "CAT_DANG", "CD-BTT-81",
            ("Sơn PU bóng mờ", "Hiện đại", "Ke treo thép sơn tĩnh điện", 12, 12),
            {"Hoa văn": "Hoa sen", "Số tầng": 1, "Kiểu chân": "Treo tường", "Có ngăn kéo": False},
            "Gỗ Sồi Nga sấy, mặt dày 25mm, ke treo chịu lực 80 kg. Kích thước 81 × 48 cm hợp thước Lỗ Ban.",
            gia=(1_450_000, 1_650_000), nhap=(2, 1_150_000), toi_thieu=3, ngay_giao=5),
    HangMau("DO_THO", "Bàn thờ treo tường gỗ Sồi", "BANTHO-TREO-SOI-1070",
            "Bàn thờ treo tường Gỗ Sồi 1m07 có đèn hắt", "Sồi", (1070, 610, 450), "Cánh gián", "CAT_DANG",
            "CD-BTT-107", ("Sơn PU bóng mờ", "Hiện đại", "Ke treo thép, đèn LED hắt sáng", 19, 12),
            {"Hoa văn": "Hoa sen", "Số tầng": 1, "Kiểu chân": "Treo tường", "Có ngăn kéo": True},
            "Ngăn kéo đựng hương, đèn LED hắt sáng bát hương. Kích thước 107 × 61 cm hợp thước Lỗ Ban.",
            gia=(2_300_000, 2_600_000), nhap=(3, 1_850_000), toi_thieu=1, ngay_giao=5),
    HangMau("DO_THO", "Bàn thờ đứng gỗ Sồi", "BANTHO-DUNG-SOI-1270", "Bàn thờ đứng Gỗ Sồi 1m27 hai tầng",
            "Sồi", (1270, 610, 1270), "Cánh gián", "CAT_DANG", "CD-BTD-127",
            ("Sơn PU bóng mờ", "Hiện đại", "Ray ngăn kéo giảm chấn", 55, 24),
            {"Hoa văn": "Đục hoa sen", "Số tầng": 2, "Kiểu chân": "Chân quỳ", "Có ngăn kéo": True},
            "Hai tầng, tầng dưới 2 ngăn kéo và hộc để đồ lễ. Hợp phòng thờ chung cư.",
            gia=(3_600_000, 4_100_000), nhap=(3, 2_950_000), toi_thieu=1),
    HangMau("DO_THO", "Tủ thờ chạm sen", "TUTHO-XOAN-1530", "Tủ thờ Gỗ Xoan đào 1m53 chạm sen", "Xoan đào",
            (1530, 610, 1270), "Cánh gián", "CAT_DANG", "CD-TT-153",
            ("Sơn PU màu cánh gián", "Cổ điển", "Bản lề đồng", 85, 24),
            {"Hoa văn": "Chạm sen", "Số tầng": 2, "Kiểu chân": "Chân quỳ", "Có ngăn kéo": True},
            "Gỗ Xoan đào, cánh chạm sen nổi; 3 ngăn kéo trên, 2 cánh dưới.",
            gia=(5_300_000, 5_900_000), nhap=(2, 4_500_000), toi_thieu=1),
    HangMau("DO_THO", "Sập thờ gỗ Gụ", "SAPTHO-GU-1750", "Sập thờ Gỗ Gụ 1m75 chân quỳ dạ cá", "Gụ",
            (1750, 1070, 810), "Nâu cánh gián", "CAT_DANG", "CD-ST-175",
            ("Lau dầu (vecni)", "Cổ điển", "Diềm đục tứ linh thủ công", 190, 60),
            {"Hoa văn": "Tứ linh", "Số tầng": 1, "Kiểu chân": "Chân quỳ dạ cá", "Có ngăn kéo": False},
            "Gỗ Gụ, mặt liền khối dày 5cm, chân quỳ dạ cá, diềm đục tứ linh thủ công.",
            gia=(21_000_000, 23_500_000), nhap=(1, 18_000_000), ngay_giao=15),

    # ---------------- Giường ----------------
    HangMau("GIUONG", "Giường gỗ Xoan đào đầu cong", "GIUONG-XOAN-1600", "Giường ngủ Gỗ Xoan đào 1m6 × 2m đầu cong",
            "Xoan đào", (2000, 1600, 1000), "Cánh gián", "HAI_HAU", "HH-GX16",
            ("Sơn PU màu cánh gián", "Cổ điển", "Giát giường gỗ thông", 95, 24),
            {"Kiểu dáng": "Đầu cong", "Có ngăn kéo": False, "Kích thước nệm": "1m6 × 2m",
             "Đầu giường": "Gỗ nguyên tấm", "Chiều cao gầm (mm)": 300},
            "Gỗ Xoan đào sấy, thành giường dày 2,5cm, gầm cao 30cm dễ vệ sinh.",
            gia=(6_900_000, 7_500_000), nhap=(3, 5_800_000), toi_thieu=1, ngay_giao=5),
    HangMau("GIUONG", "Giường gỗ Xoan đào đầu cong", "GIUONG-XOAN-1800", "Giường ngủ Gỗ Xoan đào 1m8 × 2m đầu cong",
            "Xoan đào", (2000, 1800, 1000), "Cánh gián", "HAI_HAU", "HH-GX18",
            ("Sơn PU màu cánh gián", "Cổ điển", "Giát giường gỗ thông", 105, 24),
            {"Kiểu dáng": "Đầu cong", "Có ngăn kéo": False, "Kích thước nệm": "1m8 × 2m",
             "Đầu giường": "Gỗ nguyên tấm", "Chiều cao gầm (mm)": 300},
            "Gỗ Xoan đào sấy, thành giường dày 2,5cm, gầm cao 30cm dễ vệ sinh.",
            gia=(7_500_000, 8_200_000), nhap=(2, 6_300_000), toi_thieu=1, ngay_giao=5),
    HangMau("GIUONG", "Giường kiểu Nhật gỗ Sồi", "GIUONG-NHAT-SOI-1600",
            "Giường kiểu Nhật Gỗ Sồi 1m6 × 2m (giường bệt)", "Sồi", (2000, 1600, 800), "Tự nhiên", "HAI_HAU",
            "HH-GN16", ("Sơn PU tự nhiên", "Tối giản", "Lắp ghép bằng bulông", 48, 12),
            {"Kiểu dáng": "Kiểu Nhật (bệt)", "Có ngăn kéo": False, "Kích thước nệm": "1m6 × 2m",
             "Đầu giường": "Nan gỗ", "Chiều cao gầm (mm)": 0},
            "Giường thấp kiểu Nhật, khung Gỗ Sồi Nga, tháo lắp nhanh, tiện chuyển nhà.",
            gia=(3_900_000, 4_400_000), nhap=(4, 3_200_000), toi_thieu=2, ngay_giao=5),
    HangMau("GIUONG", "Giường đơn gỗ Cao su", "GIUONG-DON-CAOSU-1200", "Giường đơn Gỗ Cao su 1m2 × 2m", "Cao su",
            (2000, 1200, 900), "Óc chó", "THUAN_AN", "TA-GD12",
            ("Sơn PU màu óc chó", "Hiện đại", "Giát giường gỗ thông", 42, 12),
            {"Kiểu dáng": "Đầu vuông", "Có ngăn kéo": False, "Kích thước nệm": "1m2 × 2m",
             "Đầu giường": "Ốp nan gỗ", "Chiều cao gầm (mm)": 250},
            "Gỗ Cao su ghép thanh đã xử lý chống mối mọt. Hợp phòng trẻ em, phòng cho thuê.",
            gia=(2_900_000, 3_300_000), nhap=(4, 2_350_000), toi_thieu=2, ngay_giao=10),
    HangMau("GIUONG", "Giường tầng gỗ Thông", "GIUONG-TANG-THONG-DATRIENG",
            "Giường tầng Gỗ Thông cầu thang hộc kéo — đặt theo bậc chiều rộng", "Thông", (2000, None, 1650),
            "Trắng phối vân gỗ", "THUAN_AN", "TA-GT-DR",
            ("Sơn PU hai màu", "Trẻ em", "Cầu thang hộp 4 hộc kéo, lan can an toàn", None, 30),
            {"Kiểu dáng": "Giường tầng", "Có ngăn kéo": True, "Đầu giường": "Lan can gỗ"},
            "Đóng theo chiều rộng nệm từ 0,9m đến 1,4m. Cầu thang kiêm 4 hộc kéo đựng đồ.",
            ngay_giao=14, cong_thuc=_ct("THEO_BAC", bac=[(1000, 6_900_000), (1200, 7_600_000), (1400, 8_300_000)],
                                        tu=900, den=1400, von=780, san=920)),
    HangMau("GIUONG", "Giường gỗ Gõ đỏ chạm hoa", "GIUONG-GODO-1800", "Giường ngủ Gỗ Gõ đỏ 1m8 × 2m chạm hoa hồng",
            "Gõ đỏ", (2000, 1800, 1250), "Nâu đỏ", "DONG_KY", "DK-GG18",
            ("Lau dầu (vecni)", "Tân cổ điển", "Đầu giường đục hoa hồng thủ công", 165, 60),
            {"Kiểu dáng": "Tân cổ điển", "Có ngăn kéo": False, "Kích thước nệm": "1m8 × 2m",
             "Đầu giường": "Chạm hoa hồng", "Chiều cao gầm (mm)": 320},
            "Gỗ Gõ đỏ, đầu giường đục hoa hồng, chân tiện. Hàng cao cấp, kê vừa nệm 1m8.",
            gia=(19_500_000, 21_500_000), nhap=(1, 16_500_000), ngay_giao=12),

    # ---------------- Tủ / Kệ ----------------
    HangMau("TU_KE", "Tủ quần áo gỗ Xoan đào", "TU-AO-XOAN-3C", "Tủ quần áo Gỗ Xoan đào 3 cánh 1m6", "Xoan đào",
            (1600, 600, 2100), "Cánh gián", "DONG_KY", "DK-TA3C",
            ("Sơn PU màu cánh gián", "Cổ điển", "Bản lề giảm chấn, khóa tủ", 150, 36),
            {"Số cánh": 3, "Số ngăn kéo": 2, "Có gương": True},
            "Khoang treo áo dài và áo ngắn, 2 ngăn kéo dưới, gương soi ở cánh giữa.",
            gia=(6_100_000, 6_800_000), nhap=(3, 5_200_000), toi_thieu=1),
    HangMau("TU_KE", "Tủ quần áo gỗ Sồi", "TU-AO-SOI-2C", "Tủ quần áo Gỗ Sồi 2 cánh 1m2", "Sồi",
            (1200, 580, 2000), "Tự nhiên", "DONG_KY", "DK-TA2C",
            ("Sơn PU tự nhiên", "Hiện đại", "Bản lề giảm chấn", 105, 24),
            {"Số cánh": 2, "Số ngăn kéo": 1, "Có gương": False},
            "Gỗ Sồi Nga, 1 khoang treo và 4 đợt để đồ gấp, 1 ngăn kéo dưới.",
            gia=(5_000_000, 5_600_000), nhap=(3, 4_250_000), toi_thieu=1),
    HangMau("TU_KE", "Tủ đầu giường gỗ Sồi", "TU-DAU-GIUONG-SOI", "Tủ đầu giường Gỗ Sồi 2 ngăn kéo", "Sồi",
            (450, 400, 500), "Óc chó", "HAI_HAU", "HH-TDG",
            ("Sơn PU màu óc chó", "Hiện đại", "Ray bi giảm chấn", 14, 12),
            {"Số cánh": 0, "Số ngăn kéo": 2, "Có gương": False},
            "Đi cùng giường hộp Gỗ Sồi màu óc chó. Tay nắm âm, ray bi giảm chấn.",
            gia=(1_150_000, 1_350_000), nhap=(3, 900_000), toi_thieu=4, ngay_giao=5),
    HangMau("TU_KE", "Tủ giày gỗ Sồi", "TU-GIAY-SOI-1000", "Tủ giày Gỗ Sồi 1m cánh lật 3 tầng", "Sồi",
            (1000, 350, 1100), "Tự nhiên", "DONG_KY", "DK-TG10",
            ("Sơn PU tự nhiên", "Hiện đại", "Bản lề cánh lật", 38, 12),
            {"Số cánh": 3, "Số ngăn kéo": 0, "Có gương": False},
            "3 cánh lật chứa 18–24 đôi giày, mặt tủ để chìa khóa và đồ trang trí.",
            gia=(2_600_000, 2_950_000), nhap=(3, 2_150_000), toi_thieu=1),
    HangMau("TU_KE", "Kệ sách gỗ Thông", "KE-SACH-THONG-5T", "Kệ sách Gỗ Thông 5 tầng 80cm", "Thông",
            (800, 300, 1800), "Gỗ thông tự nhiên", "THUAN_AN", "TA-KS5T",
            ("Lau dầu chống ẩm", "Tối giản", "Ke bắt tường chống đổ", 22, 12),
            {"Số cánh": 0, "Số ngăn kéo": 0, "Có gương": False},
            "Gỗ Thông nhập khẩu, tháo lắp dễ. Mỗi tầng chịu 25 kg, có ke bắt tường chống đổ.",
            gia=(950_000, 1_150_000), nhap=(6, 720_000), toi_thieu=3, ngay_giao=10),
    HangMau("TU_KE", "Tủ rượu gỗ Gõ đỏ", "TU-RUOU-GODO-1600", "Tủ rượu Gỗ Gõ đỏ 1m6 cánh kính", "Gõ đỏ",
            (1600, 450, 2000), "Nâu đỏ", "DONG_KY", "DK-TR16",
            ("Lau dầu (vecni)", "Tân cổ điển", "Kính cường lực 5mm, đèn LED", 140, 60),
            {"Số cánh": 4, "Số ngăn kéo": 2, "Có gương": True},
            "2 cánh kính trên, 2 cánh gỗ dưới, đèn LED trong khoang trưng bày.",
            gia=(17_500_000, 19_500_000), nhap=(1, 15_000_000), ngay_giao=12),
    HangMau("TU_KE", "Kệ tivi gỗ Sồi", "KE-TIVI-SOI-1600", "Kệ tivi Gỗ Sồi 1m6 chân cao", "Sồi",
            (1600, 400, 550), "Tự nhiên", "HAI_HAU", "HH-KTV16",
            ("Sơn PU tự nhiên", "Bắc Âu", "Ray bi giảm chấn", 36, 12),
            {"Số cánh": 2, "Số ngăn kéo": 2, "Có gương": False},
            "Chân cao 15cm dễ lau gầm. 2 ngăn kéo và 2 hộc mở để đầu thu, loa.",
            gia=(3_500_000, 3_950_000), nhap=(3, 2_900_000), toi_thieu=1, ngay_giao=5),
    HangMau("TU_KE", "Tủ bếp gỗ Xoan đào", "TU-BEP-XOAN-DATRIENG", "Tủ bếp dưới Gỗ Xoan đào — đặt theo mét dài",
            "Xoan đào", (None, 600, 810), "Cánh gián", "DONG_KY", "DK-TB-DR",
            ("Sơn PU 2K", "Hiện đại", "Bản lề giảm chấn; chưa gồm mặt đá và thiết bị", None, 36),
            {"Số cánh": 0, "Số ngăn kéo": 0, "Có gương": False},
            "Thùng và cánh Gỗ Xoan đào. Giá theo mét dài tủ dưới, chưa gồm mặt đá, chậu rửa, bếp. Đo tận nhà.",
            ngay_giao=20, cong_thuc=_ct("THEO_CHIEU_DAI", don_gia=5_500_000, tu=1000, den=6000, von=650, san=800)),

    # ---------------- Bàn ghế ----------------
    HangMau("BAN_GHE", "Bộ bàn ăn gỗ Cao su", "BAN-AN-CAOSU-1200", "Bàn ăn Gỗ Cao su 1200×750mm", "Cao su",
            (1200, 750, 750), "Óc chó", "THUAN_AN", "TA-BA12",
            ("Sơn PU màu óc chó", "Hiện đại", None, 28, 12),
            {"Số chỗ ngồi": 4, "Kiểu mặt bàn": "Chữ nhật", "Có đệm": False},
            "Mặt Gỗ Cao su ghép dày 25mm, chân tháo lắp. Đủ 4 người ngồi.",
            gia=(2_100_000, 2_450_000), nhap=(4, 1_700_000), toi_thieu=2, ngay_giao=10),
    HangMau("BAN_GHE", "Bộ bàn ăn gỗ Cao su", "GHE-AN-CAOSU", "Ghế ăn Gỗ Cao su lưng nan", "Cao su",
            (430, 460, 880), "Óc chó", "THUAN_AN", "TA-GA",
            ("Sơn PU màu óc chó", "Hiện đại", "Nút cao su chống trầy sàn", 5, 12),
            {"Số chỗ ngồi": 1, "Có đệm": False},
            "Lưng nan cong ôm lưng, chân có nút cao su chống trầy sàn.",
            gia=(420_000, 520_000), nhap=(16, 330_000), toi_thieu=8, ngay_giao=10),
    HangMau("BAN_GHE", "Bàn trà gỗ Sồi", "BAN-TRA-SOI-1100", "Bàn trà Gỗ Sồi 1m1 có hộc kéo", "Sồi",
            (1100, 600, 450), "Óc chó", "HAI_HAU", "HH-BT11",
            ("Sơn PU màu óc chó", "Hiện đại", None, 24, 12),
            {"Số chỗ ngồi": 0, "Kiểu mặt bàn": "Chữ nhật, mặt gỗ", "Có đệm": False},
            "Bàn uống nước phòng khách: 2 hộc kéo hai đầu, tầng dưới để ấm chén, báo.",
            gia=(1_900_000, 2_200_000), nhap=(4, 1_550_000), toi_thieu=2, ngay_giao=5),
    HangMau("BAN_GHE", "Sofa gỗ Sồi", "SOFA-SOI-VANG-3C", "Sofa văng Gỗ Sồi 3 chỗ đệm nỉ", "Sồi",
            (1900, 780, 850), "Tự nhiên, nỉ xám", "DONG_KY", "DK-SF3C",
            ("Sơn PU tự nhiên", "Bắc Âu", "Đệm mút D40 bọc nỉ, vỏ tháo giặt được", 45, 24),
            {"Số chỗ ngồi": 3, "Có đệm": True},
            "Khung Gỗ Sồi Nga, đệm mút D40 ít xẹp lún, vỏ nỉ có khóa kéo để tháo giặt.",
            gia=(6_900_000, 7_800_000), nhap=(2, 5_800_000), toi_thieu=1),
    HangMau("BAN_GHE", "Bộ bàn ghế phòng khách Âu Á", "SALON-AUA-XOAN-6M",
            "Bộ bàn ghế phòng khách Âu Á Gỗ Xoan đào 6 món", "Xoan đào", (1950, 600, 1000), "Cánh gián", "DONG_KY",
            "DK-AA6M", ("Sơn PU màu cánh gián", "Cổ điển", "Đệm ngồi bọc gấm", 210, 36),
            {"Số chỗ ngồi": 6, "Kiểu mặt bàn": "Mặt gỗ, chân quỳ", "Có đệm": True},
            "6 món: ghế dài, 2 ghế đơn, 2 đôn, bàn trà. Tay ghế đục hoa lá, kèm đệm ngồi bọc gấm.",
            gia=(21_000_000, 23_500_000), nhap=(2, 18_000_000), toi_thieu=1, ngay_giao=15, dvt="bộ"),
    HangMau("BAN_GHE", "Bàn làm việc gỗ Sồi", "BAN-LAM-VIEC-SOI-1200", "Bàn làm việc Gỗ Sồi 1m2 có hộc kéo", "Sồi",
            (1200, 600, 750), "Tự nhiên", "HAI_HAU", "HH-BLV12",
            ("Sơn PU tự nhiên", "Hiện đại", "Ray bi giảm chấn, lỗ đi dây điện", 32, 12),
            {"Số chỗ ngồi": 1, "Kiểu mặt bàn": "Chữ nhật", "Có đệm": False},
            "Mặt Gỗ Sồi dày 25mm, 2 ngăn kéo và hộc tủ có khóa. Hợp làm việc tại nhà, bàn học.",
            gia=(2_700_000, 3_100_000), nhap=(3, 2_250_000), toi_thieu=1, ngay_giao=5),
    HangMau("BAN_GHE", "Bàn trang điểm gỗ Sồi", "BAN-TRANG-DIEM-SOI", "Bàn trang điểm Gỗ Sồi có gương kèm đôn",
            "Sồi", (900, 450, 1450), "Trắng phối vân sồi", "HAI_HAU", "HH-BTD",
            ("Sơn PU trắng phối vân gỗ", "Hiện đại", "Gương soi 50×70cm, đôn bọc nỉ", 30, 12),
            {"Số chỗ ngồi": 1, "Kiểu mặt bàn": "Có gương", "Có đệm": True},
            "Gương soi 50×70cm, 4 ngăn kéo nhỏ đựng mỹ phẩm, kèm 1 đôn ngồi bọc nỉ.",
            gia=(2_800_000, 3_200_000), nhap=(2, 2_300_000), toi_thieu=1, ngay_giao=5),
    HangMau("BAN_GHE", "Đôn gỗ Sồi", "DON-SOI-TRON-350", "Đôn gỗ Sồi tròn mặt 35cm", "Sồi",
            (350, 350, 450), "Tự nhiên", "HAI_HAU", "HH-DON35",
            ("Sơn PU tự nhiên", "Tối giản", None, 4, 6),
            {"Số chỗ ngồi": 1, "Có đệm": False},
            "Đôn đa năng: ghế phụ phòng khách, đôn ngồi bàn trang điểm, kệ để chậu cây.",
            gia=(280_000, 350_000), nhap=(10, 210_000), toi_thieu=4, ngay_giao=5),

    # ---------------- Gỗ công nghiệp ----------------
    HangMau("GO_CN", "Tủ quần áo MDF 3 cánh", "TU-AO-MDF-3C", "Tủ quần áo MDF 3 cánh 1m2 chống ẩm", "MDF",
            (1200, 550, 2000), "Trắng vân gỗ", "MDF", "MDF-TA3C",
            ("Melamine chống ẩm", "Hiện đại", "Bản lề giảm chấn, gương cánh giữa", 85, 12),
            {"Bề mặt": "Melamine chống ẩm", "Số cánh": 3, "Số ngăn kéo": 2, "Có gương": True, "Chống ẩm": True},
            "MDF lõi xanh chống ẩm phủ Melamine, 2 ngăn kéo dưới, cánh giữa có gương.",
            gia=(3_200_000, 3_650_000), nhap=(4, 2_650_000), toi_thieu=2, ngay_giao=3),
    HangMau("GO_CN", "Tủ giày MDF", "TU-GIAY-MDF-800", "Tủ giày MDF 80cm 2 cánh", "MDF",
            (800, 330, 1000), "Trắng", "MDF", "MDF-TG80",
            ("Melamine", "Tối giản", "Tay nắm nhôm", 26, 12),
            {"Bề mặt": "Melamine", "Số cánh": 2, "Số ngăn kéo": 0, "Chống ẩm": False},
            "4 tầng để 12–15 đôi giày, đợt chỉnh được độ cao cho giày cao cổ.",
            gia=(1_050_000, 1_250_000), nhap=(5, 820_000), toi_thieu=3, ngay_giao=3),
    HangMau("GO_CN", "Tủ quần áo âm tường MDF", "TU-AM-TUONG-MDF-DATRIENG",
            "Tủ quần áo âm tường MDF lõi xanh — đặt theo m² mặt đứng", "MDF", (None, 600, None),
            "Theo bảng màu Melamine", "MDF", "MDF-TAT-DR",
            ("Melamine chống ẩm", "Hiện đại", "Bản lề giảm chấn, thanh treo nhôm", None, 24),
            {"Bề mặt": "Melamine chống ẩm", "Chống ẩm": True},
            "Đóng kịch trần theo kích thước phòng. Giá theo m² mặt đứng (dài × cao), cộng 500.000 đ công lắp đặt.",
            ngay_giao=12, cong_thuc=_ct("THEO_DIEN_TICH", don_gia=4_800_000, phu_phi=500_000, tu=400, den=3000,
                                        von=620, san=780)),
]

# (mã bộ, tên, mô tả, giá niêm yết, giá sàn, [(mã biến thể, số lượng)])
BO_MOI = [
    ("BO-BANAN-CAOSU-1200", "Bộ bàn ăn 4 ghế Gỗ Cao su (1200×750mm)",
     "Bộ 5 món: 1 bàn + 4 ghế — tự trừ tồn từng món khi bán", 4_350_000, 3_950_000,
     [("BAN-AN-CAOSU-1200", 1), ("GHE-AN-CAOSU", 4)]),
    ("BO-SOFA-SOI-BANTRA", "Bộ sofa văng Gỗ Sồi kèm bàn trà",
     "Sofa văng 3 chỗ + bàn trà 1m1 — tự trừ tồn từng món khi bán", 9_600_000, 8_900_000,
     [("SOFA-SOI-VANG-3C", 1), ("BAN-TRA-SOI-1100", 1)]),
]

# Cách gọi thường của khách -> từ có trong tên hàng
DONG_NGHIA_MOI = [("bàn uống nước", "bàn trà"), ("tab đầu giường", "tủ đầu giường"),
                  ("táp đầu giường", "tủ đầu giường"), ("bàn phấn", "bàn trang điểm"),
                  ("giường 2 tầng", "giường tầng"), ("kệ giày", "tủ giày")]


def nguoi_chu(conn, ten_dang_nhap: str | None = None) -> NguoiDung:
    if ten_dang_nhap:
        r = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE ten_dang_nhap = %s",
                         (ten_dang_nhap,)).fetchone()
    else:
        r = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE vai_tro = 'CHU' AND kich_hoat "
                         "ORDER BY id LIMIT 1").fetchone()
    if not r or r["vai_tro"] != "CHU":
        raise LoiNghiepVu("CAN_TAI_KHOAN_CHU", "Cần một tài khoản Chủ cửa hàng để ghi nhận người nhập hàng")
    return NguoiDung(id=r["id"], vai_tro=r["vai_tro"], ho_ten=r["ho_ten"])


def _nhom_hang(conn) -> dict:
    """Nhóm hàng theo mã; CSDL dựng không kèm dữ liệu mẫu thì tạo nhóm còn thiếu theo seed.LOAI_HANG."""
    co = {r["ma"]: r for r in conn.execute("SELECT id, ma, thuoc_tinh_mau FROM loai_hang").fetchall()}
    for ma, ten, dvt, mau in seed.LOAI_HANG:
        if ma not in co:
            co[ma] = conn.execute("INSERT INTO loai_hang (ma, ten, don_vi_tinh, thuoc_tinh_mau) "
                                  "VALUES (%s, %s, %s, %s) RETURNING id, ma, thuoc_tinh_mau",
                                  (ma, ten, dvt, Jsonb(mau))).fetchone()
    return co


def _xuong(conn, chu: NguoiDung, kq: dict) -> dict:
    ids = {}
    for khoa, (ten, lien_he, sdt, dia_chi, loai_hang) in XUONG.items():
        r = conn.execute("SELECT id FROM nha_cung_cap WHERE ma = %s OR f_chuan_hoa(ten) = f_chuan_hoa(%s) "
                         "ORDER BY (ma = %s) DESC LIMIT 1", (khoa, ten, khoa)).fetchone()
        if not r:
            r = inventory.tao_xuong(conn, chu, {"ten": ten, "lien_he": lien_he, "so_dien_thoai": sdt,
                                                "dia_chi": dia_chi, "loai_hang": loai_hang})
            kq["xuong_moi"].append(ten)
        ids[khoa] = r["id"]
    return ids


def nap(conn, chu: NguoiDung | None = None) -> dict:
    """Nạp toàn bộ hàng bổ sung trong giao dịch của `conn` (không commit). Trả về báo cáo những gì đã tạo."""
    chu = chu or nguoi_chu(conn)
    kq = {"mat_hang": [], "bo_qua": [], "loai_go_moi": [], "xuong_moi": [], "phieu_nhap": [], "bo": [],
          "dong_nghia": []}

    for go, he_so in LOAI_GO_MOI:
        if not conn.execute("SELECT 1 FROM he_so_go WHERE loai_go = %s", (go,)).fetchone():
            catalog.dat_he_so_go(conn, chu, go, he_so)
            kq["loai_go_moi"].append(go)
    nhom = _nhom_hang(conn)
    xuong = _xuong(conn, chu, kq)

    moi: dict[str, int] = {}
    for h in HANG_MAU:
        if conn.execute("SELECT 1 FROM bien_the WHERE ma_noi_bo = %s", (h.ma,)).fetchone():
            kq["bo_qua"].append(h.ma)
            continue
        dai, rong, cao = h.kt
        hoan_thien, kieu_dang, vat_lieu, kg, bao_hanh = h.chi_tiet
        bt = catalog.tao_bien_the(conn, chu, {
            "loai_hang_id": nhom[h.loai]["id"], "ten_mau_moi": h.mau, "ma_noi_bo": h.ma, "ten_hien_thi": h.ten,
            "loai_go": h.go, "dai_mm": dai, "rong_mm": rong, "cao_mm": cao, "mau_sac": h.mau_sac,
            "hoan_thien": hoan_thien, "kieu_dang": kieu_dang, "vat_lieu_phu": vat_lieu,
            "xuat_xu": XUAT_XU[h.xuong], "khoi_luong_kg": kg, "bao_hanh_thang": bao_hanh, "don_vi_tinh": h.dvt,
            "mo_ta": h.mo_ta, "ton_toi_thieu": h.toi_thieu, "dat_theo_kich_thuoc": h.cong_thuc is not None,
            "thuoc_tinh": {**(nhom[h.loai]["thuoc_tinh_mau"] or {}), **h.thuoc_tinh},
            "gia_san": h.gia[0] if h.gia else None, "gia_niem_yet": h.gia[1] if h.gia else None})
        moi[h.ma] = bt["id"]
        if h.cong_thuc:
            catalog.luu_cong_thuc(conn, chu, bt["id"], h.cong_thuc)
        conn.execute("INSERT INTO ma_xuong (bien_the_id, nha_cung_cap_id, ma_hang_xuong, gia_nhap, so_ngay_giao) "
                     "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (bien_the_id, nha_cung_cap_id) DO NOTHING",
                     (bt["id"], xuong[h.xuong], h.ma_xuong, h.nhap[1] if h.nhap else 0, h.ngay_giao))
        kq["mat_hang"].append(h.ma)

    # Hàng về: mỗi xưởng một phiếu nhập cho các mặt hàng vừa thêm (hàng đặt riêng không nhập kho)
    theo_xuong = defaultdict(list)
    for h in HANG_MAU:
        if h.ma in moi and h.nhap:
            theo_xuong[h.xuong].append({"bien_the_id": moi[h.ma], "so_luong": h.nhap[0], "gia_von_don_vi": h.nhap[1]})
    for khoa, dong in theo_xuong.items():
        phieu = inventory.tao_phieu_nhap(conn, chu, xuong[khoa], dong, ghi_chu="Nhập hàng bổ sung danh mục")
        kq["phieu_nhap"].append((phieu["ma"], XUONG[khoa][0], phieu["tong_tien"]))

    for ma, ten, mo_ta, niem_yet, san, thanh_phan in BO_MOI:
        if conn.execute("SELECT 1 FROM bo_san_pham WHERE ma = %s", (ma,)).fetchone():
            continue
        ids = conn.execute("SELECT ma_noi_bo, id FROM bien_the WHERE ma_noi_bo = ANY(%s) AND dang_ban",
                           ([m for m, _ in thanh_phan],)).fetchall()
        ids = {r["ma_noi_bo"]: r["id"] for r in ids}
        if len(ids) < len(thanh_phan):
            continue  # Chủ đã ngừng bán một thành phần: không dựng bộ thiếu món
        bo_id = conn.execute("INSERT INTO bo_san_pham (ma, ten, mo_ta, gia_niem_yet, gia_san) "
                             "VALUES (%s, %s, %s, %s, %s) RETURNING id", (ma, ten, mo_ta, niem_yet, san)).fetchone()["id"]
        conn.cursor().executemany("INSERT INTO thanh_phan_bo (bo_san_pham_id, bien_the_id, so_luong) VALUES (%s, %s, %s)",
                                  [(bo_id, ids[m], sl) for m, sl in thanh_phan])
        audit.ghi(conn, chu, "TAO_BO_SAN_PHAM", "BO_SAN_PHAM", bo_id,
                  sau={"ma": ma, "ten": ten, "thanh_phan": dict(thanh_phan)})
        kq["bo"].append(ma)

    for tu_khoa, tu_chuan in DONG_NGHIA_MOI:
        if not conn.execute("SELECT 1 FROM tu_dong_nghia WHERE tu_khoa_cn = f_chuan_hoa(%s)", (tu_khoa,)).fetchone():
            catalog.them_dong_nghia(conn, chu, tu_khoa, tu_chuan)
            kq["dong_nghia"].append(f"{tu_khoa} → {tu_chuan}")
    return kq


def in_bao_cao(kq: dict, xem_truoc: bool) -> None:
    dau = "XEM TRƯỚC (đã hoàn tác, chưa ghi gì)" if xem_truoc else "ĐÃ NẠP"
    print(f"{dau}: {len(kq['mat_hang'])} mặt hàng mới, bỏ qua {len(kq['bo_qua'])} mặt hàng đã có")
    if kq["loai_go_moi"]:
        print("  Loại gỗ mới:", ", ".join(kq["loai_go_moi"]))
    if kq["xuong_moi"]:
        print("  Xưởng mới:", "; ".join(kq["xuong_moi"]))
    for ma, xuong, tong in kq["phieu_nhap"]:
        print(f"  Phiếu nhập {ma} • {xuong}: {tong:,} đ".replace(",", "."))
    if kq["bo"]:
        print("  Bộ sản phẩm mới:", ", ".join(kq["bo"]))
    if kq["dong_nghia"]:
        print("  Từ đồng nghĩa mới:", "; ".join(kq["dong_nghia"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Bổ sung 30 mặt hàng nội thất gỗ mẫu vào danh mục")
    p.add_argument("--xem-truoc", action="store_true", help="chạy thử rồi hoàn tác, không ghi gì")
    p.add_argument("--tai-khoan", help="tên đăng nhập của Chủ ghi trong nhật ký (mặc định: Chủ đầu tiên)")
    a = p.parse_args()
    try:
        with db.connect() as conn:   # một giao dịch: commit khi thoát khối, lỗi giữa chừng thì không ghi gì
            bao_cao = nap(conn, nguoi_chu(conn, a.tai_khoan))
            if a.xem_truoc:
                conn.rollback()
    except LoiNghiepVu as e:
        raise SystemExit(f"Lỗi dữ liệu, chưa ghi gì: {e.thong_bao}") from e
    in_bao_cao(bao_cao, a.xem_truoc)
