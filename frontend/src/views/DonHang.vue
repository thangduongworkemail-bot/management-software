<script setup>
import { onMounted, ref, watch } from 'vue'
import { get, post } from '../api'
import { ngayGio, tien } from '../lib/format'
import { bao, laChu, trangThai, xemGiaVon } from '../store'
import HopThoai from '../components/HopThoai.vue'
import HuyHieu from '../components/HuyHieu.vue'

const LOC = [['', 'Tất cả'], ['CHO_DUYET_GIA', 'Chờ duyệt giá'], ['CHO_THANH_TOAN', 'Chờ thanh toán'], ['CON_NO', 'Còn nợ'],
  ['DA_THANH_TOAN', 'Đã thanh toán'], ['CHO_XUONG_GIAO', 'Chờ xưởng giao'], ['XUNG_DOT_TON', 'Xung đột tồn'], ['HET_HAN', 'Hết hạn']]
const loc = ref('')
const q = ref('')
const ds = ref([])
const chiTiet = ref(null)

async function tai() {
  const p = new URLSearchParams()
  if (loc.value) p.set('trang_thai', loc.value)
  if (q.value) p.set('q', q.value)
  ds.value = await get(`/don-hang?${p}`)
}
onMounted(tai)
watch([loc], tai)
watch(() => trangThai.suKien, () => { tai(); if (chiTiet.value) mo(chiTiet.value.id) })

async function mo(id) { chiTiet.value = await get(`/don-hang/${id}`) }

