import { reactive } from 'vue'

function doc(khoa) {
  try { return JSON.parse(localStorage.getItem(khoa)) } catch { return null }
}
function ghi(khoa, gia_tri) {
  try {
    if (gia_tri === null) localStorage.removeItem(khoa)
    else localStorage.setItem(khoa, JSON.stringify(gia_tri))
  } catch { /* chế độ riêng tư: bỏ qua */ }
}

export const trangThai = reactive({
  token: doc('kv_token'),
  nguoi: doc('kv_nguoi'),
  online: navigator.onLine,
  donCho: 0,          // số đơn ngoại tuyến chưa đồng bộ
  thongBao: [],       // toast
  suKien: 0,          // tăng mỗi khi có sự kiện realtime -> view tự tải lại
  suKienCuoi: null,
})

export const laChu = () => trangThai.nguoi?.vai_tro === 'CHU'
export const xemGiaVon = () => ['CHU', 'QUAN_TRI'].includes(trangThai.nguoi?.vai_tro)

export function dangNhapXong(token, nguoi) {
  trangThai.token = token
  trangThai.nguoi = nguoi
  ghi('kv_token', token)
  ghi('kv_nguoi', nguoi)
}

export function dangXuat() {
  trangThai.token = null
  trangThai.nguoi = null
  ghi('kv_token', null)
  ghi('kv_nguoi', null)
}

let soToast = 0
export function bao(noiDung, loai = 'thong-tin', giay = 5) {
  const id = ++soToast
  trangThai.thongBao.push({ id, noiDung, loai })
  setTimeout(() => {
    const i = trangThai.thongBao.findIndex(t => t.id === id)
    if (i >= 0) trangThai.thongBao.splice(i, 1)
  }, giay * 1000)
}

window.addEventListener('online', () => { trangThai.online = true })
window.addEventListener('offline', () => { trangThai.online = false })
