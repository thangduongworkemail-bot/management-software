"""Khôi phục dấu tiếng Việt cho file xuất từ KiotViet đã bị lưu lại bằng bảng mã Latin-1 (ANSI).

Khi mở CSV bằng Excel rồi "Save as CSV" trên máy không dùng bảng mã tiếng Việt, mọi chữ không có trong
Latin-1 (ạ, ộ, ế, ư, đ…) bị thay bằng dấu "?" — thông tin bị mất hẳn, không giải mã ngược được.
Script này khôi phục theo từ điển các từ có trong danh mục đồ gỗ, và kiểm chứng từng ô: chuỗi khôi phục
mã hóa lại sang Latin-1 phải ra đúng từng byte của file gốc. Từ nào chưa có trong từ điển thì dừng lại báo lỗi.

    python data_bo_sung/khoi_phuc_dau.py data_bo_sung/DanhSachSanPham_KV17112026-230038-395.csv

Kết quả ghi ra <tên gốc>_khoi_phuc.csv (UTF-8 có BOM, Excel mở đúng dấu) và in danh sách cần người duyệt.
"""
import csv
import re
import sys
from pathlib import Path

# Tiêu đề chuẩn của file "Danh sách hàng hóa" xuất từ KiotViet
TIEU_DE = ["Loại hàng", "Nhóm hàng(3 Cấp)", "Mã hàng", "Tên hàng", "Tên hàng trên hóa đơn điện tử", "Thương hiệu",
           "Giá bán", "Tỷ lệ tính thuế(%)", "Áp dụng giảm thuế", "Giá vốn", "Tồn kho", "KH đặt", "Dự kiến hết hàng",
           "Tồn nhỏ nhất", "Tồn lớn nhất", "ĐVT", "Mã ĐVT Cơ bản", "Quy đổi", "Thuộc tính", "Mã HH Liên quan",
           "Hình ảnh (url1,url2...)", "Trọng lượng", "Đang kinh doanh", "Được bán trực tiếp", "Mô tả", "Mẫu ghi chú",
           "Vị trí", "Hàng thành phần", "Thời gian tạo"]

# Từ bị hỏng (chữ thường, đúng như trong file) -> từ khôi phục. Mỗi "?" thay đúng một ký tự ngoài Latin-1.
TU_DIEN = {
    "??": "đồ", "??c": "đục", "??i": "đại", "??m": "đệm", "??u": "đầu", "?n": "ăn", "?nh": "ảnh",
    "?ài": "đài", "?àn": "đàn", "?ào": "đào", "?á": "đá", "b?": "bộ", "b?ch": "bạch", "bu?ng": "buồng",
    "c?p": "cấp", "c?t": "cột", "d?y": "dầy", "g?": "gỗ", "g?i": "gối", "gh?": "ghế", "gi??ng": "giường",
    "h??ng": "hương", "h?c": "học", "h?p": "hộp", "k?": "kệ", "l?ng": "lửng", "li?n": "liền", "m?ng": "mỏng",
    "m?t": "mặt", "m?u": "mẫu", "n?n": "nến", "nghi?p": "nghiệp", "nh?a": "nhựa", "p?": "pơ", "ph?": "phổ",
    "ph?n": "phản", "qu?": "quỳ", "r?ng": "rộng", "s?t": "sắt", "t?": "tủ", "t?ng": "tầng", "th?": "thờ",
    "th?n": "thần", "thuy?n": "thuyền", "v?ng": "văng", "x?i": "xồi", "x?p": "xập",
}

# Từ đoán theo ngữ cảnh, khôi phục được nhưng không chắc chắn: báo để người duyệt
KHONG_CHAC = {"c?t": "cột (có thể là cắt / cốt / cụt)", "l?ng": "lửng (có thể là lồng / lắng)"}