async function thaoTac(duongDan, body = {}, thanhCong = 'Đã cập nhật') {
  try {
    const kq = await post(`/don-hang/${chiTiet.value.id}/${duongDan}`, body)
    chiTiet.value = kq.don || kq
    bao(thanhCong, 'thanh-cong')
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

function huy() {
  const lyDo = prompt('Lý do hủy đơn:')
  if (lyDo) thaoTac('huy', { ly_do: lyDo }, 'Đã hủy đơn và nhả hàng giữ chỗ')
}
function traHang() {
  const lyDo = prompt('Lý do khách trả hàng:')
  if (lyDo) thaoTac('tra-hang', { ly_do: lyDo }, 'Đã nhập lại kho hàng trả')
}
function thuTien(laCoc) {
  const soTien = Number(prompt(laCoc ? 'Số tiền khách đặt cọc:' : 'Số tiền mặt thu:', laCoc ? '' : chiTiet.value.con_phai_thu))
  if (soTien > 0) thaoTac('thanh-toan', { so_tien: soTien, la_coc: laCoc }, 'Đã ghi nhận tiền')
}
</script>

<template>
  <div class="space-y-4">
    <div class="the flex flex-wrap gap-2 items-end">
      <div class="flex-1 min-w-[220px]">
        <label class="nhan" for="tim-don">Tìm theo mã đơn, tên hoặc SĐT khách</label>
        <form @submit.prevent="tai"><input id="tim-don" v-model="q" class="o-nhap" placeholder="KV2610…" /></form>
      </div>
      <div class="flex flex-wrap gap-1">
        <button v-for="[ma, ten] in LOC" :key="ma" :class="loc === ma ? 'nut-do' : 'nut-vien'" class="nut-nho" @click="loc = ma">{{ ten }}</button>
      </div>
    </div>

    <div class="the p-0 overflow-x-auto">
      <table class="bang">
        <thead><tr><th>Mã đơn</th><th>Khách</th><th>Hàng</th><th class="text-right">Tổng</th><th class="text-right">Còn thu</th><th>Trạng thái</th><th>Lập lúc</th></tr></thead>
        <tbody>
          <tr v-for="d in ds" :key="d.id" class="hover:bg-than-nhat cursor-pointer" @click="mo(d.id)">
            <td class="font-mono font-bold text-do">{{ d.ma }}</td>
            <td>{{ d.ten_khach || 'Khách lẻ' }}</td>
            <td class="max-w-[280px] truncate">{{ d.tom_tat }}</td>
            <td class="text-right font-bold">{{ tien(d.tong_tien) }}</td>
            <td class="text-right">{{ tien(d.tong_tien - d.giam_tru - d.da_thu) }}</td>
            <td class="space-x-1"><HuyHieu :ma="d.trang_thai" /><HuyHieu v-if="d.trang_thai_giao !== 'CHUA_GIAO'" :ma="d.trang_thai_giao" /></td>
            <td class="text-xs">{{ ngayGio(d.tao_luc) }} • {{ d.nguoi_lap }}</td>
          </tr>
          <tr v-if="!ds.length"><td colspan="7" class="text-center text-slate-600">Không có đơn.</td></tr>
        </tbody>
      </table>
    </div>

    <HopThoai :mo="!!chiTiet" :tieu-de="`Đơn #${chiTiet?.ma}`" @dong="chiTiet = null">
      <template v-if="chiTiet">
        <div class="flex flex-wrap gap-1"><HuyHieu :ma="chiTiet.trang_thai" /><HuyHieu :ma="chiTiet.trang_thai_giao" /><HuyHieu :ma="chiTiet.hoa_don?.trang_thai" /></div>
        <div class="text-sm">Khách: <strong>{{ chiTiet.ten_khach || 'Khách lẻ' }}</strong> {{ chiTiet.so_dien_thoai || '' }} • Lập bởi {{ chiTiet.nguoi_lap }}</div>
        <table class="bang">
          <tbody>
            <tr v-for="l in chiTiet.dong" :key="l.id">
              <td>{{ l.so_luong }} × {{ l.mo_ta }}
                <div v-if="l.tham_so?.dien_giai" class="text-xs text-slate-600">{{ l.tham_so.dien_giai }}</div>
                <div v-if="xemGiaVon()" class="text-xs text-slate-600">Niêm yết {{ tien(l.gia_niem_yet_chup) }} • Sàn {{ tien(l.gia_san_chup) }} • Vốn {{ tien(l.gia_von_chup) }}</div>
              </td>
              <td class="text-right font-bold">{{ tien(l.thanh_tien) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="grid grid-cols-3 gap-2 text-sm text-center">
          <div class="bg-than-nhat rounded p-2">Tổng<br /><strong>{{ tien(chiTiet.tong_tien) }}</strong></div>
          <div class="bg-than-nhat rounded p-2">Đã thu<br /><strong>{{ tien(chiTiet.da_thu) }}</strong></div>
          <div class="bg-than-nhat rounded p-2">Còn thu<br /><strong class="text-do">{{ tien(chiTiet.con_phai_thu) }}</strong></div>
        </div>
        <div v-if="chiTiet.thanh_toan.length" class="text-sm space-y-1">
          <div class="font-bold">Các khoản thu</div>
          <div v-for="t in chiTiet.thanh_toan" :key="t.id">
            {{ ngayGio(t.thoi_diem) }} • {{ t.phuong_thuc === 'TIEN_MAT' ? 'Tiền mặt' : 'Chuyển khoản' }}{{ t.xac_nhan_tay ? ' (xác nhận tay)' : '' }}
            • <strong>{{ tien(t.so_tien) }}</strong>
            <span v-for="b in t.bang_chung" :key="b.gia_tri" class="huy-hieu-xam ml-1">{{ b.kieu === 'BON_SO_CUOI' ? `*${b.gia_tri}` : 'Ảnh biên lai' }}</span>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button v-if="chiTiet.con_phai_thu > 0 && !['DA_HUY', 'CHO_DUYET_GIA'].includes(chiTiet.trang_thai)" class="nut-vien nut-nho" @click="thuTien(false)">Thu tiền mặt</button>
          <button v-if="chiTiet.trang_thai === 'CHO_THANH_TOAN'" class="nut-vien nut-nho" @click="thuTien(true)">Nhận đặt cọc</button>
          <button v-if="laChu() && ['CHO_THANH_TOAN', 'CON_NO'].includes(chiTiet.trang_thai) && chiTiet.trang_thai_giao === 'CHUA_GIAO' && chiTiet.khach_hang_id" class="nut-vien nut-nho" @click="thaoTac('ban-chiu', {}, 'Đã giao hàng, ghi công nợ khách')">Cho mua chịu</button>
          <button v-if="chiTiet.trang_thai_giao === 'CHO_XUONG_GIAO' && ['DA_THANH_TOAN', 'CON_NO'].includes(chiTiet.trang_thai)" class="nut-vien nut-nho" @click="thaoTac('giao-hang', {}, 'Đã giao hàng')">Hàng về — giao khách</button>
          <template v-if="laChu() && chiTiet.trang_thai_giao === 'XUNG_DOT_TON'">
            <button class="nut-do nut-nho" @click="thaoTac('xung-dot', { cach: 'CHO_XUONG_GIAO' })">Chuyển sang "Chờ xưởng giao"</button>
            <button class="nut-vien nut-nho" @click="thaoTac('xung-dot', { cach: 'HUY' })">Báo khách đổi mẫu (hủy)</button>
          </template>
          <button v-if="!['DA_THANH_TOAN', 'DA_HUY'].includes(chiTiet.trang_thai)" class="nut-vien nut-nho" @click="huy">Hủy đơn</button>
          <button v-if="laChu() && ['DA_THANH_TOAN', 'CON_NO'].includes(chiTiet.trang_thai) && chiTiet.trang_thai_giao === 'DA_GIAO'" class="nut-vien nut-nho" @click="traHang">Khách trả hàng</button>
          <router-link :to="`/phieu/${chiTiet.id}`" target="_blank" class="nut-vien nut-nho">In phiếu</router-link>
        </div>
      </template>
    </HopThoai>
  </div>
</template>
