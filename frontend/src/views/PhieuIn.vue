<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { get } from '../api'
import { ngayGio, nhanTrangThai, tien } from '../lib/format'

const route = useRoute()
const don = ref(null)
const inTrang = () => window.print()

onMounted(async () => {
  don.value = await get(`/don-hang/${route.params.id}`)
  setTimeout(inTrang, 300)
})
</script>

<template>
  <div v-if="don" class="max-w-[80mm] sm:max-w-md mx-auto p-4 bg-white text-sm space-y-2">
    <div class="text-center border-b border-dashed border-slate-400 pb-2">
      <div class="font-extrabold">CỬA HÀNG NỘI THẤT GỖ KHANH VÂN — THÁI NGUYÊN</div>
      <div class="font-extrabold text-do">PHIẾU BÁN HÀNG NỘI BỘ</div>
      <div class="text-xs">(Không phải hóa đơn điện tử)</div>
    </div>
    <div class="flex justify-between"><span>Mã đơn: <strong>#{{ don.ma }}</strong></span><span>{{ ngayGio(don.tao_luc) }}</span></div>
    <div>Khách: <strong>{{ don.ten_khach || 'Khách lẻ' }}</strong> {{ don.so_dien_thoai || '' }}</div>
    <div class="border-y border-dashed border-slate-400 py-2 space-y-1">
      <div v-for="d in don.dong" :key="d.id" class="flex justify-between gap-2">
        <span>{{ d.so_luong }} × {{ d.mo_ta }}</span><span class="font-bold whitespace-nowrap">{{ tien(d.thanh_tien) }}</span>
      </div>
    </div>
    <div v-if="don.giam_tru" class="flex justify-between"><span>Giảm trừ</span><span>−{{ tien(don.giam_tru) }}</span></div>
    <div class="flex justify-between font-extrabold text-base"><span>TỔNG</span><span>{{ tien(don.tong_tien - don.giam_tru) }}</span></div>
    <div class="flex justify-between"><span>Đã thu</span><span>{{ tien(don.da_thu) }}</span></div>
    <div class="flex justify-between font-bold"><span>Còn lại</span><span>{{ tien(don.con_phai_thu) }}</span></div>
    <div>Trạng thái: <strong>{{ nhanTrangThai(don.trang_thai) }}</strong>{{ don.hoa_don?.trang_thai === 'CHO_XUAT' ? ' (Chờ xuất HĐĐT)' : '' }}</div>
    <div class="text-center text-xs pt-2">Người bán: {{ don.nguoi_lap }} • Cảm ơn quý khách!</div>
    <button class="khong-in nut-vien w-full" @click="inTrang">In lại</button>
  </div>
</template>
