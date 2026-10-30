import { dangXuat, trangThai } from './store'

export class LoiApi extends Error {
  constructor(status, body) {
    super(body?.thong_bao || `Lỗi ${status}`)
    this.status = status
    this.ma = body?.loi
    this.chiTiet = body?.chi_tiet
  }
  get matKetNoi() { return this.status === 0 }
}

export async function api(duongDan, { method = 'GET', body, headers = {}, tho = false } = {}) {
  const h = { ...headers }
  if (trangThai.token) h.Authorization = `Bearer ${trangThai.token}`
  let duLieu = body
  if (body !== undefined && !(body instanceof Blob)) {
    h['Content-Type'] = 'application/json'
    duLieu = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`/api${duongDan}`, { method, headers: h, body: duLieu })
  } catch {
    throw new LoiApi(0, { loi: 'MAT_KET_NOI', thong_bao: 'Không kết nối được máy chủ' })
  }
  if (res.status === 401 && trangThai.token) dangXuat()
  if (!res.ok) {
    let data = {}
    try { data = await res.json() } catch { /* không phải JSON */ }
    throw new LoiApi(res.status, data)
  }
  if (tho) return res
  return res.status === 204 ? null : res.json()
}

export const get = (p) => api(p)
export const post = (p, body = {}, headers) => api(p, { method: 'POST', body, headers })
export const put = (p, body = {}) => api(p, { method: 'PUT', body })
export const patch = (p, body = {}) => api(p, { method: 'PATCH', body })

/** Xin URL có chữ ký rồi PUT file thẳng lên kho lưu trữ (cục bộ hoặc S3). */
export async function taiFileLen(file, mucDich) {
  const url = await post('/files/presign', { ten_file: file.name, muc_dich: mucDich })
  const res = await fetch(url.upload_url, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } })
  if (!res.ok) throw new LoiApi(res.status, { thong_bao: 'Tải file lên thất bại' })
  return url.file_url
}

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
