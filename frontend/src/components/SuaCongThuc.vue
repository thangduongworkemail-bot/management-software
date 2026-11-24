<script setup>
// Chủ tự cấu hình công thức giá hàng đặt kích thước riêng (FR-02): 3 kiểu mét dài / m² / bậc kích thước,
// hệ số loại gỗ, khoảng kích thước cho phép, tỷ lệ giá sàn và giá vốn ước tính. Xem trước giá ngay khi gõ.
import { computed, ref, watch } from 'vue'
import { get, put } from '../api'
import { docKichThuoc, docMotKichThuoc } from '../lib/dimension'
import { tien } from '../lib/format'
import { tinhGia } from '../lib/pricing'
import { bao } from '../store'
import HopThoai from './HopThoai.vue'

const props = defineProps({ mo: Boolean, hang: Object })
const emit = defineEmits(['dong', 'da-luu'])

const KIEU = [
  { ma: 'THEO_CHIEU_DAI', ten: 'Theo mét dài', vd: 'Tủ thờ, kệ, bàn dài',
    cach: 'Giá = Đơn giá 1 mét × chiều dài × hệ số gỗ + phụ phí' },
  { ma: 'THEO_DIEN_TICH', ten: 'Theo m²', vd: 'Mặt bàn, vách, sàn',
    cach: 'Giá = Đơn giá 1 m² × (dài × rộng) × hệ số gỗ + phụ phí' },
  { ma: 'THEO_BAC', ten: 'Theo bậc kích thước', vd: 'Giường theo cỡ nệm',
    cach: 'Kích thước đến mức nào thì giá cố định bấy nhiêu' },
]

const f = ref(null)
const goc = ref(null)
const loi = ref('')
const dangLuu = ref(false)

/** 1800 -> "1m8", 2000 -> "2m", 400 -> "400mm": viết lại theo cách cửa hàng hay nói. */
function hienKichThuoc(mm) {
  if (!mm) return ''
  if (mm % 1000 === 0) return `${mm / 1000}m`
  if (mm > 1000 && mm % 100 === 0) return `${Math.floor(mm / 1000)}m${(mm % 1000) / 100}`
  return `${mm}mm`
}
const phanNghinRaPhanTram = (n) => n / 10
const phanTramRaPhanNghin = (n) => Math.round(Number(n) * 10)

watch(() => props.mo, async (mo) => {
  if (!mo || !props.hang) return
  loi.value = ''
  f.value = null
  try {
    const d = await get(`/hang-hoa/bien-the/${props.hang.id}/cong-thuc`)
    goc.value = d
    const ct = d.cong_thuc || { kieu: 'THEO_CHIEU_DAI', don_gia: null, phu_phi: 0, bac_gia: [], kich_thuoc_min_mm: 400,
      kich_thuoc_max_mm: 3000, ty_le_gia_von_phan_nghin: 650, ty_le_gia_san_phan_nghin: 800 }
    f.value = {
      kieu: ct.kieu,
      don_gia: ct.don_gia,
      phu_phi: ct.phu_phi,
      bac: ct.bac_gia.length ? ct.bac_gia.map(b => ({ kich_thuoc: hienKichThuoc(b.toi_da_mm), gia: b.gia }))
        : [{ kich_thuoc: '1m6', gia: null }, { kich_thuoc: '1m8', gia: null }],
      min: hienKichThuoc(ct.kich_thuoc_min_mm),
      max: hienKichThuoc(ct.kich_thuoc_max_mm),
      von: phanNghinRaPhanTram(ct.ty_le_gia_von_phan_nghin),
      san: phanNghinRaPhanTram(ct.ty_le_gia_san_phan_nghin),
      he_so: d.he_so_phan_nghin / 1000,
      thu: ct.kieu === 'THEO_DIEN_TICH' ? '1m6 x 80cm' : '2m',
    }
  } catch (e) { loi.value = e.message }
}, { immediate: true })

function docMm(text, ten) {
  try {
    const mm = docMotKichThuoc(String(text))
    if (!mm) throw new Error()
    return mm
  } catch { throw new Error(`${ten}: không đọc được kích thước "${text}"`) }
}

