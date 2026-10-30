"""Sinh chuỗi VietQR động (chuẩn EMVCo/Napas 247) cho từng đơn hàng."""


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def tao_chuoi_vietqr(bank_bin: str, so_tai_khoan: str, so_tien: int, noi_dung: str) -> str:
    if so_tien <= 0:
        raise ValueError("Số tiền VietQR phải dương")
    thu_huong = _tlv("00", bank_bin) + _tlv("01", so_tai_khoan)
    merchant = _tlv("00", "A000000727") + _tlv("01", thu_huong) + _tlv("02", "QRIBFTTA")
    payload = (
        _tlv("00", "01")
        + _tlv("01", "12")              # QR động, dùng một lần
        + _tlv("38", merchant)
        + _tlv("53", "704")             # VND
        + _tlv("54", str(so_tien))
        + _tlv("58", "VN")
        + _tlv("62", _tlv("08", noi_dung[:25]))
        + "6304"
    )
    return payload + f"{crc16_ccitt(payload.encode('utf-8')):04X}"
