<script setup>
import { onMounted, ref } from 'vue'
import { get, post } from '../api'
import { ngayGio } from '../lib/format'
import { bao, trangThai } from '../store'

const taiKhoan = ref([])
const thietBi = ref([])
const nhatKy = ref([])
const kiemTra = ref(null)
const maGhep = ref(null)

async function tai() {
  ;[taiKhoan.value, thietBi.value, nhatKy.value] = await Promise.all([get('/tai-khoan'), get('/thiet-bi'), get('/nhat-ky?gioi_han=80')])
}
onMounted(tai)

const tkMoi = ref({ ten_dang_nhap: '', ho_ten: '', vai_tro: 'THO', mat_khau: '' })
async function taoTaiKhoan() {
  try {
    await post('/tai-khoan', tkMoi.value)
    bao('Đã tạo tài khoản', 'thanh-cong')
    tkMoi.value = { ten_dang_nhap: '', ho_ten: '', vai_tro: 'THO', mat_khau: '' }
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

async function lam(duongDan, body, thongBao) {
  try { const kq = await post(duongDan, body); bao(thongBao, 'thanh-cong'); tai(); return kq } catch (e) { bao(e.message, 'loi') }
}

async function datLaiMatKhau(tk) {
  const mk = prompt(`Mật khẩu mới cho ${tk.ho_ten} (ít nhất 8 ký tự):`)
  if (mk) lam(`/tai-khoan/${tk.id}/dat-lai-mat-khau`, { mat_khau_moi: mk }, 'Đã đặt lại mật khẩu')
}

const tbMoi = ref({ ten: 'Điện thoại của Chủ (Máy nhận tiền)', loai: 'MAY_NHAN_TIEN' })
async function taoMaGhep() {
  maGhep.value = await lam('/thiet-bi/ma-ghep', tbMoi.value, 'Đã tạo mã ghép nối (hết hạn sau 10 phút)')
}

async function kiemTraChuoi() {
  kiemTra.value = await get('/nhat-ky/kiem-tra')
}
const TEN_LOAI = { MAY_QUAY: 'Máy tính quầy', DIEN_THOAI: 'Điện thoại', MAY_NHAN_TIEN: 'Máy nhận tiền' }
</script>

<template>
  <div class="grid lg:grid-cols-12 gap-4">
    <section class="lg:col-span-7 space-y-4">
      <div class="the space-y-3">
        <div class="font-extrabold">TÀI KHOẢN & PHÂN QUYỀN</div>
        <table class="bang">
          <thead><tr><th>Tài khoản</th><th>Họ tên</th><th>Vai trò</th><th></th></tr></thead>
          <tbody>
            <tr v-for="tk in taiKhoan" :key="tk.id">
              <td class="font-mono">{{ tk.ten_dang_nhap }}</td><td>{{ tk.ho_ten }}</td>
              <td>{{ tk.vai_tro }} <span v-if="!tk.kich_hoat" class="huy-hieu-loi">Đã khóa</span></td>
              <td class="text-right whitespace-nowrap space-x-2">
                <button class="underline text-sm" @click="datLaiMatKhau(tk)">Đặt lại MK</button>
                <button v-if="tk.id !== trangThai.nguoi.id" class="underline text-sm text-do"
                  @click="lam(`/tai-khoan/${tk.id}/kich-hoat?bat=${!tk.kich_hoat}`, {}, tk.kich_hoat ? 'Đã khóa' : 'Đã mở khóa')">
                  {{ tk.kich_hoat ? 'Khóa' : 'Mở khóa' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        <form class="grid sm:grid-cols-4 gap-2 items-end" @submit.prevent="taoTaiKhoan">
          <label><span class="nhan">Tên đăng nhập</span><input v-model="tkMoi.ten_dang_nhap" class="o-nhap" pattern="[a-z0-9._\-]+" required /></label>
          <label><span class="nhan">Họ tên</span><input v-model="tkMoi.ho_ten" class="o-nhap" required /></label>
          <label><span class="nhan">Mật khẩu</span><input v-model="tkMoi.mat_khau" type="password" minlength="8" class="o-nhap" required /></label>
          <button class="nut-do">+ Thêm thợ phụ</button>
        </form>
        <div class="text-xs bg-than-nhat rounded p-3">
          Thợ / Nhân viên: tra giá niêm yết, lập báo giá & đơn bán, phiếu nhập. Bán dưới giá sàn → gửi Chủ duyệt.
          Không xem giá vốn, giá sàn, lợi nhuận, công nợ xưởng, nhật ký.
        </div>
      </div>

      <div class="the space-y-3">
        <div class="flex flex-wrap justify-between gap-2 items-center">
          <div class="font-extrabold">NHẬT KÝ THAO TÁC (CHỈ GHI THÊM, CHUỖI BĂM SHA-256)</div>
          <button class="nut-vien nut-nho" @click="kiemTraChuoi">Kiểm tra toàn vẹn chuỗi</button>
        </div>
        <p v-if="kiemTra" :class="kiemTra.toan_ven ? 'huy-hieu-tot' : 'huy-hieu-loi'" class="!text-sm">
          {{ kiemTra.toan_ven ? `Toàn vẹn 100% — ${kiemTra.so_dong} dòng` : `PHÁT HIỆN ${kiemTra.loi.length} dòng bị sửa: ${kiemTra.loi.map(l => '#' + l.nhat_ky_id).join(', ')}` }}
        </p>
        <div class="overflow-x-auto max-h-[480px]">
          <table class="bang">
            <thead><tr><th>Thời gian</th><th>Người & thiết bị</th><th>Hành động</th><th>Trước → Sau</th><th>Mã băm</th></tr></thead>
            <tbody>
              <tr v-for="n in nhatKy" :key="n.id">
                <td class="text-xs whitespace-nowrap">{{ ngayGio(n.thoi_diem) }}</td>
                <td class="text-xs">{{ n.ten_nguoi_thuc_hien }}<div v-if="n.ten_thiet_bi">{{ n.ten_thiet_bi }}</div></td>
                <td><span class="huy-hieu-xam">{{ n.hanh_dong }}</span><div class="text-xs">{{ n.thuc_the }} {{ n.thuc_the_id }}</div></td>
                <td class="text-xs max-w-[260px] break-words">
                  <span v-if="n.du_lieu_truoc">{{ JSON.stringify(n.du_lieu_truoc) }} → </span>{{ n.du_lieu_sau ? JSON.stringify(n.du_lieu_sau) : '' }}</td>
                <td class="font-mono text-xs">{{ n.current_hash.slice(0, 6) }}…{{ n.current_hash.slice(-4) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <aside class="lg:col-span-5 the space-y-4">
      <div class="font-extrabold">GHÉP NỐI "MÁY NHẬN TIỀN" & THIẾT BỊ</div>
      <form class="space-y-2" @submit.prevent="taoMaGhep">
        <input v-model="tbMoi.ten" class="o-nhap" aria-label="Tên thiết bị" required />
        <select v-model="tbMoi.loai" class="o-nhap" aria-label="Loại thiết bị">
          <option v-for="(t, k) in TEN_LOAI" :key="k" :value="k">{{ t }}</option>
        </select>
        <button class="nut-do w-full">Tạo mã 6 số</button>
      </form>
      <div v-if="maGhep" class="bg-than-nhat rounded-lg p-4 text-center">
        <div class="text-sm font-semibold">Nhập mã này trên app của thiết bị:</div>
        <div class="text-4xl font-extrabold tracking-widest text-do">{{ maGhep.ma_ghep.slice(0, 3) }} {{ maGhep.ma_ghep.slice(3) }}</div>
        <div class="text-xs">Hết hạn {{ ngayGio(maGhep.ma_ghep_het_han) }} • dùng một lần</div>
      </div>
      <div class="space-y-2 text-sm">
        <div v-for="tb in thietBi" :key="tb.id" class="bg-than-nhat rounded p-3 flex justify-between items-center gap-2">
          <div><div class="font-bold">{{ tb.ten }}</div>
            <div class="text-xs">{{ TEN_LOAI[tb.loai] }} • {{ tb.trang_thai }} • báo sống {{ ngayGio(tb.lan_bao_song) }}
              <span v-if="tb.mat_ket_noi" class="huy-hieu-loi">Mất kết nối</span></div></div>
          <button v-if="tb.trang_thai === 'HOAT_DONG'" class="text-do font-bold" @click="lam(`/thiet-bi/${tb.id}/thu-hoi`, {}, 'Đã thu hồi thiết bị')">Thu hồi</button>
        </div>
      </div>
    </aside>
  </div>
</template>