/** Dữ liệu gửi lên máy chủ; ném lỗi tiếng Việt nếu ô nào gõ sai. */
function duLieuGui() {
  const v = f.value
  const body = {
    kieu: v.kieu, phu_phi: Number(v.phu_phi) || 0,
    kich_thuoc_min_mm: docMm(v.min, 'Nhỏ nhất'), kich_thuoc_max_mm: docMm(v.max, 'Lớn nhất'),
    ty_le_gia_von_phan_nghin: phanTramRaPhanNghin(v.von), ty_le_gia_san_phan_nghin: phanTramRaPhanNghin(v.san),
  }
  if (v.kieu === 'THEO_BAC') {
    body.bac_gia = v.bac.filter(b => b.kich_thuoc || b.gia)
      .map((b, i) => ({ toi_da_mm: docMm(b.kich_thuoc, `Bậc ${i + 1}`), gia: Number(b.gia) || 0 }))
  } else {
    body.don_gia = v.don_gia === null || v.don_gia === '' ? null : Number(v.don_gia)
  }
  return body
}

const heSoPhanNghin = computed(() => Math.round(Number(f.value?.he_so || 1) * 1000))

// Xem trước giá bằng bản JS của công thức (khớp backend từng đồng)
const xemTruoc = computed(() => {
  if (!f.value?.thu) return null
  try {
    const ct = { ...duLieuGui(), he_so_phan_nghin: heSoPhanNghin.value }
    if (ct.kieu !== 'THEO_BAC' && !ct.don_gia) return { loi: 'Nhập đơn giá để xem trước' }
    if (ct.kieu === 'THEO_BAC' && !ct.bac_gia.length) return { loi: 'Thêm ít nhất một bậc' }
    const kt = docKichThuoc(f.value.thu, ct.kich_thuoc_min_mm, ct.kich_thuoc_max_mm)
    if (!kt.hopLe) return { loi: kt.canhBao.join('; ') }
    const gia = tinhGia(ct, kt.giaTriMm)
    const lamTron = (x) => Math.round(x / 1000) * 1000
    return { gia, san: lamTron(gia * ct.ty_le_gia_san_phan_nghin / 1000), von: lamTron(gia * ct.ty_le_gia_von_phan_nghin / 1000) }
  } catch (e) { return { loi: e.message } }
})

async function luu() {
  loi.value = ''
  dangLuu.value = true
  try {
    const body = duLieuGui()
    if (goc.value.loai_go && heSoPhanNghin.value !== goc.value.he_so_phan_nghin) {
      await put('/hang-hoa/he-so-go', { loai_go: goc.value.loai_go, he_so_phan_nghin: heSoPhanNghin.value })
    }
    const kq = await put(`/hang-hoa/bien-the/${props.hang.id}/cong-thuc`, body)
    bao('Đã lưu công thức giá. Đơn và báo giá đã lập giữ nguyên giá cũ.', 'thanh-cong', 8)
    emit('da-luu', kq)
    emit('dong')
  } catch (e) {
    loi.value = e.message
  } finally {
    dangLuu.value = false
  }
}
</script>