# Sửa theo cụm sau khi khôi phục từng từ. "g?" trong file chỉ có 2 ký tự nên gốc là "gế"/"gỗ" chứ không thể
# là "ghế"; ở các vị trí dưới đây nghĩa là ghế (gõ thiếu chữ h), nên sửa thẳng thành "ghế".
SUA_CUM = [
    ("bộ gỗ ăn", "bộ ghế ăn", "file ghi 'g?' (2 ký tự), theo nghĩa là 'ghế'"),
    ("bộ gỗ gỗ", "bộ ghế gỗ", "file ghi 'g?' (2 ký tự), theo nghĩa là 'ghế'"),
    ("bàn gỗ sopa", "bàn ghế sopa", "file ghi 'g?' (2 ký tự), theo nghĩa là 'ghế'"),
    ("bàn phản", "bàn phấn", "'ph?n' sau 'bàn' là bàn phấn (sau 'giat' là giát phản)"),
]

_RE_TU = re.compile(r"(?:[^\W\d_]|\?)+")   # một từ: chuỗi liền chữ cái hoặc "?"


def khop_byte(goc: str, moi: str) -> bool:
    """moi là bản khôi phục hợp lệ của goc nếu mã hóa lại sang Latin-1 (ký tự lạ -> '?') ra đúng goc."""
    return moi.encode("latin-1", "replace").decode("latin-1") == goc


def _giu_hoa(goc: str, moi: str) -> str:
    return moi[:1].upper() + moi[1:] if goc[:1].isupper() else moi


def khoi_phuc_o(goc: str) -> tuple[str, list[str]]:
    ghi_chu = []

    def thay(m):
        tu = m.group(0)
        if "?" not in tu:
            return tu
        if tu.lower() not in TU_DIEN:
            raise ValueError(f"Chưa có trong từ điển: '{tu}' (trong ô '{goc}')")
        if tu.lower() in KHONG_CHAC:
            ghi_chu.append(f"'{tu}' -> {KHONG_CHAC[tu.lower()]}")
        return _giu_hoa(tu, TU_DIEN[tu.lower()])

    moi = _RE_TU.sub(thay, goc)
    if "?" in moi or not khop_byte(goc, moi):
        raise ValueError(f"Không khôi phục trọn vẹn được ô '{goc}' -> '{moi}'")
    for cu, thay_bang, ly_do in SUA_CUM:
        if cu in moi.lower():
            i = moi.lower().index(cu)
            moi = moi[:i] + _giu_hoa(moi[i:], thay_bang) + moi[i + len(cu):]
            ghi_chu.append(f"'{cu}' -> '{thay_bang}': {ly_do}")
    return moi, ghi_chu


def main(duong_dan: str) -> None:
    goc = Path(duong_dan)
    dong = list(csv.reader(goc.open(encoding="latin-1", newline="")))
    if len(dong[0]) != len(TIEU_DE) or not all(khop_byte(g, m) for g, m in zip(dong[0], TIEU_DE)):
        raise SystemExit("Tiêu đề không khớp mẫu 'Danh sách hàng hóa' của KiotViet")

    can_duyet, ket_qua = [], [TIEU_DE]
    for r in dong[1:]:
        moi = []
        for i, o in enumerate(r):
            o_moi, ghi_chu = khoi_phuc_o(o)
            if i == 1:  # tên nhóm hàng viết hoa chữ đầu như trên KiotViet
                o_moi = o_moi[:1].upper() + o_moi[1:]
            if ghi_chu:
                can_duyet.append((r[2], TIEU_DE[i], o, o_moi, ghi_chu))
            moi.append(o_moi)
        ket_qua.append(moi)

    dich = goc.with_name(goc.stem + "_khoi_phuc.csv")
    with dich.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(ket_qua)
    print(f"Đã khôi phục {len(ket_qua) - 1} dòng -> {dich}")
    print(f"\nCần người duyệt ({len(can_duyet)} ô):")
    for ma, cot, o, o_moi, ghi_chu in can_duyet:
        print(f"  {ma} [{cot}] '{o}' -> '{o_moi}'")
        for g in ghi_chu:
            print(f"      {g}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_name("DanhSachSanPham_KV17112026-230038-395.csv")))
