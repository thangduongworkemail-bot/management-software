"""Adapter hóa đơn điện tử (Nghị định 123/2020/NĐ-CP).

Worker chỉ làm việc với giao diện `EInvoiceAdapter`; lỗi tạm thời (mạng, 5xx) ném
`LoiTamThoi` để được thử lại theo chu kỳ, lỗi dữ liệu ném `LoiVinhVien` để chủ xử lý.

MockAdapter là mặc định để chạy demo. VNPT / Viettel dựng theo tài liệu tích hợp công
khai của nhà cung cấp nhưng CHƯA được kiểm thử với tài khoản thật — cần đối chiếu lại
tài liệu kỹ thuật được cấp kèm hợp đồng trước khi bật ở môi trường sản xuất.
"""
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

import httpx

from ..config import settings


class LoiTamThoi(Exception):
    pass


class LoiVinhVien(Exception):
    pass


@dataclass
class DongHoaDon:
    ten: str
    don_vi_tinh: str
    so_luong: int
    don_gia: int
    thanh_tien: int


@dataclass
class YeuCauHoaDon:
    hoa_don_id: int
    ma_don: str
    ten_nguoi_mua: str | None
    ma_so_thue: str | None
    dia_chi: str | None
    email: str | None
    phuong_thuc_tt: str
    dong: list[DongHoaDon]
    tong_tien: int


@dataclass
class KetQuaHoaDon:
    ky_hieu: str
    so_hoa_don: str
    xml: str | None = None
    link_pdf: str | None = None
    link_xml: str | None = None


def kiem_tra_thong_tin_nguoi_mua(yc: YeuCauHoaDon) -> None:
    if not yc.ten_nguoi_mua and not yc.ma_so_thue:
        raise LoiVinhVien("Thiếu tên người mua hoặc mã số thuế")
    if not yc.dong:
        raise LoiVinhVien("Hóa đơn không có dòng hàng")


def tao_xml_hoa_don(yc: YeuCauHoaDon, ky_hieu: str, so_hoa_don: str) -> str:
    goc = ET.Element("HDon")
    ttc = ET.SubElement(ET.SubElement(goc, "DLHDon"), "TTChung")
    for tag, val in (("KHMSHDon", settings.einvoice_template.split("/")[0]), ("KHHDon", ky_hieu),
                     ("SHDon", so_hoa_don), ("NLap", datetime.now().strftime("%Y-%m-%d")),
                     ("DVTTe", "VND"), ("HTTToan", yc.phuong_thuc_tt), ("MaDon", yc.ma_don)):
        ET.SubElement(ttc, tag).text = val
    ndhd = ET.SubElement(goc.find("DLHDon"), "NDHDon")
    nban = ET.SubElement(ndhd, "NBan")
    ET.SubElement(nban, "MST").text = settings.einvoice_seller_tax_code
    ET.SubElement(nban, "Ten").text = "Cửa hàng Nội thất gỗ Khanh Vân"
    nmua = ET.SubElement(ndhd, "NMua")
    ET.SubElement(nmua, "Ten").text = yc.ten_nguoi_mua or ""
    ET.SubElement(nmua, "MST").text = yc.ma_so_thue or ""
    ET.SubElement(nmua, "DChi").text = yc.dia_chi or ""
    dshhdv = ET.SubElement(ndhd, "DSHHDVu")
    for i, d in enumerate(yc.dong, 1):
        hh = ET.SubElement(dshhdv, "HHDVu")
        for tag, val in (("STT", i), ("THHDVu", d.ten), ("DVTinh", d.don_vi_tinh), ("SLuong", d.so_luong),
                         ("DGia", d.don_gia), ("ThTien", d.thanh_tien)):
            ET.SubElement(hh, tag).text = str(val)
    ET.SubElement(ET.SubElement(ndhd, "TToan"), "TgTTTBSo").text = str(yc.tong_tien)
    return ET.tostring(goc, encoding="unicode")


class EInvoiceAdapter:
    ten = "BASE"

    def phat_hanh(self, yc: YeuCauHoaDon) -> KetQuaHoaDon:
        raise NotImplementedError


class MockAdapter(EInvoiceAdapter):
    """Giả lập cổng HĐĐT: cấp số hóa đơn, sinh XML; có thể cấu hình tỉ lệ lỗi để thử Retry Queue."""
    ten = "MOCK"

    def __init__(self, ti_le_loi: float | None = None):
        self.ti_le_loi = settings.einvoice_mock_fail_rate if ti_le_loi is None else ti_le_loi

    def phat_hanh(self, yc: YeuCauHoaDon) -> KetQuaHoaDon:
        kiem_tra_thong_tin_nguoi_mua(yc)
        if self.ti_le_loi and random.random() < self.ti_le_loi:
            raise LoiTamThoi("Cổng HĐĐT giả lập không phản hồi (timeout)")
        ky_hieu = settings.einvoice_series
        so = f"{yc.hoa_don_id:08d}"
        return KetQuaHoaDon(ky_hieu=ky_hieu, so_hoa_don=so, xml=tao_xml_hoa_don(yc, ky_hieu, so))


