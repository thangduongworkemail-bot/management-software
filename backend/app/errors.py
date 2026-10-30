class LoiNghiepVu(Exception):
    """Lỗi nghiệp vụ trả về cho client dưới dạng {"loi": ma, "thong_bao": ..., "chi_tiet": ...}."""

    def __init__(self, ma: str, thong_bao: str, http_status: int = 400, chi_tiet=None):
        super().__init__(thong_bao)
        self.ma = ma
        self.thong_bao = thong_bao
        self.http_status = http_status
        self.chi_tiet = chi_tiet


def khong_tim_thay(doi_tuong: str) -> LoiNghiepVu:
    return LoiNghiepVu("KHONG_TIM_THAY", f"Không tìm thấy {doi_tuong}", 404)


def khong_du_quyen(thong_bao: str = "Bạn không có quyền thực hiện thao tác này") -> LoiNghiepVu:
    return LoiNghiepVu("KHONG_DU_QUYEN", thong_bao, 403)
