<script setup>
import { computed, ref, watch } from 'vue'
import { get, patch, post } from '../api'
import { bao } from '../store'
import HopThoai from './HopThoai.vue'

// hang = null: thêm mặt hàng mới; hang = dòng danh mục: sửa mặt hàng đó
const props = defineProps({ mo: Boolean, hang: Object })
const emit = defineEmits(['dong', 'da-luu'])

const loaiHang = ref([])
const mauHang = ref([])
const loaiGo = ref([])
const f = ref(null)
const dangLuu = ref(false)
const laMoi = computed(() => !props.hang)

const KIEU = { chu: 'Chữ', so: 'Số', co_khong: 'Có/Không' }
const kieuCua = (v) => (typeof v === 'boolean' ? 'co_khong' : typeof v === 'number' ? 'so' : 'chu')
const oTrong = (v) => (v === null || v === undefined ? '' : v)

function dongThuocTinh(giaTri, mau) {
  const dong = Object.entries(giaTri).map(([k, v]) => ({ k, v, kieu: kieuCua(v) }))
  for (const [k, v] of Object.entries(mau || {})) {
    if (!(k in giaTri)) dong.push({ k, v: v === 0 ? '' : v, kieu: kieuCua(v) })
  }
  return dong
}

async function napDanhMuc() {
  if (!loaiHang.value.length) {
    ;[loaiHang.value, mauHang.value, loaiGo.value] = await Promise.all([
      get('/hang-hoa/loai-hang'), get('/hang-hoa/mau-hang'), get('/hang-hoa/he-so-go')])
  }
}

watch(() => props.mo, async (mo) => {
  if (!mo) return
  f.value = null
  try {
    await napDanhMuc()
    const h = props.hang ? await get(`/hang-hoa/bien-the/${props.hang.id}`) : {}
    const mau = loaiHang.value.find(l => l.id === h.loai_hang_id)?.thuoc_tinh_mau
    f.value = {
      ma_noi_bo: h.ma || '', ten_hien_thi: h.ten || '', loai_hang_id: h.loai_hang_id || null,
      mau_hang_id: h.mau_hang_id || null, mauMoi: false, ten_mau_moi: '',
      loai_go: h.loai_go || '', mau_sac: oTrong(h.mau_sac), hoan_thien: oTrong(h.hoan_thien), kieu_dang: oTrong(h.kieu_dang),
      vat_lieu_phu: oTrong(h.vat_lieu_phu), xuat_xu: oTrong(h.xuat_xu), dai_mm: oTrong(h.dai_mm), rong_mm: oTrong(h.rong_mm),
      cao_mm: oTrong(h.cao_mm), khoi_luong_kg: oTrong(h.khoi_luong_kg), bao_hanh_thang: oTrong(h.bao_hanh_thang),
      don_vi_tinh: oTrong(h.don_vi_tinh), ton_toi_thieu: h.ton_toi_thieu ?? 0, mo_ta: oTrong(h.mo_ta),
      dat_theo_kich_thuoc: !!h.dat_theo_kich_thuoc,
      thuoc: dongThuocTinh(h.thuoc_tinh || {}, mau),
      gia_von: oTrong(h.gia_von), gia_san: oTrong(h.gia_san), gia_niem_yet: oTrong(h.gia_niem_yet),
      ton_ban_dau: 0, ly_do: '',
    }
  } catch (e) { bao(e.message, 'loi'); emit('dong') }
})

const mauTheoLoai = computed(() => mauHang.value.filter(m => m.loai_hang_id === f.value?.loai_hang_id))

function doiLoai() {
  f.value.mau_hang_id = null
  f.value.mauMoi = !mauTheoLoai.value.length
  // Điền sẵn thuộc tính mẫu của nhóm mới, giữ các dòng đã nhập
  const daNhap = Object.fromEntries(f.value.thuoc.filter(d => d.k.trim() && d.v !== '').map(d => [d.k, d.v]))
  f.value.thuoc = dongThuocTinh(daNhap, loaiHang.value.find(l => l.id === f.value.loai_hang_id)?.thuoc_tinh_mau)
}

