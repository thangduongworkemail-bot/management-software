<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, get, post, taiFileLen } from '../api'
import { db } from '../db'
import { docKichThuoc } from '../lib/dimension'
import { tien, kichThuoc } from '../lib/format'
import { tinhGia } from '../lib/pricing'
import { timNgoaiTuyen } from '../lib/search'
import { bao, laChu, trangThai } from '../store'
import { luuDonNgoaiTuyen } from '../sync'
import HopThoai from '../components/HopThoai.vue'
import HuyHieu from '../components/HuyHieu.vue'
import MaQr from '../components/MaQr.vue'

const q = ref('')
const ketQua = ref([])
const thoiGianTim = ref(null)
const gioHang = ref([])
const khach = ref({ ten: '', so_dien_thoai: '', ma_so_thue: '' })
const canHoaDon = ref(false)
const don = ref(null)            // đơn vừa tạo trên máy chủ
const dangGui = ref(false)

// --- Tìm kiếm (máy chủ khi có mạng, IndexedDB khi mất mạng) -----------------
let hen = null
watch(q, (v) => {
  clearTimeout(hen)
  hen = setTimeout(() => tim(v), 200)
})

async function tim(v) {
  if (!v.trim()) { ketQua.value = []; return }
  if (trangThai.online) {
    try {
      const kq = await get(`/hang-hoa/tim-kiem?q=${encodeURIComponent(v)}`)
      ketQua.value = kq.ket_qua
      thoiGianTim.value = kq.thoi_gian_ms
      return
    } catch (e) {
      if (!e.matKetNoi) { bao(e.message, 'loi'); return }
    }
  }
  ketQua.value = await timNgoaiTuyen(v)
  thoiGianTim.value = null
}

// --- Hàng đặt kích thước riêng -------------------------------------------
const datRieng = ref(null)   // { hang, kich_thuoc, ket_qua, loi }

function chon(h) {
  if (h.dat_theo_kich_thuoc) {
    datRieng.value = { hang: h, kich_thuoc: '', ket_qua: null, loi: '' }
    return
  }
  themVaoGio({ hang: h, so_luong: 1, don_gia_ban: h.gia_niem_yet })
}

async function tinhDatRieng() {
  const d = datRieng.value
  d.loi = ''
  d.ket_qua = null
  try {
    if (trangThai.online) {
      d.ket_qua = await post(`/hang-hoa/bien-the/${d.hang.id}/tinh-gia`, { kich_thuoc: d.kich_thuoc })
    } else {
      const ct = await db.cong_thuc.get(d.hang.id)
      const kt = docKichThuoc(d.kich_thuoc, ct.kich_thuoc_min_mm, ct.kich_thuoc_max_mm)
      if (!kt.hopLe) throw new Error(kt.canhBao.join('; '))
      d.ket_qua = { gia: tinhGia(ct, kt.giaTriMm), kich_thuoc_mm: kt.giaTriMm, dien_giai: '(tính ngoại tuyến)' }
    }
  } catch (e) {
    d.loi = e.message
  }
}

function themDatRieng() {
  const d = datRieng.value
  themVaoGio({ hang: d.hang, so_luong: 1, don_gia_ban: d.ket_qua.gia, kich_thuoc: d.kich_thuoc,
               mo_ta: `${d.hang.ten} — ${d.ket_qua.kich_thuoc_mm.join(' × ')} mm`, dien_giai: d.ket_qua.dien_giai })
  datRieng.value = null
}

function themVaoGio(dong) {
  const trung = !dong.kich_thuoc && gioHang.value.find(g => g.hang.kieu === dong.hang.kieu && g.hang.id === dong.hang.id)
  if (trung) trung.so_luong++
  else gioHang.value.push(dong)
  q.value = ''
  ketQua.value = []
}

const tong = computed(() => gioHang.value.reduce((s, g) => s + g.so_luong * (g.don_gia_ban || 0), 0))

function dongGuiLen(g) {
  return {
    [g.hang.kieu === 'BO' ? 'bo_san_pham_id' : 'bien_the_id']: g.hang.id,
    so_luong: g.so_luong,
    don_gia_ban: g.don_gia_ban,
    kich_thuoc: g.kich_thuoc || null,
  }
}

