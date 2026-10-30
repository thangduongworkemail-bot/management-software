// Bản JS của backend/app/domain/dimension.py — dùng khi bán ngoại tuyến. Giữ hai bản cùng quy tắc.
import { boDau } from './text'

const HE_SO = { mm: 1, cm: 10, phan: 10, m: 1000, met: 1000 }
const RE_M_KIEU_NOI = /^(\d+)\s*m\s*(\d+)$/
const RE_SO_DON_VI = /^(\d+(?:[.,]\d+)?)\s*(mm|cm|phan|met|m)?$/
const RE_TACH = /\s*(?:x|×|\*|nhan)\s*/

// Nhân số thập phân dạng chuỗi với hệ số rồi làm tròn nửa lên, không qua số thực
function sangMm(chuoiSo, heSo) {
  const [nguyen, thapPhan = ''] = chuoiSo.split('.')
  const mau = 10n ** BigInt(thapPhan.length)
  const tu = BigInt(nguyen + thapPhan) * BigInt(heSo)
  return Number((tu * 2n + mau) / (mau * 2n))
}

export function docMotKichThuoc(token) {
  const t = boDau(String(token)).toLowerCase().trim()
  if (!t) throw new Error('Kích thước trống')
  let m = t.match(RE_M_KIEU_NOI)
  if (m) return sangMm(`${m[1]}.${m[2]}`, 1000)
  m = t.match(RE_SO_DON_VI)
  if (!m) throw new Error(`Không hiểu kích thước '${String(token).trim()}'`)
  const so = m[1].replace(',', '.')
  if (m[2]) return sangMm(so, HE_SO[m[2]])
  const giaTri = Number(so)
  if (giaTri < 10) return sangMm(so, 1000)
  if (giaTri < 400) return sangMm(so, 10)
  return sangMm(so, 1)
}

export function docKichThuoc(text, minMm = 400, maxMm = 3000) {
  if (!text || !String(text).trim()) throw new Error('Chưa nhập kích thước')
  const phan = boDau(String(text)).toLowerCase().trim().split(RE_TACH).filter(p => p.trim())
  if (!phan.length) throw new Error(`Không hiểu kích thước '${text}'`)
  const giaTriMm = phan.map(docMotKichThuoc)
  const canhBao = []
  for (const mm of giaTriMm) {
    if (mm < minMm) canhBao.push(`${mm} mm nhỏ hơn mức tối thiểu ${minMm} mm`)
    else if (mm > maxMm) canhBao.push(`${mm} mm lớn hơn mức tối đa ${maxMm} mm`)
  }
  return { giaTriMm, canhBao, hopLe: canhBao.length === 0 }
}