function giaTri(d) {
  if (d.kieu === 'co_khong') return !!d.v
  if (d.kieu === 'so') return d.v === '' || d.v === null ? '' : Number(d.v)
  return String(d.v ?? '').trim()
}

function thanBody() {
  const v = f.value
  const thuoc_tinh = {}
  for (const d of v.thuoc) {
    const gt = giaTri(d)
    if (d.k.trim() && gt !== '' && !Number.isNaN(gt)) thuoc_tinh[d.k.trim()] = gt
  }
  const body = {
    ma_noi_bo: v.ma_noi_bo.trim().toUpperCase(), ten_hien_thi: v.ten_hien_thi.trim(),
    loai_go: v.loai_go, mau_sac: v.mau_sac, hoan_thien: v.hoan_thien, kieu_dang: v.kieu_dang,
    vat_lieu_phu: v.vat_lieu_phu, xuat_xu: v.xuat_xu, dai_mm: v.dai_mm, rong_mm: v.rong_mm, cao_mm: v.cao_mm,
    khoi_luong_kg: v.khoi_luong_kg, bao_hanh_thang: v.bao_hanh_thang,
    // Trùng đơn vị của nhóm thì để trống: đổi đơn vị nhóm sau này vẫn áp dụng cho mặt hàng
    don_vi_tinh: v.don_vi_tinh === loaiHang.value.find(l => l.id === v.loai_hang_id)?.don_vi_tinh ? null : v.don_vi_tinh,
    ton_toi_thieu: v.ton_toi_thieu, mo_ta: v.mo_ta, thuoc_tinh,
  }
  if (v.mauMoi) Object.assign(body, { ten_mau_moi: v.ten_mau_moi, loai_hang_id: v.loai_hang_id })
  else body.mau_hang_id = v.mau_hang_id
  if (!v.dat_theo_kich_thuoc) Object.assign(body, { gia_von: v.gia_von, gia_san: v.gia_san, gia_niem_yet: v.gia_niem_yet })
  if (laMoi.value) Object.assign(body, { ton_ban_dau: v.ton_ban_dau || 0, ly_do: v.ly_do })
  return body
}

async function luu() {
  dangLuu.value = true
  try {
    const kq = laMoi.value ? await post('/hang-hoa/bien-the', thanBody())
      : await patch(`/hang-hoa/bien-the/${props.hang.id}`, thanBody())
    bao(laMoi.value ? `Đã thêm mặt hàng ${kq.ma}` : `Đã lưu thông tin ${kq.ma}`, 'thanh-cong')
    emit('da-luu', kq)
    emit('dong')
  } catch (e) {
    bao(e.ma === 'CSDL_23505' ? 'Mã nội bộ đã được dùng cho mặt hàng khác' : e.message, 'loi')
  } finally { dangLuu.value = false }
}
</script>

