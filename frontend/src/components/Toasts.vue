<script setup>
import { trangThai } from '../store'

const MAU = {
  'thanh-cong': 'bg-emerald-700 text-white',
  'canh-bao': 'bg-amber-400 text-than',
  loi: 'bg-do text-white',
  'thong-tin': 'bg-than text-white',
}
</script>

<template>
  <div class="khong-in fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(420px,calc(100vw-2rem))]" aria-live="polite">
    <div v-for="t in trangThai.thongBao" :key="t.id" :class="MAU[t.loai]"
      class="rounded-xl px-4 py-3 font-bold shadow-lg">
      {{ t.noiDung }}
    </div>
  </div>
</template>
