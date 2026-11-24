/**
 * Thông báo đẩy (Web Push) trên máy đang dùng: Chủ nhận yêu cầu duyệt giá, tiền về lệch, hàng sắp hết
 * ngay cả khi app đang đóng. Hỗ trợ: Android (Chrome, Edge, Samsung Internet), máy tính (Chrome, Edge, Firefox),
 * iPhone/iPad iOS 16.4+ khi đã cài ra màn hình chính.
 */
import { reactive } from 'vue'
import { get, post } from './api'
import { dangChayNhuApp, laAppGoc, laIOS } from './nen-tang'

// trangThai: 'dang-kiem-tra' | 'khong-ho-tro' | 'can-cai-app' | 'bi-chan' | 'chua-bat' | 'da-bat'
export const day = reactive({ trangThai: 'dang-kiem-tra' })

const coApiDay = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

function tuB64u(s) {
  const nhi = atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (s.length % 4)) % 4))
  return Uint8Array.from(nhi, (c) => c.charCodeAt(0))
}
function raB64u(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function dangKyTrinhDuyet() {
  const reg = await navigator.serviceWorker.getRegistration()
  return { reg, sub: reg ? await reg.pushManager.getSubscription() : null }
}

export async function kiemTraDay() {
  if (laAppGoc) { day.trangThai = 'khong-ho-tro'; return day.trangThai }
  if (!coApiDay()) {
    // Safari trên iPhone chỉ có Web Push khi mở từ biểu tượng đã cài ra màn hình chính
    day.trangThai = laIOS && !dangChayNhuApp() ? 'can-cai-app' : 'khong-ho-tro'
    return day.trangThai
  }
  if (Notification.permission === 'denied') { day.trangThai = 'bi-chan'; return day.trangThai }
  try {
    const { reg, sub } = await dangKyTrinhDuyet()
    day.trangThai = !reg ? 'khong-ho-tro' : sub && Notification.permission === 'granted' ? 'da-bat' : 'chua-bat'
  } catch {
    day.trangThai = 'khong-ho-tro'
  }
  return day.trangThai
}

/** Gọi sau khi đăng nhập: máy đã bật thông báo thì gắn lại vào tài khoản vừa đăng nhập. */
export async function dongBoDangKy() {
  if ((await kiemTraDay()) !== 'da-bat') return
  const { sub } = await dangKyTrinhDuyet()
  await post('/day/dang-ky', sub.toJSON()).catch(() => {})
}

/** Phải gọi trực tiếp trong sự kiện bấm nút (iOS chỉ cho xin quyền khi người dùng vừa chạm). */
export async function batDay() {
  const quyen = await Notification.requestPermission()
  if (quyen !== 'granted') {
    day.trangThai = quyen === 'denied' ? 'bi-chan' : 'chua-bat'
    return false
  }
  const { reg, sub: cu } = await dangKyTrinhDuyet()
  if (!reg) throw new Error('Ứng dụng chưa sẵn sàng chạy nền. Tải lại trang rồi thử lại.')
  const { khoa_cong_khai } = await get('/day/khoa')
  let sub = cu
  // Máy chủ đổi khóa thì đăng ký cũ vô hiệu: đăng ký lại
  if (sub && sub.options?.applicationServerKey && raB64u(sub.options.applicationServerKey) !== khoa_cong_khai) {
    await sub.unsubscribe()
    sub = null
  }
  sub ||= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: tuB64u(khoa_cong_khai) })
  await post('/day/dang-ky', sub.toJSON())
  day.trangThai = 'da-bat'
  return true
}

export async function tatDay() {
  const { sub } = await dangKyTrinhDuyet()
  if (sub) {
    await post('/day/huy', { endpoint: sub.endpoint }).catch(() => {})
    await sub.unsubscribe()
  }
  day.trangThai = 'chua-bat'
}

/** Đăng xuất: máy không nhận thông báo của người vừa thoát nữa (giữ quyền để lần sau bật lại nhanh). */
export async function goKhiDangXuat() {
  try {
    const { sub } = await dangKyTrinhDuyet()
    if (sub) await post('/day/huy', { endpoint: sub.endpoint })
  } catch { /* mất mạng: máy chủ tự gắn lại cho người đăng nhập sau */ }
}

export const guiThu = () => post('/day/thu')
