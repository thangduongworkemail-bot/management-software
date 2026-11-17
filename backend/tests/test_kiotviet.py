"""Đọc file KiotViet và lập kế hoạch nhập — logic thuần, không cần CSDL."""
import csv
import io

import pytest

from app.domain.kiotviet import (LoiFileKiotViet, doan_loai_go, doan_nhom, doc_csv, doc_kich_thuoc_thuoc_tinh,
                                 lap_ke_hoach)

TIEU_DE = ["Loại hàng", "Nhóm hàng(3 Cấp)", "Mã hàng", "Tên hàng", "Giá bán", "Giá vốn", "Tồn kho", "Tồn nhỏ nhất",
           "ĐVT", "Thuộc tính", "Mã HH Liên quan", "Hình ảnh (url1,url2...)", "Đang kinh doanh"]
LOAI_GO = ["Sồi", "Mít", "Gõ đỏ", "Xoan đào", "Óc chó", "MDF"]


def _dong(ma, ten, gia_ban="1,000,000.0", gia_von="600,000.0", ton="1.0", thuoc_tinh="", lien_quan="",
          loai="Hàng hóa", dvt="cái", anh="", kinh_doanh="1", toi_thieu="0.0"):
    return [loai, "Đồ gỗ", ma, ten, gia_ban, gia_von, ton, toi_thieu, dvt, thuoc_tinh, lien_quan, anh, kinh_doanh]


def _csv(*dong) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows([TIEU_DE, *dong])
    return buf.getvalue().encode("utf-8-sig")


def _ke_hoach(*dong):
    return lap_ke_hoach(doc_csv(_csv(*dong)), LOAI_GO)


def test_gom_bien_the_theo_ma_lien_quan():
    kh, bo_qua = _ke_hoach(
        _dong("SP000058", "kệ ti vi gỗ xồi Nga", "4,000,000.0", "1,800,000.0", "0.0", "CHÂN:1m8"),
        _dong("SP000061", "kệ ti vi gỗ xồi Nga", "6,000,000.0", "2,800,000.0", "4.0", "CHÂN:2m4", "SP000058"),
        _dong("sp000032", "giường gỗ lát ta", "3,800,000.0", "1,700,000.0", "9.0", "CHÂN:m6x2m",
              anh="https://anh.vn/g.jpg,https://anh.vn/g2.jpg", toi_thieu="3.0"))
    assert bo_qua == []
    ke, ke_2m4, giuong = kh
    assert (ke.ma, ke.ten_hien_thi, ke.ten_mau) == ("SP000058", "Kệ ti vi gỗ xồi Nga – 1m8", "Kệ ti vi gỗ xồi Nga")
    assert (ke_2m4.ten_hien_thi, ke_2m4.ten_mau, ke_2m4.dai_mm) == ("Kệ ti vi gỗ xồi Nga – 2m4", "Kệ ti vi gỗ xồi Nga", 2400)
    assert (ke_2m4.gia_niem_yet, ke_2m4.gia_von, ke_2m4.ton) == (6_000_000, 2_800_000, 4)
    assert (ke.ma_loai_hang, ke.loai_go, ke.thuoc_tinh, ke.don_vi_tinh) == ("TU_KE", "Sồi", {"Chân": "1m8"}, "cái")
    # Hàng đứng một mình không ghép thuộc tính vào tên; mã viết hoa; lấy ảnh đầu tiên
    assert (giuong.ma, giuong.ten_hien_thi, giuong.ma_loai_hang) == ("SP000032", "Giường gỗ lát ta", "GIUONG")
    assert (giuong.rong_mm, giuong.dai_mm, giuong.loai_go) == (1600, 2000, None)
    assert (giuong.anh_url, giuong.ton_toi_thieu) == ("https://anh.vn/g.jpg", 3)


@pytest.mark.parametrize("gia_tri, mm", [
    ("2m4", (2400, None)), ("1m", (1000, None)), ("m8x2m", (2000, 1800)), ("m5xm9", (1900, 1500)),
    ("2mx2m2", (2200, 2000)), ("rộng 80", (800, None)), ("rộng m2", (1200, None)), ("61cm", (610, None)),
    ("35 cm", (350, None)), ("chân 14", (None, None)), ("3 buồng", (None, None)), ("chân quỳ", (None, None)),
    ("12000000", (None, None)),
])
def test_kich_thuoc_tu_thuoc_tinh(gia_tri, mm):
    assert doc_kich_thuoc_thuoc_tinh(gia_tri) == mm


