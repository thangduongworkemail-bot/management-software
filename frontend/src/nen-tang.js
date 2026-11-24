/**
 * Một mã nguồn chạy ở ba nơi:
 *  - trình duyệt máy tính quầy,
 *  - PWA cài từ trình duyệt lên điện thoại (Android: Chrome, iPhone: Safari > Thêm vào MH chính),
 *  - app gốc đóng gói bằng Capacitor (file APK cho Android, Xcode cho iOS).
 * File này gom mọi khác biệt giữa các nơi chạy để phần còn lại của giao diện không phải quan tâm.
 */
import { reactive } from 'vue'
import { Capacitor } from '@capacitor/core'
import { chuanHoaMayChu, noiUrl, urlWebSocket } from './lib/may-chu'

export const laAppGoc = Capacitor.isNativePlatform()
export const nenTang = Capacitor.getPlatform() // 'web' | 'android' | 'ios'

const ua = navigator.userAgent || ''
export const laIOS = nenTang === 'ios' || /iPhone|iPad|iPod/.test(ua)
  || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
export const laAndroid = nenTang === 'android' || /Android/i.test(ua)

/** Đang mở như một app (app gốc, hoặc PWA đã cài và mở từ biểu tượng ngoài màn hình chính). */
export function dangChayNhuApp() {
  return laAppGoc || window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true
}

// --- Máy chủ cửa hàng (chỉ app gốc cần chọn) ---------------------------------
const KHOA_MAY_CHU = 'kv_may_chu'
const MAY_CHU_MAC_DINH = (() => {
  try { return chuanHoaMayChu(import.meta.env.VITE_MAY_CHU) } catch { return '' }
})()

function docMayChu() {
  try { return localStorage.getItem(KHOA_MAY_CHU) || MAY_CHU_MAC_DINH } catch { return MAY_CHU_MAC_DINH }
}

export const mayChu = reactive({ goc: laAppGoc ? docMayChu() : '' })

/** Lưu địa chỉ máy chủ (đã kiểm tra kết nối được) cho app gốc. */
export function datMayChu(goc) {
  mayChu.goc = goc
  try { localStorage.setItem(KHOA_MAY_CHU, goc) } catch { /* bộ nhớ đầy: dùng tạm trong phiên */ }
}

export const canChonMayChu = () => laAppGoc && !mayChu.goc

/** Đường dẫn trên máy chủ ("/api/…", "/files/…") -> URL dùng được ở nơi đang chạy. */
export const urlMayChu = (duongDan) => noiUrl(mayChu.goc, duongDan)
/** Liên kết gửi cho khách (báo giá công khai): luôn là địa chỉ máy chủ thật, không phải địa chỉ nội bộ của app. */
export const urlCongKhai = (duongDan) => noiUrl(mayChu.goc || location.origin, duongDan)
export const urlRealtime = (token) => urlWebSocket(mayChu.goc || location.origin, token)

/** Thử kết nối máy chủ trước khi lưu, báo lỗi dễ hiểu cho người không rành máy tính. */
export async function kiemTraMayChu(nhap) {
  const goc = chuanHoaMayChu(nhap)
  if (!goc) throw new Error('Hãy nhập địa chỉ máy chủ của cửa hàng')
  const hen = new AbortController()
  const dongHo = setTimeout(() => hen.abort(), 8000)
  try {
    const res = await fetch(`${goc}/api/suc-khoe`, { signal: hen.signal })
    if (!res.ok) throw new Error(`Máy chủ trả lỗi ${res.status}`)
    const body = await res.json().catch(() => ({}))
    if (!body.ok) throw new Error('Địa chỉ này không phải máy chủ Khanh Vân')
    return goc
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Quá 8 giây không thấy máy chủ trả lời. Kiểm tra mạng hoặc địa chỉ.')
    if (e instanceof TypeError) throw new Error('Không kết nối được. Kiểm tra địa chỉ, wifi/4G, và máy chủ cửa hàng đang bật.')
    throw e
  } finally {
    clearTimeout(dongHo)
  }
}

// --- Chia sẻ (Zalo, Messenger…) --------------------------------------------------
/** Mở bảng chia sẻ của điện thoại; máy không có thì sao chép vào bộ nhớ tạm. Trả về 'chia-se' | 'sao-chep'. */
export async function chiaSe({ tieuDe, noiDung, url }) {
  if (laAppGoc) {
    const { Share } = await import('@capacitor/share')
    await Share.share({ title: tieuDe, text: noiDung, url, dialogTitle: tieuDe })
    return 'chia-se'
  }
  if (navigator.share) {
    await navigator.share({ title: tieuDe, text: noiDung, url })
    return 'chia-se'
  }
  await navigator.clipboard?.writeText([noiDung, url].filter(Boolean).join('\n'))
  return 'sao-chep'
}

// --- Nút Quay lại của Android ----------------------------------------------------
// Hộp thoại đang mở thì đóng hộp thoại; còn trang trước thì lùi; hết thì thu nhỏ app (không thoát giữa chừng).
if (laAppGoc) {
  import('@capacitor/app').then(({ App }) => App.addListener('backButton', ({ canGoBack }) => {
    const sk = new CustomEvent('kv:quay-lai', { cancelable: true })
    window.dispatchEvent(sk)
    if (sk.defaultPrevented) return
    if (canGoBack) window.history.back()
    else App.minimizeApp()
  })).catch(() => { /* iOS không có nút Quay lại; plugin thiếu thì giữ hành vi mặc định */ })
}
