<script setup>
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MENU } from './router'
import { ketNoiRealtime, ngatRealtime } from './realtime'
import { dangXuat, trangThai } from './store'
import { batDauDongBo } from './sync'
import Toasts from './components/Toasts.vue'

const route = useRoute()
const router = useRouter()
const menu = computed(() => MENU.filter(m => m.vaiTro.includes(trangThai.nguoi?.vai_tro)))
const tranTrang = computed(() => route.meta.tranTrang || route.meta.congKhai)
const VAI_TRO = { CHU: 'Chủ cửa hàng', THO: 'Thợ / Nhân viên', QUAN_TRI: 'Quản trị viên' }

let daBatDau = false
// Chỉ điều hướng khi đăng xuất (token có -> mất); lúc mới tải trang router guard đã lo,
// vì ở thời điểm này route chưa được phân giải nên meta.congKhai chưa đúng.
watch(() => trangThai.token, (token, cu) => {
  if (token) {
    ketNoiRealtime()
    if (!daBatDau) { batDauDongBo(); daBatDau = true }
  } else {
    ngatRealtime()
    if (cu && !route.meta.congKhai) router.push('/dang-nhap')
  }
}, { immediate: true })

function thoat() {
  dangXuat()
}
</script>

<template>
  <Toasts />
  <router-view v-if="tranTrang" />
  <div v-else class="min-h-screen flex flex-col">
    <header class="khong-in bg-do text-white sticky top-0 z-30 shadow">
      <div class="max-w-[1400px] mx-auto px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <img src="/icon.svg" alt="" class="h-9 w-9 rounded-lg shrink-0" />
        <div class="font-extrabold leading-tight min-w-0 flex-1">
          NỘI THẤT KHANH VÂN
          <div class="text-xs font-semibold opacity-90 truncate">{{ trangThai.nguoi?.ho_ten }} • {{ VAI_TRO[trangThai.nguoi?.vai_tro] }}</div>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-2 text-xs font-bold">
          <span :class="trangThai.online ? 'bg-white/20' : 'bg-white text-do'" class="px-2 py-1 rounded">
            {{ trangThai.online ? '● Có mạng' : '● MẤT MẠNG — bán ngoại tuyến' }}
          </span>
          <span v-if="trangThai.donCho" class="px-2 py-1 rounded bg-white text-do">{{ trangThai.donCho }} đơn chờ đồng bộ</span>
          <button class="px-3 py-2 rounded bg-white/15 hover:bg-white/25" @click="thoat">Đăng xuất</button>
        </div>
      </div>
      <nav class="max-w-[1400px] mx-auto px-2 pb-2 flex gap-1 overflow-x-auto" aria-label="Chức năng">
        <router-link v-for="m in menu" :key="m.path" :to="m.path"
          class="px-3 py-2 rounded-lg text-sm font-bold whitespace-nowrap hover:bg-white/15"
          active-class="" exact-active-class="!bg-white !text-do">
          {{ m.ten }}
        </router-link>
      </nav>
    </header>
    <main class="flex-1 max-w-[1400px] w-full mx-auto p-4">
      <router-view />
    </main>
  </div>
</template>
