<script setup>
import { onMounted, ref } from 'vue'
import { get } from '../api'
import { db } from '../db'
import { ngayGio } from '../lib/format'
import { trangThai } from '../store'
import { dayDonCho } from '../sync'

const tt = ref(null)
const mayChu = ref(true)
const danhMucLuc = ref(null)

async function tai() {
  try { tt.value = await get('/he-thong/trang-thai'); mayChu.value = true } catch { mayChu.value = false }
  danhMucLuc.value = (await db.meta.get('danh_muc'))?.thoi_diem
}
onMounted(tai)

function guiZalo() {
  const noiDung = encodeURIComponent(`Lỗi app Khanh Vân lúc ${new Date().toLocaleString('vi-VN')}: mạng ${trangThai.online ? 'có' : 'mất'}, máy chủ ${mayChu.value ? 'tốt' : 'không trả lời'}, ${trangThai.donCho} đơn chờ đồng bộ.`)
  window.open(`https://zalo.me/share?text=${noiDung}`, '_blank')
}
</script>

<template>
  <div class="max-w-xl mx-auto space-y-3 text-lg [&_.the.flex]:flex-wrap [&_.the.flex]:gap-x-3 [&_strong]:text-right">
    <h1 class="tieu-de">Trung tâm sự cố</h1>
    <div class="the flex justify-between"><span>Kết nối mạng:</span><strong :class="!trangThai.online && 'text-do'">{{ trangThai.online ? '● Tốt' : '! Mất mạng' }}</strong></div>
    <div class="the flex justify-between"><span>Máy chủ:</span><strong :class="!mayChu && 'text-do'">{{ mayChu ? '● Tốt' : '! Không trả lời' }}</strong></div>
    <template v-if="tt">
      <div v-for="m in tt.may_nhan_tien" :key="m.id" class="the flex justify-between">
        <span>Máy nhận tiền:</span>
        <strong :class="m.so_phut_chua_bao >= 15 && 'text-do'">{{ m.so_phut_chua_bao >= 15 ? `! Chưa báo ${m.so_phut_chua_bao} phút` : '● Đang hoạt động' }}</strong>
      </div>
      <div class="the flex justify-between"><span>Hóa đơn điện tử:</span><strong>{{ tt.hddt.cho_xuat }} chờ xuất<span v-if="tt.hddt.loi" class="text-do">, {{ tt.hddt.loi }} lỗi</span></strong></div>
      <div class="the flex justify-between"><span>Kiểm tra toàn vẹn:</span>
        <strong>{{ tt.kiem_tra_toan_ven_cuoi ? (tt.kiem_tra_toan_ven_cuoi.du_lieu_sau.toan_ven ? '● Tốt' : '! Có sai lệch') + ' • ' + ngayGio(tt.kiem_tra_toan_ven_cuoi.thoi_diem) : 'Chưa chạy' }}</strong></div>
    </template>
    <div class="the flex justify-between items-center gap-2"><span>Đơn bán lúc mất mạng chưa gửi:</span>
      <strong>{{ trangThai.donCho }} <button v-if="trangThai.donCho" class="nut-vien nut-nho ml-2" @click="dayDonCho">Gửi ngay</button></strong></div>
    <div class="the flex justify-between"><span>Bảng giá trong máy cập nhật:</span><strong>{{ ngayGio(danhMucLuc) }}</strong></div>
    <div class="the bg-than-nhat space-y-1">
      <div class="font-extrabold text-do">Cách xử lý (3 bước):</div>
      <div>1. Mở app Khanh Vân trên điện thoại của Chủ.</div>
      <div>2. Kiểm tra mạng và pin điện thoại.</div>
      <div>3. Chưa được? Cứ bán bình thường và bấm xác nhận tay.</div>
    </div>
    <button class="nut-vien w-full" @click="guiZalo">Gửi thông tin lỗi qua Zalo</button>
  </div>
</template>
