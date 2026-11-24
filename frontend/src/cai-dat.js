/**
 * Cài PWA lên màn hình chính.
 * Android/Chrome và Edge máy tính bắn sự kiện `beforeinstallprompt`: giữ lại để hiện nút "Cài app" của riêng mình.
 * iPhone/iPad không có sự kiện này, giao diện hiện hướng dẫn bấm Chia sẻ > Thêm vào MH chính.
 * Phải import sớm (main.js) để không lỡ sự kiện bắn ngay lúc tải trang.
 */
import { reactive } from 'vue'

export const caiDat = reactive({ suKien: null, vuaCai: false })

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  caiDat.suKien = e
})
window.addEventListener('appinstalled', () => {
  caiDat.suKien = null
  caiDat.vuaCai = true
})

/** Hiện hộp thoại cài của trình duyệt. Trả về true nếu người dùng đồng ý. */
export async function moHopThoaiCai() {
  const e = caiDat.suKien
  if (!e) return false
  e.prompt()
  const { outcome } = await e.userChoice
  caiDat.suKien = null
  return outcome === 'accepted'
}

const KHOA_AN = 'kv_an_goi_y_cai'
export function daAnGoiY() {
  try { return Date.now() - Number(localStorage.getItem(KHOA_AN) || 0) < 30 * 864e5 } catch { return false }
}
export function anGoiY() {
  try { localStorage.setItem(KHOA_AN, String(Date.now())) } catch { /* bỏ qua */ }
}
