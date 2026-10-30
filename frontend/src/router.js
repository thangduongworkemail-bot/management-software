import { createRouter, createWebHistory } from 'vue-router'
import { trangThai } from './store'

const TAT_CA = ['CHU', 'THO', 'QUAN_TRI']

export const MENU = [
  { path: '/', ten: 'Tổng quan', vaiTro: TAT_CA },
  { path: '/ban-hang', ten: 'Bán hàng', vaiTro: ['CHU', 'THO'] },
  { path: '/don-hang', ten: 'Đơn hàng', vaiTro: TAT_CA },
  { path: '/kho', ten: 'Kho & Xưởng', vaiTro: TAT_CA },
  { path: '/hang-hoa', ten: 'Hàng hóa & Giá', vaiTro: TAT_CA },
  { path: '/doi-soat', ten: 'Đối soát & Chốt ngày', vaiTro: ['CHU'] },
  { path: '/hoa-don', ten: 'HĐĐT & Công nợ', vaiTro: ['CHU', 'THO'] },
  { path: '/he-thong', ten: 'Nhân viên & Nhật ký', vaiTro: ['CHU', 'QUAN_TRI'] },
  { path: '/su-co', ten: 'Trung tâm sự cố', vaiTro: TAT_CA },
]

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
  if (!trangThai.token) return { path: '/dang-nhap', query: { tiep: to.fullPath } }
  if (to.meta.vaiTro && !to.meta.vaiTro.includes(trangThai.nguoi?.vai_tro)) return '/'
  return true
})
