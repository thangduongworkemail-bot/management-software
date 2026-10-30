<script setup>
import { onMounted, ref } from 'vue'
import { get, post } from '../api'
import { kichThuoc, ngayGio, thongSo, tien } from '../lib/format'
import { bao, laChu, xemGiaVon } from '../store'
import HopThoai from '../components/HopThoai.vue'
import SuaHangHoa from '../components/SuaHangHoa.vue'

const hang = ref([])
const loaiHang = ref([])
const loc = ref(null)
const dongNghia = ref([])
const chiTiet = ref(null)
const lichSu = ref([])

async function tai() {
  ;[hang.value, loaiHang.value, dongNghia.value] = await Promise.all([
    get(loc.value ? `/hang-hoa?loai_hang_id=${loc.value}` : '/hang-hoa'), get('/hang-hoa/loai-hang'), get('/hang-hoa/tu-dong-nghia')])
}
onMounted(tai)

async function mo(h) {
  chiTiet.value = { ...(h.kieu === 'BO' ? await get(`/hang-hoa/bo/${h.id}`) : await get(`/hang-hoa/bien-the/${h.id}`)),
                    giaMoi: { loai_gia: 'GIA_NIEM_YET', so_tien: h.gia_niem_yet }, thu: { kich_thuoc: '', kq: null, loi: '' } }
  lichSu.value = laChu() && h.kieu === 'BIEN_THE' ? await get(`/hang-hoa/bien-the/${h.id}/lich-su-gia`) : []
}

