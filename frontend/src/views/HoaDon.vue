<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, get, post, put } from '../api'
import { ngayGio, tien } from '../lib/format'
import { bao, laChu, trangThai } from '../store'
import HopThoai from '../components/HopThoai.vue'
import HuyHieu from '../components/HuyHieu.vue'

const hoaDon = ref([])
const congNo = ref(null)
const sua = ref(null)

async function tai() {
  hoaDon.value = await get('/hoa-don')
  if (laChu()) congNo.value = await get('/cong-no')
}
onMounted(tai)
watch(() => trangThai.suKien, tai)

async function luuNguoiMua() {
  try {
    const { id, ten_nguoi_mua, ma_so_thue, dia_chi, email } = sua.value
    await put(`/hoa-don/${id}/nguoi-mua`, { ten_nguoi_mua, ma_so_thue: ma_so_thue || null, dia_chi, email })
    bao('Đã cập nhật — hóa đơn quay lại hàng đợi', 'thanh-cong')
    sua.value = null
    tai()
  } catch (e) { bao(e.message, 'loi') }
}

async function lam(duongDan, body, thongBao) {
  try { await post(duongDan, body); bao(thongBao, 'thanh-cong'); tai() } catch (e) { bao(e.message, 'loi') }
}

function ghiSo(hd) {
  const so = prompt('Số hóa đơn đã xuất trên cổng của nhà cung cấp:')
  if (so) lam(`/hoa-don/${hd.id}/ghi-so`, { ky_hieu: hd.ky_hieu || 'C26TKV', so_hoa_don: so }, 'Đã ghi số hóa đơn')
}

async function taiGoi(dinhDang) {
  const res = await api(`/hoa-don/goi-du-lieu?dinh_dang=${dinhDang}`, { tho: true })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(await res.blob())
  a.download = `hoa-don-cho-xuat.${dinhDang}`
  a.click()
}

function traNoXuong(x) {
  const soTien = Number(prompt(`Trả nợ ${x.ten} (đang nợ ${tien(x.so_du_cong_no)}):`))
  if (soTien > 0) lam(`/kho/xuong/${x.id}/chi-tra`, { so_tien: soTien }, 'Đã ghi trả nợ xưởng')
}
</script>

<template>
  <div class="grid lg:grid-cols-12 gap-4">
    <section class="lg:col-span-7 the space-y-3">
      <div class="flex flex-wrap justify-between gap-2 items-center">
        <div class="font-extrabold">HÀNG ĐỢI HÓA ĐƠN ĐIỆN TỬ (KHÔNG CHẶN BÁN HÀNG)</div>
        <div v-if="laChu()" class="flex gap-2">
          <button class="nut-vien nut-nho" @click="taiGoi('csv')">Xuất CSV</button>
          <button class="nut-vien nut-nho" @click="taiGoi('json')">Xuất JSON</button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="bang">
          <thead><tr><th>Đơn</th><th>Người mua & MST</th><th class="text-right">Tổng</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>
            <tr v-for="hd in hoaDon" :key="hd.id">
              <td class="font-mono font-bold text-do">{{ hd.ma_don }}</td>
              <td>{{ hd.ten_nguoi_mua || '—' }}<div class="text-xs">{{ hd.ma_so_thue ? `MST ${hd.ma_so_thue}` : 'Chưa có MST' }}</div></td>
              <td class="text-right font-bold">{{ tien(hd.tong_tien) }}</td>
              <td><HuyHieu :ma="hd.trang_thai" />
                <div class="text-xs mt-1">
                  <template v-if="hd.so_hoa_don">Số {{ hd.ky_hieu }}-{{ hd.so_hoa_don }} • {{ ngayGio(hd.xuat_luc) }}
                    <a v-if="hd.link_xml" :href="hd.link_xml" target="_blank" class="underline">XML</a></template>
                  <template v-else-if="hd.so_lan_thu">Đã thử {{ hd.so_lan_thu }} lần<span v-if="hd.loi_cuoi"> — {{ hd.loi_cuoi }}</span></template>
                </div></td>
              <td class="text-right whitespace-nowrap space-x-1">
                <button v-if="hd.trang_thai !== 'DA_XUAT'" class="text-do font-extrabold" @click="sua = { ...hd }">Bổ sung</button>
                <button v-if="laChu() && hd.trang_thai === 'LOI'" class="text-do font-extrabold" @click="lam(`/hoa-don/${hd.id}/thu-lai`, {}, 'Đã đưa lại vào hàng đợi')">Thử lại</button>
                <button v-if="laChu() && hd.trang_thai !== 'DA_XUAT'" class="text-do font-extrabold" @click="ghiSo(hd)">Ghi số HĐ</button>
              </td>
            </tr>
            <tr v-if="!hoaDon.length"><td colspan="5" class="text-center">Không có hóa đơn.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="congNo" class="lg:col-span-5 space-y-4">
      <div class="the space-y-2 text-sm">
        <div class="font-extrabold">KHÁCH ĐẶT CỌC / MUA CHỊU</div>
        <p v-if="!congNo.khach_hang.length">Không có khách nợ.</p>
        <div v-for="k in congNo.khach_hang" :key="k.id" class="bg-than-nhat rounded-lg p-3">
          <div class="flex justify-between font-extrabold"><span>{{ k.ten }}</span><span class="text-do">{{ tien(k.du_no) }}</span></div>
          <div v-for="d in k.don" :key="d.id">Đơn #{{ d.ma }} còn {{ tien(d.con_no) }}</div>
        </div>
      </div>
      <div class="the space-y-2 text-sm">
        <div class="font-extrabold">NỢ PHẢI TRẢ XƯỞNG GỖ</div>
        <div v-for="x in congNo.xuong" :key="x.id" class="bg-than-nhat rounded-lg p-3 flex justify-between items-center gap-2">
          <div><div class="font-extrabold">{{ x.ten }}</div><div>Hạn thanh toán: {{ x.han_thanh_toan ? new Date(x.han_thanh_toan).toLocaleDateString('vi-VN') : '—' }}</div></div>
          <div class="text-right"><div class="font-extrabold text-do">{{ tien(x.so_du_cong_no) }}</div>
            <button class="text-xs underline" @click="traNoXuong(x)">Ghi trả nợ</button></div>
        </div>
      </div>
    </section>

    <HopThoai :mo="!!sua" :tieu-de="`Thông tin người mua — đơn #${sua?.ma_don}`" @dong="sua = null">
      <form v-if="sua" class="space-y-3" @submit.prevent="luuNguoiMua">
        <label class="block"><span class="nhan">Tên người mua / đơn vị</span><input v-model="sua.ten_nguoi_mua" class="o-nhap" /></label>
        <label class="block"><span class="nhan">Mã số thuế</span><input v-model="sua.ma_so_thue" class="o-nhap" inputmode="numeric" pattern="[0-9]{10}(-?[0-9]{3})?" /></label>
        <label class="block"><span class="nhan">Địa chỉ</span><input v-model="sua.dia_chi" class="o-nhap" /></label>
        <label class="block"><span class="nhan">Email nhận hóa đơn</span><input v-model="sua.email" type="email" class="o-nhap" /></label>
        <button class="nut-do w-full">Lưu & đưa vào hàng đợi</button>
      </form>
    </HopThoai>
  </div>
</template>
