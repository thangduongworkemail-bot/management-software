import { api, uuid } from './api'
import { db } from './db'
import { bao, trangThai } from './store'

export async function taiDanhMuc() {
  const d = await api('/sync/danh-muc')
  await db.transaction('rw', db.hang_hoa, db.cong_thuc, db.dong_nghia, db.meta, async () => {
    await Promise.all([db.hang_hoa.clear(), db.cong_thuc.clear(), db.dong_nghia.clear()])
    await db.hang_hoa.bulkPut(d.hang_hoa.map(h => ({ ...h, khoa: `${h.kieu}-${h.id}` })))
    await db.cong_thuc.bulkPut(d.cong_thuc)
    await db.dong_nghia.bulkPut(d.tu_dong_nghia)
    await db.meta.put({ khoa: 'danh_muc', thoi_diem: d.thoi_diem })
  })
  return d
}

export async function demDonCho() {
  trangThai.donCho = await db.don_cho.count()
  return trangThai.donCho
}

/** Lưu đơn lập lúc mất mạng; khóa idempotency giúp gửi lại bao nhiêu lần cũng chỉ tạo một đơn. */
export async function luuDonNgoaiTuyen(don) {
  const ban_ghi = { ...don, idempotency_key: uuid(), tao_luc: new Date().toISOString() }
  await db.don_cho.put(ban_ghi)
  await demDonCho()
  return ban_ghi
}

let dangDay = false
export async function dayDonCho() {
  if (dangDay || !trangThai.token) return
  const ds = await db.don_cho.toArray()
  if (!ds.length) return
  dangDay = true
  try {
    const { ket_qua } = await api('/sync/don-hang', {
      method: 'POST',
      body: { don: ds.map(({ loi, ...d }) => d) },
    })
    let ok = 0
    for (const r of ket_qua) {
      if (r.ok) {
        await db.don_cho.delete(r.idempotency_key)
        ok++
        if (r.trang_thai_giao === 'XUNG_DOT_TON') bao(`Đơn #${r.ma} thiếu hàng khi đồng bộ — Chủ cần xử lý`, 'canh-bao', 10)
      } else {
        await db.don_cho.update(r.idempotency_key, { loi: r.thong_bao || r.loi })
      }
    }
    if (ok) bao(`Đã đồng bộ ${ok} đơn ngoại tuyến lên máy chủ`, 'thanh-cong')
  } catch (e) {
    if (!e.matKetNoi) bao(`Đồng bộ đơn lỗi: ${e.message}`, 'loi')
  } finally {
    dangDay = false
    await demDonCho()
  }
}

export function batDauDongBo() {
  const chay = async () => {
    if (!trangThai.token || !navigator.onLine) return
    try {
      await dayDonCho()
      await taiDanhMuc()
    } catch { /* thử lại chu kỳ sau */ }
  }
  window.addEventListener('online', chay)
  setInterval(chay, 60_000)
  demDonCho()
  chay()
}
