<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get } from '../api'
import { ngayGio, nhanTrangThai, tien } from '../lib/format'
import { chiaSe, laAppGoc } from '../nen-tang'
import { bao } from '../store'

const route = useRoute()
const router = useRouter()
const don = ref(null)
const inTrang = () => window.print()

onMounted(async () => {
  don.value = await get(`/don-hang/${route.params.id}`)
  // App gốc trên điện thoại không có lệnh in của trình duyệt: gửi phiếu cho khách qua Zalo/tin nhắn
  if (!laAppGoc) setTimeout(inTrang, 300)
})

function noiDungPhieu(d) {
  return [
    'NỘI THẤT GỖ KHANH VÂN — PHIẾU BÁN HÀNG',
    `Mã đơn: #${d.ma} • ${ngayGio(d.tao_luc)}`,
    `Khách: ${d.ten_khach || 'Khách lẻ'}${d.so_dien_thoai ? ` ${d.so_dien_thoai}` : ''}`,
    ...d.dong.map(x => `- ${x.so_luong} × ${x.mo_ta}: ${tien(x.thanh_tien)}`),
    ...(d.giam_tru ? [`Giảm trừ: −${tien(d.giam_tru)}`] : []),
    `TỔNG: ${tien(d.tong_tien - d.giam_tru)}`,
    `Đã thu: ${tien(d.da_thu)} • Còn lại: ${tien(d.con_phai_thu)}`,
    `Người bán: ${d.nguoi_lap}. Cảm ơn quý khách!`,
  ].join('\n')
}

async function guiPhieu() {
  try {
    const cach = await chiaSe({ tieuDe: `Phiếu bán hàng #${don.value.ma}`, noiDung: noiDungPhieu(don.value) })
    if (cach === 'sao-chep') bao('Đã sao chép nội dung phiếu', 'thanh-cong')
  } catch { /* người dùng đóng bảng chia sẻ */ }
}

const quayLai = () => (window.history.length > 1 ? router.back() : router.push('/don-hang'))
</script>

<template>
  <div v-if="don" class="max-w-[80mm] sm:max-w-md mx-auto p-4 bg-white text-sm space-y-2 dem-tren-an-toan">
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
    <div class="khong-in space-y-2 pt-2">
      <button v-if="laAppGoc" class="nut-do w-full" @click="guiPhieu">Gửi phiếu cho khách (Zalo, tin nhắn…)</button>
      <button v-else class="nut-vien w-full" @click="inTrang">In lại</button>
      <button v-if="laAppGoc" class="nut-vien w-full" @click="quayLai">Quay lại</button>
      <p v-if="laAppGoc" class="text-xs text-slate-600 text-center">Muốn in ra giấy: mở đơn này trên máy tính quầy rồi bấm In phiếu.</p>
    </div>
  </div>
</template>
