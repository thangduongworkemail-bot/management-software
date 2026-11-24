<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { post } from '../api'
import { laAppGoc, mayChu } from '../nen-tang'
import { dangNhapXong } from '../store'
import CaiDatApp from '../components/CaiDatApp.vue'
import ChonMayChu from '../components/ChonMayChu.vue'

const route = useRoute()
const router = useRouter()
const ten = ref('')
const matKhau = ref('')
const loi = ref('')
const dangGui = ref(false)

const NHANH = [
  { ten: 'covan', nhan: 'Cô Vân (Chủ)', mk: 'KhanhVan@2026', mo_ta: 'Toàn quyền: giá vốn, duyệt giá sàn, xác nhận tiền, chốt sổ.' },
  { ten: 'anhnam', nhan: 'Anh Nam (Thợ)', mk: 'AnhNam@2026', mo_ta: 'Tra giá niêm yết, lập đơn, phiếu nhập. Không xem giá vốn.' },
  { ten: 'admin', nhan: 'Quản trị viên', mk: 'Admin@2026', mo_ta: 'Tài khoản, thiết bị, nhật ký hệ thống.' },
]
const chon = ref(null)
// App Android/iOS: chưa có máy chủ, hoặc người dùng bấm "Đổi máy chủ"
const chonMayChu = ref(laAppGoc && (!mayChu.goc || route.query.doi_may_chu === '1'))

function chonNhanh(t) {
  chon.value = t
  ten.value = t.ten
  matKhau.value = t.mk
}

async function dangNhap() {
  loi.value = ''
  dangGui.value = true
  try {
    const kq = await post('/auth/dang-nhap', { ten_dang_nhap: ten.value, mat_khau: matKhau.value })
    dangNhapXong(kq.token, kq.nguoi_dung)
    const tiep = typeof route.query.tiep === 'string' && route.query.tiep.startsWith('/') ? route.query.tiep : null
    router.replace(tiep || (kq.nguoi_dung.vai_tro === 'THO' ? '/ban-hang' : '/'))
  } catch (e) {
    loi.value = e.message
  } finally {
    dangGui.value = false
  }
}
</script>

<template>
  <div class="min-h-screen grid grid-rows-[auto_1fr] lg:grid-rows-1 lg:grid-cols-2">
    <section class="bg-do text-white px-5 pb-5 sm:p-8 lg:p-14 flex flex-col justify-center gap-4 sm:gap-6 dem-tren-an-toan">
      <div class="flex items-center gap-4 pt-4 sm:pt-0 pb-4 sm:pb-6 border-b border-white/25">
        <img src="/hust-logo.png" alt="" class="h-12 sm:h-16 lg:h-20 w-auto shrink-0 rounded-[3px] ring-2 ring-white/90 shadow-lg shadow-black/20" />
        <div class="leading-tight">
          <div class="text-base sm:text-xl font-extrabold sm:tracking-wide">ĐẠI HỌC BÁCH KHOA HÀ NỘI</div>
          <div class="text-[10px] sm:text-xs font-semibold tracking-wide text-white/80 mt-0.5">HANOI UNIVERSITY OF SCIENCE AND TECHNOLOGY</div>
        </div>
      </div>
      <h1 class="text-2xl sm:text-3xl lg:text-4xl font-extrabold leading-tight">Hệ thống Bán hàng &amp; Quản lý Kho<br />Nội thất gỗ Khanh Vân</h1>
      <ul class="hidden sm:block space-y-2 text-lg font-medium">
        <li>• Tra giá dưới 1 giây, tính giá hàng đặt kích thước riêng.</li>
        <li>• Sinh mã VietQR tại quầy, tiền về tự xác nhận.</li>
        <li>• Hóa đơn điện tử tách riêng, không làm kẹt việc bán.</li>
        <li>• Mất mạng vẫn bán được, có mạng lại tự đồng bộ.</li>
      </ul>
    </section>
    <section v-if="chonMayChu" class="p-5 sm:p-6 lg:p-14 flex flex-col justify-start lg:justify-center gap-5 bg-white dem-duoi-an-toan">
      <h2 class="tieu-de">Kết nối máy chủ cửa hàng</h2>
      <p class="text-sm">Lần đầu mở app trên máy này: nhập địa chỉ máy chủ mà máy tính quầy đang dùng. Chỉ cần làm một lần.</p>
      <ChonMayChu @xong="chonMayChu = false" />
    </section>
    <section v-else class="p-5 sm:p-6 lg:p-14 flex flex-col justify-start lg:justify-center gap-5 bg-white dem-duoi-an-toan">
      <h2 class="tieu-de">Chọn nhanh tài khoản demo</h2>
      <div class="grid sm:grid-cols-3 gap-3">
        <button v-for="t in NHANH" :key="t.ten" type="button" :aria-pressed="chon?.ten === t.ten"
          :class="chon?.ten === t.ten ? 'nut-do' : 'nut-vien'" @click="chonNhanh(t)">{{ t.nhan }}</button>
      </div>
      <p v-if="chon" class="bg-than-nhat rounded-lg p-3 text-sm font-semibold">{{ chon.mo_ta }}</p>
      <form class="space-y-4" @submit.prevent="dangNhap">
        <div>
          <label class="nhan" for="ten">Tài khoản</label>
          <input id="ten" v-model="ten" class="o-nhap" autocomplete="username" required />
        </div>
        <div>
          <label class="nhan" for="mk">Mật khẩu</label>
          <input id="mk" v-model="matKhau" type="password" class="o-nhap" autocomplete="current-password" required />
        </div>
        <p v-if="loi" class="text-do font-bold" role="alert">{{ loi }}</p>
        <button class="nut-do w-full text-lg" :disabled="dangGui">{{ dangGui ? 'Đang đăng nhập…' : 'ĐĂNG NHẬP' }}</button>
      </form>
      <p v-if="laAppGoc" class="text-sm text-slate-600">
        Máy chủ: <strong>{{ mayChu.goc }}</strong> ·
        <button type="button" class="font-bold underline" @click="chonMayChu = true">Đổi</button>
      </p>
      <CaiDatApp gon class="lg:hidden" />
    </section>
  </div>
</template>