function duLieuKhach() {
  const k = khach.value
  return k.ten || k.so_dien_thoai ? { ten: k.ten || null, so_dien_thoai: k.so_dien_thoai || null, ma_so_thue: k.ma_so_thue || null } : null
}

// --- Tạo đơn ---------------------------------------------------------------
async function taoDon() {
  if (!gioHang.value.length) return
  dangGui.value = true
  const body = { dong: gioHang.value.map(dongGuiLen), khach_hang: duLieuKhach(), can_hoa_don: canHoaDon.value }
  try {
    don.value = await post('/don-hang', body)
    gioHang.value = []
    if (don.value.trang_thai === 'CHO_DUYET_GIA') bao('Giá thấp hơn mức cho phép — đã gửi Chủ duyệt', 'canh-bao', 8)
  } catch (e) {
    if (e.matKetNoi) moBanNgoaiTuyen.value = true
    else bao(e.chiTiet?.length && e.ma === 'KHONG_DU_TON'
      ? `Không đủ hàng: ${e.chiTiet.map(t => `${t.ma_noi_bo} còn ${t.kha_dung}`).join(', ')}` : e.message, 'loi', 8)
  } finally {
    dangGui.value = false
  }
}

// Mất mạng: thu tiền mặt, lưu đơn vào IndexedDB kèm khóa chống trùng
const moBanNgoaiTuyen = ref(false)
async function banNgoaiTuyen() {
  await luuDonNgoaiTuyen({ dong: gioHang.value.map(dongGuiLen), khach_hang: duLieuKhach(), can_hoa_don: canHoaDon.value,
                           thanh_toan: { phuong_thuc: 'TIEN_MAT', so_tien: tong.value } })
  bao('Đã lưu đơn ngoại tuyến. Có mạng lại sẽ tự gửi lên máy chủ.', 'thanh-cong', 8)
  gioHang.value = []
  moBanNgoaiTuyen.value = false
}

// --- Thanh toán đơn hiện tại ---------------------------------------------
async function taiLaiDon() {
  if (don.value) don.value = await get(`/don-hang/${don.value.id}`)
}

watch(() => trangThai.suKien, () => {
  const sk = trangThai.suKienCuoi
  if (don.value && sk?.du_lieu?.don_id === don.value.id) taiLaiDon()
})

