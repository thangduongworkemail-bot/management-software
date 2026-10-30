"""Bộ đọc kích thước theo thói quen nói của thợ mộc, quy về số nguyên milimét.

    "1m8"      -> [1800]        "1,8m" / "1.8 m" -> [1800]
    "180"      -> [1800] (cm)   "2m4"            -> [2400]
    "1m8 x 2m" -> [1800, 2000]  "180 phân"       -> [1800]
    "1800mm"   -> [1800]        "1m05"           -> [1050]

Số trần không đơn vị: < 10 hiểu là mét, < 400 hiểu là cm (phân), còn lại là mm.
"""
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .text import bo_dau

MIN_MM_MAC_DINH = 400
MAX_MM_MAC_DINH = 3000

_HE_SO_DON_VI = {"mm": 1, "cm": 10, "phan": 10, "m": 1000, "met": 1000}

# 1m8, 1m85, 2m4, 1 m 8
_RE_M_KIEU_NOI = re.compile(r"^(\d+)\s*m\s*(\d+)$")
# 1,8m  1.8 m  180cm  1800mm  2m  180 phan  180
_RE_SO_DON_VI = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(mm|cm|phan|met|m)?$")
_RE_TACH_CHIEU = re.compile(r"\s*(?:x|×|\*|nhan)\s*")


class LoiKichThuoc(ValueError):
    pass


@dataclass
class KetQuaKichThuoc:
    goc: str
    gia_tri_mm: list[int]
    canh_bao: list[str] = field(default_factory=list)

    @property
    def hop_le(self) -> bool:
        return not self.canh_bao


def _sang_mm(so: Decimal, he_so: int) -> int:
    return int((so * he_so).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def doc_mot_kich_thuoc(token: str) -> int:
    t = bo_dau(token).lower().strip()
    if not t:
        raise LoiKichThuoc("Kích thước trống")

    m = _RE_M_KIEU_NOI.match(t)
    if m:
        so = Decimal(f"{m.group(1)}.{m.group(2)}")
        return _sang_mm(so, 1000)

    m = _RE_SO_DON_VI.match(t)
    if not m:
        raise LoiKichThuoc(f"Không hiểu kích thước '{token.strip()}'")
    try:
        so = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation as e:
        raise LoiKichThuoc(f"Không hiểu kích thước '{token.strip()}'") from e

    don_vi = m.group(2)
    if don_vi:
        return _sang_mm(so, _HE_SO_DON_VI[don_vi])
    if so < 10:
        return _sang_mm(so, 1000)
    if so < 400:
        return _sang_mm(so, 10)
    return _sang_mm(so, 1)


def doc_kich_thuoc(text: str, min_mm: int = MIN_MM_MAC_DINH, max_mm: int = MAX_MM_MAC_DINH) -> KetQuaKichThuoc:
    if text is None or not str(text).strip():
        raise LoiKichThuoc("Chưa nhập kích thước")
    chuoi = bo_dau(str(text)).lower().strip()
    phan = [p for p in _RE_TACH_CHIEU.split(chuoi) if p.strip()]
    if not phan:
        raise LoiKichThuoc(f"Không hiểu kích thước '{text}'")

    gia_tri = [doc_mot_kich_thuoc(p) for p in phan]
    canh_bao = []
    for mm in gia_tri:
        if mm < min_mm:
            canh_bao.append(f"{mm} mm nhỏ hơn mức tối thiểu {min_mm} mm")
        elif mm > max_mm:
            canh_bao.append(f"{mm} mm lớn hơn mức tối đa {max_mm} mm")
    return KetQuaKichThuoc(goc=str(text), gia_tri_mm=gia_tri, canh_bao=canh_bao)
