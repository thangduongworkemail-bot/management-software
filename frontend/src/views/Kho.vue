<script setup>
import { computed, onMounted, ref } from 'vue'
import { get, post, taiFileLen } from '../api'
import { LOAI_SO_CAI, kichThuoc, ngayGio, tien } from '../lib/format'
import { bao, laChu, xemGiaVon } from '../store'
import HopThoai from '../components/HopThoai.vue'
import SuaHangHoa from '../components/SuaHangHoa.vue'

const tab = ref('ton')
const hang = ref([])
const soCai = ref([])
const giuCho = ref([])
const xuong = ref([])
const phieu = ref([])
const tatCa = ref([])

async function tai() {
  ;[hang.value, soCai.value, giuCho.value, xuong.value, phieu.value, tatCa.value] = await Promise.all([
    get('/hang-hoa'), get('/kho/so-cai?gioi_han=150'), get('/kho/giu-cho'), get('/kho/xuong'), get('/kho/phieu-nhap'),
    laChu() ? get('/hang-hoa?ca_ngung_ban=true') : []])
}
onMounted(tai)
const bienThe = computed(() => hang.value.filter(h => h.kieu === 'BIEN_THE' && !h.dat_theo_kich_thuoc))

// --- Phiếu nhập ------------------------------------------------------------
const pn = ref({ nha_cung_cap_id: null, dong: [{ bien_the_id: null, so_luong: 1, gia_von_don_vi: 0 }], ghi_chu: '', file: null })
async function luuPhieu() {
  try {
    const anh = pn.value.file ? await taiFileLen(pn.value.file, 'chung-tu-nhap') : null
    const kq = await post('/kho/phieu-nhap', { nha_cung_cap_id: pn.value.nha_cung_cap_id, ghi_chu: pn.value.ghi_chu || null,
      anh_chung_tu_url: anh, dong: pn.value.dong.filter(d => d.bien_the_id) })
    bao(`Đã nhập kho phiếu ${kq.ma}`, 'thanh-cong')
    pn.value = { nha_cung_cap_id: null, dong: [{ bien_the_id: null, so_luong: 1, gia_von_don_vi: 0 }], ghi_chu: '', file: null }
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

// --- Xưởng mới ---------------------------------------------------------------
const XUONG_TRONG = { ten: '', lien_he: '', so_dien_thoai: '', dia_chi: '', loai_hang: '', ma_so_thue: '', han_thanh_toan_ngay: 30, ghi_chu: '' }
const xm = ref(null)
async function luuXuong() {
  try {
    const x = await post('/kho/xuong', xm.value)
    bao(`Đã thêm ${x.ten}`, 'thanh-cong')
    xuong.value = await get('/kho/xuong')
    pn.value.nha_cung_cap_id = x.id
    xm.value = null
  } catch (e) { bao(e.message, 'loi') }
}

// --- Kiểm kê -----------------------------------------------------------------
const dem = ref({})
const lyDoKiemKe = ref('')
const hienDaXoa = ref(false)
const dsKiemKe = computed(() => tatCa.value.filter(h => h.kieu === 'BIEN_THE' && (hienDaXoa.value || h.dang_ban)))
const lechCua = (h) => (dem.value[h.id] === '' || dem.value[h.id] === undefined ? null : dem.value[h.id] - h.ton_hien_co)
const dongLech = computed(() => dsKiemKe.value.filter(h => h.dang_ban && !h.dat_theo_kich_thuoc && lechCua(h)))

async function ghiKiemKe() {
  try {
    const kq = await post('/kho/kiem-ke', { ly_do: lyDoKiemKe.value,
      dong: dongLech.value.map(h => ({ bien_the_id: h.id, so_thuc_te: dem.value[h.id] })) })
    bao(`Đã ghi ${kq.length} dòng điều chỉnh vào sổ cái`, 'thanh-cong')
    dem.value = {}
    lyDoKiemKe.value = ''
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

const sua = ref({ mo: false, hang: null })
const xoa = ref(null)
async function xacNhanXoa() {
  try {
    await post(`/hang-hoa/bien-the/${xoa.value.hang.id}/xoa`, { ly_do: xoa.value.ly_do })
    bao(`Đã xóa ${xoa.value.hang.ma} khỏi danh mục`, 'thanh-cong')
    xoa.value = null
    tai()
  } catch (e) { bao(e.message, 'loi') }
}
async function khoiPhuc(h) {
  try {
    await post(`/hang-hoa/bien-the/${h.id}/khoi-phuc`)
    bao(`Đã khôi phục ${h.ma}`, 'thanh-cong')
    tai()
  } catch (e) { bao(e.message, 'loi') }
}
const tomTat = (h) => [h.loai_go && `Gỗ ${h.loai_go}`, h.mau_sac, h.hoan_thien, kichThuoc(h)].filter(Boolean).join(' • ')

const TABS = computed(() => [['ton', 'Tồn kho'], ...(laChu() ? [['kiem-ke', 'Kiểm kê & hàng hóa']] : []), ['so-cai', 'Sổ cái'],
  ['giu-cho', 'Đang giữ chỗ'], ['nhap', 'Nhập kho'], ['phieu', 'Phiếu nhập']])
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-1">
      <button v-for="[ma, ten] in TABS" :key="ma" :class="tab === ma ? 'nut-do' : 'nut-vien'" class="nut-nho" @click="tab = ma">{{ ten }}</button>
    </div>

    <div v-if="tab === 'ton'" class="the p-0 overflow-x-auto">
      <table class="bang">
        <thead><tr><th>Mã</th><th>Mặt hàng</th><th class="text-center">Hiện có</th><th class="text-center">Đang giữ</th><th class="text-center">Khả dụng</th><th class="text-right">Niêm yết</th><th v-if="xemGiaVon()" class="text-right">Giá vốn BQ</th></tr></thead>
        <tbody>
          <tr v-for="h in hang.filter(x => !x.dat_theo_kich_thuoc)" :key="`${h.kieu}-${h.id}`">
            <td class="font-mono text-xs font-bold">{{ h.ma }}</td>
            <td>{{ h.ten }} <span v-if="h.kieu === 'BO'" class="huy-hieu-xam">BỘ</span></td>
            <td class="text-center">{{ h.ton_hien_co }}</td>
            <td class="text-center">{{ h.dang_giu_cho }}</td>
            <td class="text-center"><span :class="h.ton_kha_dung <= h.ton_toi_thieu ? 'huy-hieu-loi' : 'font-extrabold'">{{ h.ton_kha_dung }}</span></td>
            <td class="text-right">{{ tien(h.gia_niem_yet) }}</td>
            <td v-if="xemGiaVon()" class="text-right">{{ tien(h.gia_von) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="p-3 text-xs">Tồn khả dụng = Tồn hiện có − Đang giữ chỗ. Bộ sản phẩm tính theo thành phần thiếu nhiều nhất.</p>
    </div>

    <div v-if="tab === 'kiem-ke'" class="space-y-3">
      <div class="the flex flex-wrap items-end gap-3">
        <div class="flex-1 min-w-[16rem]">
          <div class="tieu-de">Kiểm kê &amp; quản lý hàng hóa</div>
          <p class="text-sm">Nhập số <b>thực đếm</b>; hệ thống tự tính chênh lệch và ghi dòng điều chỉnh vào sổ cái (không sửa số cũ).
            Sửa, thêm hoặc xóa mặt hàng ngay tại đây.</p>
        </div>
        <label class="flex items-center gap-2 text-sm font-bold"><input v-model="hienDaXoa" type="checkbox" class="w-5 h-5 accent-do" /> Hiện hàng đã xóa</label>
        <button class="nut-do nut-nho" @click="sua = { mo: true, hang: null }">+ Thêm mặt hàng</button>
      </div>

      <div class="the p-0 overflow-x-auto">
        <table class="bang">
          <thead><tr><th>Mã</th><th>Mặt hàng</th><th class="text-center">Sổ sách</th><th class="text-center">Đang giữ</th>
            <th class="text-center">Thực đếm</th><th class="text-center">Lệch</th><th class="text-right">Thao tác</th></tr></thead>
          <tbody>
            <tr v-for="h in dsKiemKe" :key="h.id" :class="!h.dang_ban && 'opacity-60'">
              <td class="font-mono text-xs font-bold">{{ h.ma }}</td>
              <td><div class="font-extrabold">{{ h.ten }} <span v-if="!h.dang_ban" class="huy-hieu-xam">ĐÃ XÓA</span></div>
                <div class="text-xs text-slate-600">{{ tomTat(h) }}</div></td>
              <template v-if="h.dat_theo_kich_thuoc">
                <td colspan="4" class="text-center text-xs">Hàng đặt theo kích thước — không giữ tồn</td>
              </template>
              <template v-else>
                <td class="text-center font-bold">{{ h.ton_hien_co }}</td>
                <td class="text-center">{{ h.dang_giu_cho }}</td>
                <td class="text-center">
                  <input v-if="h.dang_ban" v-model.number="dem[h.id]" type="number" :min="h.dang_giu_cho"
                    class="o-nhap min-h-[40px] w-20 px-2 text-center" :aria-label="`Số thực đếm ${h.ma}`" :placeholder="String(h.ton_hien_co)" />
                </td>
                <td class="text-center font-extrabold">
                  <span v-if="lechCua(h)" :class="lechCua(h) > 0 ? 'text-emerald-700' : 'text-do'">{{ lechCua(h) > 0 ? '+' : '' }}{{ lechCua(h) }}</span>
                  <span v-else-if="lechCua(h) === 0" class="text-xs">khớp</span>
                </td>
              </template>
              <td class="text-right whitespace-nowrap">
                <template v-if="h.dang_ban">
                  <button class="nut-vien nut-nho" @click="sua = { mo: true, hang: h }">Sửa</button>
                  <button class="nut-vien nut-nho ml-1 text-do border-do" @click="xoa = { hang: h, ly_do: '' }">Xóa</button>
                </template>
                <button v-else class="nut-vien nut-nho" @click="khoiPhuc(h)">Khôi phục</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <form class="the flex flex-wrap items-end gap-3 sticky bottom-2" @submit.prevent="ghiKiemKe">
        <label class="flex-1 min-w-[16rem]"><span class="nhan">Lý do kiểm kê (bắt buộc)</span>
          <input v-model="lyDoKiemKe" class="o-nhap" minlength="3" required placeholder="VD: Kiểm kê cuối tháng 10/2026" /></label>
        <button class="nut-do" :disabled="!dongLech.length">Ghi kiểm kê ({{ dongLech.length }} dòng lệch)</button>
      </form>
    </div>

    <div v-if="tab === 'so-cai'" class="the p-0 overflow-x-auto">
      <p class="p-3 text-sm font-bold">Sổ cái chỉ ghi thêm — không sửa, không xóa. Mọi số tồn đều tính lại từ đây.</p>
      <table class="bang">
        <thead><tr><th>Thời điểm</th><th>Loại</th><th>Mặt hàng</th><th class="text-center">Biến động</th><th>Tham chiếu</th><th>Người</th></tr></thead>
        <tbody>
          <tr v-for="s in soCai" :key="s.id">
            <td class="text-xs whitespace-nowrap">{{ ngayGio(s.thoi_diem) }}</td>
            <td><span :class="['GIU_CHO', 'XUAT'].includes(s.loai) ? 'huy-hieu-loi' : 'huy-hieu-xam'">{{ LOAI_SO_CAI[s.loai] }}</span></td>
            <td>{{ s.ten_hien_thi }}</td>
            <td class="text-center font-extrabold">{{ s.so_luong > 0 ? '+' : '' }}{{ s.so_luong }}</td>
            <td class="text-xs">{{ s.tham_chieu }}<template v-if="s.ly_do"> • {{ s.ly_do }}</template></td>
            <td class="text-xs">{{ s.nguoi_thuc_hien || 'Hệ thống' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="tab === 'giu-cho'" class="grid md:grid-cols-2 gap-3">
      <div v-for="g in giuCho" :key="g.id" class="the">
        <div class="flex justify-between font-extrabold"><span>#{{ g.ma }} ({{ tien(g.tong_tien) }})</span>
          <span v-if="g.giu_cho_den" class="text-do">Hết hạn {{ ngayGio(g.giu_cho_den) }}</span></div>
        <div class="text-sm">{{ g.tom_tat }}</div>
      </div>
      <p v-if="!giuCho.length" class="the">Không có đơn nào đang giữ hàng.</p>
    </div>

    <div v-if="tab === 'nhap'" class="grid lg:grid-cols-2 gap-4">
      <form class="the space-y-3" @submit.prevent="luuPhieu">
        <div class="tieu-de">Phiếu nhập kho theo xưởng</div>
        <div>
          <label class="nhan" for="ncc">Xưởng giao hàng</label>
          <div class="flex gap-2">
            <select id="ncc" v-model="pn.nha_cung_cap_id" class="o-nhap" required>
              <option v-for="x in xuong" :key="x.id" :value="x.id">{{ x.ten }}</option>
            </select>
            <button type="button" class="nut-vien whitespace-nowrap" @click="xm = { ...XUONG_TRONG }">+ Xưởng mới</button>
          </div>
        </div>
        <div v-for="(d, i) in pn.dong" :key="i" class="grid grid-cols-12 gap-2 items-end">
          <label class="col-span-6"><span class="nhan">Mặt hàng</span>
            <select v-model="d.bien_the_id" class="o-nhap" required>
              <option v-for="h in bienThe" :key="h.id" :value="h.id">{{ h.ma }}</option>
            </select></label>
          <label class="col-span-2"><span class="nhan">SL</span><input v-model.number="d.so_luong" type="number" min="1" class="o-nhap" required /></label>
          <label class="col-span-4"><span class="nhan">Giá vốn/đv</span><input v-model.number="d.gia_von_don_vi" type="number" min="0" step="1000" class="o-nhap" required /></label>
        </div>
        <button type="button" class="nut-vien nut-nho" @click="pn.dong.push({ bien_the_id: null, so_luong: 1, gia_von_don_vi: 0 })">+ Thêm dòng</button>
        <div><label class="nhan" for="pn-anh">Ảnh chứng từ</label><input id="pn-anh" type="file" accept="image/*" class="o-nhap py-2" @change="pn.file = $event.target.files[0]" /></div>
        <div><label class="nhan" for="pn-gc">Ghi chú</label><input id="pn-gc" v-model="pn.ghi_chu" class="o-nhap" /></div>
        <button class="nut-do w-full">Lưu phiếu nhập</button>
        <p class="text-xs">Giá vốn được tính bình quân gia quyền; công nợ phải trả xưởng tự tăng.</p>
      </form>
      <section class="the space-y-3">
        <div class="flex items-center justify-between gap-2">
          <div class="tieu-de">Xưởng cung cấp ({{ xuong.length }})</div>
          <button class="nut-vien nut-nho" @click="xm = { ...XUONG_TRONG }">+ Thêm xưởng</button>
        </div>
        <div v-for="x in xuong" :key="x.id" class="bg-than-nhat rounded-lg p-3 text-sm">
          <div class="flex justify-between gap-2 font-extrabold"><span>{{ x.ten }}</span>
            <span v-if="xemGiaVon() && x.so_du_cong_no" class="text-do whitespace-nowrap">Nợ {{ tien(x.so_du_cong_no) }}</span></div>
          <div v-if="x.loai_hang">{{ x.loai_hang }}</div>
          <div class="text-xs text-slate-600">{{ [x.lien_he, x.so_dien_thoai, x.dia_chi].filter(Boolean).join(' • ') }}</div>
        </div>
      </section>
    </div>

    <div v-if="tab === 'phieu'" class="the p-0 overflow-x-auto">
      <table class="bang">
        <thead><tr><th>Mã phiếu</th><th>Xưởng</th><th>Ngày</th><th class="text-center">Số lượng</th><th v-if="xemGiaVon()" class="text-right">Tổng tiền</th><th>Người lập</th></tr></thead>
        <tbody>
          <tr v-for="p in phieu" :key="p.id">
            <td class="font-mono font-bold">{{ p.ma }}</td><td>{{ p.xuong }}</td><td>{{ ngayGio(p.ngay_nhap) }}</td>
            <td class="text-center">{{ p.tong_so_luong }}</td><td v-if="xemGiaVon()" class="text-right">{{ tien(p.tong_tien) }}</td><td>{{ p.nguoi_lap }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <HopThoai :mo="!!xm" tieu-de="Thêm xưởng cung cấp" @dong="xm = null">
      <form v-if="xm" class="grid sm:grid-cols-2 gap-3" @submit.prevent="luuXuong">
        <label class="sm:col-span-2"><span class="nhan">Tên xưởng *</span><input v-model="xm.ten" class="o-nhap" required minlength="2" placeholder="VD: Xưởng Mộc Đồng Kỵ" /></label>
        <label><span class="nhan">Người liên hệ</span><input v-model="xm.lien_he" class="o-nhap" /></label>
        <label><span class="nhan">Số điện thoại</span><input v-model="xm.so_dien_thoai" type="tel" class="o-nhap" pattern="[0-9 +().\-]{6,20}" /></label>
        <label class="sm:col-span-2"><span class="nhan">Địa chỉ</span><input v-model="xm.dia_chi" class="o-nhap" /></label>
        <label class="sm:col-span-2"><span class="nhan">Mặt hàng cung cấp</span><input v-model="xm.loai_hang" class="o-nhap" placeholder="VD: Bàn ghế, giường" /></label>
        <label><span class="nhan">Mã số thuế</span><input v-model="xm.ma_so_thue" class="o-nhap" pattern="[0-9\-]{10,14}" /></label>
        <label><span class="nhan">Hạn thanh toán (ngày)</span><input v-model.number="xm.han_thanh_toan_ngay" type="number" min="0" max="365" class="o-nhap" /></label>
        <label class="sm:col-span-2"><span class="nhan">Ghi chú</span><input v-model="xm.ghi_chu" class="o-nhap" /></label>
        <button class="nut-do sm:col-span-2">Lưu xưởng</button>
      </form>
    </HopThoai>

    <HopThoai :mo="!!xoa" :tieu-de="`Xóa ${xoa?.hang.ma || ''} khỏi danh mục`" @dong="xoa = null">
      <form v-if="xoa" class="space-y-3" @submit.prevent="xacNhanXoa">
        <p class="text-sm"><b>{{ xoa.hang.ten }}</b> sẽ ẩn khỏi bán hàng, tra giá và nhập kho.
          <template v-if="xoa.hang.ton_hien_co"> Số tồn còn lại (<b>{{ xoa.hang.ton_hien_co }}</b>) được ghi điều chỉnh về 0 trong sổ cái.</template>
          Đơn cũ, lịch sử giá và sổ cái giữ nguyên; có thể khôi phục bất cứ lúc nào.</p>
        <label class="block"><span class="nhan">Lý do (bắt buộc)</span><input v-model="xoa.ly_do" class="o-nhap" minlength="3" required placeholder="VD: Ngừng nhập mẫu này" /></label>
        <button class="nut-do w-full">Xóa khỏi danh mục</button>
      </form>
    </HopThoai>

    <SuaHangHoa :mo="sua.mo" :hang="sua.hang" @dong="sua.mo = false" @da-luu="tai" />
  </div>
</template>
