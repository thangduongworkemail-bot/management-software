"""Đọc file "Danh sách hàng hóa" xuất từ KiotViet (CSV) và lập kế hoạch nhập vào danh mục.

Logic thuần, không đụng CSDL (phần ghi nằm ở app/nhap_kiotviet.py):
- tìm cột theo tên tiêu đề, không phụ thuộc thứ tự cột;
- gom biến thể theo "Mã HH Liên quan" thành một mẫu hàng, tên biến thể = tên + giá trị thuộc tính;
- xếp nhóm hàng của hệ thống theo từ khóa trong tên (không khớp thì dùng nhóm hàng của KiotViet);
- đọc kích thước từ thuộc tính ("2m4", "m8x2m", "rộng 80", "61cm") để tìm kiếm theo kích thước được;
- cảnh báo số liệu đáng ngờ (giá vốn quá thấp / lẻ, tồn âm, biến thể trùng) để người nhập kiểm tra lại.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .dimension import LoiKichThuoc, doc_kich_thuoc
from .text import chuan_hoa


class LoiFileKiotViet(ValueError):
    pass


# Tiêu đề KiotViet đã chuẩn hóa (bỏ dấu, chữ thường, bỏ phần trong ngoặc) -> khóa nội bộ
COT = {
    "loai hang": "loai", "nhom hang": "nhom", "ma hang": "ma", "ten hang": "ten", "gia ban": "gia_ban",
    "gia von": "gia_von", "ton kho": "ton", "ton nho nhat": "ton_toi_thieu", "dvt": "dvt",
    "thuoc tinh": "thuoc_tinh", "ma hh lien quan": "ma_lien_quan", "hinh anh": "hinh_anh",
    "dang kinh doanh": "dang_kinh_doanh", "mo ta": "mo_ta",
}
BAT_BUOC = ("ma", "ten", "gia_ban")

# Nhóm hàng của hệ thống (loai_hang.ma) theo từ khóa trong tên đã bỏ dấu; xét lần lượt, khớp đầu tiên thắng
QUY_TAC_NHOM = [
    ("DO_THO", r"\b(ban tho|an gian|[xs]ap tho|dai nen|tam cap|khung anh)\b"),
    ("GIUONG", r"\b(giuong|giat phan)\b"),
    ("GO_CN", r"\bcong nghiep\b"),
    ("TU_KE", r"\b(tu|ke)\b"),
    ("BAN_GHE", r"\b(ban|ghe|sopa|sopha|sofa|dem|goi)\b"),
]

# Cách viết riêng của cửa hàng -> tên loại gỗ chuẩn (đã bỏ dấu) để khớp bảng hệ số gỗ
BIET_DANH_GO = {"xoi": "soi"}

_RE_MA = re.compile(r"^[A-Z0-9][A-Za-z0-9-]*$")
_RE_MAT_DAU = re.compile(r"[^\W\d_]\?|\?[^\W\d_]|\?\?|�")
_RE_KICH_THUOC = re.compile(r"^(?:rong\s+)?[\dm][\dm.,]*(?:\s*(?:cm|mm))?(?:\s*x\s*[\dm][\dm.,]*(?:\s*(?:cm|mm))?)?$")


@dataclass
class MatHangNhap:
    so_dong: int
    ma: str
    ten_hien_thi: str
    ten_mau: str
    ma_loai_hang: str | None          # None: không đoán được, dùng nhóm hàng KiotViet
    nhom_kiotviet: str
    gia_niem_yet: int | None
    gia_von: int | None
    ton: int
    ton_toi_thieu: int
    don_vi_tinh: str | None
    thuoc_tinh: dict
    loai_go: str | None = None
    dai_mm: int | None = None
    rong_mm: int | None = None
    anh_url: str | None = None
    mo_ta: str | None = None
    canh_bao: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Đọc file
# ---------------------------------------------------------------------------
def _chuan_tieu_de(t: str) -> str:
    return re.sub(r"\(.*?\)", "", chuan_hoa(t)).strip()


def giai_ma(du_lieu: bytes) -> str:
    """KiotViet xuất UTF-8; Excel trên Windows tiếng Việt lưu lại CSV theo bảng mã cp1258."""
    try:
        van_ban = du_lieu.decode("utf-8-sig")
    except UnicodeDecodeError:
        van_ban = du_lieu.decode("cp1258", errors="replace")
    return unicodedata.normalize("NFC", van_ban)


def doc_csv(du_lieu: bytes) -> list[dict]:
    """Trả về các dòng dạng {khóa nội bộ: giá trị đã strip, 'so_dong': số dòng trong file}."""
    doc = csv.reader(io.StringIO(giai_ma(du_lieu)))
    try:
        tieu_de = next(doc)
    except StopIteration:
        raise LoiFileKiotViet("File trống") from None
    khoa = [COT.get(_chuan_tieu_de(t)) for t in tieu_de]
    thieu = [k for k in BAT_BUOC if k not in khoa]
    if thieu:
        raise LoiFileKiotViet("Không phải file 'Danh sách hàng hóa' của KiotViet: thiếu cột "
                              + ", ".join(thieu) + " (cần Mã hàng, Tên hàng, Giá bán)")
    dong = []
    for so_dong, r in enumerate(doc, start=2):
        if not any(o.strip() for o in r):
            continue
        d = {k: o.strip() for k, o in zip(khoa, r) if k}
        d["so_dong"] = so_dong
        dong.append(d)
    hong = [d.get("ma") or f"dòng {d['so_dong']}" for d in dong if _RE_MAT_DAU.search(d.get("ten", ""))]
    if hong:
        raise LoiFileKiotViet(
            f"File đã mất dấu tiếng Việt ở {len(hong)} dòng (ví dụ {hong[0]}): dấu bị thay bằng '?', thường do mở "
            "bằng Excel rồi lưu dạng CSV thường. Xuất lại từ KiotViet, hoặc trong Excel chọn 'CSV UTF-8'.")
    return dong


# ---------------------------------------------------------------------------
# Chuyển đổi từng ô
# ---------------------------------------------------------------------------
def doc_so(o: str | None, ten_cot: str) -> Decimal | None:
    """'26,000,000.0' / '26000000' / '26.000.000' -> Decimal; ô trống -> None."""
    s = (o or "").replace(" ", "")
    if not s or s in ("--", "-"):
        return None
    s = s.replace(",", "")
    if s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise LoiFileKiotViet(f"{ten_cot} '{o}' không phải số") from None


def viet_hoa_dau(s: str) -> str:
    return s[:1].upper() + s[1:]


def doc_thuoc_tinh(o: str | None) -> dict[str, str]:
    """'CHÂN:2m4|MÀU:nâu' -> {'Chân': '2m4', 'Màu': 'nâu'} (tên thuộc tính viết hoa chữ đầu)."""
    kq = {}
    for phan in (o or "").split("|"):
        if ":" in phan:
            ten, gia_tri = (x.strip() for x in phan.split(":", 1))
            if ten and gia_tri:
                kq[viet_hoa_dau(ten.lower())] = gia_tri
    return kq


def doc_kich_thuoc_thuoc_tinh(gia_tri: str) -> tuple[int | None, int | None]:
    """Kích thước ghi trong thuộc tính -> (dài, rộng) mm. 'm8x2m' là 1m8 × 2m (giường: rộng × dài);
    một số đo là chiều dài (mặt trước) của món đồ; 'chân 14', '2 buồng'… không phải kích thước."""
    s = chuan_hoa(gia_tri)
    if not _RE_KICH_THUOC.match(s) or not re.search(r"\d", s):
        return None, None
    s = re.sub(r"^rong\s+", "", s)
    s = re.sub(r"(^|x\s*)m(?=\d)", r"\g<1>1m", s)   # "m8" = 1m8, "m2" = 1m2 theo cách nói của thợ
    try:
        kq = doc_kich_thuoc(s, min_mm=100, max_mm=6000)   # ngoài 10cm–6m thì không phải số đo đồ gỗ
    except LoiKichThuoc:
        return None, None
    mm = kq.gia_tri_mm if kq.hop_le else []
    if len(mm) == 1:
        return mm[0], None
    if len(mm) == 2:
        return mm[1], mm[0]
    return None, None


def doan_nhom(ten: str) -> str | None:
    cn = chuan_hoa(ten)
    for ma, mau in QUY_TAC_NHOM:
        if re.search(mau, cn):
            return ma
    return None


def doan_loai_go(ten: str, loai_go_co_san: list[str]) -> str | None:
    tu = [BIET_DANH_GO.get(t, t) for t in re.findall(r"\w+", chuan_hoa(ten))]
    cau = f" {' '.join(tu)} "
    for go in sorted(loai_go_co_san, key=len, reverse=True):   # "xoan dao" trước "xoan"
        if f" {chuan_hoa(go)} " in cau:
            return go
    return None


# ---------------------------------------------------------------------------
# Lập kế hoạch nhập
# ---------------------------------------------------------------------------
def lap_ke_hoach(dong: list[dict], loai_go_co_san: list[str] = ()) -> tuple[list[MatHangNhap], list[str]]:
    """Trả về (mặt hàng sẽ nhập, các dòng bỏ qua kèm lý do). Lỗi dữ liệu nghiêm trọng (mã sai, trùng mã)
    làm hỏng cả file để không nhập một nửa."""
    loi, bo_qua, giu = [], [], []
    thay_ma = set()
    for d in dong:
        ma = d.get("ma", "").upper()
        if not _RE_MA.match(ma):
            loi.append(f"Dòng {d['so_dong']}: mã hàng '{d.get('ma', '')}' chỉ được gồm chữ không dấu, số và '-'")
        elif ma in thay_ma:
            loi.append(f"Dòng {d['so_dong']}: mã hàng {ma} bị trùng")
        thay_ma.add(ma)
        if d.get("loai") and chuan_hoa(d["loai"]) != "hang hoa":
            bo_qua.append(f"{ma}: loại '{d['loai']}' (chỉ nhập hàng hóa, không nhập dịch vụ / combo)")
        elif d.get("dang_kinh_doanh") == "0":
            bo_qua.append(f"{ma}: đã ngừng kinh doanh trên KiotViet")
        elif not d.get("ten"):
            loi.append(f"Dòng {d['so_dong']}: thiếu tên hàng")
        else:
            giu.append({**d, "ma": ma})
    if loi:
        raise LoiFileKiotViet("; ".join(loi))

    nhom_bien_the: dict[str, list[dict]] = {}
    for d in giu:
        nhom_bien_the.setdefault((d.get("ma_lien_quan") or d["ma"]).upper(), []).append(d)

    ke_hoach = []
    for khoa, cac_dong in nhom_bien_the.items():
        cha = next((d for d in cac_dong if d["ma"] == khoa), cac_dong[0])
        ten_mau = viet_hoa_dau(cha["ten"])
        ten_da_dung: dict[str, str] = {}
        for d in cac_dong:
            ke_hoach.append(_mot_mat_hang(d, ten_mau, len(cac_dong) > 1, ten_da_dung, loai_go_co_san))
    return ke_hoach, bo_qua


def _mot_mat_hang(d: dict, ten_mau: str, la_bien_the: bool, ten_da_dung: dict, loai_go_co_san) -> MatHangNhap:
    canh_bao = []
    ten = viet_hoa_dau(d["ten"])
    thuoc_tinh = doc_thuoc_tinh(d.get("thuoc_tinh"))
    if la_bien_the and thuoc_tinh:
        ten = f"{ten} – {', '.join(thuoc_tinh.values())}"
    if ten in ten_da_dung:
        canh_bao.append(f"Trùng tên & thuộc tính với {ten_da_dung[ten]} — có thể nhập trùng trên KiotViet")
    ten_da_dung.setdefault(ten, d["ma"])

    dai = rong = None
    for k, v in thuoc_tinh.items():
        if re.fullmatch(r"\d{5,}", v):
            canh_bao.append(f"Thuộc tính '{k}: {v}' trông như giá tiền — kiểm tra lại")
        if dai is None:
            dai, rong = doc_kich_thuoc_thuoc_tinh(v)

    gia_ban, gia_von = doc_so(d.get("gia_ban"), "Giá bán"), doc_so(d.get("gia_von"), "Giá vốn")
    gia_ban = int(gia_ban) if gia_ban else None
    gia_von = int(gia_von) if gia_von else None
    if not gia_ban:
        canh_bao.append("Chưa có giá bán")
    if gia_ban and gia_von:
        if gia_von >= gia_ban:
            canh_bao.append(f"Giá vốn {gia_von:,} không thấp hơn giá bán {gia_ban:,}")
        elif gia_von * 5 < gia_ban:
            canh_bao.append(f"Giá vốn {gia_von:,} chỉ bằng {gia_von * 100 // gia_ban}% giá bán {gia_ban:,} "
                            "— có thể gõ thiếu chữ số")
    if gia_von and gia_von % 1000:
        canh_bao.append(f"Giá vốn {gia_von:,} lẻ đến hàng đơn vị — có thể gõ nhầm")

    ton = doc_so(d.get("ton"), "Tồn kho") or Decimal(0)
    if ton != ton.to_integral_value():
        canh_bao.append(f"Tồn kho {ton} không nguyên, làm tròn xuống")
    if ton < 0:
        canh_bao.append(f"Tồn âm {ton} trên KiotViet (bán vượt tồn) — ghi tồn đầu kỳ 0")
        ton = Decimal(0)
    ton_toi_thieu = doc_so(d.get("ton_toi_thieu"), "Tồn nhỏ nhất") or Decimal(0)

    anh = next((u.strip() for u in (d.get("hinh_anh") or "").split(",") if u.strip().startswith(("http://", "https://"))),
               None)
    return MatHangNhap(
        so_dong=d["so_dong"], ma=d["ma"], ten_hien_thi=ten, ten_mau=ten_mau, ma_loai_hang=doan_nhom(d["ten"]),
        nhom_kiotviet=d.get("nhom") or "Hàng KiotViet", gia_niem_yet=gia_ban, gia_von=gia_von, ton=int(ton),
        ton_toi_thieu=max(int(ton_toi_thieu), 0), don_vi_tinh=d.get("dvt") or None, thuoc_tinh=thuoc_tinh,
        loai_go=doan_loai_go(d["ten"], list(loai_go_co_san)), dai_mm=dai, rong_mm=rong, anh_url=anh,
        mo_ta=d.get("mo_ta") or None, canh_bao=canh_bao)
