// Bản JS của backend/app/domain/pricing.py (số học BigInt, làm tròn đến nghìn đồng, nửa lên)

function lamTronNghin(tu, mau) {
  // round(tu / mau / 1000) * 1000 với tu, mau > 0
  return Number(((tu * 2n + mau * 1000n) / (mau * 2000n)) * 1000n)
}

export function tinhTheoChieuDai(donGiaM, daiMm, heSo = 1000, phuPhi = 0) {
  const tu = BigInt(donGiaM) * BigInt(daiMm) * BigInt(heSo) + BigInt(phuPhi) * 1_000_000n
  return lamTronNghin(tu, 1_000_000n)
}

export function tinhTheoDienTich(donGiaM2, daiMm, rongMm, heSo = 1000, phuPhi = 0) {
  const tu = BigInt(donGiaM2) * BigInt(daiMm) * BigInt(rongMm) * BigInt(heSo) + BigInt(phuPhi) * 1_000_000_000n
  return lamTronNghin(tu, 1_000_000_000n)
}

export function tinhTheoBac(bacGia, kichThuocMm) {
  const bac = [...bacGia].sort((a, b) => a.toi_da_mm - b.toi_da_mm).find(b => kichThuocMm <= b.toi_da_mm)
  if (!bac) throw new Error(`Kích thước ${kichThuocMm} mm vượt bậc lớn nhất`)
  return bac.gia
}

export function tinhGia(ct, kichThuocMm) {
  if (ct.kieu === 'THEO_CHIEU_DAI') return tinhTheoChieuDai(ct.don_gia, kichThuocMm[0], ct.he_so_phan_nghin, ct.phu_phi)
  if (ct.kieu === 'THEO_DIEN_TICH') {
    if (kichThuocMm.length < 2) throw new Error('Tính theo diện tích cần nhập Dài × Rộng')
    return tinhTheoDienTich(ct.don_gia, kichThuocMm[0], kichThuocMm[1], ct.he_so_phan_nghin, ct.phu_phi)
  }
  if (ct.kieu === 'THEO_BAC') return tinhTheoBac(ct.bac_gia, kichThuocMm[0])
  throw new Error(`Kiểu công thức không hợp lệ: ${ct.kieu}`)
}