class ViettelSInvoiceAdapter(EInvoiceAdapter):
    """Viettel S-Invoice REST: POST /services/einvoiceapplication/api/InvoiceAPI/InvoiceWS/createInvoice/{MST}."""
    ten = "VIETTEL"

    def phat_hanh(self, yc: YeuCauHoaDon) -> KetQuaHoaDon:
        kiem_tra_thong_tin_nguoi_mua(yc)
        if not settings.viettel_username:
            raise LoiVinhVien("Chưa cấu hình tài khoản Viettel S-Invoice")
        url = (f"{settings.viettel_url}/services/einvoiceapplication/api/InvoiceAPI/InvoiceWS/"
               f"createInvoice/{settings.einvoice_seller_tax_code}")
        body = {
            "generalInvoiceInfo": {
                "invoiceType": "1", "templateCode": settings.einvoice_template,
                "invoiceSeries": settings.einvoice_series, "currencyCode": "VND",
                "adjustmentType": "1", "paymentStatus": True, "transactionUuid": f"KV-HD-{yc.hoa_don_id}",
            },
            "buyerInfo": {"buyerName": yc.ten_nguoi_mua or "", "buyerTaxCode": yc.ma_so_thue or "",
                          "buyerAddressLine": yc.dia_chi or "", "buyerEmail": yc.email or ""},
            "payments": [{"paymentMethodName": yc.phuong_thuc_tt}],
            "itemInfo": [{"lineNumber": i, "itemName": d.ten, "unitName": d.don_vi_tinh, "quantity": d.so_luong,
                          "unitPrice": d.don_gia, "itemTotalAmountWithoutTax": d.thanh_tien}
                         for i, d in enumerate(yc.dong, 1)],
            "summarizeInfo": {"totalAmountWithoutTax": yc.tong_tien, "totalAmountWithTax": yc.tong_tien},
        }
        data = _goi_http("POST", url, json=body, auth=(settings.viettel_username, settings.viettel_password))
        ket_qua = data.get("result") or {}
        if data.get("errorCode") or not ket_qua.get("invoiceNo"):
            raise LoiVinhVien(f"Viettel từ chối: {data.get('errorCode')} {data.get('description')}")
        so = ket_qua["invoiceNo"]
        return KetQuaHoaDon(ky_hieu=so[:len(settings.einvoice_series)], so_hoa_don=so)


class VnptInvoiceAdapter(EInvoiceAdapter):
    """VNPT Invoice: nghiệp vụ ImportAndPublishInv qua cổng dịch vụ của đơn vị."""
    ten = "VNPT"

    def phat_hanh(self, yc: YeuCauHoaDon) -> KetQuaHoaDon:
        kiem_tra_thong_tin_nguoi_mua(yc)
        if not settings.vnpt_url:
            raise LoiVinhVien("Chưa cấu hình địa chỉ dịch vụ VNPT Invoice")
        xml = tao_xml_hoa_don(yc, settings.einvoice_series, "0")
        data = _goi_http("POST", f"{settings.vnpt_url}/api/publish/importAndPublishInv", json={
            "account": settings.vnpt_username, "acPass": settings.vnpt_password,
            "xmlInvData": xml, "pattern": settings.einvoice_template, "serial": settings.einvoice_series,
        })
        ket_qua = str(data.get("result", ""))
        if ket_qua.startswith("ERR"):
            raise LoiVinhVien(f"VNPT từ chối: {ket_qua}")
        # Dạng trả về: "OK:pattern;serial-key_invNo"
        so = ket_qua.rsplit("_", 1)[-1] if "_" in ket_qua else ket_qua
        return KetQuaHoaDon(ky_hieu=settings.einvoice_series, so_hoa_don=so, xml=xml)


def _goi_http(method: str, url: str, **kwargs) -> dict:
    try:
        r = httpx.request(method, url, timeout=20, **kwargs)
    except httpx.HTTPError as e:
        raise LoiTamThoi(f"Lỗi kết nối cổng HĐĐT: {e}") from e
    if r.status_code >= 500 or r.status_code == 429:
        raise LoiTamThoi(f"Cổng HĐĐT trả lỗi {r.status_code}")
    if r.status_code >= 400:
        raise LoiVinhVien(f"Cổng HĐĐT từ chối ({r.status_code}): {r.text[:300]}")
    return r.json()


def lay_adapter(ten: str | None = None) -> EInvoiceAdapter:
    ten = (ten or settings.einvoice_provider).upper()
    return {"MOCK": MockAdapter, "VIETTEL": ViettelSInvoiceAdapter, "VNPT": VnptInvoiceAdapter}[ten]()
