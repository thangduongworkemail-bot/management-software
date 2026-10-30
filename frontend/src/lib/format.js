export const tien = (n) => (n === null || n === undefined ? '—' : `${Number(n).toLocaleString('vi-VN')} đ`)

export const ngayGio = (s) => (s ? new Date(s).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '—')

export const ngay = (s) => (s ? new Date(s).toLocaleDateString('vi-VN') : '—')

export const TRANG_THAI_DON = {
  CHO_DUYET_GIA: ['Chờ Chủ duyệt giá', 'canh-bao'],
  CHO_THANH_TOAN: ['Chờ thanh toán', 'canh-bao'],
  CON_NO: ['Đã cọc / còn nợ', 'canh-bao'],
  DA_THANH_TOAN: ['Đã thanh toán', 'tot'],
  HET_HAN: ['Hết hạn giữ chỗ', 'xam'],
  DA_HUY: ['Đã hủy', 'xam'],
  CHUA_GIAO: ['Chưa giao', 'xam'],
  DA_GIAO: ['Đã giao', 'tot'],
  CHO_XUONG_GIAO: ['Chờ xưởng giao', 'canh-bao'],
  XUNG_DOT_TON: ['Xung đột tồn', 'loi'],
  CHUA_CAN: ['Không cần HĐĐT', 'xam'],
  CHO_XUAT: ['Chờ xuất HĐĐT', 'canh-bao'],
  DA_XUAT: ['Đã xuất HĐĐT', 'tot'],
  LOI: ['Lỗi — cần xử lý', 'loi'],
  CHUA_KHOP: ['Chưa khớp đơn', 'loi'],
  LECH_TIEN: ['Lệch tiền', 'loi'],
  DA_KHOP: ['Đã khớp', 'tot'],
  DOI_SOAT: ['Đã đối soát', 'tot'],
}

export const nhanTrangThai = (ma) => TRANG_THAI_DON[ma]?.[0] || ma

export const LOAI_SO_CAI = {
  NHAP: 'Nhập kho', XUAT: 'Xuất bán', GIU_CHO: 'Giữ chỗ', NHA_CHO: 'Nhả giữ chỗ',
  TRA_HANG: 'Khách trả', DIEU_CHINH: 'Điều chỉnh',
}

export const kichThuoc = (h) => [h.dai_mm, h.rong_mm, h.cao_mm].filter(Boolean).join(' × ') + (h.dai_mm || h.rong_mm || h.cao_mm ? ' mm' : '')

export const giaTriThuocTinh = (v) => (v === true ? 'Có' : v === false ? 'Không' : String(v))

/** Thông số chi tiết của một mặt hàng dạng [nhãn, giá trị], bỏ các ô trống. */
export function thongSo(h) {
  const kt = kichThuoc(h)
  return [
    ['Nhóm / mẫu', [h.loai_hang, h.mau_hang].filter(Boolean).join(' • ')],
    ['Loại gỗ', h.loai_go], ['Màu sắc', h.mau_sac], ['Hoàn thiện bề mặt', h.hoan_thien],
    ['Kiểu dáng', h.kieu_dang], ['Vật liệu / phụ kiện', h.vat_lieu_phu],
    ['Kích thước (D × R × C)', kt.trim() ? kt : null],
    ['Khối lượng', h.khoi_luong_kg ? `${h.khoi_luong_kg} kg` : null],
    ['Bảo hành', h.bao_hanh_thang ? `${h.bao_hanh_thang} tháng` : null],
    ['Xuất xứ', h.xuat_xu], ['Đơn vị tính', h.don_vi_tinh],
    ...Object.entries(h.thuoc_tinh || {}).filter(([, v]) => v !== '' && v !== null && v !== 0).map(([k, v]) => [k, giaTriThuocTinh(v)]),
  ].filter(([, v]) => v !== null && v !== undefined && v !== '')
}
