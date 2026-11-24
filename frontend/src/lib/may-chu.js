/**
 * Địa chỉ máy chủ cửa hàng cho bản app Android/iOS.
 *
 * Trên web/PWA giao diện và API cùng một máy chủ nên mọi đường dẫn là tương đối ("/api/…").
 * Trong app gốc (Capacitor) giao diện nằm sẵn trong app, nên phải ghép địa chỉ máy chủ vào trước.
 */

const MANG_NOI_BO = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|[^.]+\.local\b|[^.:/]+(:\d+)?$)/i

/** "khanhvan.vn", "192.168.1.10:8000/", "https://x.trycloudflare.com/api" -> gốc URL chuẩn (không có "/" cuối). */
export function chuanHoaMayChu(nhap) {
  let s = String(nhap ?? '').trim()
  if (!s) return ''
  // Máy trong mạng nội bộ thường chưa có chứng chỉ HTTPS; còn lại mặc định HTTPS.
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = `${MANG_NOI_BO.test(s) ? 'http' : 'https'}://${s}`
  let u
  try {
    u = new URL(s)
  } catch {
    throw new Error('Địa chỉ máy chủ không hợp lệ')
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('Địa chỉ máy chủ phải bắt đầu bằng http:// hoặc https://')
  return u.origin
}

/** Ghép gốc máy chủ vào đường dẫn tuyệt đối trên máy chủ ("/api/…", "/files/…"); URL đầy đủ, data:, blob: giữ nguyên. */
export function noiUrl(goc, duongDan) {
  if (!duongDan || typeof duongDan !== 'string' || !duongDan.startsWith('/') || duongDan.startsWith('//')) return duongDan
  return `${goc || ''}${duongDan}`
}

/** URL WebSocket realtime: http -> ws, https -> wss. */
export function urlWebSocket(goc, token) {
  const u = new URL('/ws', goc)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  u.searchParams.set('token', token)
  return u.toString()
}
