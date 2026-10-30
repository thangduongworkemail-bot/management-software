import Dexie from 'dexie'

/** Kho cục bộ IndexedDB: danh mục + bảng giá hiện hành để bán khi mất mạng, và hàng đợi đơn ngoại tuyến. */
export const db = new Dexie('khanhvan')

db.version(1).stores({
  hang_hoa: 'khoa, ma, kieu',
  cong_thuc: 'bien_the_id',
  dong_nghia: 'tu_khoa_cn',
  don_cho: 'idempotency_key, tao_luc',
  meta: 'khoa',
})
