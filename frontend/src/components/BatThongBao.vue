<script setup>
import { onMounted, ref } from 'vue'
import { batDay, day, guiThu, kiemTraDay, tatDay } from '../day'
import { laAppGoc, laIOS } from '../nen-tang'
import { bao, trangThai } from '../store'
import BieuTuong from './BieuTuong.vue'

const dangLam = ref(false)
const MO_TA = { CHU: 'yêu cầu duyệt giá của thợ, tiền về bị lệch, hóa đơn điện tử lỗi và hàng sắp hết',
  THO: 'kết quả Chủ duyệt giá', QUAN_TRI: 'sự cố hệ thống' }

onMounted(kiemTraDay)

async function lam(viec, thongBaoXong) {
  dangLam.value = true
  try {
    const ok = await viec()
    if (thongBaoXong && ok !== false) bao(thongBaoXong, 'thanh-cong')
  } catch (e) {
    bao(e.message || 'Không bật được thông báo', 'loi', 8)
  } finally {
    dangLam.value = false
  }
}

async function thu() {
  const kq = await guiThu()
  if (!kq.thanh_cong) throw new Error('Gửi thử không thành công, hãy tắt rồi bật lại thông báo')
}
</script>

<template>
  <section class="the space-y-3" aria-label="Thông báo trên máy này">
    <div class="flex items-start gap-3">
      <BieuTuong ten="chuong" class="w-6 h-6 text-do shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        <div class="font-extrabold">Thông báo trên máy này</div>
        <p class="text-sm">Nhận ngay {{ MO_TA[trangThai.nguoi?.vai_tro] || 'thông báo quan trọng' }}, kể cả khi đang tắt app.</p>
      </div>
      <span v-if="day.trangThai === 'da-bat'" class="huy-hieu-tot shrink-0">Đang bật</span>
    </div>

    <template v-if="day.trangThai === 'chua-bat'">
      <button class="nut-do w-full" :disabled="dangLam" @click="lam(batDay, 'Đã bật thông báo trên máy này')">Bật thông báo</button>
    </template>
    <template v-else-if="day.trangThai === 'da-bat'">
      <div class="grid grid-cols-2 gap-2">
        <button class="nut-vien" :disabled="dangLam" @click="lam(thu, 'Đã gửi thử, kiểm tra thanh thông báo')">Gửi thử</button>
        <button class="nut-vien" :disabled="dangLam" @click="lam(tatDay, 'Đã tắt thông báo trên máy này')">Tắt</button>
      </div>
    </template>
    <p v-else-if="day.trangThai === 'can-cai-app'" class="text-sm font-semibold bg-amber-50 border border-amber-300 rounded-lg p-3">
      Trên iPhone/iPad, cần <strong>cài app ra màn hình chính</strong> trước (Safari › Chia sẻ › Thêm vào MH chính,
      iOS 16.4 trở lên), rồi mở app từ biểu tượng đó để bật thông báo.
    </p>
    <p v-else-if="day.trangThai === 'bi-chan'" class="text-sm font-semibold bg-amber-50 border border-amber-300 rounded-lg p-3">
      Máy đang chặn thông báo của app. Vào <strong>Cài đặt › Thông báo</strong>{{ laIOS ? ' › Khanh Vân' : ' của trình duyệt' }}
      để cho phép, rồi mở lại app.
    </p>
    <p v-else-if="day.trangThai === 'khong-ho-tro'" class="text-sm text-slate-700">
      <template v-if="laAppGoc">Bản app cài từ file hiện báo ngay trên màn hình khi app đang mở. Muốn nhận cả khi tắt app,
        dùng bản cài từ trình duyệt (Chrome trên Android, Safari trên iPhone).</template>
      <template v-else>Trình duyệt này chưa hỗ trợ thông báo đẩy. Thông báo vẫn hiện trên màn hình khi app đang mở.</template>
    </p>
  </section>
</template>
