import { createRouter, createWebHistory } from 'vue-router'
import { canChonMayChu } from './nen-tang'
import { trangThai } from './store'

const TAT_CA = ['CHU', 'THO', 'QUAN_TRI']

// tenNgan, bieuTuong: thanh điều hướng dưới cùng trên điện thoại
export const MENU = [
  { path: '/', ten: 'Tổng quan', tenNgan: 'Tổng quan', bieuTuong: 'tong-quan', vaiTro: TAT_CA },
  { path: '/ban-hang', ten: 'Bán hàng', tenNgan: 'Bán hàng', bieuTuong: 'ban-hang', vaiTro: ['CHU', 'THO'] },
  { path: '/don-hang', ten: 'Đơn hàng', tenNgan: 'Đơn hàng', bieuTuong: 'don-hang', vaiTro: TAT_CA },
  { path: '/kho', ten: 'Kho & Xưởng', tenNgan: 'Kho', bieuTuong: 'kho', vaiTro: TAT_CA },
  { path: '/hang-hoa', ten: 'Hàng hóa & Giá', tenNgan: 'Hàng hóa', bieuTuong: 'hang-hoa', vaiTro: TAT_CA },
  { path: '/doi-soat', ten: 'Đối soát & Chốt ngày', tenNgan: 'Đối soát', bieuTuong: 'doi-soat', vaiTro: ['CHU'] },
  { path: '/hoa-don', ten: 'HĐĐT & Công nợ', tenNgan: 'HĐĐT', bieuTuong: 'hoa-don', vaiTro: ['CHU', 'THO'] },
  { path: '/he-thong', ten: 'Nhân viên & Nhật ký', tenNgan: 'Hệ thống', bieuTuong: 'he-thong', vaiTro: ['CHU', 'QUAN_TRI'] },
  { path: '/su-co', ten: 'Trung tâm sự cố', tenNgan: 'Sự cố', bieuTuong: 'su-co', vaiTro: TAT_CA },
]

/** 4 mục hay dùng nhất của từng vai trò hiện ở thanh dưới; các mục còn lại nằm trong nút "Thêm". */
const UU_TIEN_DUOI = ['/ban-hang', '/', '/don-hang', '/kho', '/hang-hoa', '/he-thong', '/su-co']
export function chiaMenuDienThoai(menu) {
  const chinh = UU_TIEN_DUOI.filter(p => menu.some(m => m.path === p)).slice(0, 4)
  return {
    chinh: menu.filter(m => chinh.includes(m.path)),
    phu: menu.filter(m => !chinh.includes(m.path)),
  }
}

const view = {
  '/': () => import('./views/TongQuan.vue'),
  '/ban-hang': () => import('./views/BanHang.vue'),
  '/don-hang': () => import('./views/DonHang.vue'),
  '/kho': () => import('./views/Kho.vue'),
  '/hang-hoa': () => import('./views/HangHoa.vue'),
  '/doi-soat': () => import('./views/DoiSoat.vue'),
  '/hoa-don': () => import('./views/HoaDon.vue'),
  '/he-thong': () => import('./views/HeThong.vue'),
  '/su-co': () => import('./views/SuCo.vue'),
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/dang-nhap', component: () => import('./views/DangNhap.vue'), meta: { congKhai: true } },
    { path: '/bao-gia/:ma', component: () => import('./views/BaoGiaCongKhai.vue'), meta: { congKhai: true, tranTrang: true } },
    { path: '/phieu/:id', component: () => import('./views/PhieuIn.vue'), meta: { tranTrang: true } },
    ...MENU.map(m => ({ path: m.path, component: view[m.path], meta: { vaiTro: m.vaiTro } })),
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (to.meta.congKhai) return true
  // App Android/iOS mở lần đầu: phải chọn máy chủ cửa hàng trước (màn đăng nhập có ô nhập)
  if (canChonMayChu()) return { path: '/dang-nhap', query: { tiep: to.fullPath } }
  if (!trangThai.token) return { path: '/dang-nhap', query: { tiep: to.fullPath } }
  if (to.meta.vaiTro && !to.meta.vaiTro.includes(trangThai.nguoi?.vai_tro)) return '/'
  return true
})
