<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { goKhiDangXuat, dongBoDangKy } from './day'
import { laAppGoc, mayChu } from './nen-tang'
import { chiaMenuDienThoai, MENU } from './router'
import { ketNoiRealtime, ngatRealtime } from './realtime'
import { dangXuat, trangThai } from './store'
import { batDauDongBo } from './sync'
import BatThongBao from './components/BatThongBao.vue'
import BieuTuong from './components/BieuTuong.vue'
import CaiDatApp from './components/CaiDatApp.vue'
import HopThoai from './components/HopThoai.vue'
import Toasts from './components/Toasts.vue'

const route = useRoute()
const router = useRouter()
const menu = computed(() => MENU.filter(m => m.vaiTro.includes(trangThai.nguoi?.vai_tro)))
const menuDienThoai = computed(() => chiaMenuDienThoai(menu.value))
const tranTrang = computed(() => route.meta.tranTrang || route.meta.congKhai)
const VAI_TRO = { CHU: 'Chủ cửa hàng', THO: 'Thợ / Nhân viên', QUAN_TRI: 'Quản trị viên' }
const moThem = ref(false)
const dangOMucPhu = computed(() => menuDienThoai.value.phu.some(m => m.path === route.path))

let daBatDau = false
let sauKhiThoat = '/dang-nhap'
// Chỉ điều hướng khi đăng xuất (token có -> mất); lúc mới tải trang router guard đã lo,
// vì ở thời điểm này route chưa được phân giải nên meta.congKhai chưa đúng.
watch(() => trangThai.token, (token, cu) => {
  if (token) {
    ketNoiRealtime()
    dongBoDangKy()
    if (!daBatDau) { batDauDongBo(); daBatDau = true }
  } else {
    ngatRealtime()
    if (cu && !route.meta.congKhai) router.push(sauKhiThoat)
    sauKhiThoat = '/dang-nhap'
  }
}, { immediate: true })

watch(() => route.fullPath, () => { moThem.value = false })

async function thoat(den = '/dang-nhap') {
  moThem.value = false
  sauKhiThoat = den
  await goKhiDangXuat()
  dangXuat()
}
</script>

<template>
  <Toasts />
  <div v-if="tranTrang"><router-view /></div>
  <div v-else class="min-h-screen flex flex-col">
    <header class="khong-in bg-do text-white sticky top-0 z-30 shadow dem-tren-an-toan">
      <div class="max-w-[1400px] mx-auto px-3 sm:px-4 py-2 flex items-center gap-x-3 gap-y-2">
        <img src="/icon.svg" alt="" class="h-9 w-9 rounded-lg shrink-0" />
        <div class="font-extrabold leading-tight min-w-0 flex-1">
          <span class="hidden sm:inline">NỘI THẤT </span>KHANH VÂN
          <div class="text-xs font-semibold opacity-90 truncate">{{ trangThai.nguoi?.ho_ten }} • {{ VAI_TRO[trangThai.nguoi?.vai_tro] }}</div>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-2 text-xs font-bold">
          <span :class="trangThai.online ? 'bg-white/20' : 'bg-white text-do'" class="px-2 py-1 rounded" role="status">
            <template v-if="trangThai.online">● Có mạng</template>
            <template v-else>● MẤT MẠNG<span class="hidden sm:inline"> — bán ngoại tuyến</span></template>
          </span>
          <span v-if="trangThai.donCho" class="px-2 py-1 rounded bg-white text-do">{{ trangThai.donCho }} đơn chờ<span class="hidden sm:inline"> đồng bộ</span></span>
          <button class="hidden md:inline-flex px-3 py-2 rounded bg-white/15 hover:bg-white/25" @click="thoat()">Đăng xuất</button>
        </div>
      </div>
      <nav class="hidden md:flex max-w-[1400px] mx-auto px-2 pb-2 gap-1 overflow-x-auto" aria-label="Chức năng">
        <router-link v-for="m in menu" :key="m.path" :to="m.path"
          class="px-3 py-2 rounded-lg text-sm font-bold whitespace-nowrap hover:bg-white/15"
          active-class="" exact-active-class="!bg-white !text-do">
          {{ m.ten }}
        </router-link>
      </nav>
    </header>

    <main class="flex-1 max-w-[1400px] w-full mx-auto p-3 sm:p-4 chua-cho-thanh-duoi">
      <CaiDatApp v-if="['/', '/ban-hang'].includes(route.path)" gon class="md:hidden" />
      <router-view />
    </main>

    <!-- Điện thoại: thanh điều hướng dưới cùng, ngón cái với tới được -->
    <nav class="khong-in md:hidden fixed bottom-0 inset-x-0 z-30 bg-white border-t border-slate-300 dem-duoi-an-toan"
      aria-label="Chức năng chính">
      <div class="grid grid-cols-5">
        <router-link v-for="m in menuDienThoai.chinh" :key="m.path" :to="m.path"
          class="o-thanh-duoi" active-class="" exact-active-class="o-thanh-duoi-chon">
          <BieuTuong :ten="m.bieuTuong" class="w-6 h-6" />
          <span>{{ m.tenNgan }}</span>
        </router-link>
        <button type="button" class="o-thanh-duoi" :class="{ 'o-thanh-duoi-chon': dangOMucPhu || moThem }"
          :aria-expanded="moThem" @click="moThem = true">
          <BieuTuong ten="them" class="w-6 h-6" />
          <span>Thêm</span>
        </button>
      </div>
    </nav>

    <HopThoai :mo="moThem" tieu-de="Chức năng khác" @dong="moThem = false">
      <div class="grid grid-cols-2 gap-2">
        <router-link v-for="m in menuDienThoai.phu" :key="m.path" :to="m.path"
          class="nut-vien !justify-start !px-3 text-left" exact-active-class="!border-do !text-do">
          <BieuTuong :ten="m.bieuTuong" class="w-5 h-5 shrink-0" />{{ m.ten }}
        </router-link>
      </div>
      <BatThongBao />
      <CaiDatApp />
      <div v-if="laAppGoc" class="the flex items-center gap-3 text-sm">
        <BieuTuong ten="may-chu" class="w-6 h-6 shrink-0" />
        <span class="flex-1 min-w-0 truncate">Máy chủ: <strong>{{ mayChu.goc }}</strong></span>
        <button type="button" class="font-bold underline min-h-[40px] px-1" @click="thoat('/dang-nhap?doi_may_chu=1')">Đổi</button>
      </div>
      <button class="nut-vien w-full" @click="thoat()"><BieuTuong ten="thoat" class="w-5 h-5" />Đăng xuất</button>
    </HopThoai>
  </div>
</template>
