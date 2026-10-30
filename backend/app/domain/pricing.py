"""Ba công thức tính giá hàng đặt riêng (FR-02). Toàn bộ là số học số nguyên/phân số,
kết quả làm tròn đến nghìn đồng (nửa lên).

    Theo chiều dài : đơn giá/m  × dài(m)          × hệ số gỗ + phụ phí
    Theo diện tích : đơn giá/m² × dài(m) × rộng(m) × hệ số gỗ + phụ phí
    Theo bậc       : tra bảng giá cố định theo kích thước chuẩn
"""
from dataclasses import dataclass, field
from fractions import Fraction

from .text import dinh_dang_tien

THEO_CHIEU_DAI = "THEO_CHIEU_DAI"
THEO_DIEN_TICH = "THEO_DIEN_TICH"
THEO_BAC = "THEO_BAC"


class LoiCongThuc(ValueError):
    pass


@dataclass
class CongThucGia:
    kieu: str
    don_gia: int | None = None
    phu_phi: int = 0
    bac_gia: list[dict] = field(default_factory=list)   # [{"toi_da_mm": 1600, "gia": 7800000}, ...]
    kich_thuoc_min_mm: int = 400
    kich_thuoc_max_mm: int = 3000
    ty_le_gia_von_phan_nghin: int = 650
    ty_le_gia_san_phan_nghin: int = 800


@dataclass
class KetQuaGia:
    gia: int
    dien_giai: str
    tham_so: dict


def lam_tron_nghin(gia_tri: Fraction | int) -> int:
    gia_tri = Fraction(gia_tri)
    if gia_tri < 0:
        raise LoiCongThuc("Giá không được âm")
    nghin = gia_tri / 1000
    return int(nghin + Fraction(1, 2)) * 1000  # int() cắt về 0, với số dương là làm tròn nửa lên


def _he_so_hien_thi(he_so_phan_nghin: int) -> str:
    return f"{Fraction(he_so_phan_nghin, 1000):.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _met_hien_thi(mm: int) -> str:
    return f"{Fraction(mm, 1000):.3f}".rstrip("0").rstrip(".").replace(".", ",")


def tinh_theo_chieu_dai(don_gia_m: int, dai_mm: int, he_so_phan_nghin: int = 1000, phu_phi: int = 0) -> int:
    _kiem_tra_so_nguyen_khong_am(don_gia_m=don_gia_m, dai_mm=dai_mm, phu_phi=phu_phi)
    tho = Fraction(don_gia_m * dai_mm * he_so_phan_nghin, 1_000_000) + phu_phi
    return lam_tron_nghin(tho)


def tinh_theo_dien_tich(don_gia_m2: int, dai_mm: int, rong_mm: int,
                        he_so_phan_nghin: int = 1000, phu_phi: int = 0) -> int:
    _kiem_tra_so_nguyen_khong_am(don_gia_m2=don_gia_m2, dai_mm=dai_mm, rong_mm=rong_mm, phu_phi=phu_phi)
    tho = Fraction(don_gia_m2 * dai_mm * rong_mm * he_so_phan_nghin, 1_000_000_000) + phu_phi
    return lam_tron_nghin(tho)


def tinh_theo_bac(bac_gia: list[dict], kich_thuoc_mm: int) -> int:
    if not bac_gia:
        raise LoiCongThuc("Chưa khai báo bảng bậc giá")
    for bac in sorted(bac_gia, key=lambda b: b["toi_da_mm"]):
        if kich_thuoc_mm <= bac["toi_da_mm"]:
            return int(bac["gia"])
    lon_nhat = max(b["toi_da_mm"] for b in bac_gia)
    raise LoiCongThuc(f"Kích thước {kich_thuoc_mm} mm vượt bậc lớn nhất ({lon_nhat} mm)")


def tinh_gia(cong_thuc: CongThucGia, kich_thuoc_mm: list[int], loai_go: str | None = None,
             he_so_phan_nghin: int = 1000) -> KetQuaGia:
    if not kich_thuoc_mm:
        raise LoiCongThuc("Thiếu kích thước")
    ten_go = f" (gỗ {loai_go})" if loai_go else ""

    if cong_thuc.kieu == THEO_CHIEU_DAI:
        dai = kich_thuoc_mm[0]
        gia = tinh_theo_chieu_dai(cong_thuc.don_gia, dai, he_so_phan_nghin, cong_thuc.phu_phi)
        dien_giai = (f"{dinh_dang_tien(cong_thuc.don_gia)}/m × {_he_so_hien_thi(he_so_phan_nghin)}{ten_go}"
                     f" × {_met_hien_thi(dai)} m")
        tham_so = {"dai_mm": dai}
    elif cong_thuc.kieu == THEO_DIEN_TICH:
        if len(kich_thuoc_mm) < 2:
            raise LoiCongThuc("Tính theo diện tích cần nhập Dài × Rộng")
        dai, rong = kich_thuoc_mm[0], kich_thuoc_mm[1]
        gia = tinh_theo_dien_tich(cong_thuc.don_gia, dai, rong, he_so_phan_nghin, cong_thuc.phu_phi)
        dien_giai = (f"{dinh_dang_tien(cong_thuc.don_gia)}/m² × ({_met_hien_thi(dai)} m × {_met_hien_thi(rong)} m)"
                     f" × {_he_so_hien_thi(he_so_phan_nghin)}{ten_go}")
        tham_so = {"dai_mm": dai, "rong_mm": rong}
    elif cong_thuc.kieu == THEO_BAC:
        kt = kich_thuoc_mm[0]
        gia = tinh_theo_bac(cong_thuc.bac_gia, kt)
        dien_giai = f"Bậc kích thước {_met_hien_thi(kt)} m"
        tham_so = {"kich_thuoc_mm": kt}
    else:
        raise LoiCongThuc(f"Kiểu công thức không hợp lệ: {cong_thuc.kieu}")

    if cong_thuc.phu_phi and cong_thuc.kieu != THEO_BAC:
        dien_giai += f" + phụ phí {dinh_dang_tien(cong_thuc.phu_phi)}"
    dien_giai += f" = {dinh_dang_tien(gia)}"
    tham_so["he_so_phan_nghin"] = he_so_phan_nghin if cong_thuc.kieu != THEO_BAC else None
    return KetQuaGia(gia=gia, dien_giai=dien_giai, tham_so=tham_so)


def gia_theo_ty_le(gia: int, ty_le_phan_nghin: int) -> int:
    return lam_tron_nghin(Fraction(gia * ty_le_phan_nghin, 1000))


def _kiem_tra_so_nguyen_khong_am(**gia_tri) -> None:
    for ten, v in gia_tri.items():
        if not isinstance(v, int) or isinstance(v, bool):
            raise LoiCongThuc(f"{ten} phải là số nguyên")
        if v < 0:
            raise LoiCongThuc(f"{ten} không được âm")
