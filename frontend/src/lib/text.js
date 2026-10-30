export function boDau(s) {
  return String(s ?? '').replace(/đ/g, 'd').replace(/Đ/g, 'D').normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function chuanHoa(s) {
  return boDau(s).toLowerCase().replace(/\s+/g, ' ').trim()
}
