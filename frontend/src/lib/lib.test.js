import { describe, expect, it } from 'vitest'
import { docKichThuoc, docMotKichThuoc } from './dimension'
import { tinhTheoBac, tinhTheoChieuDai, tinhTheoDienTich } from './pricing'

describe('docMotKichThuoc — khớp backend', () => {
  it.each([
    ['1m8', 1800], ['2m4', 2400], ['1m85', 1850], ['1,8m', 1800], ['180', 1800], ['180 phân', 1800],
    ['1800mm', 1800], ['2 mét', 2000], ['2.4', 2400], ['183,35cm', 1834],
  ])('%s -> %i', (vao, mm) => expect(docMotKichThuoc(vao)).toBe(mm))

  it('nhiều chiều và cảnh báo dung sai', () => {
    expect(docKichThuoc('1m8 x 2m').giaTriMm).toEqual([1800, 2000])
    expect(docKichThuoc('3m5').hopLe).toBe(false)
    expect(() => docKichThuoc('abc')).toThrow()
  })
})

describe('công thức giá — khớp backend', () => {
  it('tủ thờ 1.850.000 × 1,2 × 2,4 m', () => expect(tinhTheoChieuDai(1_850_000, 2400, 1200)).toBe(5_328_000))
  it('làm tròn nửa lên', () => expect(tinhTheoChieuDai(1_333_500, 1000)).toBe(1_334_000))
  it('diện tích + phụ phí', () => expect(tinhTheoDienTich(3_200_000, 1600, 800, 1500, 300_000)).toBe(6_444_000))
  it('bậc', () => expect(tinhTheoBac([{ toi_da_mm: 1600, gia: 7.8e6 }, { toi_da_mm: 1800, gia: 8.5e6 }], 1700)).toBe(8.5e6))
})