<template>
  <HopThoai :mo="mo" :tieu-de="`Công thức giá — ${hang?.ten || ''}`" rong @dong="emit('dong')">
    <p v-if="!f && loi" class="text-do font-bold" role="alert">{{ loi }}</p>
    <form v-if="f" class="space-y-4" @submit.prevent="luu">
      <fieldset class="space-y-2">
        <legend class="nhan">Cách tính giá</legend>
        <div class="grid sm:grid-cols-3 gap-2">
          <label v-for="k in KIEU" :key="k.ma" :class="f.kieu === k.ma ? 'border-do bg-do-nhat' : 'border-slate-300'"
            class="border-2 rounded-xl p-3 cursor-pointer">
            <input v-model="f.kieu" type="radio" name="kieu" :value="k.ma" class="sr-only" />
            <span class="font-extrabold block">{{ k.ten }}</span>
            <span class="text-xs">{{ k.vd }}</span>
          </label>
        </div>
        <p class="text-sm bg-than-nhat rounded-lg p-2 font-semibold">{{ KIEU.find(k => k.ma === f.kieu).cach }}</p>
      </fieldset>

      <div v-if="f.kieu !== 'THEO_BAC'" class="grid sm:grid-cols-2 gap-3">
        <div>
          <label class="nhan" for="ct-don-gia">Đơn giá 1 {{ f.kieu === 'THEO_CHIEU_DAI' ? 'mét dài' : 'm²' }} (đồng)</label>
          <input id="ct-don-gia" v-model.number="f.don_gia" type="number" min="0" step="1000" class="o-nhap text-right" required />
        </div>
        <div>
          <label class="nhan" for="ct-phu-phi">Phụ phí mỗi sản phẩm (đồng)</label>
          <input id="ct-phu-phi" v-model.number="f.phu_phi" type="number" min="0" step="1000" class="o-nhap text-right" />
        </div>
      </div>

      <fieldset v-else class="space-y-2">
        <legend class="nhan">Bảng bậc giá (theo số đo đầu tiên khách nói, vd giường "1m8 x 2m" tính bậc 1m8)</legend>
        <div v-for="(b, i) in f.bac" :key="i" class="flex gap-2 items-center">
          <span class="text-sm font-bold w-16 shrink-0">Đến</span>
          <input v-model="b.kich_thuoc" class="o-nhap" :aria-label="`Bậc ${i + 1}: kích thước tối đa`" placeholder="1m6" />
          <input v-model.number="b.gia" type="number" min="0" step="1000" class="o-nhap text-right"
            :aria-label="`Bậc ${i + 1}: giá`" placeholder="Giá (đồng)" />
          <button type="button" class="text-do font-bold px-2 min-h-[48px]" :aria-label="`Xóa bậc ${i + 1}`"
            :disabled="f.bac.length <= 1" @click="f.bac.splice(i, 1)">Xóa</button>
        </div>
        <button type="button" class="nut-vien nut-nho" @click="f.bac.push({ kich_thuoc: '', gia: null })">+ Thêm bậc</button>
      </fieldset>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label class="nhan" for="ct-min">Nhỏ nhất nhận làm</label>
          <input id="ct-min" v-model="f.min" class="o-nhap" placeholder="40cm" required />
        </div>
        <div>
          <label class="nhan" for="ct-max">Lớn nhất nhận làm</label>
          <input id="ct-max" v-model="f.max" class="o-nhap" placeholder="3m" required />
        </div>
        <div>
          <label class="nhan" for="ct-san">Giá sàn (% giá)</label>
          <input id="ct-san" v-model.number="f.san" type="number" min="0" max="100" step="0.1" class="o-nhap text-right" required />
        </div>
        <div>
          <label class="nhan" for="ct-von">Giá vốn ước (% giá)</label>
          <input id="ct-von" v-model.number="f.von" type="number" min="0" max="100" step="0.1" class="o-nhap text-right" required />
        </div>
      </div>

      <div v-if="goc.loai_go && f.kieu !== 'THEO_BAC'" class="flex flex-wrap items-end gap-3">
        <div>
          <label class="nhan" for="ct-he-so">Hệ số gỗ {{ goc.loai_go }}</label>
          <input id="ct-he-so" v-model.number="f.he_so" type="number" min="0.01" max="10" step="0.01" class="o-nhap text-right w-32" required />
        </div>
        <p class="text-xs text-slate-600 flex-1 min-w-[200px] pb-1">
          Đổi hệ số áp dụng cho <strong>mọi</strong> mặt hàng gỗ {{ goc.loai_go }} tính theo công thức.
        </p>
      </div>

      <div class="border-2 border-dashed border-slate-300 rounded-xl p-3 space-y-2">
        <label class="nhan" for="ct-thu">Xem trước với kích thước khách đặt</label>
        <input id="ct-thu" v-model="f.thu" class="o-nhap" placeholder='"2m4", "1m6 x 80cm"' />
        <p v-if="xemTruoc?.loi" class="text-sm font-bold text-amber-800">{{ xemTruoc.loi }}</p>
        <div v-else-if="xemTruoc" class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span class="text-2xl font-extrabold text-do">{{ tien(xemTruoc.gia) }}</span>
          <span class="text-sm">Giá sàn {{ tien(xemTruoc.san) }} • Giá vốn ước {{ tien(xemTruoc.von) }}</span>
        </div>
      </div>

      <p v-if="loi" class="text-do font-bold" role="alert">{{ loi }}</p>
      <p class="text-xs text-slate-600">Đơn và báo giá đã lập giữ nguyên giá cũ (đã chụp lại lúc chốt). Mọi lần sửa được ghi vào nhật ký.</p>
      <button class="nut-do w-full" :disabled="dangLuu">{{ dangLuu ? 'Đang lưu…' : 'Lưu công thức' }}</button>
    </form>
  </HopThoai>
</template>