<template>
  <HopThoai :mo="mo" rong :tieu-de="laMoi ? 'Thêm mặt hàng' : `Sửa thông tin ${hang?.ma || ''}`" @dong="emit('dong')">
    <p v-if="!f" class="text-sm">Đang tải…</p>
    <form v-else class="space-y-5" @submit.prevent="luu">
      <fieldset class="grid sm:grid-cols-2 gap-3">
        <legend class="font-extrabold mb-2">Nhận diện</legend>
        <label><span class="nhan">Mã nội bộ *</span>
          <input v-model="f.ma_noi_bo" class="o-nhap font-mono uppercase" required pattern="[A-Za-z0-9][A-Za-z0-9-]*"
            title="Chữ không dấu, số và dấu gạch ngang" placeholder="VD: TU-GIAY-SOI-900" /></label>
        <label><span class="nhan">Tên hiển thị *</span><input v-model="f.ten_hien_thi" class="o-nhap" required minlength="2" /></label>
        <label><span class="nhan">Nhóm hàng *</span>
          <select v-model="f.loai_hang_id" class="o-nhap" required @change="doiLoai">
            <option v-for="l in loaiHang" :key="l.id" :value="l.id">{{ l.ten }}</option>
          </select></label>
        <label v-if="!f.mauMoi"><span class="nhan">Mẫu hàng *</span>
          <select v-model="f.mau_hang_id" class="o-nhap" required
            @change="f.mau_hang_id === 'moi' && (f.mauMoi = true, f.mau_hang_id = null)">
            <option v-for="m in mauTheoLoai" :key="m.id" :value="m.id">{{ m.ten }}</option>
            <option value="moi">+ Mẫu mới…</option>
          </select></label>
        <label v-else><span class="nhan">Tên mẫu mới *</span>
          <span class="flex gap-2"><input v-model="f.ten_mau_moi" class="o-nhap" required placeholder="VD: Tủ giày" />
            <button v-if="mauTheoLoai.length" type="button" class="nut-vien nut-nho" @click="f.mauMoi = false">Chọn có sẵn</button></span></label>
      </fieldset>

      <fieldset class="grid sm:grid-cols-2 gap-3">
        <legend class="font-extrabold mb-2">Chất liệu &amp; hoàn thiện</legend>
        <label><span class="nhan">Loại gỗ</span>
          <select v-model="f.loai_go" class="o-nhap">
            <option value="">(Không ghi)</option>
            <option v-for="g in loaiGo" :key="g.loai_go" :value="g.loai_go">{{ g.loai_go }}</option>
          </select></label>
        <label><span class="nhan">Màu sắc</span><input v-model="f.mau_sac" class="o-nhap" placeholder="VD: Óc chó, Cánh gián" /></label>
        <label><span class="nhan">Hoàn thiện bề mặt</span><input v-model="f.hoan_thien" class="o-nhap" list="ds-hoan-thien" placeholder="VD: Sơn PU bóng mờ" /></label>
        <label><span class="nhan">Kiểu dáng</span><input v-model="f.kieu_dang" class="o-nhap" list="ds-kieu-dang" placeholder="VD: Hiện đại" /></label>
        <label class="sm:col-span-2"><span class="nhan">Vật liệu phụ / phụ kiện</span>
          <input v-model="f.vat_lieu_phu" class="o-nhap" placeholder="VD: Bản lề giảm chấn Hafele, kính cường lực" /></label>
        <datalist id="ds-hoan-thien"><option>Sơn PU bóng mờ</option><option>Sơn PU bóng gương</option><option>Sơn NC</option>
          <option>Lau dầu (vecni)</option><option>Melamine</option><option>Melamine chống ẩm</option><option>Laminate</option><option>Acrylic</option></datalist>
        <datalist id="ds-kieu-dang"><option>Hiện đại</option><option>Cổ điển</option><option>Tân cổ điển</option><option>Đông Dương</option><option>Bắc Âu</option></datalist>
      </fieldset>

      <fieldset class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <legend class="font-extrabold mb-2">Kích thước &amp; khối lượng</legend>
        <label><span class="nhan">Dài (mm)</span><input v-model.number="f.dai_mm" type="number" min="0" class="o-nhap" /></label>
        <label><span class="nhan">Rộng (mm)</span><input v-model.number="f.rong_mm" type="number" min="0" class="o-nhap" /></label>
        <label><span class="nhan">Cao (mm)</span><input v-model.number="f.cao_mm" type="number" min="0" class="o-nhap" /></label>
        <label><span class="nhan">Khối lượng (kg)</span><input v-model.number="f.khoi_luong_kg" type="number" min="0" class="o-nhap" /></label>
      </fieldset>

      <fieldset class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <legend class="font-extrabold mb-2">Bán hàng &amp; kho</legend>
        <label><span class="nhan">Bảo hành (tháng)</span><input v-model.number="f.bao_hanh_thang" type="number" min="0" max="240" class="o-nhap" /></label>
        <label><span class="nhan">Xuất xứ</span><input v-model="f.xuat_xu" class="o-nhap" placeholder="VD: Ý Yên, Nam Định" /></label>
        <label><span class="nhan">Đơn vị tính</span><input v-model="f.don_vi_tinh" class="o-nhap" placeholder="Theo nhóm hàng" /></label>
        <label><span class="nhan">Tồn tối thiểu</span><input v-model.number="f.ton_toi_thieu" type="number" min="0" class="o-nhap" /></label>
        <label class="col-span-2 sm:col-span-4"><span class="nhan">Mô tả</span>
          <textarea v-model="f.mo_ta" rows="2" class="o-nhap py-2" placeholder="Điểm nổi bật để tư vấn khách" /></label>
      </fieldset>

      <fieldset class="space-y-2">
        <legend class="font-extrabold mb-2">Thuộc tính riêng của nhóm hàng</legend>
        <div v-for="(d, i) in f.thuoc" :key="i" class="grid grid-cols-12 gap-2 items-center">
          <input v-model="d.k" class="o-nhap col-span-5 sm:col-span-4" placeholder="Tên thuộc tính" :aria-label="`Tên thuộc tính ${i + 1}`" />
          <select v-model="d.kieu" class="o-nhap col-span-3 sm:col-span-2 px-2" :aria-label="`Kiểu thuộc tính ${i + 1}`">
            <option v-for="(ten, ma) in KIEU" :key="ma" :value="ma">{{ ten }}</option>
          </select>
          <label v-if="d.kieu === 'co_khong'" class="col-span-3 sm:col-span-5 flex items-center gap-2 font-semibold">
            <input v-model="d.v" type="checkbox" class="w-5 h-5 accent-do" /> {{ d.v ? 'Có' : 'Không' }}</label>
          <input v-else v-model="d.v" :type="d.kieu === 'so' ? 'number' : 'text'" class="o-nhap col-span-3 sm:col-span-5"
            :aria-label="`Giá trị ${d.k || 'thuộc tính'}`" />
          <button type="button" class="nut-vien nut-nho col-span-1 px-0" :aria-label="`Bỏ thuộc tính ${d.k}`" @click="f.thuoc.splice(i, 1)">✕</button>
        </div>
        <button type="button" class="nut-vien nut-nho" @click="f.thuoc.push({ k: '', v: '', kieu: 'chu' })">+ Thêm thuộc tính</button>
      </fieldset>

      <fieldset v-if="!f.dat_theo_kich_thuoc" class="grid sm:grid-cols-3 gap-3">
        <legend class="font-extrabold mb-1">Giá (đ)</legend>
        <p class="sm:col-span-3 text-xs -mt-1">Đổi giá không ghi đè: mức cũ được đóng lại và giữ trong lịch sử giá.</p>
        <label><span class="nhan">Giá vốn</span><input v-model.number="f.gia_von" type="number" min="0" step="1000" class="o-nhap" /></label>
        <label><span class="nhan">Giá sàn</span><input v-model.number="f.gia_san" type="number" min="0" step="1000" class="o-nhap" /></label>
        <label><span class="nhan">Giá niêm yết</span><input v-model.number="f.gia_niem_yet" type="number" min="0" step="1000" class="o-nhap" /></label>
      </fieldset>
      <p v-else class="bg-than-nhat rounded-lg p-3 text-sm">Hàng đặt theo kích thước: giá tính theo công thức, không đặt giá cố định.</p>

      <fieldset v-if="laMoi" class="grid sm:grid-cols-3 gap-3">
        <legend class="font-extrabold mb-2">Tồn ban đầu (hàng đếm được khi kiểm kê)</legend>
        <label><span class="nhan">Số lượng</span><input v-model.number="f.ton_ban_dau" type="number" min="0" class="o-nhap" /></label>
        <label class="sm:col-span-2"><span class="nhan">Lý do ghi sổ</span>
          <input v-model="f.ly_do" class="o-nhap" :required="f.ton_ban_dau > 0" minlength="3" placeholder="VD: Kiểm kê tháng 10 phát hiện hàng chưa có mã" /></label>
      </fieldset>

      <div class="flex gap-2 sticky bottom-0 bg-white pt-2">
        <button type="button" class="nut-vien flex-1" @click="emit('dong')">Hủy</button>
        <button class="nut-do flex-1" :disabled="dangLuu">{{ dangLuu ? 'Đang lưu…' : laMoi ? 'Thêm mặt hàng' : 'Lưu thay đổi' }}</button>
      </div>
    </form>
  </HopThoai>
</template>
