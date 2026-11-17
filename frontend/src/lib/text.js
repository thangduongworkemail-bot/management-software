export function boDau(s) {
  return String(s ?? '').replace(/đ/g, 'd').replace(/Đ/g, 'D').normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function chuanHoa(s) {
  return boDau(s).toLowerCase().replace(/\s+/g, ' ').trim()
}

const thoatRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Có cụm từ `tu` đứng thành từ riêng trong `s` (cả hai đã chuẩn hóa) — giống f_chua_tu() trong CSDL. */
export const chuaTu = (s, tu) => new RegExp(`(?<![\\w])${thoatRegex(tu)}(?![\\w])`).test(s)

/** Bổ sung tên chuẩn của các từ đồng nghĩa có trong chuỗi tìm kiếm của mặt hàng, để hàng tên "tủ áo" vẫn
 *  khớp câu tìm đã đổi sang "tủ quần áo" — giống f_mo_rong_dong_nghia() trong CSDL. */
export function moRongDongNghia(s, dongNghia) {
  return [s, ...dongNghia.filter(d => chuaTu(s, d.tu_khoa_cn)).map(d => d.tu_chuan_cn)].join(' ')
}
