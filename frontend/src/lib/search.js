// Tìm kiếm ngoại tuyến trên danh mục trong IndexedDB: không dấu, từ đồng nghĩa, token kích thước.
import { db } from '../db'
import { docMotKichThuoc } from './dimension'
import { chuanHoa } from './text'

const RE_KICH_THUOC = /^(\d+m\d+|\d+(?:[.,]\d+)?(?:m|mm|cm))$/

function tokenKichThuoc(mm) {
  if (!mm) return ''
  if (mm % 1000 === 0) return `${mm} ${mm / 1000}m`
  if (mm % 100 === 0) return `${mm} ${Math.floor(mm / 1000)}m${(mm % 1000) / 100}`
  return String(mm)
}

export function chuoiTimKiem(h) {
  const thuocTinh = Object.values(h.thuoc_tinh || {}).filter(v => typeof v === 'string')
  return chuanHoa([h.ma, h.ten, h.mau_hang, h.loai_hang, h.loai_go, h.mau_sac, h.kieu === 'BO' ? 'bo' : '',
    h.hoan_thien, h.kieu_dang, h.vat_lieu_phu, ...thuocTinh,
    tokenKichThuoc(h.dai_mm), tokenKichThuoc(h.rong_mm), tokenKichThuoc(h.cao_mm)].filter(Boolean).join(' '))
}

export async function timNgoaiTuyen(q, gioiHan = 20) {
  let cn = chuanHoa(q)
  if (!cn) return []
  for (const { tu_khoa_cn: tk, tu_chuan_cn: tc } of await db.dong_nghia.toArray()) {
    if (!cn.includes(tc)) cn = cn.replace(new RegExp(`(?<![\\w])${tk.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w])`, 'g'), tc)
  }
  const tokens = cn.split(' ').map(t => {
    if (RE_KICH_THUOC.test(t)) {
      try { return String(docMotKichThuoc(t)) } catch { return t }
    }
    return t
  })
  const tatCa = await db.hang_hoa.toArray()
  return tatCa
    .filter(h => h.dang_ban !== false)
    .map(h => ({ h, s: chuoiTimKiem(h) }))
    .filter(({ s }) => tokens.every(t => s.includes(t)))
    .slice(0, gioiHan)
    .map(({ h }) => h)
}
