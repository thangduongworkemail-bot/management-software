<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { get } from '../api'
import { ngay, tien } from '../lib/format'

const route = useRoute()
const bg = ref(null)
const loi = ref('')

onMounted(async () => {
  try { bg.value = await get(`/public/bao-gia/${route.params.ma}`) } catch (e) { loi.value = e.message }
})

const inTrang = () => window.print()

async function chiaSe() {
  if (navigator.share) await navigator.share({ title: `Báo giá ${bg.value.ma}`, url: location.href }).catch(() => {})
  else await navigator.clipboard?.writeText(location.href)
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-4 sm:p-8 bg-white min-h-screen">
    <p v-if="loi" class="text-do font-bold text-lg">{{ loi }}</p>
    <article v-else-if="bg" class="space-y-5">
      <header class="flex items-start justify-between gap-4 border-b-2 border-do pb-4">
        <div>
          <div class="text-2xl font-extrabold text-do">{{ bg.cua_hang.ten }}</div>
          <div class="text-sm">{{ bg.cua_hang.dia_chi }}</div>
        </div>
        <img src="/icon.svg" alt="" class="h-16 w-16 rounded-xl" />
      </header>
      <div class="flex flex-wrap justify-between gap-2">
        <h1 class="text-xl font-extrabold">BÁO GIÁ {{ bg.ma }}</h1>
        <div class="text-sm text-right">Ngày lập: {{ ngay(bg.tao_luc) }}<br /><strong>Giữ giá đến: {{ ngay(bg.het_han_luc) }}</strong></div>
      </div>
      <div v-if="bg.ten_khach">Kính gửi: <strong>{{ bg.ten_khach }}</strong></div>
      <table class="bang">
        <thead><tr><th>Mặt hàng</th><th class="text-center">SL</th><th class="text-right">Đơn giá</th><th class="text-right">Thành tiền</th></tr></thead>
        <tbody>
          <tr v-for="(d, i) in bg.dong" :key="i">
            <td>{{ d.mo_ta }}<div v-if="d.dien_giai" class="text-xs text-slate-600">{{ d.dien_giai }}</div></td>
            <td class="text-center">{{ d.so_luong }}</td><td class="text-right whitespace-nowrap">{{ tien(d.don_gia) }}</td>
            <td class="text-right font-bold whitespace-nowrap">{{ tien(d.thanh_tien) }}</td>
          </tr>
        </tbody>
      </table>
      <div class="text-right text-2xl font-extrabold">TỔNG: <span class="text-do">{{ tien(bg.tong_tien) }}</span></div>
      <p class="text-sm">Người báo giá: {{ bg.nguoi_lap }}.</p>
      <div class="khong-in flex gap-2">
        <button class="nut-do" @click="inTrang">In / Lưu PDF</button>
        <button class="nut-vien" @click="chiaSe">Chia sẻ</button>
      </div>
    </article>
  </div>
</template>