@pytest.mark.parametrize("ten, nhom", [
    ("bàn thờ thần tài gỗ xồi Nga", "DO_THO"), ("xập thờ gỗ mít ta", "DO_THO"), ("đài nến", "DO_THO"),
    ("giat phản", "GIUONG"), ("tap đầu giường gỗ xoan đào", "GIUONG"), ("bàn phấn gỗ công nghiệp", "GO_CN"),
    ("Tủ áo gỗ lát", "TU_KE"), ("kệ ti vi gỗ hương đá", "TU_KE"), ("bộ bàn ghế sopa gỗ hương đá", "BAN_GHE"),
    ("đệm gối da", "BAN_GHE"), ("chổi lau nhà", None),
])
def test_doan_nhom_hang(ten, nhom):
    assert doan_nhom(ten) == nhom


def test_doan_loai_go_chi_theo_bang_he_so():
    assert doan_loai_go("Tủ áo gỗ xoan đào", LOAI_GO) == "Xoan đào"
    assert doan_loai_go("Tủ áo gỗ xoan ta", LOAI_GO) is None
    assert doan_loai_go("xập thờ gỗ mít ta", LOAI_GO) == "Mít"
    assert doan_loai_go("bàn ghế gỗ xồi Nga sopa góc", LOAI_GO) == "Sồi"


def test_canh_bao_so_lieu_dang_ngo():
    kh, _ = _ke_hoach(
        _dong("SP1", "kệ ti vi gỗ xồi Nga", "5,000,000.0", "260,000.0", thuoc_tinh="CHÂN:2m2"),
        _dong("SP2", "kệ ti vi gỗ xồi Nga", "6,000,000.0", "2,800,008.0", thuoc_tinh="CHÂN:2m4", lien_quan="SP1"),
        _dong("SP3", "kệ ti vi gỗ xồi Nga", thuoc_tinh="CHÂN:2m2", lien_quan="SP1"),
        _dong("SP4", "bộ ghế phòng khách gỗ xồi", thuoc_tinh="Bộ:12000000"),
        _dong("SP5", "tam cấp", "250,000.0", "300,000.0", ton="-2.0"))
    cb = {m.ma: " | ".join(m.canh_bao) for m in kh}
    assert "thiếu chữ số" in cb["SP1"] and "lẻ đến hàng đơn vị" in cb["SP2"] and "Trùng tên" in cb["SP3"]
    assert "trông như giá tiền" in cb["SP4"] and kh[3].thuoc_tinh == {"Bộ": "12000000"}
    assert "không thấp hơn giá bán" in cb["SP5"] and "Tồn âm" in cb["SP5"] and kh[4].ton == 0


def test_bo_qua_dich_vu_va_hang_ngung_kinh_doanh():
    kh, bo_qua = _ke_hoach(_dong("DV1", "Công lắp đặt", loai="Dịch vụ"), _dong("SP1", "tủ cũ", kinh_doanh="0"),
                           _dong("SP2", "tủ mới"))
    assert [m.ma for m in kh] == ["SP2"] and len(bo_qua) == 2


@pytest.mark.parametrize("dong", [
    [_dong("SP 01", "tủ")], [_dong("SP1", "tủ"), _dong("sp1", "tủ khác")], [_dong("SP1", "")],
])
def test_ma_sai_trung_hoac_thieu_ten_thi_khong_nhap_gi(dong):
    with pytest.raises(LoiFileKiotViet):
        _ke_hoach(*dong)


def test_tu_choi_file_da_mat_dau():
    """File bị Excel lưu lại bằng bảng mã Latin-1: chữ tiếng Việt thành '?', không đoán bừa."""
    hong = "Mã hàng,Tên hàng,Giá bán\nSP000097,b? bàn gh? tay h?p,26000000\n".encode("latin-1", "replace")
    with pytest.raises(LoiFileKiotViet, match="mất dấu"):
        doc_csv(hong)


def test_doc_file_cp1258_cua_excel_tieng_viet():
    # cp1258: "à", "ê", "đ" có sẵn; dấu ngã (0xDE), sắc (0xEC), hỏi (0xD2) là ký tự tổ hợp -> phải chuẩn hóa NFC
    du_lieu = b"Ma\xde h\xe0ng,T\xean h\xe0ng,Gia\xec ba\xecn\n" + b'SP1,"B\xe0n \xf0a\xec, Tu\xd2",1000000\n'
    dong = doc_csv(du_lieu)
    assert dong[0]["ten"] == "Bàn đá, Tủ" and dong[0]["gia_ban"] == "1000000"


def test_thieu_cot_bat_buoc():
    with pytest.raises(LoiFileKiotViet, match="thiếu cột"):
        doc_csv("Mã hàng,Tên\nSP1,tủ\n".encode())
