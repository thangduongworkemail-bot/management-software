import pytest

from app.domain.dimension import LoiKichThuoc, doc_kich_thuoc, doc_mot_kich_thuoc


@pytest.mark.parametrize("vao, mm", [
    ("1m8", 1800), ("1M8", 1800), ("1 m 8", 1800), ("2m4", 2400), ("1m85", 1850), ("1m05", 1050),
    ("1,8m", 1800), ("1.8m", 1800), ("1,8 m", 1800), ("2m", 2000), ("2 mét", 2000), ("2 met", 2000),
    ("180", 1800), ("180cm", 1800), ("180 phân", 1800), ("1800", 1800), ("1800mm", 1800), ("1800 mm", 1800),
    ("2.4", 2400), ("2,4", 2400), ("0,5m", 500), ("45cm", 450),
])
def test_doc_mot_kich_thuoc(vao, mm):
    assert doc_mot_kich_thuoc(vao) == mm


@pytest.mark.parametrize("vao, ds", [
    ("1m8 x 2m", [1800, 2000]), ("1m8x2m", [1800, 2000]), ("1800×2000", [1800, 2000]), ("180 * 200", [1800, 2000]),
    ("1,6m x 80cm", [1600, 800]), ("2m4", [2400]), ("1m6 x 2m x 45cm", [1600, 2000, 450]),
])
def test_doc_nhieu_chieu(vao, ds):
    kq = doc_kich_thuoc(vao)
    assert kq.gia_tri_mm == ds
    assert kq.hop_le


def test_ket_qua_luon_la_so_nguyen():
    for vao in ("1m8", "1,85m", "183,3cm", "2.45"):
        assert all(isinstance(v, int) for v in doc_kich_thuoc(vao).gia_tri_mm)
    assert doc_mot_kich_thuoc("183,35cm") == 1834  # làm tròn nửa lên về mm


@pytest.mark.parametrize("vao, tu_khoa", [("30cm", "nhỏ hơn"), ("3m5", "lớn hơn"), ("350", "lớn hơn")])
def test_canh_bao_ngoai_dung_sai(vao, tu_khoa):
    kq = doc_kich_thuoc(vao)
    assert not kq.hop_le
    assert tu_khoa in kq.canh_bao[0]


def test_nguong_dung_sai_tuy_chinh():
    assert doc_kich_thuoc("1m", min_mm=1200, max_mm=2200).canh_bao
    assert doc_kich_thuoc("1m8", min_mm=1200, max_mm=2200).hop_le


@pytest.mark.parametrize("vao", ["", "   ", "abc", "1m8m", "m8", "1,,8", "x", "1m8 x abc"])
def test_dau_vao_khong_hieu(vao):
    with pytest.raises(LoiKichThuoc):
        doc_kich_thuoc(vao)