async function datGia() {
  try {
    await post(`/hang-hoa/bien-the/${chiTiet.value.id}/gia`, chiTiet.value.giaMoi)
    bao('Đã đóng mức giá cũ và mở mức giá mới', 'thanh-cong')
    await mo(chiTiet.value)
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

async function thuTinh() {
  const t = chiTiet.value.thu
  t.loi = ''
  try { t.kq = await post(`/hang-hoa/bien-the/${chiTiet.value.id}/tinh-gia`, { kich_thuoc: t.kich_thuoc }) } catch (e) { t.kq = null; t.loi = e.message }
}

const dn = ref({ tu_khoa: '', tu_chuan: '' })
async function themDongNghia() {
  try {
    await post('/hang-hoa/tu-dong-nghia', dn.value)
    dn.value = { tu_khoa: '', tu_chuan: '' }
    dongNghia.value = await get('/hang-hoa/tu-dong-nghia')
  } catch (e) { bao(e.message, 'loi') }
}

const sua = ref({ mo: false, hang: null })
async function daLuu(kq) {
  await tai()
  if (chiTiet.value && kq.id === chiTiet.value.id) await mo(kq)
}

const TEN_GIA = { GIA_VON: 'Giá vốn', GIA_SAN: 'Giá sàn', GIA_NIEM_YET: 'Giá niêm yết', GIA_NHOM_KHACH: 'Giá nhóm khách' }
</script>

<template>
  <div class="grid lg:grid-cols-12 gap-4">
    <aside class="lg:col-span-3 space-y-4">
      <div class="the space-y-1">
        <div class="font-extrabold mb-2">NHÓM HÀNG</div>
        <button :class="!loc ? 'bg-do text-white' : 'bg-than-nhat'" class="w-full text-left rounded-lg p-3 font-bold" @click="loc = null; tai()">Tất cả</button>
        <button v-for="l in loaiHang" :key="l.id" :class="loc === l.id ? 'bg-do text-white' : 'bg-than-nhat'"
          class="w-full text-left rounded-lg p-3 font-bold flex justify-between" @click="loc = l.id; tai()">
          <span>{{ l.ten }}</span><span>{{ l.so_bien_the }}</span>
        </button>
      </div>
      <div class="the space-y-2 text-sm">
        <div class="font-extrabold">TỪ ĐỒNG NGHĨA KHI TÌM</div>
        <div v-for="d in dongNghia" :key="d.id" class="bg-than-nhat rounded p-2">"{{ d.tu_khoa }}" = {{ d.tu_chuan }}</div>
        <form v-if="laChu()" class="space-y-2" @submit.prevent="themDongNghia">
          <input v-model="dn.tu_khoa" class="o-nhap" placeholder="Khách hay gọi (vd: tủ áo)" aria-label="Từ khách hay gọi" required />
          <input v-model="dn.tu_chuan" class="o-nhap" placeholder="Tên chuẩn (vd: tủ quần áo)" aria-label="Tên chuẩn" required />
          <button class="nut-vien nut-nho w-full">Thêm</button>
        </form>
      </div>
    </aside>

    <section class="lg:col-span-9 the p-0 overflow-x-auto">
      <div class="p-3 flex items-center justify-between gap-2 border-b border-slate-200">
        <span class="font-extrabold">{{ hang.length }} mặt hàng</span>
        <button v-if="laChu()" class="nut-do nut-nho" @click="sua = { mo: true, hang: null }">+ Thêm mặt hàng</button>
      </div>
      <table class="bang">
        <thead><tr><th>Mã</th><th>Tên & quy cách</th><th v-if="xemGiaVon()" class="text-right">Giá vốn</th><th v-if="xemGiaVon()" class="text-right">Giá sàn</th><th class="text-right text-do">Niêm yết</th><th class="text-center">Khả dụng</th></tr></thead>
        <tbody>
          <tr v-for="h in hang" :key="`${h.kieu}-${h.id}`" class="hover:bg-than-nhat cursor-pointer" @click="mo(h)">
            <td class="font-mono text-xs font-bold">{{ h.ma }}</td>
            <td><div class="font-extrabold">{{ h.ten }} <span v-if="h.kieu === 'BO'" class="huy-hieu-xam">BỘ</span></div>
              <div class="text-xs text-slate-600">{{ [h.loai_go && `Gỗ ${h.loai_go}`, h.hoan_thien, kichThuoc(h)].filter(Boolean).join(' • ') }}</div></td>
            <td v-if="xemGiaVon()" class="text-right">{{ tien(h.gia_von) }}</td>
            <td v-if="xemGiaVon()" class="text-right font-bold">{{ tien(h.gia_san) }}</td>
            <td class="text-right font-extrabold text-do">{{ h.dat_theo_kich_thuoc ? 'Theo công thức' : tien(h.gia_niem_yet) }}</td>
            <td class="text-center">{{ h.dat_theo_kich_thuoc ? '—' : h.ton_kha_dung }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <HopThoai :mo="!!chiTiet" :tieu-de="chiTiet?.ten" @dong="chiTiet = null">
      <template v-if="chiTiet">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-mono font-bold">{{ chiTiet.ma }}</span>
          <button v-if="laChu() && chiTiet.kieu === 'BIEN_THE'" class="nut-vien nut-nho" @click="sua = { mo: true, hang: chiTiet }">Sửa thông tin</button>
        </div>
        <p v-if="chiTiet.mo_ta && chiTiet.kieu === 'BIEN_THE'" class="text-sm">{{ chiTiet.mo_ta }}</p>
        <dl v-if="chiTiet.kieu === 'BIEN_THE'" class="grid grid-cols-[auto_1fr] text-sm border border-slate-200 rounded-lg overflow-hidden">
          <template v-for="([nhan, gt], i) in thongSo(chiTiet)" :key="nhan">
            <dt :class="i % 2 ? '' : 'bg-than-nhat'" class="px-3 py-1.5 font-bold text-slate-600">{{ nhan }}</dt>
            <dd :class="i % 2 ? '' : 'bg-than-nhat'" class="px-3 py-1.5 font-semibold">{{ gt }}</dd>
          </template>
        </dl>
        <div v-if="chiTiet.thanh_phan" class="text-sm">
          <div class="font-bold">Thành phần bộ (bán bộ tự trừ tồn từng món):</div>
          <div v-for="t in chiTiet.thanh_phan" :key="t.bien_the_id">{{ t.so_luong }} × {{ t.ten_hien_thi }} (còn {{ t.ton_kha_dung }})</div>
        </div>
        <div v-if="chiTiet.xuong?.length" class="text-sm">
          <div class="font-bold">Xưởng cung cấp:</div>
          <div v-for="x in chiTiet.xuong" :key="x.ten">{{ x.ten }} • mã xưởng {{ x.ma_hang_xuong }} • giao {{ x.so_ngay_giao }} ngày<template v-if="x.gia_nhap"> • nhập {{ tien(x.gia_nhap) }}</template></div>
        </div>
        <div v-if="chiTiet.dat_theo_kich_thuoc" class="space-y-2">
          <div class="font-bold">Thử tính giá đặt riêng</div>
          <form class="flex gap-2" @submit.prevent="thuTinh">
            <input v-model="chiTiet.thu.kich_thuoc" class="o-nhap" placeholder='"2m4", "1m8 x 80cm"…' aria-label="Kích thước" required />
            <button class="nut-vien">Tính</button>
          </form>
          <p v-if="chiTiet.thu.loi" class="text-do font-bold">{{ chiTiet.thu.loi }}</p>
          <div v-if="chiTiet.thu.kq" class="bg-than-nhat rounded p-3 text-sm">{{ chiTiet.thu.kq.dien_giai }}
            <div v-if="xemGiaVon()" class="text-xs mt-1">Giá sàn {{ tien(chiTiet.thu.kq.gia_san) }} • Giá vốn ước {{ tien(chiTiet.thu.kq.gia_von) }}</div></div>
        </div>
        <form v-if="laChu() && chiTiet.kieu === 'BIEN_THE' && !chiTiet.dat_theo_kich_thuoc" class="space-y-2" @submit.prevent="datGia">
          <div class="font-bold">Đổi giá (đóng mức cũ, mở mức mới — không ghi đè)</div>
          <div class="flex gap-2">
            <select v-model="chiTiet.giaMoi.loai_gia" class="o-nhap" aria-label="Loại giá">
              <option value="GIA_NIEM_YET">Giá niêm yết</option><option value="GIA_SAN">Giá sàn</option><option value="GIA_VON">Giá vốn</option>
            </select>
            <input v-model.number="chiTiet.giaMoi.so_tien" type="number" min="0" step="1000" class="o-nhap" aria-label="Số tiền" required />
          </div>
          <button class="nut-do w-full">Áp dụng giá mới</button>
        </form>
        <div v-if="lichSu.length" class="text-xs space-y-1">
          <div class="font-bold text-sm">Lịch sử giá</div>
          <div v-for="g in lichSu" :key="g.id" :class="g.den_ngay ? 'text-slate-500' : 'font-bold'">
            {{ TEN_GIA[g.loai_gia] }} {{ tien(g.so_tien) }} • từ {{ ngayGio(g.tu_ngay) }} {{ g.den_ngay ? `đến ${ngayGio(g.den_ngay)}` : '(đang áp dụng)' }}
            <template v-if="g.nguoi_dat"> • {{ g.nguoi_dat }}</template>
          </div>
        </div>
      </template>
    </HopThoai>
    <SuaHangHoa :mo="sua.mo" :hang="sua.hang" @dong="sua.mo = false" @da-luu="daLuu" />
  </div>
</template>