const conLai = ref(0)
let dongHo = null
onMounted(() => {
  dongHo = setInterval(() => {
    conLai.value = don.value?.giu_cho_den ? Math.max(0, new Date(don.value.giu_cho_den) - Date.now()) : 0
  }, 1000)
})
onBeforeUnmount(() => clearInterval(dongHo))
const demNguoc = computed(() => {
  const s = Math.floor(conLai.value / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})

const tienKhachDua = ref(null)
async function thuTienMat() {
  try {
    const kq = await post(`/don-hang/${don.value.id}/thanh-toan`, { so_tien: Number(tienKhachDua.value) })
    don.value = kq.don
    bao(kq.tien_thoi ? `Đã thu. Thối lại khách ${tien(kq.tien_thoi)}` : 'Đã thu tiền mặt', 'thanh-cong', 10)
    tienKhachDua.value = null
  } catch (e) { bao(e.message, 'loi') }
}

const xacNhan = ref(null)    // { bon_so_cuoi, file }
async function guiXacNhanTay() {
  try {
    let anh = null
    if (xacNhan.value.file) anh = await taiFileLen(xacNhan.value.file, 'bien-lai')
    const kq = await post(`/don-hang/${don.value.id}/xac-nhan-tay`,
      { bon_so_cuoi: xacNhan.value.bon_so_cuoi || null, anh_bien_lai_url: anh })
    don.value = kq.don
    xacNhan.value = null
    bao('Đã xác nhận nhận tiền', 'thanh-cong')
  } catch (e) { bao(e.message, 'loi') }
}

async function moPhongTienVe() {
  try {
    await post('/dev/mo-phong-tien-ve', { ma_don: don.value.ma })
    await taiLaiDon()
  } catch (e) { bao(e.message, 'loi') }
}

async function taoBaoGia() {
  if (!gioHang.value.length) return
  try {
    const bg = await post('/bao-gia', { dong: gioHang.value.map(dongGuiLen), khach_hang: duLieuKhach() })
    const url = `${location.origin}/bao-gia/${bg.ma_chia_se}`
    if (navigator.share) await navigator.share({ title: `Báo giá ${bg.ma} — Nội thất Khanh Vân`, url }).catch(() => {})
    else await navigator.clipboard?.writeText(url)
    bao(`Đã tạo báo giá ${bg.ma} (giữ giá 7 ngày). Liên kết đã sẵn sàng chia sẻ.`, 'thanh-cong', 10)
    window.open(url, '_blank')
  } catch (e) { bao(e.message, 'loi') }
}

function donMoi() {
  don.value = null
  khach.value = { ten: '', so_dien_thoai: '', ma_so_thue: '' }
  canHoaDon.value = false
}
</script>

<template>
  <div class="grid lg:grid-cols-12 gap-4">
    <!-- Cột trái: tìm & giỏ hàng -->
    <section class="lg:col-span-7 space-y-4">
      <div class="the space-y-3">
        <label for="tim" class="tieu-de block">Tìm hàng</label>
        <input id="tim" v-model="q" class="o-nhap text-lg" autocomplete="off"
          placeholder='Gõ không dấu cũng được: "giuong 1m8 soi", "tu ao", "ban tho mit"…' />
        <p v-if="thoiGianTim !== null && ketQua.length" class="text-xs text-slate-600">
          {{ ketQua.length }} kết quả trong {{ thoiGianTim }} ms
        </p>
        <p v-if="!trangThai.online && q" class="text-xs font-bold text-do">Đang tìm trên dữ liệu đã lưu trong máy (mất mạng)</p>
        <ul v-if="ketQua.length" class="divide-y divide-slate-200 border border-slate-200 rounded-lg overflow-hidden">
          <li v-for="h in ketQua" :key="`${h.kieu}-${h.id}`">
            <button class="w-full text-left p-3 hover:bg-than-nhat flex justify-between gap-3" @click="chon(h)">
              <span>
                <span class="font-extrabold block">{{ h.ten }}</span>
                <span class="text-xs text-slate-600">
                  {{ h.ma }} <template v-if="kichThuoc(h).trim()">• {{ kichThuoc(h) }}</template>
                  <template v-if="!h.dat_theo_kich_thuoc">• Còn {{ h.ton_kha_dung ?? '?' }}</template>
                </span>
              </span>
              <span class="text-right shrink-0">
                <span v-if="h.dat_theo_kich_thuoc" class="huy-hieu-canh-bao">Đặt kích thước</span>
                <span v-else class="font-extrabold text-do">{{ tien(h.gia_niem_yet) }}</span>
              </span>
            </button>
          </li>
        </ul>
        <p v-else-if="q && thoiGianTim !== null" class="text-sm">Không thấy mặt hàng phù hợp.</p>
      </div>

      <div v-if="datRieng" class="the border-2 border-do space-y-3">
        <div class="font-extrabold text-do">TÍNH GIÁ HÀNG ĐẶT KÍCH THƯỚC RIÊNG</div>
        <div class="font-bold">{{ datRieng.hang.ten }}</div>
        <form class="flex gap-2" @submit.prevent="tinhDatRieng">
          <input v-model="datRieng.kich_thuoc" class="o-nhap" aria-label="Kích thước khách đặt"
            placeholder='Nhập như nói: "2m4", "1m8 x 2m", "180"' required />
          <button class="nut-vien">Tính</button>
        </form>
        <p v-if="datRieng.loi" class="text-do font-bold" role="alert">{{ datRieng.loi }}</p>
        <div v-if="datRieng.ket_qua" class="bg-than-nhat rounded-lg p-3">
          <div class="text-sm font-semibold">{{ datRieng.ket_qua.dien_giai }}</div>
          <div class="text-2xl font-extrabold text-do mt-1">{{ tien(datRieng.ket_qua.gia) }}</div>
        </div>
        <div class="flex gap-2">
          <button class="nut-do" :disabled="!datRieng.ket_qua" @click="themDatRieng">Thêm vào đơn</button>
          <button class="nut-vien" @click="datRieng = null">Bỏ</button>
        </div>
      </div>

      <div class="the space-y-3">
        <div class="tieu-de">Giỏ hàng</div>
        <p v-if="!gioHang.length" class="text-slate-600">Chưa có mặt hàng nào.</p>
        <div v-for="(g, i) in gioHang" :key="i" class="flex flex-wrap items-center gap-3 border-b border-slate-200 pb-3">
          <div class="flex-1 min-w-[200px]">
            <div class="font-extrabold">{{ g.mo_ta || g.hang.ten }}</div>
            <div class="text-xs text-slate-600">{{ g.hang.ma }}<template v-if="g.dien_giai"> • {{ g.dien_giai }}</template></div>
          </div>
          <div class="flex items-center gap-1" role="group" aria-label="Số lượng">
            <button class="nut-vien nut-nho w-10" :disabled="g.so_luong <= 1" @click="g.so_luong--" aria-label="Bớt">−</button>
            <span class="w-8 text-center font-extrabold">{{ g.so_luong }}</span>
            <button class="nut-vien nut-nho w-10" :disabled="!!g.kich_thuoc" @click="g.so_luong++" aria-label="Thêm">+</button>
          </div>
          <label class="w-40">
            <span class="sr-only">Đơn giá bán</span>
            <input v-model.number="g.don_gia_ban" type="number" min="0" step="1000" class="o-nhap text-right" />
          </label>
          <button class="text-do font-bold px-2" @click="gioHang.splice(i, 1)">Xóa</button>
        </div>
        <div class="grid sm:grid-cols-3 gap-3">
          <div><label class="nhan" for="kh-ten">Tên khách</label><input id="kh-ten" v-model="khach.ten" class="o-nhap" /></div>
          <div><label class="nhan" for="kh-sdt">Số điện thoại</label><input id="kh-sdt" v-model="khach.so_dien_thoai" class="o-nhap" inputmode="tel" /></div>
          <div><label class="nhan" for="kh-mst">Mã số thuế</label><input id="kh-mst" v-model="khach.ma_so_thue" class="o-nhap" inputmode="numeric" /></div>
        </div>
        <label class="flex items-center gap-2 font-bold"><input v-model="canHoaDon" type="checkbox" class="w-5 h-5" /> Khách cần hóa đơn điện tử</label>
        <div class="flex flex-wrap items-center gap-3 justify-between pt-2">
          <div class="text-2xl font-extrabold">Tổng: <span class="text-do">{{ tien(tong) }}</span></div>
          <div class="flex gap-2">
            <button class="nut-vien" :disabled="!gioHang.length || !trangThai.online" @click="taoBaoGia">Gửi báo giá</button>
            <button v-if="trangThai.online" class="nut-do text-lg" :disabled="!gioHang.length || dangGui" @click="taoDon">Chốt đơn</button>
            <button v-else class="nut-do text-lg" :disabled="!gioHang.length" @click="moBanNgoaiTuyen = true">Bán ngoại tuyến (tiền mặt)</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Cột phải: thanh toán -->
    <aside class="lg:col-span-5">
      <div v-if="don" class="the space-y-4 lg:sticky lg:top-28">
        <div class="flex justify-between items-start gap-2">
          <div>
            <div class="text-sm font-bold text-slate-600">Đơn #{{ don.ma }}</div>
            <div class="flex gap-1 mt-1"><HuyHieu :ma="don.trang_thai" /><HuyHieu :ma="don.trang_thai_giao" /></div>
          </div>
          <button class="nut-vien nut-nho" @click="donMoi">Đơn mới</button>
        </div>
        <div class="flex justify-between items-baseline border-b border-slate-300 pb-3">
          <span class="font-extrabold">KHÁCH CẦN TRẢ:</span>
          <span class="text-3xl font-extrabold text-do">{{ tien(don.con_phai_thu) }}</span>
        </div>

        <template v-if="don.trang_thai === 'CHO_DUYET_GIA'">
          <p class="bg-amber-50 border border-amber-300 rounded-lg p-3 font-bold">
            Giá bán thấp hơn mức cho phép. Đã gửi yêu cầu tới điện thoại của Chủ — chờ duyệt rồi mới thu tiền.
          </p>
        </template>

        <template v-else-if="don.con_phai_thu > 0 && don.vietqr">
          <div class="flex flex-col items-center gap-2 bg-than-nhat rounded-xl p-4">
            <MaQr :noi-dung="don.vietqr" :kich-thuoc="240" />
            <div class="text-sm font-bold">Nội dung CK: {{ don.ma }}</div>
            <div class="text-xs">{{ don.tai_khoan_nhan.chu_tai_khoan }} • {{ don.tai_khoan_nhan.so_tai_khoan }}</div>
            <div v-if="don.giu_cho_den" class="font-extrabold text-do">Giữ hàng còn {{ demNguoc }}</div>
            <div class="text-xs font-bold">● Tiền về sẽ tự xác nhận, màn hình tự cập nhật</div>
          </div>
          <form class="flex gap-2" @submit.prevent="thuTienMat">
            <input v-model="tienKhachDua" type="number" min="1" step="1000" class="o-nhap" aria-label="Tiền mặt khách đưa"
              :placeholder="`Tiền mặt khách đưa (≥ ${tien(don.con_phai_thu)})`" required />
            <button class="nut-vien shrink-0">Thu tiền mặt</button>
          </form>
          <button v-if="laChu()" class="nut-do w-full" @click="xacNhan = { bon_so_cuoi: '', file: null }">
            Khách đã chuyển, tôi đã thấy tiền (Xác nhận tay)
          </button>
          <button v-if="laChu()" class="text-xs underline w-full" @click="moPhongTienVe">(Demo) Mô phỏng Máy nhận tiền báo tiền về</button>
        </template>

        <div v-else-if="don.trang_thai === 'DA_THANH_TOAN'" class="bg-emerald-50 border border-emerald-300 rounded-xl p-4 text-center space-y-2">
          <div class="text-2xl font-extrabold text-emerald-800">ĐÃ THU ĐỦ TIỀN</div>
          <div class="text-sm">Hóa đơn điện tử: <HuyHieu :ma="don.hoa_don?.trang_thai" /> (không chặn giao hàng)</div>
        </div>

        <ul class="text-sm space-y-1">
          <li v-for="d in don.dong" :key="d.id" class="flex justify-between gap-2">
            <span>{{ d.so_luong }} × {{ d.mo_ta }}</span><span class="font-bold">{{ tien(d.thanh_tien) }}</span>
          </li>
        </ul>
        <router-link :to="`/phieu/${don.id}`" target="_blank" class="nut-vien w-full">In phiếu bán hàng nội bộ</router-link>
      </div>
      <div v-else class="the text-slate-600">Chốt đơn để hiện mã VietQR và các cách thu tiền.</div>
    </aside>

    <HopThoai :mo="!!xacNhan" tieu-de="Xác nhận đã nhận tiền" @dong="xacNhan = null">
      <template v-if="xacNhan">
        <p class="bg-amber-50 border border-amber-300 rounded-lg p-3 font-semibold">
          Chỉ bấm khi bạn đã <strong>THẤY TIỀN</strong> trong app ngân hàng. Ảnh biên lai khách đưa chỉ là bằng chứng.
        </p>
        <div>
          <label class="nhan" for="4so">Cách 1 — 4 số cuối mã giao dịch</label>
          <input id="4so" v-model="xacNhan.bon_so_cuoi" class="o-nhap text-2xl tracking-[0.5em] text-center" maxlength="4"
            inputmode="numeric" pattern="\d{4}" />
        </div>
        <div>
          <label class="nhan" for="anh">Cách 2 — Chụp ảnh biên lai</label>
          <input id="anh" type="file" accept="image/*" capture="environment" class="o-nhap py-2"
            @change="xacNhan.file = $event.target.files[0]" />
        </div>
        <button class="nut-do w-full" :disabled="!/^\d{4}$/.test(xacNhan.bon_so_cuoi) && !xacNhan.file" @click="guiXacNhanTay">
          Xác nhận đã nhận {{ tien(don?.con_phai_thu) }}
        </button>
      </template>
    </HopThoai>

    <HopThoai :mo="moBanNgoaiTuyen" tieu-de="Bán khi mất mạng" @dong="moBanNgoaiTuyen = false">
      <p class="font-semibold">Không kết nối được máy chủ. Thu <strong>tiền mặt {{ tien(tong) }}</strong> rồi lưu đơn vào máy.
        Khi có mạng, đơn tự gửi lên (không bị tạo trùng). Nếu kho thiếu hàng, Chủ sẽ được báo để xử lý.</p>
      <button class="nut-do w-full" @click="banNgoaiTuyen">Đã thu tiền mặt — lưu đơn</button>
    </HopThoai>
  </div>
</template>
